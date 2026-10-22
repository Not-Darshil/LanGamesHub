// Browser end-to-end test: host + guests in separate browser contexts against a real
// server on the disposable test database. Usage (from repo root):
//   node e2e/run.mjs [game ...]      e.g. node e2e/run.mjs uno chess
// Env: LGH_BROWSER (Chromium-family executable), TEST_DATABASE_URL (or read from .env).
//      LGH_URL + LGH_ROOM_PASSWORD + LGH_ADMIN_PASSWORD: test an already-running server
//      (e.g. an installed bundle) instead of starting one. Its database must be fresh.
import { spawn, execFileSync } from "node:child_process";
import { readFileSync, mkdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright-core";
import { GAME_BOTS } from "./bots.mjs";

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..");
const PORT = 8800;
const EXTERNAL_SERVER = process.env.LGH_URL;
const BASE = EXTERNAL_SERVER ?? `http://127.0.0.1:${PORT}`;
const SERVER_HOST = new URL(BASE).hostname;
const ROOM_PASSWORD = process.env.LGH_ROOM_PASSWORD ?? "e2e-room-pass";
const ADMIN_PASSWORD = process.env.LGH_ADMIN_PASSWORD ?? "e2e-admin-password";
const externalRequests = [];
const SHOTS = process.env.LGH_SHOTS ?? join(ROOT, "e2e", "screenshots");
const BROWSER =
  process.env.LGH_BROWSER ?? "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser";
const PYTHON = join(ROOT, "backend", ".venv", "bin", "python");

function testDatabaseUrl() {
  if (process.env.TEST_DATABASE_URL) return process.env.TEST_DATABASE_URL;
  const line = readFileSync(join(ROOT, ".env"), "utf8")
    .split("\n").find((l) => l.startsWith("TEST_DATABASE_URL="));
  if (!line) throw new Error("TEST_DATABASE_URL is not configured");
  return line.slice("TEST_DATABASE_URL=".length).trim();
}

const results = [];
function check(name, ok, detail = "") {
  results.push({ name, ok, detail });
  console.log(`${ok ? "PASS" : "FAIL"}  ${name}${detail ? ` — ${detail}` : ""}`);
}

async function startServer(dbUrl) {
  execFileSync(PYTHON, [join(ROOT, "e2e", "reset_db.py"), dbUrl], { stdio: "inherit" });
  const server = spawn(PYTHON, ["-m", "app"], {
    cwd: join(ROOT, "backend"),
    env: {
      ...process.env, DATABASE_URL: dbUrl, BIND_HOST: "127.0.0.1", BIND_PORT: String(PORT),
      ROOM_PASSWORD, ADMIN_USERNAME: "admin", ADMIN_PASSWORD, LOG_LEVEL: "WARNING",
      DISCONNECT_GRACE_SECONDS: "15",
      // Bots act far faster than people; keep the per-player action limit out of the way.
      RATE_LIMIT_ACTIONS_PER_SECOND: "50",
    },
    stdio: ["ignore", "inherit", "inherit"],
  });
  for (let i = 0; i < 60; i++) {
    try {
      const r = await fetch(`${BASE}/api/health/ready`);
      if (r.ok) return server;
    } catch { /* not up yet */ }
    await new Promise((r) => setTimeout(r, 250));
  }
  server.kill();
  throw new Error("server did not become ready");
}

async function newPage(browser) {
  const context = await browser.newContext({ viewport: { width: 1200, height: 900 } });
  // Offline guard: any request to a host other than the LanGamesHub server is blocked
  // and recorded (CDNs, fonts, analytics...). The app must not need any.
  await context.route("**/*", (route) => {
    const url = new URL(route.request().url());
    if (url.hostname !== SERVER_HOST && url.protocol.startsWith("http")) {
      externalRequests.push(url.href);
      return route.abort();
    }
    return route.continue();
  });
  const page = await context.newPage();
  page.on("dialog", (d) => d.accept());
  page.on("pageerror", (e) => check("no uncaught page errors", false, e.message));
  return page;
}

/** Click the confirm button of the app's styled confirmation dialog. */
async function confirmDialog(page) {
  const dialog = page.getByRole("dialog");
  await dialog.waitFor();
  await dialog.locator(".modal-actions button").last().click();
  await dialog.waitFor({ state: "detached" });
}

async function guestJoin(browser, admin, nickname) {
  const page = await newPage(browser);
  await page.goto(BASE);
  await page.getByPlaceholder("Room password").fill(ROOM_PASSWORD);
  await page.getByRole("button", { name: "Request access" }).click();
  await page.getByText("Waiting for the host").waitFor();
  const row = admin.locator("tr", { hasText: "Approve" }).first();
  await row.getByRole("button", { name: "Approve" }).click();
  await page.getByPlaceholder("Nickname").fill(nickname);
  await page.getByRole("button", { name: "Continue" }).click();
  await page.getByRole("heading", { name: "Lobby" }).waitFor();
  return page;
}

async function blankCheck(page) {
  await page.locator(".blank-screen").waitFor();
  return (await page.evaluate(() => document.body.innerText.trim())) === "";
}

async function coreFlow(browser, admin, players) {
  const [alice, bob] = players;
  // Rejection: neutral blank page that survives reload, and real 403s from the API.
  const eve = await newPage(browser);
  await eve.goto(BASE);
  await eve.getByPlaceholder("Room password").fill("wrong-password");
  await eve.getByRole("button", { name: "Request access" }).click();
  await eve.getByText("Incorrect password").waitFor();
  check("wrong room password is refused", true);
  await eve.getByPlaceholder("Room password").fill(ROOM_PASSWORD);
  await eve.getByRole("button", { name: "Request access" }).click();
  await eve.getByText("Waiting for the host").waitFor();
  await admin.getByRole("button", { name: "Reject" }).click();
  check("rejected guest sees blank page", await blankCheck(eve));
  await eve.reload();
  check("rejected guest stays blank after reload", await blankCheck(eve));
  const apiStatus = await eve.evaluate(async () => (await fetch("/api/state")).status);
  check("rejected guest API calls are refused", apiStatus === 403, `status ${apiStatus}`);

  // Guest Screen Hide on one guest only; survives reload; restore brings it back.
  await admin.locator("tr", { hasText: "Alice" }).getByRole("button", { name: "Hide Screen" }).click();
  check("hidden guest sees blank page", await blankCheck(alice));
  check("other guest unaffected",
    await bob.getByRole("heading", { name: "Lobby" }).isVisible());
  await alice.reload();
  check("hidden guest stays blank after reload", await blankCheck(alice));
  check("admin shows hidden status",
    await admin.locator("tr", { hasText: "Alice" }).getByText("hidden").isVisible());
  await admin.locator("tr", { hasText: "Alice" }).getByRole("button", { name: "Restore Screen" }).click();
  await alice.getByRole("heading", { name: "Lobby" }).waitFor();
  check("restored guest sees lobby again", true);
}

async function playGame(admin, players, key, bot) {
  const gameType = bot.gameType ?? key;
  const roomName = `E2E ${key}`;
  await admin.locator(".create-room select").first().selectOption(gameType);
  if (bot.setup) await bot.setup(admin);
  await admin.getByPlaceholder("Room name").fill(roomName);
  await admin.getByRole("button", { name: "Create room" }).click();
  for (const p of players) {
    const card = p.locator(".room-card", { hasText: roomName });
    await card.getByRole("button", { name: "Join" }).click();
    await p.getByRole("button", { name: "I'm ready" }).click();
  }
  const adminCard = admin.locator(".room-card", { hasText: roomName });
  await adminCard.getByText("ready — waiting for host to start").waitFor();
  await players[0].screenshot({ path: join(SHOTS, `${key}-waiting.png`), fullPage: true });
  check(`${key}: room waits for explicit host start`,
    await players[0].getByText("Everyone is ready. The host will start the game.").isVisible());
  await adminCard.getByRole("button", { name: "Start game" }).click();
  await confirmDialog(admin);
  for (const p of players) await p.locator(`.game.${bot.css}`).waitFor();
  check(`${key}: game started for all players`, true);

  const summary = await bot.play(players, check);
  const html = await Promise.all(players.map((p) => p.content()));
  check(`${key}: log uses nicknames, not ids`, html.every((h) => !h.includes("{{")));
  await Promise.all(players.map((p, i) =>
    p.screenshot({ path: join(SHOTS, `${key}-${i}.png`), fullPage: true })));
  console.log(`      ${key}: ${summary}`);

  // Clean up so players can join the next game.
  if (await adminCard.getByRole("button", { name: "Finish game" }).isVisible()) {
    await adminCard.getByRole("button", { name: "Finish game" }).click();
    await confirmDialog(admin);
  }
  if (bot.after) await bot.after(players, check);
  for (const p of players) {
    await p.getByRole("button", { name: "Back to lobby" }).click();
    await p.getByRole("heading", { name: "Lobby" }).waitFor();
  }
}

async function soundAndThemeFlow(admin, players) {
  const [alice] = players;
  const aliceRow = admin.locator("tr", { hasText: "Alice" });
  await aliceRow.getByText("Sound on").waitFor();
  check("host sees which guests have sound on", true);
  // One guest only.
  const [, bob] = players;
  const bobRow = admin.locator("tr", { hasText: "Bob" });
  await aliceRow.getByRole("button", { name: "Mute Alice" }).click();
  await alice.getByLabel("Muted by the host").waitFor();
  await aliceRow.getByText("Muted by host").waitFor();
  check("host can mute one guest", await bob.getByRole("button", { name: "Mute sounds" }).isVisible()
    && await bobRow.getByText("Sound on").isVisible());
  await aliceRow.getByRole("button", { name: "Unmute Alice" }).click();
  await alice.getByRole("button", { name: "Mute sounds" }).waitFor();
  await aliceRow.getByText("Sound on").waitFor();
  check("host can unmute one guest", true);
  await admin.getByRole("button", { name: "Mute everyone" }).click();
  await alice.getByLabel("Muted by the host").waitFor();
  await aliceRow.getByText("Muted by host").waitFor();
  check("host can mute every guest", true);
  await admin.getByRole("button", { name: "Unmute everyone" }).click();
  await alice.getByRole("button", { name: "Mute sounds" }).waitFor();
  check("host can unmute every guest", true);

  const theme = () => alice.evaluate(() => document.documentElement.dataset.theme);
  const before = await theme();
  await alice.locator(".theme-toggle").click();
  const after = await theme();
  check("theme toggle switches light/dark", before !== after && ["light", "dark"].includes(after), `${before} -> ${after}`);
  await alice.locator(".theme-toggle").click();
}

async function historyFlow(admin, players, played) {
  const [alice] = players;
  await alice.getByRole("tab", { name: "My matches" }).click();
  const rows = alice.locator(".match-row");
  await rows.first().waitFor();
  const count = await rows.count();
  check("players see the matches they played", count === played, `${count} of ${played}`);
  let replays = 0;
  for (let i = 0; i < count; i++) {
    await rows.nth(i).click();
    const dialog = alice.getByRole("dialog");
    await dialog.getByText("Final standings").waitFor();
    if (await dialog.locator(".replay-inner .game").count()) replays++;
    if (i === 0) await alice.screenshot({ path: join(SHOTS, "match-replay.png"), fullPage: true });
    await dialog.getByRole("button", { name: "Close" }).click();
    await dialog.waitFor({ state: "detached" });
  }
  check("each match opens with standings and its final position", replays === count, `${replays}/${count}`);
  await alice.screenshot({ path: join(SHOTS, "my-matches.png"), fullPage: true });
  await alice.getByRole("tab", { name: "Play" }).click();

  const adminRows = admin.locator(".match-row");
  let adminReplays = 0;
  for (let i = 0; i < Math.min(played, await adminRows.count()); i++) {
    await adminRows.nth(i).click();
    const dialog = admin.getByRole("dialog");
    await dialog.getByText("Where it ended").waitFor();
    if (await dialog.locator(".replay-inner .game").count()) adminReplays++;
    await dialog.getByRole("button", { name: "Close" }).click();
    await dialog.waitFor({ state: "detached" });
  }
  check("host can open every match's final position", adminReplays === played, `${adminReplays}/${played}`);
  await admin.getByRole("tab", { name: /Finished/ }).click();
  const finished = await admin.locator(".admin-rooms .room-card").count();
  check("finished rooms are on their own tab", finished === played, `${finished}`);
  await admin.getByRole("tab", { name: /Active/ }).click();
}

async function main() {
  mkdirSync(SHOTS, { recursive: true });
  const requested = process.argv.slice(2);
  const games = requested.length ? requested : Object.keys(GAME_BOTS);
  const server = EXTERNAL_SERVER ? null : await startServer(testDatabaseUrl());
  const browser = await chromium.launch({ executablePath: BROWSER, headless: true });
  try {
    const admin = await newPage(browser);
    await admin.goto(`${BASE}/admin`);
    await admin.getByPlaceholder("Password").fill(ADMIN_PASSWORD);
    await admin.getByRole("button", { name: "Log in" }).click();
    await admin.getByRole("heading", { name: /Access requests/ }).waitFor();
    check("admin login", true);

    const alice = await guestJoin(browser, admin, "Alice");
    const bob = await guestJoin(browser, admin, "Bob");
    check("guests approved and in lobby", true);
    await coreFlow(browser, admin, [alice, bob]);
    await soundAndThemeFlow(admin, [alice, bob]);
    let carol = null;
    await alice.screenshot({ path: join(SHOTS, "lobby.png"), fullPage: true });
    for (const game of games) {
      const bot = GAME_BOTS[game];
      if (!bot) throw new Error(`no bot for ${game}`);
      let seats = [alice, bob];
      if (bot.players === 3) {
        carol ??= await guestJoin(browser, admin, "Carol");
        seats = [alice, bob, carol];
      }
      await playGame(admin, seats, game, bot);
    }
    await historyFlow(admin, [alice, bob], games.length);
    await admin.screenshot({ path: join(SHOTS, "admin.png"), fullPage: true });
    check("no requests to any host other than the LanGamesHub server",
      externalRequests.length === 0, externalRequests.slice(0, 5).join(", "));
  } catch (error) {
    check("e2e run completed", false, String(error?.stack ?? error));
  } finally {
    await browser.close();
    server?.kill();
  }
  const failed = results.filter((r) => !r.ok);
  console.log(`\n${results.length - failed.length}/${results.length} checks passed`);
  process.exit(failed.length ? 1 : 0);
}

await main();
