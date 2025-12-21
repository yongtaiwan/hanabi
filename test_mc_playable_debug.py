"""
Debug test to understand why Monte Carlo player doesn't play a known '1'.
"""

from hanabi.core.game import Game, create_standard_game_settings
from hanabi.core.player import PlayerTeam
from hanabi.core.moves import NumberHint, Play, Discard
from hanabi.core.enums import Color, Number
from hanabi.ai.monte_carlo_player import MonteCarloPlayer, MonteCarloConfig
from hanabi.ai.random_player import RandomPlayer


def test_known_playable_one():
    """Test that a known playable '1' is played."""
    print("="*70)
    print("Testing: Known playable '1' should be played")
    print("="*70)

    # Use config with enough simulations
    config = MonteCarloConfig(
        min_think_time_s=4.0,
        max_think_time_s=6.0,
        min_simulations=50,
        max_simulations=100,
        rollout_mc_steps=1,
    )

    # Create game
    settings = create_standard_game_settings(3)
    player = MonteCarloPlayer(0, config)
    team = PlayerTeam([player, RandomPlayer(1), RandomPlayer(2)])
    game = Game.create(team=team, settings=settings)

    # Give hint that card 0 is number 1
    number_hint = NumberHint(teammate=0, number=Number.ONE, cards=[0])
    player.observe(1, number_hint)  # Player 1 gives hint to player 0

    # Verify hints
    hints = player.getHints()
    print(f"Hints: {hints}")
    assert 0 in hints
    assert hints[0]["number"] == Number.ONE

    # Get player view
    player_view = game._getPlayerView(0)

    # Generate candidate moves
    from hanabi.core.move_generation import generate_all_valid_moves
    candidate_moves = generate_all_valid_moves(
        player_view=player_view,
        common_view=game.state.commonView,
        game_settings=settings,
        player_index=0,
    )

    # Filter to valid moves
    candidate_moves = [m for m in candidate_moves if player._is_move_valid(m, player_view)]

    # Find Play and Discard moves for card 0
    play_move = None
    discard_move = None
    for move in candidate_moves:
        if isinstance(move, Play) and move.card == 0:
            play_move = move
        elif isinstance(move, Discard) and move.card == 0:
            discard_move = move

    if play_move is None or discard_move is None:
        print(f"SKIP: Could not find both play and discard moves. Play: {play_move}, Discard: {discard_move}")
        return

    print(f"\nCandidate moves found: Play(card=0)={play_move}, Discard(card=0)={discard_move}")
    print(f"Total candidate moves: {len(candidate_moves)}")

    # Evaluate moves
    print("\nEvaluating moves with Monte Carlo...")
    best_move = player._evaluate_moves_monte_carlo(player_view, candidate_moves)

    print(f"\nSelected move: {best_move}")

    if isinstance(best_move, Play) and best_move.card == 0:
        print("✓ PASS: Play(card=0) was selected")
    else:
        print(f"✗ FAIL: Expected Play(card=0), got {best_move}")
        print("\nThis indicates the Monte Carlo evaluation is not correctly valuing the immediate +1 point.")


if __name__ == "__main__":
    test_known_playable_one()

