"""Real Claude -> MATLAB collaboration; only the explicitly bounded 2+2 tool task."""
import json
from pathlib import Path
import sys,time,uuid
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from yutong_teams.config import Config,atomic_json
from yutong_teams.control import Coordinator
from yutong_teams.interfaces.http import serve

root=Path(__file__).resolve().parents[1]/'.test-data'/('v2-team-'+uuid.uuid4().hex[:8])
config=Config(root);a=config.agent('matlab');a['timeout']=420;config.save_agent(a)
c=Coordinator(config);server,_=serve(c)
g=c.admin_call('group.create',dict(name='真实协作验收',members=['claude','matlab'],goal='验证原生协作工具和真实 MATLAB 计算',workspace=str(root)))
report={'home':str(root),'checks':[]}
try:
    m=c.admin_call('message.send',dict(group_id=g['id'],mode='request_reply',text='请通过 teams_task_create 把计算 disp(2+2) 的任务委派给 matlab 成员，要求它用真实 MATLAB 工具执行并通过 teams_task_update 提交实际输出。不读写任何工程文件、不调用其他成员。你只负责委派，并回复说明已经委派；收到交付审核通过的通知后再汇报确认结果。'))
    deadline=time.monotonic()+480
    reviewed=False
    while time.monotonic()<deadline:
        for r in c.repo.list('request',g['id']):
            if r['status']!='pending':continue
            if r['kind']=='tool':
                args=json.dumps(r.get('arguments',{}),ensure_ascii=False)
                allowed=('disp(2+2)' in args.replace(' ','')) and not any(x in args.lower() for x in ('delete','write','save','system','eval('))
                c.admin_call('attention.answer',dict(id=r['id'],allow=allowed))
                report['checks'].append({'tool':r.get('tool'),'allowed':allowed})
            elif r['kind']=='review':
                t=c.repo.require('task',r['task_id'])
                if t['agent_id']=='matlab' and '4' in t['result']:
                    c.admin_call('attention.answer',dict(id=r['id'],allow=True));reviewed=True
        runs=c.repo.list('run',g['id'])
        if reviewed and not any(r['status'] in ('starting','running','waiting') for r in runs):break
        if any(r['status']=='failed' for r in runs):break
        time.sleep(.3)
    report.update(runs=[{k:r.get(k) for k in ('id','actor_id','status','error','result')} for r in c.repo.list('run',g['id'])],
                  tasks=c.repo.list('task',g['id']),messages=c.repo.list('message',g['id']),
                  deliveries=c.repo.list('delivery',g['id']))
    report['ok']=reviewed and any(t['agent_id']=='matlab' and t['status']=='done' for t in report['tasks'])
    atomic_json(root/'report.json',report)
    print(json.dumps({'home':str(root),'ok':report['ok'],'runs':[{k:r[k] for k in ('actor_id','status','error')} for r in report['runs']]},ensure_ascii=False))
finally:
    server.shutdown();server.server_close();c.close()
