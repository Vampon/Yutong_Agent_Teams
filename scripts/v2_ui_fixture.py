"""Deterministic UI sample data, never used as provider integration evidence."""
from pathlib import Path
import sys,time
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from yutong_teams.config import Config,atomic_json
from yutong_teams.control import Coordinator
from yutong_teams.core.contracts import Principal,HUMAN
from yutong_teams.interfaces.http import serve
root=Path(__file__).resolve().parents[1]/'.test-data'/('v2-ui-'+sys.argv[1] if len(sys.argv)>1 else 'v2-ui')
config=Config(root)
for aid,title,color,role in [('reviewer','方案评审 Agent','#96765d','方案设计、接口评审与任务协调'),('simulator','仿真 Agent','#b68b46','边界工况验证与仿真结果分析'),('knowledge','企业知识 Agent','#5e8d89','规范查询与证据整理')]:
    config.save_agent(dict(id=aid,name=title,kind='external',color=color,role=role))
c=Coordinator(config,start=False);server,token=serve(c,port=int(sys.argv[2]) if len(sys.argv)>2 else 44988)
if not c.repo.list('group'):
    g=c.groups.create(dict(name='控制策略联合评审',members=['reviewer','simulator','knowledge'],goal='完成低速控制策略的接口与边界条件评审，输出可以复核的结论。'))['id']
    p=Principal(actor_id='reviewer',group_id=g);q=Principal(actor_id='simulator',group_id=g);k=Principal(actor_id='knowledge',group_id=g)
    m=c.messages.send(HUMAN,g,dict(text='请先对齐评审范围，再由仿真成员检查边界工况。涉及验收标准的选择请交给我确认。',targets=['reviewer'],mode='request_reply'))
    c.messages.acknowledge(p,g,m['id'],'read');c.messages.send(p,g,dict(reply_to=m['id'],text='我会先明确接口，再安排边界条件检查。\n\n- 仿真成员：整理低速与坡道工况。\n- 知识成员：核对验收条款，并标注原文出处。\n\n遇到标准不一致的地方，会提交到「待我处理」。'))
    n=c.messages.send(p,g,dict(text='请整理低速起步与坡道驻车的边界工况。先确认验收口径，再开始实际验证。',targets=['simulator'],mode='request_reply'))
    c.messages.acknowledge(q,g,n['id'],'read')
    c.agent_call(q,'actor.status',dict(focus='整理工况矩阵',blocked='等待确认坡道工况验收口径'))
    c.agent_call(p,'actor.status',dict(focus='对齐接口与交付依赖'))
    c.agent_call(k,'actor.status',dict(focus='核对规范条款'))
    c.agent_call(q,'human.request',dict(title='坡道起步以哪一版标准验收？',detail='当前任务尚未执行仿真。需要你确认验收基线后，才能确定工况矩阵。',options=['沿用当前项目基线','使用新版试验规范']))
    c.groups.update_context(p,g,dict(version=1,constraints=['所有结论附带依据或可复核的运行输出','变更工程文件前先提交确认'],decision='先完成接口与验收口径确认，再进入仿真验证。'))
    for title,aid in [('整理接口约束','reviewer'),('核对验收规范条款','knowledge'),('验证低速起步边界','simulator'),('复核坡道驻车工况','simulator')]:
        c.tasks.create(HUMAN,g,dict(title=title,agent_id=aid,description='记录输入、依据与交付结果，便于团队复核。'))
atomic_json(root.parent/'v2-ui'/'server.json',dict(url='http://127.0.0.1:%d/#'%server.server_port+token,home=str(root)))
print('UI fixture listening on %d'%server.server_port,flush=True)
try:
    while True:time.sleep(.5)
except KeyboardInterrupt:pass
finally:server.shutdown();server.server_close();c.close()
