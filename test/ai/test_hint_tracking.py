"""
Unit tests for hint tracking logic in HintTrackingPlayer.

Tests verify that hints are correctly tracked and shifted when cards are played or discarded.

Indices are left-to-right (C1 = index 0); after a play/discard at ``i``, indices above ``i``
slide down by one, and new draws append on the right (no change to existing indices).
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
        self._observer_view = PlayerView({}, self.player.game_settings.max_cards_in_hand)

    def test_receive_color_hint(self):
        """Test receiving a color hint."""
        hint = ColorHint(teammate=0, color=Color.RED, cards=[0, 2])
        self.player._update_hints_from_hint(hint, self._observer_view)

        hints = self.player.get_hints()
        self.assertEqual(hints[0]["color"], Color.RED)
        self.assertIsNone(hints[0]["number"])
        self.assertEqual(hints[2]["color"], Color.RED)
        self.assertIsNone(hints[2]["number"])

    def test_receive_number_hint(self):
        """Test receiving a number hint."""
        hint = NumberHint(teammate=0, number=Number.ONE, cards=[1, 3])
        self.player._update_hints_from_hint(hint, self._observer_view)

        hints = self.player.get_hints()
        self.assertEqual(hints[1]["number"], Number.ONE)
        self.assertIsNone(hints[1]["color"])
        self.assertEqual(hints[3]["number"], Number.ONE)
        self.assertIsNone(hints[3]["color"])

    def test_receive_multiple_hints(self):
        """Test receiving multiple hints for the same card."""
        color_hint = ColorHint(teammate=0, color=Color.RED, cards=[1])
        number_hint = NumberHint(teammate=0, number=Number.ONE, cards=[1])

        self.player._update_hints_from_hint(color_hint, self._observer_view)
        self.player._update_hints_from_hint(number_hint, self._observer_view)

        hints = self.player.get_hints()
        self.assertEqual(hints[1]["color"], Color.RED)
        self.assertEqual(hints[1]["number"], Number.ONE)

    def test_play_card_at_position_0(self):
        """Play C1 (index 0): remaining cards shift down; hints follow."""
        self.player._hints = {
            0: {"color": Color.RED, "number": None},
            1: {"color": Color.BLUE, "number": None},
            2: {"color": Color.GREEN, "number": None},
            3: {"color": Color.YELLOW, "number": None},
        }

        self.player._update_hints_from_card_move(Play(0))

        hints = self.player.get_hints()
        self.assertEqual(hints[0]["color"], Color.BLUE)
        self.assertEqual(hints[1]["color"], Color.GREEN)
        self.assertEqual(hints[2]["color"], Color.YELLOW)

    def test_play_card_at_position_1(self):
        """Play index 1: indices < 1 unchanged; > 1 shift down by 1."""
        self.player._hints = {
            0: {"color": Color.RED, "number": None},
            1: {"color": Color.BLUE, "number": None},
            2: {"color": Color.GREEN, "number": None},
            3: {"color": Color.YELLOW, "number": None},
        }

        self.player._update_hints_from_card_move(Play(1))

        hints = self.player.get_hints()
        self.assertEqual(hints[0]["color"], Color.RED)
        self.assertEqual(hints[1]["color"], Color.GREEN)
        self.assertEqual(hints[2]["color"], Color.YELLOW)

    def test_play_card_at_position_2(self):
        """Play index 2: only indices > 2 shift down."""
        self.player._hints = {
            0: {"color": Color.RED, "number": None},
            1: {"color": Color.BLUE, "number": None},
            2: {"color": Color.GREEN, "number": None},
            3: {"color": Color.YELLOW, "number": None},
        }

        self.player._update_hints_from_card_move(Play(2))

        hints = self.player.get_hints()
        self.assertEqual(hints[0]["color"], Color.RED)
        self.assertEqual(hints[1]["color"], Color.BLUE)
        self.assertEqual(hints[2]["color"], Color.YELLOW)

    def test_play_card_at_last_position(self):
        """Play rightmost (index 3): only that hint removed."""
        self.player._hints = {
            0: {"color": Color.RED, "number": None},
            1: {"color": Color.BLUE, "number": None},
            2: {"color": Color.GREEN, "number": None},
            3: {"color": Color.YELLOW, "number": None},
        }

        self.player._update_hints_from_card_move(Play(3))

        hints = self.player.get_hints()
        self.assertEqual(hints[0]["color"], Color.RED)
        self.assertEqual(hints[1]["color"], Color.BLUE)
        self.assertEqual(hints[2]["color"], Color.GREEN)

    def test_discard_card_shifts_hints(self):
        """Discarding uses the same index shift as play."""
        self.player._hints = {
            0: {"color": Color.RED, "number": None},
            1: {"color": Color.BLUE, "number": None},
            2: {"color": Color.GREEN, "number": None},
        }

        self.player._update_hints_from_card_move(Discard(1))

        hints = self.player.get_hints()
        self.assertEqual(hints[0]["color"], Color.RED)
        self.assertEqual(hints[1]["color"], Color.GREEN)

    def test_multiple_plays_shift_hints_correctly(self):
        self.player._hints = {
            0: {"color": Color.RED, "number": None},
            1: {"color": Color.BLUE, "number": None},
            2: {"color": Color.GREEN, "number": None},
            3: {"color": Color.YELLOW, "number": None},
        }

        self.player._update_hints_from_card_move(Play(0))
        hints = self.player.get_hints()
        self.assertEqual(hints[0]["color"], Color.BLUE)
        self.assertEqual(hints[1]["color"], Color.GREEN)
        self.assertEqual(hints[2]["color"], Color.YELLOW)

        self.player._update_hints_from_card_move(Play(2))
        hints = self.player.get_hints()
        self.assertEqual(hints[0]["color"], Color.BLUE)
        self.assertEqual(hints[1]["color"], Color.GREEN)

    def test_hint_after_play(self):
        self.player._hints = {
            1: {"color": Color.BLUE, "number": None},
        }

        self.player._update_hints_from_card_move(Play(0))
        hints = self.player.get_hints()
        self.assertEqual(hints[0]["color"], Color.BLUE)

        new_hint = ColorHint(teammate=0, color=Color.RED, cards=[0])
        self.player._update_hints_from_hint(new_hint, self._observer_view)
        hints = self.player.get_hints()
        self.assertEqual(hints[0]["color"], Color.RED)

    def test_observe_hint_only_tracks_own_hints(self):
        """Test that observe() only tracks hints for this player."""
        hint_for_me = ColorHint(teammate=0, color=Color.RED, cards=[0])
        self.player.observe(1, hint_for_me, self._observer_view)

        hints = self.player.get_hints()
        self.assertEqual(hints[0]["color"], Color.RED)

        hint_for_other = ColorHint(teammate=1, color=Color.BLUE, cards=[0])
        self.player.observe(2, hint_for_other, self._observer_view)

        hints = self.player.get_hints()
        self.assertEqual(len(hints), 1)
        self.assertEqual(hints[0]["color"], Color.RED)

    def test_observe_play_only_tracks_own_plays(self):
        """Test that observe() only tracks plays/discards for this player."""
        self.player._hints = {
            0: {"color": Color.RED, "number": None},
            1: {"color": Color.BLUE, "number": None},
        }

        self.player.observe(1, Play(0), self._observer_view)

        hints = self.player.get_hints()
        self.assertEqual(hints[0]["color"], Color.RED)
        self.assertEqual(hints[1]["color"], Color.BLUE)

        self.player.observe(0, Play(0), self._observer_view)

        hints = self.player.get_hints()
        self.assertEqual(hints[0]["color"], Color.BLUE)


if __name__ == "__main__":
    unittest.main()
