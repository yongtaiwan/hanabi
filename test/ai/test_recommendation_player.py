"""
Tests for RecommendationPlayer (Cox et al. strategy 1): 5 players, 4-card hands, standard suits only.
"""

import unittest
from unittest.mock import patch

from hanabi.ai import recommendation_player as rp_mod
from hanabi.ai.recommendation_player import Slot, RecommendationPlayer, _STANDARD_HINT_COLORS
from hanabi.core.card import Card
from hanabi.core.enums import CardKind, Color, Number
from hanabi.core.game import CommonView, GameSettings, Hand, PlayerView, create_standard_game_settings
from hanabi.core.moves import ColorHint, Discard, NumberHint, Play


def _five_player_settings() -> GameSettings:
    return create_standard_game_settings(5)


def _empty_common() -> CommonView:
    return CommonView(
        live_tokens=3,
        hint_tokens=8,
        cards_to_draw=40,
        cards_discarded={},
        cards_played={},
    )


class TestRecommendationPlayerSettings(unittest.TestCase):
    """Game settings support checks."""

    def test_supports_only_five_players_three_fuse(self) -> None:
        s5 = create_standard_game_settings(5)
        s3 = create_standard_game_settings(3)
        s5_four_fuse = GameSettings(
            num_players=s5.num_players,
            max_live_tokens=4,
            max_hint_tokens=s5.max_hint_tokens,
            max_cards_in_hand=s5.max_cards_in_hand,
            cards=s5.cards,
        )
        self.assertTrue(RecommendationPlayer.supports_game_settings(s5))
        self.assertFalse(RecommendationPlayer.supports_game_settings(s3))
        self.assertFalse(RecommendationPlayer.supports_game_settings(s5_four_fuse))


class TestStandardHintColors(unittest.TestCase):
    """MULTI is excluded from hint encoding (same five suits as standard settings)."""

    def test_multi_not_in_hint_colors(self) -> None:
        self.assertNotIn(Color.MULTI, _STANDARD_HINT_COLORS)
        self.assertEqual(5, len(_STANDARD_HINT_COLORS))

    def test_hint_colors_match_standard_deck_colors(self) -> None:
        settings = _five_player_settings()
        deck_colors = frozenset(settings.cards.keys())
        self.assertEqual(deck_colors, frozenset(_STANDARD_HINT_COLORS))


class TestSlotPaperLabels(unittest.TestCase):
    """Paper C1..C4: index 0 = C1 (left) through index 3 = C4 (right)."""

    def test_slot_enum_names(self) -> None:
        self.assertEqual("C1", Slot(0).name)
        self.assertEqual("C4", Slot(3).name)


class TestDiscardC1Move(unittest.TestCase):
    """Rule 5 default discard must target engine index 0 (oldest), not the draw slot (highest index)."""

    def test_discard_c1_returns_discard_zero(self) -> None:
        """``_discard_c1`` must emit ``Discard(0)`` — C1, not C4 (``Discard(3)``)."""
        settings = _five_player_settings()
        player = RecommendationPlayer(0)
        player.set_game_settings(settings)
        common = CommonView(
            live_tokens=3,
            hint_tokens=7,
            cards_to_draw=10,
            cards_discarded={},
            cards_played={},
        )
        player.set_common_view(common)
        view = PlayerView(
            teammates={
                1: Hand([Card(Color.RED, Number.ONE)] * 4),
                2: Hand([Card(Color.BLUE, Number.TWO)] * 4),
                3: Hand([Card(Color.GREEN, Number.THREE)] * 4),
                4: Hand([Card(Color.WHITE, Number.FOUR)] * 4),
            },
            own_hand_size=4,
        )
        move = player._discard_c1(view)
        self.assertIsInstance(move, Discard)
        self.assertEqual(0, move.card)


class TestFollowPlayRecommendation(unittest.TestCase):
    """Cox et al. action rules 1--2 for following a play recommendation."""

    def setUp(self) -> None:
        self.settings = _five_player_settings()
        self.player = RecommendationPlayer(0)
        self.player.set_game_settings(self.settings)
        self.player.set_common_view(
            CommonView(
                live_tokens=3,
                hint_tokens=7,
                cards_to_draw=10,
                cards_discarded={},
                cards_played={},
            )
        )
        self.view = PlayerView(
            teammates={
                1: Hand([Card(Color.RED, Number.ONE)] * 4),
                2: Hand([Card(Color.BLUE, Number.TWO)] * 4),
                3: Hand([Card(Color.GREEN, Number.THREE)] * 4),
                4: Hand([Card(Color.WHITE, Number.FOUR)] * 4),
            },
            own_hand_size=4,
        )

    def test_follow_play_when_no_play_since_hint(self) -> None:
        m = self.player._try_follow_play_recommendation(self.view, 0, plays_since_hint=0, errors=0)
        self.assertIsInstance(m, Play)
        self.assertEqual(0, m.card)

    def test_follow_play_other_slot_when_no_play_since_hint(self) -> None:
        m = self.player._try_follow_play_recommendation(self.view, 1, plays_since_hint=0, errors=0)
        self.assertIsInstance(m, Play)
        self.assertEqual(1, m.card)

    def test_follow_when_exactly_one_play_since_hint_and_under_two_errors(self) -> None:
        m = self.player._try_follow_play_recommendation(self.view, 0, plays_since_hint=1, errors=1)
        self.assertIsInstance(m, Play)
        self.assertEqual(0, m.card)

    def test_no_follow_when_two_or_more_plays_since_hint(self) -> None:
        self.assertIsNone(
            self.player._try_follow_play_recommendation(self.view, 0, plays_since_hint=2, errors=0)
        )

    def test_no_follow_when_one_play_since_hint_and_two_errors(self) -> None:
        self.assertIsNone(
            self.player._try_follow_play_recommendation(self.view, 0, plays_since_hint=1, errors=2)
        )

    def test_no_follow_when_recommendation_is_discard_code(self) -> None:
        self.assertIsNone(
            self.player._try_follow_play_recommendation(self.view, 4, plays_since_hint=0, errors=0)
        )


class TestGetRecommendationForHand(unittest.TestCase):
    """Paper priorities 1–5 via :meth:`RecommendationPlayer._get_recommendation_for_hand`."""

    def setUp(self) -> None:
        self.settings = _five_player_settings()
        self.common = _empty_common()
        self.player = RecommendationPlayer(0)
        self.player.set_game_settings(self.settings)
        self.player.set_common_view(self.common)

    def test_rank5_prefers_c1_slot_first(self) -> None:
        """Two playable fives: C1 (index 0) is checked before C4 (index 3)."""
        hand_cards = [
            Card(Color.RED, Number.FIVE),
            Card(Color.RED, Number.ONE),
            Card(Color.RED, Number.ONE),
            Card(Color.BLUE, Number.FIVE),
        ]

        def kind(card: Card, st: GameSettings) -> CardKind:
            if Number.FIVE == card.number:
                return CardKind.PLAYABLE
            return CardKind.DISPENSABLE

        with patch.object(self.common, "card_kind", new=kind):
            rec = self.player._get_recommendation_for_hand(hand_cards, self.common, self.settings)
        self.assertEqual(Slot.C1, rec)

    def test_discard_c1_when_no_prior_rule_applies(self) -> None:
        """If kinds never match rules 1–4, rule 5 returns discard C1 (code 4 in 4–7 discard range)."""

        def kind(card: Card, st: GameSettings) -> CardKind:
            return CardKind.CRITICAL

        hand_cards = [Card(Color.RED, Number.ONE)] * 4
        with patch.object(self.common, "card_kind", new=kind):
            rec = self.player._get_recommendation_for_hand(hand_cards, self.common, self.settings)
        self.assertEqual(len(Slot) + Slot.C1, rec)

    def test_three_cards_rule5_discards_c1(self) -> None:
        """Three cards: C1 still index 0; rule 5 is discard C1 (code 4)."""

        def kind(card: Card, st: GameSettings) -> CardKind:
            return CardKind.CRITICAL

        hand_cards = [Card(Color.RED, Number.ONE)] * 3
        with patch.object(self.common, "card_kind", new=kind):
            rec = self.player._get_recommendation_for_hand(hand_cards, self.common, self.settings)
        self.assertEqual(len(Slot) + Slot.C1, rec)


class TestSumPeerRecommendations(unittest.TestCase):
    """Encoding vs decoding sums over teammate hands."""

    def setUp(self) -> None:
        self.settings = _five_player_settings()
        self.common = _empty_common()
        self.player = RecommendationPlayer(0)
        self.player.set_game_settings(self.settings)
        self.player.set_common_view(self.common)
        dummy = [Card(Color.RED, Number.ONE)] * 4
        self.view = PlayerView(
            teammates={
                1: Hand(dummy),
                2: Hand(dummy),
                3: Hand(dummy),
                4: Hand(dummy),
            },
            own_hand_size=4,
        )

    def test_sum_includes_all_teammates_when_not_decoding(self) -> None:
        with patch.object(
            RecommendationPlayer,
            "_get_recommendation_for_hand",
            return_value=1,
        ):
            total, mod8, breakdown = self.player._sum_peer_recommendations(self.view)
        self.assertEqual(4, total)
        self.assertEqual(4, mod8)
        self.assertEqual("P2:1, P3:1, P4:1, P5:1", breakdown)

    def test_sum_excludes_hinter_when_decoding(self) -> None:
        with patch.object(
            RecommendationPlayer,
            "_get_recommendation_for_hand",
            return_value=2,
        ):
            total, mod8, breakdown = self.player._sum_peer_recommendations(self.view, exclude_index=1)
        self.assertEqual(6, total)
        self.assertEqual(6, mod8)
        self.assertEqual("P3:2, P4:2, P5:2", breakdown)


class TestDecodeRecommendation(unittest.TestCase):
    """Mod-8 decode matches encode-side sum convention."""

    def setUp(self) -> None:
        self.settings = _five_player_settings()
        self.common = _empty_common()
        self.player = RecommendationPlayer(2)
        self.player.set_game_settings(self.settings)
        self.player.set_common_view(self.common)
        dummy = [Card(Color.RED, Number.ONE)] * 4
        self.view = PlayerView(
            teammates={
                0: Hand(dummy),
                1: Hand(dummy),
                3: Hand(dummy),
                4: Hand(dummy),
            },
            own_hand_size=4,
        )

    def test_decode_subtracts_sum_excluding_hinter(self) -> None:
        hinter = 1
        with patch.object(
            RecommendationPlayer,
            "_get_recommendation_for_hand",
            return_value=3,
        ):
            out = self.player._decode_recommendation_with_view(self.view, hint_value=10, hinter=hinter)
        # three teammates (0,3,4) × 3 = 9; (10 - 9) % 8 == 1
        self.assertEqual(1, out)


class TestComputeHint(unittest.TestCase):
    """Rank vs color branch and standard colors only."""

    def setUp(self) -> None:
        self.settings = _five_player_settings()
        self.common = _empty_common()
        self.player = RecommendationPlayer(0)
        self.player.set_game_settings(self.settings)
        self.player.set_common_view(self.common)

    def test_color_hint_skips_multi_even_if_present(self) -> None:
        """Hand contains MULTI but also RED; color path must choose RED, never MULTI."""
        red_cards = [
            Card(Color.MULTI, Number.TWO),
            Card(Color.RED, Number.TWO),
            Card(Color.RED, Number.TWO),
            Card(Color.RED, Number.TWO),
        ]
        view = PlayerView(teammates={1: Hand(red_cards)}, own_hand_size=4)

        with patch.object(
            RecommendationPlayer,
            "_sum_peer_recommendations",
            return_value=(4, 4, "P2:1, P3:1, P4:1, P5:1"),
        ):
            move = self.player._compute_hint(view)

        self.assertIsInstance(move, ColorHint)
        self.assertEqual(Color.RED, move.color)
        self.assertNotEqual(Color.MULTI, move.color)

    def test_number_hint_when_value_mod8_lt_4(self) -> None:
        view = PlayerView(
            teammates={1: Hand([Card(Color.RED, Number.THREE)] * 4)},
            own_hand_size=4,
        )
        with patch.object(
            RecommendationPlayer,
            "_sum_peer_recommendations",
            return_value=(0, 0, "P2:0"),
        ):
            move = self.player._compute_hint(view)
        self.assertIsInstance(move, NumberHint)
        self.assertEqual(Number.THREE, move.number)


class TestRecommendationPlayerModule(unittest.TestCase):
    """Sanity check: module documents no MULTI."""

    def test_module_mentions_no_multi_support(self) -> None:
        doc = (rp_mod.__doc__ or "").lower()
        self.assertIn("multi", doc)


if __name__ == "__main__":
    unittest.main()
