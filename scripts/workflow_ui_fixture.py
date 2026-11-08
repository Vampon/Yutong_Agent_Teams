"""Isolated final-delivery UI fixture, without real model calls."""
import json
from pathlib import Path
import sys
import time
import uuid
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from yutong_teams.config import Config, atomic_json
from yutong_teams.control import Coordinator
from yutong_teams.core.contracts import HUMAN, Principal
from yutong_teams.interfaces.http import serve

root = Path(__file__).resolve().parents[1] / '.test-data' / ('workflow-ui-' + uuid.uuid4().hex[:8])
config = Config(root)
for aid in ('lead', 'peer'):
    config.save_agent(dict(id=aid, name='队长' if aid == 'lead' else '评审成员', kind='external'))
c = Coordinator(config, start=False)
server, token = serve(c, port=0)
gid = c.groups.create(dict(name='最终交付验收', members=['lead', 'peer'], review=True))['id']
p, q = Principal(actor_id='lead', group_id=gid), Principal(actor_id='peer', group_id=gid)
m = c.messages.send(HUMAN, gid, dict(text='验证内部评审和最终验收', targets=['lead'], mode='request_reply'))
c.messages.read_inbox(p, gid, [m['id']])
t = c.tasks.create(p, gid, dict(title='内部代码评审', agent_id='peer', work_id=m['root_id']))
c.agent_call(q, 'task.update', dict(id=t['id'], version=t['version'], action='submit', text='边界条件与测试结果核对通过。'))
w = c.agent_call(p, 'work.submit', dict(work_id=m['root_id'], version=1, title='排序实现与评审结果',
    text='## 交付结果\n实现与独立评审已完成。\n\n- 边界条件检查通过\n- 回归测试通过\n- 无遗留问题\n\n请确认本次最终交付。'))
atomic_json(root.parent / 'workflow-ui-server.json', dict(url=c.endpoint + '/#' + token, token=token,
    group_id=gid, work_id=w['id'], request_id=w['request_id'], home=str(root)))
print('Workflow fixture ready', flush=True)
try:
    while True: time.sleep(.5)
except KeyboardInterrupt:
    pass
finally:
    server.shutdown(); server.server_close(); c.close()
