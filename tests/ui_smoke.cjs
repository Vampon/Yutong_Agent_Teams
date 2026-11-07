// Run after scripts/v2_ui_fixture.py. All data is isolated UI fixture data.
const {
  chromium,
} = require("D:/Project/CCU Agent/browser-runtime/node_modules/playwright");
const fs = require("fs");
const assert = require("assert");
const screenshotPrefix = process.env.SCREENSHOT_PREFIX || "v2";
(async () => {
  const browser = await chromium.launch({ channel: "msedge", headless: true });
  const page = await browser.newPage({
    viewport: { width: 1440, height: 920 },
  });
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  const { url } = JSON.parse(
    fs.readFileSync(".test-data/v2-ui/server.json", "utf8"),
  );
  try {
    await page.goto(url);
    await page
      .getByRole("heading", { name: "控制策略联合评审", exact: true })
      .waitFor();
    assert.equal(
      await page.getByText("本地工作台", { exact: true }).count(),
      0,
    );
    assert.equal(await page.locator(".eyebrow").count(), 0);
    assert.equal(await page.locator(".brand-mark").evaluate(async (image) => { await image.decode(); return image.naturalWidth > 0; }), true);
    await page.screenshot({ path: `docs/screenshots/${screenshotPrefix}-chat.png` });
    await page.locator("[data-action=tab][data-id=tasks]").click();
    await page.locator(".board").waitFor();
    await page.screenshot({ path: `docs/screenshots/${screenshotPrefix}-tasks.png` });
    await page.locator("[data-action=new-task]").click();
    await page
      .locator("#task-form [name=title]")
      .fill("UI regression " + Date.now());
    await page
      .locator("#task-form [name=description]")
      .fill("由自动界面测试创建的任务");
    await page.locator("#task-form [name=auto_run]").uncheck();
    await page.locator("#task-form button[type=submit]").click();
    await page.locator("#dialog").waitFor({ state: "hidden" });
    await page.locator(".tabs [data-action=tab][data-id=context]").click();
    await page.locator(".context-brief").waitFor();
    await page.locator("[data-action=edit-context]").click();
    await page
      .locator("#context-form [name=brief]")
      .fill("完成低速控制策略的接口与边界条件评审，输出可以复核的结论。");
    await page.locator("#context-form button[type=submit]").click();
    await page.locator("#dialog").waitFor({ state: "hidden" });
    await page.screenshot({ path: `docs/screenshots/${screenshotPrefix}-context.png` });
    await page.locator("[data-action=tab][data-id=chat]").click();
    await page
      .locator("#composer-text")
      .fill('<img src=x onerror="window.TEST_XSS=1"> 界面测试留信');
    await page.locator("[name=mode]").selectOption("mail");
    await page.locator("#message-form button[type=submit]").click();
    await page
      .getByText('<img src=x onerror="window.TEST_XSS=1"> 界面测试留信', {
        exact: true,
      })
      .last()
      .waitFor();
    assert.equal(await page.evaluate(() => window.TEST_XSS), undefined);
    await page.locator(".receipt").first().click();
    await page.locator(".receipt-steps").waitFor();
    await page.locator("#dialog [data-action=close-dialog]").click();
    await page.locator("[data-action=nav-attention]").click();
    await page.screenshot({ path: `docs/screenshots/${screenshotPrefix}-attention.png` });
    if (await page.locator(".attention-card").count()) {
      await page.locator(".attention-card").first().click();
      await page
        .locator("#dialog [name=answer]")
        .fill("界面回归测试：沿用当前项目基线。");
      await page.locator("#dialog [data-action=answer-request]").last().click();
      await page.locator("#dialog").waitFor({ state: "hidden" });
    }
    await page.locator("[data-action=nav-agents]").click();
    await page.locator(".agent-card").first().waitFor();
    await page.screenshot({ path: `docs/screenshots/${screenshotPrefix}-agents.png` });
    await page.locator("[data-action=new-agent]").click();
    await page.locator("#adapter-kind").selectOption("http");
    const agentId = "ui_" + Date.now();
    await page.locator("#agent-form [name=id]").fill(agentId);
    await page.locator("#agent-form [name=name]").fill("UI HTTP Test");
    await page
      .locator("#agent-form [name=url]")
      .fill("http://127.0.0.1:1/agent");
    await page.locator("#agent-form button[type=submit]").click();
    await page.locator("#dialog").waitFor({ state: "hidden" });
    await page
      .getByRole("heading", { name: "UI HTTP Test", exact: true })
      .last()
      .waitFor();
    await page.locator("[data-action=nav-team]").click();
    await page.locator("[data-action=connections]").click();
    await page.locator("#dialog [data-action=connection]").first().click();
    await page.locator("#sdk-code").waitFor();
    assert(
      (await page.locator("#sdk-code").innerText()).includes("from_connection"),
    );
    await page.locator("#dialog [data-action=close-dialog]").click();
    await page.setViewportSize({ width: 1024, height: 680 });
    await page.locator("[data-action=tab][data-id=tasks]").click();
    assert.equal(
      await page.evaluate(
        () => document.documentElement.scrollWidth > innerWidth,
      ),
      false,
    );
    assert.deepEqual(errors, []);
    console.log(
      JSON.stringify({
        ok: true,
        checks: [
          "application logo",
          "removed labels",
          "group chat",
          "task creation",
          "context edit",
          "XSS escaping",
          "receipt detail",
          "human answer",
          "adapter form",
          "external connection",
          "1024 layout",
        ],
        errors,
      }),
    );
  } finally {
    await browser.close();
  }
})().catch((e) => {
  console.error(e);
  process.exitCode = 1;
});
