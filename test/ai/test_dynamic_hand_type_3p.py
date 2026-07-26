"""Tests for :mod:`hanabi.ai.dynamic_hand_type_3p`."""

from __future__ import annotations

import unittest
from typing import List, Optional

from hanabi.ai.dht_belief import (
    HandEncodingMode,
    LegacyDiscardKind,
    Playability,
    RecState,
    apply_decoded_value,
    chop_slot,
    discard_anchor_slot,
    discard_type_for_slot,
    hand_encoding_mode,
    legacy_kind_row,
    set_playability,
    slot_belief_from_legacy_kind,
)
from hanabi.ai import dynamic_hand_type_3p as h3p
from hanabi.ai.dynamic_hand_type_3p import DynamicHandType3P, HintSlotShape
from hanabi.core.card import Card, Suit
from hanabi.core.enums import CardKind, Color, Number
from hanabi.core.game import CommonView, Hand, PlayerView, create_standard_game_settings
from hanabi.core.moves import ColorHint, Discard, NumberHint, Play


def _legacy_row(kinds: List[Optional[CardKind]]) -> List[h3p.SlotBelief]:
    return [slot_belief_from_legacy_kind(k) for k in kinds]


def _set_legacy_row(player: DynamicHandType3P, seat: int, kinds: List[Optional[CardKind]]) -> None:
    player._slot_belief[seat] = _legacy_row(kinds)


def _player_legacy_matrix(player: DynamicHandType3P) -> List[List[Optional[CardKind]]]:
    return [legacy_kind_row(row) for row in player._slot_belief]


def _belief_matrix_from_legacy(
    matrix: List[List[Optional[CardKind]]],
) -> List[List[h3p.SlotBelief]]:
    return [_legacy_row(row) for row in matrix]


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


class TestDynamicHandType3PSettings(unittest.TestCase):
    def test_supports_only_three_players(self) -> None:
        s3 = create_standard_game_settings(3)
        s5 = create_standard_game_settings(5)
        self.assertTrue(DynamicHandType3P.supports_game_settings(s3))
        self.assertFalse(DynamicHandType3P.supports_game_settings(s5))


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
            3,
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

    def test_stale_critical_does_not_encode_as_play_while_unplayable(self) -> None:
        """Critical+unplayable belief is not a play candidate; encode from next unsettled slot."""
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
        # G5 is physically playable but critical+unplayable belief skips it; B4 is dispensable → 0.
        stale_critical = [CardKind.CRITICAL, None, None, None, None]
        self.assertEqual(CardKind.PLAYABLE, common.card_kind(hand[0], settings))
        self.assertEqual(0, h3p._encode_hand_type(hand, 5, common, settings, stale_critical))

    def test_play_type_indexes_unknown_playability_only(self) -> None:
        """Legacy play types are k-th among unknown playability, not absolute from-new."""
        settings = create_standard_game_settings(3)
        common = _common(settings)
        hand = [
            Card(Color.RED, Number.ONE),
            Card(Color.BLUE, Number.TWO),
            Card(Color.GREEN, Number.THREE),
            Card(Color.WHITE, Number.FOUR),
            Card(Color.YELLOW, Number.FIVE),
        ]
        row = [slot_belief_from_legacy_kind(None) for _ in range(5)]
        row[4].playability = Playability.UNPLAYABLE
        row[3].playability = Playability.UNPLAYABLE
        self.assertEqual(3, h3p._encode_hand_type(hand, 5, common, settings, row))
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
        """Encode types 0/6/7 from discard anchor (skips known useless), not raw leftmost kind."""
        kinds = [
            CardKind.USELESS,
            CardKind.CRITICAL,
            CardKind.USELESS,
            CardKind.DISPENSABLE,
            CardKind.DISPENSABLE,
        ]
        belief: List[Optional[CardKind]] = [CardKind.USELESS, None, None, None, None]
        self.assertEqual(6, h3p._hand_type_when_no_playable(kinds, belief))

    def test_no_playable_type_six_skips_known_critical_anchor(self) -> None:
        """With leftmost already critical, encode type 6 from the next slot's physical kind."""
        kinds = [
            CardKind.CRITICAL,
            CardKind.CRITICAL,
            CardKind.USELESS,
            CardKind.DISPENSABLE,
            CardKind.DISPENSABLE,
        ]
        belief: List[Optional[CardKind]] = [CardKind.CRITICAL, None, None, None, None]
        self.assertEqual(1, discard_anchor_slot(_legacy_row(belief)))
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
        self.assertIsNone(matrix[0][3])
        self.assertIsNone(matrix[0][4])
        self.assertIsNone(matrix[0][0])

    def test_type_zero_marks_chop_safe(self) -> None:
        matrix = [[None] * 5]
        h3p._apply_decoded_hand_type(matrix, 0, 0)
        self.assertEqual(CardKind.DISPENSABLE, matrix[0][0])

    def test_type_six_marks_chop_critical(self) -> None:
        matrix = [[None] * 5]
        h3p._apply_decoded_hand_type(matrix, 0, 6)
        self.assertEqual(CardKind.CRITICAL, matrix[0][0])

    def test_type_seven_marks_chop_useless(self) -> None:
        matrix = [[None] * 5]
        h3p._apply_decoded_hand_type(matrix, 0, 7)
        self.assertEqual(CardKind.USELESS, matrix[0][0])

    def test_type_three_marks_third_from_new_playable(self) -> None:
        matrix = [[None] * 5]
        h3p._apply_decoded_hand_type(matrix, 0, 3)
        self.assertEqual(CardKind.PLAYABLE, matrix[0][2])
        self.assertIsNone(matrix[0][3])
        self.assertIsNone(matrix[0][4])

    def test_decode_asserts_on_invalid_play_type(self) -> None:
        """Play decode with no unknown slots is a convention bug."""
        matrix: List[List[Optional[CardKind]]] = [
            [CardKind.PLAYABLE, CardKind.PLAYABLE, CardKind.PLAYABLE, CardKind.PLAYABLE, CardKind.USELESS]
        ]
        with self.assertRaises(AssertionError):
            h3p._apply_decoded_hand_type(matrix, 0, 1)


class TestDuplicateIdentifiedPlayableCollapse(unittest.TestCase):
    def test_duplicate_useless_belief_not_reencoded_as_playable(self) -> None:
        """Belief ``USELESS`` (duplicate collapse at encode) must not resurrect as play type ``1``–``5``."""
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


class TestDiscardAnchorFromBelief(unittest.TestCase):
    def test_leftmost_needs_discard_info(self) -> None:
        row = _legacy_row([CardKind.USELESS, None, CardKind.DISPENSABLE])
        self.assertEqual(1, discard_anchor_slot(row))

    def test_critical_is_skipped_as_discard_anchor(self) -> None:
        """Known critical does not need discard info; anchor is the next unsettled slot."""
        row = _legacy_row([CardKind.CRITICAL, None, CardKind.DISPENSABLE])
        self.assertEqual(1, discard_anchor_slot(row))

    def test_no_anchor_when_only_useless_or_critical(self) -> None:
        row = _legacy_row([CardKind.USELESS, CardKind.CRITICAL, CardKind.USELESS])
        self.assertIsNone(discard_anchor_slot(row))

    def test_type_six_marks_next_after_known_critical(self) -> None:
        """Re-decode type 6 after leftmost critical marks the next unsettled slot."""
        from hanabi.ai.dht_belief import apply_decoded_value, Playability

        row = _legacy_row([CardKind.CRITICAL, None, None, None, None])
        for belief in row:
            belief.playability = Playability.UNKNOWN
        apply_decoded_value(row, 6)
        self.assertEqual(Playability.UNPLAYABLE, row[0].playability)
        self.assertEqual(LegacyDiscardKind.CRITICAL, row[0].legacy_kind)
        self.assertEqual(LegacyDiscardKind.CRITICAL, row[1].legacy_kind)
        self.assertEqual(LegacyDiscardKind.UNKNOWN, row[2].legacy_kind)
        # Criticals are tier 5; chop is leftmost unknown kind (tier 4).
        self.assertEqual(2, chop_slot(row))


class TestChopFromBelief(unittest.TestCase):
    def test_useless_outranks_recommended(self) -> None:
        row = _legacy_row([None, CardKind.USELESS, None, None, None])
        row[3].rec_state = RecState.RECOMMENDED
        self.assertEqual(1, chop_slot(row))

    def test_recommended_outranks_safe(self) -> None:
        row = _legacy_row([CardKind.DISPENSABLE, None, None, None, None])
        row[2].rec_state = RecState.RECOMMENDED
        self.assertEqual(2, chop_slot(row))


class TestPlayableSlotFromHandType(unittest.TestCase):
    def test_type_three_is_third_from_new(self) -> None:
        self.assertEqual(2, _playable_slot_from_hand_type(3, 5))

    def test_non_playable_types_return_none(self) -> None:
        self.assertIsNone(_playable_slot_from_hand_type(0, 5))
        self.assertIsNone(_playable_slot_from_hand_type(6, 5))


class TestStep5IdentifiesNewPlayable(unittest.TestCase):
    def test_true_when_decode_would_newly_mark_playable(self) -> None:
        """Next player (P1 for hinter P3) gets W1 newly marked playable → step-2 urgent."""
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
        beliefs = _belief_matrix_from_legacy([[None] * 5 for _ in range(3)])
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
        beliefs = _belief_matrix_from_legacy(
            [
                [None, None, None, None, CardKind.PLAYABLE],
                [None, None, None, None, None],
                [None, None, None, None, None],
            ]
        )
        self.assertFalse(
            h3p._convention_hint_would_identify_new_playable(2, view, common, settings, beliefs)
        )

    def test_false_when_same_identity_already_playable_on_other_seat(self) -> None:
        """Do not prioritize a hint that would double-mark the same playable card."""
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
                        Card(Color.WHITE, Number.ONE),
                    ]
                ),
            },
            own_hand_size=5,
        )
        beliefs = _belief_matrix_from_legacy([[None] * 5 for _ in range(3)])
        set_playability(beliefs[1][4], Playability.PLAYABLE)
        self.assertFalse(
            h3p._convention_hint_would_identify_new_playable(2, view, common, settings, beliefs)
        )

    def test_false_when_only_topping_up_hand_that_already_has_playable(self) -> None:
        """Defer when next already has a playable (topping up is not step-2-urgent)."""
        settings = create_standard_game_settings(3)
        common = _common(settings)
        view = PlayerView(
            teammates={
                0: Hand(
                    [
                        Card(Color.BLUE, Number.ONE),
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
        beliefs = _belief_matrix_from_legacy([[None] * 5 for _ in range(3)])
        set_playability(beliefs[0][0], Playability.PLAYABLE)
        self.assertFalse(
            h3p._convention_hint_would_identify_new_playable(2, view, common, settings, beliefs)
        )

    def test_false_when_both_peers_would_newly_mark_same_identity(self) -> None:
        """Next's new playable matching prev's new mark is double-play risk — not urgent."""
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
                        Card(Color.WHITE, Number.ONE),
                    ]
                ),
            },
            own_hand_size=5,
        )
        beliefs = _belief_matrix_from_legacy([[None] * 5 for _ in range(3)])
        self.assertFalse(
            h3p._convention_hint_would_identify_new_playable(2, view, common, settings, beliefs)
        )

    def test_false_when_only_prev_player_gets_new_playable(self) -> None:
        """Prev-only unlock is not step-2-urgent (next can hint after a discard)."""
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
                        Card(Color.RED, Number.FOUR),
                    ]
                ),
                1: Hand(
                    [
                        Card(Color.BLUE, Number.TWO),
                        Card(Color.GREEN, Number.FOUR),
                        Card(Color.YELLOW, Number.FIVE),
                        Card(Color.RED, Number.THREE),
                        Card(Color.WHITE, Number.ONE),
                    ]
                ),
            },
            own_hand_size=5,
        )
        beliefs = _belief_matrix_from_legacy([[None] * 5 for _ in range(3)])
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
        player = DynamicHandType3P(2)
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
        player = DynamicHandType3P(1)
        player.set_game_settings(settings)
        for seat in range(3):
            self.assertEqual(5, len(player._slot_belief[seat]))
            self.assertTrue(all(kind is None for kind in _player_legacy_matrix(player)[seat]))

    def test_drawn_slot_unknown_after_play(self) -> None:
        settings = create_standard_game_settings(3)
        player = DynamicHandType3P(0)
        player.set_game_settings(settings)
        player.set_common_view(_common(settings))
        _set_legacy_row(player, 0, [None, CardKind.CRITICAL, CardKind.PLAYABLE, None, CardKind.USELESS])
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
            _player_legacy_matrix(player)[0],
        )

    def test_shrink_hand_when_no_draw(self) -> None:
        settings = create_standard_game_settings(3)
        player = DynamicHandType3P(0)
        player.set_game_settings(settings)
        common = _common(settings)
        player.set_common_view(common)
        _set_legacy_row(player, 0, [None, None, None, CardKind.PLAYABLE, None])
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
        self.assertEqual([None, None, CardKind.PLAYABLE, None], _player_legacy_matrix(player)[0])

    def test_safe_cleared_on_non_useless_middle_rank_discard(self) -> None:
        settings = create_standard_game_settings(3)
        player = DynamicHandType3P(0)
        player.set_game_settings(settings)
        common = _common(settings)
        player.set_common_view(common)
        player._slot_belief = [
            _legacy_row([None, CardKind.DISPENSABLE, None, CardKind.CRITICAL, None]),
            _legacy_row([CardKind.DISPENSABLE, None, None, None, None]),
            _legacy_row([None, None, CardKind.DISPENSABLE, None, None]),
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
            _player_legacy_matrix(player)[0],
        )
        self.assertEqual([None, None, None, None, None], _player_legacy_matrix(player)[1])
        self.assertEqual([None, None, None, None, None], _player_legacy_matrix(player)[2])

    def test_safe_unchanged_on_useless_middle_rank_discard(self) -> None:
        settings = create_standard_game_settings(3)
        player = DynamicHandType3P(0)
        player.set_game_settings(settings)
        common = _common(settings)
        player.set_common_view(common)
        _set_legacy_row(player, 1, [None, CardKind.DISPENSABLE, None, None, None])
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
        self.assertEqual([CardKind.DISPENSABLE, None, None, None, None], _player_legacy_matrix(player)[1])

    def test_frontier_play_reopens_unplayable_using_played_snapshot(self) -> None:
        """Game updates common_view before observe; reopen must use prior cards_played snapshot."""
        settings = create_standard_game_settings(3)
        player = DynamicHandType3P(0)
        player.set_game_settings(settings)
        player.set_common_view(_common(settings))
        player._cards_played_snapshot = {}
        for seat in range(3):
            for belief in player._slot_belief[seat]:
                belief.playability = Playability.UNPLAYABLE
        # Simulate post-move common_view already showing R1 played.
        player._common_view = CommonView(
            live_tokens=3,
            hint_tokens=8,
            cards_to_draw=39,
            cards_discarded={},
            cards_played={Color.RED: Number.ONE},
        )
        view = PlayerView(
            teammates={
                1: Hand([Card(Color.GREEN, Number.TWO)] * 4),
                2: Hand([Card(Color.BLUE, Number.THREE)] * 5),
            },
            own_hand_size=5,
        )
        player.observe_play_move(1, Play(0), view)
        self.assertTrue(
            all(Playability.UNKNOWN == b.playability for row in player._slot_belief for b in row),
            "frontier-opening play must reopen all unplayable slots",
        )
        self.assertEqual({Color.RED: Number.ONE}, player._cards_played_snapshot)

    def test_safe_unchanged_on_rank_one_discard(self) -> None:
        settings = create_standard_game_settings(3)
        player = DynamicHandType3P(0)
        player.set_game_settings(settings)
        common = _common(settings)
        player.set_common_view(common)
        _set_legacy_row(player, 0, [None, CardKind.DISPENSABLE, None, None, None])
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
        self.assertEqual([CardKind.DISPENSABLE, None, None, None], _player_legacy_matrix(player)[0])

    def test_safe_cleared_on_middle_rank_misplay(self) -> None:
        settings = create_standard_game_settings(3)
        player = DynamicHandType3P(0)
        player.set_game_settings(settings)
        common = _common(settings)
        player.set_common_view(common)
        player._slot_belief = [
            _legacy_row([None, CardKind.DISPENSABLE, None, None, None]),
            _legacy_row([CardKind.DISPENSABLE, None, None, None, None]),
            _legacy_row([None] * 5),
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
        self.assertEqual([None, None, None, None, None], _player_legacy_matrix(player)[0])
        self.assertEqual([None, None, None, None, None], _player_legacy_matrix(player)[1])


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
        player = DynamicHandType3P(0)
        player.set_game_settings(settings)
        player.set_common_view(common)
        move = player.play(view)
        self.assertTrue(player.is_move_legal(view, move))

    def test_plays_identified_playable_first(self) -> None:
        settings = create_standard_game_settings(3)
        player = DynamicHandType3P(0)
        player.set_game_settings(settings)
        player.set_common_view(_common(settings))
        _set_legacy_row(player, 0, [None, CardKind.PLAYABLE, None, None, None])
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


class TestIndependentOwnDecode(unittest.TestCase):
    def test_decoders_match_public_decode_hinter_updates_teammates_only(self) -> None:
        """Every observer updates both non-hinter rows; hinter never writes own row."""
        settings = create_standard_game_settings(3)
        common = _common(settings)
        players = [DynamicHandType3P(i) for i in range(3)]
        for player in players:
            player.set_game_settings(settings)
            player.set_common_view(common)

        hand_p1 = [Card(Color.GREEN, Number.TWO)] * 4 + [Card(Color.RED, Number.ONE)]
        hand_p2 = [Card(Color.BLUE, Number.ONE)] * 5
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
        enc = (
            h3p._peer_code_for_hand(hand_p1, players[0]._slot_belief[1], common, settings)
            + h3p._peer_code_for_hand(hand_p2, players[0]._slot_belief[2], common, settings)
        ) % 8
        hint = h3p._build_hint_for_encoded(0, views[0], enc)
        self.assertIsNotNone(hint)
        own_before = [
            [
                h3p.SlotBelief(b.playability, b.legacy_kind, b.rec_state)
                for b in players[seat]._slot_belief[seat]
            ]
            for seat in range(3)
        ]
        hinter_own_before = _player_legacy_matrix(players[0])[0]
        for player, view in zip(players, views):
            if isinstance(hint, NumberHint):
                player.observe_number_hint_move(0, hint, view)
            else:
                assert isinstance(hint, ColorHint)
                player.observe_color_hint_move(0, hint, view)
        self.assertEqual(hinter_own_before, _player_legacy_matrix(players[0])[0])
        h3p.assert_independent_own_decode_matches(players, 0, hint, views, own_before)
        self.assertTrue(
            any(kind is not None for kind in _player_legacy_matrix(players[0])[1]),
            "hinter must update hint-target row from public decode",
        )
        self.assertTrue(
            any(kind is not None for kind in _player_legacy_matrix(players[0])[2]),
            "hinter must update other non-hinter row from public decode",
        )
        h3p.assert_public_non_hinter_rows_agree(players, 0, hint)

    def test_hinter_does_not_update_own_row(self) -> None:
        settings = create_standard_game_settings(3)
        common = _common(settings)
        hinter = DynamicHandType3P(0)
        hinter.set_game_settings(settings)
        hinter.set_common_view(common)
        hand_p1 = [Card(Color.GREEN, Number.TWO)] * 4 + [Card(Color.RED, Number.ONE)]
        hand_p2 = [Card(Color.BLUE, Number.ONE)] * 5
        view = PlayerView(teammates={1: Hand(hand_p1), 2: Hand(hand_p2)}, own_hand_size=5)
        enc = (
            h3p._peer_code_for_hand(hand_p1, hinter._slot_belief[1], common, settings)
            + h3p._peer_code_for_hand(hand_p2, hinter._slot_belief[2], common, settings)
        ) % 8
        hint = h3p._build_hint_for_encoded(0, view, enc)
        self.assertIsNotNone(hint)
        own_before = _player_legacy_matrix(hinter)[0]
        if isinstance(hint, NumberHint):
            hinter.observe_number_hint_move(0, hint, view)
        else:
            assert isinstance(hint, ColorHint)
            hinter.observe_color_hint_move(0, hint, view)
        self.assertEqual(own_before, _player_legacy_matrix(hinter)[0])
        self.assertTrue(any(kind is not None for kind in _player_legacy_matrix(hinter)[1]))
        self.assertTrue(any(kind is not None for kind in _player_legacy_matrix(hinter)[2]))


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


class TestRecommendationMode(unittest.TestCase):
    def test_rec_play_decode_does_not_mark_newer_unplayable(self) -> None:
        """Rec play picks by rank, not newest playable — newer unknowns stay unknown."""
        # n_play=3, n_disc=5 → recommendation mode (sum 8).
        row = [slot_belief_from_legacy_kind(None) for _ in range(5)]
        row[2].playability = Playability.UNPLAYABLE
        row[3].playability = Playability.UNPLAYABLE
        self.assertEqual(HandEncodingMode.RECOMMENDATION, hand_encoding_mode(row))
        # Unknown-from-newest: [4, 1, 0]. Type 3 → slot 0 playable; 4 and 1 stay unknown.
        apply_decoded_value(row, 3)
        self.assertEqual(Playability.PLAYABLE, row[0].playability)
        self.assertEqual(Playability.UNKNOWN, row[1].playability)
        self.assertEqual(Playability.UNKNOWN, row[4].playability)

    def test_legacy_play_decode_marks_newer_unplayable(self) -> None:
        """Legacy play type still proves newer unknowns are unplayable."""
        row = [slot_belief_from_legacy_kind(None) for _ in range(5)]
        self.assertEqual(HandEncodingMode.LEGACY, hand_encoding_mode(row))
        apply_decoded_value(row, 3)
        self.assertEqual(Playability.PLAYABLE, row[2].playability)
        self.assertEqual(Playability.UNPLAYABLE, row[3].playability)
        self.assertEqual(Playability.UNPLAYABLE, row[4].playability)
        self.assertEqual(Playability.UNKNOWN, row[0].playability)
        self.assertEqual(Playability.UNKNOWN, row[1].playability)

    def test_legacy_type_zero_switches_hand_to_recommendation_mode(self) -> None:
        row = [slot_belief_from_legacy_kind(None) for _ in range(5)]
        apply_decoded_value(row, 0)
        self.assertEqual(HandEncodingMode.RECOMMENDATION, hand_encoding_mode(row))

    def test_rec_type_zero_marks_chop_recommended(self) -> None:
        row = [slot_belief_from_legacy_kind(None) for _ in range(5)]
        apply_decoded_value(row, 0)
        self.assertEqual(HandEncodingMode.RECOMMENDATION, hand_encoding_mode(row))
        apply_decoded_value(row, 0)
        chop = chop_slot(row)
        assert chop is not None
        self.assertEqual(RecState.RECOMMENDED, row[chop].rec_state)

    def test_discard_recommended_before_safe_chop(self) -> None:
        settings = create_standard_game_settings(3)
        common = CommonView(
            live_tokens=settings.max_live_tokens,
            hint_tokens=7,
            cards_to_draw=40,
            cards_discarded={},
            cards_played={},
        )
        player = DynamicHandType3P(0)
        player.set_game_settings(settings)
        player.set_common_view(common)
        row = player._slot_belief[0]
        row[1].legacy_kind = LegacyDiscardKind.SAFE
        row[3].rec_state = RecState.RECOMMENDED
        view = PlayerView(
            teammates={
                1: Hand([Card(Color.RED, Number.TWO)] * 5),
                2: Hand([Card(Color.BLUE, Number.THREE)] * 5),
            },
            own_hand_size=5,
        )
        move = player.play(view)
        self.assertIsInstance(move, Discard)
        assert isinstance(move, Discard)
        self.assertEqual(3, move.card)

    def test_rec_encode_ignores_physical_useless_older_than_chop(self) -> None:
        """Visible useless older than belief chop is not encodable; encode chop instead."""
        settings = create_standard_game_settings(3)
        common = CommonView(
            live_tokens=3,
            hint_tokens=8,
            cards_to_draw=40,
            cards_discarded={Color.RED: Suit({Number.ONE: 3})},
            cards_played={Color.RED: Number.ONE},
        )
        hand = [
            Card(Color.RED, Number.ONE),
            Card(Color.BLUE, Number.TWO),
            Card(Color.GREEN, Number.THREE),
            Card(Color.WHITE, Number.FOUR),
            Card(Color.YELLOW, Number.FIVE),
        ]
        row = [slot_belief_from_legacy_kind(None) for _ in range(5)]
        for belief in row:
            belief.playability = Playability.UNPLAYABLE
        row[3].rec_state = RecState.RECOMMENDED
        self.assertEqual(HandEncodingMode.RECOMMENDATION, hand_encoding_mode(row))
        self.assertEqual(3, chop_slot(row))
        self.assertEqual(CardKind.USELESS, common.card_kind(hand[0], settings))
        code = h3p._encode_recommendation_peer_code(hand, row, common, settings)
        self.assertEqual(0, code)
        self.assertEqual(
            code,
            h3p._peer_code_for_hand(hand, row, common, settings),
            "peer code must use recommendation encode when hand is in rec mode",
        )

    def test_rec_mode_peer_code_is_decodable_on_same_row(self) -> None:
        """Recommendation peer codes must map under apply_decoded_value (exp run 79 crash)."""
        settings = create_standard_game_settings(3)
        common = _common(settings)
        hand = [
            Card(Color.BLUE, Number.FIVE),
            Card(Color.GREEN, Number.FOUR),
            Card(Color.WHITE, Number.THREE),
            Card(Color.YELLOW, Number.TWO),
            Card(Color.RED, Number.FIVE),
        ]
        row = [slot_belief_from_legacy_kind(None) for _ in range(5)]
        for belief in row[:-1]:
            belief.playability = Playability.UNPLAYABLE
        self.assertEqual(HandEncodingMode.RECOMMENDATION, hand_encoding_mode(row))
        code = h3p._peer_code_for_hand(hand, row, common, settings)
        apply_decoded_value(row, code)

    def test_rec_encode_skips_physically_playable_chop(self) -> None:
        """Do not recommend discarding a stale-unplayable slot that is physically playable."""
        settings = create_standard_game_settings(3)
        common = _common(settings)
        hand = [
            Card(Color.RED, Number.ONE),
            Card(Color.BLUE, Number.TWO),
            Card(Color.GREEN, Number.THREE),
            Card(Color.WHITE, Number.FOUR),
            Card(Color.YELLOW, Number.FIVE),
        ]
        row = [slot_belief_from_legacy_kind(None) for _ in range(5)]
        for belief in row:
            belief.playability = Playability.UNPLAYABLE
        # Slot 0 is chop and physically playable; slot 1 is trash.
        common = CommonView(
            live_tokens=3,
            hint_tokens=8,
            cards_to_draw=40,
            cards_discarded={Color.BLUE: Suit({Number.TWO: 2})},
            cards_played={},
        )
        self.assertEqual(CardKind.PLAYABLE, common.card_kind(hand[0], settings))
        self.assertEqual(CardKind.USELESS, common.card_kind(hand[1], settings))
        code = h3p._encode_recommendation_peer_code(hand, row, common, settings)
        self.assertEqual(discard_type_for_slot(row, 1), code)

    def test_rec_encode_dispensable_prefers_newest(self) -> None:
        """Among safe discards on the chop chain, prefer newest slot (no rank)."""
        settings = create_standard_game_settings(3)
        # No yellow/green piles: Y2, G4, G2 are dispensable; W4 playable → not on chain.
        common = CommonView(
            live_tokens=3,
            hint_tokens=8,
            cards_to_draw=40,
            cards_discarded={},
            cards_played={Color.RED: Number.THREE, Color.WHITE: Number.THREE, Color.BLUE: Number.ONE},
        )
        hand = [
            Card(Color.YELLOW, Number.TWO),
            Card(Color.GREEN, Number.FOUR),
            Card(Color.GREEN, Number.FIVE),
            Card(Color.WHITE, Number.FOUR),
            Card(Color.GREEN, Number.TWO),
        ]
        row = [slot_belief_from_legacy_kind(None) for _ in range(5)]
        set_playability(row[3], Playability.PLAYABLE)
        for slot in (0, 1, 2, 4):
            set_playability(row[slot], Playability.UNPLAYABLE)
        self.assertEqual(HandEncodingMode.RECOMMENDATION, hand_encoding_mode(row))
        self.assertEqual(CardKind.DISPENSABLE, common.card_kind(hand[0], settings))
        self.assertEqual(CardKind.DISPENSABLE, common.card_kind(hand[1], settings))
        self.assertEqual(CardKind.DISPENSABLE, common.card_kind(hand[4], settings))
        code = h3p._encode_recommendation_peer_code(hand, row, common, settings)
        self.assertEqual(discard_type_for_slot(row, 4), code)


class TestDynamicHandType3PGui(unittest.TestCase):
    def test_get_gui_chop_slot_uses_priority_tiers(self) -> None:
        """Chop is the expected discard by priority tiers (§3.4)."""
        player = DynamicHandType3P(0)
        settings = create_standard_game_settings(3)
        player.set_game_settings(settings)
        self.assertEqual(0, player.get_gui_chop_slot(0))
        _set_legacy_row(player, 0, [CardKind.CRITICAL, None, None, None, None])
        self.assertEqual(1, player.get_gui_chop_slot(0))
        _set_legacy_row(player, 0, [CardKind.CRITICAL, CardKind.DISPENSABLE, None, None, None])
        self.assertEqual(1, player.get_gui_chop_slot(0))

    def test_get_gui_inferred_kind_by_slot_omits_unknown(self) -> None:
        """Only known belief slots appear in the GUI map."""
        player = DynamicHandType3P(0)
        settings = create_standard_game_settings(3)
        player.set_game_settings(settings)
        _set_legacy_row(player, 1, [None, None, CardKind.PLAYABLE, None, None])
        self.assertEqual({2: CardKind.PLAYABLE}, player.get_gui_inferred_kind_by_slot(1))


if __name__ == "__main__":
    unittest.main()
