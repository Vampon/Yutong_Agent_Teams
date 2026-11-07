import json
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
import sys,tempfile,threading,unittest
from yutong_teams.config import Config
from yutong_teams.runtime.providers.acp import ACPAdapter
from yutong_teams.runtime.providers.command import CommandAdapter
from yutong_teams.runtime.providers.http import HttpAdapter


class AdapterTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.config=Config(self.tmp.name)
        self.binding={'workspace':self.tmp.name,'connection':{'mcp_config':{'mcpServers':{'teams':{'command':sys.executable,'args':[]}}}}}
    def tearDown(self):self.tmp.cleanup()
    def test_acp_persistent_session_and_permission_channel(self):
        a={'id':'acp','kind':'acp','command':sys.executable,'args':[str(Path(__file__).parent/'fixtures'/'acp_server.py')],'timeout':10}
        metadata={};approvals=[];session={}
        driver=ACPAdapter(self.config,a,session,self.binding,lambda **kw:metadata.update(kw))
        try:
            values=[driver.run('work',{},threading.Event(),lambda *x:None,lambda name,args:approvals.append(name) or False) for _ in range(2)]
            self.assertEqual(['turn-1','turn-2'],values);self.assertEqual(['fixture-write']*2,approvals)
            self.assertEqual('fixture-session',metadata['provider_id'])
        finally:driver.close()
    def test_command_output_bound(self):
        a={'command':sys.executable,'args':['-c','import sys;sys.stdin.read();sys.stdout.write("x"*1100000)'],'timeout':10}
        driver=CommandAdapter(self.config,a,{},self.binding,lambda **kw:None)
        with self.assertRaises(ValueError):driver.run('test',{},threading.Event(),lambda *x:None,lambda *x:False)

    def test_acp_modern_resume_keeps_provider_id(self):
        a={'id':'acp','kind':'acp','command':sys.executable,'args':[str(Path(__file__).parent/'fixtures'/'acp_server.py'),'--resume'],'timeout':10}
        metadata={}
        driver=ACPAdapter(self.config,a,{'provider_id':'saved'},self.binding,lambda **kw:metadata.update(kw))
        try:
            self.assertEqual('turn-1',driver.run('work',{},threading.Event(),lambda *x:None,lambda *x:False))
            self.assertEqual('saved',metadata['provider_id'])
            self.assertTrue(metadata['resume_supported'])
        finally:driver.close()

    def test_acp_permission_id_uses_prior_tool_metadata(self):
        a={'id':'acp','kind':'acp','command':sys.executable,'args':[str(Path(__file__).parent/'fixtures'/'acp_server.py'),'--id-only'],'timeout':10}
        approvals=[]
        driver=ACPAdapter(self.config,a,{},self.binding,lambda **kw:None)
        try:
            driver.run('work',{},threading.Event(),lambda *x:None,lambda name,args:approvals.append((name,args)) or False)
            self.assertEqual([('read_fixture',{'path':'fixture'})],approvals)
        finally:driver.close()

    def test_acp_load_replay_is_not_new_turn_output_and_tools_are_correlated(self):
        a={'id':'acp','kind':'acp','command':sys.executable,'args':[str(Path(__file__).parent/'fixtures'/'acp_server.py')],'timeout':10}
        events=[]
        driver=ACPAdapter(self.config,a,{'provider_id':'saved'},self.binding,lambda **kw:None)
        try:
            value=driver.run('work',{},threading.Event(),lambda kind,data:events.append((kind,data)),lambda *x:False)
            self.assertEqual('turn-1',value)
            self.assertNotIn('OLD_HISTORY_REPLAY',json.dumps(events))
            calls=[data for kind,data in events if kind=='tool']
            self.assertEqual(['fixture-read','fixture-read'],[x['id'] for x in calls])
            self.assertEqual('completed',calls[-1]['status'])
            self.assertEqual('fixture-result',calls[-1]['result'])
        finally:driver.close()
    def test_command_stdin_and_stdout(self):
        a={'command':sys.executable,'args':['-c','import sys;print("reply:"+sys.stdin.read())'],'timeout':10}
        driver=CommandAdapter(self.config,a,{},self.binding,lambda **kw:None)
        self.assertEqual('reply:payload',driver.run('payload',{},threading.Event(),lambda *x:None,lambda *x:False))
    def test_adp_v2_success_and_truncated_stream(self):
        requests=[];frames=[{'Type':'message.added','MessageId':'m','Message':{'Type':'reply'}},{'Type':'text.delta','MessageId':'m','Text':'initial'},{'Type':'text.replace','MessageId':'m','Text':'corrected'},{'Type':'response.completed','Response':{'Status':'success','Messages':[]}}]
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def do_POST(self):
                requests.append(json.loads(self.rfile.read(int(self.headers['Content-Length']))))
                self.send_response(200);self.send_header('Content-Type','text/event-stream');self.end_headers()
                self.wfile.write(''.join('data: '+json.dumps(x)+'\n\n' for x in frames).encode())
        server=ThreadingHTTPServer(('127.0.0.1',0),Handler);threading.Thread(target=server.serve_forever,daemon=True).start()
        a={'id':'adp','kind':'adp','url':'http://127.0.0.1:%d'%server.server_port,'user_id':'fixture','timeout':10}
        driver=HttpAdapter(self.config,a,{'generation':'one'},self.binding,lambda **kw:None)
        try:
            self.assertEqual('corrected',driver.run('test',{'id':'r','group_id':'g'},threading.Event(),lambda *x:None,lambda *x:False))
            frames.pop()
            with self.assertRaises(RuntimeError):driver.run('test',{'id':'r2','group_id':'g'},threading.Event(),lambda *x:None,lambda *x:False)
            self.assertEqual(requests[0]['ConversationId'],requests[1]['ConversationId']);self.assertNotEqual(requests[0]['RequestId'],requests[1]['RequestId'])
        finally:server.shutdown();server.server_close()


if __name__=='__main__':unittest.main()
