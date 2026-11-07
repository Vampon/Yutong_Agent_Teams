export const escape = (v) =>
  String(v ?? "").replace(
    /[&<>"']/g,
    (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        c
      ],
  );
const paths = {
  layers: "m12 3 9 5-9 5-9-5 9-5Zm-9 9 9 5 9-5M3 16l9 5 9-5",
  chat: "M4 4h16v12H9l-5 4V4Z",
  grid: "M3 3h7v7H3zM14 3h7v7h-7zM3 14h7v7H3zM14 14h7v7h-7z",
  users:
    "M16 21v-3a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v3M17 4a4 4 0 0 1 0 8M22 21v-3a4 4 0 0 0-3-3.87M13 7a4 4 0 1 1-8 0 4 4 0 0 1 8 0Z",
  inbox: "M4 3h16l2 13v5H2v-5L4 3ZM2 16h6l2 3h4l2-3h6",
  plus: "M12 5v14M5 12h14",
  settings: "M4 7h16M4 17h16M8 4v6M16 14v6",
  arrow: "M4 12h15M13 6l6 6-6 6",
  send: "M12 19V5m-6 6 6-6 6 6",
  pause: "M8 4v16M16 4v16",
  play: "m7 4 14 8-14 8V4Z",
  close: "m6 6 12 12M6 18 18 6",
  check: "m5 12 4 4L19 6",
  clock: "M12 7v5l4 2M22 12a10 10 0 1 1-20 0 10 10 0 0 1 20 0Z",
  chevron: "m9 5 7 7-7 7",
  down: "m6 9 6 6 6-6",
  link: "m10 13 4-4M8 16l-1 1a4 4 0 0 1-6-6l5-5a4 4 0 0 1 6 0M16 8l1-1a4 4 0 1 1 6 6l-5 5a4 4 0 0 1-6 0",
  book: "M4 3h16v18H4V3ZM8 7h8M8 11h8M8 15h5",
  activity: "M2 12h4l3-8 6 16 3-8h4",
  reply: "m9 5-7 7 7 7M2 12h11a8 8 0 0 1 8 8",
  code: "m8 6-6 6 6 6m8-12 6 6-6 6m-3-15-2 18",
  copy: "M9 9h12v12H9zM5 15H3V3h12v2",
  more: "M5 12h.01M12 12h.01M19 12h.01",
  alert: "m12 3 10 18H2L12 3Zm0 6v5m0 3v.01",
  stop: "M5 5h14v14H5z",
  refresh: "M3 10a9 9 0 1 1 1 8M3 4v6h6",
  terminal: "m4 5 7 7-7 7M13 19h7",
  folder: "M3 5h6l2 3h10v13H3V5Z",
  search: "M21 21l-5-5M18 10a8 8 0 1 1-16 0 8 8 0 0 1 16 0Z",
  shield: "m12 2 9 4v6c0 5-9 10-9 10S3 17 3 12V6l9-4Z",
  mail: "M2 4h20v16H2V4Zm0 0 10 9L22 4",
};
export const icon = (name, cls = "") =>
  `<svg class="icon ${cls}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.65" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="${paths[name] || paths.chat}"/></svg>`;
export const button = (
  action,
  label,
  { id = "", cls = "", ic = "", extra = "" } = {},
) =>
  `<button type="button" class="btn ${cls}" data-action="${action}" data-id="${escape(id)}" ${extra}>${ic ? icon(ic) : ""}${escape(label)}</button>`;
export const ibutton = (action, title, id = "", ic = action) =>
  `<button type="button" class="icon-btn" data-action="${action}" data-id="${escape(id)}" title="${escape(title)}" aria-label="${escape(title)}">${icon(ic)}</button>`;
export const time = (value, seconds = false) =>
  value
    ? new Date(value).toLocaleTimeString("zh-CN", {
        hour: "2-digit",
        minute: "2-digit",
        ...(seconds ? { second: "2-digit" } : {}),
      })
    : "—";
export const date = (value) =>
  value
    ? new Date(value).toLocaleString("zh-CN", {
        month: "2-digit",
        day: "2-digit",
        hour: "2-digit",
        minute: "2-digit",
      })
    : "—";
export const name = (s, id) =>
  id === "human"
    ? "你"
    : id === "system"
      ? "系统"
      : s.config.agents.find((a) => a.id === id)?.name || id;
const agentIcons = {
  claude: "/assets/agents/claude.svg",
  deepseek: "/assets/agents/deepseek.svg",
  ccu: "/assets/agents/ccu.png",
  matlab: "/assets/agents/matlab.svg",
};
export function installAvatarImages(root = document) {
  // Capture image events: they do not bubble. Keep initials visible until load.
  root.addEventListener(
    "load",
    (event) => {
      const image = event.target;
      if (image.matches?.(".avatar-image") && image.naturalWidth > 0)
        image.parentElement.classList.add("has-image");
    },
    true,
  );
  root.addEventListener(
    "error",
    (event) => {
      const image = event.target;
      if (image.matches?.(".avatar-image"))
        image.parentElement.classList.remove("has-image");
    },
    true,
  );
}
export const avatar = (s, id, size = "") => {
  const a = s.config.agents.find((a) => a.id === id);
  const color = /^#[0-9a-f]{6}$/i.test(a?.color) ? a.color : "#586a89";
  const src = id !== "human" && id !== "system" ? agentIcons[a?.kind] : null;
  return `<span class="avatar ${size}" style="--actor-color:${color}"><span class="avatar-label">${escape(id === "human" ? "你" : (a?.name || id || "?").slice(0, 1))}</span>${src ? `<img class="avatar-image" src="${src}" alt="" draggable="false" />` : ""}</span>`;
};
export const empty = (title, detail = "", ic = "chat", action = "") =>
  `<div class="empty">${icon(ic)}<h3>${escape(title)}</h3>${detail ? `<p>${escape(detail)}</p>` : ""}${action}</div>`;
export const badge = (text, cls = "") =>
  `<span class="badge ${cls}">${escape(text)}</span>`;
export function markdown(text) {
  const blocks = String(text || "").split(/(```[\s\S]*?```)/g);
  return blocks
    .map((part) =>
      part.startsWith("```")
        ? `<pre><code>${escape(part.replace(/^```[^\n]*\n?/, "").replace(/```$/, ""))}</code></pre>`
        : escape(part)
            .split(/\n\s*\n/)
            .map(
              (p) =>
                `<p>${p
                  .replace(/^#{1,4} (.+)$/gm, "<strong>$1</strong>")
                  .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
                  .replace(/`([^`]+)`/g, "<code>$1</code>")
                  .replace(/\n/g, "<br>")}</p>`,
            )
            .join(""),
    )
    .join("");
}
export const activeStatuses = ["starting", "running", "waiting"];
export const sessionNames = {
  stopped: "未启动",
  ready: "就绪",
  busy: "执行中",
  waiting: "等你确认",
  starting: "连接中",
  offline: "离线",
  error: "异常",
};
export const taskNames = {
  todo: "待开始",
  queued: "排队中",
  running: "进行中",
  blocked: "受阻",
  review: "待审核",
  done: "已完成",
  failed: "执行失败",
  interrupted: "已中断",
  cancelled: "已取消",
};
export function receipt(d) {
  if (d.replied_at) return ["已回复", "good"];
  if (d.state === "uncertain") return ["待核对", "warn"];
  if (d.state === "dismissed") return ["已忽略", ""];
  if (d.read_at) return ["已读", "blue"];
  if (d.delivered_at) return ["已送达", ""];
  if (d.budget_wait) return ["等待继续", "warn"];
  if (d.mode === "mail" && d.state === "queued") return ["待领取", ""];
  return [d.state === "offered" ? "投递中" : "待送达", ""];
}
export const field = (label, html, hint = "") =>
  `<label class="field"><span>${escape(label)}</span>${html}${hint ? `<small>${escape(hint)}</small>` : ""}</label>`;
export const input = (key, value = "", extra = "") =>
  `<input name="${key}" value="${escape(value)}" ${extra}>`;
export const textarea = (key, value = "", extra = "") =>
  `<textarea name="${key}" ${extra}>${escape(value)}</textarea>`;
export const options = (values, selected) =>
  values
    .map(
      ([v, label]) =>
        `<option value="${escape(v)}" ${v === selected ? "selected" : ""}>${escape(label)}</option>`,
    )
    .join("");
