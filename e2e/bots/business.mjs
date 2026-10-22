// Business bot: plays through the real UI (roll, buy when offered, end turn) and checks
// that cash and property ownership change and stay in sync across players.

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

/** Wait until one of the pages shows its "your turn" marker; returns that page. */
async function whoseTurn(pages, marker, timeout = 8000) {
  const deadline = Date.now() + timeout;
  while (Date.now() < deadline) {
    for (const page of pages) {
      if (await page.locator(marker).count()) return page;
    }
    await sleep(100);
  }
  return null;
}

const version = (page) =>
  page.locator("[data-game-version]").getAttribute("data-game-version").catch(() => null);

/** Wait until the server has accepted a move and pushed a newer game version. */
async function waitForUpdate(page, before) {
  try {
    await page.waitForFunction(
      (v) => document.querySelector("[data-game-version]")?.getAttribute("data-game-version") !== v,
      before, { timeout: 5000 });
  } catch {
    const error = await page.locator("p.error").allInnerTexts();
    const status = await page.locator(".game-status").allInnerTexts();
    throw new Error(`move not applied (error: ${JSON.stringify(error)}, status: ${JSON.stringify(status)})`);
  }
}

async function finished(pages) {
  return (await pages[0].locator(".result").count()) > 0;
}

const usable = async (locator) =>
  (await locator.count()) > 0 && (await locator.first().isVisible()) && (await locator.first().isEnabled());

/** Exact cash per player, from the rows' data attributes (the shown number animates). */
const cashes = (page) => page.locator(".business .bz-player").evaluateAll(
  (rows) => rows.map((r) => `${r.dataset.player}=${r.dataset.cash}`).join(" "));
const owned = (page) => page.locator(".business .bz-tile.owned").count();

/** Wait until every page shows the same value (pushes can arrive a moment apart). */
async function agreed(pages, read, timeout = 4000) {
  const deadline = Date.now() + timeout;
  let values = [];
  while (Date.now() < deadline) {
    values = await Promise.all(pages.map(read));
    if (values.every((v) => v === values[0])) return { same: true, values };
    await sleep(150);
  }
  return { same: false, values };
}

export const business = {
  css: "business",
  async play(pages, check) {
    const startCash = await cashes(pages[0]);
    const startOwned = await owned(pages[0]);
    check("business: board drawn with 36 squares for every player",
      (await Promise.all(pages.map((p) => p.locator(".bz-tile").count()))).every((n) => n === 36));

    let actions = 0, rolls = 0, buys = 0, ends = 0;
    for (; actions < 30 && !(await finished(pages)); actions++) {
      const page = await whoseTurn(pages, '.game-status:text("Your turn")');
      if (!page) break;
      const before = await version(page);
      const button = (name) => page.locator(".business .side-panel").getByRole("button", { name, exact: true });
      if (await usable(button("Buy"))) {
        await button("Buy").click();
        buys++;
      } else if (await usable(button("Decline"))) {
        await button("Decline").click();
      } else if (await usable(button("Pay debt"))) {
        await button("Pay debt").click();
      } else if (await usable(button("Declare bankruptcy"))) {
        await button("Declare bankruptcy").click();
        await page.getByRole("dialog").getByRole("button", { name: "Declare bankruptcy" }).click();
      } else if (await usable(button("Pay fine"))) {
        await button("Pay fine").click();
      } else if (await usable(button("End turn"))) {
        await button("End turn").click();
        ends++;
      } else if (await usable(button("Roll dice"))) {
        await button("Roll dice").click();
        rolls++;
      } else {
        await sleep(200); // a button is momentarily disabled while the last action is in flight
        continue;
      }
      await waitForUpdate(page, before);
    }

    check("business: rolls, purchases and turn ends accepted through the UI",
      actions >= 20 || (await finished(pages)), `${actions} actions: ${rolls} rolls, ${buys} buys, ${ends} ends`);
    const cash = await agreed(pages, cashes);
    check("business: cash changed and every player sees the same balances",
      cash.same && cash.values[0] !== startCash, `${startCash} -> ${cash.values.join(" | ")}`);
    const props = await agreed(pages, owned);
    check("business: purchases show as owned tiles on every board",
      props.same && (buys === 0 || props.values[0] > startOwned), `${startOwned} -> ${props.values.join("/")}`);
    const mine = await Promise.all(pages.map((p) => p.locator(".business .bz-chip").count()));
    check("business: owned tiles match the players' property lists",
      mine.reduce((a, b) => a + b, 0) === props.values[0], `${mine} vs ${props.values[0]}`);
    return `${actions} actions (${rolls} rolls, ${buys} purchases, ${ends} turns ended), ${props.values[0]} properties owned`;
  },
};
