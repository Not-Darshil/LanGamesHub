# Security model

LanGamesHub is designed for a trusted LAN party, not the internet. This page describes
what it enforces and where its boundaries are.

## Identities

| Identity | How it is obtained | Cookie |
| --- | --- | --- |
| Admin | Username + password at `/admin` (argon2-hashed in the database) | `lgh_admin` |
| Player (guest) | Shared room password → pending request → host approval | `lgh_player` |
| Player (host) | "Open player view" on the dashboard, while logged in as admin | `lgh_player` |

The host's player identity is an ordinary player session: it grants no admin rights,
and the admin session grants no player identity. Session tokens are 256-bit random
values in **HttpOnly, SameSite=Strict** cookies; the database stores only their SHA-256
digests.

## Authorization is enforced on the server

* Every protected REST endpoint re-checks the session's status (approved, not expired,
  not revoked) on every request. The blank white page shown to rejected guests is
  presentation only; a rejected or revoked browser gets `403` from every API and has its
  WebSockets closed, no matter how it calls them or how often it reconnects.
* WebSockets authenticate at the handshake and are re-authorized on **every push**. A
  session that stops being authorized is disconnected instead of receiving data.
* Clients can only send keepalive pings over WebSockets. Every state change goes through
  authenticated REST endpoints, so forged socket messages have no effect.
* State-changing requests require a custom header and a same-origin `Origin`, which
  blocks cross-site request forgery. WebSocket handshakes from another origin are
  refused.

## Data isolation

* Each player receives only their own session, the lobby (room names and counts), and
  their own room and game. Room details and game state never go to non-members.
* Each game engine filters its view per player: UNO hands, Battleship fleets, and the
  legality of a Wild Draw Four are never sent to other players. Battleship never reveals
  unhit enemy ship cells, even after the game ends.
* The admin dashboard shows room metadata and whose turn it is, but **never the state of
  a game in progress**, because the host may also be playing.
* Finished matches keep their final game state so players can review where a game ended.
  A participant sees it exactly as the engine's per-player view allows (their own hand
  or fleet only); other players' private information stays hidden. The host sees the
  spectator view of finished matches, which contains no hidden information. Players can
  only list and open matches they took part in, and hidden guests get none.

## Game integrity

The server is authoritative. Clients send intents; dice, shuffles, and draws use the OS
CSPRNG (`random.SystemRandom`); every action is validated against the rules before it is
applied. Room operations (join, leave, ready, start, actions) run in database
transactions with row locks, so concurrent requests cannot overfill rooms, start a game
twice, or apply two moves against the same state.

## Abuse limits

Per-IP rate limits apply to access requests and admin logins, and per-player limits to
game actions. API request bodies are capped at 64 KB, WebSocket messages at 1 KB, and
each session may hold at most 5 sockets. Pending requests expire. The dashboard flags
requests from IP addresses that were rejected before.

## Room chat

Each room has a chat and emoji reactions. Only members of a room can post to it or
receive its messages; the lobby, other rooms and hidden guests get nothing, and the host
dashboard shows no message contents. Messages are plain text (control characters are
stripped, 300 characters at most) and are rendered as text, never as HTML. Reactions are
limited to a fixed set of emoji. Per-player limits: 5 messages per 10 seconds and 8
reactions per 5 seconds. The host can turn chat off for everyone. Messages are stored
with their room and deleted when the room is removed.

## Sound controls

The host can mute sound effects for one guest or for everyone (including guests who join
later). Like Screen Hide, this only affects the LanGamesHub page: the browser is told to
stop playing its own sound effects. Guests report whether their sound is on so the host
can see it; nothing else about the device is collected.

## Guest Screen Hide boundaries

Guest Screen Hide controls **only the LanGamesHub page** in the selected guest's
browser. It replaces that page with a plain white screen and the server stops sending
that session any room, game, or player information until the host restores it. It does
**not** and cannot:

* control, lock, or blank the guest's operating system, desktop, or other applications;
* close or take over the browser, or send keyboard or mouse input;
* terminate processes or monitor anything outside LanGamesHub.

Hiding never changes game state, turns, room membership, or authorization. A hidden
player who sends a legal move through the API still has it validated normally; error
responses to a hidden session are reduced to a generic "Not available" so they cannot
reveal cards, rooms, or other players' names. Only an
authenticated admin can hide or restore; the state is stored server-side and enforced on
refresh, reconnect, and server restart.

## Known limits

* **Plain HTTP.** Traffic on the LAN is not encrypted, so anyone able to sniff the LAN
  could read session cookies. Use a trusted network. If you put LanGamesHub behind an
  HTTPS reverse proxy, set `COOKIE_SECURE=true`.
* **Client IP addresses** are shown as observed by the server; forwarded headers are
  ignored on purpose. Behind a proxy, every client would appear as the proxy.
* **Single process.** Run exactly one server process. Rate limits and live connections
  are kept in memory.
* The room password is shared by every guest; each guest still needs individual host
  approval.
