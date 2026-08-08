"""Tests for :class:`~hanabi.core.moves.HasWhy` and explained leaf move subclasses."""

import unittest

from hanabi.core.card import Card
from hanabi.core.enums import Color, Number
from hanabi.core.moves import (
    ColorHint,
    ConcreteMove,
    Discard,
    ExplainedColorHint,
    ExplainedDiscard,
    ExplainedPlay,
    FinishedDiscard,
    FinishedPlay,
    HasWhy,
    Play,
    ensure_concrete_move,
    finished_card_move_for_observer,
    move_with_why,
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
        self.assertIsInstance(
            FinishedPlay(0, Card(Color.RED, Number.ONE), successful=True), ConcreteMove
        )

    def test_move_with_why_wraps_plain_play(self) -> None:
        m = move_with_why(Play(1), "reason")
        self.assertIsInstance(m, HasWhy)
        self.assertEqual("reason", m.why())
        self.assertIs(m, move_with_why(m, "ignored"))


class TestFinishedCardMoves(unittest.TestCase):
    def test_finished_play_carries_outcome(self) -> None:
        card = Card(Color.BLUE, Number.TWO)
        finished = finished_card_move_for_observer(Play(3), card, successful=True)
        assert isinstance(finished, FinishedPlay)
        self.assertEqual(3, finished.card)
        self.assertEqual(card, finished.moved_card)
        self.assertTrue(finished.successful)
        self.assertIsInstance(finished, Play)

    def test_finished_discard_carries_moved_card(self) -> None:
        card = Card(Color.GREEN, Number.FOUR)
        finished = finished_card_move_for_observer(Discard(1), card)
        assert isinstance(finished, FinishedDiscard)
        self.assertEqual(1, finished.card)
        self.assertEqual(card, finished.moved_card)
        self.assertIsInstance(finished, Discard)

    def test_move_with_why_rejects_finished(self) -> None:
        finished = FinishedPlay(0, Card(Color.RED, Number.ONE), successful=False)
        with self.assertRaises(AssertionError):
            move_with_why(finished, "nope")


if __name__ == "__main__":
    unittest.main()
