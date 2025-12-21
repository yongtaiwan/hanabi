"""
Test script for Monte Carlo player.

This script runs a quick test to verify the Monte Carlo player works correctly.

NOTE: The default MonteCarloPlayer config uses 1-2 seconds per turn, which
      can make full games take 30-60+ seconds. For faster testing, this script
      uses a faster config (100-200ms per turn).
"""

from hanabi.core.game import create_standard_game_settings
from hanabi.core.game_field import GameField
from hanabi.ai.random_player import RandomPlayer
from hanabi.ai.monte_carlo_player import MonteCarloPlayer, MonteCarloConfig


def create_random_player(player_index: int) -> RandomPlayer:
    """Factory function to create a RandomPlayer."""
    return RandomPlayer(player_index)


def create_monte_carlo_player(player_index: int) -> MonteCarloPlayer:
    """Factory function to create a MonteCarloPlayer with fast config for testing."""
    # Use fast config for testing (100-200ms per turn instead of 1-2s)
    config = MonteCarloConfig(
        min_think_time_s=0.1,   # 100ms
        max_think_time_s=0.2,   # 200ms
        min_simulations=1,
        max_simulations=20,     # Cap at 20 simulations for speed
    )
    return MonteCarloPlayer(player_index, config=config)


def main():
    """Run a quick test of the Monte Carlo player."""
    print("=" * 70)
    print("TESTING MONTE CARLO PLAYER")
    print("=" * 70)

    # Create game settings (standard 3-player game)
    settings = create_standard_game_settings(3)

    # Create a GameField
    game_field = GameField.create_from_settings(settings, seed=42)

    # Define AI factories
    ai_factories = {
        "RandomPlayer": create_random_player,
        "MonteCarloPlayer": create_monte_carlo_player,
    }

    # Run a small experiment: 3 runs (reduced for speed)
    print("\nRunning 3 test games with fast config (100-200ms per turn)...")
    print("Note: For production use, use default config (1-2s per turn) for better decisions.")
    results = game_field.run_experiment(
        ai_factories=ai_factories,
        num_runs=3,
        save_records=False,  # Don't save for quick test
        random_seed=42,
        experiment_id="monte_carlo_test"
    )

    # Print summary
    print("\n" + "=" * 70)
    print("TEST RESULTS")
    print("=" * 70)
    for ai_name, stats in results.summary.items():
        print(f"\n{ai_name}:")
        print(f"  Games played: {stats.games_played}")
        print(f"  Average score: {stats.average_score:.2f}")
        print(f"  Best score: {stats.best_score}")
        print(f"  Worst score: {stats.worst_score}")
        print(f"  Win rate (perfect scores): {stats.win_rate * 100:.1f}%")
        print(f"  Average moves: {stats.average_moves:.1f}")
        print(f"  Average duration: {stats.average_duration:.3f}s")

    print("\n" + "=" * 70)
    print("Test completed successfully!")
    print("=" * 70)


if __name__ == "__main__":
    main()

