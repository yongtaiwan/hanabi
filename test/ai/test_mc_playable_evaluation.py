"""
Test to verify Monte Carlo evaluation correctly values playable cards.

This test creates a simple scenario where we know a card is playable
and verifies that playing it scores higher than discarding it.
"""

from hanabi.core.game import Game, create_standard_game_settings
from hanabi.core.player import PlayerTeam
from hanabi.core.moves import ColorHint, NumberHint, Play, Discard
from hanabi.core.enums import Color, Number
from hanabi.core.card import Card
from hanabi.ai.monte_carlo_player import MonteCarloPlayer, MonteCarloConfig, MCGameState


def test_playable_card_scores_higher():
    """Test that playing a known playable card scores higher than discarding it."""
    print("="*70)
    print("Testing: Playable card should score higher than discard")
    print("="*70)

    # Use a config with more simulations for reliability
    config = MonteCarloConfig(
        min_think_time_s=1.0,
        max_think_time_s=2.0,
        min_simulations=20,
        max_simulations=50,
        rollout_mc_steps=1,
    )

    # Create game
    settings = create_standard_game_settings(3)
    player = MonteCarloPlayer(0, config)
    from hanabi.ai.random_player import RandomPlayer
    team = PlayerTeam([player, RandomPlayer(1), RandomPlayer(2)])
    game = Game.create(team=team, settings=settings)

    # Find a playable color
    common_view = game.state.commonView
    playable_color = None
    for color in [Color.RED, Color.BLUE, Color.GREEN, Color.YELLOW, Color.WHITE]:
        if color not in common_view.cardsPlayed:
            playable_color = color
            break

    if playable_color is None:
        print("SKIP: All colors already started")
        return

    print(f"Using playable color: {playable_color}")

    player_view = game._getPlayerView(0)
    # Give hints that card 0 is this playable color and number 1
    color_hint = ColorHint(teammate=0, color=playable_color, cards=[0])
    number_hint = NumberHint(teammate=0, number=Number.ONE, cards=[0])
    player.observe(0, color_hint, player_view)
    player.observe(0, number_hint, player_view)

    # Verify hints
    hints = player.getHints()
    print(f"Hints for card 0: {hints.get(0, {})}")
    assert 0 in hints
    assert hints[0]["color"] == playable_color
    assert hints[0]["number"] == Number.ONE

    # Verify hint constraint works
    print("\nSampling determinized states to verify hint constraint...")
    for i in range(10):
        world = player._sample_determinized_state(player_view)
        hand = world._hands[0]
        assert hand[0].color == playable_color, f"Card 0 should be {playable_color}, got {hand[0].color}"
        assert hand[0].number == Number.ONE, f"Card 0 should be 1, got {hand[0].number}"
    print("✓ Hint constraint working correctly - card 0 is always the playable card")

    # Now test evaluation
    print("\nEvaluating moves with Monte Carlo...")
    candidate_moves = game.state.generate_all_valid_moves(
        player_view=player_view,
        common_view=common_view,
        game_settings=settings,
        player_index=0,
    )

    # Filter to valid moves
    candidate_moves = [m for m in candidate_moves if player.is_move_legal(player_view, m)]

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

    print(f"Found moves: Play(card=0)={play_move}, Discard(card=0)={discard_move}")

    # Evaluate both moves
    print("\nRunning Monte Carlo evaluation...")
    best_move = player._evaluate_moves_monte_carlo(player_view, candidate_moves)

    print(f"\nSelected move: {best_move}")

    # Check if play scored higher
    # We need to manually check the scores
    scores_sum = [0.0] * len(candidate_moves)
    counts = [0] * len(candidate_moves)

    # Run one batch to see scores
    player._run_one_world_batch(player_view, candidate_moves, scores_sum, counts)

    play_idx = candidate_moves.index(play_move)
    discard_idx = candidate_moves.index(discard_move)

    play_avg = scores_sum[play_idx] / counts[play_idx] if counts[play_idx] > 0 else 0
    discard_avg = scores_sum[discard_idx] / counts[discard_idx] if counts[discard_idx] > 0 else 0

    print(f"\nAfter 1 simulation:")
    print(f"  Play(card=0):   avg={play_avg:.2f}, count={counts[play_idx]}")
    print(f"  Discard(card=0): avg={discard_avg:.2f}, count={counts[discard_idx]}")

    if play_avg < discard_avg:
        print(f"\n✗ FAIL: Play scored lower ({play_avg:.2f}) than discard ({discard_avg:.2f})")
        print("This indicates a bug in the evaluation logic!")
        return False
    else:
        print(f"\n✓ PASS: Play scored higher ({play_avg:.2f}) than discard ({discard_avg:.2f})")
        return True


if __name__ == "__main__":
    test_playable_card_scores_higher()

