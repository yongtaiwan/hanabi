"""
Unit tests for hint tracking logic in HintTrackingPlayer.

Tests verify that hints are correctly tracked and shifted when cards are played/discarded.
"""

import unittest
from hanabi.core.player import HumanPlayer
from hanabi.core.game import create_standard_game_settings, PlayerView
from hanabi.core.moves import ColorHint, NumberHint, Play, Discard
from hanabi.core.enums import Color, Number


class TestHintTracking(unittest.TestCase):
    """Test hint tracking logic."""

    def setUp(self):
        """Set up test fixtures."""
        self.player = HumanPlayer(0)
        self.player.set_game_settings(create_standard_game_settings(3))
        self._observer_view = PlayerView({}, self.player.gameSettings.maxCardsInHand)

    def test_receive_color_hint(self):
        """Test receiving a color hint."""
        hint = ColorHint(teammate=0, color=Color.RED, cards=[0, 2])
        self.player._updateHintsFromHint(hint)

        hints = self.player.getHints()
        self.assertEqual(hints[0]["color"], Color.RED)
        self.assertIsNone(hints[0]["number"])
        self.assertEqual(hints[2]["color"], Color.RED)
        self.assertIsNone(hints[2]["number"])

    def test_receive_number_hint(self):
        """Test receiving a number hint."""
        hint = NumberHint(teammate=0, number=Number.ONE, cards=[1, 3])
        self.player._updateHintsFromHint(hint)

        hints = self.player.getHints()
        self.assertEqual(hints[1]["number"], Number.ONE)
        self.assertIsNone(hints[1]["color"])
        self.assertEqual(hints[3]["number"], Number.ONE)
        self.assertIsNone(hints[3]["color"])

    def test_receive_multiple_hints(self):
        """Test receiving multiple hints for the same card."""
        color_hint = ColorHint(teammate=0, color=Color.RED, cards=[1])
        number_hint = NumberHint(teammate=0, number=Number.ONE, cards=[1])

        self.player._updateHintsFromHint(color_hint)
        self.player._updateHintsFromHint(number_hint)

        hints = self.player.getHints()
        self.assertEqual(hints[1]["color"], Color.RED)
        self.assertEqual(hints[1]["number"], Number.ONE)

    def test_play_card_at_position_0(self):
        """Test playing card at position 0 - all hints should shift right by 1."""
        # Set up hints at positions 0, 1, 2, 3
        self.player._hints = {
            0: {"color": Color.RED, "number": None},
            1: {"color": Color.BLUE, "number": None},
            2: {"color": Color.GREEN, "number": None},
            3: {"color": Color.YELLOW, "number": None},
        }

        # Play card at position 0
        move = Play(0)
        self.player._updateHintsFromCardMove(move)

        hints = self.player.getHints()
        # Position 0 hint (RED) should be removed (card was played)
        # New card fills position 0, so all other cards stay at same positions (no net shift)
        self.assertEqual(hints[1]["color"], Color.BLUE)  # Was at 1, stays at 1
        self.assertEqual(hints[2]["color"], Color.GREEN)  # Was at 2, stays at 2
        self.assertEqual(hints[3]["color"], Color.YELLOW)  # Was at 3, stays at 3

    def test_play_card_at_position_1(self):
        """Test playing card at position 1 - hints < 1 shift right, hints > 1 stay same."""
        # Set up hints at positions 0, 1, 2, 3
        self.player._hints = {
            0: {"color": Color.RED, "number": None},
            1: {"color": Color.BLUE, "number": None},
            2: {"color": Color.GREEN, "number": None},
            3: {"color": Color.YELLOW, "number": None},
        }

        # Play card at position 1
        move = Play(1)
        self.player._updateHintsFromCardMove(move)

        hints = self.player.getHints()
        # Position 1 hint (BLUE) should be removed
        # Hints at positions < 1 should shift right by 1
        self.assertEqual(hints[1]["color"], Color.RED)  # Was at 0, shifted to 1
        # Hints at positions > 1 should stay the same
        self.assertEqual(hints[2]["color"], Color.GREEN)  # Was at 2, stays at 2
        self.assertEqual(hints[3]["color"], Color.YELLOW)  # Was at 3, stays at 3
        # Position 1 now has RED (from position 0), not BLUE (which was removed)

    def test_play_card_at_position_2(self):
        """Test playing card at position 2 - hints < 2 shift right, hints > 2 stay same."""
        # Set up hints at positions 0, 1, 2, 3
        self.player._hints = {
            0: {"color": Color.RED, "number": None},
            1: {"color": Color.BLUE, "number": None},
            2: {"color": Color.GREEN, "number": None},
            3: {"color": Color.YELLOW, "number": None},
        }

        # Play card at position 2
        move = Play(2)
        self.player._updateHintsFromCardMove(move)

        hints = self.player.getHints()
        # Position 2 hint (GREEN) should be removed
        # Hints at positions < 2 should shift right by 1
        self.assertEqual(hints[1]["color"], Color.RED)  # Was at 0, shifted to 1
        self.assertEqual(hints[2]["color"], Color.BLUE)  # Was at 1, shifted to 2
        # Hints at positions > 2 should stay the same
        self.assertEqual(hints[3]["color"], Color.YELLOW)  # Was at 3, stays at 3
        # Position 2 now has BLUE (from position 1), not GREEN (which was removed)

    def test_play_card_at_last_position(self):
        """Test playing card at last position - all other hints shift right."""
        # Set up hints at positions 0, 1, 2, 3
        self.player._hints = {
            0: {"color": Color.RED, "number": None},
            1: {"color": Color.BLUE, "number": None},
            2: {"color": Color.GREEN, "number": None},
            3: {"color": Color.YELLOW, "number": None},
        }

        # Play card at position 3 (last)
        move = Play(3)
        self.player._updateHintsFromCardMove(move)

        hints = self.player.getHints()
        # Position 3 hint (YELLOW) should be removed
        # All other hints should shift right by 1
        self.assertEqual(hints[1]["color"], Color.RED)  # Was at 0, shifted to 1
        self.assertEqual(hints[2]["color"], Color.BLUE)  # Was at 1, shifted to 2
        self.assertEqual(hints[3]["color"], Color.GREEN)  # Was at 2, shifted to 3
        # Position 3 now has GREEN (from position 2), not YELLOW (which was removed)

    def test_discard_card_shifts_hints(self):
        """Test that discarding a card also shifts hints."""
        # Set up hints at positions 0, 1, 2
        self.player._hints = {
            0: {"color": Color.RED, "number": None},
            1: {"color": Color.BLUE, "number": None},
            2: {"color": Color.GREEN, "number": None},
        }

        # Discard card at position 1
        move = Discard(1)
        self.player._updateHintsFromCardMove(move)

        hints = self.player.getHints()
        # Position 1 hint (BLUE) should be removed
        # Hints should shift correctly
        self.assertEqual(hints[1]["color"], Color.RED)  # Was at 0, shifted to 1
        self.assertEqual(hints[2]["color"], Color.GREEN)  # Was at 2, stays at 2
        # Position 1 now has RED (from position 0), not BLUE (which was removed)

    def test_multiple_plays_shift_hints_correctly(self):
        """Test that multiple plays shift hints correctly."""
        # Set up hints at positions 0, 1, 2, 3
        self.player._hints = {
            0: {"color": Color.RED, "number": None},
            1: {"color": Color.BLUE, "number": None},
            2: {"color": Color.GREEN, "number": None},
            3: {"color": Color.YELLOW, "number": None},
        }

        # Play card at position 0 (RED hint removed)
        self.player._updateHintsFromCardMove(Play(0))
        # New card fills position 0, so remaining hints stay at same positions
        hints = self.player.getHints()
        self.assertEqual(hints[1]["color"], Color.BLUE)  # Was at 1, stays at 1
        self.assertEqual(hints[2]["color"], Color.GREEN)  # Was at 2, stays at 2
        self.assertEqual(hints[3]["color"], Color.YELLOW)  # Was at 3, stays at 3

        # Play card at position 2 (GREEN hint removed)
        self.player._updateHintsFromCardMove(Play(2))
        # Position 2 hint (GREEN) removed, positions < 2 shift right, positions > 2 stay same
        hints = self.player.getHints()
        self.assertEqual(hints[2]["color"], Color.BLUE)  # Was at 1, shifted to 2
        self.assertEqual(hints[3]["color"], Color.YELLOW)  # Was at 3, stays at 3

    def test_hint_after_play(self):
        """Test receiving a hint after playing a card."""
        # Set up initial hint
        self.player._hints = {
            1: {"color": Color.BLUE, "number": None},
        }

        # Play card at position 0
        self.player._updateHintsFromCardMove(Play(0))
        # New card fills position 0, so hint at position 1 stays at position 1
        hints = self.player.getHints()
        self.assertEqual(hints[1]["color"], Color.BLUE)

        # Receive new hint at position 0
        new_hint = ColorHint(teammate=0, color=Color.RED, cards=[0])
        self.player._updateHintsFromHint(new_hint)
        hints = self.player.getHints()
        self.assertEqual(hints[0]["color"], Color.RED)
        self.assertEqual(hints[1]["color"], Color.BLUE)  # Still at position 1

    def test_observe_hint_only_tracks_own_hints(self):
        """Test that observe() only tracks hints for this player."""
        # Hint for this player (player 0)
        hint_for_me = ColorHint(teammate=0, color=Color.RED, cards=[0])
        self.player.observe(1, hint_for_me, self._observer_view)  # Player 1 gives hint to player 0

        hints = self.player.getHints()
        self.assertEqual(hints[0]["color"], Color.RED)

        # Hint for another player (player 1)
        hint_for_other = ColorHint(teammate=1, color=Color.BLUE, cards=[0])
        self.player.observe(2, hint_for_other, self._observer_view)  # Player 2 gives hint to player 1

        # Should not affect this player's hints
        hints = self.player.getHints()
        self.assertEqual(len(hints), 1)
        self.assertEqual(hints[0]["color"], Color.RED)

    def test_observe_play_only_tracks_own_plays(self):
        """Test that observe() only tracks plays/discards for this player."""
        # Set up hints
        self.player._hints = {
            0: {"color": Color.RED, "number": None},
            1: {"color": Color.BLUE, "number": None},
        }

        # Another player plays a card
        self.player.observe(1, Play(0), self._observer_view)  # Player 1 plays their card 0

        # Should not affect this player's hints
        hints = self.player.getHints()
        self.assertEqual(hints[0]["color"], Color.RED)
        self.assertEqual(hints[1]["color"], Color.BLUE)

        # This player plays a card
        self.player.observe(0, Play(0), self._observer_view)  # Player 0 plays their card 0

        # RED hint at 0 is removed, new card fills position 0, so BLUE hint stays at 1
        hints = self.player.getHints()
        self.assertEqual(hints[1]["color"], Color.BLUE)  # Was at 1, stays at 1


if __name__ == "__main__":
    unittest.main()

