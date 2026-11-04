# Practice Tournament Checklist (4 players)

Takes about 15 minutes. You need: this laptop, 1 phone on the same Wi-Fi, and a second screen or browser window for the TV.
Tick each box. If something does not match "Expect", write it in **Problems found** at the bottom.

Start: `cd ~/Documents/ego && python3 tournament_manager.py`
If asked "Resume tournament?", click **No** for a clean practice run (the old save is kept as a backup, not deleted).

## 1. Registration and check-in
- [ ] Add 4 players with ranks 1–4 (name, rank, **Add Team**). Expect: each appears in the list with `·`.
- [ ] Select player 1, click **Check In / Undo**. Expect: `✔`, counter `Checked in: 1/4`, QR window opens.
- [ ] Click **Check In / Undo** again on player 1. Expect: back to `·`, counter `0/4`. Then check all 4 in.
- [ ] Expect: counter `Checked in: 4/4`.

## 2. Bracket generation
- [ ] Click **START TOURNAMENT**. Expect: no "not checked in" warning; 2 matches: seed 1 vs 4 and seed 2 vs 3.
- [ ] Expect: **Edit bracket — swap** row is visible. Swap two players, then swap them back.

## 3. Player QR codes and phone access
- [ ] macOS asks "Allow incoming connections?" → **Allow** (first run only).
- [ ] Select a player, click **Show QR / Link**, scan with your phone. Expect: page opens showing "You are <name>" and "vs <opponent>".
- [ ] Expect: page fits the phone screen with no sideways scrolling.
- [ ] Open the same link on a second phone or browser tab. Expect: same content.

## 4. Live TV display
- [ ] Click **Open TV Display** (or open `http://<laptop-ip>:8000/display` on the other screen).
- [ ] Double-click the page. Expect: fullscreen. Click once more. Expect: "Click once to enable sound" hint disappears.
- [ ] Expect: tournament name, ROUND/SEMIFINALS heading, bracket with both matches, FINAL slot shown as TBD.
- [ ] Readable from 3+ metres away? (yes / no)

## 5. Calling matches and announcements
- [ ] Click **Call** on Match 1, enter station `1`. Expect within 2 s: TV overlay **PLAY NOW**, both names, Match 1, Station 1, chime.
- [ ] Expect: the phone of a Match 1 player shows **PLAY NOW · Station 1** within 3 s, without refreshing.
- [ ] Expect: overlay disappears by itself after about 12 s.
- [ ] Click **Call** on Match 2, station `2`. Expect: new overlay for Match 2.
- [ ] Click **Un-call** then **Call** on Match 2 again. Expect: **no** second announcement.
- [ ] Click **Announce** on Match 2. Expect: overlay shows again. Click **Dismiss Announcement**. Expect: overlay closes within 2 s.
- [ ] Untick **TV sound**, click **Announce**. Expect: overlay, **no** chime. Tick it again.

## 6. Results and advancing
- [ ] Click the winner button on Match 1. Expect: row shows "<winner> def. <loser> ✔"; TV shows it under LATEST RESULTS; Match 1 player's phone says "You beat…" or "Eliminated…".
- [ ] Try **Drop Player** on a player in the live Match 2. Expect: refused ("Finish or un-call it first").
- [ ] Record Match 2's winner. Click **Advance to Next Round**. Expect: final appears as **Match 3**; TV FINAL slot shows both names.

## 7. Final and champion
- [ ] **Call** Match 3 (station `1`), check the TV overlay, then record the winner and click **Advance to Next Round**.
- [ ] Expect: app shows `👑 TOURNAMENT CHAMPION: <name>`; TV shows gold CHAMPION banner; champion's phone shows "You won the tournament!"

## 8. Restart and restore
- [ ] Before step 7's result (or in a second run): with the final **called**, close the app window.
- [ ] Expect: TV footer shows "Reconnecting…".
- [ ] Relaunch the app, click **Yes** to resume. Expect: final still LIVE at Station 1; round 1 results unchanged.
- [ ] Expect: TV and phone recover by themselves within a few seconds, no refresh.
- [ ] After the champion is crowned, relaunch and resume. Expect: champion shown.

## Problems found
| # | Step | What happened | Expected |
|---|------|---------------|----------|
|   |      |               |          |
