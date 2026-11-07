import {
  escape as e,
  icon,
  button,
  avatar,
  name,
  taskNames,
  empty,
} from "../ui.js";
export function tasks(s, g) {
  const columns = [
    ["待开始", ["todo", "queued"]],
    ["进行中", ["running"]],
    ["待处理", ["blocked", "failed", "interrupted", "review"]],
    ["已完成", ["done", "cancelled"]],
  ];
  return `<div class="board-wrap"><div class="panel-toolbar"><div><h2>任务看板</h2><p>委派工作、跟踪依赖，审核真实交付。</p></div>${button("new-task", "新建任务", { ic: "plus", cls: "primary" })}</div><div class="board">${columns
    .map(([title, statuses], index) => {
      const items = g.tasks.filter((t) => statuses.includes(t.status));
      return `<section class="board-column"><div class="column-heading"><span class="column-marker marker-${index}"></span><h3>${title}</h3><span>${items.length}</span></div><div class="task-stack">${items.map((t) => `<button class="task-card" data-action="task" data-id="${t.id}"><div class="task-tags"><span class="task-status status-${t.status}">${taskNames[t.status]}</span>${t.depends_on.length ? `<span>${icon("link")}${t.depends_on.filter((d) => g.tasks.find((x) => x.id === d)?.status === "done").length}/${t.depends_on.length}</span>` : ""}</div><h4>${e(t.title)}</h4>${t.description ? `<p>${e(t.description.slice(0, 100))}</p>` : ""}${t.error ? `<div class="task-error">${icon("alert")}${e(t.error.slice(0, 90))}</div>` : ""}<footer>${avatar(s, t.agent_id, "tiny")}<span>${e(name(s, t.agent_id))}</span>${t.status === "review" ? '<span class="review-dot"></span>' : ""}</footer></button>`).join("") || '<div class="column-empty">暂无任务</div>'}</div></section>`;
    })
    .join("")}</div></div>`;
}
