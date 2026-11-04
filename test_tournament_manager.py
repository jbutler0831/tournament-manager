"""Run: python3 -m unittest test_tournament_manager.py"""
import unittest
from datetime import datetime

from tournament_manager import Team, TournamentGenerator, build_state, load_tournament, save_tournament, start_web_server


def make(names, checked=None):
    g = TournamentGenerator("Test", datetime.now())
    for i, n in enumerate(names, 1):
        g.add_team(n, i)
        g.teams[-1].checked_in = checked is None or n in checked
    g.generate_bracket()
    return g


def team(g, name):
    return next(t for t in g.teams if t.name == name)


def players(g, rnd=1):
    return {t.name for m in g.rounds[rnd] for t in (m.team1, m.team2)} - {"BYE"}


class CheckInTests(unittest.TestCase):
    def test_no_shows_left_out(self):
        g = make(["A", "B", "C", "D"], checked={"A", "B", "C"})
        self.assertEqual(players(g), {"A", "B", "C"})

    def test_late_arrival_fills_bye(self):
        g = make(["A", "B", "C"])  # 4-slot bracket: A gets a BYE
        g.rounds[1][1].set_winner(g.rounds[1][1].team1)  # play has started elsewhere
        msg = g.add_late_player(Team("D", 4))
        self.assertIn("placed", msg)
        self.assertEqual(players(g), {"A", "B", "C", "D"})
        bye_match = next(m for m in g.rounds[1] if "D" in (m.team1.name, m.team2.name))
        self.assertIsNone(bye_match.winner)

    def test_full_bracket_reseeds_only_before_play(self):
        g = make(["A", "B", "C", "D"])
        self.assertIn("re-seeded", g.add_late_player(Team("E", 5)))
        self.assertEqual(len(g.rounds[1]), 4)

        g = make(["A", "B", "C", "D"])
        g.call_match(g.rounds[1][0])
        with self.assertRaises(ValueError):
            g.add_late_player(Team("E", 5))
        self.assertTrue(g.rounds[1][0].in_progress)


class EditSafetyTests(unittest.TestCase):
    def test_drop_gives_walkover(self):
        g = make(["A", "B", "C", "D"])
        m = next(m for m in g.rounds[1] if "A" in (m.team1.name, m.team2.name))
        opp = m.team2 if m.team1.name == "A" else m.team1
        g.drop_player(team(g, "A"))
        self.assertIs(m.winner, opp)

    def test_drop_refused_mid_match(self):
        g = make(["A", "B", "C", "D"])
        m = next(m for m in g.rounds[1] if "A" in (m.team1.name, m.team2.name))
        g.call_match(m, "2")
        with self.assertRaises(ValueError):
            g.drop_player(team(g, "A"))
        self.assertFalse(team(g, "A").dropped)
        self.assertTrue(m.in_progress)

    def test_dropped_winner_becomes_bye_next_round(self):
        g = make(["A", "B", "C", "D"])
        for m in g.rounds[1]:
            m.set_winner(m.team1)
        winners = [m.winner for m in g.rounds[1]]
        g.drop_player(winners[0])
        self.assertEqual([m.winner for m in g.rounds[1]], winners)  # completed results untouched
        champion = g.advance_round(g.rounds[1])
        self.assertIsNone(champion)
        self.assertIs(g.rounds[2][0].winner, winners[1])
        self.assertEqual(g.rounds[2][0].id, 3)  # match numbers continue across rounds

    def test_swap_blocked_on_live_and_done(self):
        g = make(["A", "B", "C", "D", "E", "F", "G", "H"])
        live, done, open1, open2 = g.rounds[1]
        g.call_match(live, "1")
        done.set_winner(done.team1)
        for m in (live, done):
            with self.assertRaises(ValueError):
                g.swap_slots(m, "team1", open1, "team1")
        self.assertEqual(len(g.editable_slots()), 4)
        a, b = open1.team1, open2.team2
        g.swap_slots(open1, "team1", open2, "team2")
        self.assertIs(open1.team1, b)
        self.assertIs(open2.team2, a)


class ReleaseRegressionTests(unittest.TestCase):
    def test_champion_survives_dropping_after_final(self):
        g = make(["A", "B"])
        final = g.rounds[1][0]
        final.set_winner(final.team1)
        g.drop_player(final.team1)
        self.assertIs(g.advance_round(g.rounds[1]), final.team1)

    def test_archive_never_overwrites(self):
        import os, tempfile
        from tournament_manager import archive_save
        path = os.path.join(tempfile.mkdtemp(), "t.pkl")
        made = []
        for i in range(3):  # three archives within the same second
            open(path, "w").write(str(i))
            made.append(archive_save(path))
        self.assertEqual(len(set(made)), 3)
        self.assertEqual([open(m).read() for m in made], ["0", "1", "2"])


class SaveAndWebTests(unittest.TestCase):
    def test_save_roundtrip_keeps_links(self):
        import os, tempfile
        g = make(["A", "B", "C"])
        g.call_match(g.rounds[1][1], "2")
        path = os.path.join(tempfile.mkdtemp(), "t.pkl")
        save_tournament(g, path)
        g2 = load_tournament(path)
        m = g2.rounds[1][1]
        self.assertTrue(m.in_progress)
        self.assertEqual(m.station, "2")
        self.assertIn(m.team1, g2.teams)  # same objects, not copies
        self.assertFalse(os.path.exists(path + ".tmp"))

    def test_announce_is_display_only(self):
        g = make(["A", "B", "C", "D"])
        before = build_state(g)
        s = build_state(g, announce={"seq": 3, "match": 1}, sound=False)
        self.assertEqual(s["announce"], {"seq": 3, "match": 1})
        self.assertFalse(s["sound"])
        self.assertEqual(s["rounds"], before["rounds"])

    def test_server_is_read_only(self):
        import json, urllib.request, urllib.error
        g = make(["A", "B", "C"])
        state = json.dumps(build_state(g)).encode()
        srv = start_web_server(lambda: state, port=0)
        base = f"http://127.0.0.1:{srv.server_address[1]}"
        try:
            s = json.load(urllib.request.urlopen(base + "/api/state"))
            self.assertEqual([p["name"] for p in s["players"]], ["A", "B", "C"])
            self.assertEqual(s["rounds"][0][0]["p2"], None)  # BYE
            self.assertIn(b"viewport", urllib.request.urlopen(base + "/p/1").read())
            self.assertIn(b"Live now", urllib.request.urlopen(base + "/display").read())
            for path, data in (("/nope", None), ("/api/state", b"x=1")):
                with self.assertRaises(urllib.error.HTTPError):
                    urllib.request.urlopen(base + path, data=data)
        finally:
            srv.shutdown()


if __name__ == "__main__":
    unittest.main()
