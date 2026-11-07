// Run against scripts/v2_ui_fixture.py; never uses the everyday user directory.
const {
  chromium,
} = require("D:/Project/CCU Agent/browser-runtime/node_modules/playwright");
const fs = require("fs");
const assert = require("assert");

(async () => {
  const browser = await chromium.launch({ channel: "msedge", headless: true });
  const { url } = JSON.parse(
    fs.readFileSync(".test-data/v2-ui/server.json", "utf8"),
  );
  const page = await browser.newPage({
    viewport: { width: 1440, height: 920 },
  });
  const errors = [];
  const remoteRequests = [];
  page.on("pageerror", (error) => errors.push(error.message));
  page.on("request", (request) => {
    if (new URL(request.url()).origin !== new URL(url).origin)
      remoteRequests.push(request.url());
  });
  const checks = [];
  const card = (target, name) =>
    target.locator(".agent-card").filter({
      has: target.getByRole("heading", { name, exact: true }),
    });
  try {
    await page.goto(url);
    await page.locator("[data-action=nav-agents]").click();
    for (const name of [
      "Claude Code",
      "DeepSeek Harness",
      "CCU Agent",
      "MATLAB Agent",
    ]) {
      await card(page, name).locator(".avatar.has-image").waitFor();
      assert(
        await card(page, name)
          .locator(".avatar-image")
          .evaluate((image) => image.naturalWidth > 0),
      );
      assert.equal(
        await card(page, name)
          .locator(".avatar-label")
          .evaluate((label) => getComputedStyle(label).visibility),
        "hidden",
      );
    }
    assert.equal(
      await card(page, "腾讯 ADP").locator(".avatar-image").count(),
      0,
    );
    await card(page, "腾讯 ADP")
      .locator(".avatar-label")
      .waitFor({ state: "visible" });
    await page.screenshot({ path: "docs/screenshots/fixes-agent-icons.png" });
    checks.push("four local brand icons and unknown-brand fallback");

    await page.locator("[data-action=new-group]").click();
    await page.locator("#group-form").waitFor();
    for (const [width, height] of [
      [1440, 920],
      [1024, 680],
    ]) {
      await page.setViewportSize({ width, height });
      const rows = await page.locator(".member-option").evaluateAll((options) =>
        options.map((option) => {
          const box = option.getBoundingClientRect();
          const input = option.querySelector("input").getBoundingClientRect();
          const avatar = option
            .querySelector(".avatar")
            .getBoundingClientRect();
          const label = option.lastElementChild.getBoundingClientRect();
          return {
            checkboxWidth: input.width,
            contained:
              input.left >= box.left &&
              avatar.left >= input.right &&
              label.left >= avatar.right &&
              label.right <= box.right,
            noOverflow: option.scrollWidth <= option.clientWidth,
          };
        }),
      );
      assert(rows.length >= 5);
      assert(
        rows.every(
          (row) => row.checkboxWidth <= 18 && row.contained && row.noOverflow,
        ),
        JSON.stringify(rows),
      );
    }
    await page.setViewportSize({ width: 1440, height: 920 });
    await page.screenshot({ path: "docs/screenshots/fixes-member-picker.png" });
    const groupName = "UI 成员选择回归 " + Date.now();
    await page.locator("#group-form [name=name]").fill(groupName);
    await page.locator("#group-form [name=members][value=claude]").check();
    await page.locator("#group-form [name=members][value=deepseek]").check();
    await page.locator("#group-form button[type=submit]").click();
    await page.locator("#dialog").waitFor({ state: "hidden" });
    await page.getByRole("heading", { name: groupName, exact: true }).waitFor();
    assert.equal(await page.locator(".team-panel .member-row").count(), 2);
    checks.push(
      "member picker stays inside cards at 1440/1024 widths and creates the selected team",
    );

    const failed = await browser.newPage({
      viewport: { width: 1440, height: 920 },
    });
    await failed.route("**/assets/agents/claude.svg", (route) =>
      route.fulfill({ status: 404, body: "" }),
    );
    await failed.goto(url);
    await failed.locator("[data-action=nav-agents]").click();
    const fallback = card(failed, "Claude Code");
    await fallback.locator(".avatar-image").waitFor({ state: "attached" });
    await failed.waitForFunction(() => {
      const image = document.querySelector('.avatar-image[src$="claude.svg"]');
      return image && image.complete && image.naturalWidth === 0;
    });
    assert.equal(await fallback.locator(".avatar.has-image").count(), 0);
    await fallback.locator(".avatar-label").waitFor({ state: "visible" });
    assert.equal(
      await fallback
        .locator(".avatar-image")
        .evaluate((image) => getComputedStyle(image).opacity),
      "0",
    );
    await failed.close();
    checks.push("failed image shows initial without broken-image placeholder");
    assert.deepEqual(remoteRequests, []);
    assert.deepEqual(errors, []);
    checks.push("no external asset requests or JavaScript errors");
    const report = { ok: true, checks, errors };
    fs.writeFileSync(
      "docs/evidence/fixes-ui.json",
      JSON.stringify(report, null, 2),
    );
    console.log(JSON.stringify(report));
  } finally {
    await browser.close();
  }
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
