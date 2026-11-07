// UI integration against an isolated, non-running v2_ui_fixture.py instance.
const {
  chromium,
} = require("D:/Project/CCU Agent/browser-runtime/node_modules/playwright");
const fs = require("fs");
const assert = require("assert");

(async () => {
  const { url } = JSON.parse(
    fs.readFileSync(".test-data/v2-ui/server.json", "utf8"),
  );
  const browser = await chromium.launch({ channel: "msedge", headless: true });
  const page = await browser.newPage({
    viewport: { width: 1440, height: 920 },
  });
  const errors = [],
    remote = [],
    checks = [];
  page.on("pageerror", (e) => errors.push(e.message));
  page.on("request", (r) => {
    if (new URL(r.url()).origin !== new URL(url).origin) remote.push(r.url());
  });
  const dialog = page.locator("#dialog");
  const cards = page.locator(".agent-card");
  const card = (name) =>
    cards.filter({ has: page.getByRole("heading", { name, exact: true }) });
  const save = async (id) => {
    await page.locator(`#${id} button[type=submit]`).click();
    await dialog.waitFor({ state: "hidden" });
  };
  try {
    await page.goto(url);
    await page.locator("[data-action=nav-agents]").click();
    assert.equal(
      await card("腾讯 ADP").locator("[data-action=clone-agent]").count(),
      0,
    );
    assert.equal(
      await card("方案评审 Agent").locator("[data-action=clone-agent]").count(),
      0,
    );
    for (const [preset, title, text] of [
      ["review", "需求评审 · Claude Code", "需求完整性"],
      ["develop", "代码开发 · Claude Code", "方案实现"],
    ]) {
      await card("Claude Code").locator("[data-action=clone-agent]").click();
      await page.locator("#persona-preset").selectOption(preset);
      assert.equal(
        await page.locator("#profile-form [name=name]").inputValue(),
        title,
      );
      assert(
        (await page.locator("#profile-form [name=role]").inputValue()).includes(
          text,
        ),
      );
      assert(
        (await page.locator("#profile-form [name=instructions]").inputValue())
          .length > 60,
      );
      assert.equal(
        await page.locator("#profile-form [name=command]").count(),
        0,
      );
      if (preset === "review") {
        await page
          .locator("#profile-form [name=permission_mode]")
          .selectOption("deny");
        await page.screenshot({
          path: "docs/screenshots/v030-create-persona.png",
        });
      }
      await save("profile-form");
      await card(title).waitFor();
    }
    checks.push(
      "two Claude personas created through editable presets, one shared runtime",
    );
    await card("需求评审 · Claude Code")
      .locator("[data-action=edit-agent]")
      .click();
    const original = await page
      .locator("#profile-form [name=instructions]")
      .inputValue();
    await page
      .locator("#profile-form [name=instructions]")
      .fill(original + "\n评审输出附需求编号。");
    await save("profile-form");
    await page.reload();
    await page.locator("[data-action=nav-agents]").click();
    await card("需求评审 · Claude Code")
      .locator("[data-action=edit-agent]")
      .click();
    assert(
      (
        await page.locator("#profile-form [name=instructions]").inputValue()
      ).includes("评审输出附需求编号"),
    );
    await dialog.locator("[data-action=close-dialog]").first().click();
    checks.push("persona instructions persist across reload");

    await page.locator("[data-action=nav-settings]").click();
    await page.locator("[data-action=permissions]").click();
    const avatarWidths = await page.locator(".permission-member > .avatar").evaluateAll(nodes => nodes.map(x => x.getBoundingClientRect().width));
    assert(avatarWidths.every(width => width <= 40), "permission avatar stretched");
    await page.locator("#permissions-form [name=mode]").selectOption("auto");
    await page.locator("#permissions-form [name=review]").uncheck();
    await page.screenshot({ path: "docs/screenshots/v030-permissions.png" });
    await save("permissions-form");
    await page.locator("[data-action=nav-agents]").click();
    assert.equal(
      (
        await card("Claude Code").locator(".permission-badge").textContent()
      ).trim(),
      "自动允许",
    );
    assert.equal(
      (
        await card("代码开发 · Claude Code")
          .locator(".permission-badge")
          .textContent()
      ).trim(),
      "自动允许",
    );
    assert.equal(
      (
        await card("需求评审 · Claude Code")
          .locator(".permission-badge")
          .textContent()
      ).trim(),
      "自动拒绝",
    );
    await card("Claude Code").locator(".permission-badge").click();
    await page
      .locator('#permissions-form [name="permission:claude"]')
      .selectOption("ask");
    await save("permissions-form");
    assert.equal(
      (
        await card("代码开发 · Claude Code")
          .locator(".permission-badge")
          .textContent()
      ).trim(),
      "由我确认",
    );
    checks.push(
      "global policy, source inheritance and persona override apply independently",
    );

    const reviewerId =
      await card("需求评审 · Claude Code").getAttribute("data-agent");
    const developerId =
      await card("代码开发 · Claude Code").getAttribute("data-agent");
    await page.locator("[data-action=new-group]").click();
    const form = page.locator("#group-form");
    await form.locator("[name=name]").fill("双 Claude 协作");
    await form.locator(`[name=members][value="${reviewerId}"]`).check();
    await form.locator(`[name=members][value="${developerId}"]`).check();
    await form.locator("[name=leader]").selectOption(reviewerId);
    assert.equal(await form.locator("[name=review]").isChecked(), false);
    await save("group-form");
    await page
      .getByRole("heading", { name: "双 Claude 协作", exact: true })
      .waitFor();
    checks.push(
      "both personas join the same group; new-group review default follows settings",
    );

    await page.locator("[data-action=nav-agents]").click();
    for (const [width, height] of [
      [1440, 920],
      [1024, 760],
    ]) {
      await page.setViewportSize({ width, height });
      const geometry = await cards.evaluateAll((nodes) =>
        nodes.map((node) => {
          const r = node.getBoundingClientRect();
          const outside = [...node.querySelectorAll("button")].filter((b) => {
            const x = b.getBoundingClientRect();
            return x.right > r.right + 1 || x.left < r.left - 1;
          });
          return { height: r.height, overflow: outside.length };
        }),
      );
      assert(
        geometry.every((r) => r.height < 220 && !r.overflow),
        JSON.stringify(geometry),
      );
      await page.screenshot({
        path: `docs/screenshots/v030-personas-${width}.png`,
      });
    }
    checks.push(
      "compact persona cards fit at 1440 and 1024 without overflowing controls",
    );
    assert.deepEqual(errors, []);
    assert.deepEqual(remote, []);
    fs.writeFileSync(
      "docs/evidence/v030-ui-profiles.json",
      JSON.stringify(
        { ok: true, checks, errors, remoteRequests: remote },
        null,
        2,
      ),
    );
    console.log(JSON.stringify({ ok: true, checks }));
  } finally {
    await browser.close();
  }
})().catch((error) => {
  console.error(error);
  process.exit(1);
});
