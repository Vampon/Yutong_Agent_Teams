import {
  escape as e,
  icon,
  button,
  ibutton,
  time,
  name,
  avatar,
  markdown,
  empty,
  receipt,
  options,
} from "../ui.js";
import { runCard } from "./runs.js";
export function chat(s, g, draft = {}) {
  const timeline = [
    ...g.messages.map((m) => ({ order: m.order, html: message(s, g, m) })),
    ...s.runs
      .filter((r) => r.group_id === g.id)
      .map((r) => ({ order: r.order, html: runCard(s, g, r) })),
  ].sort((a, b) => a.order - b.order);
  return `<div class="chat-layout"><div class="conversation scroll" id="conversation">${timeline.length ? timeline.map((x) => x.html).join("") : empty("一起开始这项协作", "说明目标、选择接收人，成员可在执行中相互委派和回复。", "chat")}</div>
 <div class="composer-zone">${g.paused ? `<div class="notice">${icon("pause")}协作已暂停，消息会保留在收件箱。${button("pause", "继续协作", { ic: "play" })}</div>` : ""}<form id="message-form" class="composer">
 ${draft.reply_to ? `<div class="reply-preview">${icon("reply")}<span>回复 ${e(name(s, g.messages.find((m) => m.id === draft.reply_to)?.author || "human"))}：${e(g.messages.find((m) => m.id === draft.reply_to)?.text.slice(0, 90) || "")}</span>${ibutton("clear-reply", "取消引用", "", "close")}</div>` : ""}
 <textarea id="composer-text" name="text" data-draft="text" placeholder="说明任务、补充信息，或 @ 成员…" rows="1" aria-label="消息内容">${e(draft.text || "")}</textarea>
 <div class="composer-tools"><div class="composer-controls"><label class="select-quiet"><span>发送给</span><select name="target" data-draft="target" aria-label="消息接收人">${options([[g.leader, `${name(s, g.leader)} · 队长`], ...g.members.filter((a) => a !== g.leader).map((a) => [a, name(s, a)]), ["@all", "所有成员"]], draft.target || g.leader)}</select></label><span class="divider-v"></span><select class="mode-select" name="mode" data-draft="mode" aria-label="发送方式">${options(
   [
     ["send", "消息"],
     ["request_reply", "需要回复"],
     ["mail", "留信"],
   ],
   draft.mode || "send",
 )}</select></div><div class="composer-send"><span class="composer-shortcut">Ctrl ↵</span><button class="send-button" id="message-submit" type="submit" aria-label="发送消息" title="发送消息（Ctrl + Enter）" ${draft.text?.trim() ? "" : "disabled"}>${icon("send")}</button></div></div></form>${draft.mode === "mail" ? '<div class="composer-hint">留信不会唤起成员，成员可主动读取。</div>' : ""}</div></div>`;
}
function message(s, g, m) {
  const ds = g.deliveries.filter((d) => d.message_id === m.id);
  const original = g.messages.find((x) => x.id === m.reply_to);
  if (m.origin === "task_assignment") {
    const task = g.tasks.find((t) => t.id === m.task_id);
    return `<article class="delegation" id="message-${m.id}"><details data-disclosure-key="message:${m.id}"><summary>${icon("users")}<span><strong>${e(name(s, m.author))}</strong> 分配任务给 ${m.targets.map((t) => e(name(s, t))).join("、")}<b>${e(task?.title || m.text.split("\n")[0])}</b></span><time>${time(m.time, true)}</time>${icon("chevron")}</summary><div class="delegation-body prose">${markdown(m.text)}${task ? button("task", "查看任务", { id: task.id, cls: "small" }) : ""}</div></details></article>`;
  }
  return `<article class="message ${m.author === "human" ? "from-human" : ""}" id="message-${m.id}">${avatar(s, m.author)}<div class="message-main"><div class="message-meta"><strong>${e(name(s, m.author))}</strong><time title="${e(dateTitle(m.time))}">${time(m.time, true)}</time><span class="message-route">${icon(m.mode === "mail" ? "mail" : "arrow")}${m.targets.map((t) => e(name(s, t))).join("、")}</span>${m.mode === "request_reply" ? '<span class="request-label">需要回复</span>' : ""}${ibutton("reply", "回复此消息", m.id, "reply")}</div>${original ? `<button class="quote" data-action="jump-message" data-id="${original.id}">${e(name(s, original.author))} · ${e(original.text.slice(0, 100))}</button>` : ""}<div class="message-body prose">${markdown(m.text)}</div><div class="message-receipts">${ds
    .map((d) => {
      const [label, cls] = receipt(d);
      return `<button class="receipt ${cls}" data-action="receipt" data-id="${e(d.id)}"><span class="receipt-dot"></span>${ds.length > 1 ? e(name(s, d.recipient)) + " · " : ""}${label}</button>`;
    })
    .join(
      "",
    )}${m.origin === "adapter_response" ? '<span class="subtle">接口返回</span>' : ""}</div></div></article>`;
}
function dateTitle(value) {
  return new Date(value).toLocaleString("zh-CN", { hour12: false });
}
export function inbox(s, g, filter = "all") {
  const rows = g.deliveries
    .filter(
      (d) =>
        (filter === "all" || d.recipient === filter) &&
        (!d.read_at ||
          d.state === "uncertain" ||
          (d.mode === "request_reply" && !d.replied_at)),
    )
    .filter((d) => d.state !== "dismissed");
  return `<div class="page-panel"><div class="panel-toolbar"><div><h2>收件箱</h2><p>查看待送达、未读和等待回复的消息。</p></div><select id="inbox-filter" aria-label="按成员筛选">${options([["all", "所有成员"], ["human", "发给我的"], ...g.members.map((a) => [a, name(s, a)])], filter)}</select></div>${
    rows.length
      ? `<div class="inbox-list">${rows
          .map((d) => {
            const m = g.messages.find((x) => x.id === d.message_id);
            if (!m) return "";
            const [label, cls] = receipt(d);
            return `<button class="inbox-row" data-action="receipt" data-id="${e(d.id)}">${avatar(s, d.recipient)}<div><div class="row-title">${e(name(s, d.recipient))}<span class="badge ${cls}">${label}</span><time>${time(m.time)}</time></div><p>${e(m.text.slice(0, 170))}</p><small>来自 ${e(name(s, m.author))}${m.mode === "mail" ? " · 留信" : ""}</small></div>${icon("chevron")}</button>`;
          })
          .join("")}</div>`
      : empty("收件箱已处理完", "新的消息和待核对的投递会出现在这里。", "inbox")
  }</div>`;
}
