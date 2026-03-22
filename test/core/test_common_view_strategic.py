"""Tests for CommonView.card_kind."""

import unittest

from hanabi.core.card import Card, Suit
from hanabi.core.enums import Color, Number, CardKind
from hanabi.core.game import CommonView, GameSettings, create_standard_game_settings


def _settings() -> GameSettings:
    return create_standard_game_settings(5)


def _discards(settings: GameSettings, red: dict | None = None) -> dict:
    """Build discard piles; ``red`` maps Number -> count discarded for red only."""
    red = red or {}
    out = {}
    for c, suit in settings.cards.items():
        d = {n: 0 for n in suit.cards}
        if c == Color.RED:
            for n, cnt in red.items():
                d[n] = cnt
        out[c] = Suit(d)
    return out


class TestCommonViewStrategic(unittest.TestCase):
    def test_unreachable_rank_is_useless_not_critical(self):
        """Both red 3s discarded, pile at 2: red 5 cannot be reached; not critical."""
        settings = _settings()
        disc = _discards(settings, red={Number.THREE: 2})
        common = CommonView(
            live_tokens=3,
            hint_tokens=8,
            cards_to_draw=40,
            cards_discarded=disc,
            cards_played={Color.RED: Number.TWO},
        )
        r5 = Card(Color.RED, Number.FIVE)
        self.assertTrue(common._color_rank_unreachable(Color.RED, Number.FIVE, settings))
        self.assertEqual(
            common.card_kind(r5, settings),
            CardKind.USELESS,
        )

    def test_playable_last_copy_of_three_is_playable_not_critical(self):
        """One red 3 discarded, pile at 2: next play is 3 — playable, not critical."""
        settings = _settings()
        disc = _discards(settings, red={Number.THREE: 1})
        common = CommonView(
            live_tokens=3,
            hint_tokens=8,
            cards_to_draw=40,
            cards_discarded=disc,
            cards_played={Color.RED: Number.TWO},
        )
        r3 = Card(Color.RED, Number.THREE)
        self.assertEqual(
            common.card_kind(r3, settings),
            CardKind.PLAYABLE,
        )

    def test_last_copy_not_yet_playable_is_critical(self):
        """Pile at 1, one red 3 remains (one 3 discarded): 3 not playable, critical."""
        settings = _settings()
        disc = _discards(settings, red={Number.THREE: 1})
        common = CommonView(
            live_tokens=3,
            hint_tokens=8,
            cards_to_draw=40,
            cards_discarded=disc,
            cards_played={Color.RED: Number.ONE},
        )
        r3 = Card(Color.RED, Number.THREE)
        self.assertEqual(
            common.card_kind(r3, settings),
            CardKind.CRITICAL,
        )

    def test_dispensable_when_two_copies_remain_off_pile(self):
        settings = _settings()
        disc = _discards(settings)
        common = CommonView(
            live_tokens=3,
            hint_tokens=8,
            cards_to_draw=40,
            cards_discarded=disc,
            cards_played={Color.RED: Number.ONE},
        )
        r3 = Card(Color.RED, Number.THREE)
        self.assertEqual(
            common.card_kind(r3, settings),
            CardKind.DISPENSABLE,
        )


if __name__ == "__main__":
    unittest.main()
