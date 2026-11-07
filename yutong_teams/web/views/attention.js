import {
  escape as e,
  icon,
  button,
  avatar,
  name,
  date,
  empty,
  sessionNames,
  activeStatuses,
} from "../ui.js";
export function attention(s, groupId = "") {
  const pending = s.requests.filter(
    (r) => r.status === "pending" && (!groupId || r.group_id === groupId),
  );
  return `<div class="page-panel attention-page"><div class="panel-toolbar"><div><h2>待我处理</h2><p>成员的提问、工具执行确认和交付审核集中在这里。</p></div><span class="count-label">${pending.length} 项</span></div>${pending.length ? `<div class="attention-cards">${pending.map((r) => `<button class="attention-card" data-action="request" data-id="${r.id}"><div class="attention-card-top"><span class="request-kind kind-${r.kind}">${icon(r.kind === "review" ? "check" : r.kind === "tool" ? "shield" : "chat")}${r.kind === "review" ? "交付审核" : r.kind === "tool" ? "工具确认" : "问题答复"}</span><time>${date(r.created)}</time></div><h3>${e(r.title)}</h3><p>${e(r.detail?.slice(0, 160) || r.tool || "")}</p><footer>${avatar(s, r.actor_id, "tiny")}<span>${e(name(s, r.actor_id))}</span><span class="subtle">${e(s.groups.find((g) => g.id === r.group_id)?.name || "")}</span>${icon("arrow")}</footer></button>`).join("")}</div>` : empty("暂时没有待处理事项", "成员需要你的判断时，这里会及时提醒。", "check")}</div>`;
}
export function sidePanel(s, g) {
  const pending = s.requests.filter(
    (r) => r.status === "pending" && r.group_id === g.id,
  );
  const uncertain = g.deliveries.filter((d) => d.state === "uncertain");
  return `<aside class="team-panel scroll">${
    pending.length
      ? `<section class="side-section needs-you"><div class="section-heading"><h3>需要你参与</h3><span class="count-label">${pending.length}</span></div>${pending
          .slice(0, 4)
          .map(
            (r) =>
              `<button class="attention-mini" data-action="request" data-id="${r.id}"><span class="attention-mini-icon">${icon(r.kind === "tool" ? "shield" : r.kind === "review" ? "check" : "chat")}</span><span><strong>${e(r.title)}</strong><small>${e(name(s, r.actor_id))}</small></span>${icon("chevron")}</button>`,
          )
          .join(
            "",
          )}${pending.length > 4 ? button("nav-attention", "查看全部", { cls: "quiet small" }) : ""}</section>`
      : ""
  }
 ${uncertain.length ? `<section class="side-section"><button class="uncertain-alert" data-action="tab" data-id="inbox">${icon("alert")}<span>${uncertain.length} 条投递需要核对</span>${icon("chevron")}</button></section>` : ""}
 <section class="side-section"><div class="section-heading"><h3>协作成员</h3>${button("edit-group", "管理", { cls: "quiet small" })}</div><div class="member-list">${g.members
   .map((a) => {
     const session = g.sessions.find((x) => x.actor_id === a);
     const context = g.actor_context.find((x) => x.actor_id === a);
     const unread = g.deliveries.filter(
       (d) => d.recipient === a && !d.read_at && d.state !== "dismissed",
     ).length;
     return `<button class="member-row" data-action="member" data-id="${a}">${avatar(s, a)}<div class="member-detail"><div><strong>${e(name(s, a))}</strong>${a === g.leader ? '<span class="leader-label">队长</span>' : ""}</div><span class="member-state"><i class="state-dot state-${session?.state}"></i>${sessionNames[session?.state] || "未连接"}${unread ? `<span class="unread-count">${unread} 待收</span>` : ""}</span>${context?.blocked ? `<p class="error-text">${e(context.blocked)}</p>` : context?.focus ? `<p>${e(context.focus)}</p>` : ""}</div>${icon("chevron")}</button>`;
   })
   .join(
     "",
   )}</div>${button("connections", "连接外部成员", { ic: "link", cls: "wide quiet" })}</section>
 ${g.context.brief ? `<section class="side-section side-brief"><div class="section-heading"><h3>共同目标</h3>${button("tab", "查看", { id: "context", cls: "quiet small" })}</div><p>${e(g.context.brief.slice(0, 300))}</p></section>` : ""}
 ${
   g.tasks.some((t) => t.status === "review")
     ? `<section class="side-section"><h3>等待审核的交付</h3>${g.tasks
         .filter((t) => t.status === "review")
         .map(
           (t) =>
             `<button class="side-delivery" data-action="task" data-id="${t.id}">${icon("check")}<span>${e(t.title)}</span>${icon("chevron")}</button>`,
         )
         .join("")}</section>`
     : ""
 }</aside>`;
}
