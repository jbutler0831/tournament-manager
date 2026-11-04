# Tournament Manager

**Version:** v0.1.0-beta

A desktop app for running in-person, single-elimination tournaments (built with fighting game events in mind).
The organizer runs everything from one laptop. Players follow their bracket on their phones, and a TV at the venue shows live matches and announces who plays next.

> **Platform status:** **macOS: tested** (Python 3.14). **Windows: coming later.** A Windows `.exe` is planned but has not been built or tested yet.

## Features

- **Check-in:** see who has arrived (✔) and who hasn't (·). No-shows are left out when the bracket starts.
- **Live bracket editing:** swap players, add late arrivals into open BYE slots, drop players (their opponent advances). Matches being played and finished results are locked and can't be changed.
- **Player pages:** each player gets a link and QR code at check-in. On their phone they see their next opponent, their station, results and the whole bracket. Pages refresh by themselves.
- **TV display:** a fullscreen dark-theme view for a venue screen: live matches with station numbers, up next, latest results and the full bracket.
- **Next-match announcements:** calling a match shows a large animated **PLAY NOW** card on the TV with an optional chime. Organizers can re-announce or dismiss it.
- **Auto-save and recovery:** every change is saved. If the app closes or crashes, reopen it and choose **Resume**.

## Requirements

- macOS with Python 3 (tested with 3.14; 3.9 or newer is required by the `qrcode` package, older versions are untested)
- Tkinter (included with the python.org installer)
- The `qrcode` package
- A Wi-Fi network shared by the laptop, players' phones and the TV

## Install

```
git clone https://github.com/jbutler0831/tournament-manager.git
cd tournament-manager
python3 -m pip install -r requirements.txt
```

## Run

```
python3 tournament_manager.py
```

The first time, macOS asks whether to allow incoming network connections. Click **Allow**, or phones can't open their pages.

## Running a tournament

1. Add players with a name and rank (1 = best seed), then **Add Team**.
2. As players arrive, select them and click **Check In / Undo**. A QR code pops up for them to scan.
3. Click **START TOURNAMENT**.
4. Click **Open TV Display** and show that browser window fullscreen on the venue screen (double-click for fullscreen, click once to enable sound).
5. For each match: **Call** (enter a station), then click the winner when it's over.
6. When every match in a round has a result, click **Advance to Next Round**.

| Page | Address |
|---|---|
| Whole bracket | `http://<laptop-ip>:8000/` |
| A player's page | `http://<laptop-ip>:8000/p/<number>` (use the QR code) |
| TV display | `http://<laptop-ip>:8000/display` |

The app shows the real address in its window. If port 8000 is busy, it uses the next free port up to 8009.

## Saves

The tournament is saved to `tournament_save.pkl` next to `tournament_manager.py` after every change.
When you start a new tournament instead of resuming, the old save is renamed with a timestamp. It is never deleted.

## Tests

```
python3 -m unittest test_tournament_manager.py
```

`TESTING_CHECKLIST.md` is a 15-minute hands-on practice run with a phone and a TV.

## Known limitations

- **Single elimination only.** No double elimination, round robin or pools.
- **Windows and Linux are untested.** Windows support is planned.
- **Local network only, no login.** Anyone on the same Wi-Fi can view the pages. The pages are read-only and cannot change the tournament.
- **Guest Wi-Fi often blocks phones** from reaching the laptop ("client isolation"). Use your own router or a phone hotspot if pages don't load.
- **Late arrivals** can only join round 1 while a BYE slot is open, or before any match has started.
- **Run one copy of the app at a time.** Two copies would share the same save file.
- **Only open save files created by this app.** Save files use Python's pickle format, which can run code when loaded.
- The phone page names rounds "Round 1, Round 2…", while the TV uses "Semifinals", "Final", etc.

## License

MIT. See [LICENSE](LICENSE).
