"""Tests for experiment outcome replay and pair classification."""

import os
import unittest

from hanabi.core.game_field import AIStatistics, ExperimentResults, GameResult, RunResult
from hanabi.core.game_history import GameHistory
from hanabi.tools import experiment_outcome as eo


class TestExperimentOutcome(unittest.TestCase):
    """Replay real records and check classification invariants."""

    def setUp(self) -> None:
        self._repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

    def _path(self, *parts: str) -> str:
        return os.path.join(self._repo_root, *parts)

    def test_replay_random_2p_matches_final_score(self) -> None:
        """Short 2p Random record replays to the saved final score."""
        path = self._path(
            "game_records",
            "exp_ai_comparison",
            "20260405_155855",
            "2p",
            "games",
            "all-games",
            "run_000_ai_RandomPlayer.yaml",
        )
        s = eo.replay_summary(eo.load_history_file(path))
        self.assertEqual(0, s.score)
        self.assertFalse(s.perfect)
        self.assertTrue(s.lost_all_lives)

    def test_settings_from_history_overrides_hand_size(self) -> None:
        """Saved max_cards_in_hand is applied when reconstructing settings."""
        path = self._path(
            "game_records",
            "exp_ai_comparison",
            "20260405_160417",
            "5p",
            "games",
            "all-games",
            "run_000_ai_CommonSenseCheater.yaml",
        )
        data = eo.load_history_file(path)
        settings = GameHistory.settings_from_history_dict(data)
        self.assertEqual(5, settings.num_players)
        self.assertEqual(4, settings.max_cards_in_hand)

    def test_pair_cheater_perfect_ai_not_is_bucket_3(self) -> None:
        """When cheater hits perfect and AI does not, outcome uses AI subcodes (3.x)."""
        base = self._path(
            "game_records",
            "exp_ai_comparison",
            "20260405_160417",
            "5p",
            "games",
            "all-games",
        )
        code = eo.classify_pair_from_history_files(
            os.path.join(base, "run_000_ai_RecommendationPlayer.yaml"),
            os.path.join(base, "run_000_ai_CommonSenseCheater.yaml"),
        )
        self.assertEqual("3.3", code)

    def test_pair_both_below_perfect_uses_cheater_subcodes(self) -> None:
        """When cheater also misses perfect, outcome uses cheater subcodes (2.x)."""
        base = self._path(
            "game_records",
            "exp_ai_comparison",
            "20260405_160417",
            "5p",
            "games",
            "all-games",
        )
        code = eo.classify_pair_from_history_files(
            os.path.join(base, "run_002_ai_RecommendationPlayer.yaml"),
            os.path.join(base, "run_002_ai_CommonSenseCheater.yaml"),
        )
        self.assertEqual("2.4", code)

    def test_perfect_ai_yields_perfect_code(self) -> None:
        """AI replay at max score is classified as perfect regardless of pairing."""
        base = self._path(
            "game_records",
            "exp_ai_comparison",
            "20260405_160417",
            "5p",
            "games",
            "all-games",
        )
        perfect_data = eo.load_history_file(os.path.join(base, "run_000_ai_CommonSenseCheater.yaml"))
        imperfect_data = eo.load_history_file(os.path.join(base, "run_002_ai_RecommendationPlayer.yaml"))
        s_p = eo.replay_summary(perfect_data)
        s_i = eo.replay_summary(imperfect_data)
        target = eo.perfect_score_total(GameHistory.settings_from_history_dict(perfect_data))
        self.assertEqual("perfect", eo.classify_experiment_pair(s_p, s_i, perfect_target=target))

    def test_build_experiment_outcome_categories_payload(self) -> None:
        """Batch payload aggregates per-run classification vs CommonSenseCheater."""
        base = self._path(
            "game_records",
            "exp_ai_comparison",
            "20260405_160417",
            "5p",
            "games",
            "all-games",
        )

        def _gr(tail: str, score: int) -> GameResult:
            return GameResult(
                score=score,
                moves_count=1,
                duration_seconds=0.0,
                end_reason="test",
                game_record_path=os.path.join(base, tail),
            )

        dummy_stats = AIStatistics(
            games_played=2,
            average_score=18.0,
            best_score=25,
            worst_score=17,
            win_rate=0.0,
            std_dev=0.0,
            average_moves=10.0,
            average_duration=0.1,
        )
        runs = [
            RunResult(
                run_id=0,
                deck_seed=0,
                ai_results={
                    "RecommendationPlayer": _gr("run_000_ai_RecommendationPlayer.yaml", 19),
                    "CommonSenseCheater": _gr("run_000_ai_CommonSenseCheater.yaml", 25),
                },
            ),
            RunResult(
                run_id=2,
                deck_seed=2,
                ai_results={
                    "RecommendationPlayer": _gr("run_002_ai_RecommendationPlayer.yaml", 17),
                    "CommonSenseCheater": _gr("run_002_ai_CommonSenseCheater.yaml", 23),
                },
            ),
        ]
        results = ExperimentResults(
            experiment_id="fixture",
            settings={},
            num_runs=2,
            runs=runs,
            summary={
                "RecommendationPlayer": dummy_stats,
                "CommonSenseCheater": dummy_stats,
            },
        )
        payload = eo.build_experiment_outcome_categories_payload(results)
        if payload is None:
            self.fail("expected outcome payload")
        self.assertEqual("CommonSenseCheater", payload["baseline"])
        sub = payload["subjects"]["RecommendationPlayer"]
        by_code = {str(r["code"]): r for r in sub["outcomes"]}
        self.assertEqual(1, by_code["3.3"]["count"])
        self.assertEqual([0], by_code["3.3"]["game_numbers"])
        self.assertEqual([{"score": 19, "game_numbers": [0]}], by_code["3.3"]["games_by_score"])
        self.assertEqual(1, by_code["2.4"]["count"])
        self.assertEqual([2], by_code["2.4"]["game_numbers"])
        self.assertEqual([{"score": 17, "game_numbers": [2]}], by_code["2.4"]["games_by_score"])
        self.assertEqual(2, sum(int(r["count"]) for r in sub["outcomes"]))
        tip = sub.get("top_non_perfect_reason")
        self.assertIsNotNone(tip)
        self.assertTrue(str(tip).startswith("Tied at 1 games:"), tip)

    def test_games_by_score_groups_run_ids_ascending(self) -> None:
        """Non-perfect rows include subject scores bucketed low-to-high."""
        from hanabi.tools.experiment_outcome import OutcomeBreakdown, OutcomeRunRef, outcome_breakdown_to_yaml_dict

        counts = {c: 0 for c in ("perfect", "2.1", "2.2", "2.3", "2.4", "3.1", "3.2", "3.3", "3.4")}
        counts["perfect"] = 1
        counts["3.4"] = 3
        breakdown = OutcomeBreakdown(
            subject_ai="HintHandSubtype3P",
            baseline_ai="CommonSenseCheater",
            counts=counts,
            non_perfect_runs={
                "3.4": [
                    OutcomeRunRef(5, "a", "b", 20),
                    OutcomeRunRef(3, "a", "b", 20),
                    OutcomeRunRef(9, "a", "b", 21),
                ]
            },
        )
        row = next(r for r in outcome_breakdown_to_yaml_dict(breakdown)["outcomes"] if "3.4" == r["code"])
        self.assertEqual([3, 5, 9], row["game_numbers"])
        self.assertEqual(
            [{"score": 20, "game_numbers": [3, 5]}, {"score": 21, "game_numbers": [9]}],
            row["games_by_score"],
        )

    def test_mismatched_deck_asserts(self) -> None:
        """Paired classification requires identical deck and settings."""
        base = self._path(
            "game_records",
            "exp_ai_comparison",
            "20260405_160417",
            "5p",
            "games",
            "all-games",
        )
        a = eo.load_history_file(os.path.join(base, "run_000_ai_CommonSenseCheater.yaml"))
        b = eo.load_history_file(os.path.join(base, "run_002_ai_CommonSenseCheater.yaml"))
        with self.assertRaises(AssertionError):
            eo.classify_pair_from_histories(a, b)


if __name__ == "__main__":
    unittest.main()
