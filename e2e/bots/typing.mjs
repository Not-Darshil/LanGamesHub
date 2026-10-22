// Typing Race bot: both players type the passage through the real input, concurrently.
// Register in e2e/bots.mjs: import { typing } from "./bots/typing.mjs"; GAME_BOTS.typing = typing.

const INPUT = '[aria-label="Type the passage here"]';

/** Resolves once the input is writable, i.e. the local countdown has reached GO. */
function waitForGo(page, timeout = 15000) {
  return page.waitForFunction((sel) => {
    const el = document.querySelector(sel);
    return !!el && !el.readOnly;
  }, INPUT, { timeout });
}

export const typing = {
  css: "typing",
  async setup(admin) {
    await admin.getByRole("radio", { name: "Short passage" }).click();
  },
  async play(pages, check) {
    const countdown = await Promise.all(pages.map((p) => p.locator(".ty-countdown").count()));
    check("typing: countdown shown before the race", countdown.every((n) => n > 0), `${countdown}`);
    const early = await Promise.all(pages.map((p) => p.locator(INPUT).evaluate((el) => el.readOnly)));
    check("typing: typing locked during the countdown", early.every(Boolean), `${early}`);

    await Promise.all(pages.map((p) => waitForGo(p)));
    const passages = await Promise.all(pages.map((p) => p.locator("[data-passage]").getAttribute("data-passage")));
    const passage = passages[0];
    check("typing: everyone races the same short passage",
      passages.every((t) => t === passage) && passage.length >= 100 && passage.length <= 150, `${passage.length} chars`);

    // ~16 characters per second: well under the server's 25/s anti-cheat limit.
    const started = Date.now();
    await Promise.all(pages.map(async (page) => {
      const input = page.locator(INPUT);
      await input.focus();
      await page.keyboard.type(passage, { delay: 60 });
    }));
    const typedMs = Date.now() - started;

    try {
      await Promise.all(pages.map((p) => p.locator(".result").waitFor({ timeout: 15000 })));
    } catch (error) {
      const state = await Promise.all(pages.map(async (p) => ({
        status: await p.locator(".game-status").innerText().catch(() => "?"),
        toasts: await p.locator(".toast").allInnerTexts(),
        lanes: await p.locator(".ty-lane").allInnerTexts(),
        typed: await p.locator(INPUT).inputValue().catch(() => "?"),
      })));
      throw new Error(`race did not finish: ${JSON.stringify(state)}`);
    }
    const done = await Promise.all(pages.map((p) => p.locator(".ty-lane.done").count()));
    check("typing: both players finished", done.every((n) => n === pages.length), `${done}`);
    const rows = await pages[0].locator(".ty-results-list li").allInnerTexts();
    const speeds = rows.map((r) => Number(r.match(/(\d+) WPM/)?.[1]));
    check("typing: results show each finisher's WPM",
      rows.length === pages.length && speeds.every((n) => n > 0), rows.map((r) => r.replace(/\s+/g, " ")).join(" | "));
    const mine = await Promise.all(pages.map((p) => p.locator(".ty-mine").innerText()));
    check("typing: each player sees their own speed", mine.every((t) => /\d+ WPM/.test(t)));
    const result = await pages[0].locator(".result").innerText();
    check("typing: winner announced with WPM", /Winner:/.test(result) && /Finished first at \d+ WPM/.test(result),
      result.replace(/\s+/g, " "));
    return `${passage.length}-char passage typed in ${(typedMs / 1000).toFixed(1)}s; ${speeds.join(" / ")} WPM`;
  },
};
