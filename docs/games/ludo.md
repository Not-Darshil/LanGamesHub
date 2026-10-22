# Ludo — LanGamesHub rule set

Engine: `backend/app/games/ludo.py` · Players: 2–4 · Each player has 4 tokens.

## Colours and seats
Colours run clockwise: red, green, yellow, blue. Seats are assigned colours so that
two players sit opposite each other:

| Players | Colours (seat order)        |
| ------- | --------------------------- |
| 2       | red, yellow                 |
| 3       | red, green, yellow          |
| 4       | red, green, yellow, blue    |

## Board
* A shared **main track** of 52 squares (absolute indices 0–51, clockwise).
  Each colour's **start square** is red 0, green 13, yellow 26, blue 39.
* **Safe squares**: the four start squares and the four star squares 8, 21, 34, 47.
* Each colour has a private **home column** of 5 squares, then **home**.

A token's *progress* is counted from its own start square:

| Progress | Meaning                                                   |
| -------- | --------------------------------------------------------- |
| −1       | in the yard                                               |
| 0–50     | on the main track at absolute `(start + progress) mod 52` |
| 51–55    | in its own home column (no other colour can reach these)  |
| 56       | home (finished)                                           |

## Turn
1. The current player sends `roll`; the **server** rolls one die with its CSPRNG.
2. Legal moves for that roll:
   * a token in the yard may leave only on a **6**, onto its start square (progress 0);
   * a token on the board may move forward by the roll if it does not pass home:
     **an exact roll is required to reach home** (progress must stay ≤ 56).
3. If there is no legal move, the turn ends (a 6 still earns the extra roll below).
   Otherwise the player sends `move` with a token index (0–3).
4. **Rolling a 6 grants another roll** by the same player. A **third consecutive 6**
   forfeits the rest of the turn immediately (that roll cannot be used).

## Captures and stacking
* A token that finishes its move on a main-track square occupied by **opponent**
  tokens sends all of them back to their yards — **unless the square is safe**.
* Any number of tokens (of any colours) may share a square. There are no blockades:
  tokens can always move past or onto other tokens.
* Home-column squares and home are never shared with opponents.
* Capturing or reaching home does not grant an extra roll (only a 6 does).

## Winning and leaving
The first player to bring all four tokens home wins and the game ends. A player who
leaves is removed with their tokens; if only one player remains, they win.

## Actions and visibility
| `type` | fields  | when                                        |
| ------ | ------- | ------------------------------------------- |
| `roll` |         | current player, phase `roll`                |
| `move` | `token` | current player, phase `move`, a legal token |

All information is public: every token's progress, colours, current player, phase, the
current die value, the legal tokens for that die, and the event log.
