#!/usr/bin/env python3
"""Grid search for :class:`~hanabi.ai.five_player_recommendation.HintThresholds` (strong/medium/weak)."""

from __future__ import annotations

import argparse
import statistics
import time
from typing import Dict, List, Tuple

from hanabi.ai.five_player_recommendation import FivePlayerRecommendationPlayer, HintThresholds
from hanabi.core.game import create_ai_simulation_game_settings
from hanabi.core.game_field import GameField


def _presets() -> Dict[str, HintThresholds]:
    """Candidate strong/medium/weak gates for split USELESS vs DISPENSABLE discard scoring."""
    return {
        "default": HintThresholds(),
        "comb2_med_ndd1": HintThresholds(2, 1, 1, 1, 0, 1, strong_min_combined=2),
        "strong_nud1_np2_med_ndd1": HintThresholds(2, 1, 1, 1, 0, 1),
        "strong_nud1_np2_med_np1": HintThresholds(2, 1, 1, 0, 1, 1),
        "strong_nud1_sv1": HintThresholds(99, 1, 1, 1, 1, 1),
        "strong_np2_sv1_med_ndd1": HintThresholds(2, 0, 1, 1, 0, 1),
        "strong_np2_nud1_med_ndd1": HintThresholds(2, 1, 1, 1, 0, 1),
        "strong_all_disc_med_np1": HintThresholds(2, 1, 1, 0, 1, 1),
        "med_ndd1_only": HintThresholds(99, 0, 99, 1, 0, 1),
        "med_np1_ndd1": HintThresholds(99, 0, 99, 1, 1, 1),
        "strong_comb3": HintThresholds(0, 0, 1, 0, 0, 1, strong_min_combined=3),
        "weak2": HintThresholds(2, 1, 1, 1, 1, 2),
        "weak0": HintThresholds(2, 1, 1, 1, 1, 0),
        "legacy_nd1_strong": HintThresholds(2, 0, 1, 1, 1, 1, strong_min_combined=1),
    }


def _run_batch(
    name: str,
    thresholds: HintThresholds,
    *,
    num_runs: int,
    seed: int,
) -> Tuple[float, float, int, int]:
    settings = create_ai_simulation_game_settings(5)
    field = GameField.create_from_settings(settings)

    def factory(player_index: int) -> FivePlayerRecommendationPlayer:
        return FivePlayerRecommendationPlayer(player_index, hint_thresholds=thresholds)

    results = field.run_experiment(
        {name: factory},
        num_runs=num_runs,
        save_records=False,
        random_seed=seed,
    )
    stats = results.summary[name]
    scores = [run.ai_results[name].score for run in results.runs]
    perfects = sum(1 for s in scores if 25 == s)
    return (
        stats.average_score,
        statistics.pstdev(scores) if 1 < len(scores) else 0.0,
        stats.worst_score,
        perfects,
    )


def _fmt_thresholds(th: HintThresholds) -> str:
    return (
        f"str:np>={th.strong_min_new_plays} nud>={th.strong_min_new_useless_discards} "
        f"sv>={th.strong_min_saves} comb>={th.strong_min_combined} | "
        f"med:ndd>={th.medium_min_new_dispensable_discards} np>={th.medium_min_new_plays} "
        f"comb>={th.medium_min_combined} | weak>={th.weak_min_total}"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Grid-search 5p mini-rec hint thresholds.")
    parser.add_argument("--runs", type=int, default=150, help="Games per preset (default: 150).")
    parser.add_argument("--seed", type=int, default=42, help="Base deck seed (default: 42).")
    parser.add_argument(
        "--validate",
        type=int,
        default=0,
        metavar="N",
        help="Re-run top presets with N games each (same seed).",
    )
    args = parser.parse_args()

    presets = _presets()
    rows: List[Tuple[str, HintThresholds, float, float, int, int, float]] = []

    t0 = time.perf_counter()
    for name, thresholds in presets.items():
        mean, stdev, worst, perfects = _run_batch(name, thresholds, num_runs=args.runs, seed=args.seed)
        rows.append((name, thresholds, mean, stdev, worst, perfects, time.perf_counter() - t0))

    rows.sort(key=lambda r: (-r[2], -r[5], r[4]))

    print(f"\n5p hint threshold grid ({args.runs} games/preset, seed={args.seed})")
    print(f"{'preset':<28} {'mean':>6} {'std':>5} {'worst':>5} {'perf':>5}")
    print("-" * 55)
    for name, th, mean, stdev, worst, perfects, _ in rows:
        print(f"{name:<28} {mean:6.2f} {stdev:5.2f} {worst:5d} {perfects:5d}")
    print("\nTop preset thresholds:")
    for name, th, mean, _, worst, perfects, _ in rows[:3]:
        print(f"  {name} mean={mean:.2f} worst={worst} perf={perfects}: {_fmt_thresholds(th)}")
    print(f"\nGrid elapsed: {time.perf_counter() - t0:.1f}s")

    if 0 < args.validate:
        top = rows[: min(3, len(rows))]
        print(f"\nValidation ({args.validate} games, seed={args.seed}) — top {len(top)}:")
        print(f"{'preset':<28} {'mean':>6} {'worst':>5} {'perf':>5}")
        print("-" * 48)
        for name, thresholds, _, _, _, _, _ in top:
            mean, _, worst, perfects = _run_batch(name, thresholds, num_runs=args.validate, seed=args.seed)
            print(f"{name:<28} {mean:6.2f} {worst:5d} {perfects:5d}")


if __name__ == "__main__":
    main()
