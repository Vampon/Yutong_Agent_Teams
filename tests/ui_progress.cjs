const { chromium } = require("D:/Project/CCU Agent/browser-runtime/node_modules/playwright");
const fs = require("fs"), assert = require("assert");
(async () => {
  const { url } = JSON.parse(fs.readFileSync(".test-data/progress-ui-server.json", "utf8"));
  const browser = await chromium.launch({ channel: "msedge", headless: true });
  const page = await browser.newPage({ viewport: { width: 1440, height: 920 } });
  const errors = [], checks = [];
  page.on("pageerror", e => errors.push(e.message));
  try {
    await page.goto(url);
    const composer = page.locator("#composer-text");
    await composer.waitFor();
    assert.equal(await page.locator("#message-submit").isDisabled(), true);
    await composer.fill("下一步计划\n".repeat(20));
    const tall = await composer.evaluate(el => ({ height: el.clientHeight, resize: getComputedStyle(el).resize, shadow: getComputedStyle(el).boxShadow, outline: getComputedStyle(el).outlineStyle }));
    assert(tall.height >= 170 && tall.height <= 190);
    assert.equal(tall.resize, "none");
    assert.equal(tall.shadow, "none");
    assert.equal(tall.outline, "none");
    await composer.fill("请开始协作检查");
    assert((await composer.boundingBox()).height < 80);
    await page.locator('[name=target]').selectOption("@all");
    await page.locator("#message-submit").click();
    await page.waitForFunction(() => document.querySelectorAll(".run-card.is-live").length === 2);
    await page.locator(".run-card .trace-text").first().waitFor();
    await composer.fill("这段草稿要保持，不能因过程刷新而丢失。");
    await composer.evaluate(el => { el.setSelectionRange(3, 9); window.progressComposer = el; });
    const initial = await page.locator(".run-card .trace-text").last().textContent();
    await page.waitForFunction(previous => [...document.querySelectorAll(".run-card .trace-text")].some(el => el.textContent !== previous && el.textContent.includes("检查点")), initial);
    assert.equal(await composer.inputValue(), "这段草稿要保持，不能因过程刷新而丢失。");
    assert(await composer.evaluate(el => el === window.progressComposer));
    assert.deepEqual(await composer.evaluate(el => [el.selectionStart, el.selectionEnd]), [3, 9]);
    checks.push("auto-growing composer, no blue focus ring or resize handle; draft DOM and selection survive streaming");

    const conversation = page.locator("#conversation");
    await conversation.evaluate(el => { el.scrollTop = 0; });
    await page.waitForTimeout(800);
    assert.equal(await conversation.evaluate(el => el.scrollTop), 0);
    checks.push("history reading position is retained during live updates");
    await conversation.evaluate(el => { el.scrollTop = el.scrollHeight; });
    await page.locator(".run-card .trace-tool").first().locator("summary").click();
    await page.waitForTimeout(700);
    assert.equal(await page.locator(".run-card .trace-tool").first().getAttribute("open"), "");
    await page.screenshot({ path: "docs/screenshots/v031-live-output.png" });
    await page.locator(".run-card [data-action=run]").first().click();
    await page.locator(".run-detail").waitFor();
    const before = await page.locator(".run-detail .trace-text").last().textContent();
    await page.waitForFunction(value => document.querySelector(".run-detail")?.textContent.includes("等待确认") || [...document.querySelectorAll(".run-detail .trace-text")].some(el => el.textContent !== value && el.textContent.includes("检查点")), before);
    await page.screenshot({ path: "docs/screenshots/v031-process-detail.png" });
    await page.locator("#dialog [data-action=close-dialog]").click();
    await page.waitForFunction(() => document.querySelectorAll(".run-waiting").length === 2);
    for (let i = 0; i < 2; i++) {
      await page.locator(".run-waiting [data-action=request]").first().click();
      await page.locator('#dialog [data-action=answer-request][data-choice=deny]').click();
    }
    await page.waitForFunction(() => !document.querySelector(".run-card.is-live"));
    assert.equal(await page.locator(".run-card[open]").count(), 0);
    checks.push("two live members expose text, tool input/result and approval state; detail stays live and completed runs collapse");

    const times = await page.locator(".message-meta time").allTextContents();
    assert(times.every(t => /\d{1,2}:\d{2}:\d{2}/.test(t)));
    const order = await page.locator("#conversation").evaluate(el => [...el.children].map(x => x.className));
    assert(order.indexOf("delegation") >= 0);
    await page.locator(".delegation summary").click();
    assert((await page.locator(".delegation-body").textContent()).includes("交叉检查"));
    checks.push("second-level timestamps, distinct expandable task delegation and stable causal message/run order");
    await page.setViewportSize({ width: 1024, height: 680 });
    await conversation.evaluate(el => { el.scrollTop = el.scrollHeight; });
    await page.screenshot({ path: "docs/screenshots/v031-composer-1024.png" });
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false);
    assert.deepEqual(errors, []);
    const report = { ok: true, checks, errors };
    fs.writeFileSync("docs/evidence/v031-ui-progress.json", JSON.stringify(report, null, 2));
    console.log(JSON.stringify(report));
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exit(1); });
