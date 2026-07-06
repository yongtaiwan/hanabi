"""Tests for :mod:`hanabi.ai.hint_hand_subtype_3p`."""

from __future__ import annotations

import unittest
from typing import List, Optional

from hanabi.ai import hint_hand_subtype_3p as h3p
from hanabi.ai.hint_hand_subtype_3p import HintHandSubtype3P, HintSlotShape
from hanabi.core.card import Card, Suit
from hanabi.core.enums import CardKind, Color, Number
from hanabi.core.game import CommonView, Hand, PlayerView, create_standard_game_settings
from hanabi.core.moves import ColorHint, Discard, NumberHint, Play


def _common(settings=None) -> CommonView:
    settings = settings or create_standard_game_settings(3)
    return CommonView(
        live_tokens=settings.max_live_tokens,
        hint_tokens=settings.max_hint_tokens,
        cards_to_draw=40,
        cards_discarded={},
        cards_played={},
    )


def _playable_slot_from_hand_type(hand_type: int, hand_size: int) -> Optional[int]:
    """Nth-from-new playable slot for decoded types ``1``–``5`` (mirrors step ``5`` decode)."""
    if not 1 <= hand_type <= 5:
        return None
    play_slot = h3p._new_slot(hand_size) - (hand_type - 1)
    if 0 <= play_slot < hand_size:
        return play_slot
    return None


class TestHintHandSubtype3PSettings(unittest.TestCase):
    def test_supports_only_three_players(self) -> None:
        s3 = create_standard_game_settings(3)
        s5 = create_standard_game_settings(5)
        self.assertTrue(HintHandSubtype3P.supports_game_settings(s3))
        self.assertFalse(HintHandSubtype3P.supports_game_settings(s5))


class TestHintSlotShape(unittest.TestCase):
    def test_old_mid_new_five_card_hand(self) -> None:
        self.assertEqual(HintSlotShape.OLD, h3p._hint_slot_shape([0, 2], 5))
        self.assertEqual(HintSlotShape.MID, h3p._hint_slot_shape([2, 3], 5))
        self.assertEqual(HintSlotShape.NEW, h3p._hint_slot_shape([4], 5))
        self.assertEqual(4, h3p._new_slot(5))


class TestInferEncodedType(unittest.TestCase):
    def test_old_number_to_next_type_only(self) -> None:
        move = NumberHint(teammate=1, cards=[0], number=Number.ONE)
        self.assertEqual(0, h3p._infer_encoded_type_from_hint(0, 1, move, 3))
        move_mid = NumberHint(teammate=1, cards=[1], number=Number.TWO)
        self.assertEqual(0, h3p._infer_encoded_type_from_hint(0, 1, move_mid, 3))

    def test_new_number_to_next(self) -> None:
        move = NumberHint(teammate=1, cards=[2], number=Number.THREE)
        self.assertEqual(4, h3p._infer_encoded_type_from_hint(0, 1, move, 3))

    def test_mid_suit_to_prev(self) -> None:
        move = ColorHint(teammate=2, cards=[1, 2], color=Color.BLUE)
        self.assertEqual(3, h3p._infer_encoded_type_from_hint(0, 2, move, 5))

    def test_public_inference_when_hand_hidden(self) -> None:
        move = NumberHint(teammate=1, cards=[0], number=Number.ONE)
        self.assertEqual(0, h3p._infer_encoded_type_from_hint(0, 1, move, 5))


def _unknown_belief(hand_size: int) -> List[Optional[CardKind]]:
    return [None for _ in range(hand_size)]


class TestEncodeHandType(unittest.TestCase):
    def test_newest_playable_is_third_from_new(self) -> None:
        settings = create_standard_game_settings(3)
        common = _common(settings)
        hand = [
            Card(Color.BLUE, Number.TWO),
            Card(Color.YELLOW, Number.THREE),
            Card(Color.RED, Number.ONE),
            Card(Color.GREEN, Number.FOUR),
            Card(Color.WHITE, Number.FIVE),
        ]
        self.assertEqual(3, h3p._encode_hand_type(hand, 5, common, settings, _unknown_belief(5)))

    def test_no_playable_chop_safe(self) -> None:
        settings = create_standard_game_settings(3)
        common = CommonView(
            live_tokens=3,
            hint_tokens=8,
            cards_to_draw=40,
            cards_discarded={},
            cards_played={Color.RED: Number.ONE},
        )
        hand = [
            Card(Color.BLUE, Number.THREE),
            Card(Color.YELLOW, Number.FOUR),
            Card(Color.GREEN, Number.TWO),
            Card(Color.WHITE, Number.FIVE),
            Card(Color.RED, Number.FOUR),
        ]
        self.assertEqual(0, h3p._encode_hand_type(hand, 5, common, settings, _unknown_belief(5)))

    def test_excludes_identified_playable_from_hand_type(self) -> None:
        """Identified playable slots are omitted when picking newest playable (type 1–5)."""
        settings = create_standard_game_settings(3)
        common = _common(settings)
        hand = [
            Card(Color.YELLOW, Number.ONE),
            Card(Color.BLUE, Number.ONE),
            Card(Color.GREEN, Number.TWO),
            Card(Color.BLUE, Number.THREE),
            Card(Color.RED, Number.ONE),
        ]
        self.assertEqual(1, h3p._encode_hand_type(hand, 5, common, settings, _unknown_belief(5)))
        self.assertEqual(
            4,
            h3p._encode_hand_type(
                hand,
                5,
                common,
                settings,
                [None, None, None, None, CardKind.PLAYABLE],
            ),
        )
        self.assertEqual(
            0,
            h3p._encode_hand_type(
                hand,
                5,
                common,
                settings,
                [CardKind.PLAYABLE, CardKind.PLAYABLE, None, None, CardKind.PLAYABLE],
            ),
        )

    def test_stale_critical_uses_physical_playable_for_encoding(self) -> None:
        """Pile advance: belief CRITICAL but card physically PLAYABLE counts for hand type."""
        settings = create_standard_game_settings(3)
        common = CommonView(
            live_tokens=3,
            hint_tokens=8,
            cards_to_draw=40,
            cards_discarded={Color.BLUE: Suit({Number.ONE: 1})},
            cards_played={Color.GREEN: Number.FOUR, Color.BLUE: Number.TWO},
        )
        hand = [
            Card(Color.GREEN, Number.FIVE),
            Card(Color.BLUE, Number.FOUR),
            Card(Color.YELLOW, Number.THREE),
            Card(Color.WHITE, Number.FOUR),
            Card(Color.RED, Number.THREE),
        ]
        stale_critical = [CardKind.CRITICAL, None, None, None, None]
        self.assertEqual(5, h3p._encode_hand_type(hand, 5, common, settings, stale_critical))
    def test_chop_safe_is_type_zero(self) -> None:
        kinds = [CardKind.DISPENSABLE, CardKind.USELESS, CardKind.CRITICAL]
        self.assertEqual(0, h3p._hand_type_when_no_playable(kinds, _unknown_belief(3)))

    def test_chop_critical_is_type_six(self) -> None:
        kinds = [CardKind.CRITICAL, CardKind.DISPENSABLE]
        self.assertEqual(6, h3p._hand_type_when_no_playable(kinds, _unknown_belief(2)))

    def test_chop_useless_is_type_seven(self) -> None:
        kinds = [CardKind.USELESS, CardKind.CRITICAL]
        self.assertEqual(7, h3p._hand_type_when_no_playable(kinds, _unknown_belief(2)))

    def test_no_playable_type_six_when_chop_critical_not_first_useless(self) -> None:
        """Encode types 0/6/7 from chop, not first left-to-right useless/critical."""
        kinds = [
            CardKind.USELESS,
            CardKind.CRITICAL,
            CardKind.USELESS,
            CardKind.DISPENSABLE,
            CardKind.DISPENSABLE,
        ]
        belief: List[Optional[CardKind]] = [CardKind.USELESS, None, None, None, None]
        self.assertEqual(6, h3p._hand_type_when_no_playable(kinds, belief))


class TestBuildShapeHint(unittest.TestCase):
    def test_old_unavailable_when_rank_spans_new(self) -> None:
        hand = [
            Card(Color.RED, Number.TWO),
            Card(Color.YELLOW, Number.THREE),
            Card(Color.BLUE, Number.FOUR),
            Card(Color.GREEN, Number.ONE),
            Card(Color.WHITE, Number.TWO),
        ]
        self.assertIsNone(h3p._build_shape_hint(1, hand, HintSlotShape.OLD, True))

    def test_new_number_always_buildable(self) -> None:
        hand = [Card(Color.RED, Number.ONE), Card(Color.BLUE, Number.TWO)]
        hint = h3p._build_shape_hint(1, hand, HintSlotShape.NEW, True)
        self.assertIsInstance(hint, NumberHint)
        self.assertIn(1, hint.cards)


class TestPickOldMidShape(unittest.TestCase):
    def test_builds_mid_when_only_mid_possible(self) -> None:
        hand = [
            Card(Color.RED, Number.TWO),
            Card(Color.YELLOW, Number.THREE),
            Card(Color.BLUE, Number.FOUR),
            Card(Color.GREEN, Number.ONE),
            Card(Color.WHITE, Number.TWO),
        ]
        self.assertFalse(h3p._old_mid_buildable(hand, 0)[0])
        self.assertTrue(h3p._old_mid_buildable(hand, 0)[1])

    def test_build_hint_when_only_mid_possible(self) -> None:
        view = PlayerView(
            teammates={
                1: Hand(
                    [
                        Card(Color.RED, Number.TWO),
                        Card(Color.YELLOW, Number.THREE),
                        Card(Color.BLUE, Number.FOUR),
                        Card(Color.GREEN, Number.ONE),
                        Card(Color.WHITE, Number.TWO),
                    ]
                ),
            },
            own_hand_size=5,
        )
        hint = h3p._build_hint_for_encoded(0, view, enc_type=0)
        self.assertIsInstance(hint, NumberHint)

    def test_no_color_fallback_for_number_channel(self) -> None:
        """Type 0 requires a number hint; do not fall back to color (would infer as type 2)."""
        view = PlayerView(
            teammates={
                1: Hand(
                    [
                        Card(Color.RED, Number.TWO),
                        Card(Color.BLUE, Number.TWO),
                        Card(Color.GREEN, Number.TWO),
                        Card(Color.WHITE, Number.TWO),
                        Card(Color.RED, Number.TWO),
                    ]
                ),
            },
            own_hand_size=5,
        )
        self.assertIsNone(h3p._build_hint_for_encoded(0, view, enc_type=0))


class TestBeliefDecode(unittest.TestCase):
    def test_type_marks_playable_not_chop(self) -> None:
        matrix = [[None] * 5]
        h3p._apply_decoded_hand_type(matrix, 0, 3)
        self.assertEqual(CardKind.PLAYABLE, matrix[0][2])
        self.assertIsNone(matrix[0][0])

    def test_type_zero_marks_chop_safe(self) -> None:
        matrix = [[None, None, None]]
        h3p._apply_decoded_hand_type(matrix, 0, 0)
        self.assertEqual(CardKind.DISPENSABLE, matrix[0][0])

    def test_type_six_marks_chop_critical(self) -> None:
        matrix = [[None, CardKind.CRITICAL, None]]
        h3p._apply_decoded_hand_type(matrix, 0, 6)
        self.assertEqual(CardKind.CRITICAL, matrix[0][0])

    def test_type_seven_marks_chop_useless(self) -> None:
        matrix = [[None, None, None]]
        h3p._apply_decoded_hand_type(matrix, 0, 7)
        self.assertEqual(CardKind.USELESS, matrix[0][0])

    def test_type_three_marks_third_from_new_playable(self) -> None:
        matrix = [[None, None, None, None, None]]
        h3p._apply_decoded_hand_type(matrix, 0, 3)
        self.assertEqual(CardKind.PLAYABLE, matrix[0][2])

    def test_transition_playable_allows_duplicate_collapse_to_useless(self) -> None:
        self.assertTrue(h3p._transition_allowed(CardKind.PLAYABLE, CardKind.USELESS))
        self.assertFalse(h3p._transition_allowed(CardKind.USELESS, CardKind.PLAYABLE))
        self.assertFalse(h3p._transition_allowed(CardKind.PLAYABLE, CardKind.DISPENSABLE))
        self.assertFalse(h3p._transition_allowed(CardKind.USELESS, CardKind.DISPENSABLE))
        self.assertTrue(h3p._transition_allowed(CardKind.CRITICAL, CardKind.PLAYABLE))
        self.assertFalse(h3p._transition_allowed(CardKind.CRITICAL, CardKind.DISPENSABLE))

    def test_decode_asserts_on_conflicting_transition(self) -> None:
        """Decode must not silently skip; disallowed kind transitions are convention bugs."""
        matrix: List[List[Optional[CardKind]]] = [[None, None, None, None, CardKind.USELESS]]
        with self.assertRaises(AssertionError):
            h3p._apply_decoded_hand_type(matrix, 0, 1)


class TestDuplicateIdentifiedPlayableCollapse(unittest.TestCase):
    def test_later_duplicate_playable_becomes_useless(self) -> None:
        """Leftmost ``PLAYABLE`` per card identity wins; right duplicate is ``USELESS``."""
        cards = [
            Card(Color.RED, Number.ONE),
            Card(Color.BLUE, Number.TWO),
            Card(Color.RED, Number.ONE),
            Card(Color.GREEN, Number.THREE),
            Card(Color.WHITE, Number.FOUR),
        ]
        matrix: List[List[Optional[CardKind]]] = [
            [CardKind.PLAYABLE, None, CardKind.PLAYABLE, None, None],
        ]
        h3p._collapse_duplicate_identified_playables_in_row(cards, matrix, 0)
        self.assertEqual(CardKind.PLAYABLE, matrix[0][0])
        self.assertEqual(CardKind.USELESS, matrix[0][2])

    def test_different_playable_cards_unchanged(self) -> None:
        cards = [
            Card(Color.RED, Number.ONE),
            Card(Color.BLUE, Number.ONE),
            Card(Color.GREEN, Number.ONE),
        ]
        matrix: List[List[Optional[CardKind]]] = [
            [CardKind.PLAYABLE, CardKind.PLAYABLE, CardKind.PLAYABLE],
        ]
        h3p._collapse_duplicate_identified_playables_in_row(cards, matrix, 0)
        self.assertEqual([CardKind.PLAYABLE, CardKind.PLAYABLE, CardKind.PLAYABLE], matrix[0])

    def test_duplicate_useless_belief_not_reencoded_as_playable(self) -> None:
        """Belief ``USELESS`` (duplicate collapse) must not resurrect as play type ``1``–``5``."""
        settings = create_standard_game_settings(3)
        common = _common(settings)
        hand = [
            Card(Color.RED, Number.ONE),
            Card(Color.BLUE, Number.TWO),
            Card(Color.GREEN, Number.THREE),
            Card(Color.WHITE, Number.FOUR),
            Card(Color.RED, Number.ONE),
        ]
        belief: List[Optional[CardKind]] = [
            CardKind.PLAYABLE,
            None,
            None,
            None,
            CardKind.USELESS,
        ]
        self.assertEqual(0, h3p._encode_hand_type(hand, 5, common, settings, belief))

    def test_align_after_hint_collapses_duplicate_playables(self) -> None:
        """Hinter canonical row is collapsed and copied to every seat after a hint."""
        settings = create_standard_game_settings(3)
        players = [HintHandSubtype3P(i) for i in range(3)]
        for player in players:
            player.set_game_settings(settings)
        duplicate_playable = [CardKind.PLAYABLE, None, CardKind.PLAYABLE, None, None]
        for player in players:
            player._inferred_card_kind[1] = duplicate_playable.copy()
        hand_cards = [
            [Card(Color.WHITE, Number.FOUR)] * 5,
            [
                Card(Color.RED, Number.ONE),
                Card(Color.BLUE, Number.TWO),
                Card(Color.RED, Number.ONE),
                Card(Color.GREEN, Number.THREE),
                Card(Color.YELLOW, Number.FOUR),
            ],
            [Card(Color.WHITE, Number.FIVE)] * 5,
        ]
        hint = ColorHint(1, [0], Color.WHITE)
        h3p.align_convention_beliefs_after_move(players, 0, hint, hand_cards=hand_cards)
        expected = [CardKind.PLAYABLE, None, CardKind.USELESS, None, None]
        for player in players:
            self.assertEqual(expected, player._inferred_card_kind[1])


class TestChopFromBelief(unittest.TestCase):
    def test_leftmost_unknown_or_safe(self) -> None:
        slots = [CardKind.USELESS, None, CardKind.DISPENSABLE]
        self.assertEqual(1, h3p._chop_slot_from_belief(slots))

    def test_critical_is_never_chop(self) -> None:
        slots = [CardKind.CRITICAL, None, CardKind.DISPENSABLE]
        self.assertEqual(1, h3p._chop_slot_from_belief(slots))

    def test_no_chop_when_all_critical(self) -> None:
        slots = [CardKind.CRITICAL, CardKind.CRITICAL, CardKind.CRITICAL]
        self.assertIsNone(h3p._chop_slot_from_belief(slots))


class TestPlayableSlotFromHandType(unittest.TestCase):
    def test_type_three_is_third_from_new(self) -> None:
        self.assertEqual(2, _playable_slot_from_hand_type(3, 5))

    def test_non_playable_types_return_none(self) -> None:
        self.assertIsNone(_playable_slot_from_hand_type(0, 5))
        self.assertIsNone(_playable_slot_from_hand_type(6, 5))


class TestStep5IdentifiesNewPlayable(unittest.TestCase):
    def test_true_when_decode_would_newly_mark_playable(self) -> None:
        """P1 has W1 playable; P3 hint encodes type 1 so P1 observer gets slot 4 playable."""
        settings = create_standard_game_settings(3)
        common = _common(settings)
        view = PlayerView(
            teammates={
                0: Hand(
                    [
                        Card(Color.BLUE, Number.FOUR),
                        Card(Color.GREEN, Number.TWO),
                        Card(Color.YELLOW, Number.THREE),
                        Card(Color.WHITE, Number.FIVE),
                        Card(Color.WHITE, Number.ONE),
                    ]
                ),
                1: Hand(
                    [
                        Card(Color.BLUE, Number.TWO),
                        Card(Color.GREEN, Number.FOUR),
                        Card(Color.YELLOW, Number.FIVE),
                        Card(Color.RED, Number.THREE),
                        Card(Color.WHITE, Number.FOUR),
                    ]
                ),
            },
            own_hand_size=5,
        )
        beliefs: List[List[Optional[CardKind]]] = [[None] * 5 for _ in range(3)]
        self.assertTrue(
            h3p._convention_hint_would_identify_new_playable(2, view, common, settings, beliefs)
        )

    def test_false_when_playable_already_identified(self) -> None:
        settings = create_standard_game_settings(3)
        common = _common(settings)
        view = PlayerView(
            teammates={
                0: Hand(
                    [
                        Card(Color.BLUE, Number.FOUR),
                        Card(Color.GREEN, Number.TWO),
                        Card(Color.YELLOW, Number.THREE),
                        Card(Color.WHITE, Number.FIVE),
                        Card(Color.WHITE, Number.ONE),
                    ]
                ),
                1: Hand([Card(Color.RED, Number.THREE)] * 5),
            },
            own_hand_size=5,
        )
        beliefs: list[list[CardKind | None]] = [
            [None, None, None, None, CardKind.PLAYABLE],
            [None, None, None, None, None],
            [None, None, None, None, None],
        ]
        self.assertFalse(
            h3p._convention_hint_would_identify_new_playable(2, view, common, settings, beliefs)
        )

    def test_step5_prefers_hint_over_discard(self) -> None:
        settings = create_standard_game_settings(3)
        common = CommonView(
            live_tokens=3,
            hint_tokens=8,
            cards_to_draw=40,
            cards_discarded={},
            cards_played={Color.GREEN: Number.ONE},
        )
        player = HintHandSubtype3P(2)
        player.set_game_settings(settings)
        player.set_common_view(common)
        view = PlayerView(
            teammates={
                0: Hand(
                    [
                        Card(Color.BLUE, Number.FOUR),
                        Card(Color.GREEN, Number.TWO),
                        Card(Color.YELLOW, Number.THREE),
                        Card(Color.WHITE, Number.FIVE),
                        Card(Color.WHITE, Number.ONE),
                    ]
                ),
                1: Hand(
                    [
                        Card(Color.BLUE, Number.TWO),
                        Card(Color.GREEN, Number.FOUR),
                        Card(Color.YELLOW, Number.FIVE),
                        Card(Color.RED, Number.THREE),
                        Card(Color.WHITE, Number.FOUR),
                    ]
                ),
            },
            own_hand_size=5,
        )
        move = player.play(view)
        self.assertIsInstance(move, NumberHint)


class TestBeliefLifecycle(unittest.TestCase):
    def test_initialized_at_deal(self) -> None:
        settings = create_standard_game_settings(3)
        player = HintHandSubtype3P(1)
        player.set_game_settings(settings)
        for seat in range(3):
            self.assertEqual(5, len(player._inferred_card_kind[seat]))
            self.assertTrue(all(kind is None for kind in player._inferred_card_kind[seat]))

    def test_drawn_slot_unknown_after_play(self) -> None:
        settings = create_standard_game_settings(3)
        player = HintHandSubtype3P(0)
        player.set_game_settings(settings)
        player.set_common_view(_common(settings))
        player._inferred_card_kind[0] = [None, CardKind.CRITICAL, CardKind.PLAYABLE, None, CardKind.USELESS]
        view = PlayerView(
            teammates={
                1: Hand([Card(Color.RED, Number.TWO)] * 5),
                2: Hand([Card(Color.BLUE, Number.THREE)] * 5),
            },
            own_hand_size=5,
        )
        player.observe_play_move(0, Play(2), view)
        self.assertEqual(
            [None, CardKind.CRITICAL, None, CardKind.USELESS, None],
            player._inferred_card_kind[0],
        )

    def test_shrink_hand_when_no_draw(self) -> None:
        settings = create_standard_game_settings(3)
        player = HintHandSubtype3P(0)
        player.set_game_settings(settings)
        common = _common(settings)
        player.set_common_view(common)
        player._inferred_card_kind[0] = [None, None, None, CardKind.PLAYABLE, None]
        player._common_view = CommonView(
            live_tokens=common.live_tokens,
            hint_tokens=common.hint_tokens,
            cards_to_draw=common.cards_to_draw,
            cards_discarded={Color.RED: Suit({Number.TWO: 1})},
            cards_played=common.cards_played,
        )
        view = PlayerView(
            teammates={
                1: Hand([Card(Color.RED, Number.TWO)] * 5),
                2: Hand([Card(Color.BLUE, Number.THREE)] * 5),
            },
            own_hand_size=4,
        )
        player.observe_discard_move(0, Discard(1), view)
        self.assertEqual([None, None, CardKind.PLAYABLE, None], player._inferred_card_kind[0])

    def test_safe_cleared_on_non_useless_middle_rank_discard(self) -> None:
        settings = create_standard_game_settings(3)
        player = HintHandSubtype3P(0)
        player.set_game_settings(settings)
        common = _common(settings)
        player.set_common_view(common)
        player._inferred_card_kind = [
            [None, CardKind.DISPENSABLE, None, CardKind.CRITICAL, None],
            [CardKind.DISPENSABLE, None, None, None, None],
            [None, None, CardKind.DISPENSABLE, None, None],
        ]
        player._common_view = CommonView(
            live_tokens=common.live_tokens,
            hint_tokens=common.hint_tokens,
            cards_to_draw=common.cards_to_draw,
            cards_discarded={Color.RED: Suit({Number.TWO: 1})},
            cards_played=common.cards_played,
        )
        view = PlayerView(
            teammates={
                1: Hand([Card(Color.GREEN, Number.FOUR)] * 5),
                2: Hand([Card(Color.BLUE, Number.THREE)] * 5),
            },
            own_hand_size=5,
        )
        player.observe_discard_move(1, Discard(2), view)
        self.assertEqual(
            [None, None, None, CardKind.CRITICAL, None],
            player._inferred_card_kind[0],
        )
        self.assertEqual([None, None, None, None, None], player._inferred_card_kind[1])
        self.assertEqual([None, None, None, None, None], player._inferred_card_kind[2])

    def test_safe_unchanged_on_useless_middle_rank_discard(self) -> None:
        settings = create_standard_game_settings(3)
        player = HintHandSubtype3P(0)
        player.set_game_settings(settings)
        common = _common(settings)
        player.set_common_view(common)
        player._inferred_card_kind[1] = [None, CardKind.DISPENSABLE, None, None, None]
        player._discard_pile_snapshot = {Color.RED: {Number.THREE: 1}}
        player._common_view = CommonView(
            live_tokens=common.live_tokens,
            hint_tokens=common.hint_tokens,
            cards_to_draw=common.cards_to_draw,
            cards_discarded={Color.RED: Suit({Number.THREE: 2})},
            cards_played={Color.RED: Number.THREE},
        )
        view = PlayerView(
            teammates={
                1: Hand([Card(Color.GREEN, Number.FOUR)] * 5),
                2: Hand([Card(Color.BLUE, Number.TWO)] * 5),
            },
            own_hand_size=5,
        )
        player.observe_discard_move(1, Discard(0), view)
        self.assertEqual([CardKind.DISPENSABLE, None, None, None, None], player._inferred_card_kind[1])

    def test_safe_unchanged_on_rank_one_discard(self) -> None:
        settings = create_standard_game_settings(3)
        player = HintHandSubtype3P(0)
        player.set_game_settings(settings)
        common = _common(settings)
        player.set_common_view(common)
        player._inferred_card_kind[0] = [None, CardKind.DISPENSABLE, None, None, None]
        player._common_view = CommonView(
            live_tokens=common.live_tokens,
            hint_tokens=common.hint_tokens,
            cards_to_draw=common.cards_to_draw,
            cards_discarded={Color.WHITE: Suit({Number.ONE: 1})},
            cards_played=common.cards_played,
        )
        view = PlayerView(
            teammates={
                1: Hand([Card(Color.RED, Number.TWO)] * 5),
                2: Hand([Card(Color.BLUE, Number.THREE)] * 5),
            },
            own_hand_size=4,
        )
        player.observe_discard_move(0, Discard(0), view)
        self.assertEqual([CardKind.DISPENSABLE, None, None, None], player._inferred_card_kind[0])

    def test_safe_cleared_on_middle_rank_misplay(self) -> None:
        settings = create_standard_game_settings(3)
        player = HintHandSubtype3P(0)
        player.set_game_settings(settings)
        common = _common(settings)
        player.set_common_view(common)
        player._inferred_card_kind = [
            [None, CardKind.DISPENSABLE, None, None, None],
            [CardKind.DISPENSABLE, None, None, None, None],
            [None, None, None, None, None],
        ]
        player._common_view = CommonView(
            live_tokens=common.live_tokens - 1,
            hint_tokens=common.hint_tokens,
            cards_to_draw=common.cards_to_draw,
            cards_discarded={Color.RED: Suit({Number.TWO: 1})},
            cards_played=common.cards_played,
        )
        view = PlayerView(
            teammates={
                1: Hand([Card(Color.GREEN, Number.FOUR)] * 5),
                2: Hand([Card(Color.BLUE, Number.THREE)] * 5),
            },
            own_hand_size=5,
        )
        player.observe_play_move(1, Play(0), view)
        self.assertEqual([None, None, None, None, None], player._inferred_card_kind[0])
        self.assertEqual([None, None, None, None, None], player._inferred_card_kind[1])


class TestPlaySmoke(unittest.TestCase):
    def test_play_returns_legal_move(self) -> None:
        settings = create_standard_game_settings(3)
        common = _common(settings)
        common = CommonView(
            live_tokens=common.live_tokens,
            hint_tokens=7,
            cards_to_draw=common.cards_to_draw,
            cards_discarded=common.cards_discarded,
            cards_played=common.cards_played,
        )
        view = PlayerView(
            teammates={
                1: Hand([Card(Color.RED, Number.ONE)] * 5),
                2: Hand([Card(Color.BLUE, Number.TWO)] * 5),
            },
            own_hand_size=5,
        )
        player = HintHandSubtype3P(0)
        player.set_game_settings(settings)
        player.set_common_view(common)
        move = player.play(view)
        self.assertTrue(player.is_move_legal(view, move))

    def test_plays_identified_playable_first(self) -> None:
        settings = create_standard_game_settings(3)
        player = HintHandSubtype3P(0)
        player.set_game_settings(settings)
        player.set_common_view(_common(settings))
        player._inferred_card_kind[0] = [None, CardKind.PLAYABLE, None, None, None]
        view = PlayerView(
            teammates={
                1: Hand([Card(Color.RED, Number.TWO)] * 5),
                2: Hand([Card(Color.BLUE, Number.THREE)] * 5),
            },
            own_hand_size=3,
        )
        move = player.play(view)
        self.assertIsInstance(move, Play)
        self.assertEqual(1, move.card)


class TestBeliefSyncAfterHint(unittest.TestCase):
    def test_all_seats_share_belief_after_hint(self) -> None:
        settings = create_standard_game_settings(3)
        common = _common(settings)
        players = [HintHandSubtype3P(i) for i in range(3)]
        for player in players:
            player.set_game_settings(settings)
            player.set_common_view(common)

        hand_p1 = [Card(Color.GREEN, Number.TWO)] * 4 + [Card(Color.RED, Number.ONE)]
        hand_p2 = [Card(Color.BLUE, Number.THREE)] * 5
        views = [
            PlayerView(teammates={1: Hand(hand_p1), 2: Hand(hand_p2)}, own_hand_size=5),
            PlayerView(
                teammates={0: Hand([Card(Color.WHITE, Number.FOUR)] * 5), 2: Hand(hand_p2)},
                own_hand_size=5,
            ),
            PlayerView(
                teammates={0: Hand([Card(Color.WHITE, Number.FOUR)] * 5), 1: Hand(hand_p1)},
                own_hand_size=5,
            ),
        ]
        hint = NumberHint(teammate=1, cards=[4], number=Number.ONE)
        for player, view in zip(players, views):
            player.observe_number_hint_move(0, hint, view)
        h3p.align_convention_beliefs_after_move(players, 0, hint)
        self.assertEqual(players[0]._inferred_card_kind, players[1]._inferred_card_kind)
        self.assertTrue(any(kind is not None for kind in players[0]._inferred_card_kind[1]))

    def test_hinter_updates_both_non_hinter_rows(self) -> None:
        settings = create_standard_game_settings(3)
        common = _common(settings)
        hinter = HintHandSubtype3P(0)
        hinter.set_game_settings(settings)
        hinter.set_common_view(common)
        hand_p1 = [Card(Color.GREEN, Number.TWO)] * 4 + [Card(Color.RED, Number.ONE)]
        hand_p2 = [Card(Color.BLUE, Number.THREE)] * 5
        view = PlayerView(teammates={1: Hand(hand_p1), 2: Hand(hand_p2)}, own_hand_size=5)
        hint = NumberHint(teammate=1, cards=[4], number=Number.ONE)
        hinter.observe_number_hint_move(0, hint, view)
        self.assertTrue(
            any(kind is not None for kind in hinter._inferred_card_kind[1]),
            "hinter should update hint target row from channel decode",
        )
        self.assertTrue(
            any(kind is not None for kind in hinter._inferred_card_kind[2]),
            "hinter should update other non-hinter row from channel decode",
        )

    def test_hinter_second_decode_uses_pre_decode_peer_type(self) -> None:
        """Hinter must snapshot peer types before applying both non-hinter decodes."""
        settings = create_standard_game_settings(3)
        common = _common(settings)
        hand_p1 = [Card(Color.GREEN, Number.TWO)] * 4 + [Card(Color.RED, Number.ONE)]
        hand_p2 = [Card(Color.BLUE, Number.THREE)] * 5
        beliefs_before = [[None for _ in range(5)] for _ in range(3)]
        view = PlayerView(teammates={1: Hand(hand_p1), 2: Hand(hand_p2)}, own_hand_size=5)
        hint = NumberHint(teammate=1, cards=[4], number=Number.ONE)

        encoded_type = h3p._infer_encoded_type_from_hint(0, 1, hint, 5)
        peer_p1_before = h3p._encode_hand_type(hand_p1, 5, common, settings, beliefs_before[1])
        peer_p2 = h3p._encode_hand_type(hand_p2, 5, common, settings, beliefs_before[2])
        decoded_p2 = (encoded_type - peer_p1_before) % 8

        expected = [[None for _ in range(5)] for _ in range(3)]
        expected[2] = beliefs_before[2][:]
        h3p._apply_decoded_hand_type(expected, 2, decoded_p2)
        self.assertTrue(any(kind is not None for kind in expected[2]), "expected decode should assign on P2")

        hinter = HintHandSubtype3P(0)
        hinter.set_game_settings(settings)
        hinter.set_common_view(common)
        hinter.observe_number_hint_move(0, hint, view)
        self.assertEqual(expected[2], hinter._inferred_card_kind[2])


class TestSafeDoublePlay(unittest.TestCase):
    def test_encode_duplicate_playable_same_card_uses_oldest_only(self) -> None:
        """Two physically playable copies of one card: hand type uses leftmost only."""
        settings = create_standard_game_settings(3)
        common = _common(settings)
        hand = [
            Card(Color.RED, Number.ONE),
            Card(Color.BLUE, Number.TWO),
            Card(Color.RED, Number.ONE),
            Card(Color.GREEN, Number.THREE),
            Card(Color.WHITE, Number.FOUR),
        ]
        self.assertEqual(5, h3p._encode_hand_type(hand, 5, common, settings, _unknown_belief(5)))
        hand_single = [
            Card(Color.RED, Number.ONE),
            Card(Color.BLUE, Number.TWO),
            Card(Color.GREEN, Number.THREE),
            Card(Color.WHITE, Number.FOUR),
            Card(Color.YELLOW, Number.FIVE),
        ]
        self.assertEqual(
            h3p._encode_hand_type(hand_single, 5, common, settings, _unknown_belief(5)),
            h3p._encode_hand_type(hand, 5, common, settings, _unknown_belief(5)),
        )

    def test_encode_different_playable_cards_unchanged(self) -> None:
        settings = create_standard_game_settings(3)
        common = _common(settings)
        hand = [
            Card(Color.RED, Number.ONE),
            Card(Color.BLUE, Number.ONE),
            Card(Color.GREEN, Number.ONE),
            Card(Color.WHITE, Number.TWO),
            Card(Color.YELLOW, Number.THREE),
        ]
        self.assertEqual(3, h3p._encode_hand_type(hand, 5, common, settings, _unknown_belief(5)))

    def test_invalidate_playable_on_teammates_when_one_life_left(self) -> None:
        settings = create_standard_game_settings(3)
        player = HintHandSubtype3P(0, safe_double_play=True)
        player.set_game_settings(settings)
        common = CommonView(
            live_tokens=1,
            hint_tokens=8,
            cards_to_draw=40,
            cards_discarded={},
            cards_played={Color.RED: Number.ONE},
        )
        player.set_common_view(common)
        player._inferred_card_kind = [
            [None] * 5,
            [CardKind.PLAYABLE, None, None, None, None],
            [None, CardKind.PLAYABLE, None, None, None],
        ]
        h3p._invalidate_playable_matching_card_on_other_players(
            player._inferred_card_kind,
            mover_index=0,
            hand_cards=[
                [Card(Color.WHITE, Number.FOUR)] * 5,
                [Card(Color.RED, Number.ONE), Card(Color.BLUE, Number.TWO)] * 2 + [Card(Color.GREEN, Number.THREE)],
                [Card(Color.YELLOW, Number.ONE), Card(Color.RED, Number.ONE)] + [Card(Color.WHITE, Number.FOUR)] * 3,
            ],
            played_card=Card(Color.RED, Number.ONE),
        )
        self.assertIsNone(player._inferred_card_kind[1][0])
        self.assertIsNone(player._inferred_card_kind[2][1])

    def test_no_invalidate_when_mover_is_teammate_row(self) -> None:
        matrix: List[List[Optional[CardKind]]] = [
            [None] * 2,
            [CardKind.PLAYABLE, None],
            [None] * 2,
        ]
        h3p._invalidate_playable_matching_card_on_other_players(
            matrix,
            mover_index=1,
            hand_cards=[
                [Card(Color.RED, Number.ONE), Card(Color.BLUE, Number.TWO)],
                [Card(Color.RED, Number.ONE), Card(Color.BLUE, Number.TWO)],
                [Card(Color.GREEN, Number.THREE), Card(Color.WHITE, Number.FOUR)],
            ],
            played_card=Card(Color.RED, Number.ONE),
        )
        self.assertEqual(CardKind.PLAYABLE, matrix[1][0])

    def test_align_clears_stale_playable_at_one_life(self) -> None:
        settings = create_standard_game_settings(3)
        players = [HintHandSubtype3P(i, safe_double_play=True) for i in range(3)]
        for player in players:
            player.set_game_settings(settings)
            player.set_common_view(
                CommonView(
                    live_tokens=1,
                    hint_tokens=8,
                    cards_to_draw=39,
                    cards_discarded={},
                    cards_played={Color.RED: Number.ONE},
                )
            )
        for player in players:
            player._inferred_card_kind = [
                [None] * 3,
                [None] * 3,
                [CardKind.PLAYABLE, None, None],
            ]
        move = Play(0)
        hand_cards = [
            [Card(Color.BLUE, Number.TWO), Card(Color.GREEN, Number.THREE), Card(Color.WHITE, Number.FOUR)],
            [Card(Color.BLUE, Number.TWO), Card(Color.GREEN, Number.THREE), Card(Color.WHITE, Number.FOUR)],
            [Card(Color.RED, Number.ONE), Card(Color.YELLOW, Number.TWO), Card(Color.WHITE, Number.FOUR)],
        ]
        h3p.align_convention_beliefs_after_move(
            players,
            1,
            move,
            cards_played_before={},
            hand_cards=hand_cards,
        )
        self.assertIsNone(players[0]._inferred_card_kind[2][0])

    def test_safe_double_play_disabled_skips_align_invalidation(self) -> None:
        settings = create_standard_game_settings(3)
        players = [HintHandSubtype3P(i, safe_double_play=False) for i in range(3)]
        for player in players:
            player.set_game_settings(settings)
            player.set_common_view(
                CommonView(
                    live_tokens=1,
                    hint_tokens=8,
                    cards_to_draw=39,
                    cards_discarded={},
                    cards_played={Color.RED: Number.ONE},
                )
            )
            player._inferred_card_kind = [
                [None] * 3,
                [None] * 3,
                [CardKind.PLAYABLE, None, None],
            ]
        move = Play(0)
        hand_cards = [
            [Card(Color.BLUE, Number.TWO), Card(Color.GREEN, Number.THREE), Card(Color.WHITE, Number.FOUR)],
            [Card(Color.BLUE, Number.TWO), Card(Color.GREEN, Number.THREE), Card(Color.WHITE, Number.FOUR)],
            [Card(Color.RED, Number.ONE), Card(Color.YELLOW, Number.TWO), Card(Color.WHITE, Number.FOUR)],
        ]
        h3p.align_convention_beliefs_after_move(
            players,
            1,
            move,
            cards_played_before={},
            hand_cards=hand_cards,
        )
        self.assertEqual(CardKind.PLAYABLE, players[0]._inferred_card_kind[2][0])


class TestHintHandSubtype3PGui(unittest.TestCase):
    def test_get_gui_chop_slot_is_leftmost_unknown_or_dispensable(self) -> None:
        """Chop is the leftmost unknown or dispensable slot."""
        player = HintHandSubtype3P(0)
        settings = create_standard_game_settings(3)
        player.set_game_settings(settings)
        self.assertEqual(0, player.get_gui_chop_slot(0))
        player._inferred_card_kind[0][0] = CardKind.CRITICAL
        self.assertEqual(1, player.get_gui_chop_slot(0))
        player._inferred_card_kind[0][1] = CardKind.DISPENSABLE
        self.assertEqual(1, player.get_gui_chop_slot(0))

    def test_get_gui_inferred_kind_by_slot_omits_unknown(self) -> None:
        """Only known belief slots appear in the GUI map."""
        player = HintHandSubtype3P(0)
        settings = create_standard_game_settings(3)
        player.set_game_settings(settings)
        player._inferred_card_kind[1][2] = CardKind.PLAYABLE
        self.assertEqual({2: CardKind.PLAYABLE}, player.get_gui_inferred_kind_by_slot(1))


if __name__ == "__main__":
    unittest.main()
