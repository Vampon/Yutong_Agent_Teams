import { escape as e, icon, button, avatar, empty, badge } from "../ui.js";
import { permissionNames, canClone } from "../personas.js";
export function agents(s) {
  return `<div class="page-panel agents-page"><div class="panel-toolbar"><div><h2>智能体</h2><p>接入现有运行器，或让外部系统通过 MCP / HTTP 加入协作。</p></div>${button("new-agent", "接入智能体", { ic: "plus", cls: "primary" })}</div><div class="agents-grid">${s.config.agents
    .map((a) => {
      const spec = s.catalog.find((x) => x.kind === a.kind);
      const cap = spec?.capabilities || {};
      return `<article class="agent-card" data-agent="${e(a.id)}"><header>${avatar(s, a.id, "large")}<div><h3>${e(a.name)}</h3>${a.source_id ? `<span>基于 ${e(a.source_name)}</span>` : (spec?.title || a.kind) !== a.name ? `<span>${e(spec?.title || a.kind)}</span>` : ""}</div>${button("edit-agent", "设置", { id: a.id, cls: "quiet small", ic: "settings" })}</header><p title="${e(a.role || "")}">${e(a.role || spec?.description || "")}</p><div class="capabilities">${badge(cap.tools ? "协作工具" : "文本接口", cap.tools ? "blue" : "")}${badge(cap.session === "external" ? "外部会话" : cap.session === "none" ? "单次执行" : cap.session === "provider" || cap.session === "provider_declared" ? "平台会话" : "持续会话")}${cap.approvals ? button("agent-permissions", permissionNames[a.permission_effective] || "由我确认", { id: a.id, cls: "permission-badge", ic: "shield", extra: 'title="设置工具权限"' }) : ""}</div><footer><span>${s.groups.filter((g) => g.members.includes(a.id)).length} 个协作</span><div class="agent-actions">${button("check-agent", "检查配置", { id: a.id, cls: "quiet small" })}${canClone(a, spec) ? button("clone-agent", "创建分身", { id: a.id, cls: "quiet small", ic: "plus" }) : ""}</div></footer></article>`;
    })
    .join(
      "",
    )}</div><section class="integration-strip">${icon("link")}<div><h3>接入你自己的 Agent</h3><p>支持 MCP 的系统可直接获得协作工具；自研系统可使用 HTTP 或 Python SDK。身份、会话和消息回执由统一接口管理。</p></div>${button("new-external", "创建外部成员", { ic: "plus" })}</section></div>`;
}
export function settings(s) {
  const gateway = s.config.gateway || {};
  return `<div class="page-panel settings-page"><div class="panel-toolbar"><div><h2>设置</h2></div></div>${permissionSettings(s)}<section class="settings-section"><div><h3>用户数据</h3><p>配置、会话、协作记录和接入凭据保存在你的用户目录。</p><code>${e(s.home)}</code></div>${button("home", "打开目录", { ic: "folder" })}</section><section class="settings-section gateway-section"><div><h3>跨电脑接入</h3><p>开启后，内网其他电脑上的 Agent 可使用成员专属凭据接入。</p></div><form id="gateway-form"><label class="check-row"><input type="checkbox" name="enabled" ${gateway.enabled ? "checked" : ""}>启用 Agent 接入服务</label><div class="form-row"><label class="field"><span>监听地址</span><input name="host" value="${e(gateway.host || "0.0.0.0")}"></label><label class="field"><span>端口</span><input name="port" type="number" min="1024" max="65535" value="${gateway.port || 43821}"></label></div><label class="field"><span>其他电脑使用的地址</span><input name="public_url" value="${e(gateway.public_url || "")}" placeholder="http://这台电脑的内网 IP:43821"><small>跨不可信网络时，通过 HTTPS 反向代理提供此地址。桌面管理界面始终仅在本机开放。</small></label><button class="btn primary" type="submit">保存接入设置</button></form></section><section class="settings-section"><div><h3>接入能力</h3><p>原生运行器可在执行中调用协作工具；文本接口由工作台转交输入和结果。外部系统需实现 MCP、ACP 或 HTTP 协议之一。</p></div></section></div>`;
}

export function permissionSettings(s) {
  const policy = s.config.permissions || {};
  return `<section class="settings-section"><div><h3>工具权限与交付审核</h3><p>工具确认：${e(permissionNames[policy.mode] || "由我确认")} · 新协作交付${policy.review === false ? "自动完成" : "由你审核"}</p><p>可为每个成员单独设置，运行过程中也可调整。</p></div>${button("permissions", "配置权限", { ic: "shield" })}</section>`;
}
