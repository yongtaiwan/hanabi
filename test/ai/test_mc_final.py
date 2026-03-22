"""
Final comprehensive test to verify Monte Carlo player performance.
"""

from hanabi.core.game_field import GameField
from hanabi.core.game import create_standard_game_settings
from hanabi.ai.monte_carlo_player import MonteCarloPlayer, MonteCarloConfig
from hanabi.ai.random_player import RandomPlayer


def main():
    """Run comprehensive performance test."""
    print("=" * 70)
    print("FINAL MONTE CARLO PLAYER PERFORMANCE TEST")
    print("=" * 70)
    print("\nTesting with default configuration (2.0-4.0s thinking time)")
    print("Target: At least 1.0 points better than Random player on average")
    print("\nRunning 30 games for statistical significance...")

    settings = create_standard_game_settings(3)
    game_field = GameField.create_from_settings(settings, seed=42)

    # Use default config (now 2.0-4.0s)
    def create_mc_player(idx):
        return MonteCarloPlayer(idx)  # Uses default config

    def create_random_player(idx):
        return RandomPlayer(idx)

    ai_factories = {
        "MonteCarlo": create_mc_player,
        "Random": create_random_player,
    }

    results = game_field.run_experiment(
        ai_factories=ai_factories, num_runs=30, save_records=False, random_seed=42, experiment_id="mc_final_test"
    )

    mc_stats = results.summary.get("MonteCarlo")
    random_stats = results.summary.get("Random")

    print("\n" + "=" * 70)
    print("RESULTS")
    print("=" * 70)

    if mc_stats and random_stats:
        score_diff = mc_stats.average_score - random_stats.average_score

        print(f"\nMonte Carlo Player:")
        print(f"  Average score: {mc_stats.average_score:.2f}")
        print(f"  Best score:    {mc_stats.best_score}")
        print(f"  Worst score:   {mc_stats.worst_score}")
        print(f"  Games played:  {mc_stats.games_played}")

        print(f"\nRandom Player:")
        print(f"  Average score: {random_stats.average_score:.2f}")
        print(f"  Best score:    {random_stats.best_score}")
        print(f"  Worst score:   {random_stats.worst_score}")
        print(f"  Games played:  {random_stats.games_played}")

        print(f"\n{'=' * 70}")
        print(f"Score Difference: {score_diff:.2f} points")
        print(f"{'=' * 70}")

        if score_diff >= 1.0:
            print(f"\n✓ SUCCESS: Monte Carlo player is {score_diff:.2f} points better!")
            print("  This exceeds the 1.0 point requirement.")
        else:
            print(f"\n✗ FAILED: Monte Carlo player is only {score_diff:.2f} points better.")
            print("  Need at least 1.0 points better. Consider increasing thinking time.")

        print("=" * 70)

    return mc_stats, random_stats


if __name__ == "__main__":
    main()
