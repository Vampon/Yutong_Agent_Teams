import {
  escape as e,
  icon,
  button,
  markdown,
  date,
  name,
  empty,
} from "../ui.js";
export function context(s, g) {
  const c = g.context;
  return `<div class="page-panel context-page"><div class="panel-toolbar"><div><h2>共享上下文</h2><p>所有成员共同读取的目标、约束和协作记录。</p></div>${button("edit-context", "编辑目标与约束", { ic: "settings" })}</div><section class="context-brief"><div class="section-heading">${icon("book")}<h3>协作目标</h3></div><div class="prose">${c.brief ? markdown(c.brief) : '<p class="muted">尚未设置协作目标。</p>'}</div>${c.constraints.length ? `<ul class="constraints">${c.constraints.map((v) => `<li>${e(v)}</li>`).join("")}</ul>` : ""}</section><div class="context-columns">${[
    ["decisions", "已达成的决定", "decision"],
    ["handoffs", "交接记录", "handoff"],
  ]
    .map(
      ([key, title, kind]) =>
        `<section class="context-section"><div class="section-heading"><h3>${title}</h3>${button("add-context", "添加", { id: kind, ic: "plus", cls: "quiet small" })}</div>${
          c[key].length
            ? c[key]
                .slice()
                .reverse()
                .map(
                  (item) =>
                    `<article class="context-entry"><div class="prose">${markdown(item.text)}</div><footer>${e(name(s, item.by))}<time>${date(item.time)}</time></footer></article>`,
                )
                .join("")
            : '<div class="section-empty">暂无记录</div>'
        }</section>`,
    )
    .join("")}</div></div>`;
}
const events = {
  "group.created": "创建了协作",
  "group.updated": "调整了成员与协作设置",
  "group.paused": "暂停了协作",
  "group.resumed": "继续了协作",
  "actor.joined": "加入了成员",
  "chat.message": "发送了消息",
  "message.read": "确认已读",
  "message.replied": "回复了消息",
  "message.delivered": "消息已送达",
  "message.offered": "领取了消息",
  "message.uncertain": "投递需要核对",
  "message.recovery_decided": "处理了不确定的投递",
  "message.task_superseded": "结束了旧任务投递",
  "context.updated": "更新了共享上下文",
  "task.created": "创建了任务",
  "task.dispatched": "分配了任务",
  "task.submit": "提交了交付",
  "task.approve": "通过了交付",
  "task.revise": "要求修订交付",
  "task.block": "报告了阻碍",
  "task.progress": "更新了进度",
  "task.cancel": "取消了任务",
  "task.retry": "重试了任务",
  "task.start": "启动了任务",
  "task.assign": "调整了任务负责人",
  "human.requested": "请求人类参与",
  "human.responded": "答复了确认事项",
  "tool.permission": "按工具权限策略处理了执行请求",
  "session.connected": "接入了协作",
  "session.online": "已上线",
  "session.offline": "已离线",
  "session.retired": "新建了成员会话",
  "session.stopped": "停止了成员会话",
  "session.enabled": "允许成员继续执行",
  "actor.status_updated": "更新了工作状态",
  "run.started": "开始执行",
  "run.completed": "执行结束",
  "run.failed": "执行失败",
  "run.cancelled": "执行已停止",
  "run.interrupted": "执行意外中断",
  "delivery.budget_wait": "已达到本轮协作次数上限",
};
export function activity(s, g) {
  return `<div class="page-panel"><div class="panel-toolbar"><div><h2>协作动态</h2><p>保留成员通信、任务流转和人类介入的实际记录。</p></div></div><div class="timeline">${g.activity.map((ev) => `<article class="timeline-item"><span class="timeline-node"></span><div><strong>${e(name(s, ev.actor_id))}</strong> ${e(events[ev.kind] || ev.kind)}${ev.data.title ? `<p>${e(ev.data.title)}</p>` : ev.kind === "chat.message" ? `<p>${e(ev.data.text?.slice(0, 150))}</p>` : ev.data.error ? `<p class="error-text">${e(ev.data.error)}</p>` : ""}</div><time>${date(ev.time)}</time></article>`).join("")}</div></div>`;
}
