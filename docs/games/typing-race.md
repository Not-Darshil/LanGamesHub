# Typing Race — LanGamesHub rule set

Engine: `backend/app/games/typing_race.py` · Passages: `backend/app/games/typing_passages.py`
· Players: 2–8 · Game type: `typing`

## Setup
Everyone types the same passage. The passage is picked at random by the server from the
length chosen when the room is created (room option `length`):

| Key | Passage | Time limit |
| --- | --- | --- |
| `short` | about 100–150 characters | 90 s |
| `medium` | about 200–280 characters (the default) | 150 s |
| `long` | about 350–450 characters | 240 s |

Passages are original sentences or very old proverbs and fables, in plain ASCII (letters,
digits, spaces and basic punctuation, straight quotes, single spaces), so every character
can be typed on any keyboard.

## Timeline
All times come from the server's clock; browsers only display them.

* When the host starts the game, a **5-second countdown** begins. Progress sent before
  the start is refused ("The race has not started").
* The race **closes** when the time limit has passed since the start. The server ends the
  race within about half a second of the close, even if nobody types; a report that
  arrives after the close is not counted.

## Typing
* Browsers send `progress` with everything the player has typed so far:
  `{"type": "progress", "typed": "The early bird cat"}`.
* The server compares it with the passage. Your **progress** is the length of the
  correctly typed beginning: everything from the first wrong character on does not count
  until you fix it. Backspacing is allowed, so progress can go down as well as up.
* A report is refused if it is not text, if it runs more than 10 characters past the end
  of the passage, or once you have finished.
* **Anti-cheat:** progress faster than a human can type is refused. After `s` seconds of
  racing you may have at most `25 × s + 10` correct characters (about 300 WPM, plus a
  little slack for network delay). Pasting is also disabled in the browser.

## Finishing
* You finish when your correct progress reaches the end of the passage. The server
  records your finishing time and your speed:
  **WPM = (passage characters ÷ 5) ÷ minutes since the start**, both measured on the
  server. The log announces e.g. "Alice finished 1st at 87 WPM". Players who finish in
  the same millisecond share the place.
* The race ends as soon as **everyone still racing has finished**, or when the time
  limit runs out.

## Result
* The **first finisher wins** ("Finished first at 92 WPM"), including when the time runs
  out after someone has finished.
* If the time runs out and **nobody finished**, whoever got furthest wins, and players
  level at the front share the win ("Time's up"). If nobody typed anything, or everyone
  is level, the race is a draw.

## Standings
Finishers in finishing order (detail "92 WPM"), then everyone else by progress (detail
"64% complete"). Players who left are listed last by the room.

## Leaving
A player who leaves is out of the race. If only one player is left, they win ("Everyone
else left"). If everyone who is left has already finished, the race ends there.

## Visibility
Typing Race has no hidden information. Everyone (including the host as a spectator)
sees the passage, the countdown and time left (sent as `starts_in_ms` / `ends_in_ms`
relative to the moment the view was built, so browsers count down locally without
clock skew), and for each player: correct characters, percent complete, whether they
have finished, their place, and their WPM (final once finished, otherwise live: progress
÷ 5 ÷ minutes elapsed). Nobody's raw typing (including typos) leaves the server. Each
player's view also includes their own status (`me`), and the final standings once the
race is over.
