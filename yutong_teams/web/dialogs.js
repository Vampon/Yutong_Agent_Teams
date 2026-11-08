import {
  escape as e,
  icon,
  button,
  ibutton,
  field,
  input,
  textarea,
  options,
  name,
  avatar,
  markdown,
  date,
  sessionNames,
  taskNames,
  receipt,
  badge,
} from "./ui.js";
import { permissionNames, permissionOptions, presets } from "./personas.js";
export function dialog(title, body, footer = "", form = "") {
  return `${form ? `<form id="${form}">` : ""}<header class="dialog-header"><h2>${e(title)}</h2>${ibutton("close-dialog", "关闭", "", "close")}</header><div class="dialog-body">${body}</div>${footer ? `<footer class="dialog-footer">${footer}</footer>` : ""}${form ? "</form>" : ""}`;
}
const submit = (text) =>
  `<button class="btn primary" type="submit">${text}</button>`;
export function groupForm(s, g) {
  return dialog(
    g ? "协作设置" : "新建协作",
    `${field("名称", input("name", g?.name || "", 'required maxlength="100" placeholder="例如：整车控制策略评审"'))}${g ? "" : field("共同目标", textarea("goal", "", 'rows="3" placeholder="希望共同完成什么？有哪些验收标准？"'))}<div class="field"><span>协作成员</span><div class="member-options">${s.config.agents.map((a) => `<label class="member-option"><input type="checkbox" name="members" value="${a.id}" ${g?.members.includes(a.id) ? "checked" : ""}>${avatar(s, a.id)}<span>${e(a.name)}</span></label>`).join("")}</div></div>${field("队长", `<select name="leader">${options([["", "由第一位选中成员担任"], ...s.config.agents.map((a) => [a.id, a.name])], g?.leader || "")}</select>`)}<label class="check-row"><input type="checkbox" name="review" ${(g ? g.review !== false : s.config.permissions?.review !== false) ? "checked" : ""}>最终交付后由我确认</label><details class="advanced"><summary>工作目录与执行设置</summary>${field("工作目录", `<div class="input-action">${input("workspace", g?.workspace || "", 'placeholder="默认使用用户目录下的 workspace"')}${button("pick-folder", "选择", { ic: "folder" })}</div>`)}${field("每轮协作的运行次数上限", input("max_turns", g?.max_turns || 24, 'type="number" min="2" max="100"'), "达到上限后保留待投递消息，由你决定继续。")}</details>`,
    button("close-dialog", "取消") + submit(g ? "保存" : "创建协作"),
    "group-form",
  );
}
export function taskForm(s, g) {
  return dialog(
    "新建任务",
    `${field("交付名称", input("title", "", 'required maxlength="200" placeholder="例如：完成控制算法边界条件评审"'))}${field("任务说明与验收标准", textarea("description", "", 'rows="4"'))}${field(
      "负责人",
      `<select name="agent_id">${options(
        g.members.map((a) => [a, name(s, a)]),
        g.leader,
      )}</select>`,
    )}${
      g.tasks.length
        ? `<div class="field"><span>前置任务</span><div class="dependency-options">${g.tasks
            .filter((t) => t.status !== "cancelled")
            .map(
              (t) =>
                `<label class="check-row"><input type="checkbox" name="depends_on" value="${t.id}">${e(t.title)}<span class="subtle">${taskNames[t.status]}</span></label>`,
            )
            .join("")}</div></div>`
        : ""
    }<label class="check-row"><input type="checkbox" name="auto_run" checked>前置任务完成后自动交给负责人</label>`,
    button("close-dialog", "取消") + submit("创建任务"),
    "task-form",
  );
}
export function taskDetail(s, g, t) {
  const actions = [];
  if (t.status === "todo") actions.push(["start", "开始执行", "primary"]);
  if (t.status === "review")
    actions.push(
      ["revise", "要求修订", ""],
      ["approve", "通过交付", "primary"],
    );
  if (["blocked", "failed", "interrupted", "cancelled"].includes(t.status))
    actions.push(["retry", "重新交给负责人", "primary"]);
  if (!["done", "cancelled"].includes(t.status))
    actions.unshift(["cancel", "取消任务", "quiet"]);
  return dialog(
    t.title,
    `<div class="detail-meta">${avatar(s, t.agent_id)}<strong>${e(name(s, t.agent_id))}</strong>${badge(taskNames[t.status], t.status === "review" ? "warn" : t.status === "done" ? "good" : "")}</div>${t.description ? `<div class="prose">${markdown(t.description)}</div>` : ""}${
      t.depends_on.length
        ? `<div class="detail-section"><h3>前置任务</h3>${t.depends_on
            .map((id) => {
              const x = g.tasks.find((v) => v.id === id);
              return `<div class="dependency-line">${icon(x?.status === "done" ? "check" : "clock")}${e(x?.title || id)}<span>${taskNames[x?.status] || ""}</span></div>`;
            })
            .join("")}</div>`
        : ""
    }${t.error ? `<div class="notice warning">${icon("alert")}<span>${e(t.error)}</span></div>` : ""}${t.result ? `<div class="detail-section"><h3>交付内容</h3><div class="prose result-body">${markdown(t.result)}</div></div>` : ""}${t.feedback ? `<div class="detail-section"><h3>补充要求</h3><p>${e(t.feedback)}</p></div>` : ""}${t.status !== "done" ? field("补充意见", textarea("task_feedback", "", 'rows="3" placeholder="修订要求、重试时需要补充的信息…"')) : ""}`,
    actions
      .map(([action, label, cls]) =>
        button("task-action", label, {
          id: t.id,
          cls,
          extra: `data-choice="${action}"`,
        }),
      )
      .join(""),
  );
}
export function requestDetail(s, r) {
  return dialog(
    r.title,
    `<div class="detail-meta">${avatar(s, r.actor_id)}<strong>${e(name(s, r.actor_id))}</strong><span class="subtle">${date(r.created)}</span></div><div class="prose">${markdown(r.detail)}</div>${r.kind === "tool" ? `<h3>工具参数</h3><pre class="code-block">${e(JSON.stringify(r.arguments, null, 2))}</pre>` : ""}${r.kind === "question" && r.options?.length ? `<div class="answer-options">${r.options.map((v, i) => button("answer-option", v, { id: String(i) })).join("")}</div>` : ""}${field(r.kind === "tool" ? "备注（可选）" : "你的答复或审核意见", textarea("answer", "", 'rows="3" placeholder="填写你的意见…"'))}`,
    r.kind === "question"
      ? button("answer-request", "提交答复", {
          id: r.id,
          cls: "primary",
          extra: 'data-choice="allow"',
        })
      : button("answer-request", r.kind === "tool" ? "拒绝执行" : "要求修订", {
          id: r.id,
          extra: 'data-choice="deny"',
        }) +
          button(
            "answer-request",
            r.kind === "tool" ? "允许本次执行" : r.kind === "final_review" ? "确认最终交付" : "通过交付",
            { id: r.id, cls: "primary", extra: 'data-choice="allow"' },
          ) +
          (r.kind === "tool"
            ? button("agent-permissions", "工具权限", {
                id: r.actor_id,
                cls: "quiet",
                ic: "shield",
              })
            : ""),
  );
}
export function workDetail(work) {
  const label = work.status === "done" ? "已完成" : work.status === "review" ? "待你确认" : "修订中";
  return dialog(
    work.title,
    `<div class="detail-meta">${badge(label, work.status === "done" ? "good" : "warn")}${work.accepted ? `<span class="subtle">${date(work.accepted)}</span>` : ""}</div><div class="prose result-body">${markdown(work.result)}</div>${work.feedback ? `<div class="detail-section"><h3>修订要求</h3><p>${e(work.feedback)}</p></div>` : ""}${work.status === "done" ? field("需要修订时填写要求", textarea("work_feedback", "", 'rows="3" placeholder="说明需要调整的内容…"')) : ""}`,
    work.status === "done" ? button("reopen-work", "重新打开交付", { id: work.id }) : "",
  );
}
export function memberDetail(s, g, aid) {
  const a = s.config.agents.find((x) => x.id === aid),
    session = g.sessions.find((x) => x.actor_id === aid),
    spec = s.catalog.find((x) => x.kind === a.kind);
  const runs = s.runs
    .filter((r) => r.group_id === g.id && r.actor_id === aid)
    .slice(-5)
    .reverse();
  const external = a.kind === "external";
  return dialog(
    a.name,
    `<div class="member-hero">${avatar(s, aid, "large")}<div><h3>${e(a.name)}</h3><p>${e(a.role || "")}</p></div>${badge(sessionNames[session.state] || session.state, session.state === "error" ? "warn" : "")}</div><p class="muted">${e(spec?.description || "")}</p>${session.error ? `<div class="notice warning">${icon("alert")}<span>${e(session.error)}</span></div>` : ""}${external ? button("connection", "获取接入配置", { id: aid, cls: "primary", ic: "link" }) : `<div class="session-actions">${button("session-action", "允许继续", { id: aid, ic: "play", extra: 'data-choice="start"' })}${button("session-action", "停止运行", { id: aid, ic: "stop", extra: 'data-choice="stop"' })}${button("confirm-new-session", "新建会话", { id: aid, ic: "refresh" })}</div>`}<div class="detail-section"><h3>最近运行</h3>${runs.length ? runs.map((r) => `<button class="run-row" data-action="run" data-id="${r.id}">${icon("terminal")}<span>${{ completed: "执行结束", failed: "执行失败", cancelled: "已停止", interrupted: "已中断", running: "执行中", starting: "启动中", waiting: "等待确认" }[r.status] || r.status}</span><time>${date(r.created)}</time>${icon("chevron")}</button>`).join("") : '<p class="muted">暂无运行记录。</p>'}</div><details class="advanced"><summary>会话详情</summary><dl class="detail-list"><dt>会话标识</dt><dd>${e(session.provider_id || "尚未建立")}</dd>${session.model ? `<dt>当前模型</dt><dd>${e(session.model_provider)} / ${e(session.model)}</dd>` : ""}${session.model_source ? `<dt>模型配置来源</dt><dd>${e(session.model_source)}</dd>` : ""}<dt>已完成轮次</dt><dd>${session.turns}</dd><dt>最近活动</dt><dd>${date(session.last_seen)}</dd></dl></details>`,
  );
}
export function receiptDetail(s, g, d) {
  const m = g.messages.find((m) => m.id === d.message_id);
  const [label, cls] = receipt(d);
  return dialog(
    "消息回执",
    `<div class="detail-meta">${avatar(s, d.recipient)}<strong>${e(name(s, d.recipient))}</strong>${badge(label, cls)}</div>${m ? `<div class="prose receipt-message">${markdown(m.text.slice(0, 10000))}</div>` : ""}<div class="receipt-steps">${[
      ["已送达", d.delivered_at],
      ["已读", d.read_at],
      ["已回复", d.replied_at],
    ]
      .map(
        ([stage, value]) =>
          `<div class="receipt-step ${value ? "complete" : ""}"><span>${icon(value ? "check" : "clock")}</span><strong>${stage}</strong><time>${value ? date(value) : "未确认"}</time></div>`,
      )
      .join(
        "",
      )}</div>${d.error ? `<div class="notice warning">${icon("alert")}<span>${e(d.error)}</span></div>` : ""}${d.state === "uncertain" ? '<p class="muted">接收端可能已经执行过。请核对实际结果，再决定是否重发。</p>' : ""}`,
    `${d.recipient === "human" && !d.read_at ? button("mark-read", "确认已读", { id: d.message_id, cls: "primary" }) : ""}${["uncertain", "failed", "cancelled"].includes(d.state) ? button("recover-delivery", "忽略这次投递", { id: d.id, extra: 'data-choice="dismiss"' }) + button("recover-delivery", "确认重发", { id: d.id, cls: "primary", extra: 'data-choice="retry"' }) : ""}${m && m.author !== "human" ? button("reply", "回复消息", { id: m.id, ic: "reply" }) : ""}`,
  );
}
export function agentForm(s, a, kind, fresh = !a) {
  kind = kind || a?.kind || "external";
  const spec = s.catalog.find((x) => x.kind === kind);
  const current = a || {};
  return dialog(
    fresh ? "接入智能体" : "智能体设置",
    `${field(
      "接入方式",
      `<select name="kind" id="adapter-kind">${options(
        s.catalog.map((x) => [x.kind, x.title]),
        kind,
      )}</select>`,
    )}
    <p class="adapter-description">${e(spec.description)}</p>
    <div class="form-row">${field("名称", input("name", current.name || "", 'required maxlength="100"'))}${field("成员 ID", input("id", current.id || "", 'required pattern="[a-z][a-z0-9_-]{0,39}" ' + (!fresh ? "readonly" : 'placeholder="例如：analysis_bot"')))}</div>
    ${field("职责", input("role", current.role || "", 'maxlength="400" placeholder="便于其他成员了解它擅长什么"'))}
    ${spec.fields.map((f) => field(f.label, f.type === "json" ? textarea(f.key, JSON.stringify(current[f.key] || []), 'rows="2"') : input(f.key, f.type === "password" ? "" : current[f.key] || "", `${f.required ? "required " : ""}type="${f.type === "password" ? "password" : "text"}" autocomplete="off"`), f.hint)).join("")}
    ${kind === "adp" ? `<label class="check-row"><input type="checkbox" name="allow_personas" ${current.allow_personas ? "checked" : ""}>应用支持 SystemRole 角色覆盖，允许创建分身</label><p class="field-hint">仅在确认已发布应用支持角色覆盖时开启；分身共用应用能力，分别使用独立会话。</p>` : ""}
    <details class="advanced"><summary>工作说明与执行设置</summary>
    ${field("专属工作说明", textarea("instructions", current.instructions || "", 'rows="5" maxlength="16000"'), "每次执行都会带入，不会修改原运行器的配置。")}
    ${field("单次最长执行时间（秒）", input("timeout", current.timeout || 600, 'type="number" min="10" max="7200"'))}
    ${field("成员专用工作目录（可选）", input("cwd", current.cwd || ""), "留空使用协作的工作目录。")}</details>
    ${!fresh && spec.capabilities.approvals ? button("agent-permissions", "工具权限", { id: a.id, ic: "shield" }) : ""}`,
    button("close-dialog", "取消") + submit("保存成员"),
    "agent-form",
  );
}
export function profileForm(s, a, fresh) {
  const source = s.config.agents.find((x) => x.id === (a.source_id || a.id));
  const cap = s.catalog.find((x) => x.kind === a.kind)?.capabilities || {};
  return dialog(
    fresh ? "创建分身" : "分身设置",
    `<div class="profile-source">${avatar(s, source.id)}<div><strong>${e(source.name)}</strong><span>共用接入配置，独立身份与会话</span></div></div>
    ${
      fresh
        ? field(
            "初始设定",
            `<select id="persona-preset" name="preset">${options(
              Object.entries(presets).map(([key, value]) => [key, value.name]),
              "custom",
            )}</select>`,
          )
        : ""
    }
    ${field("分身名称", input("name", fresh ? a.name + " 分身" : a.name, 'required maxlength="100"'))}
    ${field("职责", input("role", a.role || "", 'required maxlength="400" placeholder="例如：需求评审、代码开发"'))}
    ${field("专属工作说明", textarea("instructions", a.instructions || "", 'rows="6" maxlength="16000" placeholder="指定工作方式、交付格式，以及与其他成员的分工…"'), "每次执行都会带入；修改后从下一次执行生效，已有会话继续保留。")}
    ${cap.approvals ? field("工具执行确认", `<select name="permission_mode">${options(permissionOptions(source.name), fresh ? "inherit" : a.permission_mode || "inherit")}</select>`) : ""}
    <details class="advanced"><summary>工作目录与执行设置</summary>
    ${field("专用工作目录（可选）", input("cwd", fresh ? "" : a.cwd || ""), "留空共用协作目录；会话独立不会隔离文件，并行修改同一工程时可分别指定工作目录。")}
    ${field("单次最长执行时间（秒）", input("timeout", a.timeout || 600, 'type="number" min="10" max="7200"'))}</details>`,
    button("close-dialog", "取消") + submit(fresh ? "创建分身" : "保存设定"),
    "profile-form",
  );
}

export function permissionsForm(s, agent) {
  const policy = s.config.permissions || {};
  const members = agent
    ? [agent]
    : s.config.agents.filter(
        (a) => s.catalog.find((x) => x.kind === a.kind)?.capabilities.approvals,
      );
  return dialog(
    agent ? agent.name + " · 工具权限" : "工具权限与交付审核",
    `${!agent ? field("默认工具确认策略", `<select name="mode">${options(Object.entries(permissionNames), policy.mode || "ask")}</select>`) : ""}
    <p class="permission-explanation">“自动允许”会放行运行器提交的工具确认请求，“自动拒绝”会拒绝这些请求。原运行器的允许/禁止规则仍生效；这里不限制文件访问范围。</p>
    <div class="permission-members">${members.map((a) => `<label class="permission-member">${avatar(s, a.id)}<span><strong>${e(a.name)}</strong><small>当前：${e(permissionNames[a.permission_effective] || "由我确认")}</small></span><select name="permission:${e(a.id)}" aria-label="${e(a.name)}的工具权限">${options(permissionOptions(a.source_name), a.permission_mode || (a.auto_tools ? "auto" : "inherit"))}</select></label>`).join("")}</div>
    ${!agent ? `<div class="permission-review"><label class="check-row"><input type="checkbox" name="review" ${policy.review !== false ? "checked" : ""}>新建协作默认由我确认最终交付</label><p class="field-hint">已有协作在“协作设置”中单独调整。业务提问始终保留给你答复。</p></div>` : ""}
    <p class="field-hint">保存后立即生效，也会处理这些成员正在等待的工具确认。</p>`,
    button("close-dialog", "取消") + submit("保存权限"),
    "permissions-form",
  );
}
export function contextForm(g) {
  return dialog(
    "编辑共享目标",
    `${field("协作目标", textarea("brief", g.context.brief, 'rows="5"'))}${field("共同约束", textarea("constraints", g.context.constraints.join("\n"), 'rows="4"'), "每行一条。成员会在执行前读取这些要求。")}`,
    button("close-dialog", "取消") + submit("保存上下文"),
    "context-form",
  );
}
export function connectionDetail(s, g, c) {
  const snippet = `from teams_client import AgentClient\n\nclient = AgentClient.from_connection(${JSON.stringify(c.connection_file)})\nclient.connect(client="My agent", session_id="your-session-id")\nfor item in client.claim():\n    message = item["message"]\n    client.delivered(message["id"])\n    client.read(message["id"])\n    # 调用你的 Agent，保留原生会话\n    client.reply(message["id"], "这里填写实际结果")`;
  return dialog(
    "连接 " + name(s, c.actor_id),
    `<p class="muted">这个连接绑定当前协作中的 ${e(name(s, c.actor_id))} 身份。把配置交给对应的 Agent 运行器。</p><section class="connection-section"><div class="section-heading"><h3>本机 MCP</h3>${button("copy-connection", "复制配置", { id: "mcp_config", ic: "copy", cls: "small" })}</div><pre class="code-block">${e(JSON.stringify(c.mcp_config, null, 2))}</pre></section><section class="connection-section"><div class="section-heading"><h3>Python SDK</h3>${button("export-sdk", "导出 SDK", { ic: "code", cls: "small" })}${button("copy-sdk", "复制示例", { ic: "copy", cls: "small" })}</div><pre class="code-block" id="sdk-code">${e(snippet)}</pre></section><section class="connection-section"><div class="section-heading"><h3>跨电脑 MCP / HTTP</h3></div>${c.remote_mcp && s.config.gateway?.enabled ? `<p class="muted">配置含此成员的接入凭据。</p><pre class="code-block">${e(JSON.stringify(c.remote_mcp, null, 2))}</pre><div class="button-row">${button("copy-connection", "复制远端 MCP 配置", { id: "remote_mcp", ic: "copy" })}${button("copy-endpoint", "复制 HTTP 接入信息", { ic: "copy" })}</div>` : '<p class="muted">在设置中启用跨电脑接入服务，再生成远端配置。</p>'}</section><details class="advanced"><summary>管理接入凭据</summary><p class="muted">轮换会立即使原连接失效，需要更新对应 Agent 的配置。</p>${button("rotate-connection", "轮换此成员凭据", { id: c.actor_id })}</details>`,
  );
}
