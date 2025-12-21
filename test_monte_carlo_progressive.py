"""
Progressive test for Monte Carlo player - starts small and scales up.
"""

import time
from hanabi.core.game import create_standard_game_settings
from hanabi.core.game_field import GameField
from hanabi.ai.random_player import RandomPlayer
from hanabi.ai.monte_carlo_player import MonteCarloPlayer, MonteCarloConfig


def create_random_player(player_index: int) -> RandomPlayer:
    """Factory function to create a RandomPlayer."""
    return RandomPlayer(player_index)


def create_monte_carlo_player_fast(player_index: int) -> MonteCarloPlayer:
    """Factory function to create a fast MonteCarloPlayer."""
    config = MonteCarloConfig(
        min_think_time_s=0.1,   # 100ms
        max_think_time_s=0.2,   # 200ms
        min_simulations=1,
        max_simulations=20,     # Cap at 20 simulations
    )
    return MonteCarloPlayer(player_index, config=config)


def create_monte_carlo_player_medium(player_index: int) -> MonteCarloPlayer:
    """Factory function to create a medium-speed MonteCarloPlayer."""
    config = MonteCarloConfig(
        min_think_time_s=0.3,   # 300ms
        max_think_time_s=0.5,   # 500ms
        min_simulations=2,
        max_simulations=50,     # Cap at 50 simulations
    )
    return MonteCarloPlayer(player_index, config=config)


def test_fast_config():
    """Test with very fast config (100-200ms per turn)."""
    print("=" * 70)
    print("TEST 1: Fast Config (100-200ms per turn)")
    print("=" * 70)

    settings = create_standard_game_settings(2)  # 2 players for speed
    game_field = GameField.create_from_settings(settings, seed=42)

    ai_factories = {
        "RandomPlayer": create_random_player,
        "MonteCarloFast": create_monte_carlo_player_fast,
    }

    print("Running 3 games with fast config...")
    start = time.perf_counter()

    results = game_field.run_experiment(
        ai_factories=ai_factories,
        num_runs=3,
        save_records=False,
        random_seed=42,
        experiment_id="monte_carlo_fast_test"
    )

    elapsed = time.perf_counter() - start

    print(f"\nCompleted in {elapsed:.2f}s")
    print(f"Average time per game: {elapsed/3:.2f}s")

    for ai_name, stats in results.summary.items():
        print(f"\n{ai_name}:")
        print(f"  Average score: {stats.average_score:.2f}")
        print(f"  Average duration: {stats.average_duration:.3f}s")

    return elapsed < 30  # Should complete in under 30 seconds


def test_medium_config():
    """Test with medium config (300-500ms per turn)."""
    print("\n" + "=" * 70)
    print("TEST 2: Medium Config (300-500ms per turn)")
    print("=" * 70)

    settings = create_standard_game_settings(2)
    game_field = GameField.create_from_settings(settings, seed=42)

    ai_factories = {
        "RandomPlayer": create_random_player,
        "MonteCarloMedium": create_monte_carlo_player_medium,
    }

    print("Running 2 games with medium config...")
    start = time.perf_counter()

    results = game_field.run_experiment(
        ai_factories=ai_factories,
        num_runs=2,
        save_records=False,
        random_seed=42,
        experiment_id="monte_carlo_medium_test"
    )

    elapsed = time.perf_counter() - start

    print(f"\nCompleted in {elapsed:.2f}s")
    print(f"Average time per game: {elapsed/2:.2f}s")

    for ai_name, stats in results.summary.items():
        print(f"\n{ai_name}:")
        print(f"  Average score: {stats.average_score:.2f}")
        print(f"  Average duration: {stats.average_duration:.3f}s")

    return elapsed < 60  # Should complete in under 60 seconds


def test_default_config_single():
    """Test with default config but only 1 game."""
    print("\n" + "=" * 70)
    print("TEST 3: Default Config - Single Game (1-2s per turn)")
    print("=" * 70)
    print("WARNING: This may take 30-60 seconds for one game!")

    settings = create_standard_game_settings(2)
    game_field = GameField.create_from_settings(settings, seed=42)

    ai_factories = {
        "RandomPlayer": create_random_player,
        "MonteCarloDefault": lambda i: MonteCarloPlayer(i),
    }

    print("Running 1 game with default config...")
    start = time.perf_counter()

    results = game_field.run_experiment(
        ai_factories=ai_factories,
        num_runs=1,
        save_records=False,
        random_seed=42,
        experiment_id="monte_carlo_default_test"
    )

    elapsed = time.perf_counter() - start

    print(f"\nCompleted in {elapsed:.2f}s")

    for ai_name, stats in results.summary.items():
        print(f"\n{ai_name}:")
        print(f"  Score: {stats.average_score:.2f}")
        print(f"  Duration: {stats.average_duration:.3f}s")
        print(f"  Moves: {stats.average_moves:.1f}")

    return True


if __name__ == "__main__":
    print("Progressive Monte Carlo Player Tests")
    print("Starting with fast configs and scaling up...\n")

    results = []

    try:
        results.append(("Fast Config (3 games)", test_fast_config()))
        results.append(("Medium Config (2 games)", test_medium_config()))
        results.append(("Default Config (1 game)", test_default_config_single()))
    except KeyboardInterrupt:
        print("\n\nTests interrupted by user.")
    except Exception as e:
        print(f"\n\nError during tests: {e}")
        import traceback
        traceback.print_exc()

    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    for name, passed in results:
        status = "PASS" if passed else "FAIL"
        print(f"{name}: {status}")

    print("\nNote: The default config (1-2s per turn) is designed for")
    print("      production use but will be slow for testing.")
    print("      Use fast/medium configs for development and testing.")


