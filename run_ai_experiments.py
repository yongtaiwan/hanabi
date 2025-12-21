"""
Run AI comparison experiments for different player counts.

This script compares RandomPlayer, CommonSensePlayer, and MonteCarloPlayer
on the same decks for 2/3/4/5-player games.

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
              MonteCarloPlayer/
          3p/
          4p/
          5p/
"""

import os
from datetime import datetime
from typing import Dict

from hanabi.core.game import create_standard_game_settings
from hanabi.core.game_field import GameField, ExperimentResults
from hanabi.ai import RandomPlayer, CommonSensePlayer, MonteCarloPlayer, MonteCarloConfig

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


def create_monte_carlo_player(player_index: int) -> MonteCarloPlayer:
    """Factory for MonteCarloPlayer with reasonable config for comparison."""
    # Use a balanced config: not too slow, but still effective
    config = MonteCarloConfig(
        min_think_time_s=0.5,   # 500ms
        max_think_time_s=1.0,   # 1 second
        min_simulations=5,
        max_simulations=50,
    )
    return MonteCarloPlayer(player_index, config=config)


def run_experiments(
    player_counts=(2, 3, 4, 5),
    num_runs: int = 100,
    base_seed: int = 42,
) -> None:
    """
    Run experiments for different player counts comparing both AIs.

    Args:
        player_counts: Iterable of player counts to test.
        num_runs: Number of runs per experiment.
        base_seed: Base random seed for reproducibility.
    """
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

        # Define AI factories
        ai_factories = {
            "RandomPlayer": create_random_player,
            "CommonSensePlayer": create_common_sense_player,
            "MonteCarloPlayer": create_monte_carlo_player,
        }

        # Use an experiment id that encodes timestamp and player count so we
        # can group all player counts under the same timestamp:
        #   exp_ai_comparison/<timestamp>/<Np>p/...
        experiment_id = os.path.join(timestamp, f"{num_players}p")

        print(
            f"Experiment ID: {experiment_id} "
            f"(runs={num_runs}, seed={base_seed})"
        )

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
            "Settings saved to: "
            f"{os.path.join(GameField.EXPERIMENTS_BASE_DIR, results.experiment_id, 'settings.yaml')}"
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
    lines.append(f"- AIs compared: RandomPlayer, CommonSensePlayer, MonteCarloPlayer")
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
        sorted_ais = sorted(
            results.summary.items(),
            key=lambda x: x[1].average_score,
            reverse=True
        )
        lines.append("### Ranking by Average Score")
        lines.append("")
        for rank, (ai_name, stats) in enumerate(sorted_ais, 1):
            lines.append(f"{rank}. **{ai_name}**: {stats.average_score:.2f}")
        lines.append("")

        for ai_name, stats in results.summary.items():
            lines.append(f"### {ai_name}")
            lines.append(f"- Games played: {stats.games_played}")
            lines.append(
                f"- Score: avg {stats.average_score:.2f}, "
                f"best {stats.best_score}, worst {stats.worst_score}"
            )
            lines.append(
                f"- Moves: avg {stats.average_moves:.1f}"
            )
            lines.append(
                f"- Thinking time: avg {stats.average_duration:.3f}s per game"
            )
            lines.append(
                f"- Perfect-score win rate: {stats.win_rate * 100:.1f}%"
            )
            lines.append("")

        lines.append("")

    with open(summary_md_path, "w") as f:
        f.write("\n".join(lines))


def main() -> None:
    """Entry point for running AI comparison experiments."""
    # Run with 10 games for each player count (2, 3, 4, 5 players)
    run_experiments(
        player_counts=(2, 3, 4, 5),  # All player counts
        num_runs=10,  # 10 games per configuration
        base_seed=42,
    )


if __name__ == "__main__":
    main()


