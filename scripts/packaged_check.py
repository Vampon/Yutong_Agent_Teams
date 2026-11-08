"""Exercise the single EXE without a Python/Node PATH. --live tests native Claude+MCP."""
import argparse,hashlib,json,os,queue,socket,subprocess,sys,threading,time,uuid
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from yutong_teams.config import Config,atomic_json
from yutong_teams.control import Coordinator
from yutong_teams.runtime.processes import kill,executable,ProcessChannel
from yutong_teams.sdk import AgentClient


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--live',action='store_true');parser.add_argument('--exe');args=parser.parse_args()
    project=Path(__file__).resolve().parents[1];exe=Path(args.exe).resolve() if args.exe else project/'dist'/'Yutong Agent Teams.exe'
    root=project/'.test-data'/('v2-packaged-'+uuid.uuid4().hex[:8]);root.mkdir(parents=True)
    env=dict(os.environ);windows=os.environ.get('SystemRoot',r'C:\Windows');env['PATH']=str(Path(windows)/'System32')+';'+windows
    for key in ('PYTHONPATH','PYTHONHOME','YUTONG_TEAMS_HOME'):env.pop(key,None)
    report={'exe':str(exe),'home':str(root),'sha256':hashlib.sha256(exe.read_bytes()).hexdigest(),'checks':[]}
    def check(label,ok,**detail):
        report['checks'].append(dict(check=label,ok=ok,**detail));atomic_json(root/'report.json',report)
        print(json.dumps(report['checks'][-1]),flush=True)
        if not ok:raise AssertionError(label)
    for flag,filename in [('--self-test','self-test.json'),('--smoke-gui','smoke-gui.json')]:
        proc=subprocess.Popen([str(exe),'--home',str(root),flag],env=env,creationflags=subprocess.CREATE_NO_WINDOW)
        try:
            code=proc.wait(timeout=60);value=json.loads((root/filename).read_text('utf-8'));check(flag,code==0 and value['ok'],detail=value)
        finally:kill(proc)
    with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
    config=Config(root);config.save_agent(dict(id='requester',name='External requester',kind='external'))
    config.save_agent(dict(id='echo',name='Owned command',kind='command',command=sys.executable,args=['-c','import sys;sys.stdin.read();print("PACKAGED_COMMAND_OK")']))
    if args.live:
        a=config.agent('claude');a.update(command=executable('claude','claude')[0],timeout=180);config.save_agent(a)
    seed=Coordinator(config,start=False);seed.bind('http://127.0.0.1:%d'%port)
    for aid, role in [('packaged_review', '需求评审'), ('packaged_develop', '代码开发')]:
        seed.admin_call('agent.clone', dict(id=aid, source_id='claude', name=role, role=role, instructions='Packaged persona fixture'))
    seed.admin_call('permissions.configure', dict(mode='ask', overrides={'packaged_review':'deny'}))
    gid=seed.groups.create(dict(name='Packaged acceptance',members=['requester','echo','packaged_review','packaged_develop']+(['claude'] if args.live else []),workspace=str(root)))['id']
    conn=seed.connection(gid,'requester');seed.close()
    proc=subprocess.Popen([str(exe),'--home',str(root),'--worker','--port',str(port)],env=env,creationflags=subprocess.CREATE_NO_WINDOW)
    client=AgentClient.from_connection(conn['connection_file']);pipe=None
    try:
        deadline=time.monotonic()+30
        while True:
            try:client.connect(session_id='external-session');break
            except Exception:
                if proc.poll() is not None or time.monotonic()>deadline:raise
                time.sleep(.2)
        check('scoped-http-connect',True)
        roster=client.call('context.get')['roster']
        restored={a['actor_id']:a['role'] for a in roster}
        check('frozen-shared-runtime-personas-restored',restored.get('packaged_review')=='需求评审' and restored.get('packaged_develop')=='代码开发')
        pipe=ProcessChannel([str(exe),'--mcp','--connection',conn['connection_file']],str(root),env)
        pipe.send({'jsonrpc':'2.0','id':1,'method':'initialize','params':{'protocolVersion':'2025-03-26'}})
        initialized=pipe.next(threading.Event(),time.monotonic()+30)
        check('windowed-exe-mcp-stdio',initialized.get('result',{}).get('serverInfo',{}).get('name')=='yutong-teams')
        pipe.send({'jsonrpc':'2.0','id':2,'method':'tools/call','params':{'name':'teams_send','arguments':{'targets':['echo'],'text':'Read-only packaged process check','mode':'request_reply'}}})
        response=pipe.next(threading.Event(),time.monotonic()+15);check('windowed-mcp-tool-call',response.get('result',{}).get('isError') is False)
        message=response['result']['structuredContent']['result']
        def reply_to(mid,timeout=190):
            end=time.monotonic()+timeout
            while time.monotonic()<end:
                items=client.call('inbox.list',unread=False)
                replies=[x['message'] for x in items if x['message']['reply_to']==mid]
                if replies:return replies[-1]
                time.sleep(.25)
            raise TimeoutError('No correlated reply within deadline')
        check('bundled-python-launches-external-command',reply_to(message['id'],30)['text']=='PACKAGED_COMMAND_OK')
        work=next(w for w in client.call('context.get')['works'] if w['id']==message['root_id'])
        final=client.submit_final(work['id'],work['version'],'Packaged workflow result','Actual command returned PACKAGED_COMMAND_OK')
        repeated=client.submit_final(work['id'],work['version'],'Packaged workflow result','Actual command returned PACKAGED_COMMAND_OK')
        check('frozen-final-delivery-single-acceptance',final['status']=='review' and final['request_id']==repeated['request_id'])
        check('frozen-final-review-remains-human-owned',client.call('human.status',id=final['request_id'])['status']=='pending')
        check('frozen-closed-chain-not-claimed',client.claim()==[])
        if args.live:
            word='PACKAGED_MEMORY_'+uuid.uuid4().hex[:8]
            m=client.send(['claude'],'记住单词 '+word+'。不读写文件或使用其他工具。通过协作工具确认本消息已读并回复 READY。',mode='request_reply')
            first=reply_to(m['id']);check('frozen-claude-live-mcp-reply','READY' in first['text'])
            m=client.send(['claude'],'仅根据你当前原生会话记忆，回复上一轮记住的单词。通过协作工具确认本消息已读并回复，不读文件或群历史。',mode='request_reply')
            second=reply_to(m['id']);check('frozen-claude-session-memory',word in second['text'])
        report['ok']=all(x['ok'] for x in report['checks'])
    finally:
        if pipe:pipe.close()
        kill(proc)
        atomic_json(root/'report.json',report);atomic_json(project/'.test-data'/'v2-packaged-latest.json',report)
    return 0 if report.get('ok') else 1


if __name__=='__main__':sys.exit(main())
