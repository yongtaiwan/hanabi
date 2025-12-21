"""
Performance test for Monte Carlo player vs Random player.
Tests different configurations to find optimal settings.
"""

from hanabi.core.game_field import GameField
from hanabi.core.game import create_standard_game_settings
from hanabi.ai.monte_carlo_player import MonteCarloPlayer, MonteCarloConfig
from hanabi.ai.random_player import RandomPlayer

def test_config(config_name, config, num_runs=20):
    """Test a specific Monte Carlo configuration."""
    print(f"\n{'='*70}")
    print(f"Testing: {config_name}")
    print(f"  min_think_time: {config.min_think_time_s}s")
    print(f"  max_think_time: {config.max_think_time_s}s")
    print(f"  min_simulations: {config.min_simulations}")
    print(f"  max_simulations: {config.max_simulations}")
    print(f"{'='*70}")

    settings = create_standard_game_settings(3)
    game_field = GameField.create_from_settings(settings, seed=42)

    def create_mc_player(idx):
        return MonteCarloPlayer(idx, config)

    def create_random_player(idx):
        return RandomPlayer(idx)

    ai_factories = {
        "MonteCarlo": create_mc_player,
        "Random": create_random_player,
    }

    print(f"\nRunning {num_runs} games...")
    results = game_field.run_experiment(
        ai_factories=ai_factories,
        num_runs=num_runs,
        save_records=False,
        random_seed=42,
        experiment_id=f"mc_perf_{config_name}"
    )

    mc_stats = results.summary.get("MonteCarlo")
    random_stats = results.summary.get("Random")

    if mc_stats and random_stats:
        score_diff = mc_stats.average_score - random_stats.average_score
        print(f"\nResults:")
        print(f"  Monte Carlo: {mc_stats.average_score:.2f} (best: {mc_stats.best_score}, worst: {mc_stats.worst_score})")
        print(f"  Random:      {random_stats.average_score:.2f} (best: {random_stats.best_score}, worst: {random_stats.worst_score})")
        print(f"  Difference:  {score_diff:.2f}")

        if score_diff >= 1.0:
            print(f"  ✓ PASS: Monte Carlo is {score_diff:.2f} points better (target: 1.0+)")
        else:
            print(f"  ✗ FAIL: Monte Carlo is only {score_diff:.2f} points better (need 1.0+)")

        return score_diff, mc_stats.average_score, random_stats.average_score

    return None, None, None

def main():
    """Test multiple configurations to find optimal settings."""
    print("="*70)
    print("MONTE CARLO PLAYER PERFORMANCE TESTING")
    print("="*70)
    print("\nTesting different configurations to find optimal settings...")
    print("Target: Monte Carlo player should average at least 1.0 points better than Random")

    configs = [
        ("Fast", MonteCarloConfig(
            min_think_time_s=0.5,
            max_think_time_s=1.0,
            min_simulations=5,
            max_simulations=50,
        )),
        ("Medium", MonteCarloConfig(
            min_think_time_s=1.0,
            max_think_time_s=2.0,
            min_simulations=5,
            max_simulations=100,
        )),
        ("Slow", MonteCarloConfig(
            min_think_time_s=1.5,
            max_think_time_s=3.0,
            min_simulations=10,
            max_simulations=200,
        )),
        ("Very Slow", MonteCarloConfig(
            min_think_time_s=2.0,
            max_think_time_s=4.0,
            min_simulations=10,
            max_simulations=300,
        )),
    ]

    results = []
    for config_name, config in configs:
        diff, mc_score, random_score = test_config(config_name, config, num_runs=15)
        if diff is not None:
            results.append((config_name, diff, mc_score, random_score))

    # Summary
    print("\n" + "="*70)
    print("SUMMARY")
    print("="*70)
    print(f"{'Config':<15} {'MC Avg':<10} {'Random Avg':<12} {'Difference':<12} {'Status':<10}")
    print("-"*70)

    best_config = None
    best_diff = -100

    for config_name, diff, mc_score, random_score in results:
        status = "✓ PASS" if diff >= 1.0 else "✗ FAIL"
        if diff > best_diff:
            best_diff = diff
            best_config = config_name
        print(f"{config_name:<15} {mc_score:<10.2f} {random_score:<12.2f} {diff:<12.2f} {status:<10}")

    print("\n" + "="*70)
    if best_config and best_diff >= 1.0:
        print(f"✓ SUCCESS: Best configuration is '{best_config}' with {best_diff:.2f} point advantage")
        print("="*70)
    elif best_config:
        print(f"⚠ WARNING: Best configuration is '{best_config}' but only {best_diff:.2f} points better")
        print("  May need to increase thinking time or simulations further")
        print("="*70)
    else:
        print("✗ FAILED: No configuration achieved 1.0+ point advantage")
        print("="*70)

if __name__ == "__main__":
    main()


