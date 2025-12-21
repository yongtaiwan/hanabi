"""
Test to verify Monte Carlo player fixes and identify remaining bugs.
This will run a quick game and check if move evaluation produces different scores.
"""

from hanabi.core.game_field import GameField
from hanabi.core.game import create_standard_game_settings
from hanabi.ai.monte_carlo_player import MonteCarloPlayer, MonteCarloConfig
from hanabi.ai.random_player import RandomPlayer

def test_monte_carlo_vs_random():
    """Compare Monte Carlo player with Random player."""
    print("=" * 70)
    print("Testing Monte Carlo Player vs Random Player")
    print("=" * 70)

    settings = create_standard_game_settings(3)

    # Create players with fast config for testing
    mc_config = MonteCarloConfig(
        min_think_time_s=1.0,   # 1s
        max_think_time_s=2.0,   # 2s
        min_simulations=5,
        max_simulations=100,
    )

    def create_mc_player(idx):
        return MonteCarloPlayer(idx, mc_config)

    def create_random_player(idx):
        return RandomPlayer(idx)

    # Run experiment
    game_field = GameField.create_from_settings(settings, seed=42)

    ai_factories = {
        "MonteCarlo": create_mc_player,
        "Random": create_random_player,
    }

    print("\nRunning 10 test games (this may take a few minutes)...")
    results = game_field.run_experiment(
        ai_factories=ai_factories,
        num_runs=10,
        save_records=False,
        random_seed=42,
        experiment_id="mc_vs_random_test"
    )

    # Print results
    print("\n" + "=" * 70)
    print("RESULTS")
    print("=" * 70)

    mc_stats = results.summary.get("MonteCarlo")
    random_stats = results.summary.get("Random")

    if mc_stats and random_stats:
        print(f"\nMonte Carlo Player:")
        print(f"  Average score: {mc_stats.average_score:.2f}")
        print(f"  Best score: {mc_stats.best_score}")
        print(f"  Worst score: {mc_stats.worst_score}")

        print(f"\nRandom Player:")
        print(f"  Average score: {random_stats.average_score:.2f}")
        print(f"  Best score: {random_stats.best_score}")
        print(f"  Worst score: {random_stats.worst_score}")

        score_diff = mc_stats.average_score - random_stats.average_score
        print(f"\nScore difference: {score_diff:.2f}")

        if score_diff >= 1.0:
            print("✓ Monte Carlo player performs at least 1.0 points better!")
        else:
            print(f"⚠ Monte Carlo player only {score_diff:.2f} points better (need 1.0+)")

    print("\n" + "=" * 70)

if __name__ == "__main__":
    test_monte_carlo_vs_random()

