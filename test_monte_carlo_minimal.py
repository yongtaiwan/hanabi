"""
Minimal test for Monte Carlo player - just verify it can make a move.
"""

import time
from hanabi.core.game import Game, create_standard_game_settings
from hanabi.core.game_field import GameField
from hanabi.core.player import PlayerTeam
from hanabi.ai.random_player import RandomPlayer
from hanabi.ai.monte_carlo_player import MonteCarloPlayer, MonteCarloConfig


def test_single_move():
    """Test that MonteCarloPlayer can make a single move."""
    print("=" * 70)
    print("MINIMAL TEST: Single Move")
    print("=" * 70)

    # Create a very fast config (minimal thinking time)
    config = MonteCarloConfig(
        min_think_time_s=0.1,  # 100ms
        max_think_time_s=0.2,  # 200ms
        min_simulations=1,     # Minimum 1 simulation
        max_simulations=10,    # Cap at 10 simulations
    )

    # Create game with 2 players (faster)
    settings = create_standard_game_settings(2)
    game_field = GameField.create_from_settings(settings, seed=42)

    # Create team with one MonteCarlo and one Random
    players = [
        MonteCarloPlayer(0, config=config),
        RandomPlayer(1),
    ]
    team = PlayerTeam(players)

    # Create game
    game = Game.create(team=team, settings=settings)

    # Get initial player view
    player_view = game._getPlayerView(0)

    print(f"Initial state: hint_tokens={game.state.commonView.hintTokens}, "
          f"live_tokens={game.state.commonView.liveTokens}")
    print(f"Player 0 hand size: {player_view.ownHandSize}")
    print(f"Teammates: {list(player_view.teammates.keys())}")

    # Test making one move
    print("\nTesting MonteCarloPlayer making a move...")
    start = time.perf_counter()

    try:
        move = players[0].play(player_view)
        elapsed = time.perf_counter() - start

        print(f"✓ Move generated: {move}")
        print(f"✓ Time taken: {elapsed:.3f}s")
        print("\nTest PASSED!")
        return True
    except Exception as e:
        print(f"✗ Error: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_one_turn():
    """Test that MonteCarloPlayer can complete one full turn."""
    print("\n" + "=" * 70)
    print("MINIMAL TEST: One Full Turn")
    print("=" * 70)

    # Create a very fast config
    config = MonteCarloConfig(
        min_think_time_s=0.1,
        max_think_time_s=0.2,
        min_simulations=1,
        max_simulations=10,
    )

    settings = create_standard_game_settings(2)
    game_field = GameField.create_from_settings(settings, seed=42)

    players = [
        MonteCarloPlayer(0, config=config),
        RandomPlayer(1),
    ]
    team = PlayerTeam(players)
    game = Game.create(team=team, settings=settings)

    print(f"Initial state: hint_tokens={game.state.commonView.hintTokens}")
    print(f"Current player: {game.currentPlayer}")

    print("\nProcessing one turn...")
    start = time.perf_counter()

    try:
        # Process one move
        current_player = game.currentPlayer
        player = team.players[current_player]
        player_view = game._getPlayerView(current_player)

        move = player.play(player_view)
        game._processMove(current_player, move)
        game._advanceTurn()

        elapsed = time.perf_counter() - start

        print(f"✓ Turn completed: {move}")
        print(f"✓ Time taken: {elapsed:.3f}s")
        print(f"✓ New state: hint_tokens={game.state.commonView.hintTokens}, "
              f"live_tokens={game.state.commonView.liveTokens}")
        print("\nTest PASSED!")
        return True
    except Exception as e:
        print(f"✗ Error: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_one_game_short():
    """Test one very short game (terminate early)."""
    print("\n" + "=" * 70)
    print("MINIMAL TEST: One Short Game (max 10 turns)")
    print("=" * 70)

    config = MonteCarloConfig(
        min_think_time_s=0.1,
        max_think_time_s=0.2,
        min_simulations=1,
        max_simulations=5,  # Very small
    )

    settings = create_standard_game_settings(2)
    game_field = GameField.create_from_settings(settings, seed=42)

    players = [
        MonteCarloPlayer(0, config=config),
        RandomPlayer(1),
    ]
    team = PlayerTeam(players)
    game = Game.create(team=team, settings=settings)

    print("Playing game (max 10 turns)...")
    start = time.perf_counter()
    turn_count = 0
    max_turns = 10

    try:
        while not game.isFinished and turn_count < max_turns:
            current_player = game.currentPlayer
            player = team.players[current_player]
            player_view = game._getPlayerView(current_player)

            move = player.play(player_view)
            game._processMove(current_player, move)
            game._advanceTurn()

            turn_count += 1
            if turn_count % 5 == 0:
                elapsed = time.perf_counter() - start
                print(f"  Turn {turn_count}: score={game.getScore()}, "
                      f"elapsed={elapsed:.1f}s")

        elapsed = time.perf_counter() - start
        print(f"\n✓ Completed {turn_count} turns")
        print(f"✓ Final score: {game.getScore()}")
        print(f"✓ Time taken: {elapsed:.2f}s")
        print(f"✓ Average time per turn: {elapsed/turn_count:.3f}s")
        print("\nTest PASSED!")
        return True
    except Exception as e:
        print(f"✗ Error: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    print("Running minimal tests for MonteCarloPlayer...")
    print("These tests use very short time budgets to verify functionality.\n")

    results = []

    results.append(("Single Move", test_single_move()))
    results.append(("One Turn", test_one_turn()))
    results.append(("Short Game", test_one_game_short()))

    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    for name, passed in results:
        status = "PASS" if passed else "FAIL"
        print(f"{name}: {status}")

    all_passed = all(passed for _, passed in results)
    if all_passed:
        print("\n✓ All minimal tests passed!")
    else:
        print("\n✗ Some tests failed!")

