# Snakes and Ladders — LanGamesHub rule set

Engine: `backend/app/games/snakes.py` · Players: 2–4

## Board
Squares 1–100 on a 10×10 grid, numbered boustrophedon from the bottom-left (row 1 runs
left→right, row 2 right→left, …). All tokens start off the board at square 0.

| Ladders (bottom → top) | Snakes (head → tail) |
| ---------------------- | -------------------- |
| 1 → 38                 | 16 → 6               |
| 4 → 14                 | 47 → 26              |
| 9 → 31                 | 49 → 11              |
| 21 → 42                | 56 → 53              |
| 28 → 84                | 62 → 19              |
| 36 → 44                | 64 → 60              |
| 51 → 67                | 87 → 24              |
| 71 → 91                | 93 → 73              |
| 80 → 100               | 95 → 75              |
|                        | 98 → 78              |

No ladder or snake ends on the start of another, so at most one jump happens per move.

## Turn
1. The current player sends `roll`. The **server** rolls one six-sided die using its
   CSPRNG; clients never supply dice values.
2. The token moves forward by the roll.
3. If it lands on a ladder's bottom it climbs to the top; on a snake's head it slides
   to the tail.
4. Play passes to the next seat. Rolling a 6 does **not** grant an extra turn.

Several tokens may share a square; there is no capturing.

## Finish rule
A player must land **exactly** on 100. If the roll would take the token past 100, the
token does not move and the turn passes.

## Winning and leaving
The first player to reach square 100 wins and the game ends. A player who leaves is
removed from turn order; if only one player remains, they win.

## Actions and visibility
The only action is `{"type": "roll"}` by the current player. Everyone sees every
token's square, the board map, whose turn it is, the last roll (die value, start,
landing square, and any snake/ladder), and the event log. There is no hidden information.
