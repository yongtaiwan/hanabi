"""
Example script demonstrating how to use GameField for AI performance comparisons.

This script runs an experiment comparing different AI players on the same decks.
"""

from hanabi.core.game import create_standard_game_settings
from hanabi.core.game_field import GameField
from hanabi.ai.random_player import RandomPlayer


def create_random_player(player_index: int) -> RandomPlayer:
    """Factory function to create a RandomPlayer."""
    return RandomPlayer(player_index)


def main():
    """Run an experiment comparing AI players."""
    # Create game settings (standard 3-player game)
    settings = create_standard_game_settings(3)

    # Create a GameField (we'll create new decks for each run)
    # For the first run, we can use a seed for reproducibility
    game_field = GameField.create_from_settings(settings, seed=42)

    # Define AI factories (functions that create players)
    ai_factories = {
        "RandomPlayer": create_random_player,
        # Add more AIs here as you implement them:
        # "StrategyAlpha": create_strategy_alpha_player,
        # "SmartPlayer": create_smart_player,
    }

    # Run experiment: 10 runs, each with a new deck shuffle
    # All AIs play the same deck in each run
    print("Running experiment...")
    results = game_field.run_experiment(
        ai_factories=ai_factories,
        num_runs=10,  # Change this to run more or fewer games
        save_records=True,  # Save individual game records
        random_seed=42,  # Seed for first run, subsequent runs use sequential seeds
        experiment_id="random_player_test"
    )

    # Save statistics (saves to game_records/experiment_<id>/statistics.yaml)
    stats_file = game_field.save_statistics(results)
    print(f"Statistics saved to: {stats_file}")
    print(f"Settings saved to: game_records/experiment_{results.experiment_id}/settings.yaml")
    print(f"Game records saved to: game_records/experiment_{results.experiment_id}/games/all-games/")
    print(f"  - Browse by run: game_records/experiment_{results.experiment_id}/games/<run_id>/")
    print(f"  - Browse by AI: game_records/experiment_{results.experiment_id}/ai/<ai_name>/")

    # Print summary
    print("\n" + "=" * 70)
    print("EXPERIMENT SUMMARY")
    print("=" * 70)
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


if __name__ == "__main__":
    main()
