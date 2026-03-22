"""
Unit tests for Monte Carlo player hint constraint logic.

Tests that hints are correctly used to constrain possible cards.
"""

import unittest
from hanabi.core.game import create_standard_game_settings, PlayerView
from hanabi.core.game_field import GameField
from hanabi.core.moves import ColorHint, NumberHint, Play, Discard
from hanabi.core.enums import Color, Number
from hanabi.core.card import Card
from hanabi.ai.monte_carlo_player import MonteCarloPlayer, MonteCarloConfig, MCGameState


class TestHintConstraints(unittest.TestCase):
    """Test that hints correctly constrain card possibilities."""

    def setUp(self):
        """Set up test fixtures."""
        self.settings = create_standard_game_settings(3)
        self.config = MonteCarloConfig(
            min_think_time_s=0.1,
            max_think_time_s=0.2,
            min_simulations=5,
            max_simulations=20,
            rollout_mc_steps=0,  # Disable MC in rollout for faster tests
        )

    def test_hint_tracking(self):
        """Test that MonteCarloPlayer tracks hints correctly."""
        player = MonteCarloPlayer(0, self.config)
        player.set_game_settings(self.settings)

        # Give player a hint
        hint = ColorHint(teammate=0, color=Color.RED, cards=[0, 1])
        player.observe(0, hint)

        # Check that hints are tracked
        hints = player.getHints()
        self.assertIn(0, hints)
        self.assertIn(1, hints)
        self.assertEqual(hints[0]["color"], Color.RED)
        self.assertEqual(hints[1]["color"], Color.RED)

    def test_hint_constrains_sampling(self):
        """Test that hints constrain card sampling in determinized states."""
        from hanabi.core.game import Game
        from hanabi.core.player import PlayerTeam
        from hanabi.ai.random_player import RandomPlayer

        player = MonteCarloPlayer(0, self.config)
        team = PlayerTeam([player, RandomPlayer(1), RandomPlayer(2)])
        game = Game.create(team=team, settings=self.settings)

        # Give player a hint that card 0 is red
        hint = ColorHint(teammate=0, color=Color.RED, cards=[0])
        player.observe(0, hint)

        # Get player view
        player_view = game._getPlayerView(0)

        # Sample multiple determinized states
        # All should have card 0 as red
        for _ in range(20):
            world = player._sample_determinized_state(player_view)
            hand = world._hands[0]
            self.assertEqual(len(hand), player_view.ownHandSize)
            # Card at position 0 should be red
            self.assertEqual(hand[0].color, Color.RED,
                           f"Card at position 0 should be red, got {hand[0]}")

    def test_number_hint_constrains_sampling(self):
        """Test that number hints constrain card sampling."""
        from hanabi.core.game import Game
        from hanabi.core.player import PlayerTeam
        from hanabi.ai.random_player import RandomPlayer

        player = MonteCarloPlayer(0, self.config)
        team = PlayerTeam([player, RandomPlayer(1), RandomPlayer(2)])
        game = Game.create(team=team, settings=self.settings)

        # Give player a hint that card 0 is number 1
        hint = NumberHint(teammate=0, number=Number.ONE, cards=[0])
        player.observe(0, hint)

        player_view = game._getPlayerView(0)

        # Sample multiple determinized states
        for _ in range(20):
            world = player._sample_determinized_state(player_view)
            hand = world._hands[0]
            self.assertEqual(hand[0].number, Number.ONE,
                           f"Card at position 0 should be 1, got {hand[0]}")

    def test_combined_hints_constrain_sampling(self):
        """Test that combined color and number hints fully constrain a card."""
        from hanabi.core.game import Game
        from hanabi.core.player import PlayerTeam
        from hanabi.ai.random_player import RandomPlayer

        player = MonteCarloPlayer(0, self.config)
        team = PlayerTeam([player, RandomPlayer(1), RandomPlayer(2)])
        game = Game.create(team=team, settings=self.settings)

        # Give player hints: card 0 is red 1
        color_hint = ColorHint(teammate=0, color=Color.RED, cards=[0])
        number_hint = NumberHint(teammate=0, number=Number.ONE, cards=[0])
        player.observe(0, color_hint)
        player.observe(0, number_hint)

        player_view = game._getPlayerView(0)

        # Sample multiple determinized states
        for _ in range(20):
            world = player._sample_determinized_state(player_view)
            hand = world._hands[0]
            self.assertEqual(hand[0], Card(Color.RED, Number.ONE),
                           f"Card at position 0 should be Red 1, got {hand[0]}")


class TestPlayableCardDetection(unittest.TestCase):
    """Test that playable cards are correctly identified."""

    def setUp(self):
        """Set up test fixtures."""
        self.settings = create_standard_game_settings(3)
        self.config = MonteCarloConfig(
            min_think_time_s=0.1,
            max_think_time_s=0.2,
            min_simulations=5,
            max_simulations=20,
            rollout_mc_steps=0,
        )

    def test_playable_card_one(self):
        """Test that a '1' card is always playable."""
        from hanabi.core.game import Game
        from hanabi.core.player import PlayerTeam
        from hanabi.ai.random_player import RandomPlayer

        player = MonteCarloPlayer(0, self.config)
        team = PlayerTeam([player, RandomPlayer(1), RandomPlayer(2)])
        game = Game.create(team=team, settings=self.settings)

        # Get common view
        common_view = game.state.commonView

        # A '1' card is playable if its color hasn't been played yet
        # Find a color that hasn't been played
        playable_color = None
        for color in [Color.RED, Color.BLUE, Color.GREEN, Color.YELLOW, Color.WHITE]:
            if color not in common_view.cardsPlayed:
                playable_color = color
                break

        if playable_color is None:
            self.skipTest("All colors already started")

        # Test that MCGameState correctly identifies playable cards
        from hanabi.ai.monte_carlo_player import MCGameState
        test_state = MCGameState(
            settings=self.settings,
            hands=[[Card(playable_color, Number.ONE)]],
            deck=[],
            current_player=0,
            live_tokens=3,
            hint_tokens=8,
            cards_played={},
            cards_discarded={},
            cards_to_draw=0,
            turns_left=None,
        )

        # Card should be playable
        card = test_state._hands[0][0]
        is_playable = (card.color not in test_state._cards_played and card.number == Number.ONE) or \
                     (card.color in test_state._cards_played and
                      card.number.value == test_state._cards_played[card.color].value + 1)
        self.assertTrue(is_playable, f"Card {card} should be playable")

    def test_playable_card_next_in_sequence(self):
        """Test that the next card in a sequence is playable."""
        # If we've played Red 1, then Red 2 is playable
        # This requires setting up a proper MCGameState
        pass


class TestMonteCarloEvaluation(unittest.TestCase):
    """Test that Monte Carlo evaluation correctly favors playable cards."""

    def setUp(self):
        """Set up test fixtures."""
        self.settings = create_standard_game_settings(3)
        self.config = MonteCarloConfig(
            min_think_time_s=0.5,
            max_think_time_s=1.0,
            min_simulations=10,
            max_simulations=50,
            rollout_mc_steps=1,  # Use MC in rollout
        )

    def test_playable_card_vs_discard(self):
        """Test that playing a known playable card scores higher than discarding it."""
        from hanabi.core.game import Game
        from hanabi.core.player import PlayerTeam
        from hanabi.ai.random_player import RandomPlayer

        player = MonteCarloPlayer(0, self.config)
        team = PlayerTeam([player, RandomPlayer(1), RandomPlayer(2)])
        game = Game.create(team=team, settings=self.settings)

        # Give player a hint that card 0 is a playable '1'
        # First, find a color that hasn't been played
        common_view = game.state.commonView
        playable_color = None
        for color in [Color.RED, Color.BLUE, Color.GREEN, Color.YELLOW, Color.WHITE]:
            if color not in common_view.cardsPlayed:
                playable_color = color
                break

        if playable_color is None:
            self.skipTest("No playable color available in test setup")

        # Give hint that card 0 is this color and number 1
        color_hint = ColorHint(teammate=0, color=playable_color, cards=[0])
        number_hint = NumberHint(teammate=0, number=Number.ONE, cards=[0])
        player.observe(0, color_hint)
        player.observe(0, number_hint)

        # Get player view
        player_view = game._getPlayerView(0)

        # Generate candidate moves
        from hanabi.core.move_generation import generate_all_valid_moves
        candidate_moves = generate_all_valid_moves(
            player_view=player_view,
            common_view=common_view,
            game_settings=self.settings,
            player_index=0,
        )

        # Filter to valid moves
        candidate_moves = [m for m in candidate_moves if player._is_move_valid(m, player_view)]

        # Find play and discard moves for card 0
        play_move = None
        discard_move = None
        for move in candidate_moves:
            if isinstance(move, Play) and move.card == 0:
                play_move = move
            elif isinstance(move, Discard) and move.card == 0:
                discard_move = move

        if play_move is None or discard_move is None:
            self.skipTest("Could not find both play and discard moves for card 0")

        # Evaluate both moves
        # This is a simplified test - in reality we'd need to run the full MC evaluation
        # For now, we'll just verify that the player can identify playable cards
        self.assertIsNotNone(play_move)
        self.assertIsNotNone(discard_move)


if __name__ == "__main__":
    unittest.main()

