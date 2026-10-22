"""Business: an Indian property-trading board game. Rules: docs/games/business.md."""

from __future__ import annotations

import copy
import random
import time
from collections.abc import Callable
from typing import Any

from app.games.base import (
    Action,
    GameEngine,
    GameError,
    GameInfo,
    Options,
    Outcome,
    Placing,
    State,
    log,
    rank,
    require_int,
    who,
)
from app.games.business_board import (
    CARDS,
    DECK_NAMES,
    DURATIONS,
    GO_TO_JAIL,
    GROUP_SQUARES,
    GROUPS,
    HOTEL,
    INCOME_TAX,
    JAIL,
    JAIL_FINE,
    PROPERTIES,
    PROPERTY_KINDS,
    SALARY,
    SIZE,
    SQUARES,
    START_CASH,
    TRANSPORT_RENT,
    TRANSPORTS,
    UTILITIES,
    UTILITY_MULTIPLIER,
    board_view,
    house_cost,
    money,
    mortgage_value,
    unmortgage_cost,
)

LOG_LIMIT = 40
BOARD = board_view()
RULES = {
    "start_cash": START_CASH, "salary": SALARY, "jail_fine": JAIL_FINE, "income_tax": INCOME_TAX,
    "transport_rents": TRANSPORT_RENT[1:], "utility_multipliers": UTILITY_MULTIPLIER[1:],
    "jail": JAIL, "go_to_jail": GO_TO_JAIL, "size": SIZE,
}


def _name(square: int) -> str:
    return SQUARES[square]["name"]


class BusinessEngine(GameEngine):
    info = GameInfo("business", "Business", 2, 6,
                    "Buy Indian cities, build houses and hotels, and bankrupt your rivals.")
    timed = True  # deadline() is set when the room picked a game length

    def __init__(self, clock: Callable[[], float] = time.time) -> None:
        self.clock = clock  # wall-clock seconds; injectable for tests

    def now(self) -> float:
        return self.clock()

    # -- options and clock -------------------------------------------------------------

    def validate_options(self, options: Options | None) -> Options:
        options = dict(options or {})
        duration = options.pop("duration", None)
        if options:
            raise GameError("Unknown Business option")
        if duration in (None, "", "none", 0):
            return {}
        if isinstance(duration, str) and duration.isdigit():
            duration = int(duration)
        if isinstance(duration, bool) or duration not in DURATIONS:
            raise GameError("Game length must be 30, 45, 60 or 90 minutes")
        return {"duration": duration}

    def options_label(self, options: Options) -> str | None:
        duration = (options or {}).get("duration")
        return f"{duration} min game" if duration in DURATIONS else "No time limit"

    def configure(self, state: State, options: Options) -> None:
        duration = (options or {}).get("duration")
        if duration in DURATIONS:
            state["duration"] = duration
            state["ends_at"] = state["started_at"] + duration * 60

    def deadline(self, state: State) -> float | None:
        if state["result"] is not None:
            return None
        return state.get("ends_at")

    def expire(self, state: State) -> State:
        due = self.deadline(state)
        if due is None or self.now() < due:
            return state
        new_state = copy.deepcopy(state)
        self._finish_on_time(new_state)
        return new_state

    def _finish_on_time(self, state: State) -> None:
        worth = {p: self.net_worth(state, p) for p in self._active(state)}
        best = max(worth.values())
        winners = [p for p in self._active(state) if worth[p] == best]
        state["result"] = {"winners": winners, "draw": False,
                           "reason": "Time up: highest net worth"}
        state["offer"] = None
        state["trade"] = None
        names = " and ".join(who(w) for w in winners)
        log(state, f"Time is up! Highest net worth: {names} with {money(best)}", LOG_LIMIT)

    # -- setup -------------------------------------------------------------------------

    def new_game(self, players: list[str], rng: random.Random) -> State:
        decks = {}
        for deck, cards in CARDS.items():
            order = list(range(len(cards)))
            rng.shuffle(order)
            decks[deck] = order
        return {
            "players": list(players),            # seat order; bankrupt players stay listed
            "cash": {p: START_CASH for p in players},
            "pos": {p: 0 for p in players},
            "jail": {},                          # player -> failed escape rolls so far
            "bankrupt": [],                      # in order of elimination
            "left": [],
            "owner": [None] * SIZE,
            "houses": [0] * SIZE,                # 1-4 houses, 5 = hotel
            "mortgaged": [False] * SIZE,
            "current": 0,
            "phase": "roll",                     # roll | buy | end | debt
            "dice": None,
            "roll_seq": 0,
            "doubles": 0,                        # doubles rolled in a row this turn
            "again": False,                      # the last roll was a double: roll again
            "offer": None,                       # {"square"} while phase == "buy"
            "debts": [],                         # current player's unpaid {creditor, amount, what}
            "resume": None,                      # {"move": n}: a move waiting on a paid jail fine
            "trade": None,
            "trade_seq": 0,
            "card": None,                        # the last drawn card (public)
            "card_seq": 0,
            "moves": [],                         # token movements caused by the last action
            "decks": decks,                      # hidden: card order per deck
            "deck_pos": {deck: 0 for deck in CARDS},
            "started_at": self.now(),
            "duration": None,
            "ends_at": None,
            "result": None,
            "log": [],
        }

    # -- small helpers -----------------------------------------------------------------

    @staticmethod
    def _current(state: State) -> str:
        return state["players"][state["current"]]

    @staticmethod
    def _active(state: State) -> list[str]:
        return [p for p in state["players"] if p not in state["bankrupt"]]

    @staticmethod
    def _owned(state: State, player: str) -> list[int]:
        return [i for i in PROPERTIES if state["owner"][i] == player]

    @staticmethod
    def net_worth(state: State, player: str) -> int:
        total = state["cash"][player]
        for i in PROPERTIES:
            if state["owner"][i] != player:
                continue
            price = SQUARES[i]["price"]
            total += price // 2 if state["mortgaged"][i] else price
            total += state["houses"][i] * house_cost(i)
        return total

    def _log(self, state: State, message: str) -> None:
        log(state, message, LOG_LIMIT)

    # -- actions -----------------------------------------------------------------------

    def _apply(self, state: State, player: str, action: Action, rng: random.Random) -> None:
        if state.get("ends_at") is not None and self.now() >= state["ends_at"]:
            self._finish_on_time(state)
            return  # time ran out before this action arrived; the game is over
        if player in state["bankrupt"]:
            raise GameError("You are bankrupt and out of the game")
        kind = action["type"]
        state["moves"] = []
        if kind in ("accept_trade", "decline_trade", "cancel_trade"):
            self._respond_trade(state, player, kind)
        else:
            if self._current(state) != player:
                raise GameError("It is not your turn")
            handler = {
                "roll": self._roll,
                "pay_fine": self._pay_fine,
                "buy": self._buy,
                "decline": self._decline,
                "end_turn": self._end_turn,
                "build": self._build,
                "sell": self._sell,
                "mortgage": self._mortgage,
                "unmortgage": self._unmortgage,
                "pay_debt": self._pay_debt,
                "declare_bankruptcy": self._declare_bankruptcy,
                "propose_trade": self._propose_trade,
            }.get(kind)
            if handler is None:
                raise GameError("Unknown action")
            handler(state, player, action, rng)
        self._check_winner(state)

    # Turn flow ------------------------------------------------------------------------

    def _roll(self, state: State, player: str, action: Action, rng: random.Random) -> None:
        if state["phase"] != "roll":
            raise GameError({"buy": "Buy or decline the property first",
                             "debt": "Settle your debt first"}.get(state["phase"],
                                                                   "You have already rolled"))
        d1, d2 = rng.randint(1, 6), rng.randint(1, 6)
        total, doubles = d1 + d2, d1 == d2
        state["dice"] = [d1, d2]
        state["roll_seq"] += 1
        state["again"] = False
        if player in state["jail"]:
            if doubles:
                del state["jail"][player]
                self._log(state, f"{who(player)} rolled double {d1}s and left Jail")
                self._walk(state, player, total)
            else:
                state["jail"][player] += 1
                attempts = state["jail"][player]
                if attempts < 3:
                    self._log(state, f"{who(player)} rolled {d1} + {d2} and stayed in Jail "
                                     f"({attempts}/3)")
                else:
                    self._log(state, f"{who(player)} failed a third time: the "
                                     f"{money(JAIL_FINE)} fine is due")
                    if state["cash"][player] >= JAIL_FINE:
                        self._pay(state, player, None, JAIL_FINE, "jail fine")
                        del state["jail"][player]
                        self._walk(state, player, total)
                    else:
                        self._charge(state, player, None, JAIL_FINE, "jail fine")
                        state["resume"] = {"move": total}
            self._settle(state)
            return
        state["doubles"] = state["doubles"] + 1 if doubles else 0
        if state["doubles"] == 3:
            self._log(state, f"{who(player)} rolled a third double in a row and was sent to Jail")
            self._send_to_jail(state, player)
            self._settle(state)
            return
        state["again"] = doubles
        self._log(state, f"{who(player)} rolled {d1} + {d2}" + (" (double)" if doubles else ""))
        self._walk(state, player, total)
        self._settle(state)

    def _pay_fine(self, state: State, player: str, action: Action, rng: random.Random) -> None:
        if player not in state["jail"]:
            raise GameError("You are not in Jail")
        if state["phase"] != "roll":
            raise GameError("Pay the fine before you roll")
        if state["cash"][player] < JAIL_FINE:
            raise GameError(f"You need {money(JAIL_FINE)} to pay the fine")
        self._pay(state, player, None, JAIL_FINE, "to leave Jail")
        del state["jail"][player]

    def _end_turn(self, state: State, player: str, action: Action, rng: random.Random) -> None:
        if state["phase"] != "end":
            raise GameError({"roll": "Roll the dice first",
                             "buy": "Buy or decline the property first",
                             "debt": "Settle your debt first"}.get(state["phase"], "Not now"))
        self._next_turn(state)

    def _settle(self, state: State) -> None:
        """Pick the phase once the current player's move (and its effects) are resolved."""
        if state["result"] is not None:
            return
        if state["debts"]:
            state["phase"] = "debt"
        elif state["offer"] is not None:
            state["phase"] = "buy"
        else:
            state["phase"] = "roll" if state["again"] else "end"

    def _next_turn(self, state: State) -> None:
        if state["trade"] is not None:
            self._log(state, f"The trade offer from {who(state['trade']['from'])} expired")
            state["trade"] = None
        state["offer"] = None
        state["debts"] = []
        state["resume"] = None
        state["doubles"] = 0
        state["again"] = False
        state["phase"] = "roll"
        count = len(state["players"])
        for step in range(1, count + 1):
            index = (state["current"] + step) % count
            if state["players"][index] not in state["bankrupt"]:
                state["current"] = index
                return

    def _check_winner(self, state: State) -> None:
        if state["result"] is not None:
            return
        active = self._active(state)
        if len(active) == 1:
            state["result"] = {"winners": active, "draw": False, "reason": "Last player standing"}
            state["offer"] = None
            state["trade"] = None
            state["debts"] = []
            self._log(state, f"{who(active[0])} won as the last player standing")

    # Movement ---------------------------------------------------------------------------

    def _walk(self, state: State, player: str, steps: int) -> None:
        """Move forward by a dice roll, square by square."""
        start = state["pos"][player]
        dest = (start + steps) % SIZE
        state["moves"].append({"player": player, "from": start, "to": dest, "walk": True})
        state["pos"][player] = dest
        if start + steps >= SIZE:
            self._salary(state, player)
        self._land(state, player)

    def _advance_to(self, state: State, player: str, target: int) -> None:
        """Card move forward to a square, collecting the salary if it passes Start."""
        start = state["pos"][player]
        state["moves"].append({"player": player, "from": start, "to": target, "walk": False})
        state["pos"][player] = target
        if target <= start:
            self._salary(state, player)
        self._land(state, player)

    def _go_back(self, state: State, player: str, steps: int) -> None:
        start = state["pos"][player]
        dest = (start - steps) % SIZE
        state["moves"].append({"player": player, "from": start, "to": dest, "walk": False})
        state["pos"][player] = dest
        self._land(state, player)

    def _send_to_jail(self, state: State, player: str) -> None:
        start = state["pos"][player]
        state["moves"].append({"player": player, "from": start, "to": JAIL, "walk": False})
        state["pos"][player] = JAIL
        state["jail"][player] = 0
        if player == self._current(state):
            state["again"] = False
            state["doubles"] = 0

    def _salary(self, state: State, player: str) -> None:
        state["cash"][player] += SALARY
        self._log(state, f"{who(player)} collected {money(SALARY)} salary at Start")

    def _land(self, state: State, player: str) -> None:
        square = state["pos"][player]
        kind = SQUARES[square]["kind"]
        if kind in PROPERTY_KINDS:
            owner = state["owner"][square]
            if owner is None:
                state["offer"] = {"square": square}
            elif owner != player:
                if state["mortgaged"][square]:
                    self._log(state, f"{who(player)} landed on {_name(square)}: mortgaged, no rent")
                else:
                    self._charge(state, player, owner, self.rent(state, square), "rent")
        elif kind == "tax":
            self._charge(state, player, None, INCOME_TAX, "Income Tax")
        elif kind in ("chance", "fund"):
            self._draw(state, player, kind)
        elif kind == "go_to_jail":
            self._log(state, f"{who(player)} was sent to Jail")
            self._send_to_jail(state, player)

    def rent(self, state: State, square: int) -> int:
        owner = state["owner"][square]
        info = SQUARES[square]
        if info["kind"] == "city":
            houses = state["houses"][square]
            if houses:
                return int(info["rents"][houses])
            whole = all(state["owner"][i] == owner for i in GROUP_SQUARES[info["group"]])
            return int(info["rents"][0]) * (2 if whole else 1)
        if info["kind"] == "transport":
            return TRANSPORT_RENT[sum(state["owner"][i] == owner for i in TRANSPORTS)]
        dice = sum(state["dice"] or [0])
        return dice * UTILITY_MULTIPLIER[sum(state["owner"][i] == owner for i in UTILITIES)]

    # Cards ------------------------------------------------------------------------------

    def _draw(self, state: State, player: str, deck: str) -> None:
        order = state["decks"][deck]
        card = CARDS[deck][order[state["deck_pos"][deck] % len(order)]]
        state["deck_pos"][deck] = (state["deck_pos"][deck] + 1) % len(order)
        state["card_seq"] += 1
        state["card"] = {"deck": deck, "title": DECK_NAMES[deck], "text": card["text"],
                         "player": player, "seq": state["card_seq"]}
        self._log(state, f"{who(player)} drew {DECK_NAMES[deck]}: {card['text']}")
        kind = card["kind"]
        if kind == "collect":
            state["cash"][player] += card["amount"]
        elif kind == "pay":
            self._charge(state, player, None, card["amount"], "")
        elif kind == "advance":
            self._advance_to(state, player, card["to"])
        elif kind == "back":
            self._go_back(state, player, card["steps"])
        elif kind == "jail":
            self._send_to_jail(state, player)
        elif kind == "repairs":
            houses = sum(h for i, h in enumerate(state["houses"])
                         if state["owner"][i] == player and h < HOTEL)
            hotels = sum(1 for i, h in enumerate(state["houses"])
                         if state["owner"][i] == player and h == HOTEL)
            amount = houses * card["house"] + hotels * card["hotel"]
            if amount:
                self._charge(state, player, None, amount, "for repairs")
            else:
                self._log(state, f"{who(player)} paid nothing (no buildings)")
        elif kind == "collect_each":
            for other in self._others_in_turn_order(state, player):
                if state["result"] is not None or player in state["bankrupt"]:
                    break
                self._charge(state, other, player, card["amount"], "")
        elif kind == "pay_each":
            for other in self._others_in_turn_order(state, player):
                self._charge(state, player, other, card["amount"], "")

    def _others_in_turn_order(self, state: State, player: str) -> list[str]:
        players = state["players"]
        start = players.index(player)
        ordered = players[start + 1:] + players[:start]
        return [p for p in ordered if p not in state["bankrupt"]]

    # Money and debt ---------------------------------------------------------------------

    def _pay(self, state: State, debtor: str, creditor: str | None, amount: int,
             what: str) -> None:
        state["cash"][debtor] -= amount
        if creditor is not None:
            state["cash"][creditor] += amount
        message = f"{who(debtor)} paid {money(amount)}" + (f" {what}" if what else "")
        if creditor is not None:
            message += f" to {who(creditor)}"
        elif not what:
            message += " to the bank"
        self._log(state, message)

    def _charge(self, state: State, debtor: str, creditor: str | None, amount: int,
                what: str) -> None:
        """``debtor`` owes ``amount``: pay now, open a debt, or liquidate a bystander."""
        if amount <= 0:
            return
        current = self._current(state)
        if debtor == current and state["debts"]:
            state["debts"].append({"creditor": creditor, "amount": amount, "what": what})
            return
        if state["cash"][debtor] >= amount:
            self._pay(state, debtor, creditor, amount, what)
            return
        if debtor == current:
            state["debts"].append({"creditor": creditor, "amount": amount, "what": what})
            self._log(state, f"{who(debtor)} cannot cover {money(amount)}"
                             + (f" {what}" if what else "")
                             + (f" to {who(creditor)}" if creditor else "")
                             + f" with {money(state['cash'][debtor])} in cash")
            return
        # Not their turn: raise the money automatically, or go bankrupt to the creditor.
        self._liquidate(state, debtor, amount)
        if state["cash"][debtor] >= amount:
            self._pay(state, debtor, creditor, amount, what)
            return
        self._log(state, f"{who(debtor)} cannot pay {money(amount)}")
        self._bankrupt(state, debtor, creditor)

    def _liquidate(self, state: State, player: str, amount: int) -> None:
        """Sell buildings evenly, then mortgage cheapest-first, until ``amount`` is covered."""
        sold = 0
        while state["cash"][player] < amount:
            candidates = [i for i in self._owned(state, player)
                          if self._can(self._check_sell, state, player, i)]
            if not candidates:
                break
            square = min(candidates, key=lambda i: (house_cost(i), -state["houses"][i], i))
            self._do_sell(state, square)
            sold += 1
        mortgaged = []
        while state["cash"][player] < amount:
            candidates = [i for i in self._owned(state, player)
                          if self._can(self._check_mortgage, state, player, i)]
            if not candidates:
                break
            square = min(candidates, key=lambda i: (SQUARES[i]["price"], i))
            state["mortgaged"][square] = True
            state["cash"][player] += mortgage_value(square)
            mortgaged.append(_name(square))
        if sold or mortgaged:
            parts = []
            if sold:
                parts.append(f"sold {sold} building{'s' if sold > 1 else ''}")
            if mortgaged:
                parts.append("mortgaged " + ", ".join(mortgaged))
            self._log(state, f"{who(player)} automatically " + " and ".join(parts)
                             + " to raise cash")

    def _pay_debt(self, state: State, player: str, action: Action, rng: random.Random) -> None:
        if state["phase"] != "debt" or not state["debts"]:
            raise GameError("You have no debt to pay")
        debt = state["debts"][0]
        short = debt["amount"] - state["cash"][player]
        if short > 0:
            raise GameError(f"You need {money(short)} more: sell buildings or mortgage property")
        while state["debts"] and state["cash"][player] >= state["debts"][0]["amount"]:
            debt = state["debts"].pop(0)
            self._pay(state, player, debt["creditor"], debt["amount"], debt["what"])
        self._after_debts(state)

    def _after_debts(self, state: State) -> None:
        """Continue the turn once every debt is paid (or forgiven)."""
        if state["debts"] or state["result"] is not None:
            return
        player = self._current(state)
        resume = state["resume"]
        state["resume"] = None
        if resume:
            state["jail"].pop(player, None)
            self._walk(state, player, resume["move"])
        self._settle(state)

    def _declare_bankruptcy(self, state: State, player: str, action: Action,
                            rng: random.Random) -> None:
        if state["phase"] != "debt" or not state["debts"]:
            raise GameError("You can only declare bankruptcy when you cannot pay a debt")
        debt = state["debts"][0]
        if state["cash"][player] >= debt["amount"]:
            raise GameError("You have enough cash to pay this debt")
        self._bankrupt(state, player, debt["creditor"])
        self._check_winner(state)
        if state["result"] is None:
            self._next_turn(state)

    def _bankrupt(self, state: State, player: str, creditor: str | None) -> None:
        trade = state["trade"]
        if trade is not None and player in (trade["from"], trade["to"]):
            state["trade"] = None
        proceeds = 0
        squares = self._owned(state, player)
        for i in squares:
            proceeds += state["houses"][i] * house_cost(i) // 2
            state["houses"][i] = 0
        cash = state["cash"][player]
        state["cash"][player] = 0
        if creditor is not None:
            state["cash"][creditor] += cash + proceeds
            for i in squares:
                state["owner"][i] = creditor  # mortgaged property stays mortgaged
            self._log(state, f"{who(player)} went bankrupt to {who(creditor)}, who takes "
                             f"{money(cash + proceeds)} and {len(squares)} "
                             f"propert{'y' if len(squares) == 1 else 'ies'}")
        else:
            for i in squares:
                state["owner"][i] = None
                state["mortgaged"][i] = False
            self._log(state, f"{who(player)} went bankrupt; their properties return to the bank")
        state["jail"].pop(player, None)
        state["bankrupt"].append(player)
        if player == self._current(state):
            state["debts"] = []
            state["offer"] = None
            state["resume"] = None
        elif any(d["creditor"] == player for d in state["debts"]):
            # Debts to a player who is out of the game are forgiven.
            state["debts"] = [d for d in state["debts"] if d["creditor"] != player]
            self._after_debts(state)

    # Buying -------------------------------------------------------------------------------

    def _buy(self, state: State, player: str, action: Action, rng: random.Random) -> None:
        if state["phase"] != "buy" or state["offer"] is None:
            raise GameError("There is nothing to buy")
        square = state["offer"]["square"]
        price = SQUARES[square]["price"]
        if state["cash"][player] < price:
            raise GameError(f"You need {money(price)} to buy {_name(square)}")
        state["cash"][player] -= price
        state["owner"][square] = player
        state["offer"] = None
        self._log(state, f"{who(player)} bought {_name(square)} for {money(price)}")
        self._settle(state)

    def _decline(self, state: State, player: str, action: Action, rng: random.Random) -> None:
        if state["phase"] != "buy" or state["offer"] is None:
            raise GameError("There is nothing to decline")
        square = state["offer"]["square"]
        state["offer"] = None
        self._log(state, f"{who(player)} declined to buy {_name(square)}")
        self._settle(state)

    # Buildings and mortgages ---------------------------------------------------------------

    @staticmethod
    def _can(check: Callable[[State, str, int], None], state: State, player: str,
             square: int) -> bool:
        try:
            check(state, player, square)
        except GameError:
            return False
        return True

    @staticmethod
    def _check_owned(state: State, player: str, square: int) -> None:
        if SQUARES[square]["kind"] not in PROPERTY_KINDS:
            raise GameError(f"{_name(square)} is not a property")
        if state["owner"][square] != player:
            raise GameError(f"You do not own {_name(square)}")

    def _check_build(self, state: State, player: str, square: int) -> None:
        self._check_owned(state, player, square)
        info = SQUARES[square]
        if info["kind"] != "city":
            raise GameError("You can only build on cities")
        group = GROUP_SQUARES[info["group"]]
        name = GROUPS[info["group"]]["name"]
        if any(state["owner"][i] != player for i in group):
            raise GameError(f"Own every {name} city before building")
        if any(state["mortgaged"][i] for i in group):
            raise GameError(f"Unmortgage the {name} group before building")
        houses = state["houses"][square]
        if houses >= HOTEL:
            raise GameError(f"{info['name']} already has a hotel")
        if houses > min(state["houses"][i] for i in group):
            raise GameError(f"Build evenly: add to the other {name} cities first")
        if state["cash"][player] < house_cost(square):
            raise GameError(f"You need {money(house_cost(square))} to build")

    def _check_sell(self, state: State, player: str, square: int) -> None:
        self._check_owned(state, player, square)
        info = SQUARES[square]
        houses = state["houses"][square]
        if info["kind"] != "city" or houses == 0:
            raise GameError(f"{info['name']} has no buildings to sell")
        group = GROUP_SQUARES[info["group"]]
        if houses < max(state["houses"][i] for i in group):
            raise GameError(f"Sell evenly: sell from the other {GROUPS[info['group']]['name']} "
                            f"cities first")

    def _check_mortgage(self, state: State, player: str, square: int) -> None:
        self._check_owned(state, player, square)
        if state["mortgaged"][square]:
            raise GameError(f"{_name(square)} is already mortgaged")
        group = SQUARES[square].get("group")
        if group and any(state["houses"][i] for i in GROUP_SQUARES[group]):
            raise GameError(f"Sell the buildings in the {GROUPS[group]['name']} group first")

    def _check_unmortgage(self, state: State, player: str, square: int) -> None:
        self._check_owned(state, player, square)
        if not state["mortgaged"][square]:
            raise GameError(f"{_name(square)} is not mortgaged")
        if state["cash"][player] < unmortgage_cost(square):
            raise GameError(f"You need {money(unmortgage_cost(square))} to unmortgage")

    @staticmethod
    def _require_phase(state: State, allowed: tuple[str, ...]) -> None:
        if state["phase"] not in allowed:
            raise GameError({"debt": "Settle your debt first: sell buildings or mortgage",
                             "buy": "Buy or decline the property first"}.get(
                                 state["phase"], "You cannot do that now"))

    def _build(self, state: State, player: str, action: Action, rng: random.Random) -> None:
        self._require_phase(state, ("roll", "buy", "end"))
        square = require_int(action, "square", 0, SIZE - 1)
        self._check_build(state, player, square)
        cost = house_cost(square)
        state["cash"][player] -= cost
        state["houses"][square] += 1
        built = "a hotel" if state["houses"][square] == HOTEL else "a house"
        self._log(state, f"{who(player)} built {built} on {_name(square)} for {money(cost)}")

    def _do_sell(self, state: State, square: int) -> int:
        refund = house_cost(square) // 2
        state["houses"][square] -= 1
        state["cash"][state["owner"][square]] += refund
        return refund

    def _sell(self, state: State, player: str, action: Action, rng: random.Random) -> None:
        self._require_phase(state, ("roll", "buy", "end", "debt"))
        square = require_int(action, "square", 0, SIZE - 1)
        self._check_sell(state, player, square)
        sold = "a hotel" if state["houses"][square] == HOTEL else "a house"
        refund = self._do_sell(state, square)
        self._log(state, f"{who(player)} sold {sold} on {_name(square)} for {money(refund)}")

    def _mortgage(self, state: State, player: str, action: Action, rng: random.Random) -> None:
        self._require_phase(state, ("roll", "buy", "end", "debt"))
        square = require_int(action, "square", 0, SIZE - 1)
        self._check_mortgage(state, player, square)
        state["mortgaged"][square] = True
        state["cash"][player] += mortgage_value(square)
        self._log(state, f"{who(player)} mortgaged {_name(square)} for "
                         f"{money(mortgage_value(square))}")

    def _unmortgage(self, state: State, player: str, action: Action, rng: random.Random) -> None:
        self._require_phase(state, ("roll", "buy", "end"))
        square = require_int(action, "square", 0, SIZE - 1)
        self._check_unmortgage(state, player, square)
        state["mortgaged"][square] = False
        state["cash"][player] -= unmortgage_cost(square)
        self._log(state, f"{who(player)} paid {money(unmortgage_cost(square))} to unmortgage "
                         f"{_name(square)}")

    # Trading ------------------------------------------------------------------------------

    @staticmethod
    def _parse_side(raw: Any) -> dict[str, Any]:
        if raw is None:
            raw = {}
        if not isinstance(raw, dict):
            raise GameError("Malformed trade")
        cash = raw.get("cash", 0)
        if cash is None:
            cash = 0
        if not isinstance(cash, int) or isinstance(cash, bool) or cash < 0:
            raise GameError("Trade cash must be a whole number of rupees")
        squares = raw.get("squares", [])
        if squares is None:
            squares = []
        if not isinstance(squares, list) or not all(
                isinstance(s, int) and not isinstance(s, bool) and 0 <= s < SIZE for s in squares):
            raise GameError("Malformed trade")
        if len(set(squares)) != len(squares):
            raise GameError("A property appears twice in the trade")
        return {"cash": cash, "squares": sorted(squares)}

    def _validate_trade(self, state: State, proposer: str, to: str, give: dict[str, Any],
                        get: dict[str, Any]) -> None:
        active = self._active(state)
        if proposer not in active or to not in active:
            raise GameError("Both players must still be in the game")
        if not (give["cash"] or give["squares"] or get["cash"] or get["squares"]):
            raise GameError("The trade is empty")
        for side, owner in ((give, proposer), (get, to)):
            for square in side["squares"]:
                if SQUARES[square]["kind"] not in PROPERTY_KINDS:
                    raise GameError(f"{_name(square)} cannot be traded")
                if state["owner"][square] != owner:
                    holder = "You do" if owner == proposer else "They do"
                    raise GameError(f"{holder} not own {_name(square)}")
                group = SQUARES[square].get("group")
                if group and any(state["houses"][i] for i in GROUP_SQUARES[group]):
                    raise GameError(f"Sell the buildings in the {GROUPS[group]['name']} group "
                                    f"before trading {_name(square)}")
            if state["cash"][owner] < side["cash"]:
                raise GameError(("You do" if owner == proposer else "They do")
                                + f" not have {money(side['cash'])}")

    def _propose_trade(self, state: State, player: str, action: Action,
                       rng: random.Random) -> None:
        if state["phase"] not in ("roll", "end"):
            raise GameError("You can trade before rolling or after your move")
        if state["trade"] is not None:
            raise GameError("A trade is already pending")
        to = action.get("to")
        if not isinstance(to, str) or to not in state["players"] or to == player:
            raise GameError("Choose another player to trade with")
        give = self._parse_side(action.get("give"))
        get = self._parse_side(action.get("get"))
        self._validate_trade(state, player, to, give, get)
        state["trade_seq"] += 1
        state["trade"] = {"id": state["trade_seq"], "from": player, "to": to,
                          "give": give, "get": get}
        self._log(state, f"{who(player)} offered {who(to)} a trade: "
                         f"{self._describe(give)} for {self._describe(get)}")

    @staticmethod
    def _describe(side: dict[str, Any]) -> str:
        parts = [_name(s) for s in side["squares"]]
        if side["cash"]:
            parts.append(money(side["cash"]))
        return " + ".join(parts) if parts else "nothing"

    def _respond_trade(self, state: State, player: str, kind: str) -> None:
        trade = state["trade"]
        if trade is None:
            raise GameError("There is no pending trade")
        if kind == "cancel_trade":
            if trade["from"] != player:
                raise GameError("Only the proposer can cancel this trade")
            state["trade"] = None
            self._log(state, f"{who(player)} cancelled their trade offer")
            return
        if trade["to"] != player:
            raise GameError("This trade was not offered to you")
        if kind == "decline_trade":
            state["trade"] = None
            self._log(state, f"{who(player)} declined the trade from {who(trade['from'])}")
            return
        proposer = trade["from"]
        self._validate_trade(state, proposer, player, trade["give"], trade["get"])
        for square in trade["give"]["squares"]:
            state["owner"][square] = player
        for square in trade["get"]["squares"]:
            state["owner"][square] = proposer
        state["cash"][proposer] += trade["get"]["cash"] - trade["give"]["cash"]
        state["cash"][player] += trade["give"]["cash"] - trade["get"]["cash"]
        state["trade"] = None
        self._log(state, f"{who(player)} accepted the trade from {who(proposer)}")

    # Leaving ---------------------------------------------------------------------------

    def _remove_player(self, state: State, player: str) -> None:
        if player not in state["left"]:
            state["left"].append(player)
        state["moves"] = []
        if player in state["bankrupt"]:
            self._log(state, f"{who(player)} left the game")
            return
        self._log(state, f"{who(player)} left the game (bankrupt)")
        was_current = player == self._current(state)
        self._bankrupt(state, player, None)
        self._check_winner(state)
        if state["result"] is None and was_current:
            self._next_turn(state)

    # -- queries -------------------------------------------------------------------------

    def awaiting(self, state: State) -> list[str]:
        if state["result"] is not None:
            return []
        waiting = [self._current(state)]
        trade = state["trade"]
        if trade is not None and trade["to"] not in waiting:
            waiting.append(trade["to"])
        return waiting

    def outcome(self, state: State) -> Outcome | None:
        result = state["result"]
        if result is None:
            return None
        return Outcome(winners=list(result["winners"]), draw=result["draw"],
                       reason=result["reason"])

    def standings(self, state: State) -> list[Placing]:
        """Players still in by net worth, then bankrupt players, last eliminated first."""
        entries: list[tuple[str, tuple[Any, ...], str]] = []
        winners = set(state["result"]["winners"]) if state["result"] else set()
        for p in self._active(state):
            worth = self.net_worth(state, p)
            entries.append((p, (1, p in winners, worth), f"Net worth {money(worth)}"))
        for order, p in enumerate(state["bankrupt"]):
            detail = "Left the game" if p in state["left"] else "Bankrupt"
            entries.append((p, (0, False, order), detail))
        return rank(entries)

    def _actions(self, state: State, player: str | None) -> list[str]:
        if (player is None or player not in state["players"] or player in state["bankrupt"]
                or state["result"] is not None):
            return []
        actions: list[str] = []
        phase = state["phase"]
        cash = state["cash"][player]
        if player == self._current(state):
            if phase == "roll":
                actions.append("roll")
                if player in state["jail"] and cash >= JAIL_FINE:
                    actions.append("pay_fine")
            elif phase == "buy" and state["offer"] is not None:
                if cash >= SQUARES[state["offer"]["square"]]["price"]:
                    actions.append("buy")
                actions.append("decline")
            elif phase == "end":
                actions.append("end_turn")
            elif phase == "debt" and state["debts"]:
                if cash >= state["debts"][0]["amount"]:
                    actions.append("pay_debt")
                else:
                    actions.append("declare_bankruptcy")
            if phase in ("roll", "end") and state["trade"] is None and len(
                    self._active(state)) > 1:
                actions.append("propose_trade")
        trade = state["trade"]
        if trade is not None:
            if trade["to"] == player:
                actions += ["accept_trade", "decline_trade"]
            if trade["from"] == player:
                actions.append("cancel_trade")
        return actions

    def _manageable(self, state: State, player: str | None) -> dict[str, list[int]]:
        empty: dict[str, list[int]] = {"build": [], "sell": [], "mortgage": [], "unmortgage": []}
        if (player is None or player != self._current(state) or player in state["bankrupt"]
                or state["result"] is not None):
            return empty
        phase = state["phase"]
        owned = self._owned(state, player)
        checks = {"build": (self._check_build, ("roll", "buy", "end")),
                  "sell": (self._check_sell, ("roll", "buy", "end", "debt")),
                  "mortgage": (self._check_mortgage, ("roll", "buy", "end", "debt")),
                  "unmortgage": (self._check_unmortgage, ("roll", "buy", "end"))}
        return {key: [i for i in owned if self._can(check, state, player, i)]
                if phase in phases else [] for key, (check, phases) in checks.items()}

    def view(self, state: State, player: str | None) -> dict[str, Any]:
        current = self._current(state)
        offer = None
        if state["offer"] is not None:
            square = state["offer"]["square"]
            offer = {"square": square, "price": SQUARES[square]["price"],
                     "affordable": state["cash"][current] >= SQUARES[square]["price"]}
        debt = None
        if state["debts"]:
            head = state["debts"][0]
            debt = {"debtor": current, "creditor": head["creditor"], "amount": head["amount"],
                    "what": head["what"], "total": sum(d["amount"] for d in state["debts"]),
                    "short": max(0, head["amount"] - state["cash"][current])}
        ends_in_ms = None
        if state.get("ends_at") is not None:
            ends_in_ms = 0 if state["result"] is not None else max(
                0, int((state["ends_at"] - self.now()) * 1000))
        manage = self._manageable(state, player)
        return {
            "board": BOARD,
            "rules": RULES,
            "players": [{
                "id": p,
                "cash": state["cash"][p],
                "position": state["pos"][p],
                "in_jail": p in state["jail"],
                "jail_attempts": state["jail"].get(p, 0),
                "bankrupt": p in state["bankrupt"],
                "left": p in state["left"],
                "net_worth": self.net_worth(state, p),
                "properties": len(self._owned(state, p)),
            } for p in state["players"]],
            "owners": list(state["owner"]),
            "houses": list(state["houses"]),
            "mortgaged": list(state["mortgaged"]),
            "current": current if state["result"] is None else None,
            "phase": state["phase"] if state["result"] is None else "over",
            "dice": state["dice"],
            "roll_seq": state["roll_seq"],
            "doubles": state["doubles"],
            "again": state["again"],
            "offer": offer,
            "debt": debt,
            "trade": copy.deepcopy(state["trade"]),
            "card": state["card"],
            "moves": state["moves"],
            "actions": self._actions(state, player),
            "can_build": manage["build"],
            "can_sell": manage["sell"],
            "can_mortgage": manage["mortgage"],
            "can_unmortgage": manage["unmortgage"],
            "duration": state.get("duration"),
            "ends_in_ms": ends_in_ms,
            "result": state["result"],
            "log": state["log"],
        }
