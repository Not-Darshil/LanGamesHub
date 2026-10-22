# UNO — LanGamesHub rule set

Engine: `backend/app/games/uno.py` · Players: 2–4 · Single hand: the first player to
empty their hand wins the match (no points are scored).

## Deck
108 cards. For each colour (red, yellow, green, blue): one `0`, two each of `1`–`9`,
two **Skip**, two **Reverse**, two **Draw Two**. Plus four **Wild** and four
**Wild Draw Four**. Each physical card has a unique id `0..107`; clients refer to
cards only by id and the server checks the card is in the player's hand.

## Setup
1. The server shuffles the deck with its CSPRNG and deals 7 cards to each player.
2. The top card of the deck starts the discard pile. If it is a Wild or Wild Draw Four,
   it is shuffled back into the deck and another card is turned (repeat as needed).
3. Seat 0 would play first; the starting card's effect applies to that player:
   * **Skip** — seat 0 is skipped; seat 1 starts.
   * **Reverse** — direction reverses; the last seat starts (with 2 players that is seat 1).
   * **Draw Two** — seat 0 draws 2 and is skipped; seat 1 starts.
   * Number — seat 0 starts.

## A turn
State machine for the current player (`phase`):

```
play ──play card──▶ (effects) ──▶ next player's "play" / "challenge"
  │
  └──draw──▶ drawn card playable? ──yes──▶ drawn ──play that card / pass──▶ next player
                       └──no──▶ next player
challenge (after a Wild Draw Four) ──accept / challenge──▶ resolved
```

* **Playing.** A card is playable if it is a Wild / Wild Draw Four, matches the active
  colour, matches the top card's number, or (for Skip / Reverse / Draw Two) matches the
  top card's symbol. Wilds require choosing a colour.
* **Drawing.** A player may draw one card instead of playing, whether or not they hold a
  playable card. If the drawn card is playable they may play **that card** immediately
  or pass; otherwise the turn ends. Passing is only possible after drawing.
* **Empty deck.** When the draw pile runs out, the discard pile except its top card is
  reshuffled to form a new draw pile. If no cards remain at all, the draw is shortened.

## Action cards
* **Skip** — the next player loses their turn.
* **Reverse** — reverses direction. With 2 players it acts as Skip.
* **Draw Two** — the next player draws 2 and loses their turn. Draw cards do not stack.
* **Wild** — the player chooses the active colour.
* **Wild Draw Four** — the player chooses the colour; the next player must respond:

### Wild Draw Four challenge (challengeable rule)
A Wild Draw Four may be played at any time, but it is only *legal* if the player held
no card matching the active colour at the moment of play (cards of other colours with a
matching number/symbol, and other wilds, do not count). The next player chooses:

* **Accept** — draw 4 and lose the turn.
* **Challenge** — the server checks the hand recorded at the moment of play:
  * *Guilty* (they held a card of the previous active colour): the player who played the
    Wild Draw Four draws 4 instead, and the challenger then takes a normal turn.
  * *Not guilty*: the challenger draws 6 (4 + 2 penalty) and loses the turn.

The chosen colour stands in every case. The result of the check is revealed only by its
consequence; the offender's hand is never shown to the challenger.

## UNO declarations
* When a play leaves a player with exactly one card, they must declare UNO by sending
  the play with `uno: true`, or by sending the `uno` action before they are caught.
* Until the **next player takes a turn action** (play, draw, pass, accept, challenge),
  any other player may **catch** an undeclared player: the caught player draws 2.
* Catching when nobody is catchable is rejected; there is no penalty for a false catch.

## Winning
The first player to play their last card wins immediately; that card's effect is not
applied. If players leave until only one remains, the remaining player wins.

## Players leaving
A leaving (or revoked) player's hand is placed at the bottom of the draw pile and they are
removed from turn order. If it was their turn, the next player in the current direction
plays. A pending Wild Draw Four aimed at them is cancelled; one they played is cancelled
without penalty for the target.

## Actions (client → server)
| `type`      | fields                          | who / when                                 |
| ----------- | ------------------------------- | ------------------------------------------ |
| `play`      | `card`, `color` (wilds), `uno`  | current player, phase `play` or `drawn`     |
| `draw`      |                                 | current player, phase `play`                |
| `pass`      |                                 | current player, phase `drawn`               |
| `accept`    |                                 | current player, phase `challenge`           |
| `challenge` |                                 | current player, phase `challenge`           |
| `uno`       |                                 | a player with one card who has not declared |
| `catch`     | `target`                        | any other player, while target is catchable |

## What each player sees
Their own hand (with which cards are playable on their turn), every player's card count
and UNO status, the top card, active colour, direction, whose turn it is, the draw and
discard pile sizes, the pending Wild Draw Four (who/target, not its legality), the card
they just drew (current player only), and the public event log. Never other hands or the
deck order.
