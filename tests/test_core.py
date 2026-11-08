import sqlite3
import tempfile
import time
import unittest
from yutong_teams.config import Config
from yutong_teams.control import Coordinator
from yutong_teams.core.contracts import HUMAN, Principal, Forbidden, Conflict
from yutong_teams.core.tasks import validate_graph


class CoreTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.config = Config(self.temp.name)
        for aid in ('one', 'two'):
            self.config.save_agent(dict(id=aid, name=aid, kind='external'))
        self.c = Coordinator(self.config, start=False)
        self.g = self.c.groups.create(dict(name='test', members=['one', 'two']))['id']
        self.p = Principal(actor_id='one', group_id=self.g)
        self.q = Principal(actor_id='two', group_id=self.g)

    def tearDown(self):
        self.c.close()
        self.temp.cleanup()

    def send(self, **kw):
        return self.c.messages.send(HUMAN, self.g, dict(text='work', targets=['one'], **kw))

    def test_delivery_read_reply_are_distinct_facts(self):
        m = self.send(mode='request_reply')
        self.c.messages.acknowledge(self.p, self.g, m['id'], 'delivered')
        d = self.c.repo.require('delivery', m['id']+':one')
        self.assertTrue(d['delivered_at']); self.assertFalse(d['read_at']); self.assertFalse(d['replied_at'])
        self.c.messages.send(self.p, self.g, dict(text='result', reply_to=m['id']))
        d = self.c.repo.require('delivery', d['id'])
        self.assertTrue(d['replied_at']); self.assertFalse(d['read_at'])
        self.c.messages.read_inbox(self.p, self.g, [m['id']])
        self.assertTrue(self.c.repo.require('delivery', d['id'])['read_at'])

    def test_dedupe_is_atomic_and_rejects_changed_payload(self):
        first = self.send(client_id='retry-key')
        self.assertEqual(first, self.send(client_id='retry-key'))
        with self.assertRaises(Conflict):
            self.c.messages.send(HUMAN, self.g, dict(text='different', targets=['one'], client_id='retry-key'))
        before = self.c.repo.revision()
        with self.assertRaises(ValueError):
            self.c.messages.send(HUMAN, self.g, dict(text='bad', targets=['missing']))
        self.assertEqual(before, self.c.repo.revision())
        self.assertEqual(1, len(self.c.repo.list('message', self.g)))

    def test_identity_and_group_boundaries(self):
        token = self.c.access.issue(self.g, 'one'); p = self.c.access.authenticate(token)
        m = self.c.agent_call(p, 'message.send', dict(actor_id='two', text='hello', targets=['two']))
        self.assertEqual('one', m['author'])
        gid = self.c.groups.create(dict(name='other', members=['one']))['id']
        with self.assertRaises(Forbidden): self.c.messages.send(p, gid, dict(text='bad'))
        with self.assertRaises(Forbidden): self.c.messages.send(self.q, self.g, dict(text='bad', reply_to=self.send()['id']))
        self.c.access.issue(self.g, 'one')
        with self.assertRaises(Forbidden): self.c.access.authenticate(token)

    def test_context_cas_and_foreman_permissions(self):
        self.c.groups.update_context(self.p, self.g, dict(version=1, brief='goal'))
        with self.assertRaises(Conflict): self.c.groups.update_context(self.p, self.g, dict(version=1, brief='lost'))
        with self.assertRaises(Forbidden): self.c.groups.update_context(self.q, self.g, dict(version=2, brief='steal'))
        c = self.c.groups.update_context(self.q, self.g, dict(version=2, decision='verified'))
        self.assertEqual('goal', c['brief']); self.assertEqual('two', c['decisions'][0]['by'])

    def test_lease_expiry_never_replays_automatically(self):
        m = self.send()
        self.assertEqual(1, len(self.c.messages.inbox(self.p, self.g, claim=True)))
        self.assertEqual([], self.c.messages.inbox(self.p, self.g, claim=True))
        with self.c.repo.transaction():
            d = self.c.repo.require('delivery', m['id']+':one'); d['lease_until'] = time.time()-1; self.c.repo.put('delivery', d)
        self.c.messages.expire_offers()
        self.assertEqual('uncertain', self.c.repo.require('delivery', d['id'])['state'])
        self.assertEqual([], self.c.messages.inbox(self.p, self.g, claim=True))
        self.c.messages.recover(self.g, d['id'], 'retry')
        self.assertEqual(1, len(self.c.messages.inbox(self.p, self.g, claim=True)))

    def test_internal_completion_releases_dependencies(self):
        t = self.c.tasks.create(HUMAN, self.g, dict(title='first', agent_id='one'))
        u = self.c.tasks.create(HUMAN, self.g, dict(title='second', agent_id='two', depends_on=[t['id']]))
        with self.assertRaises(Conflict): self.c.tasks.update(self.q, self.g, u['id'], dict(version=1, action='submit', text='early'))
        t = self.c.tasks.update(self.p, self.g, t['id'], dict(version=1, action='submit', text='actual result'))
        self.assertEqual('done', t['status'])
        self.assertFalse(self.c.repo.list('request'))
        with self.assertRaises(Forbidden): self.c.tasks.update(self.p, self.g, t['id'], dict(version=t['version'], action='approve'))
        self.c.tasks.update(self.q, self.g, u['id'], dict(version=1, action='submit', text='later'))
        with self.assertRaises(Conflict): self.c.tasks.update(self.q, self.g, u['id'], dict(version=1, action='submit', text='stale'))

    def test_graph_and_task_ownership(self):
        with self.assertRaises(ValueError): validate_graph([dict(id='a', depends_on=['b']), dict(id='b', depends_on=['a'])])
        with self.assertRaises(ValueError): self.c.tasks.create(self.p, self.g, dict(title='bad', agent_id='two', depends_on=['missing']))
        t = self.c.tasks.create(self.p, self.g, dict(title='delegate', agent_id='two'))
        with self.assertRaises(Forbidden): self.c.tasks.update(self.p, self.g, t['id'], dict(version=1, action='submit', text='impersonate'))
        self.assertEqual('todo', self.c.repo.require('task', t['id'])['status'])

    def test_human_answer_returns_to_requesting_member(self):
        r = self.c.agent_call(self.q, 'human.request', dict(title='Choose', options=['A','B']))
        with self.assertRaises(Forbidden): self.c.attention.resolve(self.q, r['id'], {'allow':True})
        self.c.admin_call('attention.answer', dict(id=r['id'], text='B'))
        m = self.c.repo.list('message', self.g)[-1]
        self.assertEqual(['two'], m['targets']); self.assertIn('B', m['text'])
        with self.assertRaises(Conflict): self.c.admin_call('attention.answer', dict(id=r['id'], text='Again'))

    def test_ledger_immutable_transaction_rolls_back(self):
        before = self.c.repo.revision()
        with self.assertRaises(RuntimeError):
            with self.c.repo.transaction():
                self.c.repo.emit(self.g,'bad','one',{}); raise RuntimeError('rollback')
        self.assertEqual(before, self.c.repo.revision())
        with self.assertRaises(sqlite3.IntegrityError): self.c.repo.db.execute('DELETE FROM events')

    def test_history_read_does_not_acknowledge(self):
        m = self.send(mode='mail')
        self.assertEqual(m['id'], self.c.agent_call(self.p, 'message.history', {})[0]['id'])
        self.assertFalse(self.c.repo.require('delivery',m['id']+':one')['read_at'])

    def test_new_session_preserves_previous_records(self):
        old = self.c.repo.require('session', self.g+':one'); self.c.sessions.new(self.g,'one')
        self.assertNotEqual(old['generation'],self.c.repo.require('session', self.g+':one')['generation'])
        self.assertTrue(any(e['kind']=='session.retired' for e in self.c.repo.events(self.g)))

    def test_pause_does_not_drop_mail(self):
        self.send(mode='mail'); self.c.groups.pause(self.g,True)
        self.assertFalse(self.c.messages.inbox(self.p,self.g,claim=True))
        self.assertEqual(1,len(self.c.messages.inbox(self.p,self.g)))

    def test_explicit_read_reaches_beyond_default_inbox_page(self):
        for _ in range(52): self.send(mode='mail')
        m = self.send()
        result = self.c.messages.read_inbox(self.p, self.g, [m['id']])
        self.assertEqual(m['id'], result[0]['message']['id'])
        self.assertTrue(result[0]['delivery']['read_at'])

    def test_retry_supersedes_prior_task_message(self):
        t = self.c.tasks.create(HUMAN,self.g,dict(title='run',agent_id='one',auto_run=True))
        self.c.bind('http://127.0.0.1:1'); self.c.supervisor.tick()
        t = self.c.repo.require('task',t['id'])
        self.c.tasks.update(self.p,self.g,t['id'],dict(version=t['version'],action='block',text='offline'))
        t = self.c.repo.require('task',t['id']); old = t['message_id']
        self.c.admin_call('task.action',dict(group_id=self.g,id=t['id'],version=t['version'],action='retry'))
        self.assertEqual('dismissed',self.c.repo.require('delivery',old+':one')['state'])


if __name__ == '__main__': unittest.main()
