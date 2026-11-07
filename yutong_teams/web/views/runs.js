import {
  escape as e,
  icon,
  avatar,
  name,
  markdown,
  button,
  time,
  date,
  activeStatuses,
} from "../ui.js";

export const runNames = {
  starting: "正在连接",
  running: "执行中",
  waiting: "等待确认",
  completed: "执行结束",
  failed: "执行失败",
  cancelled: "已停止",
  interrupted: "执行中断",
};
const toolNames = {
  pending: "等待执行",
  awaiting_approval: "等待确认",
  running: "执行中",
  completed: "已返回",
  failed: "失败",
  denied: "已拒绝",
};
export function clockValue(run) {
  const seconds = Math.max(
    0,
    Math.floor(
      ((run.finished ? Date.parse(run.finished) : Date.now()) -
        Date.parse(run.created)) /
        1000,
    ),
  );
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`;
}
function blocks(run) {
  return (run.trace || [])
    .map((b) => {
      if (b.kind === "text")
        return `<div class="trace-text prose">${markdown(b.text)}</div>`;
      if (b.kind === "status")
        return `<p class="trace-status">${e(b.text)}</p>`;
      if (b.kind !== "tool") return "";
      const pending = ["running", "pending", "awaiting_approval"].includes(b.status);
      const label =
        pending && !activeStatuses.includes(run.status)
          ? "已调用"
          : toolNames[b.status] || "已调用";
      return `<details class="trace-tool" data-disclosure-key="tool:${e(run.id)}:${e(b.id)}"><summary>${icon(b.status === "failed" || b.status === "denied" ? "alert" : b.status === "completed" ? "check" : "terminal")}<span>${e(b.name)}</span><small>${label}</small>${icon("chevron")}</summary><div class="trace-tool-body">${b.arguments ? `<h4>输入</h4><pre>${e(b.arguments)}</pre>` : ""}${b.result ? `<h4>输出</h4><pre>${e(b.result)}</pre>` : '<p class="muted">运行器尚未提供工具结果。</p>'}</div></details>`;
    })
    .join("");
}
function waiting(s, run) {
  const request = s.requests.find(
    (r) => r.run_id === run.id && r.status === "pending",
  );
  return request
    ? `<div class="run-waiting">${icon("shield")}<span>${e(request.title)}</span>${button("request", "处理", { id: request.id, cls: "small" })}</div>`
    : "";
}
export function runCard(s, g, run) {
  const active = activeStatuses.includes(run.status);
  return `<details class="run-card ${active ? "is-live" : ""}" id="run-${e(run.id)}" data-disclosure-key="run:${e(run.id)}" ${active ? "open" : ""}>
    <summary>${avatar(s, run.actor_id)}<strong>${e(name(s, run.actor_id))}</strong><span class="run-state ${run.status}">${active ? '<i class="pulse"></i>' : icon(run.status === "completed" ? "check" : "alert")}${runNames[run.status] || e(run.status)}</span><time data-run-clock="${e(run.id)}">${clockValue(run)}</time>${icon("chevron")}</summary>
    <div class="run-card-body"><div class="run-stream" data-run-scroll="${e(run.id)}">${blocks(run) || `<p class="trace-status">${run.status === "starting" ? "正在连接运行器，等待第一条输出…" : active ? "等待运行器输出…" : "这次执行没有记录过程输出。"}</p>`}</div>${waiting(s, run)}${run.error ? `<p class="run-error">${e(run.error)}</p>` : ""}<footer><span>${time(run.created, true)} 开始</span>${button("run", "查看完整过程", { id: run.id, cls: "quiet small", ic: "chevron" })}</footer></div></details>`;
}
export function runDetail(s, run) {
  const active = activeStatuses.includes(run.status);
  return `<div class="run-detail" data-run-detail="${e(run.id)}"><div class="detail-meta">${avatar(s, run.actor_id)}<strong>${e(name(s, run.actor_id))}</strong><span class="run-state ${run.status}">${runNames[run.status] || e(run.status)}</span><time>${date(run.created)}</time><span data-run-clock="${e(run.id)}">${clockValue(run)}</span></div>${waiting(s, run)}
    <div class="run-stream detail-stream" data-run-scroll="detail:${e(run.id)}">${blocks(run) || '<p class="muted">等待运行器提供过程输出。</p>'}${run.trace_truncated ? '<p class="trace-status">过程过长，部分内容已截断。</p>' : ""}</div>
    ${run.error ? `<div class="notice warning">${e(run.error)}</div>` : ""}${!active && run.result ? `<details class="run-result" data-disclosure-key="result:${e(run.id)}"><summary>运行器最终输出</summary><div class="prose">${markdown(run.result)}</div></details>` : ""}</div>`;
}
