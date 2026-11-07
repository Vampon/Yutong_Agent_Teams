"""Real persistent Claude session + live MCP, in an isolated test workspace."""
import json
from pathlib import Path
import sys
import time
import uuid
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from yutong_teams.config import Config, atomic_json
from yutong_teams.control import Coordinator
from yutong_teams.interfaces.http import serve

aid=sys.argv[1] if len(sys.argv)>1 else 'claude'
assert aid in ('claude','matlab')
root=Path(__file__).resolve().parents[1]/'.test-data'/('v2-'+aid+'-memory-'+uuid.uuid4().hex[:8])
config=Config(root); control=Coordinator(config); server,_=serve(control)
report={'home':str(root),'checks':[]}
word='memory_'+uuid.uuid4().hex[:8]
group=control.admin_call('group.create',{'name':'Persistent session probe','members':[aid],'workspace':str(root)})
try:
    for prompt in [f'请记住单词 {word}。不要读写文件或调用其他工具。调用协作工具确认本消息已读，然后使用 teams_reply 回复 READY。',
                   '我上一条让你记住的单词是什么？仅根据当前原生会话记忆回答，不读取群历史或其他文件。通过 teams_inbox_read 确认当前消息，再用 teams_reply 回复那个单词。']:
        sent=control.admin_call('message.send',{'group_id':group['id'],'text':prompt,'mode':'request_reply'})
        deadline=time.monotonic()+240
        while time.monotonic()<deadline:
            runs=[r for r in control.repo.list('run') if r['message_id']==sent['id']]
            if runs and runs[-1]['status'] in ('completed','failed','cancelled'):break
            for r in control.repo.list('request'):
                if r['kind']=='tool' and r['status']=='pending':
                    control.admin_call('attention.answer',{'id':r['id'],'allow':False})
            time.sleep(.3)
        delivery=control.repo.require('delivery',sent['id']+':'+aid)
        replies=[m for m in control.repo.list('message',group['id']) if m['reply_to']==sent['id']]
        session=control.repo.require('session',group['id']+':'+aid)
        item={'status':runs[-1]['status'] if runs else 'timeout','read':bool(delivery['read_at']),'replied':bool(delivery['replied_at']),
              'reply':'\n'.join(m['text'] for m in replies),'session_id':session['provider_id'],'error':runs[-1]['error'] if runs else ''}
        driver=control.supervisor.drivers.get(group['id']+':'+aid)
        item['pid']=driver.channel.proc.pid if driver and driver.channel else None
        report['checks'].append(item);print(json.dumps(item,ensure_ascii=True),flush=True)
        if item['status']!='completed':break
    report['ok']=len(report['checks'])==2 and all(r['read'] and r['replied'] and r['status']=='completed' for r in report['checks']) and word in report['checks'][-1]['reply'] and report['checks'][0]['pid']==report['checks'][1]['pid']
finally:
    atomic_json(root/'report.json',report)
    server.shutdown();server.server_close();control.close()
    print(json.dumps({'report':str(root/'report.json'),'ok':report.get('ok',False)}),flush=True)
sys.exit(0 if report.get('ok') else 1)
