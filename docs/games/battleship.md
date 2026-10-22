# Battleship — LanGamesHub rule set

Engine: `backend/app/games/battleship.py` · Players: exactly 2

## Board and fleet
Each player has a private 10×10 ocean. Rows are `0–9` (shown as A–J) and columns `0–9`
(shown as 1–10). Each fleet has five ships:

| Ship       | Length |
| ---------- | ------ |
| Carrier    | 5      |
| Battleship | 4      |
| Cruiser    | 3      |
| Submarine  | 3      |
| Destroyer  | 2      |

## Placement phase
* Both players place their fleets at the same time, in secret.
* `place` submits all five ships at once: `{"ship", "row", "col", "orientation"}` where
  `(row, col)` is the bow and `orientation` is `H` (extends to the right) or `V`
  (extends downwards). The server checks: each ship exactly once, every cell on the
  board, and no two ships overlapping. Ships may touch.
* `place_random` asks the server to place a valid fleet with its CSPRNG.
* Placement is **final** once accepted. The battle starts when both fleets are placed.

## Battle phase
* Seat 0 fires first; turns alternate after **every** shot (a hit does not grant
  another shot).
* `fire` with `row` and `col` targets the opponent's ocean. The cell must be on the
  board and not already targeted by that player.
* The result is `miss`, `hit`, or `sunk` (all cells of that ship are hit), and the
  sunk ship's type is announced.

## Winning and leaving
The first player to sink all five enemy ships wins. If a player leaves, the opponent
wins.

## Hidden information
The server never sends a player the positions of the opponent's ships — not during
placement, not during battle, and not after the game ends. A player sees:
* their own fleet and every shot the opponent fired at it;
* their own shots with their results, and the names of enemy ships they have sunk
  (whose cells they have already hit);
* whether the opponent has finished placing (yes/no only).
