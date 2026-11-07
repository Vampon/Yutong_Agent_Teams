"""Real CCU runtime/tools with deterministic local model responses (not a live-model claim)."""
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import json,re,sys,threading,time,uuid
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from yutong_teams.config import Config,atomic_json
from yutong_teams.control import Coordinator
from yutong_teams.interfaces.http import serve

root=Path(__file__).resolve().parents[1]/'.test-data'/('v2-ccu-'+uuid.uuid4().hex[:8]);root.mkdir(parents=True)
calls=[]
class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args):pass
    def do_POST(self):
        req=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        messages=req['messages'];last=max(i for i,m in enumerate(messages) if m['role']=='user')
        mid=re.findall(r'本次消息 ID：([a-f0-9]{32})',messages[last]['content'])[-1]
        tool_names=[t['function']['name'] for t in req.get('tools',[])]
        count=sum(m['role']=='tool' for m in messages[last+1:])
        remembered=sum('NATIVE_MEMORY_WORD' in str(m.get('content','')) for m in messages[:last])>0
        calls.append(dict(tools_present=all(n in tool_names for n in ('teams_reply','teams_inbox_read')),remembered=remembered))
        tc=None
        if count==0:tc={'id':'call_'+uuid.uuid4().hex,'type':'function','function':{'name':'teams_inbox_read','arguments':json.dumps({'message_ids':[mid]})}}
        elif count==1:tc={'id':'call_'+uuid.uuid4().hex,'type':'function','function':{'name':'teams_reply','arguments':json.dumps({'reply_to':mid,'text':'NATIVE_MEMORY_WORD' if remembered else 'CCU_READY'})}}
        msg={'role':'assistant','content':None if tc else 'CCU turn complete'}
        if tc:msg['tool_calls']=[tc]
        self.send_response(200);self.send_header('Content-Type','text/event-stream' if req.get('stream') else 'application/json');self.end_headers()
        if req.get('stream'):
            delta=dict(msg)
            if tc:delta['tool_calls']=[dict(tc,index=0)]
            for data,reason in [(delta,None),({},'tool_calls' if tc else 'stop')]:
                frame={'id':'fixture','object':'chat.completion.chunk','model':'fixture','created':1,'choices':[{'index':0,'delta':data,'finish_reason':reason}]}
                self.wfile.write(('data: '+json.dumps(frame)+'\n\n').encode())
            self.wfile.write(b'data: [DONE]\n\n')
        else:self.wfile.write(json.dumps({'id':'fixture','choices':[{'index':0,'message':msg,'finish_reason':'tool_calls' if tc else 'stop'}]}).encode())
model=ThreadingHTTPServer(('127.0.0.1',0),Handler);threading.Thread(target=model.serve_forever,daemon=True).start()
cfg=root/'fixture.yaml';cfg.write_text('llm:\n  base_url: http://127.0.0.1:%s/v1\n  api_key: fixture\n  model: fixture\nagent:\n  workspace: %s\n  max_iterations: 5\n'%(model.server_port,str(root).replace('\\','/')),'utf-8')
config=Config(root);a=config.agent('ccu');a.update(command=sys.executable,config_path=str(cfg),timeout=120);config.save_agent(a)
c=Coordinator(config);server,_=serve(c);g=c.groups.create(dict(name='CCU bridge test',members=['ccu'],workspace=str(root)))['id']
report={'home':str(root),'mode':'real CCU kernel with local model fixture','checks':[]}
try:
    for text in ['Remember NATIVE_MEMORY_WORD, read and reply.','Read and recall previous turn.']:
        m=c.admin_call('message.send',dict(group_id=g,text=text));deadline=time.monotonic()+130
        while time.monotonic()<deadline:
            runs=[r for r in c.repo.list('run') if r['message_id']==m['id']]
            if runs and runs[-1]['status'] in ('completed','failed'):break
            time.sleep(.1)
        d=c.repo.require('delivery',m['id']+':ccu');sess=c.repo.require('session',g+':ccu');driver=c.supervisor.drivers.get(g+':ccu')
        report['checks'].append(dict(status=runs[-1]['status'],error=runs[-1]['error'],read=bool(d['read_at']),reply=bool(d['replied_at']),session=sess['provider_id'],pid=driver.channel.proc.pid if driver and driver.channel else None))
        if runs[-1]['status']!='completed':break
    report['ok']=len(report['checks'])==2 and all(x['status']=='completed' and x['read'] and x['reply'] for x in report['checks']) and report['checks'][0]['pid']==report['checks'][1]['pid'] and any(x['remembered'] for x in calls) and all(x['tools_present'] for x in calls)
    report['model_calls']=calls;atomic_json(root/'report.json',report);print(json.dumps(report))
finally:server.shutdown();server.server_close();c.close();model.shutdown();model.server_close()
