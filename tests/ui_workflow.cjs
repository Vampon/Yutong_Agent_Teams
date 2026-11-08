const { chromium } = require("D:/Project/CCU Agent/browser-runtime/node_modules/playwright");
const fs = require("fs");
const assert = require("assert");
(async () => {
  const fixture = JSON.parse(fs.readFileSync(".test-data/workflow-ui-server.json", "utf8"));
  const browser = await chromium.launch({ channel: "msedge", headless: true });
  const page = await browser.newPage({ viewport: { width: 1440, height: 920 } });
  const errors = [], checks = [];
  page.on("pageerror", e => errors.push(e.message));
  const api = async (op, data = {}) => {
    const response = await page.request.post(fixture.url.split("/#")[0] + "/api", {
      headers: { Authorization: "Bearer " + fixture.token }, data: { op, data },
    });
    const body = await response.json();
    assert(body.ok, JSON.stringify(body));
    return body.data;
  };
  try {
    await page.goto(fixture.url);
    await page.getByRole("heading", { name: "最终交付验收", exact: true }).waitFor();
    let state = await api("state");
    assert.equal(state.requests.filter(r => r.status === "pending").length, 1);
    assert.equal(state.groups[0].tasks[0].status, "done");
    await page.locator(".final-delivery").waitFor();
    checks.push("internal review completes without a human approval card");
    await page.screenshot({ path: "docs/screenshots/v040-final-pending.png" });
    await page.locator(".final-delivery [data-action=work]").click();
    await page.getByRole("button", { name: "确认最终交付", exact: true }).click();
    await page.locator("#dialog").waitFor({ state: "hidden" });
    await page.waitForFunction(() => document.querySelector(".side-delivery small")?.textContent === "已完成");
    state = await api("state");
    assert.equal(state.requests.filter(r => r.status === "pending").length, 0);
    assert.equal(state.groups[0].works[0].status, "done");
    assert.equal(state.runs.length, 0);
    checks.push("one final confirmation closes the chain without starting a run");
    await page.reload();
    await page.locator(".side-delivery[data-action=work]").click();
    await page.locator('[name="work_feedback"]').fill("补充空输入边界的验证依据");
    await page.getByRole("button", { name: "重新打开交付", exact: true }).click();
    await page.locator("#dialog").waitFor({ state: "hidden" });
    state = await api("state");
    assert.equal(state.groups[0].works[0].status, "active");
    const revisions = state.groups[0].messages.filter(m => m.origin === "work_revision");
    assert.equal(revisions.length, 1);
    assert.equal(revisions[0].mode, "send");
    checks.push("explicit reopening creates exactly one revision message");
    await page.setViewportSize({ width: 1024, height: 680 });
    await page.screenshot({ path: "docs/screenshots/v040-final-revision-1024.png" });
    assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
    checks.push("final delivery state persists on refresh and fits 1024px");
    assert.equal(errors.length, 0);
    const report = { ok: true, checks, errors };
    fs.writeFileSync("docs/evidence/v040-ui-workflow.json", JSON.stringify(report, null, 2));
    console.log(JSON.stringify(report));
  } finally { await browser.close(); }
})().catch(e => { console.error(e); process.exitCode = 1; });
