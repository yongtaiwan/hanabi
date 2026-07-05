#!/usr/bin/env python3
"""Compare :class:`~hanabi.ai.five_player_recommendation.PlayFollowGate` presets on 5p mini-rec."""

from __future__ import annotations

import argparse
import statistics
import time

from hanabi.ai.five_player_recommendation import FivePlayerRecommendationPlayer, PlayFollowGate
from hanabi.core.game import create_standard_game_settings
from hanabi.core.game_field import GameField


def _presets() -> dict[str, PlayFollowGate]:
    return {
        "current_loose": PlayFollowGate(),  # ps>=0 or errors<2 (any ps)
        "paper_ps1": PlayFollowGate.paper(),  # ps in {0,1} and errors<2
        "strict_ps0": PlayFollowGate.strict_zero(),
        "no_gate": PlayFollowGate.none(),
        "loosen_errors3": PlayFollowGate(max_plays_since_hint=999, max_errors_exclusive=3),
        "loosen_ps2": PlayFollowGate(max_plays_since_hint=2, max_errors_exclusive=2),
        "paper_loosen_err3": PlayFollowGate(max_plays_since_hint=1, max_errors_exclusive=3),
    }


def _run(name: str, gate: PlayFollowGate, *, num_runs: int, seed: int) -> tuple[float, int, int]:
    field = GameField.create_from_settings(create_standard_game_settings(5))

    def factory(i: int) -> FivePlayerRecommendationPlayer:
        return FivePlayerRecommendationPlayer(i, play_follow_gate=gate)

    results = field.run_experiment({name: factory}, num_runs=num_runs, save_records=False, random_seed=seed)
    stats = results.summary[name]
    scores = [run.ai_results[name].score for run in results.runs]
    perfects = sum(1 for s in scores if 25 == s)
    return stats.average_score, stats.worst_score, perfects


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", type=int, default=200)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    rows: list[tuple[str, PlayFollowGate, float, int, int]] = []
    t0 = time.perf_counter()
    for name, gate in _presets().items():
        mean, worst, perf = _run(name, gate, num_runs=args.runs, seed=args.seed)
        rows.append((name, gate, mean, worst, perf))

    rows.sort(key=lambda r: (-r[2], -r[4], r[3]))
    print(f"\n5p play-follow gate grid ({args.runs} games, seed={args.seed})")
    print(f"{'preset':<22} {'mean':>6} {'worst':>5} {'perf':>5}  gate (max_ps, err<)")
    print("-" * 65)
    for name, gate, mean, worst, perf in rows:
        print(
            f"{name:<22} {mean:6.2f} {worst:5d} {perf:5d}  "
            f"({gate.max_plays_since_hint}, {gate.max_errors_exclusive})"
        )
    print(f"\nElapsed: {time.perf_counter() - t0:.1f}s")


if __name__ == "__main__":
    main()
