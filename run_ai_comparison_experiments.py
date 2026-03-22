"""
Run comprehensive experiments comparing RandomPlayer and CommonSensePlayer
across different player counts (2, 3, 4, 5 players).

This script organizes experiments by player count for better comparison.
"""

from hanabi.core.game import create_standard_game_settings
from hanabi.core.game_field import GameField
from hanabi.ai.random_player import RandomPlayer
from hanabi.ai.common_sense_player import CommonSensePlayer
from typing import Dict, Callable
from datetime import datetime


def create_random_player(player_index: int) -> RandomPlayer:
    """Factory function to create a RandomPlayer."""
    return RandomPlayer(player_index)


def create_common_sense_player(player_index: int) -> CommonSensePlayer:
    """Factory function to create a CommonSensePlayer."""
    return CommonSensePlayer(player_index)


def run_experiment_for_player_count(num_players: int, num_runs: int = 50, random_seed: int = 42) -> Dict[str, any]:
    """
    Run an experiment comparing both AI types for a specific player count.

    Args:
        num_players: Number of players (2-5)
        num_runs: Number of games to run per AI
        random_seed: Random seed for reproducibility

    Returns:
        Dictionary with experiment results and statistics
    """
    print(f"\n{'=' * 70}")
    print(f"Running experiment for {num_players} players")
    print(f"{'=' * 70}")

    # Create game settings
    settings = create_standard_game_settings(num_players)

    # Create GameField
    game_field = GameField.create_from_settings(settings, seed=random_seed)

    # Define AI factories
    ai_factories = {
        "RandomPlayer": create_random_player,
        "CommonSensePlayer": create_common_sense_player,
    }

    # Create experiment ID with player count
    experiment_id = f"ai_comparison_{num_players}p"

    print(f"Experiment ID: {experiment_id}")
    print(f"Running {num_runs} games per AI type...")

    # Run experiment
    results = game_field.run_experiment(
        ai_factories=ai_factories,
        num_runs=num_runs,
        save_records=True,
        random_seed=random_seed,
        experiment_id=experiment_id,
    )

    # Save statistics
    stats_file = game_field.save_statistics(results)
    print(f"Statistics saved to: {stats_file}")

    # Print summary for this player count
    print(f"\nResults for {num_players} players:")
    print("-" * 70)
    for ai_name, stats in results.summary.items():
        print(f"\n{ai_name}:")
        print(f"  Games played: {stats.games_played}")
        print(f"  Average score: {stats.average_score:.2f}")
        print(f"  Best score: {stats.best_score}")
        print(f"  Worst score: {stats.worst_score}")
        print(f"  Win rate (perfect scores): {stats.win_rate * 100:.1f}%")
        print(f"  Std deviation: {stats.std_dev:.2f}")
        print(f"  Average moves: {stats.average_moves:.1f}")
        print(f"  Average duration: {stats.average_duration:.3f}s")

    return {"num_players": num_players, "experiment_id": experiment_id, "results": results, "stats_file": stats_file}


def main():
    """Run experiments for all player counts and generate comparison report."""
    print("=" * 70)
    print("AI COMPARISON EXPERIMENTS")
    print("Comparing RandomPlayer vs CommonSensePlayer")
    print("=" * 70)

    # Configuration
    num_runs = 50  # Number of games per AI per player count
    random_seed = 42  # Starting seed

    # Run experiments for each player count
    all_results = []
    player_counts = [2, 3, 4, 5]

    for num_players in player_counts:
        result = run_experiment_for_player_count(num_players=num_players, num_runs=num_runs, random_seed=random_seed)
        all_results.append(result)
        # Use different seed for next experiment to ensure variety
        random_seed += 1000

    # Generate comparison summary
    print("\n" + "=" * 70)
    print("COMPREHENSIVE COMPARISON SUMMARY")
    print("=" * 70)

    # Create comparison table
    print("\nAverage Scores by Player Count:")
    print("-" * 70)
    print(f"{'Players':<10} {'RandomPlayer':<20} {'CommonSensePlayer':<20} {'Improvement':<15}")
    print("-" * 70)

    for result in all_results:
        num_players = result["num_players"]
        summary = result["results"].summary

        random_avg = summary["RandomPlayer"].average_score
        common_sense_avg = summary["CommonSensePlayer"].average_score
        improvement = common_sense_avg - random_avg
        improvement_pct = (improvement / random_avg * 100) if random_avg > 0 else 0

        print(
            f"{num_players:<10} {random_avg:<20.2f} {common_sense_avg:<20.2f} "
            f"{improvement:+.2f} ({improvement_pct:+.1f}%)"
        )

    print("\nWin Rates (Perfect Scores) by Player Count:")
    print("-" * 70)
    print(f"{'Players':<10} {'RandomPlayer':<20} {'CommonSensePlayer':<20} {'Improvement':<15}")
    print("-" * 70)

    for result in all_results:
        num_players = result["num_players"]
        summary = result["results"].summary

        random_wr = summary["RandomPlayer"].win_rate * 100
        common_sense_wr = summary["CommonSensePlayer"].win_rate * 100
        improvement = common_sense_wr - random_wr

        print(f"{num_players:<10} {random_wr:<20.1f}% {common_sense_wr:<20.1f}% {improvement:+.1f}%")

    print("\nBest Scores by Player Count:")
    print("-" * 70)
    print(f"{'Players':<10} {'RandomPlayer':<20} {'CommonSensePlayer':<20}")
    print("-" * 70)

    for result in all_results:
        num_players = result["num_players"]
        summary = result["results"].summary

        random_best = summary["RandomPlayer"].best_score
        common_sense_best = summary["CommonSensePlayer"].best_score

        print(f"{num_players:<10} {random_best:<20} {common_sense_best:<20}")

    print("\n" + "=" * 70)
    print("EXPERIMENT COMPLETE")
    print("=" * 70)
    print("\nExperiment directories:")
    for result in all_results:
        print(f"  - {result['experiment_id']}: {result['stats_file']}")
    print("\nYou can review detailed statistics in each experiment's statistics.yaml file.")


if __name__ == "__main__":
    main()
