"""Business: buying, rent, building, mortgages, jail, cards, debt, trades, clock, leaving."""

from __future__ import annotations

import json
import random
from typing import Any

import pytest

from app.games import registry
from app.games.base import GameError
from app.games.business import BusinessEngine
from app.games.business_board import CARDS, GROUP_SQUARES, SQUARES, money, square_index
from tests.games.helpers import Dice, act, rejects

AGRA, FUND, VARANASI, TAX, RAIL = 1, 2, 3, 4, 5
JAIPUR, JODHPUR, UDAIPUR, JAIL = 6, 7, 8, 9
BHOPAL, ELECTRIC, INDORE, NAGPUR, AIR = 10, 11, 12, 13, 14
CHANDIGARH, CHANCE1, WATER_WORKS = 17, 20, 30
GO_TO_JAIL, CHANCE2, DELHI, MUMBAI = 27, 33, 34, 35
TRANSPORTS = [5, 14, 23, 32]


class FakeTime:
    def __init__(self) -> None:
        self.now = 1_000_000.0

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def t() -> FakeTime:
    return FakeTime()


@pytest.fixture
def e(t: FakeTime) -> BusinessEngine:
    return BusinessEngine(clock=t)


def game(e: BusinessEngine, players: str = "ab", **options: Any) -> dict:
    return e.start(list(players), random.Random(1), options or None)


def roll(e: BusinessEngine, s: dict, p: str, d1: int, d2: int) -> dict:
    return act(e, s, p, Dice(d1, d2), type="roll")


def own(s: dict, player: str | None, *squares: int, houses: int = 0) -> None:
    for sq in squares:
        s["owner"][sq] = player
        s["houses"][sq] = houses


def stack(s: dict, deck: str, kind: str, text: str = "") -> dict:
    """Put the first card of ``kind`` (containing ``text``) on top of ``deck``."""
    index = next(i for i, c in enumerate(CARDS[deck]) if c["kind"] == kind and text in c["text"])
    order = s["decks"][deck]
    top = s["deck_pos"][deck]
    at = order.index(index)
    order[top], order[at] = order[at], order[top]
    return CARDS[deck][index]


def at(s: dict, player: str, square: int) -> None:
    s["pos"][player] = square


# -- api strategy used by the API integration test ---------------------------------------

def api_move(view: dict[str, Any]) -> dict[str, Any] | None:
    """Simple strategy: roll, buy if affordable, end turn, settle debts or go bankrupt."""
    actions = view.get("actions") or []
    if "decline_trade" in actions:
        return {"type": "decline_trade"}
    if view.get("phase") == "debt" and view.get("current") == view.get("you"):
        if "pay_debt" in actions:
            return {"type": "pay_debt"}
        if view["can_sell"]:
            return {"type": "sell", "square": view["can_sell"][0]}
        if view["can_mortgage"]:
            return {"type": "mortgage", "square": view["can_mortgage"][0]}
        return {"type": "declare_bankruptcy"}
    for kind in ("buy", "decline", "roll", "end_turn"):
        if kind in actions:
            return {"type": kind}
    return None


# -- board -----------------------------------------------------------------------------

def test_board_layout(e: BusinessEngine) -> None:
    kinds = [s["kind"] for s in SQUARES]
    assert len(SQUARES) == 36
    assert [kinds[i] for i in (0, 9, 18, 27)] == ["start", "jail", "rest", "go_to_jail"]
    assert kinds.count("city") == 22 and len(GROUP_SQUARES) == 8
    assert all(2 <= len(g) <= 3 for g in GROUP_SQUARES.values())
    assert kinds.count("transport") == 4 and kinds.count("utility") == 2
    assert kinds.count("chance") == 2 and kinds.count("fund") == 1 and kinds.count("tax") == 1
    prices = [s["price"] for s in SQUARES if s["kind"] == "city"]
    assert prices == sorted(prices) and prices[0] == 600 and prices[-1] == 4000
    assert len(CARDS["chance"]) == 12 and len(CARDS["fund"]) == 12
    view = e.view(game(e), "a")
    assert len(view["board"]) == 36
    mumbai = view["board"][MUMBAI]
    assert mumbai["name"] == "Mumbai" and mumbai["rents"][5] == 20_000
    assert mumbai["house_cost"] == 2000 and mumbai["mortgage"] == 2000
    assert mumbai["unmortgage"] == 2200


def test_money_uses_indian_grouping() -> None:
    assert money(500) == "₹500"
    assert money(2_000) == "₹2,000"
    assert money(12_340) == "₹12,340"
    assert money(123_456) == "₹1,23,456"
    assert money(12_345_678) == "₹1,23,45,678"


def test_new_game(e: BusinessEngine) -> None:
    s = game(e, "abc")
    view = e.view(s, "a")
    assert [p["cash"] for p in view["players"]] == [15_000] * 3
    assert all(p["position"] == 0 for p in view["players"])
    assert view["current"] == "a" and view["phase"] == "roll"
    assert view["actions"] == ["roll", "propose_trade"]
    assert e.view(s, "b")["actions"] == []
    assert e.awaiting(s) == ["a"]


# -- buying -----------------------------------------------------------------------------

def test_buy_property(e: BusinessEngine) -> None:
    s = roll(e, game(e), "a", 1, 2)
    view = e.view(s, "a")
    assert view["phase"] == "buy" and view["offer"] == {"square": VARANASI, "price": 600,
                                                       "affordable": True}
    assert "buy" in view["actions"] and "decline" in view["actions"]
    rejects(e, s, "a", "Buy or decline", type="end_turn")
    rejects(e, s, "a", "Buy or decline", type="roll")
    s = act(e, s, "a", type="buy")
    assert s["owner"][VARANASI] == "a" and s["cash"]["a"] == 14_400
    assert s["phase"] == "end"
    assert "{{a}} bought Varanasi for ₹600" in s["log"]
    s = act(e, s, "a", type="end_turn")
    assert s["players"][s["current"]] == "b" and s["phase"] == "roll"


def test_decline_property(e: BusinessEngine) -> None:
    s = act(e, roll(e, game(e), "a", 1, 2), "a", type="decline")
    assert s["owner"][VARANASI] is None and s["cash"]["a"] == 15_000 and s["phase"] == "end"
    assert "{{a}} declined to buy Varanasi" in s["log"]


def test_buy_needs_cash(e: BusinessEngine) -> None:
    s = game(e)
    s["cash"]["a"] = 100
    s = roll(e, s, "a", 1, 2)
    assert e.view(s, "a")["offer"]["affordable"] is False
    assert "buy" not in e.view(s, "a")["actions"]
    rejects(e, s, "a", "You need ₹600", type="buy")
    assert act(e, s, "a", type="decline")["phase"] == "end"


def test_turn_rules(e: BusinessEngine) -> None:
    s = game(e)
    rejects(e, s, "b", "not your turn", type="roll")
    rejects(e, s, "a", "Roll the dice first", type="end_turn")
    rejects(e, s, "a", "nothing to buy", type="buy")
    rejects(e, s, "a", "Unknown action", type="fly")
    s = act(e, roll(e, s, "a", 1, 2), "a", type="decline")
    rejects(e, s, "a", "already rolled", type="roll")


# -- rent -------------------------------------------------------------------------------

def test_city_rent_and_doubled_group_rent(e: BusinessEngine) -> None:
    s = game(e)
    own(s, "b", VARANASI)
    s1 = roll(e, s, "a", 1, 2)
    assert s1["cash"]["a"] == 15_000 - 40 and s1["cash"]["b"] == 15_040
    assert "{{a}} paid ₹40 rent to {{b}}" in s1["log"]
    assert s1["phase"] == "end"
    own(s, "b", AGRA)
    s2 = roll(e, s, "a", 1, 2)
    assert s2["cash"]["b"] == 15_080  # whole brown group, no buildings: doubled


def test_house_and_hotel_rent(e: BusinessEngine) -> None:
    rents = SQUARES[VARANASI]["rents"]
    for houses in range(1, 6):
        s = game(e)
        own(s, "b", AGRA, VARANASI, houses=houses)
        s = roll(e, s, "a", 1, 2)
        assert s["cash"]["b"] == 15_000 + rents[houses]
    assert rents[5] == 4_500


def test_transport_rent(e: BusinessEngine) -> None:
    for count, rent in [(1, 250), (2, 500), (3, 1_000), (4, 2_000)]:
        s = game(e)
        own(s, "b", *TRANSPORTS[:count])
        s = roll(e, s, "a", 2, 3)
        assert s["cash"]["b"] == 15_000 + rent


def test_utility_rent(e: BusinessEngine) -> None:
    s = game(e)
    own(s, "b", ELECTRIC)
    one = roll(e, s, "a", 5, 6)
    assert one["cash"]["b"] == 15_000 + 4 * 11
    own(s, "b", WATER_WORKS)
    both = roll(e, s, "a", 5, 6)
    assert both["cash"]["b"] == 15_000 + 10 * 11


def test_no_rent_on_mortgaged_or_own_property(e: BusinessEngine) -> None:
    s = game(e)
    own(s, "b", VARANASI)
    s["mortgaged"][VARANASI] = True
    s1 = roll(e, s, "a", 1, 2)
    assert s1["cash"] == {"a": 15_000, "b": 15_000} and s1["phase"] == "end"
    own(s, "a", VARANASI)
    s["mortgaged"][VARANASI] = False
    s2 = roll(e, s, "a", 1, 2)
    assert s2["cash"] == {"a": 15_000, "b": 15_000}


def test_income_tax(e: BusinessEngine) -> None:
    s = roll(e, game(e), "a", 1, 3)
    assert s["cash"]["a"] == 13_000 and "{{a}} paid ₹2,000 Income Tax" in s["log"]


# -- building ---------------------------------------------------------------------------

def test_build_evenly(e: BusinessEngine) -> None:
    s = game(e)
    own(s, "a", AGRA, VARANASI)
    assert e.view(s, "a")["can_build"] == [AGRA, VARANASI]
    s = act(e, s, "a", type="build", square=AGRA)
    assert s["houses"][AGRA] == 1 and s["cash"]["a"] == 14_500
    assert e.view(s, "a")["can_build"] == [VARANASI]
    rejects(e, s, "a", "Build evenly", type="build", square=AGRA)
    for _ in range(3):
        s = act(e, s, "a", type="build", square=VARANASI)
        s = act(e, s, "a", type="build", square=AGRA)
    s = act(e, s, "a", type="build", square=VARANASI)
    assert s["houses"][AGRA] == 4 and s["houses"][VARANASI] == 4
    s = act(e, s, "a", type="build", square=AGRA)
    assert s["houses"][AGRA] == 5 and "{{a}} built a hotel on Agra for ₹500" in s["log"]
    rejects(e, s, "a", "already has a hotel", type="build", square=AGRA)
    s = act(e, s, "a", type="build", square=VARANASI)
    assert e.view(s, "a")["can_build"] == []


def test_build_rules(e: BusinessEngine) -> None:
    s = game(e)
    own(s, "a", AGRA)
    rejects(e, s, "a", "Own every Brown city", type="build", square=AGRA)
    rejects(e, s, "a", "You do not own Varanasi", type="build", square=VARANASI)
    rejects(e, s, "a", "not a property", type="build", square=FUND)
    own(s, "a", VARANASI, RAIL)
    rejects(e, s, "a", "only build on cities", type="build", square=RAIL)
    rejects(e, s, "b", "not your turn", type="build", square=AGRA)
    rejects(e, s, "a", "must be an integer", type="build", square="1")
    s["mortgaged"][VARANASI] = True
    rejects(e, s, "a", "Unmortgage the Brown group", type="build", square=AGRA)
    s["mortgaged"][VARANASI] = False
    s["cash"]["a"] = 499
    rejects(e, s, "a", "You need ₹500 to build", type="build", square=AGRA)
    s["cash"]["a"] = 15_000
    # Building is allowed before rolling and after moving.
    s = act(e, s, "a", type="build", square=AGRA)
    s = roll(e, s, "a", 3, 4)  # Jodhpur: offer
    s = act(e, s, "a", type="decline")
    s = act(e, s, "a", type="build", square=VARANASI)
    assert s["houses"][AGRA] == s["houses"][VARANASI] == 1


def test_sell_evenly(e: BusinessEngine) -> None:
    s = game(e)
    own(s, "a", AGRA, VARANASI, houses=5)
    s = act(e, s, "a", type="sell", square=AGRA)
    assert s["houses"][AGRA] == 4 and s["cash"]["a"] == 15_250
    assert "{{a}} sold a hotel on Agra for ₹250" in s["log"]
    rejects(e, s, "a", "Sell evenly", type="sell", square=AGRA)
    assert e.view(s, "a")["can_sell"] == [VARANASI]
    s = act(e, s, "a", type="sell", square=VARANASI)
    s = act(e, s, "a", type="sell", square=AGRA)
    assert s["houses"][AGRA] == 3 and s["houses"][VARANASI] == 4
    own(s, "a", RAIL)
    rejects(e, s, "a", "no buildings", type="sell", square=RAIL)


# -- mortgages --------------------------------------------------------------------------

def test_mortgage_and_unmortgage(e: BusinessEngine) -> None:
    s = game(e)
    own(s, "a", MUMBAI, RAIL)
    s = act(e, s, "a", type="mortgage", square=MUMBAI)
    assert s["mortgaged"][MUMBAI] and s["cash"]["a"] == 17_000
    assert "{{a}} mortgaged Mumbai for ₹2,000" in s["log"]
    rejects(e, s, "a", "already mortgaged", type="mortgage", square=MUMBAI)
    rejects(e, s, "a", "not mortgaged", type="unmortgage", square=RAIL)
    assert e.view(s, "a")["can_unmortgage"] == [MUMBAI]
    s = act(e, s, "a", type="unmortgage", square=MUMBAI)
    assert not s["mortgaged"][MUMBAI] and s["cash"]["a"] == 17_000 - 2_200
    s = act(e, s, "a", type="mortgage", square=MUMBAI)
    s["cash"]["a"] = 2_199
    rejects(e, s, "a", "You need ₹2,200", type="unmortgage", square=MUMBAI)
    rejects(e, s, "a", "do not own", type="mortgage", square=DELHI)


def test_no_mortgage_with_buildings_in_group(e: BusinessEngine) -> None:
    s = game(e)
    own(s, "a", AGRA, VARANASI)
    s["houses"][AGRA] = 1
    rejects(e, s, "a", "Sell the buildings in the Brown group", type="mortgage", square=VARANASI)
    s = act(e, s, "a", type="sell", square=AGRA)
    s = act(e, s, "a", type="mortgage", square=VARANASI)
    rejects(e, s, "a", "Unmortgage the Brown group", type="build", square=AGRA)


# -- jail and doubles -------------------------------------------------------------------

def test_go_to_jail_square(e: BusinessEngine) -> None:
    s = game(e)
    at(s, "a", 22)
    s = roll(e, s, "a", 2, 3)
    assert s["pos"]["a"] == JAIL and "a" in s["jail"] and s["phase"] == "end"
    assert s["cash"]["a"] == 15_000  # never passes Start
    assert s["moves"][-1] == {"player": "a", "from": GO_TO_JAIL, "to": JAIL, "walk": False}
    # A double that lands on Go to Jail does not roll again.
    s = game(e)
    at(s, "a", 23)
    s = roll(e, s, "a", 2, 2)
    assert s["pos"]["a"] == JAIL and s["phase"] == "end"


def test_doubles_roll_again(e: BusinessEngine) -> None:
    s = roll(e, game(e), "a", 3, 3)
    assert s["pos"]["a"] == JAIPUR and s["phase"] == "buy"
    s = act(e, s, "a", type="buy")
    assert s["phase"] == "roll" and s["doubles"] == 1
    assert "end_turn" not in e.view(s, "a")["actions"]
    s = act(e, roll(e, s, "a", 1, 3), "a", type="decline")
    assert s["pos"]["a"] == BHOPAL
    assert s["phase"] == "end" and s["doubles"] == 0 and "a" not in s["jail"]


def test_three_doubles_go_to_jail(e: BusinessEngine) -> None:
    s = game(e)
    s = act(e, roll(e, s, "a", 3, 3), "a", type="decline")       # Jaipur
    s = act(e, roll(e, s, "a", 2, 2), "a", type="decline")       # Bhopal
    assert s["phase"] == "roll" and s["doubles"] == 2
    s = roll(e, s, "a", 4, 4)
    assert s["pos"]["a"] == JAIL and "a" in s["jail"] and s["phase"] == "end"
    assert "{{a}} rolled a third double in a row and was sent to Jail" in s["log"]


def test_jail_pay_fine_then_roll_normally(e: BusinessEngine) -> None:
    s = game(e)
    at(s, "a", JAIL)
    s["jail"]["a"] = 0
    assert "pay_fine" in e.view(s, "a")["actions"]
    rejects(e, s, "b", "not your turn", type="pay_fine")
    s = act(e, s, "a", type="pay_fine")
    assert "a" not in s["jail"] and s["cash"]["a"] == 14_500 and s["phase"] == "roll"
    s = roll(e, s, "a", 3, 3)  # a normal double: Lucknow, then roll again
    assert s["pos"]["a"] == 15
    assert act(e, s, "a", type="decline")["phase"] == "roll"
    rejects(e, s, "a", "not in Jail", type="pay_fine")


def test_jail_doubles_leave_without_extra_roll(e: BusinessEngine) -> None:
    s = game(e)
    at(s, "a", JAIL)
    s["jail"]["a"] = 1
    s = roll(e, s, "a", 3, 3)
    assert "a" not in s["jail"] and s["pos"]["a"] == 15
    s = act(e, s, "a", type="decline")
    assert s["phase"] == "end"


def test_jail_three_attempts(e: BusinessEngine) -> None:
    s = game(e)
    at(s, "a", JAIL)
    s["jail"]["a"] = 0
    s = roll(e, s, "a", 1, 2)
    assert s["jail"]["a"] == 1 and s["pos"]["a"] == JAIL and s["phase"] == "end"
    rejects(e, s, "a", "Pay the fine before you roll", type="pay_fine")
    s = act(e, s, "a", type="end_turn")
    s = act(e, roll(e, s, "b", 1, 2), "b", type="decline")
    s = act(e, s, "b", type="end_turn")
    s = roll(e, s, "a", 1, 2)
    assert s["jail"]["a"] == 2 and s["pos"]["a"] == JAIL
    s = act(e, s, "a", type="end_turn")
    s = act(e, roll(e, s, "b", 2, 4), "b", type="end_turn")  # b visits Jail
    s = roll(e, s, "a", 1, 2)  # third failure: pay ₹500 and move 3
    assert "a" not in s["jail"] and s["cash"]["a"] == 14_500 and s["pos"]["a"] == INDORE
    assert s["phase"] == "buy"


def test_jail_third_attempt_without_cash_opens_debt(e: BusinessEngine) -> None:
    s = game(e)
    at(s, "a", JAIL)
    s["jail"]["a"] = 2
    s["cash"]["a"] = 100
    own(s, "a", RAIL)
    s = roll(e, s, "a", 1, 2)
    view = e.view(s, "a")
    assert view["phase"] == "debt" and view["debt"]["amount"] == 500
    assert view["debt"]["creditor"] is None and view["debt"]["short"] == 400
    assert view["actions"] == ["declare_bankruptcy"] and view["can_mortgage"] == [RAIL]
    rejects(e, s, "a", "You need ₹400 more", type="pay_debt")
    rejects(e, s, "a", "Settle your debt", type="end_turn")
    s = act(e, s, "a", type="mortgage", square=RAIL)
    s = act(e, s, "a", type="pay_debt")
    assert "a" not in s["jail"] and s["pos"]["a"] == INDORE and s["cash"]["a"] == 600
    assert s["phase"] == "buy"


def test_passing_and_landing_on_start(e: BusinessEngine) -> None:
    s = game(e)
    at(s, "a", DELHI)
    s = roll(e, s, "a", 1, 2)
    assert s["pos"]["a"] == AGRA and s["cash"]["a"] == 17_000
    assert "{{a}} collected ₹2,000 salary at Start" in s["log"]
    s = game(e)
    at(s, "a", 33)
    s = roll(e, s, "a", 1, 2)
    assert s["pos"]["a"] == 0 and s["cash"]["a"] == 17_000 and s["phase"] == "end"


# -- cards ------------------------------------------------------------------------------

def draw_chance(e: BusinessEngine, s: dict, kind: str, text: str = "", square: int = CHANCE1,
                player: str = "a") -> dict:
    stack(s, "chance", kind, text)
    at(s, player, square - 5)
    return roll(e, s, player, 2, 3)


def test_card_collect_and_pay(e: BusinessEngine) -> None:
    s = draw_chance(e, game(e), "collect", "dividend")
    assert s["cash"]["a"] == 15_500 and s["card"]["text"].startswith("Your mutual fund")
    assert s["card"]["player"] == "a" and s["card"]["deck"] == "chance"
    s = draw_chance(e, game(e), "pay", "challan")
    assert s["cash"]["a"] == 14_850 and "{{a}} paid ₹150 to the bank" in s["log"]


def test_card_community_fund(e: BusinessEngine) -> None:
    s = game(e)
    stack(s, "fund", "collect", "refund")
    s = roll(e, s, "a", 1, 1)
    assert s["pos"]["a"] == FUND and s["cash"]["a"] == 16_000
    assert s["card"]["title"] == "Community Fund" and s["phase"] == "roll"


def test_card_advance(e: BusinessEngine) -> None:
    s = draw_chance(e, game(e), "advance", "Start")
    assert s["pos"]["a"] == 0 and s["cash"]["a"] == 17_000
    s = draw_chance(e, game(e), "advance", "Delhi")
    assert s["pos"]["a"] == DELHI and s["cash"]["a"] == 15_000 and s["phase"] == "buy"
    assert s["moves"] == [{"player": "a", "from": 15, "to": CHANCE1, "walk": True},
                          {"player": "a", "from": CHANCE1, "to": DELHI, "walk": False}]
    s = draw_chance(e, game(e), "advance", "Goa", square=CHANCE2)  # passes Start
    assert s["pos"]["a"] == 19 and s["cash"]["a"] == 17_000
    t = game(e)
    own(t, "b", 19)
    t = draw_chance(e, t, "advance", "Goa")  # pays rent where it lands
    assert t["cash"]["b"] == 15_000 + 180


def test_card_back_three(e: BusinessEngine) -> None:
    s = draw_chance(e, game(e), "back")
    assert s["pos"]["a"] == CHANDIGARH and s["phase"] == "buy" and s["cash"]["a"] == 15_000
    t = game(e)
    own(t, "b", WATER_WORKS)
    t = draw_chance(e, t, "back", square=CHANCE2)  # utility rent uses the dice roll (5)
    assert t["pos"]["a"] == WATER_WORKS and t["cash"]["b"] == 15_000 + 4 * 5


def test_card_go_to_jail(e: BusinessEngine) -> None:
    s = game(e)
    stack(s, "chance", "jail")
    at(s, "a", 16)
    s = roll(e, s, "a", 2, 2)  # a double, but jail ends the turn
    assert s["pos"]["a"] == JAIL and "a" in s["jail"] and s["phase"] == "end"
    assert s["cash"]["a"] == 15_000


def test_card_repairs(e: BusinessEngine) -> None:
    s = game(e)
    own(s, "a", AGRA, VARANASI, houses=1)
    own(s, "a", MUMBAI, houses=5)
    s = draw_chance(e, s, "repairs")
    assert s["cash"]["a"] == 15_000 - (2 * 250 + 1_000)
    t = draw_chance(e, game(e), "repairs")
    assert t["cash"]["a"] == 15_000 and "{{a}} paid nothing (no buildings)" in t["log"]


def test_card_collect_from_each_and_pay_each(e: BusinessEngine) -> None:
    s = game(e, "abc")
    stack(s, "fund", "collect_each")
    s = roll(e, s, "a", 1, 1)
    assert s["cash"] == {"a": 15_500, "b": 14_750, "c": 14_750}
    s = draw_chance(e, game(e, "abc"), "pay_each")
    assert s["cash"] == {"a": 14_000, "b": 15_500, "c": 15_500}
    assert "{{a}} paid ₹500 to {{b}}" in s["log"]


def test_deck_cycles(e: BusinessEngine) -> None:
    s = game(e)
    order = s["decks"]["chance"]
    texts = []
    for _ in range(13):
        at(s, "a", 15)
        s["phase"], s["again"] = "roll", False
        s = roll(e, s, "a", 2, 3)
        texts.append(s["card"]["text"])
        s["debts"], s["offer"], s["jail"] = [], None, {}
    assert texts[:12] == [CARDS["chance"][i]["text"] for i in order]
    assert len(set(texts[:12])) == 12 and texts[12] == texts[0]


# -- debt and bankruptcy ----------------------------------------------------------------

def test_debt_flow_and_bankruptcy_to_player(e: BusinessEngine) -> None:
    s = game(e, "abc")
    own(s, "b", DELHI, MUMBAI, houses=5)
    own(s, "a", AGRA, VARANASI, houses=2)
    own(s, "a", RAIL)
    s["mortgaged"][RAIL] = True
    s["cash"]["a"] = 1_000
    at(s, "a", 30)
    s = roll(e, s, "a", 2, 3)
    view = e.view(s, "a")
    assert view["phase"] == "debt" and view["debt"]["creditor"] == "b"
    assert view["debt"]["amount"] == 20_000 and view["actions"] == ["declare_bankruptcy"]
    assert view["can_sell"] == [AGRA, VARANASI] and view["can_build"] == []
    rejects(e, s, "a", "Settle your debt", type="build", square=AGRA)
    rejects(e, s, "a", "trade before rolling", type="propose_trade", to="b",
            give={"cash": 1}, get={})
    s = act(e, s, "a", type="sell", square=AGRA)
    assert s["cash"]["a"] == 1_250
    s = act(e, s, "a", type="declare_bankruptcy")
    # Remaining buildings sold at half (3 x ₹250) and all cash go to the creditor.
    assert s["cash"]["b"] == 15_000 + 1_250 + 750 and s["cash"]["a"] == 0
    assert s["owner"][AGRA] == s["owner"][RAIL] == "b" and s["mortgaged"][RAIL]
    assert s["houses"][AGRA] == s["houses"][VARANASI] == 0
    assert s["bankrupt"] == ["a"] and s["players"][s["current"]] == "b"
    assert e.outcome(s) is None
    rejects(e, s, "a", "bankrupt", type="roll")


def test_pay_debt_after_raising_cash(e: BusinessEngine) -> None:
    s = game(e)
    own(s, "b", VARANASI, houses=0)
    own(s, "b", AGRA)
    s["houses"][VARANASI] = 3  # rent 1,800 (built unevenly for the test)
    own(s, "a", MUMBAI)
    s["cash"]["a"] = 300
    s = roll(e, s, "a", 1, 2)
    rejects(e, s, "a", "You need ₹1,500 more", type="pay_debt")
    s = act(e, s, "a", type="mortgage", square=MUMBAI)
    rejects(e, s, "a", "enough cash", type="declare_bankruptcy")
    s = act(e, s, "a", type="pay_debt")
    assert s["cash"]["a"] == 500 and s["cash"]["b"] == 16_800 and s["phase"] == "end"


def test_bankruptcy_to_bank(e: BusinessEngine) -> None:
    s = game(e, "abc")
    own(s, "a", AGRA, VARANASI, houses=1)
    own(s, "a", RAIL)
    s["mortgaged"][RAIL] = True
    s["cash"]["a"] = 0
    s["houses"][AGRA] = s["houses"][VARANASI] = 0
    s["mortgaged"][AGRA] = s["mortgaged"][VARANASI] = True
    s = roll(e, s, "a", 1, 3)  # Income Tax ₹2,000
    assert s["phase"] == "debt" and e.view(s, "a")["debt"]["creditor"] is None
    s = act(e, s, "a", type="declare_bankruptcy")
    assert all(s["owner"][i] is None and not s["mortgaged"][i] for i in (AGRA, VARANASI, RAIL))
    assert s["players"][s["current"]] == "b" and e.outcome(s) is None
    assert "{{a}} went bankrupt; their properties return to the bank" in s["log"]


def test_last_player_standing_wins(e: BusinessEngine) -> None:
    s = game(e)
    s["cash"]["a"] = 0
    s = act(e, roll(e, s, "a", 1, 3), "a", type="declare_bankruptcy")
    assert e.outcome(s).winners == ["b"] and e.outcome(s).reason == "Last player standing"
    assert e.awaiting(s) == [] and e.view(s, "b")["phase"] == "over"
    rejects(e, s, "b", "over", type="roll")


def test_bystander_liquidated_automatically(e: BusinessEngine) -> None:
    s = game(e, "abcd")
    own(s, "b", AGRA, VARANASI, houses=1)
    s["cash"]["b"] = 100
    own(s, "c", MUMBAI, BHOPAL)
    s["cash"]["c"] = 0
    own(s, "d", RAIL)
    s["mortgaged"][RAIL] = True
    s["cash"]["d"] = 50
    stack(s, "fund", "collect_each")
    s = roll(e, s, "a", 1, 1)
    # b sold one house (+₹250) and paid.
    assert s["cash"]["b"] == 100 and sum(s["houses"][i] for i in (AGRA, VARANASI)) == 1
    # c mortgaged the cheapest property only.
    assert s["mortgaged"][BHOPAL] and not s["mortgaged"][MUMBAI] and s["cash"]["c"] == 450
    # d has nothing left to raise money with: bankrupt to a.
    assert "d" in s["bankrupt"] and s["owner"][RAIL] == "a" and s["mortgaged"][RAIL]
    assert s["cash"]["a"] == 15_000 + 250 + 250 + 50
    assert any("{{b}} automatically sold 1 building" in m for m in s["log"])
    assert any("{{c}} automatically mortgaged Bhopal" in m for m in s["log"])
    assert "{{d}} went bankrupt to {{a}}" in " ".join(s["log"])
    assert s["phase"] == "roll"


def test_pay_each_queues_debts(e: BusinessEngine) -> None:
    s = game(e, "abc")
    s["cash"]["a"] = 600
    own(s, "a", MUMBAI)
    s = draw_chance(e, s, "pay_each")
    assert s["cash"] == {"a": 100, "b": 15_500, "c": 15_000}
    view = e.view(s, "a")
    assert view["debt"]["creditor"] == "c" and view["debt"]["total"] == 500
    s = act(e, act(e, s, "a", type="mortgage", square=MUMBAI), "a", type="pay_debt")
    assert s["cash"] == {"a": 1_600, "b": 15_500, "c": 15_500} and s["phase"] == "end"


# -- trades -----------------------------------------------------------------------------

def trade(**kw: Any) -> dict[str, Any]:
    return {"to": "b", "give": {"cash": 0, "squares": []}, "get": {"cash": 0, "squares": []},
            **kw}


def test_trade_accept(e: BusinessEngine) -> None:
    s = game(e, "abc")
    own(s, "a", AGRA, RAIL)
    s["mortgaged"][RAIL] = True
    own(s, "b", VARANASI)
    s = act(e, s, "a", type="propose_trade", **trade(
        give={"cash": 500, "squares": [AGRA, RAIL]}, get={"cash": 0, "squares": [VARANASI]}))
    assert e.awaiting(s) == ["a", "b"]
    assert e.view(s, "b")["actions"] == ["accept_trade", "decline_trade"]
    assert "cancel_trade" in e.view(s, "a")["actions"]
    rejects(e, s, "c", "not offered to you", type="accept_trade")
    rejects(e, s, "a", "already pending", type="propose_trade", **trade(give={"cash": 1}))
    s = act(e, s, "b", type="accept_trade")
    assert s["owner"][AGRA] == s["owner"][RAIL] == "b" and s["owner"][VARANASI] == "a"
    assert s["mortgaged"][RAIL]  # transfers as mortgaged
    assert s["cash"]["a"] == 14_500 and s["cash"]["b"] == 15_500 and s["trade"] is None
    assert "{{b}} accepted the trade from {{a}}" in s["log"]


def test_trade_validation(e: BusinessEngine) -> None:
    s = game(e, "abc")
    own(s, "a", AGRA, VARANASI, houses=1)
    own(s, "b", MUMBAI)
    rejects(e, s, "a", "empty", type="propose_trade", **trade())
    rejects(e, s, "a", "another player", type="propose_trade", **trade(to="a", give={"cash": 1}))
    rejects(e, s, "a", "another player", type="propose_trade", **trade(to="z", give={"cash": 1}))
    rejects(e, s, "a", "You do not own Delhi", type="propose_trade",
            **trade(give={"squares": [DELHI]}))
    rejects(e, s, "a", "They do not own Agra", type="propose_trade",
            **trade(get={"squares": [AGRA]}))
    rejects(e, s, "a", "Sell the buildings in the Brown group", type="propose_trade",
            **trade(give={"squares": [AGRA]}))
    rejects(e, s, "a", "cannot be traded", type="propose_trade", **trade(give={"squares": [0]}))
    rejects(e, s, "a", "You do not have ₹20,000", type="propose_trade",
            **trade(give={"cash": 20_000}))
    rejects(e, s, "a", "They do not have ₹20,000", type="propose_trade",
            **trade(get={"cash": 20_000}))
    rejects(e, s, "a", "whole number", type="propose_trade", **trade(give={"cash": -5}))
    rejects(e, s, "a", "whole number", type="propose_trade", **trade(give={"cash": True}))
    rejects(e, s, "a", "twice", type="propose_trade",
            **trade(get={"squares": [MUMBAI, MUMBAI]}))
    rejects(e, s, "a", "Malformed", type="propose_trade", **trade(give="all"))
    rejects(e, s, "b", "not your turn", type="propose_trade", **trade(to="a", give={"cash": 1}))
    s["bankrupt"].append("c")
    rejects(e, s, "a", "still be in the game", type="propose_trade",
            **trade(to="c", give={"cash": 1}))
    buy_phase = roll(e, game(e), "a", 1, 2)
    rejects(e, buy_phase, "a", "trade before rolling or after", type="propose_trade",
            **trade(give={"cash": 1}))


def test_trade_decline_cancel_and_expiry(e: BusinessEngine) -> None:
    s = game(e)
    own(s, "b", MUMBAI)
    s = act(e, s, "a", type="propose_trade", **trade(give={"cash": 5_000},
                                                     get={"squares": [MUMBAI]}))
    rejects(e, s, "b", "Only the proposer", type="cancel_trade")
    declined = act(e, s, "b", type="decline_trade")
    assert declined["trade"] is None and declined["owner"][MUMBAI] == "b"
    cancelled = act(e, s, "a", type="cancel_trade")
    assert cancelled["trade"] is None
    rejects(e, cancelled, "b", "no pending trade", type="accept_trade")
    s = act(e, act(e, roll(e, s, "a", 1, 2), "a", type="decline"), "a", type="end_turn")
    assert s["trade"] is None and "The trade offer from {{a}} expired" in s["log"]


def test_trade_revalidated_on_accept(e: BusinessEngine) -> None:
    s = game(e)
    own(s, "a", AGRA, VARANASI)
    own(s, "b", MUMBAI)
    s = act(e, s, "a", type="propose_trade", **trade(give={"cash": 14_000, "squares": [AGRA]},
                                                     get={"squares": [MUMBAI]}))
    built = act(e, s, "a", type="build", square=VARANASI)
    rejects(e, built, "b", "Sell the buildings", type="accept_trade")
    s["cash"]["a"] = 1_000  # spent in the meantime
    rejects(e, s, "b", "You do not have ₹14,000", type="accept_trade")
    s["cash"]["a"] = 15_000
    s["owner"][MUMBAI] = None
    rejects(e, s, "b", "They do not own Mumbai", type="accept_trade")


# -- clock and standings ----------------------------------------------------------------

def test_options(e: BusinessEngine) -> None:
    for minutes in (30, 45, 60, 90):
        assert e.validate_options({"duration": minutes}) == {"duration": minutes}
        assert e.options_label({"duration": minutes}) == f"{minutes} min game"
    assert e.validate_options(None) == {} and e.validate_options({"duration": None}) == {}
    assert e.validate_options({"duration": "60"}) == {"duration": 60}
    assert e.options_label({}) == "No time limit"
    for bad in (20, True, "x", 60.5):
        with pytest.raises(GameError, match="Game length"):
            e.validate_options({"duration": bad})
    with pytest.raises(GameError, match="Unknown Business option"):
        e.validate_options({"speed": 2})


def test_untimed_game_has_no_deadline(e: BusinessEngine) -> None:
    s = game(e)
    assert e.deadline(s) is None and e.view(s, "a")["ends_in_ms"] is None
    assert e.expire(s) is s


def test_time_limit_ends_by_net_worth(e: BusinessEngine, t: FakeTime) -> None:
    s = game(e, "abc", duration=30)
    assert e.deadline(s) == 1_000_000.0 + 1_800
    t.now += 600
    assert e.view(s, "a")["ends_in_ms"] == 1_200_000
    assert e.expire(s) is s
    own(s, "b", MUMBAI, houses=1)        # 15,000 + 4,000 + 2,000
    own(s, "c", DELHI)
    s["mortgaged"][DELHI] = True         # 15,000 + 1,750
    t.now += 1_200
    done = e.expire(s)
    assert done is not s and e.outcome(done).winners == ["b"]
    assert e.outcome(done).reason == "Time up: highest net worth"
    standings = [(p.player, p.place, p.detail) for p in e.standings(done)]
    assert standings == [("b", 1, "Net worth ₹21,000"), ("c", 2, "Net worth ₹16,750"),
                         ("a", 3, "Net worth ₹15,000")]
    assert e.deadline(done) is None and e.view(done, "a")["ends_in_ms"] == 0


def test_time_limit_tie_and_late_action(e: BusinessEngine, t: FakeTime) -> None:
    s = game(e, duration=45)
    t.now += 45 * 60
    done = e.apply(s, "a", {"type": "roll"}, Dice(1, 2))  # arrives after time is up
    assert done["pos"]["a"] == 0
    assert sorted(e.outcome(done).winners) == ["a", "b"]
    assert [p.place for p in e.standings(done)] == [1, 1]


def test_standings_put_bankrupt_last_in_reverse_order(e: BusinessEngine) -> None:
    s = game(e, "abcd")
    s["bankrupt"] = ["c", "a"]
    s["left"] = ["a"]
    s["cash"]["d"] = 20_000
    assert [(p.player, p.place, p.detail) for p in e.standings(s)] == [
        ("d", 1, "Net worth ₹20,000"), ("b", 2, "Net worth ₹15,000"),
        ("a", 3, "Left the game"), ("c", 4, "Bankrupt")]


# -- leaving ----------------------------------------------------------------------------

def test_leaving_goes_bankrupt_to_bank(e: BusinessEngine) -> None:
    s = game(e, "abc")
    own(s, "a", AGRA, VARANASI, houses=2)
    own(s, "b", MUMBAI)
    s = act(e, s, "a", type="propose_trade", **trade(give={"cash": 1}))
    s = e.remove_player(s, "a")
    assert "a" in s["bankrupt"] and "a" in s["left"] and s["trade"] is None
    assert s["owner"][AGRA] is None and s["houses"][AGRA] == 0
    assert s["players"][s["current"]] == "b" and s["phase"] == "roll"
    s = e.remove_player(s, "c")
    assert e.outcome(s).winners == ["b"]
    assert [(p.player, p.detail) for p in e.standings(s)] == [
        ("b", "Net worth ₹19,000"), ("c", "Left the game"), ("a", "Left the game")]


def test_debts_to_a_leaver_are_forgiven(e: BusinessEngine) -> None:
    s = game(e, "abc")
    own(s, "b", VARANASI)
    s["cash"]["a"] = 10
    s = roll(e, s, "a", 1, 2)
    assert s["phase"] == "debt"
    s = e.remove_player(s, "b")
    assert s["phase"] == "end" and s["debts"] == [] and s["cash"]["a"] == 10


@pytest.mark.parametrize("count", [2, 3, 4, 5, 6])
def test_contract_views_work_after_players_leave(count: int) -> None:
    engine = BusinessEngine()
    players = [f"p{i}" for i in range(count)]
    state = engine.new_game(players, random.Random(4))
    state["current"] = count - 1
    for leaver in players[:-1]:
        state = engine.remove_player(state, leaver)
        for viewer in [*players, None]:
            engine.view(state, viewer)
        engine.awaiting(state)
    outcome = engine.outcome(state)
    assert outcome is not None and outcome.winners == [players[-1]]
    assert sorted(p.player for p in engine.standings(state)) == sorted(players)


# -- hidden information -----------------------------------------------------------------

def test_views_never_contain_the_deck_order(e: BusinessEngine) -> None:
    s = game(e, "abc")
    other = json.loads(json.dumps(s))
    other["decks"] = {deck: list(reversed(order)) for deck, order in s["decks"].items()}
    other["deck_pos"] = {"chance": 5, "fund": 7}
    for viewer in ["a", "b", "c", None]:
        view = e.view(s, viewer)
        assert view == e.view(other, viewer)
        dumped = json.dumps(view)
        assert "decks" not in dumped and "deck_pos" not in dumped
    # Nor after many turns.
    rng = random.Random(9)
    for _ in range(200):
        if e.outcome(s):
            break
        view = e.view(s, e._current(s))
        move = api_move({**view, "you": e._current(s)})
        assert move is not None
        s = e.apply(s, e._current(s), move, rng)
        assert "deck" not in json.dumps(e.view(s, None)).replace("\"deck\":", "")


# -- whole games ------------------------------------------------------------------------

def _random_move(engine: BusinessEngine, state: dict, rng: random.Random
                 ) -> tuple[str, dict[str, Any]] | None:
    """A legal-looking move for some player, mixing in building, mortgaging and trades."""
    for player in engine.awaiting(state):
        view = engine.view(state, player)
        options: list[dict[str, Any]] = [{"type": a} for a in view["actions"]
                                         if a != "propose_trade"]
        options += [{"type": "build", "square": i} for i in view["can_build"]]
        options += [{"type": "mortgage", "square": i} for i in view["can_mortgage"][:1]]
        options += [{"type": "unmortgage", "square": i} for i in view["can_unmortgage"][:1]]
        options += [{"type": "sell", "square": i} for i in view["can_sell"][:1]]
        if "propose_trade" in view["actions"]:
            others = [p["id"] for p in view["players"] if p["id"] != player and not p["bankrupt"]]
            mine = [i for i, o in enumerate(view["owners"]) if o == player]
            theirs = [i for i, o in enumerate(view["owners"]) if o == others[0]]
            options.append({"type": "propose_trade", "to": others[0],
                            "give": {"cash": 100, "squares": mine[:1]},
                            "get": {"cash": 0, "squares": theirs[:1]}})
        if options:
            return player, rng.choice(options)
    return None


@pytest.mark.parametrize("seed", range(12))
def test_random_games_stay_consistent(seed: int) -> None:
    engine = BusinessEngine()
    rng = random.Random(seed)
    players = ["a", "b", "c", "d"][: 2 + seed % 3]
    state = engine.start(players, rng)
    for _ in range(1500):
        if engine.outcome(state):
            break
        choice = _random_move(engine, state, rng)
        assert choice is not None, state["phase"]
        player, move = choice
        try:
            state = engine.apply(state, player, move, rng)
        except GameError:
            # Only trades can fail (e.g. a property with buildings in its group).
            assert move["type"] in ("propose_trade", "accept_trade"), move
            if state["trade"] and move["type"] == "accept_trade":
                state = engine.apply(state, player, {"type": "decline_trade"}, rng)
        for p in players:
            view = engine.view(state, p)
            json.dumps(view)
            if p not in state["bankrupt"]:
                assert state["cash"][p] >= 0
        assert all(0 <= h <= 5 for h in state["houses"])
        for group in GROUP_SQUARES.values():
            built = [state["houses"][i] for i in group]
            assert max(built) - min(built) <= 1 or all(state["owner"][i] for i in group)
    engine.standings(state)


@pytest.mark.parametrize("count", [2, 4, 6])
def test_api_strategy_plays_without_errors(count: int) -> None:
    engine = BusinessEngine()
    rng = random.Random(count)
    players = [f"p{i}" for i in range(count)]
    state = engine.start(players, rng)
    for _ in range(400):
        if engine.outcome(state):
            break
        moved = False
        for p in players:
            move = api_move({**engine.view(state, p), "you": p})
            if move is not None:
                state = engine.apply(state, p, move, rng)
                moved = True
                break
        assert moved


# -- through the real API ------------------------------------------------------------------

def test_business_plays_through_api(monkeypatch: pytest.MonkeyPatch, admin: Any,
                                    approved_player: Any) -> None:
    from contextlib import ExitStack

    from tests.conftest import receive_until
    from tests.test_game_integration import start_game

    monkeypatch.setitem(registry.GAMES, "business", BusinessEngine())
    a, b = approved_player("Alpha"), approved_player("Beta")
    with ExitStack() as stack_:
        sockets = [stack_.enter_context(p.ws("/ws/player")) for p in (a, b)]
        for ws in sockets:
            ws.receive_json()
        room_id = start_game(admin, [a, b], "business")
        views = [receive_until(ws, lambda m: m.get("game") is not None)["game"] for ws in sockets]
        assert "decks" not in json.dumps(views)
        moves = 0
        for _ in range(60):
            state = [p.get("/api/state").json() for p in (a, b)]
            if state[0]["room"]["status"] == "COMPLETED":
                break
            for player, s in zip((a, b), state, strict=True):
                move = api_move(s["game"])
                if move is None:
                    continue
                response = player.post(f"/api/rooms/{room_id}/actions", json={"action": move})
                assert response.status_code == 200, (move, response.text)
                moves += 1
                break
            else:
                pytest.fail("no player could move")
        assert moves >= 10
        assert square_index("Mumbai") == MUMBAI
