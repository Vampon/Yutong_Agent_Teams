import * as U from "./ui.js";
import * as D from "./dialogs.js";
import { chat, inbox } from "./views/chat.js";
import { tasks } from "./views/tasks.js";
import { context, activity } from "./views/context.js";
import { attention, sidePanel } from "./views/attention.js";
import { agents, settings } from "./views/agents.js";
import { presets } from "./personas.js";
import { runDetail, clockValue } from "./views/runs.js";
const { escape: e, icon, button, ibutton, name, options, empty } = U;
U.installAvatarImages();
const token =
  location.hash.slice(1) || sessionStorage.getItem("teams-token") || "";
sessionStorage.setItem("teams-token", token);
history.replaceState(null, "", location.pathname);
let state = null,
  view = "team",
  groupId = localStorage.getItem("teams-group") || "",
  tab = "chat",
  inboxFilter = "all",
  drafts = {},
  editing = {},
  connection = null,
  composing = false,
  fetching = false,
  pendingRender = false;
let openRunId = "";
const disclosures = new Map();
const app = document.querySelector("#app"),
  modal = document.querySelector("#dialog");
export async function api(op, data = {}) {
  const response = await fetch("/api", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: "Bearer " + token,
    },
    body: JSON.stringify({ op, data }),
  });
  const value = await response.json();
  if (!value.ok) throw new Error(value.error || "操作未完成");
  return value.data;
}
function toast(text) {
  const el = document.querySelector("#toast");
  el.textContent = text;
  el.classList.add("visible");
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => el.classList.remove("visible"), 4500);
}
function current() {
  return state?.groups.find((g) => g.id === groupId);
}
function draft() {
  return drafts[groupId] || (drafts[groupId] = {});
}
function open(html, wide = false) {
  openRunId = "";
  modal.innerHTML = html;
  modal.classList.toggle("wide-dialog", wide);
  if (!modal.open) modal.showModal();
  modal
    .querySelector("input:not([type=checkbox]):not([readonly]),textarea")
    ?.focus();
}
function close() {
  openRunId = "";
  modal.close();
  connection = null;
}
async function refresh(force = false) {
  if (fetching) return;
  fetching = true;
  try {
    const next = await api("state");
    const changed = !state || next.revision !== state.revision;
    state = next;
    if (!state.groups.some((g) => g.id === groupId))
      groupId = state.groups[0]?.id || "";
    if (changed || force) {
      if (composing) pendingRender = true;
      else if (force || view !== "settings") render(!force);
      if (openRunId && modal.open) {
        const id = openRunId;
        const run = await api("run.get", { id });
        if (modal.open && openRunId === id) {
          const restore = preserveStreams(modal);
          modal.querySelector(".dialog-body").innerHTML = runDetail(state, run);
          restore();
        }
      }
    }
  } catch (err) {
    if (!state) app.innerHTML = empty("无法连接协作服务", err.message, "alert");
    else toast(err.message);
  } finally {
    fetching = false;
  }
}
function preserveStreams(root) {
  const scrolls = [...root.querySelectorAll("[data-run-scroll]")].map((el) => ({
    key: el.dataset.runScroll,
    top: el.scrollTop,
    follow: el.scrollHeight - el.scrollTop - el.clientHeight < 32,
  }));
  return () => {
    root.querySelectorAll("[data-disclosure-key]").forEach((el) => {
      if (disclosures.has(el.dataset.disclosureKey))
        el.open = disclosures.get(el.dataset.disclosureKey);
    });
    root.querySelectorAll("[data-run-scroll]").forEach((el) => {
      const old = scrolls.find((x) => x.key === el.dataset.runScroll);
      el.scrollTop = !old || old.follow ? el.scrollHeight : old.top;
    });
  };
}
function resizeComposer() {
  const el = document.querySelector("#composer-text");
  if (!el) return;
  const top = el.scrollTop;
  el.style.height = "auto";
  const maximum = parseFloat(getComputedStyle(el).maxHeight);
  el.style.height = Math.min(maximum, el.scrollHeight) + "px";
  el.style.overflowY = el.scrollHeight > maximum ? "auto" : "hidden";
  el.scrollTop = top;
  const submit = document.querySelector("#message-submit");
  if (submit) submit.disabled = !el.value.trim();
}
function render(preserveEditor = false) {
  const g = current(),
    pending = state.requests.filter((r) => r.status === "pending").length;
  const focus = document.activeElement,
    focusId = focus?.id,
    selection =
      typeof focus?.selectionStart === "number"
        ? [focus.selectionStart, focus.selectionEnd]
        : null;
  const feed = document.querySelector("#conversation");
  const oldScroll = feed?.scrollTop || 0;
  const follow =
    !feed || feed.scrollHeight - feed.scrollTop - feed.clientHeight < 80;
  const page = document.querySelector(".page-panel");
  const pageScroll = page?.scrollTop || 0;
  const editor = preserveEditor
    ? document.querySelector("#message-form")
    : null;
  const restoreStreams = preserveStreams(app);
  const anchor =
    feed &&
    [...feed.children].find(
      (el) =>
        el.getBoundingClientRect().bottom >
        feed.getBoundingClientRect().top + 2,
    );
  const anchorOffset = anchor
    ? anchor.getBoundingClientRect().top - feed.getBoundingClientRect().top
    : 0;
  app.innerHTML = `<aside class="sidebar"><div class="brand"><img class="brand-mark" src="/assets/app-logo.png" alt="" width="34" height="34" draggable="false" /><strong>Yutong Teams</strong></div><nav class="primary-nav"><button data-action="nav-team" class="nav-item ${view === "team" ? "selected" : ""}">${icon("chat")}<span>协作空间</span></button><button data-action="nav-attention" class="nav-item ${view === "attention" ? "selected" : ""}">${icon("inbox")}<span>待我处理</span>${pending ? `<b>${pending}</b>` : ""}</button><button data-action="nav-agents" class="nav-item ${view === "agents" ? "selected" : ""}">${icon("users")}<span>智能体</span></button></nav><div class="sidebar-heading"><span>我的协作</span>${ibutton("new-group", "新建协作", "", "plus")}</div><nav class="group-list scroll">${state.groups.map((item) => `<button class="group-link ${view === "team" && groupId === item.id ? "selected" : ""}" data-action="select-group" data-id="${item.id}">${icon("chat")}<span>${e(item.name)}</span>${state.requests.some((r) => r.group_id === item.id && r.status === "pending") ? '<i class="attention-dot"></i>' : ""}</button>`).join("")}</nav><div class="sidebar-bottom"><button class="nav-item ${view === "settings" ? "selected" : ""}" data-action="nav-settings">${icon("settings")}<span>设置</span></button></div></aside><main class="workspace">${view === "team" ? (g ? team(g) : `<div class="welcome">${empty("创建你的第一个协作", "选择队长与成员，让不同 Agent 围绕同一个目标协作。", "layers", button("new-group", "新建协作", { ic: "plus", cls: "primary" }))}</div>`) : view === "attention" ? attention(state) : view === "agents" ? agents(state) : settings(state)}</main>`;
  const fresh = document.querySelector("#conversation");
  if (editor) document.querySelector("#message-form")?.replaceWith(editor);
  restoreStreams();
  resizeComposer();
  if (fresh) {
    const nextAnchor = anchor?.id && document.getElementById(anchor.id);
    fresh.scrollTop = follow ? fresh.scrollHeight : oldScroll;
    if (!follow && nextAnchor)
      fresh.scrollTop +=
        nextAnchor.getBoundingClientRect().top -
        fresh.getBoundingClientRect().top -
        anchorOffset;
  }
  const newpage = document.querySelector(".page-panel");
  if (newpage) newpage.scrollTop = pageScroll;
  if (focusId) {
    const next = document.getElementById(focusId);
    if (next && next !== document.activeElement) {
      next.focus({ preventScroll: true });
      if (selection && next.setSelectionRange)
        next.setSelectionRange(...selection);
    }
  }
}
function team(g) {
  const running = state.runs.filter(
    (r) => r.group_id === g.id && U.activeStatuses.includes(r.status),
  ).length;
  const tabs = [
    ["chat", "chat", "群聊"],
    ["tasks", "grid", "任务看板"],
    ["inbox", "inbox", "收件箱"],
    ["context", "book", "共享上下文"],
    ["activity", "activity", "动态"],
  ];
  return `<header class="workspace-header"><h1>${e(g.name)}</h1><div class="header-actions">${running ? `<span class="running-label"><span class="pulse"></span>${running} 位成员执行中</span>` : ""}${button("edit-group", "成员", { ic: "users", cls: "quiet" })}${button("pause", g.paused ? "继续" : "暂停", { ic: g.paused ? "play" : "pause", cls: g.paused ? "primary" : "quiet" })}</div></header><nav class="tabs">${tabs.map(([id, ic, label]) => `<button class="tab ${tab === id ? "active" : ""}" data-action="tab" data-id="${id}">${icon(ic)}${label}${id === "tasks" && g.tasks.filter((t) => !["done", "cancelled"].includes(t.status)).length ? `<span class="tab-count">${g.tasks.filter((t) => !["done", "cancelled"].includes(t.status)).length}</span>` : ""}</button>`).join("")}</nav><div class="team-content"><section class="work-surface ${tab === "chat" ? "chat-surface" : ""}">${tab === "chat" ? chat(state, g, draft()) : tab === "tasks" ? tasks(state, g) : tab === "inbox" ? inbox(state, g, inboxFilter) : tab === "context" ? context(state, g) : activity(state, g)}</section>${sidePanel(state, g)}</div>`;
}
async function connectionFor(aid, rotate = false) {
  connection = await api("connection.issue", {
    group_id: groupId,
    actor_id: aid,
    rotate,
  });
  open(D.connectionDetail(state, current(), connection), true);
}
const actions = {
  "close-dialog": close,
  "nav-team": () => {
    view = "team";
    render();
  },
  "nav-attention": () => {
    view = "attention";
    render();
  },
  "nav-agents": () => {
    view = "agents";
    render();
  },
  "nav-settings": () => {
    view = "settings";
    render();
  },
  "select-group": (id) => {
    groupId = id;
    localStorage.setItem("teams-group", id);
    view = "team";
    tab = "chat";
    render();
  },
  tab: (id) => {
    tab = id;
    render();
  },
  "new-group": () => {
    editing = {};
    open(D.groupForm(state, null));
  },
  "edit-group": () => {
    editing = { group: current() };
    open(D.groupForm(state, current()));
  },
  pause: async () => {
    await api("group.pause", { group_id: groupId, resume: current().paused });
  },
  "new-task": () => {
    editing = {};
    open(D.taskForm(state, current()));
  },
  task: (id) => {
    editing = { task: current().tasks.find((t) => t.id === id) };
    open(D.taskDetail(state, current(), editing.task), true);
  },
  "task-action": async (id, el) => {
    await api("task.action", {
      group_id: groupId,
      id,
      version: editing.task.version,
      action: el.dataset.choice,
      text: modal.querySelector("[name=task_feedback]")?.value || "",
    });
    close();
  },
  request: (id) => {
    editing = { request: state.requests.find((r) => r.id === id) };
    open(D.requestDetail(state, editing.request), true);
  },
  "answer-option": (id) => {
    modal.querySelector("[name=answer]").value =
      editing.request.options[Number(id)];
  },
  "answer-request": async (id, el) => {
    await api("attention.answer", {
      id,
      allow: el.dataset.choice === "allow",
      text: modal.querySelector("[name=answer]")?.value || "",
    });
    close();
  },
  reply: (id) => {
    const message = current().messages.find((m) => m.id === id);
    draft().reply_to = id;
    draft().target = message.author;
    tab = "chat";
    view = "team";
    close();
    render();
    document.querySelector("#composer-text")?.focus();
  },
  "clear-reply": () => {
    delete draft().reply_to;
    render();
  },
  "jump-message": (id) =>
    document
      .getElementById("message-" + id)
      ?.scrollIntoView({ behavior: "smooth", block: "center" }),
  receipt: (id) =>
    open(
      D.receiptDetail(
        state,
        current(),
        current().deliveries.find((d) => d.id === id),
      ),
      true,
    ),
  "mark-read": async (id) => {
    await api("message.read", { group_id: groupId, message_id: id });
    close();
  },
  "recover-delivery": async (id, el) => {
    await api("message.recover", {
      group_id: groupId,
      id,
      action: el.dataset.choice,
    });
    close();
  },
  member: (id) => open(D.memberDetail(state, current(), id)),
  "session-action": async (id, el) => {
    await api("session.action", {
      group_id: groupId,
      actor_id: id,
      action: el.dataset.choice,
    });
    close();
  },
  "confirm-new-session": (id) =>
    open(
      D.dialog(
        "新建 " + name(state, id) + " 的会话",
        "<p>当前运行会停止。新会话从共享上下文开始，已有群聊、任务与原会话记录会保留。</p>",
        button("close-dialog", "取消") +
          button("session-action", "新建会话", {
            id,
            cls: "primary",
            extra: 'data-choice="new"',
          }),
      ),
    ),
  run: async (id) => {
    const r = await api("run.get", { id });
    open(
      D.dialog(name(state, r.actor_id) + " · 运行记录", runDetail(state, r)),
      true,
    );
    openRunId = id;
  },
  "new-agent": () => {
    editing = { agent: null };
    open(D.agentForm(state, null));
  },
  "new-external": () => {
    editing = { agent: null };
    open(D.agentForm(state, null, "external"));
  },
  "edit-agent": (id) => {
    editing = { agent: state.config.agents.find((a) => a.id === id) };
    open(
      editing.agent.source_id
        ? D.profileForm(state, editing.agent, false)
        : D.agentForm(state, editing.agent),
    );
  },
  "clone-agent": (id) => {
    editing = { source: state.config.agents.find((a) => a.id === id) };
    open(D.profileForm(state, editing.source, true));
  },
  "agent-permissions": (id) => {
    editing = { permissionAgent: state.config.agents.find((a) => a.id === id) };
    open(D.permissionsForm(state, editing.permissionAgent));
  },
  permissions: () => {
    editing = {};
    open(D.permissionsForm(state));
  },
  "check-agent": async (id) =>
    toast((await api("agent.check", { id })).message),
  "edit-context": () => {
    editing = { version: current().context.version };
    open(D.contextForm(current()));
  },
  "add-context": (id) => {
    editing = { version: current().context.version, contextKind: id };
    open(
      D.dialog(
        id === "decision" ? "记录共同决定" : "添加交接记录",
        U.field("内容", U.textarea("content", "", 'rows="5" required')),
        button("close-dialog", "取消") +
          '<button class="btn primary" type="submit">保存记录</button>',
        "context-entry-form",
      ),
    );
  },
  connections: () => {
    const members = current().members.filter(
      (id) => state.config.agents.find((a) => a.id === id)?.kind === "external",
    );
    open(
      D.dialog(
        "连接外部成员",
        members.length
          ? members
              .map(
                (id) =>
                  `<button class="connection-member" data-action="connection" data-id="${id}">${U.avatar(state, id)}<span>${e(name(state, id))}</span>${icon("arrow")}</button>`,
              )
              .join("")
          : "<p>先在“智能体”中创建外部成员，再将它加入当前协作。</p>",
        members.length
          ? ""
          : button("new-external", "创建外部成员", { cls: "primary" }),
      ),
    );
  },
  connection: (id) => connectionFor(id),
  "rotate-connection": (id) => connectionFor(id, true),
  "copy-connection": async (id) => {
    await navigator.clipboard.writeText(
      JSON.stringify(connection[id], null, 2),
    );
    toast("配置已复制");
  },
  "copy-endpoint": async () => {
    await navigator.clipboard.writeText(
      JSON.stringify(
        {
          endpoint: connection.remote_endpoint,
          token: connection.token,
          group_id: connection.group_id,
          actor_id: connection.actor_id,
        },
        null,
        2,
      ),
    );
    toast("接入信息已复制");
  },
  "copy-sdk": async () => {
    await navigator.clipboard.writeText(
      modal.querySelector("#sdk-code").textContent,
    );
    toast("示例已复制");
  },
  "export-sdk": async () => {
    await api("sdk.export");
    toast("已导出 teams_client.py，将它放入你的 Agent 工程即可导入");
  },
  home: () => api("home.open"),
  "pick-folder": async () => {
    const p = await api("folder.pick");
    if (p) modal.querySelector("[name=workspace]").value = p;
  },
};
document.addEventListener("click", async (event) => {
  const el = event.target.closest("[data-action]");
  if (!el || el.disabled) return;
  const action = actions[el.dataset.action];
  if (!action) return;
  try {
    el.disabled = true;
    await action(el.dataset.id, el);
    await refresh();
  } catch (err) {
    toast(err.message);
  } finally {
    if (el.isConnected) el.disabled = false;
  }
});
document.addEventListener("input", (event) => {
  if (event.target.dataset.draft) {
    draft()[event.target.dataset.draft] = event.target.value;
    delete draft().client_id;
  }
  if (event.target.id === "composer-text") resizeComposer();
});
document.addEventListener("click", (event) => {
  const el = event.target.closest("summary")?.parentElement;
  if (el?.dataset.disclosureKey)
    setTimeout(() => {
      if (el.isConnected) disclosures.set(el.dataset.disclosureKey, el.open);
    }, 0);
});
document.addEventListener("change", (event) => {
  const el = event.target;
  if (el.dataset.draft) {
    draft()[el.dataset.draft] = el.value;
    if (el.name === "mode") render();
  }
  if (el.id === "inbox-filter") {
    inboxFilter = el.value;
    render();
  }
  if (el.id === "adapter-kind") {
    const fd = Object.fromEntries(new FormData(el.form));
    let args = [];
    try {
      args = JSON.parse(fd.args || "[]");
    } catch {}
    const value = { ...editing.agent, ...fd, args };
    open(D.agentForm(state, value, el.value, !editing.agent));
    if (!editing.agent)
      modal.querySelector("[name=id]").removeAttribute("readonly");
  }
  if (el.id === "persona-preset") {
    const preset = presets[el.value];
    if (el.value !== "custom") {
      const form = el.form;
      form.elements.name.value = preset.name + " · " + editing.source.name;
      form.elements.role.value = preset.role;
      form.elements.instructions.value = preset.instructions;
    }
  }
});
document.addEventListener("compositionstart", () => {
  composing = true;
});
document.addEventListener("compositionend", () => {
  composing = false;
  if (pendingRender) {
    pendingRender = false;
    render(true);
  }
});
document.addEventListener("keydown", (event) => {
  if (
    event.ctrlKey &&
    !event.isComposing &&
    !composing &&
    event.key === "Enter" &&
    event.target.id === "composer-text"
  ) {
    event.preventDefault();
    event.target.form.requestSubmit();
  }
});
document.addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.target,
    fd = new FormData(form),
    values = Object.fromEntries(fd),
    submitter = form.querySelector("[type=submit]");
  if (submitter?.disabled) return;
  try {
    if (submitter) submitter.disabled = true;
    switch (form.getAttribute("id")) {
      case "message-form": {
        if (!values.text.trim()) return;
        const d = draft();
        const targets = values.text
          .match(/@([a-z][a-z0-9_-]*)/g)
          ?.map((v) => v.slice(1))
          .filter((id) => current().members.includes(id));
        await api("message.send", {
          group_id: groupId,
          text: values.text,
          mode: values.mode,
          reply_to: d.reply_to || "",
          targets: d.reply_to
            ? undefined
            : targets?.length
              ? [...new Set(targets)]
              : [values.target],
          client_id: d.client_id || (d.client_id = crypto.randomUUID()),
        });
        drafts[groupId] = { target: values.target, mode: values.mode };
        render();
        break;
      }
      case "group-form": {
        const data = {
          ...values,
          members: fd.getAll("members"),
          leader: values.leader || fd.getAll("members")[0],
          review: fd.has("review"),
          max_turns: Number(values.max_turns),
        };
        if (!data.workspace) delete data.workspace;
        const value = await api(
          editing.group ? "group.update" : "group.create",
          editing.group ? { ...data, id: editing.group.id } : data,
        );
        groupId = value.id;
        view = "team";
        tab = "chat";
        close();
        break;
      }
      case "task-form":
        await api("task.add", {
          ...values,
          group_id: groupId,
          depends_on: fd.getAll("depends_on"),
          auto_run: fd.has("auto_run"),
        });
        close();
        break;
      case "context-form":
        await api("context.update", {
          group_id: groupId,
          version: editing.version,
          brief: values.brief,
          constraints: values.constraints
            .split("\n")
            .map((s) => s.trim())
            .filter(Boolean),
        });
        close();
        break;
      case "context-entry-form":
        await api("context.update", {
          group_id: groupId,
          version: editing.version,
          [editing.contextKind]: values.content,
        });
        close();
        break;
      case "agent-form": {
        const value = {
          ...editing.agent,
          ...values,
          timeout: Number(values.timeout),
        };
        value.args = JSON.parse(values.args || "[]");
        if (value.kind === "adp")
          value.allow_personas = fd.has("allow_personas");
        await api("agent.save", value);
        close();
        break;
      }
      case "profile-form": {
        const source = editing.source;
        const value = { ...values, timeout: Number(values.timeout) };
        delete value.preset;
        if (source) value.source_id = source.id;
        else
          Object.assign(value, {
            id: editing.agent.id,
            source_id: editing.agent.source_id,
          });
        await api(source ? "agent.clone" : "agent.save", value);
        close();
        toast(source ? "分身已创建，可加入协作空间" : "分身设定已保存");
        break;
      }
      case "permissions-form": {
        const overrides = {};
        for (const [key, value] of fd) {
          if (key.startsWith("permission:")) overrides[key.slice(11)] = value;
        }
        await api(
          "permissions.configure",
          editing.permissionAgent
            ? { overrides }
            : {
                mode: values.mode,
                review: fd.has("review"),
                overrides,
              },
        );
        close();
        toast("权限设置已生效");
        break;
      }
      case "gateway-form":
        await api("gateway.configure", {
          ...values,
          enabled: fd.has("enabled"),
          port: Number(values.port),
        });
        toast("接入设置已保存");
        break;
    }
    await refresh(true);
  } catch (err) {
    toast(err.message);
  } finally {
    if (submitter?.isConnected) submitter.disabled = false;
  }
});
await refresh(true);
async function poll() {
  await refresh();
  const active = state?.runs.some((r) => U.activeStatuses.includes(r.status));
  setTimeout(poll, active ? 500 : 1500);
}
setTimeout(poll, 1500);
setInterval(() => {
  document.querySelectorAll("[data-run-clock]").forEach((el) => {
    const run = state?.runs.find((r) => r.id === el.dataset.runClock);
    if (run) el.textContent = clockValue(run);
  });
}, 1000);
window.addEventListener("resize", resizeComposer);
