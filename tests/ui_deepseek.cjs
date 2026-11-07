const { chromium } = require("D:/Project/CCU Agent/browser-runtime/node_modules/playwright");
const fs = require("fs");
const assert = require("assert");
(async () => {
  const browser = await chromium.launch({ channel: "msedge", headless: true });
  const page = await browser.newPage({ viewport: { width: 1440, height: 920 } });
  const errors = [];
  page.on("pageerror", (error) => errors.push(error.message));
  const { url } = JSON.parse(fs.readFileSync(".test-data/v2-ui/server.json", "utf8"));
  try {
    await page.goto(url);
    await page.locator('[data-action="nav-agents"]').click();
    await page.locator('[data-action="edit-agent"][data-id="deepseek"]').click();
    const dialog = page.locator("#dialog");
    await dialog.locator('[name="model_provider"]').fill("huoshan");
    await dialog.locator('[name="model"]').fill("deepseek-v4-1-flash-260910");
    assert.equal(await dialog.locator('[name="dsh_config_path"]').inputValue(), "");
    assert.equal(await dialog.locator('[name="secret"]').inputValue(), "");
    await dialog.getByRole("button", { name: "保存成员", exact: true }).click();
    await page.waitForFunction(() => !document.querySelector("#dialog").open);
    await page.reload();
    await page.locator('[data-action="nav-agents"]').click();
    await page.locator('[data-action="edit-agent"][data-id="deepseek"]').click();
    assert.equal(await dialog.locator('[name="model_provider"]').inputValue(), "huoshan");
    assert.equal(await dialog.locator('[name="model"]').inputValue(), "deepseek-v4-1-flash-260910");
    await page.screenshot({ path: "docs/screenshots/v032-harness-models.png" });
    await dialog.locator('[data-action="close-dialog"]').first().click();
    await page.locator('[data-action="check-agent"][data-id="deepseek"]').click();
    await page.waitForFunction(() => document.querySelector("#toast").textContent.includes("huoshan / deepseek-v4-1-flash-260910"));
    assert.equal(errors.length, 0);
    const report = { ok: true, checks: ["model source and route fields persist after save/reload", "configured route is visible in check result without credentials"], errors };
    fs.writeFileSync("docs/evidence/v032-ui-models.json", JSON.stringify(report, null, 2));
    console.log(JSON.stringify(report));
  } finally { await browser.close(); }
})().catch((error) => { console.error(error); process.exitCode = 1; });
