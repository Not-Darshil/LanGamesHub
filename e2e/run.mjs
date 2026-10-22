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

async function playGame(admin, players, gameType, bot) {
  const roomName = `E2E ${gameType}`;
  await admin.locator(".create-room select").first().selectOption(gameType);
  await admin.getByPlaceholder("Room name").fill(roomName);
  await admin.getByRole("button", { name: "Create room" }).click();
  for (const p of players) {
    const card = p.locator(".room-card", { hasText: roomName });
    await card.getByRole("button", { name: "Join" }).click();
    await p.getByRole("button", { name: "I'm ready" }).click();
  }
  const adminCard = admin.locator(".room-card", { hasText: roomName });
  await adminCard.getByText("ready — waiting for host to start").waitFor();
  check(`${gameType}: room waits for explicit host start`,
    await players[0].getByText("Everyone is ready. The host will start the game.").isVisible());
  await adminCard.getByRole("button", { name: "Start game" }).click();
  for (const p of players) await p.locator(`.game.${bot.css}`).waitFor();
  check(`${gameType}: game started for all players`, true);

  const summary = await bot.play(players, check);
  const html = await Promise.all(players.map((p) => p.content()));
  check(`${gameType}: log uses nicknames, not ids`, html.every((h) => !h.includes("{{")));
  await Promise.all(players.map((p, i) =>
    p.screenshot({ path: join(SHOTS, `${gameType}-${i}.png`), fullPage: true })));
  console.log(`      ${gameType}: ${summary}`);

  // Clean up so players can join the next game.
  if (await adminCard.getByRole("button", { name: "Finish game" }).isVisible()) {
    await adminCard.getByRole("button", { name: "Finish game" }).click();
  }
  for (const p of players) {
    await p.getByRole("button", { name: "Back to lobby" }).click();
    await p.getByRole("heading", { name: "Lobby" }).waitFor();
  }
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
    for (const game of games) {
      const bot = GAME_BOTS[game];
      if (!bot) throw new Error(`no bot for ${game}`);
      await playGame(admin, [alice, bob], game, bot);
    }
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
