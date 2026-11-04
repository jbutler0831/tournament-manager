import json
import math
import os
import pickle
import random
import re
import socket
import sys
import threading
import webbrowser
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import qrcode
# Import the Tkinter library for the GUI
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog

# --- BACKEND LOGIC CLASSES (REUSED FROM tournament_manager.py) ---

class Team:
    """Represents a team or player in the tournament."""
    def __init__(self, name, rank=0):
        self.name = name
        self.rank = rank
        self.checked_in = False
        self.dropped = False

    def __repr__(self):
        return f"{self.name} (#{self.rank})"

class Match:
    """Represents a single match with two teams and a potential winner."""
    def __init__(self, id, team1, team2, round_num, start_time):
        self.id = id
        self.team1 = team1
        self.team2 = team2
        self.round_num = round_num
        self.start_time = start_time
        self.winner = None
        self.in_progress = False
        self.station = ""

    def set_winner(self, winner_team):
        self.winner = winner_team
        self.in_progress = False
        return winner_team

    def is_bye(self):
        return "BYE" in (self.team1.name, self.team2.name)

    def get_status_display(self):
        t1_name = self.team1.name if self.team1 else "TBD"
        t2_name = self.team2.name if self.team2 else "TBD"
        time_str = self.start_time.strftime("%I:%M %p")
        
        if self.winner:
            status = f"Winner: {self.winner.name}"
        else:
            status = f"Scheduled @ {time_str}"
            
        return f"Match {self.id} (R{self.round_num}): {t1_name} vs {t2_name} | {status}"

class TournamentGenerator:
    """Manages the overall tournament bracket and progression."""
    def __init__(self, name, start_time):
        self.name = name
        self.teams = []
        self.rounds = {}
        self.start_time = start_time
        self.current_round = 1
        self.champion = None

    def add_team(self, team_name, rank=0):
        self.teams.append(Team(team_name, rank))

    def active_teams(self):
        """Teams that showed up and haven't dropped; no-shows are left out of the bracket."""
        return [t for t in self.teams if t.checked_in and not t.dropped]

    def generate_bracket(self):
        """Generates the initial Round 1 bracket with Byes."""
        teams = self.active_teams()
        if len(teams) < 2:
            return False # Indicate failure

        sorted_teams = sorted(teams, key=lambda x: x.rank)
        num_teams = len(sorted_teams)
        bracket_size = 2 ** math.ceil(math.log2(num_teams))
        num_byes = bracket_size - num_teams
        
        # Add Byes
        for i in range(num_byes):
            sorted_teams.append(Team("BYE", 999)) 

        # Create Round 1
        final_bracket_order = self._organize_seeds(sorted_teams)
        self.rounds[1] = []
        match_id = 1
        current_time = self.start_time

        for i in range(0, len(final_bracket_order), 2):
            t1 = final_bracket_order[i]
            t2 = final_bracket_order[i+1]
            
            m = Match(match_id, t1, t2, 1, current_time)
            
            # Auto-advance if opponent is BYE
            if t2.name == "BYE":
                m.set_winner(t1)
            elif t1.name == "BYE":
                m.set_winner(t2)
                
            self.rounds[1].append(m)
            match_id += 1
            current_time += timedelta(minutes=30)
        
        return True # Indicate success

    def _organize_seeds(self, sorted_teams):
        """Recursive seeding logic."""
        if len(sorted_teams) <= 2:
            return sorted_teams
        top = sorted_teams[:len(sorted_teams)//2]
        bottom = sorted_teams[len(sorted_teams)//2:][::-1]
        merged = []
        for t1, t2 in zip(top, bottom):
            merged.extend([t1, t2])
        return merged

    # --- Live bracket editing. Only current-round matches that are not live and have no real result may change. ---

    def is_editable(self, match):
        return (match.round_num == self.current_round and not match.in_progress
                and (match.winner is None or match.is_bye()))

    def _refresh_bye(self, match):
        """Re-applies the BYE auto-advance after a slot changed."""
        match.winner = None
        if match.team2.name == "BYE":
            match.set_winner(match.team1)
        elif match.team1.name == "BYE":
            match.set_winner(match.team2)

    def add_late_player(self, team):
        """Puts a late arrival into an open BYE slot, or re-seeds if no round-1 match has started.
        Returns a message; raises ValueError if there is no safe place."""
        if self.current_round != 1:
            raise ValueError("Late entries are only possible during round 1.")
        team.checked_in = True
        team.dropped = False
        if team not in self.teams:
            self.teams.append(team)
        for m in self.rounds[1]:
            if self.is_editable(m) and m.is_bye():
                if m.team2.name == "BYE":
                    m.team2 = team
                else:
                    m.team1 = team
                self._refresh_bye(m)
                return f"{team.name} placed in Match {m.id}."
        if not any(m.in_progress or (m.winner and not m.is_bye()) for m in self.rounds[1]):
            self.generate_bracket()
            return f"No open slot, so the bracket was re-seeded with {team.name}."
        team.checked_in = False
        raise ValueError("No open slot: every round-1 match is full and play has started.")

    def drop_player(self, team):
        """Marks a player as dropped. Their open match becomes a walkover; a dropped winner
        becomes a BYE when the round advances. Raises ValueError if they are mid-match."""
        for m in self.rounds.get(self.current_round, []):
            for attr in ("team1", "team2"):
                if getattr(m, attr) is team:
                    if m.in_progress:
                        raise ValueError(f"{team.name} is playing Match {m.id}. Finish or un-call it first.")
                    if self.is_editable(m):
                        setattr(m, attr, Team("BYE", 999))
                        self._refresh_bye(m)
        team.dropped = True

    def editable_slots(self):
        """(match, 'team1'|'team2') pairs the organizer may swap."""
        return [(m, a) for m in self.rounds.get(self.current_round, []) if self.is_editable(m)
                for a in ("team1", "team2")]

    def swap_slots(self, m1, a1, m2, a2):
        if not (self.is_editable(m1) and self.is_editable(m2)):
            raise ValueError("Only matches that haven't started or finished can be edited.")
        t1, t2 = getattr(m1, a1), getattr(m2, a2)
        setattr(m1, a1, t2)
        setattr(m2, a2, t1)
        self._refresh_bye(m1)
        self._refresh_bye(m2)

    def call_match(self, match, station=""):
        """Marks a match as being played (locks it from edits)."""
        if match.winner or match.is_bye():
            raise ValueError("That match is already decided.")
        match.in_progress = True
        match.station = station

    def advance_round(self, matches):
        """Processes the winners of the current matches and sets up the next round."""
        winners = [m.winner for m in matches if m.winner]
        if len(winners) == 1:
            self.champion = winners[0]  # the final's winner keeps the title even if they leave afterwards
            return self.champion # Return the champion

        # A winner who dropped out becomes a BYE so the next opponent auto-advances.
        next_round_teams = [Team("BYE", 999) if w.dropped else w for w in winners]
            
        self.current_round += 1
        self.rounds[self.current_round] = []
        
        # Get start time for the next round, one hour after the last match of the previous round
        last_match_time = self.rounds.get(self.current_round - 1)[-1].start_time
        current_time = last_match_time + timedelta(hours=1)
        
        # Pair up winners for next round
        for i in range(0, len(next_round_teams), 2):
            if i + 1 < len(next_round_teams):
                t1 = next_round_teams[i]
                t2 = next_round_teams[i+1]
                
                # Check for Byes *again* if uneven teams somehow slipped through (though it shouldn't)
                if t1.name == "BYE":
                     t1 = t2
                     t2 = Team("BYE", 999)
                elif t2.name == "BYE":
                    pass # t1 vs BYE is handled below

                # Match numbers run across the whole tournament (Match 14, not "Match 2 of round 3") so callouts are unambiguous.
                new_match = Match(sum(len(ms) for ms in self.rounds.values()) + 1, t1, t2, self.current_round, current_time)
                
                # Auto-advance if opponent is BYE (handles round 2 if needed)
                if new_match.team2.name == "BYE":
                    new_match.set_winner(new_match.team1)
                elif new_match.team1.name == "BYE":
                    new_match.set_winner(new_match.team2) # Should not happen, as Byes are low seeds.
                
                self.rounds[self.current_round].append(new_match)
                current_time += timedelta(minutes=30)
        
        return None # No champion yet


# --- SAVE / RECOVERY ---

def documents_dir():
    """The user's Documents folder. On Windows this follows OneDrive/folder redirection."""
    if sys.platform == "win32":
        import ctypes
        buf = ctypes.create_unicode_buffer(260)
        if ctypes.windll.shell32.SHGetFolderPathW(None, 5, None, 0, buf) == 0:  # 5 = CSIDL_PERSONAL (Documents)
            return buf.value
    return os.path.join(os.path.expanduser("~"), "Documents")

def data_dir():
    """Where saves and logs live. Run as a script: next to this file (unchanged).
    Packaged .exe: Documents/TournamentManager, because a one-file .exe runs from a temp folder deleted on exit."""
    if getattr(sys, "frozen", False):
        return os.path.join(documents_dir(), "TournamentManager")
    return os.path.dirname(os.path.abspath(__file__))

DATA_DIR = data_dir()
SAVE_PATH = os.path.join(DATA_DIR, "tournament_save.pkl")
LOG_PATH = os.path.join(DATA_DIR, "tournament_manager.log")

def save_tournament(gen, path=None):
    path = path or SAVE_PATH
    # Pickle keeps the shared Team objects linked across matches. Only ever load your own save file.
    os.makedirs(os.path.dirname(path), exist_ok=True)  # first save in a packaged build creates the folder
    tmp = path + ".tmp"
    with open(tmp, "wb") as f:
        pickle.dump(gen, f)
    os.replace(tmp, path)  # atomic: a crash mid-write never leaves a half-written save

def load_tournament(path=None):
    path = path or SAVE_PATH
    with open(path, "rb") as f:
        return pickle.load(f)

def archive_save(path=None):
    """Moves the save aside (never deletes it) so a new tournament can start."""
    path = path or SAVE_PATH
    stamp, n = path.replace(".pkl", f"-{datetime.now():%Y%m%d-%H%M%S}"), 1
    target = stamp + ".pkl"
    while os.path.exists(target):
        n += 1
        target = f"{stamp}-{n}.pkl"
    os.replace(path, target)
    return target


# --- PLAYER WEB PAGES (read-only, venue Wi-Fi) ---

def build_state(gen, **display):
    """JSON-ready snapshot for the web pages. Player id = index in gen.teams; BYE = None.
    `display` carries TV-only settings (announce, sound) that are not part of the saved tournament."""
    if gen is None:
        return {}
    ids = {id(t): i for i, t in enumerate(gen.teams)}
    pid = lambda t: ids.get(id(t)) if t is not None else None
    match_json = lambda m: {"id": m.id, "round": m.round_num, "p1": pid(m.team1), "p2": pid(m.team2),
                            "winner": pid(m.winner), "done": m.winner is not None, "bye": m.is_bye(),
                            "live": m.in_progress, "station": m.station}
    return {"name": gen.name, "round": gen.current_round if gen.rounds else 0, "champion": pid(gen.champion),
            "players": [{"id": i, "name": t.name, "checked_in": t.checked_in, "dropped": t.dropped}
                        for i, t in enumerate(gen.teams)],
            "rounds": [[match_json(m) for m in gen.rounds[r]] for r in sorted(gen.rounds)], **display}

def lan_ip():
    """The laptop's address on the venue Wi-Fi."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))  # UDP connect sends nothing; it just picks the outgoing interface
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()

def start_web_server(get_state_bytes, port=8000):
    """Serves the player pages in a background thread. GET only: the web side can never change the tournament."""
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            path = self.path.split("?")[0]
            if path == "/api/state":
                body, ctype = get_state_bytes(), "application/json"
            elif path == "/" or re.fullmatch(r"/p/\d+", path):
                body, ctype = PLAYER_PAGE.encode(), "text/html; charset=utf-8"
            elif path == "/display":
                body, ctype = DISPLAY_PAGE.encode(), "text/html; charset=utf-8"
            else:
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    for p in range(port, port + 10):  # skip ports already taken by something else
        try:
            server = ThreadingHTTPServer(("0.0.0.0", p), Handler)
            break
        except OSError:
            continue
    else:
        return None
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server

def qr_photo(data, scale=6):
    """QR code as a Tk image, drawn from the qrcode matrix (no Pillow needed)."""
    q = qrcode.QRCode(border=2)
    q.add_data(data)
    q.make(fit=True)
    rows = q.get_matrix()
    img = tk.PhotoImage(width=len(rows), height=len(rows))
    img.put(" ".join("{" + " ".join("#000000" if c else "#ffffff" for c in row) + "}" for row in rows))
    return img.zoom(scale)

PLAYER_PAGE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Bracket</title>
<style>
body{font-family:system-ui,-apple-system,sans-serif;margin:0;background:#111;color:#eee;font-size:17px}
header{padding:14px 16px;background:#1d1d1d;position:sticky;top:0}
h1{font-size:1.25rem;margin:0}
.sub{color:#aaa;font-size:.9rem}
.card{margin:12px;padding:16px;border-radius:12px;background:#262626}
.big{font-size:1.6rem;font-weight:700;margin:4px 0;overflow-wrap:anywhere}
.live{color:#ff5c5c;font-weight:700}
h2{font-size:.95rem;color:#aaa;margin:18px 12px 6px;text-transform:uppercase;letter-spacing:.05em}
.m{margin:6px 12px;padding:10px 12px;background:#1b1b1b;border-radius:8px;display:flex;justify-content:space-between;gap:8px}
.p{display:block;padding:2px 0;overflow-wrap:anywhere}
.w{color:#7cfc8a;font-weight:700}.l{color:#777;text-decoration:line-through}
.me{outline:2px solid #ffd54a}
.tag{font-size:.8rem;color:#aaa;text-align:right;white-space:nowrap}
</style></head><body>
<header><h1 id="t">Loading…</h1><div class="sub" id="s"></div></header>
<main><div id="me"></div><div id="br"></div></main>
<script>
const pm = location.pathname.match(/^\/p\/(\d+)/), me = pm ? +pm[1] : null;
let last = null;
const esc = s => String(s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const nm = (S, id) => id == null ? 'BYE' : esc(S.players[id].name);
const stn = m => m.station ? ' · Station ' + esc(m.station) : '';

function meCard(S) {
  const p = S.players[me];
  if (!p) return 'Player not found. Ask the organizer for your link.';
  const h = '<div class="sub">You are</div><div class="big">' + esc(p.name) + '</div>';
  if (p.dropped) return h + 'You have dropped out.';
  if (S.champion === me) return h + '🏆 You won the tournament!';
  if (!S.round) return h + (p.checked_in ? '✔ Checked in. Waiting for the bracket to start.' : 'Not checked in yet. See the organizer.');
  const mine = S.rounds.flat().filter(m => m.p1 === me || m.p2 === me);
  const m = mine[mine.length - 1];
  if (!m) return h + 'You are not in the bracket. See the organizer.';
  const opp = m.p1 === me ? m.p2 : m.p1;
  if (!m.done) return h + '<div class="sub">Next match · M' + m.id + '</div><div class="big">vs ' + nm(S, opp) + '</div>'
    + (m.live ? '<div class="live">PLAY NOW' + stn(m) + '</div>' : '<div class="sub">Waiting to be called</div>');
  if (m.winner === me) return h + (m.bye ? 'Bye: you advance.' : '✔ You beat ' + nm(S, opp) + '.')
    + (S.champion == null ? '<div class="sub">Waiting for round ' + (m.round + 1) + '.</div>' : '');
  return h + 'Eliminated in round ' + m.round + ' by ' + nm(S, m.winner) + '.';
}

function row(S, m) {
  const cls = id => m.done && !m.bye ? (m.winner === id ? 'w' : 'l') : '';
  const mine = me != null && (m.p1 === me || m.p2 === me) ? ' me' : '';
  const tag = m.bye ? 'bye' : m.done ? 'final' : m.live ? '<span class="live">LIVE</span>' + stn(m) : 'upcoming';
  return '<div class="m' + mine + '"><div><span class="p ' + cls(m.p1) + '">' + nm(S, m.p1) + '</span><span class="p '
    + cls(m.p2) + '">' + nm(S, m.p2) + '</span></div><div class="tag">M' + m.id + '<br>' + tag + '</div></div>';
}

function render(S) {
  document.getElementById('t').textContent = S.name || 'Tournament';
  document.getElementById('s').textContent = !S.round ? 'Check-in open. Bracket not started.'
    : S.champion != null ? '🏆 Champion: ' + S.players[S.champion].name : 'Round ' + S.round + ' in progress';
  document.getElementById('me').innerHTML = me == null || !S.players ? '' : '<div class="card">' + meCard(S) + '</div>';
  document.getElementById('br').innerHTML = (S.rounds || []).map((ms, i) =>
    '<h2>Round ' + (i + 1) + '</h2>' + ms.map(m => row(S, m)).join('')).reverse().join('');
}

async function poll() {
  try {
    const txt = await (await fetch('/api/state', {cache: 'no-store'})).text();
    if (txt !== last) { last = txt; render(JSON.parse(txt)); }
  } catch (e) {
    last = null;  // force a redraw once the connection is back
    document.getElementById('s').textContent = 'Reconnecting… (check you are on the venue Wi-Fi)';
  }
  setTimeout(poll, 3000);
}
poll();
</script></body></html>"""


# Venue TV / monitor page. Read-only, same /api/state as the player pages.
DISPLAY_PAGE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Tournament Display</title>
<style>
:root{--bg:#06070b;--panel:#10131b;--line:#222838;--txt:#f3f5f9;--dim:#8891a5;--live:#ff3049;--next:#3aa6ff;--win:#35e07a;--gold:#ffc93c}
*{box-sizing:border-box}
html,body{margin:0;height:100%;overflow:hidden;background:radial-gradient(ellipse at 50% -20%,#18203a,var(--bg) 65%);color:var(--txt);
  font-family:system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
body{display:grid;grid-template-rows:auto minmax(0,1fr) auto;height:100vh;padding:1.8vh 2vw;gap:1.8vh;font-size:clamp(13px,1.45vh + .45vw,44px)}
:fullscreen body{cursor:none}
header{display:flex;align-items:flex-end;justify-content:space-between;gap:2vw;padding-bottom:1.2vh;
  border-bottom:.18em solid;border-image:linear-gradient(90deg,var(--live),var(--next)) 1}
h1{margin:0;font-size:2.3em;font-weight:900;text-transform:uppercase;letter-spacing:.02em;line-height:1;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
#status{font-size:1.25em;font-weight:800;text-transform:uppercase;letter-spacing:.12em;color:var(--next);white-space:nowrap}
main{display:grid;grid-template-columns:minmax(0,35fr) minmax(0,65fr);gap:2.2vw;min-height:0}
#left{display:flex;flex-direction:column;gap:2vh;min-height:0;overflow:hidden}
h2{margin:0 0 .9vh;font-size:.85em;font-weight:800;letter-spacing:.2em;text-transform:uppercase;color:var(--dim);display:flex;align-items:center;gap:.6em}
.dot{width:.7em;height:.7em;border-radius:50%;background:var(--live);animation:pulse 1.4s infinite}
@keyframes pulse{50%{opacity:.35}}
.card{display:flex;align-items:center;gap:1em;background:linear-gradient(90deg,rgba(255,48,73,.16),var(--panel) 40%);
  border:1px solid rgba(255,48,73,.45);border-left:.4em solid var(--live);border-radius:.5em;padding:.55em .9em;margin-bottom:1vh}
.stn{min-width:3em;text-align:center;font-size:2em;font-weight:900;line-height:1;color:var(--live)}
.stn small{display:block;font-size:.3em;letter-spacing:.2em;color:var(--dim);margin-top:.25em}
.vs{flex:1;min-width:0}
.pl{font-size:1.3em;font-weight:800;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.v{font-size:.65em;font-weight:800;color:var(--dim);letter-spacing:.15em}
.mid{font-size:.75em;color:var(--dim);font-weight:700;white-space:nowrap}
.row{display:flex;align-items:center;gap:.8em;background:var(--panel);border-left:.3em solid var(--next);border-radius:.4em;padding:.4em .8em;margin-bottom:.7vh}
.row .names{flex:1;min-width:0;font-weight:700;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.row .names i{color:var(--dim);font-style:normal;font-weight:600;font-size:.8em;margin:0 .4em}
.row.res{border-left-color:var(--win)}
.empty{color:var(--dim);font-size:.9em;padding:.4em 0}
.champ{text-align:center;padding:1.2em .8em;border-radius:.6em;background:linear-gradient(180deg,rgba(255,201,60,.18),var(--panel));border:2px solid var(--gold)}
.champ .t{color:var(--gold);letter-spacing:.25em;font-weight:900;font-size:.9em}
.champ .n{font-size:2.4em;font-weight:900;margin-top:.2em;overflow-wrap:anywhere}
#bracketWrap{display:flex;flex-direction:column;min-height:0}
#bracket{flex:1;display:flex;gap:1.4vw;min-height:0}
.col{flex:1;display:flex;flex-direction:column;min-width:0}
.col h3{margin:0 0 .5em;font-size:.8em;letter-spacing:.15em;text-transform:uppercase;color:var(--dim);text-align:center}
.col.cur h3{color:var(--next)}
.colbody{flex:1;display:flex;flex-direction:column;justify-content:space-around}
.bm{background:var(--panel);border:1px solid var(--line);border-radius:.3em;margin:.2em 0;position:relative}
.bm>div{padding:.12em .5em;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.bm>div+div{border-top:1px solid var(--line)}
.bm.live{border-color:var(--live);box-shadow:0 0 .7em rgba(255,48,73,.55)}
.bm .tag{position:absolute;right:.3em;top:50%;transform:translateY(-50%);background:var(--live);color:#fff;font-size:.65em;font-weight:900;padding:.05em .4em;border-radius:.25em}
.bm.bye{opacity:.45}
.w{color:var(--win);font-weight:800}.l{color:#59617a;text-decoration:line-through}.tbd{color:#3f4659;font-style:italic}
.bm.final-win{border-color:var(--gold)}
footer{display:flex;justify-content:space-between;gap:2vw;color:var(--dim);font-size:.8em}
:fullscreen #fsHint{display:none}
.chips{display:flex;flex-wrap:wrap;gap:.5em}
.chip{background:var(--panel);border:1px solid var(--line);border-radius:2em;padding:.3em .9em;font-weight:700}
/* Next-match announcement overlay: temporary, auto-hides so the bracket is never covered for long. */
#ann{position:fixed;inset:0;display:flex;align-items:center;justify-content:center;background:rgba(3,5,10,.78);
  backdrop-filter:blur(6px);opacity:0;visibility:hidden;transition:opacity .45s,visibility .45s;z-index:10}
#ann.show{opacity:1;visibility:visible}
#ann.next .ann-card{border-color:var(--next);box-shadow:0 0 6vh rgba(58,166,255,.45)}
.ann-card{width:min(86vw,150vh);text-align:center;padding:5vh 4vw 0;border-radius:1.2vh;overflow:hidden;position:relative;
  background:linear-gradient(160deg,#151b2e,#090b12);border:.3vh solid var(--live);box-shadow:0 0 6vh rgba(255,48,73,.45)}
#ann.show .ann-card{animation:annIn .7s cubic-bezier(.2,1.3,.4,1) both}
.ann-tour{font-size:2.6vh;letter-spacing:.4em;color:var(--dim);font-weight:800;text-transform:uppercase}
.ann-kick{font-size:9vh;font-weight:900;letter-spacing:.06em;line-height:1.1;color:var(--live);margin:1vh 0 3vh;text-shadow:0 0 3vh rgba(255,48,73,.6)}
.ann-kick.next{color:var(--next);text-shadow:0 0 3vh rgba(58,166,255,.6)}
.ann-vs{display:grid;grid-template-columns:1fr auto 1fr;align-items:center;gap:3vw}
.ann-p{font-size:7vh;font-weight:900;line-height:1.1;overflow-wrap:anywhere}
#annP1{text-align:right}#annP2{text-align:left}
#ann.show #annP1{animation:fromL .6s .25s both}#ann.show #annP2{animation:fromR .6s .25s both}
.ann-x{font-size:4vh;font-weight:900;color:var(--dim)}
.ann-meta{display:flex;justify-content:center;gap:4vw;margin:4vh 0;font-size:4vh;font-weight:800;color:var(--dim)}
.ann-meta span:empty{display:none}.ann-meta b{color:var(--txt)}.ann-meta .stn-b{color:var(--live)}
.ann-bar{margin:0 -4vw;height:1vh;background:linear-gradient(90deg,var(--live),var(--next));transform-origin:left}
#ann.show .ann-bar{animation:drain var(--ann-ms) linear both}
@keyframes annIn{from{transform:scale(.8) translateY(6vh);opacity:0}}
@keyframes fromL{from{transform:translateX(-12vw);opacity:0}}
@keyframes fromR{from{transform:translateX(12vw);opacity:0}}
@keyframes drain{to{transform:scaleX(0)}}
@media (prefers-reduced-motion:reduce){#ann *{animation:none!important}}
</style></head><body>
<div id="ann" aria-live="assertive"><div class="ann-card">
  <div class="ann-tour" id="annTour"></div><div class="ann-kick" id="annKick"></div>
  <div class="ann-vs"><div class="ann-p" id="annP1"></div><div class="ann-x">VS</div><div class="ann-p" id="annP2"></div></div>
  <div class="ann-meta"><span id="annMatch"></span><span id="annStn"></span></div><div class="ann-bar"></div>
</div></div>
<header><h1 id="name">Loading…</h1><div id="status"></div></header>
<main><div id="left"></div><div id="bracketWrap"><h2>Bracket</h2><div id="bracket"></div></div></main>
<footer><span id="follow"></span><span id="fsHint">Double-click for fullscreen</span><span id="snd"></span><span id="upd"></span></footer>
<script>
const $ = id => document.getElementById(id);
const esc = s => String(s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const nm = (S, id) => id == null ? 'BYE' : esc(S.players[id].name);
const roundName = (r, R) => r === R ? 'Final' : r === R - 1 ? 'Semifinals' : r === R - 2 && R >= 4 ? 'Quarterfinals' : 'Round ' + r;
const MAX_NEXT = 6, MAX_RESULTS = 4;  // keeps the left column readable from across the room
let last = null;

function liveCard(S, m) {
  return '<div class="card"><div class="stn">' + (m.station ? esc(m.station) : '–') + '<small>STATION</small></div>'
    + '<div class="vs"><div class="pl">' + nm(S, m.p1) + '</div><div class="v">VS</div><div class="pl">' + nm(S, m.p2) + '</div></div>'
    + '<div class="mid">M' + m.id + '</div></div>';
}
const rowHtml = (S, m, res) => '<div class="row' + (res ? ' res' : '') + '"><span class="mid">M' + m.id + '</span><span class="names">'
  + (res ? '<span class="w">' + nm(S, m.winner) + '</span><i>def.</i>' + nm(S, m.winner === m.p1 ? m.p2 : m.p1)
         : nm(S, m.p1) + '<i>vs</i>' + nm(S, m.p2)) + '</span></div>';
const more = (n, max) => n > max ? '<div class="empty">+' + (n - max) + ' more</div>' : '';

function bracketMatch(S, m) {
  if (!m) return '<div class="bm"><div class="tbd">TBD</div><div class="tbd">TBD</div></div>';
  const cls = id => m.done && !m.bye ? (m.winner === id ? 'w' : 'l') : '';
  return '<div class="bm' + (m.live ? ' live' : '') + (m.bye ? ' bye' : '') + '">'
    + '<div class="' + cls(m.p1) + '">' + nm(S, m.p1) + '</div><div class="' + cls(m.p2) + '">' + nm(S, m.p2) + '</div>'
    + (m.live ? '<span class="tag">LIVE' + (m.station ? ' · ' + esc(m.station) : '') + '</span>' : '') + '</div>';
}

function render(S) {
  $('name').textContent = S.name || 'Tournament';
  const rounds = S.rounds || [];
  if (!rounds.length) {
    const ins = (S.players || []).filter(p => p.checked_in && !p.dropped);
    $('status').textContent = 'Check-in open';
    $('left').innerHTML = '<div><h2>Checked in</h2><div class="champ"><div class="n">' + ins.length + '</div><div class="t">PLAYERS READY</div></div></div>';
    $('bracket').innerHTML = '<div class="chips">' + ins.map(p => '<span class="chip">' + esc(p.name) + '</span>').join('') + '</div>';
    return;
  }
  const size = 2 * rounds[0].length, R = Math.round(Math.log2(size)), cur = rounds[rounds.length - 1];
  $('status').textContent = S.champion != null ? 'Tournament complete' : roundName(S.round, R);

  const live = cur.filter(m => m.live), next = cur.filter(m => !m.done && !m.live && !m.bye);
  const results = rounds.slice().reverse().flat().filter(m => m.done && !m.bye);
  $('left').innerHTML =
    (S.champion != null ? '<div class="champ"><div class="t">🏆 CHAMPION</div><div class="n">' + nm(S, S.champion) + '</div></div>'
      : '<div><h2><span class="dot"></span>Live now</h2>' + (live.length ? live.map(m => liveCard(S, m)).join('') : '<div class="empty">Waiting for matches to be called</div>') + '</div>'
      + '<div><h2>Up next</h2>' + (next.length ? next.slice(0, MAX_NEXT).map(m => rowHtml(S, m)).join('') + more(next.length, MAX_NEXT) : '<div class="empty">No matches waiting</div>') + '</div>')
    + '<div><h2>Latest results</h2>' + (results.length ? results.slice(0, MAX_RESULTS).map(m => rowHtml(S, m, true)).join('') : '<div class="empty">No results yet</div>') + '</div>';

  // The app only creates a round once the previous one is finished, so preview the next round from known winners.
  const ahead = m => !m || !m.done ? '<div class="tbd">TBD</div>'
    : '<div>' + (m.winner == null || S.players[m.winner].dropped ? 'BYE' : nm(S, m.winner)) + '</div>';
  const preview = i => '<div class="bm">' + ahead(cur[2 * i]) + ahead(cur[2 * i + 1]) + '</div>';
  let cols = '';
  for (let r = 1; r <= R; r++) {
    const ms = rounds[r - 1] || Array(size >> r).fill(null);
    cols += '<div class="col' + (r === S.round && S.champion == null ? ' cur' : '') + '"><h3>' + roundName(r, R) + '</h3><div class="colbody">'
      + ms.map((m, i) => m ? bracketMatch(S, m) : r === rounds.length + 1 ? preview(i) : bracketMatch(S, null)).join('') + '</div></div>';
  }
  $('bracket').innerHTML = cols;
  // Shrink bracket text until the biggest column fits the screen height.
  const b = $('bracket');
  let fs = parseFloat(getComputedStyle(document.body).fontSize);
  b.style.fontSize = fs + 'px';
  while (fs > 8 && b.scrollHeight > b.clientHeight) b.style.fontSize = (fs -= 0.5) + 'px';
}

async function poll() {
  try {
    const txt = await (await fetch('/api/state', {cache: 'no-store'})).text();
    if (txt !== last) { last = txt; const S = JSON.parse(txt); render(S); handleAnnounce(S); }
    $('snd').textContent = soundOn && audio && audio.state !== 'running' ? '🔇 Click once to enable sound' : '';
    $('upd').textContent = 'Live · ' + new Date().toLocaleTimeString([], {hour: '2-digit', minute: '2-digit'});
  } catch (e) {
    last = null;
    $('upd').textContent = 'Reconnecting…';
  }
  setTimeout(poll, 2000);
}
// --- Announcements ---
const ANN_MS = 12000;
document.documentElement.style.setProperty('--ann-ms', ANN_MS + 'ms');
let annSeq = null, annTimer = null, soundOn = true, audio = null;
try { audio = new AudioContext(); } catch (e) {}
// Browsers keep audio muted until someone clicks the page once.
addEventListener('click', () => audio && audio.resume());
window.chimes = 0;  // count of chimes actually played (used by tests)

function chime() {
  if (!soundOn || !audio || audio.state !== 'running') return;
  const t = audio.currentTime;
  [[880, 0], [1320, .18]].forEach(([f, d]) => {
    const o = audio.createOscillator(), g = audio.createGain();
    o.type = 'sine'; o.frequency.value = f;
    g.gain.setValueAtTime(0, t + d); g.gain.linearRampToValueAtTime(.35, t + d + .02); g.gain.exponentialRampToValueAtTime(.001, t + d + .9);
    o.connect(g).connect(audio.destination); o.start(t + d); o.stop(t + d + 1);
  });
  window.chimes++;
}
const hideAnn = () => { clearTimeout(annTimer); $('ann').classList.remove('show'); };
const findMatch = (S, id) => (S.rounds || []).slice().reverse().flat().find(m => m.id === id);

function handleAnnounce(S) {
  soundOn = S.sound !== false;
  const a = S.announce;
  if (annSeq === null) { annSeq = a ? a.seq : 0; return; }  // page just opened: never replay an old announcement
  const m = a && a.match != null ? findMatch(S, a.match) : null;
  if (!a || a.seq === annSeq) { if (!m || m.done) hideAnn(); return; }  // same announcement: hide once the match finishes
  annSeq = a.seq;
  if (!m || m.done) return hideAnn();  // Dismiss, or a match that already has a result
  $('annTour').textContent = S.name || '';
  $('annKick').textContent = m.live ? 'PLAY NOW' : 'NEXT MATCH';
  $('annKick').className = 'ann-kick' + (m.live ? '' : ' next');
  $('ann').classList.toggle('next', !m.live);
  $('annP1').innerHTML = nm(S, m.p1);
  $('annP2').innerHTML = nm(S, m.p2);
  $('annMatch').innerHTML = 'Match <b>' + m.id + '</b>';
  $('annStn').innerHTML = m.station ? 'Station <b class="stn-b">' + esc(m.station) + '</b>' : '';
  const el = $('ann');
  el.classList.remove('show'); void el.offsetWidth; el.classList.add('show');  // restart the animation
  chime();
  clearTimeout(annTimer);
  annTimer = setTimeout(hideAnn, ANN_MS);
}

if (!/^(localhost|127\.)/.test(location.hostname)) $('follow').textContent = 'Follow on your phone: ' + location.host;
document.addEventListener('dblclick', () => document.fullscreenElement ? document.exitFullscreen() : document.documentElement.requestFullscreen());
addEventListener('resize', () => { if (last) render(JSON.parse(last)); });
poll();
</script></body></html>"""


# --- GUI CLASS IMPLEMENTATION ---

class TournamentGUI:
    def __init__(self, master):
        self.master = master
        master.title("Single-Elimination Tournament Manager")
        master.geometry("800x600")

        self.tournament_generator = None
        self.current_round = 0
        
        # Apply a simple style
        style = ttk.Style()
        style.configure('TFrame', background='#f0f0f0')
        style.configure('TLabel', background='#f0f0f0', font=('Arial', 10))
        style.configure('TButton', font=('Arial', 10, 'bold'))
        
        # Main frames
        self.input_frame = ttk.Frame(master, padding="10")
        self.input_frame.pack(side="top", fill="x")

        # Match area scrolls: at 800x600 only ~3 matches fit, which cut off Call/Swap/Advance in 8+ player brackets.
        sim_outer = ttk.Frame(master)
        sim_outer.pack(side="top", fill="both", expand=True)
        canvas = tk.Canvas(sim_outer, highlightthickness=0, background='#f0f0f0')
        scrollbar = ttk.Scrollbar(sim_outer, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        self.sim_frame = ttk.Frame(canvas, padding="10")
        sim_window = canvas.create_window((0, 0), window=self.sim_frame, anchor="nw")
        self.sim_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda e: canvas.itemconfigure(sim_window, width=e.width))
        wheel = lambda e: canvas.yview_scroll(-1 if e.delta > 0 else 1, "units")
        canvas.bind("<Enter>", lambda e: canvas.bind_all("<MouseWheel>", wheel))
        canvas.bind("<Leave>", lambda e: canvas.unbind_all("<MouseWheel>"))
        self.sim_canvas = canvas
        
        self.status_label = ttk.Label(self.sim_frame, text="Status: Register Teams", font=('Arial', 14, 'bold'), anchor='center')
        self.status_label.pack(pady=10)

        # TV announcement state: seq goes up on every new announcement so the display knows to show it once.
        self.announce = None
        self.announced_ids = set()
        self.tv_sound = tk.BooleanVar(value=True)

        self._create_input_widgets()

        self.state_bytes = b"{}"
        self.qr_win = None
        self.server = start_web_server(lambda: self.state_bytes)
        self.base_url = f"http://{lan_ip()}:{self.server.server_address[1]}" if self.server else None
        self.url_label.config(text=f"Player pages: {self.base_url}   TV display: {self.base_url}/display   (same Wi-Fi as this laptop)" if self.server
                              else "Web server could not start (ports 8000-8009 busy)")
        self._try_resume()

    def _changed(self):
        """Call after every tournament change: auto-saves and refreshes what the player pages see."""
        gen = self.tournament_generator
        self.state_bytes = json.dumps(build_state(gen, announce=self.announce, sound=self.tv_sound.get())).encode()
        if gen:
            try:
                save_tournament(gen)
            except OSError as e:
                messagebox.showerror("Save failed", f"Could not save the tournament: {e}")

    def _try_resume(self):
        if not os.path.exists(SAVE_PATH):
            return
        try:
            gen = load_tournament()
        except Exception as e:
            archive_save()
            messagebox.showerror("Save unreadable", f"Couldn't read the last save ({e}). It was kept as a backup next to the app.")
            return
        stage = f"round {gen.current_round}" if gen.rounds else "check-in"
        if gen.champion:
            stage = f"finished, champion {gen.champion.name}"
        if not messagebox.askyesno("Resume tournament?", f"Resume '{gen.name}' ({len(gen.teams)} players, {stage})?\n\n"
                                   "No = start a new tournament. The old save is kept as a backup."):
            archive_save()
            return
        self.tournament_generator = gen
        self.master.title(f"{gen.name} - Tournament Manager")
        self.name_entry.delete(0, tk.END)
        self.name_entry.insert(0, gen.name)
        self._refresh_team_list()
        if gen.rounds:
            self.start_btn.config(state=tk.DISABLED)
            self.name_entry.config(state=tk.DISABLED)
            self.current_round = gen.current_round
            if gen.champion:
                self._show_champion(gen.champion, announce=False)
            else:
                self._display_round()
        elif len(gen.teams) >= 2:
            self.start_btn.config(state=tk.NORMAL)

    def _player_url(self, team):
        return f"{self.base_url}/p/{self.tournament_generator.teams.index(team)}"

    def _show_qr(self, team):
        """One reusable QR window: always shows the most recent player, so it never piles up windows."""
        if not self.server:
            return
        if not (self.qr_win and self.qr_win.winfo_exists()):
            self.qr_win = tk.Toplevel(self.master)
            self.qr_win.title("Scan for your bracket")
            self.qr_name = ttk.Label(self.qr_win, font=('Arial', 18, 'bold'))
            self.qr_name.pack(pady=(10, 0))
            self.qr_img = ttk.Label(self.qr_win)
            self.qr_img.pack(padx=20, pady=10)
            self.qr_url = ttk.Label(self.qr_win, font=('Arial', 12))
            self.qr_url.pack(pady=(0, 10))
        url = self._player_url(team)
        self.qr_photo = qr_photo(url)  # keep a reference or Tk drops the image
        self.qr_name.config(text=team.name)
        self.qr_img.config(image=self.qr_photo)
        self.qr_url.config(text=url)
        self.qr_win.lift()

    def _show_qr_gui(self):
        team = self._selected_team()
        if team:
            self._show_qr(team)

    def _create_input_widgets(self):
        # --- Tournament Name Input ---
        ttk.Label(self.input_frame, text="Tournament Name:").grid(row=0, column=0, padx=5, pady=5, sticky="w")
        self.name_entry = ttk.Entry(self.input_frame, width=30)
        self.name_entry.insert(0, "Community Cup")
        self.name_entry.grid(row=0, column=1, padx=5, pady=5, sticky="w")

        # --- Team Registration Input ---
        ttk.Label(self.input_frame, text="Team Name:").grid(row=1, column=0, padx=5, pady=5, sticky="w")
        self.team_entry = ttk.Entry(self.input_frame, width=30)
        self.team_entry.grid(row=1, column=1, padx=5, pady=5, sticky="w")
        
        ttk.Label(self.input_frame, text="Rank (1=Best):").grid(row=2, column=0, padx=5, pady=5, sticky="w")
        self.rank_entry = ttk.Entry(self.input_frame, width=10)
        self.rank_entry.insert(0, "1")
        self.rank_entry.grid(row=2, column=1, padx=5, pady=5, sticky="w")
        
        # Buttons
        add_btn = ttk.Button(self.input_frame, text="Add Team", command=self._add_team_gui)
        add_btn.grid(row=1, column=2, rowspan=2, padx=10, pady=5, sticky="w")
        
        self.start_btn = ttk.Button(self.input_frame, text="START TOURNAMENT", command=self._start_tournament_gui, state=tk.DISABLED)
        self.start_btn.grid(row=0, column=3, rowspan=3, padx=20, pady=5, sticky="nsew")

        # --- Registered Teams Display ---
        ttk.Label(self.input_frame, text="Registered Teams:").grid(row=3, column=0, padx=5, pady=5, sticky="nw")
        self.team_listbox = tk.Listbox(self.input_frame, height=5, width=40)
        self.team_listbox.grid(row=4, column=0, columnspan=2, padx=5, pady=5, sticky="nsew")
        self.team_listbox.bind("<Double-Button-1>", lambda e: self._toggle_checkin_gui())

        # --- Check-in controls ---
        checkin_frame = ttk.Frame(self.input_frame)
        checkin_frame.grid(row=4, column=2, columnspan=2, padx=5, sticky="nw")
        ttk.Button(checkin_frame, text="Check In / Undo", command=self._toggle_checkin_gui).pack(fill="x", pady=2)
        ttk.Button(checkin_frame, text="Drop Player", command=self._drop_player_gui).pack(fill="x", pady=2)
        ttk.Button(checkin_frame, text="Show QR / Link", command=self._show_qr_gui).pack(fill="x", pady=2)
        self.checkin_label = ttk.Label(checkin_frame, text="Checked in: 0/0")
        self.checkin_label.pack(pady=4)

        self.url_label = ttk.Label(self.input_frame, text="", foreground="#1a5fb4")
        self.url_label.grid(row=5, column=0, columnspan=3, padx=5, sticky="w")
        ttk.Button(self.input_frame, text="Open TV Display",
                   command=lambda: self.server and webbrowser.open(f"{self.base_url}/display")).grid(row=5, column=3, padx=5, sticky="e")
        ann_frame = ttk.Frame(self.input_frame)
        ann_frame.grid(row=6, column=0, columnspan=4, padx=5, sticky="e")
        ttk.Checkbutton(ann_frame, text="TV sound", variable=self.tv_sound, command=self._changed).pack(side="left", padx=5)
        ttk.Button(ann_frame, text="Dismiss Announcement", command=lambda: self._announce(None)).pack(side="left", padx=5)

        self.input_frame.grid_columnconfigure(1, weight=1)
        self.input_frame.grid_rowconfigure(4, weight=1)

    def _add_team_gui(self):
        """Handles adding a team from the GUI input fields."""
        name = self.team_entry.get().strip()
        rank_str = self.rank_entry.get().strip()
        
        if not name:
            messagebox.showerror("Error", "Please enter a team name.")
            return

        try:
            rank = int(rank_str) if rank_str else 99
        except ValueError:
            messagebox.showerror("Error", "Rank must be a number.")
            return

        # Initialize generator if first team is added
        if not self.tournament_generator:
            tourney_name = self.name_entry.get() or "Community Cup"
            t_start = datetime.now() + timedelta(minutes=10)
            self.tournament_generator = TournamentGenerator(tourney_name, t_start)
            self.master.title(f"{tourney_name} - Tournament Manager")

        if self.current_round:
            # Tournament running: this is a late arrival.
            if not self._late_entry(Team(name, rank)):
                return
        else:
            self.tournament_generator.add_team(name, rank)

        # Clear inputs and focus
        self.team_entry.delete(0, tk.END)
        self.rank_entry.delete(0, tk.END)
        self.team_entry.focus()
        self._refresh_team_list()

        # Enable start button if at least 2 teams
        if not self.current_round and len(self.tournament_generator.teams) >= 2:
            self.start_btn.config(state=tk.NORMAL)

    def _refresh_team_list(self):
        teams = self.tournament_generator.teams
        self.team_listbox.delete(0, tk.END)
        for t in teams:
            mark = "✖ DROPPED" if t.dropped else ("✔" if t.checked_in else "·")
            self.team_listbox.insert(tk.END, f"{mark}  {t.name} (Rank: {t.rank})")
        checked = sum(t.checked_in and not t.dropped for t in teams)
        self.checkin_label.config(text=f"Checked in: {checked}/{len(teams)}")
        self._changed()  # every roster change passes through here

    def _selected_team(self):
        sel = self.team_listbox.curselection()
        if not self.tournament_generator or not sel:
            messagebox.showinfo("Select a player", "Select a player in the list first.")
            return None
        return self.tournament_generator.teams[sel[0]]

    def _late_entry(self, team):
        try:
            msg = self.tournament_generator.add_late_player(team)
        except ValueError as e:
            self._refresh_team_list()
            messagebox.showerror("Can't add player", str(e))
            return False
        self._display_round()
        self._show_qr(team)
        messagebox.showinfo("Late arrival", msg)
        return True

    def _toggle_checkin_gui(self):
        team = self._selected_team()
        if not team or team.dropped:
            return
        if not self.current_round:
            team.checked_in = not team.checked_in
            if team.checked_in:
                self._show_qr(team)
        elif team.checked_in:
            messagebox.showinfo("Already in", f"{team.name} is already in the bracket. Use Drop Player to remove them.")
        else:
            self._late_entry(team)
        self._refresh_team_list()

    def _drop_player_gui(self):
        team = self._selected_team()
        if not team or team.dropped:
            return
        if not messagebox.askyesno("Drop player", f"Drop {team.name}? Their opponent will advance."):
            return
        try:
            self.tournament_generator.drop_player(team)
        except ValueError as e:
            messagebox.showerror("Can't drop yet", str(e))
            return
        self._refresh_team_list()
        if self.current_round:
            self._display_round()

    def _start_tournament_gui(self):
        """Initiates the bracket generation and displays the first round."""
        gen = self.tournament_generator
        if not gen or len(gen.active_teams()) < 2:
            messagebox.showerror("Error", "You need at least 2 checked-in teams to start the tournament.")
            return

        no_shows = [t.name for t in gen.teams if not t.checked_in and not t.dropped]
        if no_shows and not messagebox.askyesno(
                "Not checked in", f"{len(no_shows)} not checked in and will be left out:\n"
                + ", ".join(no_shows) + "\n\nThey can still join as late arrivals in round 1. Start?"):
            return

        success = gen.generate_bracket()
        if not success:
            return

        # Lock tournament setup; player entry stays open for late arrivals and drops.
        self.start_btn.config(state=tk.DISABLED)
        self.name_entry.config(state=tk.DISABLED)

        # Start simulation display
        self.current_round = 1
        self._display_round()

    def _clear_simulation_frame(self):
        """Clears all dynamic match widgets from the simulation frame."""
        for widget in self.sim_frame.winfo_children():
            # Keep the status label
            if widget != self.status_label:
                widget.destroy()

    def _display_round(self):
        """Displays all pending matches for the current round."""
        self._clear_simulation_frame()
        self._changed()  # every bracket change redraws through here

        matches = self.tournament_generator.rounds.get(self.current_round)
        if not matches:
            self.status_label.config(text="Error: No matches found.")
            return
            
        self.status_label.config(text=f"Round {self.current_round} - {self.tournament_generator.name}")

        match_frame = ttk.Frame(self.sim_frame)
        match_frame.pack(fill="x", pady=10)

        for match in matches:
            if match.winner and match.is_bye():
                # Display auto-advance matches
                match_label = ttk.Label(match_frame, text=f"Match {match.id}: {match.winner.name} (Auto-Advance)")
                match_label.pack(pady=5, padx=10, fill='x')
                continue # Skip buttons for Byes

            if match.winner:
                loser = match.team2 if match.winner is match.team1 else match.team1
                ttk.Label(match_frame, text=f"Match {match.id}: {match.winner.name} def. {loser.name} ✔").pack(pady=5, padx=10, fill='x')
                continue

            if not match.winner:
                # Display match details and winner buttons
                match_container = ttk.Frame(match_frame, relief=tk.GROOVE, borderwidth=1, padding=5)
                match_container.pack(pady=8, padx=20, fill='x')

                live = f"  ● LIVE{' @ Station ' + match.station if match.station else ''}" if match.in_progress else ""
                ttk.Label(match_container, text=f"Match {match.id} | {match.team1.name} vs {match.team2.name}{live}").pack(side='left', padx=10)

                call_btn = ttk.Button(match_container, text="Un-call" if match.in_progress else "Call",
                                      command=lambda m=match: self._toggle_call_gui(m))
                call_btn.pack(side='right', padx=5)
                ttk.Button(match_container, text="Announce",
                           command=lambda m=match: self._announce(m)).pack(side='right', padx=5)

                # Buttons for Winner selection
                random_btn = ttk.Button(match_container, text="Random Win (R)", 
                                        command=lambda m=match: self._select_winner(m, 'r'))
                random_btn.pack(side='right', padx=5)

                t2_btn = ttk.Button(match_container, text=f"{match.team2.name} Win (2)", 
                                    command=lambda m=match: self._select_winner(m, '2'))
                t2_btn.pack(side='right', padx=5)

                t1_btn = ttk.Button(match_container, text=f"{match.team1.name} Win (1)", 
                                    command=lambda m=match: self._select_winner(m, '1'))
                t1_btn.pack(side='right', padx=5)

        # Bracket editing: swap any two slots in matches that haven't started or finished.
        self.swap_slots = self.tournament_generator.editable_slots()
        if len(self.swap_slots) >= 2:
            labels = [f"M{m.id} {'P1' if a == 'team1' else 'P2'}: {getattr(m, a).name}" for m, a in self.swap_slots]
            swap_frame = ttk.Frame(self.sim_frame)
            swap_frame.pack(pady=5)
            ttk.Label(swap_frame, text="Edit bracket — swap").pack(side='left')
            self.swap_a = ttk.Combobox(swap_frame, values=labels, state="readonly", width=24)
            self.swap_a.pack(side='left', padx=5)
            ttk.Label(swap_frame, text="with").pack(side='left')
            self.swap_b = ttk.Combobox(swap_frame, values=labels, state="readonly", width=24)
            self.swap_b.pack(side='left', padx=5)
            ttk.Button(swap_frame, text="Swap", command=self._swap_gui).pack(side='left')

        # Check if all matches in the current round are completed (excluding Byes)
        all_completed = all(m.winner for m in matches)
        if all_completed:
            advance_btn = ttk.Button(self.sim_frame, text="Advance to Next Round", 
                                     command=self._advance_round_gui)
            advance_btn.pack(pady=20)
        else:
            # Check for matches that were completed but not Byes (e.g. manually selected)
            if any(m.winner and m.team2.name != "BYE" for m in matches):
                ttk.Label(self.sim_frame, text="Select winners for all matches to advance.").pack(pady=5)
            
    def _select_winner(self, match, choice):
        """Sets the winner for a match based on button click or random selection."""
        if choice == '1':
            winner = match.team1
        elif choice == '2':
            winner = match.team2
        elif choice == 'r':
            winner = random.choice([match.team1, match.team2])
            
        match.set_winner(winner)

        # Redraw the round to show the result and check if the 'Advance' button should appear
        self._display_round()

    def _toggle_call_gui(self, match):
        if match.in_progress:
            match.in_progress = False
        else:
            station = simpledialog.askstring("Call match", f"Station for Match {match.id} (optional):", parent=self.master)
            if station is None:
                return
            self.tournament_generator.call_match(match, station.strip())
            if self._ann_key(match) not in self.announced_ids:  # auto-announce once; use Announce to repeat on purpose
                self._announce(match)
        self._display_round()

    def _announce(self, match):
        """Shows `match` on the TV overlay, or hides the overlay when match is None. Never changes the bracket."""
        self.announce = {"seq": (self.announce or {}).get("seq", 0) + 1, "match": match.id if match else None}
        if match:
            self.announced_ids.add(self._ann_key(match))
        self._changed()

    @staticmethod
    def _ann_key(match):
        return (match.id, match.team1.name, match.team2.name)

    def _swap_gui(self):
        a, b = self.swap_a.current(), self.swap_b.current()
        if a < 0 or b < 0 or a == b:
            messagebox.showinfo("Swap", "Pick two different slots.")
            return
        try:
            self.tournament_generator.swap_slots(*self.swap_slots[a], *self.swap_slots[b])
        except ValueError as e:
            messagebox.showerror("Can't edit", str(e))
        self._display_round()

    def _advance_round_gui(self):
        """Calls the backend logic to set up the next round or crown a champion."""
        matches = self.tournament_generator.rounds.get(self.current_round)
        if not all(m.winner for m in matches):
            messagebox.showwarning("Incomplete Round", "All matches in the current round must have a winner before advancing.")
            return

        champion = self.tournament_generator.advance_round(matches)
        
        if champion:
            self._show_champion(champion)
        else:
            self.current_round = self.tournament_generator.current_round
            self._display_round()

    def _show_champion(self, champion, announce=True):
        self._clear_simulation_frame()
        self._changed()
        self.status_label.config(text=f"👑 TOURNAMENT CHAMPION: {champion.name} 👑", foreground="green")
        if announce:
            messagebox.showinfo("Champion", f"The tournament champion is {champion.name}!")

# --- MAIN EXECUTION ---
if __name__ == "__main__":
    if getattr(sys, "frozen", False):
        # A packaged .exe has no console window, so errors would vanish. Send them to a log file instead.
        os.makedirs(DATA_DIR, exist_ok=True)
        sys.stdout = sys.stderr = open(LOG_PATH, "a", buffering=1, encoding="utf-8")
        print(f"--- Tournament Manager started {datetime.now():%Y-%m-%d %H:%M:%S}")
    root = tk.Tk()
    app = TournamentGUI(root)
    root.mainloop()
