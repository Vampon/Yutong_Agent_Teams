"""Inspect actual configured model availability without exposing credentials."""
import json,sys,time,uuid
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from yutong_teams.config import Config,atomic_json
from yutong_teams.control import Coordinator
from yutong_teams.interfaces.http import serve
root=Path(__file__).resolve().parents[1]/'.test-data'/('v2-availability-'+uuid.uuid4().hex[:8]);config=Config(root)
for aid in ('ccu','deepseek'):
    a=config.agent(aid);a['timeout']=20
    if aid=='ccu':a['command']=sys.executable
    config.save_agent(a)
c=Coordinator(config);server,_=serve(c);g=c.groups.create(dict(name='Availability check',members=['ccu','deepseek'],workspace=str(root)))['id']
try:
    for aid in ('ccu','deepseek'):c.admin_call('message.send',dict(group_id=g,targets=[aid],text='只做连接检查。不要读写文件或调用业务工具。用协作工具确认已读并回复 READY。'))
    deadline=time.monotonic()+90
    while time.monotonic()<deadline:
        runs=c.repo.list('run')
        if len(runs)==2 and all(r['status'] in ('failed','completed','cancelled') for r in runs):break
        time.sleep(.2)
    report=[{k:r[k] for k in ('actor_id','status','error')} for r in c.repo.list('run')]
    atomic_json(root/'report.json',report);print(json.dumps({'home':str(root),'results':report}))
finally:server.shutdown();server.server_close();c.close()
