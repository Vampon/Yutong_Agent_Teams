import tempfile
import threading
import time
import unittest
from yutong_teams.config import Config
from yutong_teams.control import Coordinator
from yutong_teams.runtime.registry import AdapterSpec, default_registry
from yutong_teams.core.contracts import HUMAN


class MemoryAdapter:
    instances = []; behavior = None
    def __init__(self,config,agent,session,binding,persist):
        self.aid,self.binding,self.persist=agent['id'],binding,persist
        self.memory=[];self.closed=False;self.instances.append(self)
        persist(provider_id=session.get('provider_id') or 'native-'+self.aid)
    def run(self,prompt,turn,stop,emit,approve):
        emit('accepted',{});self.memory.append(turn['message_id'])
        if type(self).behavior:return type(self).behavior(self,prompt,turn,stop,emit,approve)
        return 'native output is not a group reply'
    def close(self):self.closed=True


class RuntimeTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.config=Config(self.tmp.name)
        for aid in ('one','two'):self.config.save_agent(dict(id=aid,name=aid,kind='fixture'))
        registry=default_registry();registry.register(AdapterSpec('fixture','fixture',MemoryAdapter,dict(local=False,tools=True,auto_reply=False,session='native'),[],''))
        MemoryAdapter.instances=[];MemoryAdapter.behavior=None
        self.c=Coordinator(self.config,start=False,registry=registry);self.c.bind('http://127.0.0.1:1')
        self.g=self.c.groups.create(dict(name='test',members=['one','two']))['id']
    def tearDown(self):self.c.close();self.tmp.cleanup()
    def send(self,aid='one',**kw):return self.c.messages.send(HUMAN,self.g,dict(text='execute',targets=[aid],**kw))
    def wait(self,predicate,seconds=4):
        until=time.monotonic()+seconds
        while time.monotonic()<until:
            self.c.supervisor.tick()
            if predicate():return
            time.sleep(.03)
        self.fail('condition did not complete')
    def done(self,mid):return any(r['message_id']==mid and r['status']=='completed' for r in self.c.repo.list('run'))

    def test_persistent_driver_without_fabricated_read_or_reply(self):
        first=self.send();self.wait(lambda:self.done(first['id']))
        second=self.send();self.wait(lambda:self.done(second['id']))
        self.assertEqual(1,len(MemoryAdapter.instances));self.assertEqual(2,len(MemoryAdapter.instances[0].memory))
        d=self.c.repo.require('delivery',first['id']+':one')
        self.assertTrue(d['delivered_at']);self.assertFalse(d['read_at']);self.assertFalse(d['replied_at'])

    def test_mail_does_not_wake_managed_session(self):
        self.send(mode='mail');self.c.supervisor.tick()
        self.assertEqual([],MemoryAdapter.instances);self.assertEqual([],self.c.repo.list('run'))

    def test_peer_tools_run_during_original_execution(self):
        peer_finished=threading.Event()
        def behavior(adapter,prompt,turn,stop,emit,approve):
            call=adapter.binding['invoke'];call('inbox.read',{'message_ids':[turn['message_id']]})
            if adapter.aid=='one':
                call('message.send',{'targets':['two'],'text':'peer work','mode':'request_reply'})
                if not peer_finished.wait(2):raise RuntimeError('peer not concurrent')
                call('message.reply',{'reply_to':turn['message_id'],'text':'assembled'})
            else:
                call('message.reply',{'reply_to':turn['message_id'],'text':'peer result','mode':'mail'});peer_finished.set()
            return 'runtime output'
        MemoryAdapter.behavior=behavior
        m=self.send();self.wait(lambda:self.done(m['id']))
        self.assertTrue(peer_finished.is_set());self.assertEqual(2,len(self.c.repo.list('run')))
        self.assertTrue(self.c.repo.require('delivery',m['id']+':one')['replied_at'])

    def test_human_tool_permission_waits_for_actual_answer(self):
        answers=[]
        def behavior(a,p,t,stop,emit,approve):answers.append(approve('write_file',{'path':'review.txt'}));return 'done'
        MemoryAdapter.behavior=behavior
        m=self.send();self.wait(lambda:bool(self.c.repo.list('request')));self.assertFalse(answers)
        r=self.c.repo.list('request')[0];self.c.admin_call('attention.answer',{'id':r['id'],'allow':False})
        self.wait(lambda:self.done(m['id']));self.assertEqual([False],answers)

    def test_changed_config_requires_explicit_new_session(self):
        m=self.send();self.wait(lambda:self.done(m['id']))
        a=self.config.agent('one');a['command']='changed';self.c.admin_call('agent.save',a)
        n=self.send();self.wait(lambda:any(r['message_id']==n['id'] and r['status']=='failed' for r in self.c.repo.list('run')))
        self.assertIn('新建会话',self.c.repo.list('run')[-1]['error'])
        self.c.admin_call('session.action',dict(group_id=self.g,actor_id='one',action='new'))
        self.c.admin_call('message.recover',dict(group_id=self.g,id=n['id']+':one',action='retry'))
        self.wait(lambda:self.done(n['id']))

    def test_restart_preserves_native_id_and_uncertainty(self):
        m=self.send()
        with self.c.repo.transaction():
            session=self.c.repo.require('session',self.g+':one');session['provider_id']='saved';self.c.repo.put('session',session)
            self.c.repo.put('run',dict(id='abandoned',group_id=self.g,actor_id='one',status='running',delivery_id=m['id']+':one',task_id=''))
        self.c.supervisor.recover_interrupted()
        self.assertEqual('saved',self.c.repo.require('session',self.g+':one')['provider_id'])
        self.assertEqual('uncertain',self.c.repo.require('delivery',m['id']+':one')['state'])
        self.c.supervisor.tick();self.assertFalse(MemoryAdapter.instances)

    def test_task_not_submitted_is_not_completed(self):
        t=self.c.tasks.create(HUMAN,self.g,dict(title='deliver',agent_id='one',auto_run=True))
        self.wait(lambda:self.c.repo.require('task',t['id'])['status']=='blocked')
        self.assertFalse(self.c.repo.require('task',t['id'])['result'])

    def test_session_stop_releases_owned_driver(self):
        m=self.send();self.wait(lambda:self.done(m['id']));self.c.supervisor.stop_actor(self.g,'one')
        self.assertTrue(MemoryAdapter.instances[0].closed)
        n=self.send();self.c.supervisor.tick();self.assertFalse(any(r['message_id']==n['id'] for r in self.c.repo.list('run')))

    def test_shared_chain_budget_bounds_peer_loop(self):
        with self.c.repo.transaction():
            g=self.c.repo.require('group',self.g);g['max_turns']=2;self.c.repo.put('group',g)
        def behavior(a,p,t,stop,emit,approve):
            a.binding['invoke']('message.send',dict(targets=['two' if a.aid=='one' else 'one'],text='followup',mode='send'))
            return 'sent'
        MemoryAdapter.behavior=behavior
        self.send();self.wait(lambda:len(self.c.repo.list('run'))==2 and all(r['status']=='completed' for r in self.c.repo.list('run')))
        self.c.supervisor.tick()
        self.assertEqual(2,len(self.c.repo.list('run')))
        self.assertTrue(any(d.get('budget_wait') for d in self.c.repo.list('delivery')))


if __name__=='__main__':unittest.main()
