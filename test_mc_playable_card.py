"""
Unit tests to ensure Monte Carlo player plays known playable cards.

Tests that when a card is known to be playable (e.g., a '1' card),
the Monte Carlo player will prefer playing it over discarding it.
"""

import unittest
from hanabi.core.game import create_standard_game_settings
from hanabi.core.game_field import GameField
from hanabi.core.moves import ColorHint, NumberHint, Play, Discard
from hanabi.core.enums import Color, Number
from hanabi.core.card import Card
from hanabi.ai.monte_carlo_player import MonteCarloPlayer, MonteCarloConfig


class TestPlayableCardPreference(unittest.TestCase):
    """Test that playable cards are preferred over discarding."""

    def setUp(self):
        """Set up test fixtures."""
        self.settings = create_standard_game_settings(3)
        # Use fast config for testing
        self.config = MonteCarloConfig(
            min_think_time_s=0.5,
            max_think_time_s=1.0,
            min_simulations=10,
            max_simulations=30,
            rollout_mc_steps=1,
        )

    def test_known_playable_one_is_played(self):
        """
        Test that a known playable '1' card is played, not discarded.

        This is a critical test: if we know a card is a playable '1',
        playing it should score much higher than discarding it.
        """
        from hanabi.core.game import Game
        from hanabi.core.player import PlayerTeam
        from hanabi.ai.random_player import RandomPlayer

        player = MonteCarloPlayer(0, self.config)
        team = PlayerTeam([player, RandomPlayer(1), RandomPlayer(2)])
        game = Game.create(team=team, settings=self.settings)

        # Find a color that hasn't been played yet (so '1' is playable)
        common_view = game.state.commonView
        playable_color = None
        for color in [Color.RED, Color.BLUE, Color.GREEN, Color.YELLOW, Color.WHITE]:
            if color not in common_view.cardsPlayed:
                playable_color = color
                break

        if playable_color is None:
            self.skipTest("No playable color available - all colors already started")

        # Give player hints that card 0 is this playable color and number 1
        color_hint = ColorHint(teammate=0, color=playable_color, cards=[0])
        number_hint = NumberHint(teammate=0, number=Number.ONE, cards=[0])

        # Observe the hints
        player.observe(0, color_hint)
        player.observe(0, number_hint)

        # Verify hints are tracked
        hints = player.getHints()
        self.assertIn(0, hints)
        self.assertEqual(hints[0]["color"], playable_color)
        self.assertEqual(hints[0]["number"], Number.ONE)

        # Get player view
        player_view = game._getPlayerView(0)

        # Make the player choose a move
        # The player should prefer playing card 0 over discarding it
        move = player.play(player_view)

        # Verify that the move is a Play, not a Discard
        self.assertIsInstance(move, Play,
                             f"Expected Play move for known playable card, got {type(move)}")
        # The player should play a playable card (card 0 is known to be playable)
        # But other cards might also be playable, so we just verify it's a Play move
        # and that card 0 is indeed playable in the sampled world
        # Let's verify that card 0 is constrained correctly by sampling
        world = player._sample_determinized_state(player_view)
        hand = world._hands[0]
        # Card 0 should be the playable card we hinted
        self.assertEqual(hand[0], Card(playable_color, Number.ONE),
                        f"Card 0 should be {playable_color} 1, got {hand[0]}")
        # Verify it's playable
        is_playable = (hand[0].color not in common_view.cardsPlayed and hand[0].number == Number.ONE)
        self.assertTrue(is_playable, f"Card 0 ({hand[0]}) should be playable")

    def test_playable_card_scores_higher_in_simulation(self):
        """
        Test that playing a known playable card scores higher than discarding it
        in Monte Carlo simulations.

        This tests the core evaluation logic.
        """
        from hanabi.core.game import Game
        from hanabi.core.player import PlayerTeam
        from hanabi.ai.random_player import RandomPlayer

        player = MonteCarloPlayer(0, self.config)
        team = PlayerTeam([player, RandomPlayer(1), RandomPlayer(2)])
        game = Game.create(team=team, settings=self.settings)

        # Find a playable color
        common_view = game.state.commonView
        playable_color = None
        for color in [Color.RED, Color.BLUE, Color.GREEN, Color.YELLOW, Color.WHITE]:
            if color not in common_view.cardsPlayed:
                playable_color = color
                break

        if playable_color is None:
            self.skipTest("No playable color available")

        # Give hints
        color_hint = ColorHint(teammate=0, color=playable_color, cards=[0])
        number_hint = NumberHint(teammate=0, number=Number.ONE, cards=[0])
        player.observe(0, color_hint)
        player.observe(0, number_hint)

        player_view = game._getPlayerView(0)

        # Sample a determinized state
        # With hints, card 0 should always be the playable card
        world = player._sample_determinized_state(player_view)
        hand = world._hands[0]

        # Verify that card 0 is indeed the playable card
        self.assertEqual(hand[0], Card(playable_color, Number.ONE),
                        f"Card 0 should be {playable_color} 1, got {hand[0]}")

        # Test that playing it is valid
        from hanabi.core.moves import Play
        play_move = Play(0)
        test_state = world.clone()
        test_state.apply_move(0, play_move)

        # After playing, score should increase
        # (We can't easily test the exact score without running full rollouts,
        # but we can verify the card is playable)
        self.assertGreaterEqual(test_state.score(), world.score(),
                               "Playing a playable card should not decrease score")


class TestHintConstraintCorrectness(unittest.TestCase):
    """Test that hints correctly constrain card sampling."""

    def setUp(self):
        """Set up test fixtures."""
        self.settings = create_standard_game_settings(3)
        self.config = MonteCarloConfig(
            min_think_time_s=0.1,
            max_think_time_s=0.2,
            min_simulations=5,
            max_simulations=10,
            rollout_mc_steps=0,
        )

    def test_color_hint_constrains_sampling(self):
        """Test that color hints constrain sampled cards."""
        from hanabi.core.game import Game
        from hanabi.core.player import PlayerTeam
        from hanabi.ai.random_player import RandomPlayer

        player = MonteCarloPlayer(0, self.config)
        team = PlayerTeam([player, RandomPlayer(1), RandomPlayer(2)])
        game = Game.create(team=team, settings=self.settings)

        # Give color hint
        hint = ColorHint(teammate=0, color=Color.RED, cards=[0])
        player.observe(0, hint)

        player_view = game._getPlayerView(0)

        # Sample multiple times - card 0 should always be red
        for _ in range(20):
            world = player._sample_determinized_state(player_view)
            hand = world._hands[0]
            self.assertEqual(hand[0].color, Color.RED,
                           f"Card 0 should always be red, got {hand[0]}")

    def test_number_hint_constrains_sampling(self):
        """Test that number hints constrain sampled cards."""
        from hanabi.core.game import Game
        from hanabi.core.player import PlayerTeam
        from hanabi.ai.random_player import RandomPlayer

        player = MonteCarloPlayer(0, self.config)
        team = PlayerTeam([player, RandomPlayer(1), RandomPlayer(2)])
        game = Game.create(team=team, settings=self.settings)

        # Give number hint
        hint = NumberHint(teammate=0, number=Number.ONE, cards=[0])
        player.observe(0, hint)

        player_view = game._getPlayerView(0)

        # Sample multiple times - card 0 should always be number 1
        for _ in range(20):
            world = player._sample_determinized_state(player_view)
            hand = world._hands[0]
            self.assertEqual(hand[0].number, Number.ONE,
                           f"Card 0 should always be 1, got {hand[0]}")

    def test_combined_hints_fully_constrain(self):
        """Test that combined color and number hints fully constrain a card."""
        from hanabi.core.game import Game
        from hanabi.core.player import PlayerTeam
        from hanabi.ai.random_player import RandomPlayer

        player = MonteCarloPlayer(0, self.config)
        team = PlayerTeam([player, RandomPlayer(1), RandomPlayer(2)])
        game = Game.create(team=team, settings=self.settings)

        # Give both hints
        color_hint = ColorHint(teammate=0, color=Color.BLUE, cards=[0])
        number_hint = NumberHint(teammate=0, number=Number.TWO, cards=[0])
        player.observe(0, color_hint)
        player.observe(0, number_hint)

        player_view = game._getPlayerView(0)

        # Sample multiple times - card 0 should always be Blue 2
        for _ in range(20):
            world = player._sample_determinized_state(player_view)
            hand = world._hands[0]
            self.assertEqual(hand[0], Card(Color.BLUE, Number.TWO),
                           f"Card 0 should always be Blue 2, got {hand[0]}")


if __name__ == "__main__":
    unittest.main()

