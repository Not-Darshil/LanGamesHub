"""Board, prices and cards for Business. Rules: docs/games/business.md.

All content is original: Indian cities, rupee prices and our own card texts.
"""

from __future__ import annotations

from typing import Any

SIZE = 36            # squares around a 10x10 perimeter (9 per side)
START = 0
JAIL = 9
REST_HOUSE = 18
GO_TO_JAIL = 27

START_CASH = 15_000
SALARY = 2_000       # for passing or landing on Start
JAIL_FINE = 500
INCOME_TAX = 2_000
TRANSPORT_PRICE = 2_000
UTILITY_PRICE = 1_500
TRANSPORT_RENT = [0, 250, 500, 1_000, 2_000]   # by number of transports owned
UTILITY_MULTIPLIER = [0, 4, 10]                # x dice total, by utilities owned
HOTEL = 5            # houses[square] == 5 means a hotel
DURATIONS = (30, 45, 60, 90)                   # optional game length in minutes

# Colour groups, cheapest first: display name, swatch, cost of one house (or the hotel).
GROUPS: dict[str, dict[str, Any]] = {
    "brown": {"name": "Brown", "color": "#8d5a3b", "house": 500},
    "sky": {"name": "Sky", "color": "#38bdf8", "house": 500},
    "pink": {"name": "Pink", "color": "#db2777", "house": 1_000},
    "orange": {"name": "Orange", "color": "#f97316", "house": 1_000},
    "red": {"name": "Red", "color": "#dc2626", "house": 1_500},
    "yellow": {"name": "Yellow", "color": "#eab308", "house": 1_500},
    "green": {"name": "Green", "color": "#16a34a", "house": 2_000},
    "navy": {"name": "Navy", "color": "#1e3a8a", "house": 2_000},
}

PROPERTY_KINDS = frozenset({"city", "transport", "utility"})


def _city(name: str, group: str, price: int, rents: list[int]) -> dict[str, Any]:
    """rents = [base, 1 house, 2, 3, 4 houses, hotel]."""
    assert len(rents) == 6
    return {"kind": "city", "name": name, "group": group, "price": price, "rents": rents}


def _special(kind: str, name: str, price: int | None = None) -> dict[str, Any]:
    square: dict[str, Any] = {"kind": kind, "name": name}
    if price is not None:
        square["price"] = price
    return square


SQUARES: list[dict[str, Any]] = [
    # Side 1: Start -> Jail
    _special("start", "Start"),
    _city("Agra", "brown", 600, [20, 100, 300, 900, 1_600, 2_500]),
    _special("fund", "Community Fund"),
    _city("Varanasi", "brown", 600, [40, 200, 600, 1_800, 3_200, 4_500]),
    _special("tax", "Income Tax"),
    _special("transport", "Railways", TRANSPORT_PRICE),
    _city("Jaipur", "sky", 1_000, [60, 300, 900, 2_700, 4_000, 5_500]),
    _city("Jodhpur", "sky", 1_000, [60, 300, 900, 2_700, 4_000, 5_500]),
    _city("Udaipur", "sky", 1_200, [80, 400, 1_000, 3_000, 4_500, 6_000]),
    # Side 2: Jail -> Rest House
    _special("jail", "Jail"),
    _city("Bhopal", "pink", 1_400, [100, 500, 1_500, 4_500, 6_250, 7_500]),
    _special("utility", "Electricity Board", UTILITY_PRICE),
    _city("Indore", "pink", 1_400, [100, 500, 1_500, 4_500, 6_250, 7_500]),
    _city("Nagpur", "pink", 1_600, [120, 600, 1_800, 5_000, 7_000, 9_000]),
    _special("transport", "Airways", TRANSPORT_PRICE),
    _city("Lucknow", "orange", 1_800, [140, 700, 2_000, 5_500, 7_500, 9_500]),
    _city("Kochi", "orange", 1_800, [140, 700, 2_000, 5_500, 7_500, 9_500]),
    _city("Chandigarh", "orange", 2_000, [160, 800, 2_200, 6_000, 8_000, 10_000]),
    # Side 3: Rest House -> Go to Jail
    _special("rest", "Rest House"),
    _city("Goa", "red", 2_200, [180, 900, 2_500, 7_000, 8_750, 10_500]),
    _special("chance", "Chance"),
    _city("Pune", "red", 2_200, [180, 900, 2_500, 7_000, 8_750, 10_500]),
    _city("Ahmedabad", "red", 2_400, [200, 1_000, 3_000, 7_500, 9_250, 11_000]),
    _special("transport", "Waterways", TRANSPORT_PRICE),
    _city("Surat", "yellow", 2_600, [220, 1_100, 3_300, 8_000, 9_750, 11_500]),
    _city("Kolkata", "yellow", 2_600, [220, 1_100, 3_300, 8_000, 9_750, 11_500]),
    _city("Hyderabad", "yellow", 2_800, [240, 1_200, 3_600, 8_500, 10_250, 12_000]),
    # Side 4: Go to Jail -> Start
    _special("go_to_jail", "Go to Jail"),
    _city("Chennai", "green", 3_000, [260, 1_300, 3_900, 9_000, 11_000, 12_750]),
    _city("Bengaluru", "green", 3_000, [260, 1_300, 3_900, 9_000, 11_000, 12_750]),
    _special("utility", "Water Works", UTILITY_PRICE),
    _city("Gurugram", "green", 3_200, [280, 1_500, 4_500, 10_000, 12_000, 14_000]),
    _special("transport", "Roadways", TRANSPORT_PRICE),
    _special("chance", "Chance"),
    _city("Delhi", "navy", 3_500, [350, 1_750, 5_000, 11_000, 13_000, 15_000]),
    _city("Mumbai", "navy", 4_000, [500, 2_000, 6_000, 14_000, 17_000, 20_000]),
]
assert len(SQUARES) == SIZE

GROUP_SQUARES: dict[str, list[int]] = {
    g: [i for i, s in enumerate(SQUARES) if s.get("group") == g] for g in GROUPS}
TRANSPORTS = [i for i, s in enumerate(SQUARES) if s["kind"] == "transport"]
UTILITIES = [i for i, s in enumerate(SQUARES) if s["kind"] == "utility"]
PROPERTIES = [i for i, s in enumerate(SQUARES) if s["kind"] in PROPERTY_KINDS]


def square_index(name: str) -> int:
    return next(i for i, s in enumerate(SQUARES) if s["name"] == name)


def house_cost(square: int) -> int:
    group = SQUARES[square].get("group")
    return GROUPS[group]["house"] if group else 0


def mortgage_value(square: int) -> int:
    return SQUARES[square].get("price", 0) // 2


def unmortgage_cost(square: int) -> int:
    value = mortgage_value(square)
    return value + (value + 9) // 10  # the mortgage plus 10% interest, rounded up


# Cards. kind: collect / pay (amount), advance (to), back (steps), jail,
# repairs (house, hotel), collect_each / pay_each (amount, per other player).
DECK_NAMES = {"chance": "Chance", "fund": "Community Fund"}
CARDS: dict[str, list[dict[str, Any]]] = {
    "chance": [
        {"text": "Advance to Start and collect your salary.", "kind": "advance", "to": START},
        {"text": "Catch the overnight express to Delhi.", "kind": "advance", "to": square_index("Delhi")},
        {"text": "Book a seat on the Railways. Advance there.", "kind": "advance",
         "to": square_index("Railways")},
        {"text": "Tech conference in Bengaluru. Advance there.", "kind": "advance",
         "to": square_index("Bengaluru")},
        {"text": "Beach break! Advance to Goa.", "kind": "advance", "to": square_index("Goa")},
        {"text": "Wrong turn at the roundabout. Go back 3 spaces.", "kind": "back", "steps": 3},
        {"text": "Caught jumping a red light. Go directly to Jail.", "kind": "jail"},
        {"text": "Your mutual fund pays a dividend. Collect ₹500.", "kind": "collect", "amount": 500},
        {"text": "Your startup closes a funding round. Collect ₹1,500.", "kind": "collect",
         "amount": 1_500},
        {"text": "Traffic challan for overspeeding. Pay ₹150.", "kind": "pay", "amount": 150},
        {"text": "Monsoon damage: pay ₹250 per house and ₹1,000 per hotel.", "kind": "repairs",
         "house": 250, "hotel": 1_000},
        {"text": "Elected secretary of the housing society. Pay each player ₹500.",
         "kind": "pay_each", "amount": 500},
    ],
    "fund": [
        {"text": "Advance to Start and collect your salary.", "kind": "advance", "to": START},
        {"text": "Your income tax refund arrives. Collect ₹1,000.", "kind": "collect",
         "amount": 1_000},
        {"text": "A fixed deposit matures. Collect ₹1,000.", "kind": "collect", "amount": 1_000},
        {"text": "Second prize in the Diwali rangoli contest. Collect ₹200.", "kind": "collect",
         "amount": 200},
        {"text": "Consulting fee received. Collect ₹250.", "kind": "collect", "amount": 250},
        {"text": "A distant uncle leaves you an inheritance. Collect ₹1,000.", "kind": "collect",
         "amount": 1_000},
        {"text": "Housewarming party! Collect ₹250 from each player.", "kind": "collect_each",
         "amount": 250},
        {"text": "Hospital bill. Pay ₹1,000.", "kind": "pay", "amount": 1_000},
        {"text": "School fees are due. Pay ₹500.", "kind": "pay", "amount": 500},
        {"text": "Road widening levy: pay ₹400 per house and ₹1,150 per hotel.",
         "kind": "repairs", "house": 400, "hotel": 1_150},
        {"text": "Caught in a raid on an illegal gambling den. Go directly to Jail.",
         "kind": "jail"},
        {"text": "Temple trust donation drive. Pay ₹200.", "kind": "pay", "amount": 200},
    ],
}


def money(amount: int) -> str:
    """Rupees with Indian digit grouping: ₹1,23,456."""
    digits = str(abs(amount))
    if len(digits) > 3:
        head, tail = digits[:-3], digits[-3:]
        groups = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        digits = ",".join([*groups, tail])
    return ("-" if amount < 0 else "") + "₹" + digits


def board_view() -> list[dict[str, Any]]:
    """Static board definition sent to clients."""
    rows = []
    for i, s in enumerate(SQUARES):
        row: dict[str, Any] = {"index": i, "kind": s["kind"], "name": s["name"]}
        if s["kind"] in PROPERTY_KINDS:
            row["price"] = s["price"]
            row["mortgage"] = mortgage_value(i)
            row["unmortgage"] = unmortgage_cost(i)
        if s["kind"] == "city":
            group = GROUPS[s["group"]]
            row.update(group=s["group"], group_name=group["name"], color=group["color"],
                       rents=list(s["rents"]), house_cost=group["house"])
        rows.append(row)
    return rows
