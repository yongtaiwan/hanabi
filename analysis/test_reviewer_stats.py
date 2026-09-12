"""Checks for the reviewer analysis, including independent replay of edge cases."""
import gzip
import json
from pathlib import Path
import unittest

from reviewer_stats import outcome, wilson
from hanabi.tools.experiment_outcome import replay_summary


class ReviewerStatsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path = Path(__file__).parent / "reviewer-stats-2026-09-12" / "evidence.json"
        if path.exists():
            cls.data = json.loads(path.read_text())
        else:
            with gzip.open(str(path) + ".gz", "rt") as stream:
                cls.data = json.load(stream)

    def test_partition_and_score_rule(self):
        for g in self.data["games"]:
            self.assertEqual(g["paper_score"], 0 if g["lives_remaining"] == 0 else g["raw_score"])
            self.assertEqual(g["category"], outcome(g["paper_score"] == 25, g["lives_remaining"], g["needed_last_copy_lost"]))
        for r in self.data["summary"]:
            self.assertEqual(sum(r["outcomes"].values()), r["games"])
            self.assertEqual(r["wins"], r["outcomes"].get("perfect", 0))
            self.assertLessEqual(r["zero_hint_turns"], r["turns"])

    def test_same_seed_decks(self):
        decks = {}
        for g in self.data["games"]:
            key = (g["players"], g["seed"])
            if key in decks:
                self.assertEqual(g["deck"], decks[key])
            decks[key] = g["deck"]

    def test_independent_replay(self):
        selected = [g for g in self.data["games"] if g["seed"] in (42, 43, 100, 541)
                    or g["lives_remaining"] == 0
                    or any(t["last_resort_play"] for t in g["turns"])]
        for g in selected:
            history = {"settings": {"num_players": g["players"], "auto_end_when_no_points_possible": True},
                       "deck": g["deck"], "moves": [t["move"] for t in g["turns"]], "final_score": g["raw_score"]}
            result = replay_summary(history)
            self.assertEqual(result.score, g["raw_score"])
            self.assertEqual(result.lost_all_lives, g["lives_remaining"] == 0)
            self.assertEqual(result.lost_critical, g["needed_last_copy_lost"])

    def test_wilson_interval(self):
        for count in (0, 182, 385, 500):
            low, high = wilson(count, 500)
            self.assertLessEqual(low, count / 500 + 1e-12)
            self.assertGreaterEqual(high, count / 500 - 1e-12)
            self.assertGreaterEqual(low, -1e-12)
            self.assertLessEqual(high, 1 + 1e-12)


if __name__ == "__main__":
    unittest.main()
