# Business — LanGamesHub rule set

Engine: `backend/app/games/business.py` (board and cards: `business_board.py`) ·
Players: 2–6 · Indian-style property trading. All amounts are in rupees (₹).

## Board
36 squares around a 10×10 perimeter (9 per side), numbered 0–35 in the direction of play.

| Square | What                    | Square | What                    |
| ------ | ----------------------- | ------ | ----------------------- |
| 0      | **Start**               | 18     | **Rest House** (nothing happens) |
| 1, 3   | Agra, Varanasi (Brown)  | 19, 21, 22 | Goa, Pune, Ahmedabad (Red) |
| 2      | Community Fund          | 20, 33 | Chance                  |
| 4      | Income Tax (₹2,000)     | 24–26  | Surat, Kolkata, Hyderabad (Yellow) |
| 5, 14, 23, 32 | Railways, Airways, Waterways, Roadways | 27 | **Go to Jail** |
| 6–8    | Jaipur, Jodhpur, Udaipur (Sky) | 28, 29, 31 | Chennai, Bengaluru, Gurugram (Green) |
| 9      | **Jail** / just visiting | 11, 30 | Electricity Board, Water Works |
| 10, 12, 13 | Bhopal, Indore, Nagpur (Pink) | 34, 35 | Delhi, Mumbai (Navy) |
| 15–17  | Lucknow, Kochi, Chandigarh (Orange) |  |                    |

22 cities in 8 colour groups, priced ₹600 (Agra) to ₹4,000 (Mumbai). Each city has a
rent table (base, 1–4 houses, hotel); the house cost depends on the group (₹500 for
Brown/Sky, ₹1,000 Pink/Orange, ₹1,500 Red/Yellow, ₹2,000 Green/Navy). Transports cost
₹2,000 and utilities ₹1,500. The full table is sent to clients in every view (`board`).

## Money
* Everyone starts with **₹15,000**.
* **₹2,000 salary** for passing or landing on Start (also when a card moves you past it).
* The bank never runs out of money, houses or hotels.

## Turn
1. The current player sends `roll`; the server rolls two dice and moves the token.
2. The square is resolved (below). The phase becomes `buy`, `debt`, `roll` or `end`.
3. **Doubles** roll again (phase `roll` instead of `end`). A **third double in a row**
   sends the player straight to Jail without moving by that roll; the turn ends.
4. In phase `end` the player sends `end_turn`. A pending trade offer expires then.

Building, selling buildings, mortgaging and unmortgaging are allowed on your own turn
before rolling, while deciding on a purchase and after moving (phases `roll`, `buy`,
`end`). In phase `debt` only selling buildings and mortgaging are allowed.

## Squares
* **Unowned property**: `buy` (needs the cash) or `decline`. There are **no auctions**
  in this version: a declined property simply stays with the bank.
* **Owned by someone else**: pay rent, unless the property is mortgaged.
  * Cities: base rent, **doubled** when the owner holds the whole colour group and this
    city has no buildings; with buildings, the 1–4 house or hotel rent.
  * Transport: ₹250 / ₹500 / ₹1,000 / ₹2,000 for owning 1 / 2 / 3 / 4 (mortgaged ones
    still count toward the number owned).
  * Utilities: 4 × the dice total, or 10 × when the owner has both. A token moved by a
    card uses the dice total of the roll that turn.
* **Income Tax**: pay ₹2,000 to the bank.
* **Chance / Community Fund**: draw the top card of that deck (below).
* **Go to Jail**: go directly to Jail. Start, Jail (visiting) and Rest House do nothing.

## Building
* Only on cities, only when you own **every city of the group** and **none of the group
  is mortgaged**.
* **Build evenly**: a city may get a house only if no other city in its group has fewer.
  4 houses, then a hotel (the 5th building) once every city of the group has 4.
* Selling a building refunds half its cost and must also be even (sell from the city
  with the most). Selling a hotel leaves 4 houses.

## Mortgages
* Allowed only when no city in the property's group has buildings.
* Mortgaging pays half the price; unmortgaging costs that plus 10%.
* No rent is collected on a mortgaged property.

## Cards
Each deck has 12 cards, shuffled by the server at the start and then cycled in that
order. Effects: collect or pay money, advance to a square (collecting the salary if
passing Start, then resolving the square normally), go back 3 spaces, go to Jail, pay
per house and per hotel, collect from each player, pay each player. The deck order is
never sent to any client; only the last drawn card is public. There are no
"get out of jail free" cards.

## Jail
You go to Jail (without passing Start) from the Go to Jail square, a Go to Jail card,
or a third double in a row. On each turn in Jail:
* `pay_fine` (₹500) before rolling, then roll normally (doubles roll again), or
* `roll` for doubles: on doubles, leave and move by that roll, **without** rolling again.
  Otherwise stay. After the **third failed attempt** you must pay the ₹500 fine and
  then move by that roll (if you cannot pay, you enter the debt phase first).

## Debt and bankruptcy
When the current player owes more than their cash, the phase becomes `debt` with the
creditor (a player, or the bank) and the amount. They may sell buildings and mortgage,
then `pay_debt`, or `declare_bankruptcy` (only while they still cannot pay). When one
card makes them owe several players, the debts are queued and paid in seat order.

* **Bankrupt to a player**: buildings are sold back to the bank at half price and that
  money, all cash and all properties go to the creditor. Mortgaged properties stay
  mortgaged (no extra interest is charged).
* **Bankrupt to the bank**: properties return to the bank unowned and unmortgaged, and
  buildings are removed.
* A player who is **not** the current player and owes money (e.g. to a "collect from
  each player" card) is liquidated automatically: buildings are sold evenly as needed,
  then properties are mortgaged cheapest-first. If that is still not enough they go
  bankrupt to the creditor. It is all logged.
* Debts owed to a player who leaves or goes bankrupt are forgiven.

Bankrupt players stay at the table as spectators but take no further part.

## Trading
On your turn, in phase `roll` or `end`, you may offer one other active player a trade:
`{"type": "propose_trade", "to": id, "give": {"cash": n, "squares": [...]},
"get": {"cash": n, "squares": [...]}}`.
* You must own everything you give, they must own everything you ask for, neither side
  may trade a property whose colour group has buildings, both sides must have the cash
  offered, and the trade may not be empty.
* Only one trade can be pending in the game. The recipient sends `accept_trade` or
  `decline_trade`; the proposer may `cancel_trade`. The offer expires when the
  proposer's turn ends or either player leaves the game.
* Accepting re-checks everything, since the state may have changed.
* Mortgaged properties change hands still mortgaged.

## Game end
* When one non-bankrupt player remains, they win ("Last player standing").
* Room option `duration`: 30, 45, 60 or 90 minutes, or no limit (default). When time is
  up, the game ends and the highest **net worth** wins — cash + property prices (half
  for mortgaged ones) + the cost of buildings. Tied players all win.
* A player who **leaves** goes bankrupt to the bank.

## Standings
Players still in the game by net worth (detail "Net worth ₹12,340"), then bankrupt
players, the most recently eliminated first ("Bankrupt" or "Left the game").

## Actions
| `type` | fields | when |
| ------ | ------ | ---- |
| `roll` | | current player, phase `roll` (in Jail: an escape attempt) |
| `pay_fine` | | current player in Jail, phase `roll`, before rolling |
| `buy` / `decline` | | phase `buy` |
| `end_turn` | | phase `end` |
| `build` / `unmortgage` | `square` | your turn, phases `roll`, `buy`, `end` |
| `sell` / `mortgage` | `square` | your turn, phases `roll`, `buy`, `end`, `debt` |
| `pay_debt` / `declare_bankruptcy` | | phase `debt` |
| `propose_trade` | `to`, `give`, `get` | your turn, phases `roll`, `end`, no pending trade |
| `accept_trade` / `decline_trade` | | the trade's recipient |
| `cancel_trade` | | the trade's proposer |

## Visibility
Everything is public except the order of the two card decks: the board and rent tables,
owners, buildings, mortgages, every player's cash, position and jail state, the phase,
the dice, the pending purchase, debt and trade, the last drawn card, the time left
(`ends_in_ms`) and the log. Each player's view also lists the actions they may take
now and the squares they may build on, sell from, mortgage or unmortgage.
