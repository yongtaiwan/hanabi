"""Tests for :class:`~hanabi.core.moves.HasWhy` and explained leaf move subclasses."""

import unittest

from hanabi.core.enums import Color, Number
from hanabi.core.moves import (
    ColorHint,
    ConcreteMove,
    ExplainedColorHint,
    ExplainedDiscard,
    ExplainedNumberHint,
    ExplainedPlay,
    HasWhy,
    Play,
    ensure_concrete_move,
)


class TestHasWhy(unittest.TestCase):
    """Explained moves are still concrete engine moves and implement :class:`HasWhy`."""

    def test_plain_play_is_not_has_why(self) -> None:
        self.assertNotIsInstance(Play(0), HasWhy)

    def test_explained_play_is_play_and_has_why(self) -> None:
        m = ExplainedPlay(0, why="because")
        self.assertIsInstance(m, Play)
        self.assertIsInstance(m, HasWhy)
        self.assertEqual("because", m.why())

    def test_ensure_concrete_move_accepts_explained(self) -> None:
        inner = ExplainedPlay(0, why="x")
        self.assertIs(inner, ensure_concrete_move(inner))

    def test_explained_hint_subclasses_color(self) -> None:
        h = ExplainedColorHint(1, [0], Color.RED, why="hint color")
        self.assertIsInstance(h, ColorHint)
        self.assertIsInstance(h, HasWhy)
        self.assertEqual("hint color", h.why())

    def test_concrete_move_alias_covers_leaf_types(self) -> None:
        # Type-checking alias: runtime isinstance still uses leaf classes (incl. subclasses).
        self.assertIsInstance(ExplainedDiscard(0, why="d"), ConcreteMove)


if __name__ == "__main__":
    unittest.main()
