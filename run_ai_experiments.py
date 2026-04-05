"""
Run AI comparison experiments for different player counts.

This script compares selected AIs on the same shuffled decks for 2–5-player games.
Use ``--ais`` to include only the bots you want (e.g. omit ``montecarlo`` for faster batches).
``recommendation`` runs only for 5-player settings.
``commonsense_cheater`` (``CommonSenseCheater``) is for benchmarking only and is not offered
in the GUI or console apps.

Folder layout:

    game_records/
      exp_ai_comparison/
        <timestamp>/
          settings.yaml                # experiment runner settings (player counts, runs, seed)
          summary.md                   # human-readable summary for this batch
          2p/
            settings.yaml
            statistics.yaml
            games/
              all-games/
              <run_id>/
            ai/
              RandomPlayer/
              CommonSensePlayer/
              CommonSenseCheater/
              RecommendationPlayer/
              MonteCarloPlayer/
          3p/
          4p/
          5p/
"""

import os
from datetime import datetime
from typing import Callable, Dict, FrozenSet, Tuple

from hanabi.core.game import create_standard_game_settings
from hanabi.core.game_field import GameField, ExperimentResults
from hanabi.ai import (
    RandomPlayer,
    CommonSensePlayer,
    CommonSenseCheater,
    MonteCarloPlayer,
    MonteCarloConfig,
    RecommendationPlayer,
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


# CLI keys for --ais (order here defines column / summary order).
_AI_ORDER = ("random", "commonsense", "commonsense_cheater", "montecarlo", "recommendation")
# Cheater is opt-in on the CLI so default batches match the four interactive AIs (GUI/console).
_CLI_DEFAULT_AIS = tuple(k for k in _AI_ORDER if k != "commonsense_cheater")
_AI_REGISTRY: Dict[str, Tuple[str, Callable[[int], object]]] = {
    "random": ("RandomPlayer", create_random_player),
    "commonsense": ("CommonSensePlayer", create_common_sense_player),
    "commonsense_cheater": ("CommonSenseCheater", create_common_sense_cheater),
    "montecarlo": ("MonteCarloPlayer", create_monte_carlo_player),
    "recommendation": ("RecommendationPlayer", create_recommendation_player),
}


def _ai_factories_for_settings(settings, enabled: FrozenSet[str]) -> Dict[str, Callable[[int], object]]:
    """Build the ``ai_factories`` map for :meth:`GameField.run_experiment`."""
    factories: Dict[str, Callable[[int], object]] = {}
    for key in _AI_ORDER:
        if key not in enabled:
            continue
        if key == "recommendation" and not RecommendationPlayer.supports_game_settings(settings):
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
) -> None:
    """
    Run experiments for different player counts comparing selected AIs.

    Args:
        player_counts: Iterable of player counts to test.
        num_runs: Number of runs per experiment.
        base_seed: Base random seed for reproducibility.
        enabled_ais: Subset of registry keys (see ``--ais``). ``None`` means all registered AIs.
            Recommendation is skipped automatically for non-5p games.
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

    for num_players in player_counts:
        print("=" * 70)
        print(f"Running AI comparison for {num_players}-player games")
        print("=" * 70)

        # Create game settings for this player count
        settings = create_standard_game_settings(num_players)

        # Create GameField with a reproducible starting position
        game_field = GameField.create_from_settings(settings, seed=base_seed)

        ai_factories = _ai_factories_for_settings(settings, enabled_ais)
        if not ai_factories:
            raise ValueError(
                f"No AIs to run for {num_players} players with --ais {sorted(enabled_ais)!r}. "
                "(Recommendation only runs for 5 players.)"
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
        "(recommendation only participates in 5-player games)"
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

        for ai_name, stats in results.summary.items():
            lines.append(f"### {ai_name}")
            lines.append(f"- Games played: {stats.games_played}")
            lines.append(f"- Score: avg {stats.average_score:.2f}, best {stats.best_score}, worst {stats.worst_score}")
            lines.append(f"- Moves: avg {stats.average_moves:.1f}")
            lines.append(f"- Thinking time: avg {stats.average_duration:.3f}s per game")
            lines.append(f"- Perfect-score win rate: {stats.win_rate * 100:.1f}%")
            lines.append("")

        lines.append("")

    with open(summary_md_path, "w") as f:
        f.write("\n".join(lines))


def main() -> None:
    """Entry point for running AI comparison experiments."""
    import argparse

    parser = argparse.ArgumentParser(
        description=(
            "Run AI comparison experiments (Random, CommonSense, CommonSenseCheater, MonteCarlo, Recommendation)."
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
        "--ais",
        nargs="+",
        choices=list(_AI_REGISTRY.keys()),
        metavar="NAME",
        default=list(_CLI_DEFAULT_AIS),
        help=(
            "Which AIs to run (default: random, commonsense, montecarlo, recommendation). "
            "Names: random, commonsense, commonsense_cheater, montecarlo, recommendation. "
            "Add commonsense_cheater explicitly for full-state benchmarks (not in GUI/console). "
            "Example: --ais random commonsense commonsense_cheater"
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
    )


if __name__ == "__main__":
    main()
