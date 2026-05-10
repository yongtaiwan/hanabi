"""Tests for :mod:`hanabi.ai.public_knowledge`."""

import unittest

from hanabi.ai.public_knowledge import PublicKnowledgeTracker
from hanabi.core.card import Card
from hanabi.core.enums import Color, Number
from hanabi.core.game import CommonView, create_standard_game_settings


class TestPublicKnowledgeTracker(unittest.TestCase):
    """Public possibility sets: fireworks pruning, color/number hints, hand shift."""

    def test_bootstrap_all_unknown_hands_non_empty(self) -> None:
        settings = create_standard_game_settings(3)
        common = CommonView(3, 8, 40, {}, {})
        none5 = [None] * 5
        tr = PublicKnowledgeTracker(settings, common)
        tr.bootstrap_from_masks([none5, none5, none5])
        for p in range(3):
            for s in tr.slot_possibilities(p):
                self.assertTrue(1 < len(s))

    def test_prune_yellow_five_after_played_to_fireworks(self) -> None:
        settings = create_standard_game_settings(3)
        common0 = CommonView(3, 8, 40, {}, {})
        y5 = Card(Color.YELLOW, Number.FIVE)
        none5 = [None] * 5
        tr = PublicKnowledgeTracker(settings, common0)
        tr.bootstrap_from_masks([none5, none5, none5])
        for p in range(3):
            for s in tr.slot_possibilities(p):
                self.assertIn(y5, s)
        common1 = CommonView(3, 8, 40, {}, {Color.YELLOW: Number.FIVE})
        tr.set_common_view(common1)
        for p in range(3):
            for s in tr.slot_possibilities(p):
                self.assertNotIn(y5, s)

    def test_color_hint_touched_and_untouched(self) -> None:
        settings = create_standard_game_settings(3)
        common = CommonView(3, 8, 40, {}, {})
        tr = PublicKnowledgeTracker(settings, common)
        tr.bootstrap_from_masks([[None, None], [None, None], [None, None]])
        tr.apply_color_hint(1, [0], Color.BLUE)
        row = tr.slot_possibilities(1)
        for c in row[0]:
            self.assertEqual(Color.BLUE, c.color)
        for c in row[1]:
            self.assertNotEqual(Color.BLUE, c.color)

    def test_number_hint_touched_and_untouched(self) -> None:
        settings = create_standard_game_settings(3)
        common = CommonView(3, 8, 40, {}, {})
        tr = PublicKnowledgeTracker(settings, common)
        tr.bootstrap_from_masks([[None, None], [None, None], [None, None]])
        tr.apply_number_hint(0, [1], Number.TWO)
        row = tr.slot_possibilities(0)
        for c in row[0]:
            self.assertNotEqual(Number.TWO, c.number)
        for c in row[1]:
            self.assertEqual(Number.TWO, c.number)

    def test_shift_after_remove_and_draw_unknown(self) -> None:
        settings = create_standard_game_settings(3)
        common0 = CommonView(3, 8, 40, {}, {})
        tr = PublicKnowledgeTracker(settings, common0)
        tr.bootstrap_from_masks([[None, None], [None, None], [None, None]])
        before = tr.slot_possibilities(0)
        common1 = CommonView(3, 8, 40, {}, {})
        tr.shift_after_remove_and_draw(0, 0, common1, drawn_card=None)
        after = tr.slot_possibilities(0)
        self.assertEqual(2, len(after))
        self.assertEqual(before[1], after[0])
        self.assertTrue(1 < len(after[1]))

    def test_replace_player_row(self) -> None:
        settings = create_standard_game_settings(3)
        common = CommonView(3, 8, 40, {}, {})
        tr = PublicKnowledgeTracker(settings, common)
        tr.bootstrap_from_masks([[None, None], [None, None], [None, None]])
        tr.replace_player_row(2, [Card(Color.RED, Number.ONE), None])
        row = tr.slot_possibilities(2)
        self.assertEqual({Card(Color.RED, Number.ONE)}, row[0])
        self.assertTrue(1 < len(row[1]))


if __name__ == "__main__":
    unittest.main()
