"""
Run AI comparison experiments for different player counts.

This script compares selected AIs on the same shuffled decks for 2–5-player games.
Use ``--ais`` to include only the bots you want (e.g. omit ``montecarlo`` for faster batches).
``recommendation`` runs only for 5-player settings; ``three_player_recommendation`` runs only
for 3-player settings (mod-7 mini variant); ``four_player_recommendation`` runs only for
4-player settings (mod-9 mini variant).
``commonsense_cheater`` (``CommonSenseCheater``) and ``paper_cheater`` (``PaperCheater``) are
for benchmarking only and are not offered in the GUI or console apps.

Folder layout:

    game_records/
      exp_ai_comparison/
        <timestamp>/
          settings.yaml                # experiment runner settings (player counts, runs, seed)
          summary.md                   # human-readable summary for this batch
          2p/
            settings.yaml
            statistics.yaml
          outcome_categories.yaml   # vs CommonSenseCheater (5p: cheater auto-run unless --no-outcome-baseline)
            games/
              all-games/
              <run_id>/
            ai/
              RandomPlayer/
              CommonSensePlayer/
              CommonSenseCheater/
              PaperCheater/
              RecommendationPlayer/
              MonteCarloPlayer/
          3p/
          4p/
          5p/
"""

import os
from datetime import datetime
from typing import Any, Callable, Dict, FrozenSet, Tuple

from hanabi.core.game import create_standard_game_settings
from hanabi.core.game_field import GameField, ExperimentResults
from hanabi.tools.experiment_outcome import build_experiment_outcome_categories_payload
from hanabi.ai import (
    RandomPlayer,
    CommonSensePlayer,
    CommonSenseCheater,
    PaperCheater,
    MonteCarloPlayer,
    MonteCarloConfig,
    RecommendationPlayer,
    ThreePlayerRecommendationPlayer,
    FourPlayerRecommendationPlayer,
)

try:
    import yaml
except ImportError:  # pragma: no cover - yaml should be available, but guard just in case
    yaml = None


def create_random_player(player_index: int) -> RandomPlayer:
    """Factory for RandomPlayer."""
    return RandomPlayer(player_index)


def create_common_sense_player(player_index: int) -> CommonSensePlayer:
    """Factory for CommonSensePlayer."""
    return CommonSensePlayer(player_index)


def create_common_sense_cheater(player_index: int) -> CommonSenseCheater:
    """Factory for CommonSenseCheater (full-state policy; experiments only)."""
    return CommonSenseCheater(player_index)


def create_paper_cheater(player_index: int) -> PaperCheater:
    """Factory for PaperCheater (full-state index-priority policy; experiments only)."""
    return PaperCheater(player_index)


def create_monte_carlo_player(player_index: int) -> MonteCarloPlayer:
    """Factory for MonteCarloPlayer with reasonable config for comparison."""
    # Use a balanced config: not too slow, but still effective
    # Disable verbose logging for faster experiments
    config = MonteCarloConfig(
        min_think_time_s=0.5,  # 500ms
        max_think_time_s=1.0,  # 1 second
        min_simulations=5,
        max_simulations=50,
        verbose=False,  # Disable terminal output for faster experiments
    )
    return MonteCarloPlayer(player_index, config=config)


def create_recommendation_player(player_index: int) -> RecommendationPlayer:
    """Factory for RecommendationPlayer (Cox et al. strategy; 5-player games only)."""
    return RecommendationPlayer(player_index)


def create_three_player_recommendation_player(player_index: int) -> ThreePlayerRecommendationPlayer:
    """Factory for ThreePlayerRecommendationPlayer (mod-7 mini variant; 3-player games only)."""
    return ThreePlayerRecommendationPlayer(player_index)


def create_four_player_recommendation_player(player_index: int) -> FourPlayerRecommendationPlayer:
    """Factory for FourPlayerRecommendationPlayer (mod-9 mini variant; 4-player games only)."""
    return FourPlayerRecommendationPlayer(player_index)


# CLI keys for --ais (order here defines column / summary order).
_AI_ORDER = (
    "random",
    "commonsense",
    "commonsense_cheater",
    "paper_cheater",
    "montecarlo",
    "recommendation",
    "three_player_recommendation",
    "four_player_recommendation",
)
# Full-state benchmark bots are opt-in so default batches match the four interactive AIs (GUI/console).
_CLI_DEFAULT_AIS = tuple(k for k in _AI_ORDER if k not in ("commonsense_cheater", "paper_cheater"))
_AI_REGISTRY: Dict[str, Tuple[str, Callable[[int], object]]] = {
    "random": ("RandomPlayer", create_random_player),
    "commonsense": ("CommonSensePlayer", create_common_sense_player),
    "commonsense_cheater": ("CommonSenseCheater", create_common_sense_cheater),
    "paper_cheater": ("PaperCheater", create_paper_cheater),
    "montecarlo": ("MonteCarloPlayer", create_monte_carlo_player),
    "recommendation": ("RecommendationPlayer", create_recommendation_player),
    "three_player_recommendation": (
        "ThreePlayerRecommendationPlayer",
        create_three_player_recommendation_player,
    ),
    "four_player_recommendation": (
        "FourPlayerRecommendationPlayer",
        create_four_player_recommendation_player,
    ),
}


def _effective_ais_for_player_count(
    num_players: int,
    enabled: FrozenSet[str],
    *,
    include_outcome_baseline: bool,
) -> FrozenSet[str]:
    """
    Effective ``--ais`` set for :func:`_ai_factories_for_settings`.

    On 5-player games, outcome categories in ``summary.md`` pair each subject AI against
    ``CommonSenseCheater`` replays. When the cheater is omitted from ``--ais``, that entire
    section is skipped unless we add the baseline here (unless ``include_outcome_baseline``
    is false).
    """
    if 5 != num_players or not include_outcome_baseline:
        return enabled
    if "commonsense_cheater" in enabled:
        return enabled
    return frozenset(enabled | {"commonsense_cheater"})


def _ai_factories_for_settings(settings, enabled: FrozenSet[str]) -> Dict[str, Callable[[int], object]]:
    """Build the ``ai_factories`` map for :meth:`GameField.run_experiment`."""
    factories: Dict[str, Callable[[int], object]] = {}
    for key in _AI_ORDER:
        if key not in enabled:
            continue
        if key == "recommendation" and not RecommendationPlayer.supports_game_settings(settings):
            continue
        if key == "three_player_recommendation" and not ThreePlayerRecommendationPlayer.supports_game_settings(settings):
            continue
        if key == "four_player_recommendation" and not FourPlayerRecommendationPlayer.supports_game_settings(settings):
            continue
        label, factory = _AI_REGISTRY[key]
        factories[label] = factory
    return factories


def run_experiments(
    player_counts=(2, 3, 4, 5),
    num_runs: int = 100,
    base_seed: int = 42,
    *,
    enabled_ais: FrozenSet[str] | None = None,
    include_outcome_baseline: bool = True,
) -> None:
    """
    Run experiments for different player counts comparing selected AIs.

    Args:
        player_counts: Iterable of player counts to test.
        num_runs: Number of runs per experiment.
        base_seed: Base random seed for reproducibility.
        enabled_ais: Subset of registry keys (see ``--ais``). ``None`` means all registered AIs.
            Recommendation is skipped automatically for non-5p games.
        include_outcome_baseline: When True (default), 5-player runs also execute
            ``commonsense_cheater`` if it was not listed in ``enabled_ais``, so
            ``outcome_categories.yaml`` and the vs-baseline sections of ``summary.md`` are
            populated. Set False with ``--no-outcome-baseline`` to skip that extra work.
    """
    if enabled_ais is None:
        enabled_ais = frozenset(_AI_REGISTRY.keys())
    if not enabled_ais:
        raise ValueError("enabled_ais must not be empty")
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    # Base directory for this batch of experiments
    base_dir = os.path.join("game_records", "exp_ai_comparison", timestamp)
    os.makedirs(base_dir, exist_ok=True)

    # Store per-player-count ExperimentResults to generate a markdown summary later
    all_results: Dict[int, ExperimentResults] = {}
    all_outcome_payloads: Dict[int, Any] = {}
    auto_baseline_by_players: Dict[int, bool] = {}

    for num_players in player_counts:
        print("=" * 70)
        print(f"Running AI comparison for {num_players}-player games")
        print("=" * 70)

        # Create game settings for this player count
        settings = create_standard_game_settings(num_players)

        # Create GameField with a reproducible starting position
        game_field = GameField.create_from_settings(settings, seed=base_seed)

        effective_ais = _effective_ais_for_player_count(
            num_players, enabled_ais, include_outcome_baseline=include_outcome_baseline
        )
        added_for_baseline = sorted(effective_ais - enabled_ais)
        auto_baseline_by_players[num_players] = bool(added_for_baseline)
        if added_for_baseline:
            print(
                "Note: also running CommonSenseCheater for outcome-vs-baseline summary "
                f"(add with --ais or disable via --no-outcome-baseline): {added_for_baseline}"
            )
        ai_factories = _ai_factories_for_settings(settings, effective_ais)
        if not ai_factories:
            raise ValueError(
                f"No AIs to run for {num_players} players with --ais {sorted(enabled_ais)!r}. "
                "(``recommendation`` only at 5p; ``three_player_recommendation`` only at 3p; "
                "``four_player_recommendation`` only at 4p.)"
            )

        # Use an experiment id that encodes timestamp and player count so we
        # can group all player counts under the same timestamp:
        #   exp_ai_comparison/<timestamp>/<Np>p/...
        experiment_id = os.path.join(timestamp, f"{num_players}p")

        print(f"Experiment ID: {experiment_id} (runs={num_runs}, seed={base_seed})")

        results: ExperimentResults = game_field.run_experiment(
            ai_factories=ai_factories,
            num_runs=num_runs,
            save_records=True,
            random_seed=base_seed,
            experiment_id=experiment_id,
        )
        all_results[num_players] = results

        outcome_payload = build_experiment_outcome_categories_payload(results)
        if outcome_payload is not None:
            all_outcome_payloads[num_players] = outcome_payload
            if yaml is not None:
                oc_path = os.path.join(GameField.EXPERIMENTS_BASE_DIR, results.experiment_id, "outcome_categories.yaml")
                with open(oc_path, "w") as f:
                    yaml.dump(
                        outcome_payload,
                        f,
                        default_flow_style=False,
                        sort_keys=False,
                        allow_unicode=True,
                        width=120,
                    )
                print(f"Outcome categories saved to: {oc_path}")
            else:  # pragma: no cover
                print("Outcome categories computed (install PyYAML to write outcome_categories.yaml)")

        # Save statistics for this experiment
        stats_file = game_field.save_statistics(results)
        print(f"Statistics saved to: {stats_file}")
        print(
            f"Settings saved to: {os.path.join(GameField.EXPERIMENTS_BASE_DIR, results.experiment_id, 'settings.yaml')}"
        )
        print(
            "Game records saved to: "
            f"{os.path.join(GameField.EXPERIMENTS_BASE_DIR, results.experiment_id, 'games', 'all-games')}"
        )

        # Print summary for this player count
        print("\nSummary:")
        for ai_name, stats in results.summary.items():
            print(f"  {ai_name}:")
            print(f"    Games played: {stats.games_played}")
            print(f"    Average score: {stats.average_score:.2f}")
            print(f"    Best score: {stats.best_score}")
            print(f"    Worst score: {stats.worst_score}")
            print(f"    Win rate (perfect scores): {stats.win_rate * 100:.1f}%")
            print(f"    Avg moves: {stats.average_moves:.1f}")
            print(f"    Avg duration: {stats.average_duration:.3f}s")
        print()

    # Save high-level experiment settings at the timestamp root
    settings_path = os.path.join(base_dir, "settings.yaml")
    if yaml is not None:
        with open(settings_path, "w") as f:
            yaml.dump(
                {
                    "timestamp": timestamp,
                    "player_counts": list(player_counts),
                    "num_runs": num_runs,
                    "base_seed": base_seed,
                    "ais": sorted(enabled_ais),
                    "include_outcome_baseline": include_outcome_baseline,
                },
                f,
                default_flow_style=False,
                sort_keys=False,
            )

    # Generate a markdown summary for this batch
    summary_md_path = os.path.join(base_dir, "summary.md")
    lines = []
    lines.append(f"# AI Comparison Experiments ({timestamp})\n")
    lines.append("")
    lines.append(f"- Player counts: {', '.join(str(p) + 'p' for p in player_counts)}")
    lines.append(f"- Runs per configuration: {num_runs}")
    lines.append(f"- Base seed: {base_seed}")
    lines.append(
        f"- AIs selected (--ais): {', '.join(sorted(enabled_ais))} "
        "(``recommendation`` only at 5p; ``three_player_recommendation`` only at 3p; "
        "``four_player_recommendation`` only at 4p)"
    )
    if any(auto_baseline_by_players.values()):
        lines.append(
            "- Also ran **CommonSenseCheater** automatically for 5p outcome-vs-baseline summary "
            "(omit with `--no-outcome-baseline`, or list `commonsense_cheater` in `--ais` explicitly)."
        )
    lines.append("")

    # Add comparison table across all player counts
    lines.append("## Comparison Table\n")
    lines.append("")
    lines.append("| Player Count | AI | Avg Score | Best | Worst | Win Rate | Avg Moves | Avg Duration (s) |")
    lines.append("|--------------|----|-----------|------|-------|----------|-----------|------------------|")

    for num_players in player_counts:
        results = all_results.get(num_players)
        if not results:
            continue
        for ai_name, stats in results.summary.items():
            lines.append(
                f"| {num_players}p | {ai_name} | {stats.average_score:.2f} | "
                f"{stats.best_score} | {stats.worst_score} | "
                f"{stats.win_rate * 100:.1f}% | {stats.average_moves:.1f} | "
                f"{stats.average_duration:.3f} |"
            )

    lines.append("")
    lines.append("")

    for num_players in player_counts:
        results = all_results.get(num_players)
        if not results:
            continue
        lines.append(f"## {num_players}-player games\n")

        # Add ranking for this player count
        sorted_ais = sorted(results.summary.items(), key=lambda x: x[1].average_score, reverse=True)
        lines.append("### Ranking by Average Score")
        lines.append("")
        for rank, (ai_name, stats) in enumerate(sorted_ais, 1):
            lines.append(f"{rank}. **{ai_name}**: {stats.average_score:.2f}")
        lines.append("")

        payload = all_outcome_payloads.get(num_players)
        baseline_name = str(payload["baseline"]) if payload is not None else None

        for ai_name, stats in results.summary.items():
            lines.append(f"### {ai_name}")
            lines.append(f"- Games played: {stats.games_played}")
            lines.append(f"- Score: avg {stats.average_score:.2f}, best {stats.best_score}, worst {stats.worst_score}")
            lines.append(f"- Moves: avg {stats.average_moves:.1f}")
            lines.append(f"- Thinking time: avg {stats.average_duration:.3f}s per game")
            lines.append(f"- Perfect-score win rate: {stats.win_rate * 100:.1f}%")
            if (
                payload is not None
                and baseline_name is not None
                and ai_name != baseline_name
                and ai_name in payload["subjects"]
            ):
                tip = payload["subjects"][ai_name].get("top_non_perfect_reason")
                if tip:
                    lines.append(f"- Most common non-perfect (vs {baseline_name}): {tip}")
                else:
                    lines.append(f"- Most common non-perfect (vs {baseline_name}): — (all max score)")
            lines.append("")
        if payload is not None:
            baseline = str(payload["baseline"])
            lines.append(f"### Outcome categories vs {baseline}")
            lines.append("")
            lines.append(
                "Each row is an exclusive outcome vs the baseline (see `hanabi/tools/experiment_outcome.py`). "
                "Numeric taxonomy keys are omitted here; they appear as `code` in `outcome_categories.yaml` if needed."
            )
            lines.append("")
            subjects = payload["subjects"]
            for subject_name in sorted(subjects.keys()):
                body = subjects[subject_name]
                lines.append(f"#### {subject_name}")
                lines.append("")
                lines.append("| Count | Outcome |")
                lines.append("|------:|---------|")
                for row in body["outcomes"]:
                    desc = str(row["description"])
                    cnt = int(row["count"])
                    lines.append(f"| {cnt} | {desc} |")
                lines.append("")
                tip = body.get("top_non_perfect_reason")
                if tip:
                    lines.append(f"**Most common non-perfect:** {tip}")
                else:
                    lines.append("**Most common non-perfect:** — (all max score)")
                lines.append("")
                any_non_perfect = any(row.get("game_numbers") for row in body["outcomes"])
                if any_non_perfect:
                    lines.append(
                        "Non-perfect games by outcome (same game number for each AI on that shuffle, "
                        "e.g. `run_007_ai_<Name>.yaml`):"
                    )
                    lines.append("")
                    for row in body["outcomes"]:
                        nums = row.get("game_numbers")
                        if not nums:
                            continue
                        desc = str(row["description"])
                        games_fmt = ", ".join(str(int(n)) for n in nums)
                        lines.append(f"- {desc} — **games:** {games_fmt}")
                    lines.append("")

        lines.append("")

    with open(summary_md_path, "w") as f:
        f.write("\n".join(lines))


def main() -> None:
    """Entry point for running AI comparison experiments."""
    import argparse

    parser = argparse.ArgumentParser(
        description=(
            "Run AI comparison experiments (Random, CommonSense, CommonSenseCheater, PaperCheater, "
            "MonteCarlo, Recommendation, ThreePlayerRecommendation, FourPlayerRecommendation)."
        )
    )
    parser.add_argument(
        "--players",
        type=int,
        nargs="+",
        default=[2, 3, 4, 5],
        metavar="N",
        help="Player counts to run (default: 2 3 4 5). e.g. --players 5 for 5-player only.",
    )
    parser.add_argument("--runs", type=int, default=10, help="Number of runs per configuration (default: 10).")
    parser.add_argument("--seed", type=int, default=42, help="Base random seed (default: 42).")
    parser.add_argument(
        "--no-outcome-baseline",
        action="store_true",
        help=(
            "For 5-player runs, do not auto-include CommonSenseCheater. "
            "Outcome categories and vs-baseline lines in summary.md are omitted unless you "
            "pass commonsense_cheater in --ais."
        ),
    )
    parser.add_argument(
        "--ais",
        nargs="+",
        choices=list(_AI_REGISTRY.keys()),
        metavar="NAME",
        default=list(_CLI_DEFAULT_AIS),
        help=(
            "Which AIs to run (default: random, commonsense, montecarlo, recommendation, "
            "three_player_recommendation, four_player_recommendation). "
            "Names: random, commonsense, commonsense_cheater, paper_cheater, montecarlo, "
            "recommendation, three_player_recommendation, four_player_recommendation. "
            "``recommendation`` is auto-skipped for non-5p; ``three_player_recommendation`` for non-3p; "
            "``four_player_recommendation`` for non-4p. "
            "Add commonsense_cheater and/or paper_cheater for full-state benchmarks (not in GUI/console). "
            "Example: --ais random commonsense commonsense_cheater paper_cheater"
        ),
    )
    args = parser.parse_args()
    player_counts = tuple(args.players)
    if not all(2 <= p <= 5 for p in player_counts):
        parser.error("Each player count must be between 2 and 5.")
    run_experiments(
        player_counts=player_counts,
        num_runs=args.runs,
        base_seed=args.seed,
        enabled_ais=frozenset(args.ais),
        include_outcome_baseline=not args.no_outcome_baseline,
    )


if __name__ == "__main__":
    main()
