"""
Simple test to debug Monte Carlo player.
"""

import sys
from hanabi.core.game import Game, create_standard_game_settings
from hanabi.core.moves import Play
from hanabi.ai.monte_carlo_player import MonteCarloPlayer, MonteCarloConfig
from hanabi.ai.random_player import RandomPlayer

# Create game
settings = create_standard_game_settings(2)
game = Game(settings)

# Create players
config = MonteCarloConfig(
    min_think_time_s=0.05,
    max_think_time_s=0.1,
    min_simulations=2,
    max_simulations=5,
)
mc_player = MonteCarloPlayer(0, config)
random_player = RandomPlayer(1)

players = [mc_player, random_player]
game.setPlayers(players)

# Play a few moves
print("Setting up game...")
for _ in range(2):
    if game.isFinished():
        break
    move = players[game.currentPlayer].play(game.getPlayerView(game.currentPlayer))
    game.applyMove(move)
    print(f"  {move}")

if game.isFinished():
    print("Game finished, creating new game...")
    game = Game(settings)
    game.setPlayers(players)

# Now test move evaluation
print("\n" + "="*60)
print("Testing move evaluation")
print("="*60)

player_view = game.getPlayerView(0)
from hanabi.core.move_generation import generate_all_valid_moves
moves = generate_all_valid_moves(
    player_view=player_view,
    common_view=game.getCommonView(),
    game_settings=settings,
    player_index=0,
)

# Filter to just Play moves for simplicity
play_moves = [m for m in moves if isinstance(m, Play)][:3]
print(f"\nEvaluating {len(play_moves)} Play moves: {play_moves}")

# Evaluate
best_move = mc_player._evaluate_moves_monte_carlo(player_view, play_moves)
print(f"\nSelected: {best_move}")

