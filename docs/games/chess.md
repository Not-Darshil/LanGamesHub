# Chess — LanGamesHub rule set

Engine: `backend/app/games/chess_game.py` · Players: exactly 2 · Move legality from the
maintained [`python-chess`](https://pypi.org/project/chess/) library (FIDE Laws of Chess).

## Setup
Seat 0 plays White, seat 1 plays Black, from the standard starting position. No clock.

## Moves
* The player to move sends `move` with a move in UCI notation, e.g. `e2e4`, `e1g1`
  (castling as a king move), `e7e8q` (promotion piece `q`, `r`, `b` or `n` is required
  when a pawn reaches the last rank).
* The server accepts only moves in the current position's legal move list. This covers
  check (you may not leave or put your king in check), **castling** (king and rook
  unmoved, squares between empty, king not in, through, or into check), **en passant**
  (only immediately after the double pawn step), and **promotion**.

## Game end
Automatic:
* **Checkmate** — the side that delivered mate wins.
* **Stalemate** — draw.
* **Insufficient material** — draw (neither side can possibly mate).
* **Seventy-five-move rule** and **fivefold repetition** — draw.

On request:
* `claim_draw` — the player to move may claim a draw by **threefold repetition** (the
  current position has occurred three times) or the **fifty-move rule** (50 moves by each
  side without a capture or pawn move). The repetition or move count must already have
  happened; a claim based on a move not yet played is not accepted.
* `offer_draw` — either player may offer a draw; the opponent may `accept_draw` or
  `decline_draw`. Making a move withdraws/declines any pending offer.
* `resign` — either player may resign; the opponent wins.

A player who leaves loses; the opponent wins.

## Visibility
Chess has no hidden information. Both players see the position (FEN), the full move
list in SAN, whose turn it is, check status, the last move, any pending draw offer, and
the result. The player to move also receives the list of legal moves (for highlighting).
