// Per-game "bots" that play through the real UI by clicking like a person would.
// Each returns a short summary; `check` records assertions.

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

export const GAME_BOTS = {
  uno: {
    css: "uno",
    async play(pages, check) {
      let turns = 0;
      for (; turns < 40 && !(await finished(pages)); turns++) {
        const page = await whoseTurn(pages, '.game-status:text("Your turn"), .game-status:text("on you")');
        if (!page) break;
        const before = await version(page);
        const accept = page.getByRole("button", { name: "Accept (draw 4)" });
        const playable = page.locator(".uno-hand .uno-playable:enabled");
        if (await accept.isVisible()) {
          await accept.click();
        } else if (await playable.count()) {
          await playable.first().click();
          const red = page.getByRole("button", { name: "red", exact: true });
          if (await red.isVisible().catch(() => false)) await red.click();
        } else if (await page.getByRole("button", { name: "Keep it and pass" }).isVisible()) {
          await page.getByRole("button", { name: "Keep it and pass" }).click();
        } else {
          await page.getByRole("button", { name: "Draw a card" }).click();
        }
        await waitForUpdate(page, before);
      }
      check("uno: turns alternate and server accepts UI moves",
        turns >= 10 || (await finished(pages)), `${turns} turns`);
      const hands = await Promise.all(pages.map((p) => p.locator(".uno-hand .uno-card").count()));
      const counts = await Promise.all(pages.map(async (p) =>
        Number((await p.locator(".uno-hand-head h3").innerText()).match(/\d+/)?.[0])));
      check("uno: each player sees only their own hand",
        hands.every((n, i) => n === counts[i]), `rendered ${hands} vs own count ${counts}`);
      return `${turns} turns played, hands ${hands.join("/")}`;
    },
  },
  snakes: {
    css: "snakes",
    async play(pages, check) {
      let rolls = 0;
      for (; rolls < 30 && !(await finished(pages)); rolls++) {
        const page = await whoseTurn(pages, '.game-status:text("Your turn")');
        if (!page) break;
        const before = await version(page);
        await page.getByRole("button", { name: "Roll the die" }).click();
        await waitForUpdate(page, before);
      }
      const tokens = await pages[0].locator(".sl-board .sl-token").count();
      check("snakes: server-rolled moves shown on the board", rolls >= 10 || (await finished(pages)),
        `${rolls} rolls`);
      const statuses = await Promise.all(pages.map((p) => p.locator(".game-status").innerText()));
      check("snakes: both players see the same turn", new Set(statuses.map((t) => t.includes("won"))).size === 1);
      return `${rolls} rolls, ${tokens} tokens on board`;
    },
  },
  ludo: {
    css: "ludo",
    async play(pages, check) {
      let actions = 0;
      let moves = 0;
      for (; actions < 60 && !(await finished(pages)); actions++) {
        const page = await whoseTurn(pages, '.game-status:text("Your turn"), .game-status:text("Choose a token")');
        if (!page) break;
        const before = await version(page);
        const movable = page.locator(".lu-movable");
        if (await movable.count()) {
          await movable.first().click();
          moves++;
        } else {
          await page.getByRole("button", { name: "Roll the die" }).click();
        }
        await waitForUpdate(page, before);
      }
      check("ludo: rolls and token moves accepted through the UI", actions >= 20, `${actions} actions, ${moves} moves`);
      const tokens = await Promise.all(pages.map((p) => p.locator(".lu-token").count()));
      check("ludo: all 8 tokens drawn for both players", tokens.every((n) => n === 8), `${tokens}`);
      return `${actions} actions (${moves} token moves)`;
    },
  },
  battleship: {
    css: "battleship",
    async play(pages, check) {
      const [first, second] = pages;
      // Player 1 places by hand through the UI: five horizontal ships on rows A, C, E, G, I.
      for (const row of ["A", "C", "E", "G", "I"]) {
        await first.locator(`.bs-cell[aria-label="${row}1"]`).click();
      }
      await first.getByRole("button", { name: "Confirm fleet" }).click();
      await first.getByText("Waiting for").waitFor();
      // Player 2 uses server-side random placement.
      await second.getByRole("button", { name: "Place randomly" }).click();
      await first.getByText("Your turn — fire").waitFor();
      check("battleship: battle starts once both fleets are placed", true);
      const ownShips = await first.locator(".bs-grid-wrap", { hasText: "Your fleet" }).locator(".bs-ship").count();
      check("battleship: manual placement accepted (17 ship cells)", ownShips === 17, `${ownShips}`);
      const enemyShips = await first.locator(".bs-grid-wrap", { hasText: "Enemy waters" }).locator(".bs-ship").count();
      check("battleship: enemy fleet not shown", enemyShips === 0, `${enemyShips}`);

      let shots = 0;
      for (; shots < 40 && !(await finished(pages)); shots++) {
        const page = await whoseTurn(pages, '.game-status:text("Your turn")');
        if (!page) break;
        const before = await version(page);
        await page.locator(".bs-grid-wrap", { hasText: "Enemy waters" }).locator(".bs-target").first().click();
        await waitForUpdate(page, before);
      }
      const marks = await second.locator(".bs-grid-wrap", { hasText: "Your fleet" }).locator(".bs-miss, .bs-hit").count();
      check("battleship: shots fired through the UI", shots >= 20, `${shots} shots`);
      check("battleship: defender sees incoming shots", marks > 0, `${marks} marks`);
      return `${shots} shots`;
    },
  },
  chess: {
    css: "chess",
    async play(pages, check) {
      const [white, black] = pages;
      const a1 = await white.locator('.ch-square[aria-label="a1"]').getAttribute("class");
      check("chess: a1 is a dark square", a1.includes("ch-dark"));
      const flipped = await black.locator(".ch-square").first().getAttribute("aria-label");
      check("chess: board flipped for black", flipped === "h1", flipped);
      // Scholar's mate, entirely by clicking squares.
      const moves = [[white, "e2", "e4"], [black, "e7", "e5"], [white, "f1", "c4"],
        [black, "b8", "c6"], [white, "d1", "h5"], [black, "g8", "f6"], [white, "h5", "f7"]];
      for (const [page, from, to] of moves) {
        const before = await version(page);
        await page.locator(`.ch-square[aria-label="${from}"]`).click();
        await page.locator(`.ch-square[aria-label="${to}"]`).click();
        await waitForUpdate(page, before);
      }
      await black.locator(".result").waitFor();
      const result = await black.locator(".result").innerText();
      check("chess: checkmate detected and announced", /Winner: Alice/.test(result) && /Checkmate/.test(result), result);
      const san = await white.locator(".ch-moves").innerText();
      check("chess: SAN move list", san.includes("Qxf7#"), san.replace(/\n/g, " "));
      return "scholar's mate in 7 plies";
    },
  },
  chess_clock: {
    css: "chess",
    gameType: "chess",
    async setup(admin) {
      await admin.getByRole("radio", { name: "1 min Bullet" }).click();
    },
    async play(pages, check) {
      const [white, black] = pages;
      const clocks = await Promise.all(pages.map((p) => p.locator(".ch-clock").count()));
      check("chess clock: both clocks shown to both players", clocks.every((n) => n === 2), `${clocks}`);
      check("chess clock: clocks wait for White's first move",
        (await white.locator(".ch-clock.running").count()) === 0);
      const before = await version(white);
      await white.locator('.ch-square[aria-label="e2"]').click();
      await white.locator('.ch-square[aria-label="e4"]').click();
      await waitForUpdate(white, before);
      const running = black.locator(".ch-clock.running .ch-clock-time");
      await running.waitFor();
      const seconds = (t) => t.split(":").reduce((acc, part) => acc * 60 + Number(part), 0);
      const t1 = seconds(await running.innerText());
      await sleep(1600);
      const t2 = seconds(await running.innerText());
      check("chess clock: Black's clock counts down after White moves", t1 <= 60 && t2 < t1, `${t1} -> ${t2}`);
      return `clock ${t1}s -> ${t2}s`;
    },
  },
};
