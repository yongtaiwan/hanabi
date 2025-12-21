"""
Investigate why Monte Carlo player doesn't play a known '1'.
Run a real game scenario and check debug output.
"""

from hanabi.core.game import Game, create_standard_game_settings
from hanabi.core.player import PlayerTeam
from hanabi.core.moves import NumberHint, Play
from hanabi.core.enums import Number
from hanabi.ai.monte_carlo_player import MonteCarloPlayer, MonteCarloConfig
from hanabi.ai.random_player import RandomPlayer
import sys


def test_real_scenario():
    """Run a real game scenario and check what happens."""
    print("="*70)
    print("Testing: Real game scenario with known playable '1'")
    print("="*70)

    # Use config with enough simulations and debug logging
    config = MonteCarloConfig(
        min_think_time_s=4.0,
        max_think_time_s=6.0,
        min_simulations=30,
        max_simulations=100,
        rollout_mc_steps=1,
    )

    # Create game
    settings = create_standard_game_settings(3)
    mc_player = MonteCarloPlayer(0, config)
    team = PlayerTeam([mc_player, RandomPlayer(1), RandomPlayer(2)])
    game = Game.create(team=team, settings=settings)

    # Get initial state
    player_view = game._getPlayerView(0)
    print(f"\nInitial hand size: {player_view.ownHandSize}")
    print(f"Initial cards played: {game.state.commonView.cardsPlayed}")

    # Give hint that card 0 is number 1
    number_hint = NumberHint(teammate=0, number=Number.ONE, cards=[0])
    mc_player.observe(1, number_hint)  # Player 1 gives hint to player 0

    # Verify hints
    hints = mc_player.getHints()
    print(f"\nHints after giving hint: {hints}")

    # Get updated player view
    player_view = game._getPlayerView(0)

    # Check what card is actually at position 0
    # We can't see it, but we can check if it's playable based on hints
    if 0 in hints and hints[0].get("number") == Number.ONE:
        print("\n✓ Position 0 has hint for number 1 - should be playable")
        print("  (Any '1' is always playable)")

    # Now have the Monte Carlo player make a move
    print("\n" + "="*70)
    print("Monte Carlo player making a move...")
    print("="*70)
    print("\n(Check stderr for debug output)\n")

    # Capture stderr to see debug output
    move = mc_player.play(player_view)

    print(f"\nSelected move: {move}")

    if isinstance(move, Play) and move.card == 0:
        print("✓ PASS: Play(card=0) was selected")
    else:
        print(f"✗ FAIL: Expected Play(card=0), got {move}")
        print("\nThis suggests the Monte Carlo evaluation is not correctly valuing the immediate +1 point.")


if __name__ == "__main__":
    test_real_scenario()

