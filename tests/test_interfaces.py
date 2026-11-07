import json
import tempfile
import unittest
from unittest.mock import patch
import urllib.request
import urllib.error
from yutong_teams.config import Config
from yutong_teams.control import Coordinator
from yutong_teams.interfaces.http import serve
from yutong_teams.sdk import AgentClient


class InterfaceTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();config=Config(self.tmp.name)
        config.save_agent(dict(id='external',name='External',kind='external'))
        self.c=Coordinator(config,start=False);self.server,self.token=serve(self.c)
        self.g=self.c.admin_call('group.create',dict(name='test',members=['external']))['id']
        self.conn=self.c.connection(self.g,'external');self.client=AgentClient.from_connection(self.conn['connection_file'])
    def tearDown(self):self.server.shutdown();self.server.server_close();self.c.close();self.tmp.cleanup()
    def request(self,path,payload,token=None,origin=None):
        headers={'Content-Type':'application/json','Authorization':'Bearer '+(self.conn['token'] if token is None else token)}
        if origin:headers['Origin']=origin
        req=urllib.request.Request(self.c.endpoint+path,data=json.dumps(payload).encode(),headers=headers)
        with urllib.request.urlopen(req) as r:return r.status,json.loads(r.read() or b'null')
    def test_sdk_external_claim_ack_reply(self):
        self.client.connect(session_id='native-external')
        m=self.c.admin_call('message.send',dict(group_id=self.g,text='work'))
        item=self.client.claim()[0];self.assertEqual(m['id'],item['message']['id'])
        self.client.delivered(m['id']);self.client.read(m['id']);self.client.reply(m['id'],'actual output')
        d=self.c.repo.require('delivery',m['id']+':external');self.assertTrue(all(d[k] for k in ('delivered_at','read_at','replied_at')))
    def test_mcp_tools_share_bound_identity(self):
        _,init=self.request('/mcp',dict(jsonrpc='2.0',id=1,method='initialize',params={'protocolVersion':'2025-03-26'}))
        self.assertEqual('2025-03-26',init['result']['protocolVersion'])
        status,_=self.request('/mcp',dict(jsonrpc='2.0',method='notifications/initialized'));self.assertEqual(202,status)
        _,r=self.request('/mcp',dict(jsonrpc='2.0',id=2,method='tools/list'));self.assertIn('teams_reply',[t['name'] for t in r['result']['tools']])
        _,r=self.request('/mcp',dict(jsonrpc='2.0',id=3,method='tools/call',params={'name':'teams_send','arguments':{'targets':['human'],'text':'MCP'}}))
        self.assertFalse(r['result'].get('isError',False));self.assertEqual('external',self.c.repo.list('message')[-1]['author'])
    def test_scope_and_origin_rejection(self):
        for path,token,origin in [('/api',self.conn['token'],None),('/agent/v1',self.token,None),('/mcp',self.conn['token'],'https://untrusted.example')]:
            with self.assertRaises(urllib.error.HTTPError) as caught:self.request(path,{'op':'state'},token,origin)
            self.assertIn(caught.exception.code,(401,403))
    def test_gateway_excludes_desktop_management(self):
        gateway,_=serve(self.c,port=0,worker=True)
        try:
            req=urllib.request.Request('http://127.0.0.1:%d/api'%gateway.server_port,data=b'{"op":"state"}',headers={'Authorization':'Bearer '+self.token})
            with self.assertRaises(urllib.error.HTTPError) as caught:urllib.request.urlopen(req)
            self.assertEqual(404,caught.exception.code)
        finally:gateway.shutdown();gateway.server_close()
    def test_connection_file_follows_restarted_port(self):
        old=self.c.endpoint;second,_=serve(self.c)
        try:
            self.assertNotEqual(old,self.client.credentials()[0]);self.assertEqual(self.c.endpoint,self.client.credentials()[0]);self.client.heartbeat()
        finally:second.shutdown();second.server_close()
    def test_mcp_schema_rejects_identity_injection(self):
        _,r=self.request('/mcp',dict(jsonrpc='2.0',id=3,method='tools/call',params={'name':'teams_send','arguments':{'actor_id':'human','targets':['human'],'text':'bad'}}))
        self.assertTrue(r['result']['isError']);self.assertEqual([],self.c.repo.list('message'))

    def test_binary_logo_and_static_path_boundary(self):
        with urllib.request.urlopen(self.c.endpoint + '/assets/app-logo.png') as response:
            self.assertEqual('image/png', response.headers['Content-Type'])
            self.assertEqual(b'\x89PNG\r\n\x1a\n', response.read(8))
        for path in ('/../config.py', '/assets/missing.png'):
            with self.assertRaises(urllib.error.HTTPError) as caught:
                urllib.request.urlopen(self.c.endpoint + path)
            self.assertEqual(404, caught.exception.code)

    def test_startup_does_not_resolve_non_utf8_hostname(self):
        failure = UnicodeDecodeError('utf-8', b'\xbb', 0, 1, 'invalid start byte')
        for host, worker in (('127.0.0.1', False), ('0.0.0.0', True)):
            with self.subTest(worker=worker), patch('socket.getfqdn', side_effect=failure) as resolve:
                server, _ = serve(self.c, host=host, worker=worker)
                try:
                    resolve.assert_not_called()
                    self.assertEqual(host, server.server_name)
                    url = 'http://127.0.0.1:%d/' % server.server_port
                    if worker:
                        with self.assertRaises(urllib.error.HTTPError) as caught:
                            urllib.request.urlopen(url)
                        self.assertEqual(404, caught.exception.code)
                    else:
                        with urllib.request.urlopen(url) as response:
                            self.assertEqual(200, response.status)
                finally:
                    server.shutdown()
                    server.server_close()


if __name__=='__main__':unittest.main()
