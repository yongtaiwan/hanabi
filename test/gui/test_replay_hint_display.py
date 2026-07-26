"""Regression tests for GUI under-card hint badges and last-turn banner during replay seek."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock

import tkinter as tk

from hanabi.core.enums import Color, Number
from hanabi.core.moves import ColorHint, NumberHint, Play
from hanabi.gui.gui_display import GUIDisplay


class TestReplayHintDisplay(unittest.TestCase):
    """GUI ``_hints`` must reset on rebuild; color/number fields must not merge across seeks."""

    def setUp(self) -> None:
        self.root = tk.Tk()
        self.root.withdraw()
        self.display = GUIDisplay(self.root)
        self.display.set_suppress_dialogs(True)

    def tearDown(self) -> None:
        self.root.destroy()

    def test_partial_hint_update_keeps_stale_field_without_clear(self) -> None:
        """Color and number are written independently; uncleared slots keep stale fields."""
        self.display.update_hints_from_move(0, ColorHint(1, [0], Color.RED))
        self.display.update_hints_from_move(0, NumberHint(1, [0], Number.ONE))
        self.assertEqual(Color.RED, self.display._hints[1][0]["color"])
        self.assertEqual(Number.ONE, self.display._hints[1][0]["number"])

        # Simulate seek to a prefix that only had the color hint, without clearing.
        self.display.update_hints_from_move(0, ColorHint(1, [0], Color.RED))
        self.assertEqual(
            Number.ONE,
            self.display._hints[1][0]["number"],
            "without clear, number from a later seek remains — the replay desync",
        )

    def test_clear_before_rebuild_keeps_color_and_number_in_sync(self) -> None:
        """Clearing ``_hints`` then replaying a shorter prefix drops later fields."""
        self.display.update_hints_from_move(0, ColorHint(1, [0], Color.RED))
        self.display.update_hints_from_move(0, NumberHint(1, [0], Number.ONE))

        self.display._hints.clear()
        self.display.update_hints_from_move(0, ColorHint(1, [0], Color.RED))

        self.assertEqual(Color.RED, self.display._hints[1][0]["color"])
        self.assertIsNone(self.display._hints[1][0]["number"])

    def test_card_move_applied_twice_shifts_hints_twice(self) -> None:
        """Duplicate play/discard updates (old replay path) attach badges to wrong slots."""
        self.display._hints[0] = {
            0: {"color": Color.RED, "number": None},
            2: {"color": None, "number": Number.THREE},
        }
        play = Play(0)
        self.display.update_hints_from_move(0, play)
        self.assertEqual(
            {1: {"color": None, "number": Number.THREE}},
            self.display._hints[0],
        )

        # Second apply (bug) shifts again even though the card already left.
        self.display.update_hints_from_move(0, play)
        self.assertEqual(
            {0: {"color": None, "number": Number.THREE}},
            self.display._hints[0],
            "double update leaves number badge on the wrong card index",
        )


class TestLastTurnBanner(unittest.TestCase):
    """LAST TURN banner must clear when seeking back before the deck empties."""

    def setUp(self) -> None:
        self.root = tk.Tk()
        self.root.withdraw()
        self.display = GUIDisplay(self.root)
        self.display.set_suppress_dialogs(True)

    def tearDown(self) -> None:
        self.root.destroy()

    def _game_with_deck_cards(self, cards_to_draw: int) -> MagicMock:
        game = MagicMock()
        game.state.common_view.cards_to_draw = cards_to_draw
        return game

    def _banner_visible(self) -> bool:
        return "LAST TURN" in self.display._last_turn_label.cget("text")

    def test_banner_shows_when_deck_empty(self) -> None:
        """Banner text appears when the draw pile is empty."""
        self.display._game = self._game_with_deck_cards(0)
        self.display._update_last_turn_warning()
        self.assertTrue(self._banner_visible())
        self.assertEqual("#E74C3C", self.display._last_turn_label.cget("bg"))

    def test_banner_clears_when_deck_has_cards(self) -> None:
        """Banner text and red styling clear when seeking before deck empty."""
        self.display._game = self._game_with_deck_cards(0)
        self.display._update_last_turn_warning()
        self.assertTrue(self._banner_visible())

        self.display._game = self._game_with_deck_cards(5)
        self.display._update_last_turn_warning()
        self.assertFalse(self._banner_visible())
        self.assertEqual("", self.display._last_turn_label.cget("text"))
        self.assertEqual("#34495E", self.display._last_turn_label.cget("bg"))

    def test_banner_clears_when_game_cleared(self) -> None:
        """No game means the banner must not keep LAST TURN text."""
        self.display._game = self._game_with_deck_cards(0)
        self.display._update_last_turn_warning()
        self.display._game = None
        self.display._update_last_turn_warning()
        self.assertFalse(self._banner_visible())


if __name__ == "__main__":
    unittest.main()
