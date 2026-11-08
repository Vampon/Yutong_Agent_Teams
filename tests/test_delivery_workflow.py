"""Regression cases from the duplicated quicksort review and closing-message loop."""
import tempfile
import time
import unittest
from unittest.mock import patch

from yutong_teams.config import Config
from yutong_teams.control import Coordinator
from yutong_teams.core.contracts import HUMAN, Principal, Conflict, Forbidden
from yutong_teams.runtime.registry import AdapterSpec, default_registry


class FixtureAdapter:
    behavior = None

    def __init__(self, config, agent, session, binding, persist):
        self.aid, self.call = agent['id'], binding['invoke']

    def run(self, prompt, turn, stop, emit, approve):
        emit('accepted', {})
        self.call('inbox.read', {'message_ids': [turn['message_id']]})
        return type(self).behavior(self, turn) if type(self).behavior else 'done'

    def close(self):
        pass


class WorkflowTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        config = Config(self.temp.name)
        for aid in ('leader', 'worker'):
            config.save_agent(dict(id=aid, name=aid, kind='fixture'))
        registry = default_registry()
        registry.register(AdapterSpec('fixture', 'fixture', FixtureAdapter,
            dict(local=False, tools=True, auto_reply=False, session='native'), [], ''))
        FixtureAdapter.behavior = None
        self.c = Coordinator(config, start=False, registry=registry)
        self.c.bind('http://127.0.0.1:1')
        self.g = self.c.groups.create(dict(name='review', members=['leader', 'worker'], review=True))['id']
        self.p = Principal(actor_id='leader', group_id=self.g)
        self.q = Principal(actor_id='worker', group_id=self.g)
        self.m = self.c.messages.send(HUMAN, self.g, dict(text='implement and review', targets=['leader'], mode='request_reply'))
        self.c.messages.read_inbox(self.p, self.g, [self.m['id']])
        self.root = self.m['root_id']

    def tearDown(self):
        self.c.close()
        self.temp.cleanup()

    def task(self, auto=False):
        return self.c.tasks.create(HUMAN, self.g, dict(title='peer review', agent_id='worker',
            auto_run=auto, work_id=self.root))

    def finish(self, task):
        task = self.c.repo.require('task', task['id'])
        return self.c.agent_call(self.q, 'task.update', dict(id=task['id'], version=task['version'], action='submit', text='review passed with test evidence'))

    def submit(self):
        work = self.c.repo.require('work', self.root)
        return self.c.agent_call(self.p, 'work.submit', dict(work_id=self.root, version=work['version'],
            title='final delivery', text='implementation and independent review complete'))

    def run_until(self, condition):
        deadline = time.monotonic() + 4
        while time.monotonic() < deadline:
            self.c.supervisor.tick()
            if condition():
                return
            time.sleep(.01)
        self.fail('fixture did not settle')

    def test_submitted_task_consumes_queued_assignment_before_it_can_rerun(self):
        t = self.task(True)
        with self.c.repo.transaction(): self.c.supervisor._dispatch_tasks()
        t = self.finish(t)
        self.assertEqual('done', t['status'])
        self.assertEqual('dismissed', self.c.repo.require('delivery', t['message_id'] + ':worker')['state'])
        with patch('yutong_teams.runtime.supervisor.threading.Thread') as thread:
            self.c.supervisor.tick()
        self.assertFalse(any(r['actor_id'] == 'worker' for r in self.c.repo.list('run')))
        self.assertEqual('done', self.c.repo.require('task', t['id'])['status'])
        self.assertFalse(self.c.repo.list('request'))

    def test_old_assignment_cannot_reset_review_done_cancelled_or_new_generation(self):
        for status in ('review', 'done', 'cancelled', 'running'):
            with self.subTest(status=status):
                t = self.task(True)
                with self.c.repo.transaction():
                    self.c.supervisor._dispatch_tasks()
                    t = self.c.repo.require('task', t['id'])
                    t['status'] = status
                    self.c.repo.put('task', t)
                with patch('yutong_teams.runtime.supervisor.threading.Thread'):
                    self.c.supervisor.tick()
                self.assertEqual(status, self.c.repo.require('task', t['id'])['status'])
                self.assertFalse(any(r.get('task_id') == t['id'] for r in self.c.repo.list('run')))

    def test_external_claim_checks_the_same_task_state(self):
        t = self.task(True)
        with self.c.repo.transaction(): self.c.supervisor._dispatch_tasks()
        t = self.finish(t)
        self.assertEqual([], self.c.messages.inbox(self.q, self.g, claim=True))
        self.assertEqual('done', self.c.repo.require('task', t['id'])['status'])

    def test_external_task_claim_is_once_and_marks_running(self):
        t = self.task(True)
        with self.c.repo.transaction(): self.c.supervisor._dispatch_tasks()
        self.assertEqual(1, len(self.c.messages.inbox(self.q, self.g, claim=True)))
        self.assertEqual([], self.c.messages.inbox(self.q, self.g, claim=True))
        self.assertEqual('running', self.c.repo.require('task', t['id'])['status'])

    def test_task_create_retry_has_one_assignment_and_changed_payload_is_rejected(self):
        values = dict(title='review', agent_id='worker', work_id=self.root, client_id='review-once')
        a = self.c.tasks.create(self.p, self.g, values)
        b = self.c.tasks.create(self.p, self.g, values)
        self.assertEqual(a['id'], b['id'])
        with self.assertRaises(Conflict): self.c.tasks.create(self.p, self.g, dict(values, title='different'))
        with self.c.repo.transaction():
            self.c.supervisor._dispatch_tasks()
            self.c.supervisor._dispatch_tasks()
        self.assertEqual(1, len([m for m in self.c.repo.list('message') if m.get('task_id') == a['id']]))

    def test_progress_adopts_work_and_retires_unstarted_assignment(self):
        t = self.task(True)
        with self.c.repo.transaction(): self.c.supervisor._dispatch_tasks()
        t = self.c.repo.require('task', t['id'])
        self.c.tasks.update(self.q, self.g, t['id'], dict(version=t['version'], action='progress'))
        with patch('yutong_teams.runtime.supervisor.threading.Thread'):
            self.c.supervisor.tick()
        self.assertFalse(self.c.repo.list('run'))
        self.assertEqual('running', self.c.repo.require('task', t['id'])['status'])

    def test_internal_review_releases_dependencies_without_human_approval(self):
        first = self.task()
        second = self.c.tasks.create(HUMAN, self.g, dict(title='repair', agent_id='worker', depends_on=[first['id']]))
        with self.assertRaises(Conflict): self.finish(second)
        self.finish(first)
        self.assertEqual('done', self.finish(second)['status'])
        self.assertFalse(self.c.repo.list('request'))

    def test_one_final_acceptance_and_idempotent_retry(self):
        t = self.task()
        with self.assertRaises(Conflict): self.submit()
        self.finish(t)
        w = self.submit()
        self.assertEqual('review', w['status'])
        retry = self.c.agent_call(self.p, 'work.submit', dict(work_id=self.root, version=1,
            title='final delivery', text='implementation and independent review complete'))
        self.assertEqual(w['request_id'], retry['request_id'])
        self.assertEqual(1, len(self.c.repo.list('request')))
        self.assertTrue(self.c.repo.require('delivery', self.m['id'] + ':leader')['replied_at'])
        self.c.admin_call('attention.answer', dict(id=w['request_id'], allow=True))
        self.assertEqual('done', self.c.repo.require('work', self.root)['status'])
        with self.assertRaises(Conflict): self.c.admin_call('attention.answer', dict(id=w['request_id'], allow=True))

    def test_peer_cannot_submit_final_or_approve(self):
        with self.assertRaises(Forbidden):
            self.c.agent_call(self.q, 'work.submit', dict(work_id=self.root, version=1, title='bad', text='bad'))
        with self.assertRaises(ValueError): self.c.agent_call(self.q, 'work.reopen', {})

    def test_first_requested_reply_wakes_but_repeated_answers_and_replies_do_not(self):
        m = self.c.messages.send(self.p, self.g, dict(targets=['worker'], text='check', mode='request_reply', work_id=self.root))
        r = self.c.messages.send(self.q, self.g, dict(reply_to=m['id'], text='checked'))
        self.assertEqual('send', r['mode'])
        again = self.c.messages.send(self.q, self.g, dict(reply_to=m['id'], text='checked again', mode='send'))
        ack = self.c.messages.send(self.p, self.g, dict(reply_to=r['id'], text='received', mode='send'))
        self.assertEqual('mail', again['mode'])
        self.assertEqual('mail', ack['mode'])
        self.assertEqual('mail', self.c.messages.send(self.p, self.g, dict(targets=['worker'], text='FYI'))['mode'])

    def test_automatic_result_and_explicit_reply_produce_only_one_wake(self):
        t = self.task(True)
        with self.c.repo.transaction(): self.c.supervisor._dispatch_tasks()
        t = self.finish(t)
        self.c._notify_completed(t)
        self.c.messages.send(self.q, self.g, dict(reply_to=t['message_id'], text='same result', mode='send'))
        results = [m for m in self.c.repo.list('message') if m['reply_to'] == t['message_id']]
        self.assertEqual(2, len(results))
        self.assertEqual(1, sum(m['mode'] != 'mail' for m in results))

    def test_final_submission_and_acceptance_silence_old_chain_only(self):
        self.finish(self.task())
        w = self.submit()
        late = self.c.messages.send(self.q, self.g, dict(text='confirmed', targets=['leader'], mode='send', work_id=self.root))
        self.assertEqual('mail', late['mode'])
        self.c.admin_call('attention.answer', dict(id=w['request_id'], allow=True))
        self.c.supervisor.tick()
        self.assertFalse(self.c.repo.list('run'))
        with self.assertRaises(Conflict):
            self.c.tasks.create(self.p, self.g, dict(title='unwanted new work', agent_id='worker', work_id=self.root))
        new = self.c.messages.send(HUMAN, self.g, dict(text='new independent work', targets=['worker']))
        self.assertNotEqual(self.root, new['root_id'])
        self.run_until(lambda: any(r['status'] == 'completed' for r in self.c.repo.list('run')))
        self.assertEqual([new['id']], [r['message_id'] for r in self.c.repo.list('run')])

    def test_revise_is_explicit_and_old_messages_stay_quiet(self):
        self.finish(self.task())
        old = self.c.messages.send(self.q, self.g, dict(targets=['leader'], text='old result', mode='mail', work_id=self.root))
        w = self.submit()
        with self.assertRaises(ValueError): self.c.admin_call('attention.answer', dict(id=w['request_id'], allow=False))
        w = self.c.admin_call('attention.answer', dict(id=w['request_id'], allow=False, text='cover one more case'))
        self.assertEqual(('active', 2), (w['status'], w['epoch']))
        with patch('yutong_teams.runtime.supervisor.threading.Thread'):
            self.c.supervisor.tick()
        runs = self.c.repo.list('run')
        self.assertEqual(1, len(runs))
        self.assertEqual('work_revision', self.c.repo.require('message', runs[0]['message_id'])['origin'])
        self.assertNotEqual(old['id'], runs[0]['message_id'])

    def test_external_reply_to_old_epoch_cannot_wake_reopened_work(self):
        old = self.c.messages.send(self.p, self.g, dict(targets=['worker'], text='original question', mode='request_reply', work_id=self.root))
        self.c.messages.read_inbox(self.q, self.g, [old['id']])
        w = self.submit()
        self.c.admin_call('attention.answer', dict(id=w['request_id'], allow=False, text='new revision'))
        late = self.c.messages.send(self.q, self.g, dict(reply_to=old['id'], text='late original answer', mode='send'))
        self.assertEqual(1, late['work_epoch'])
        self.assertEqual('mail', late['mode'])

    def test_stale_callback_cannot_create_work_after_reopen(self):
        self.finish(self.task())
        w = self.submit()
        self.c.admin_call('attention.answer', dict(id=w['request_id'], allow=False, text='revise'))
        with self.c.repo.transaction():
            self.c.repo.put('run', dict(id='old-run', group_id=self.g, root_id=self.root,
                actor_id='worker', status='running', work_epoch=1))
        with self.assertRaises(Conflict):
            self.c.agent_call(self.q, 'task.create', dict(title='stale', agent_id='worker'))
        late = self.c.messages.send(self.q, self.g, dict(targets=['leader'], text='stale', mode='send'))
        self.assertEqual('mail', late['mode'])

    def test_full_revision_cycle_creates_one_new_acceptance_and_no_old_dispatch(self):
        t = self.finish(self.task())
        w = self.submit()
        w = self.c.admin_call('attention.answer', dict(id=w['request_id'], allow=False, text='revise implementation'))
        revision = self.c.repo.list('message')[-1]
        self.c.messages.read_inbox(self.p, self.g, [revision['id']])
        t = self.c.agent_call(self.p, 'task.update', dict(id=t['id'], version=t['version'], action='retry', text='review changed code'))
        self.assertEqual(2, t['dispatch_epoch'])
        with self.c.repo.transaction(): self.c.supervisor._dispatch_tasks()
        t = self.finish(t)
        w = self.submit()
        requests = self.c.repo.list('request')
        self.assertEqual(2, len(requests))
        self.assertEqual(1, sum(r['status'] == 'pending' for r in requests))
        self.c.admin_call('attention.answer', dict(id=w['request_id'], allow=True))
        closed = self.c.repo.require('work', self.root)
        reopened = self.c.admin_call('work.reopen', dict(group_id=self.g, id=self.root, version=closed['version'], text='new requirement'))
        self.assertEqual(3, reopened['epoch'])
        with self.assertRaises(Conflict): self.c.admin_call('work.reopen', dict(group_id=self.g, id=self.root, version=closed['version'], text='duplicate'))

    def test_prelaunch_recheck_skips_assignment_completed_after_tick(self):
        self.task(True)
        with patch('yutong_teams.runtime.supervisor.threading.Thread'):
            self.c.supervisor.tick()
        run = self.c.repo.list('run')[0]
        self.finish(self.c.repo.require('task', run['task_id']))
        session = self.c.repo.require('session', self.g + ':worker')
        import threading
        with patch.object(self.c.supervisor, '_driver') as driver:
            self.c.supervisor._execute(run, self.c.config.agent('worker'), session, threading.Event())
        driver.assert_not_called()
        self.assertTrue(self.c.repo.require('run', run['id'])['skipped'])
        self.assertEqual('ready', self.c.repo.require('session', self.g + ':worker')['state'])

    def test_review_disabled_finishes_without_fabricating_human_approval(self):
        with self.c.repo.transaction():
            group = self.c.repo.require('group', self.g); group['review'] = False; self.c.repo.put('group', group)
        w = self.submit()
        self.assertEqual('done', w['status'])
        self.assertNotIn('approved_by', w)
        self.assertFalse(self.c.repo.list('request'))

    def test_legacy_duplicate_reviews_migrate_to_internal_completion_without_approval(self):
        from yutong_teams.core.workflow_migration import upgrade
        t = self.task(True)
        with self.c.repo.transaction():
            self.c.supervisor._dispatch_tasks()
            t = self.c.repo.require('task', t['id']); t['status'] = 'review'; t['result'] = 'legacy result'
            self.c.repo.put('task', t)
            for _ in range(2): self.c.attention.create(self.q, self.g, 'review', 'legacy', task_id=t['id'])
            self.c.repo.db.execute("DELETE FROM records WHERE kind='meta' AND id='final-delivery-v1'")
        completed = upgrade(self.c.repo)
        self.assertEqual(1, len(completed))
        self.assertEqual('done', self.c.repo.require('task', t['id'])['status'])
        self.assertNotIn('approved_by', self.c.repo.require('task', t['id']))
        self.assertTrue(all(r['status'] == 'superseded' for r in self.c.repo.list('request')))
        self.assertEqual('active', self.c.repo.require('work', self.root)['status'])
        self.assertEqual([], upgrade(self.c.repo))

    def test_legacy_human_approved_chain_is_quiet_after_upgrade(self):
        from yutong_teams.core.workflow_migration import upgrade
        t = self.finish(self.task())
        self.c.messages.send(self.q, self.g, dict(text='late acknowledgement', targets=['leader'], mode='send', work_id=self.root))
        with self.c.repo.transaction():
            t['approved_by'] = 'human'; self.c.repo.put('task', t)
            self.c.repo.db.execute("DELETE FROM records WHERE kind='meta' AND id='final-delivery-v1'")
        upgrade(self.c.repo)
        self.assertEqual('legacy_task_approvals', self.c.repo.require('work', self.root)['accepted_evidence'])
        self.c.supervisor.tick()
        self.assertFalse(self.c.repo.list('run'))

    def test_closed_delivery_cannot_be_retried_through_recovery(self):
        m = self.c.messages.send(self.p, self.g, dict(targets=['worker'], text='info', mode='mail', work_id=self.root))
        self.submit()
        with self.c.repo.transaction():
            d = self.c.repo.require('delivery', m['id'] + ':worker')
            d['state'] = 'uncertain'; self.c.repo.put('delivery', d)
        with self.assertRaises(Conflict): self.c.messages.recover(self.g, d['id'], 'retry')

    def test_two_agents_review_then_acceptance_creates_no_additional_turns(self):
        def behavior(a, turn):
            if a.aid == 'worker':
                task = self.c.repo.require('task', turn['task_id'])
                a.call('task.update', dict(id=task['id'], version=task['version'], action='submit', text='independent review passed'))
            else:
                context = a.call('context.get', {})
                work = context['current_work']
                a.call('work.submit', dict(work_id=work['id'], version=work['version'], title='reviewed result', text='all checks passed'))
            return 'finished'
        FixtureAdapter.behavior = behavior
        # Agent-created task ensures the result is returned to the leader.
        self.c.tasks.create(self.p, self.g, dict(title='review', agent_id='worker', work_id=self.root))
        self.run_until(lambda: self.c.repo.list('request') and all(r['status'] == 'completed' for r in self.c.repo.list('run')))
        self.assertEqual(['worker', 'leader'], [r['actor_id'] for r in self.c.repo.list('run')])
        request = self.c.repo.list('request')[0]
        self.c.admin_call('attention.answer', dict(id=request['id'], allow=True))
        for _ in range(10): self.c.supervisor.tick()
        self.assertEqual(2, len(self.c.repo.list('run')))
        self.assertEqual('done', self.c.repo.require('work', self.root)['status'])


if __name__ == '__main__':
    unittest.main()
