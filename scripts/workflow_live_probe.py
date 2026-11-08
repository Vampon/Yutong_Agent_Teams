"""Real native-agent workflow acceptance in an isolated user/workspace directory."""
import argparse
import json
from pathlib import Path
import sys
import time
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from yutong_teams.config import Config, atomic_json
from yutong_teams.control import Coordinator
from yutong_teams.interfaces.http import serve
from yutong_teams.core.contracts import HUMAN


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--worker', choices=['claude', 'deepseek'], default='claude')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1] / '.test-data' / ('workflow-live-' + uuid.uuid4().hex[:8])
    config = Config(root)
    c = Coordinator(config)
    server, token = serve(c, port=0)
    report = dict(home=str(root), worker=args.worker, checks=[])
    def check(label, ok, **fields):
        item = dict(check=label, ok=bool(ok), **fields)
        report['checks'].append(item)
        atomic_json(root / 'report.json', report)
        print(json.dumps(item, ensure_ascii=False), flush=True)
        if not ok:
            raise AssertionError(label)
    try:
        c.admin_call('permissions.configure', dict(mode='auto', review=True))
        c.admin_call('agent.clone', dict(id='lead', source_id='claude', name='验收测试队长', role='团队协调',
            instructions='这是隔离的只读验收。内部工作只通过 teams_task_create 委派给 peer 一次。不要另发工作消息。收到内部完成结果后读取任务和 current_work，直接调用 teams_submit_final 提交一次最终交付。不需要互相确认或向人类另发确认问题。禁止修改任何文件。'))
        c.admin_call('agent.clone', dict(id='peer', source_id=args.worker, name='验收测试评审', role='独立评审',
            instructions='这是隔离的只读验收。只处理分配给你的内部任务；调用 progress，核对结果，再 submit 真实结论。任务提交自动回报，不需要额外回复。禁止修改文件，不自行提交最终交付。'))
        gid = c.groups.create(dict(name='真实最终交付验收', members=['lead', 'peer'], leader='lead',
            workspace=str(root / 'workspace'), review=True, max_turns=8,
            goal='完成一次独立的表达式边界评审；内部评审由成员完成，队长只提交一份最终交付。'))['id']
        m = c.messages.send(HUMAN, gid, dict(targets=['lead'], mode='request_reply',
            text='请让 peer 独立评审表达式 min(10, max(0, x))：x=-1、5、11 时应分别为 0、5、10。只需要一个内部评审任务；核对后由你汇总并调用 teams_submit_final 提交最终交付。不要写文件、创建其他任务或提出额外确认问题。'))
        deadline = time.monotonic() + 420
        request = None
        while time.monotonic() < deadline:
            requests = c.repo.list('request', gid)
            finals = [r for r in requests if r['kind'] == 'final_review']
            runs = c.repo.list('run', gid)
            failed = [r for r in runs if r['status'] == 'failed']
            if failed:
                check('native-agents-complete', False, errors=[r['error'] for r in failed])
            if finals and all(r['status'] == 'completed' for r in runs):
                request = finals[0]
                break
            time.sleep(.25)
        check('single-final-request', request is not None and len(c.repo.list('request', gid)) == 1)
        tasks = c.repo.list('task', gid)
        runs = c.repo.list('run', gid)
        check('one-internal-review-completed', len(tasks) == 1 and tasks[0]['status'] == 'done')
        check('one-worker-execution', len([r for r in runs if r['actor_id'] == 'peer']) == 1, runs=len(runs))
        check('independent-native-sessions', len({s['provider_id'] for s in c.repo.list('session', gid) if s['provider_id']}) == 2)
        c.admin_call('attention.answer', dict(id=request['id'], allow=True))
        before = len(runs)
        quiet_until = time.monotonic() + 20
        while time.monotonic() < quiet_until:
            time.sleep(.2)
        check('acceptance-does-not-wake-agents', len(c.repo.list('run', gid)) == before,
              observation_seconds=20, final_status=c.repo.require('work', m['root_id'])['status'])
        check('no-pending-acceptance', not any(r['status'] == 'pending' for r in c.repo.list('request', gid)))
        report['ok'] = True
    except Exception as exc:
        report.update(ok=False, error=config.redact(str(exc)))
        raise
    finally:
        server.shutdown(); server.server_close(); c.close()
        atomic_json(root / 'report.json', report)
        atomic_json(Path(__file__).resolve().parents[1] / 'docs' / 'evidence' / ('v040-live-' + args.worker + '.json'), report)
    return 0


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    sys.exit(main())
