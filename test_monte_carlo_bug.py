"""
Test script to identify bugs in Monte Carlo player.
Specifically tests that different moves produce different scores.
"""

import sys
from hanabi.core.game import Game, GameSettings
from hanabi.core.player import BasePlayer
from hanabi.core.moves import Play, Discard
from hanabi.ai.monte_carlo_player import MonteCarloPlayer, MonteCarloConfig
from hanabi.ai.random_player import RandomPlayer

def test_move_evaluation():
    """Test that different moves produce different scores."""
    print("=" * 60)
    print("Testing Monte Carlo Move Evaluation")
    print("=" * 60)

    # Create a simple 2-player game
    settings = GameSettings(numPlayers=2)
    game = Game(settings)

    # Create Monte Carlo player with fast config for testing
    config = MonteCarloConfig(
        min_think_time_s=0.1,
        max_think_time_s=0.2,
        min_simulations=3,
        max_simulations=10,
    )
    mc_player = MonteCarloPlayer(0, config)
    random_player = RandomPlayer(1)

    players = [mc_player, random_player]
    game.setPlayers(players)

    # Play a few moves to get to an interesting state
    print("\nSetting up game state...")
    for _ in range(3):
        if game.isFinished():
            break
        move = players[game.currentPlayer].play(game.getPlayerView(game.currentPlayer))
        game.applyMove(move)
        print(f"  Move {game.turnNumber}: {move}")

    if game.isFinished():
        print("Game finished too early, starting new game...")
        game = Game(settings)
        game.setPlayers(players)

    # Now test move evaluation
    print("\n" + "=" * 60)
    print("Testing move evaluation from current state")
    print("=" * 60)

    player_view = game.getPlayerView(0)
    common_view = game.getCommonView()

    print(f"\nCurrent state:")
    print(f"  Score: {common_view.cardsPlayed}")
    print(f"  Hint tokens: {common_view.hintTokens}")
    print(f"  Live tokens: {common_view.liveTokens}")
    print(f"  Player 0 hand size: {player_view.ownHandSize}")

    # Generate candidate moves
    from hanabi.core.move_generation import generate_all_valid_moves
    candidate_moves = generate_all_valid_moves(
        player_view=player_view,
        common_view=common_view,
        game_settings=settings,
        player_index=0,
    )

    print(f"\nCandidate moves: {len(candidate_moves)}")
    for i, move in enumerate(candidate_moves[:5]):  # Show first 5
        print(f"  {i}: {move}")

    # Evaluate moves multiple times and check if scores differ
    print("\n" + "=" * 60)
    print("Running Monte Carlo evaluation (multiple times to check consistency)")
    print("=" * 60)

    for run in range(3):
        print(f"\n--- Run {run + 1} ---")
        best_move = mc_player._evaluate_moves_monte_carlo(player_view, candidate_moves[:5])
        print(f"Selected: {best_move}")

    print("\n" + "=" * 60)
    print("Test complete")
    print("=" * 60)

if __name__ == "__main__":
    test_move_evaluation()


