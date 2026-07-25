"""Tests for :mod:`hanabi.ai.dynamic_recommendation_3p` and :mod:`hanabi.ai.dr_belief`."""

from __future__ import annotations

import unittest

from hanabi.ai import dynamic_recommendation_3p as dr
from hanabi.ai.dr_belief import (
    Playability,
    apply_decoded_value,
    copy_hand_belief,
    discard_chain,
    discard_types_for_n_play,
    finalize_chop_after_shift,
    fresh_hand_belief,
    indicable_discard_options,
    n_play,
    reset_chop_after_removal,
    set_playability,
)
from hanabi.ai.dynamic_recommendation_3p import (
    ChopClass,
    DynamicRecommendation3P,
    HintQuality,
    HintSlotShape,
    _HINT_CHOP_MATRIX,
)
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


def _teammate_view() -> PlayerView:
    return PlayerView(
        teammates={
            1: Hand([Card(Color.BLUE, Number.FOUR)] * 5),
            2: Hand([Card(Color.GREEN, Number.THREE)] * 5),
        },
        own_hand_size=5,
    )


class TestDynamicRecommendation3PSettings(unittest.TestCase):
    def test_supports_only_three_players(self) -> None:
        s3 = create_standard_game_settings(3)
        s5 = create_standard_game_settings(5)
        self.assertTrue(DynamicRecommendation3P.supports_game_settings(s3))
        self.assertFalse(DynamicRecommendation3P.supports_game_settings(s5))


class TestDiscardTypePartition(unittest.TestCase):
    def test_opening_n_play_five(self) -> None:
        self.assertEqual([0, 7, 6], discard_types_for_n_play(5))

    def test_n_play_zero(self) -> None:
        self.assertEqual([0, 7, 6, 5, 4, 3, 2], discard_types_for_n_play(0))

    def test_n_play_three_skips_play_codes(self) -> None:
        self.assertEqual([0, 7, 6, 5, 4], discard_types_for_n_play(3))


class TestDiscardDecode(unittest.TestCase):
    def test_confirm_chop_closes_unknowns(self) -> None:
        hand = fresh_hand_belief(5)
        self.assertEqual(0, hand.chop)
        self.assertFalse(hand.chop_confirmed)
        apply_decoded_value(hand, 0)
        self.assertTrue(all(Playability.UNPLAYABLE == b.playability for b in hand.slots))
        self.assertEqual(0, hand.chop)
        self.assertTrue(hand.chop_confirmed)

    def test_play_decode_marks_newest_unknown(self) -> None:
        hand = fresh_hand_belief(5)
        apply_decoded_value(hand, 1)
        self.assertEqual(Playability.PLAYABLE, hand.slots[4].playability)
        self.assertTrue(all(Playability.UNKNOWN == hand.slots[i].playability for i in range(4)))
        self.assertEqual(0, hand.chop)
        self.assertFalse(hand.chop_confirmed)

    def test_play_decode_marks_newer_unknowns_unplayable(self) -> None:
        """Type k ⇒ k-th newest playable; newer unknowns become unplayable (§5.1)."""
        hand = fresh_hand_belief(5)
        apply_decoded_value(hand, 3)  # 3rd newest = slot 2
        self.assertEqual(Playability.PLAYABLE, hand.slots[2].playability)
        self.assertEqual(Playability.UNPLAYABLE, hand.slots[4].playability)
        self.assertEqual(Playability.UNPLAYABLE, hand.slots[3].playability)
        self.assertTrue(all(Playability.UNKNOWN == hand.slots[i].playability for i in range(2)))

    def test_last_discard_code_names_mth_candidate_confirmed(self) -> None:
        hand = fresh_hand_belief(5)
        apply_decoded_value(hand, 6)  # D[2] when N_play=5 → candidate[2] = slot 2
        self.assertEqual(2, hand.chop)
        self.assertTrue(hand.chop_confirmed)
        self.assertTrue(hand.chop_hinted)

    def test_candidates_are_first_m_of_wrapped_chain(self) -> None:
        """Chop on 3 → chain [3,4,0,1,2]; m=3 candidates are 3/4/0 — not min(remainder)."""
        from hanabi.ai.dr_belief import discard_code_candidates

        hand = fresh_hand_belief(5)
        hand.chop = 3
        self.assertEqual([3, 4, 0, 1, 2], discard_chain(hand))
        self.assertEqual([3, 4, 0], discard_code_candidates(hand))
        apply_decoded_value(hand, 6)  # D[2] → candidate[2] = slot 0
        self.assertEqual(0, hand.chop)
        self.assertTrue(hand.chop_confirmed)

    def test_last_code_when_exactly_m_candidates(self) -> None:
        # N_play=3 → D=[0,7,6,5,4]; five candidates; last code names candidate[4].
        hand = fresh_hand_belief(5)
        set_playability(hand.slots[0], Playability.UNPLAYABLE)
        set_playability(hand.slots[1], Playability.UNPLAYABLE)
        self.assertEqual(3, n_play(hand))
        apply_decoded_value(hand, 4)
        self.assertEqual(4, hand.chop)
        self.assertTrue(hand.chop_confirmed)


class TestStickyChop(unittest.TestCase):
    def test_advances_to_next_newer_after_removal(self) -> None:
        """Recommended chop leaves → next newer candidate, default urgency (§8.2)."""
        hand = fresh_hand_belief(5)
        for belief in hand.slots:
            set_playability(belief, Playability.UNPLAYABLE)
        hand.chop = 2
        hand.chop_confirmed = True
        hand.chop_hinted = True
        reset_chop_after_removal(hand, 2)
        self.assertEqual(2, hand.chop)  # pre-shift: old slot 3 → 2 after removal
        self.assertFalse(hand.chop_confirmed)
        self.assertFalse(hand.chop_hinted)
        hand.slots = hand.slots[:2] + hand.slots[3:]
        finalize_chop_after_shift(hand)
        self.assertEqual(2, hand.chop)
        self.assertEqual(ChopClass.DEFAULT, dr._chop_class(hand))

    def test_skips_playable_when_advancing(self) -> None:
        hand = fresh_hand_belief(5)
        for belief in hand.slots:
            set_playability(belief, Playability.UNPLAYABLE)
        set_playability(hand.slots[3], Playability.PLAYABLE)
        hand.chop = 2
        hand.chop_confirmed = True
        hand.chop_hinted = True
        reset_chop_after_removal(hand, 2)
        self.assertEqual(3, hand.chop)  # old slot 4 → 3 after removal
        hand.slots = hand.slots[:2] + hand.slots[3:]
        finalize_chop_after_shift(hand)
        self.assertEqual(3, hand.chop)

    def test_falls_back_to_leftmost_when_no_newer(self) -> None:
        hand = fresh_hand_belief(5)
        for belief in hand.slots:
            set_playability(belief, Playability.UNPLAYABLE)
        hand.chop = 4
        hand.chop_confirmed = True
        hand.chop_hinted = True
        reset_chop_after_removal(hand, 4)
        self.assertIsNone(hand.chop)
        hand.slots = hand.slots[:4]
        finalize_chop_after_shift(hand)
        self.assertEqual(0, hand.chop)
        self.assertFalse(hand.chop_confirmed)
        self.assertFalse(hand.chop_hinted)

    def test_play_decode_on_chop_advances_right(self) -> None:
        hand = fresh_hand_belief(5)
        hand.chop = 4
        hand.chop_confirmed = True
        hand.chop_hinted = True
        apply_decoded_value(hand, 1)  # marks newest (slot 4) playable
        self.assertEqual(Playability.PLAYABLE, hand.slots[4].playability)
        self.assertEqual(0, hand.chop)
        self.assertFalse(hand.chop_confirmed)
        self.assertFalse(hand.chop_hinted)


class TestIndicableOptions(unittest.TestCase):
    def test_opening_options(self) -> None:
        hand = fresh_hand_belief(5)
        opts = indicable_discard_options(hand)
        codes = [c for c, _, _ in opts]
        self.assertEqual([0, 7, 6], codes)
        self.assertEqual(0, opts[0][1])
        self.assertTrue(opts[0][2])
        self.assertEqual(1, opts[1][1])
        self.assertTrue(opts[1][2])
        self.assertEqual(2, opts[2][1])
        self.assertTrue(opts[2][2])


class TestHintSlotShape(unittest.TestCase):
    def test_old_mid_new(self) -> None:
        self.assertEqual(HintSlotShape.OLD, dr._hint_slot_shape([0, 2], 5))
        self.assertEqual(HintSlotShape.MID, dr._hint_slot_shape([2, 3], 5))
        self.assertEqual(HintSlotShape.NEW, dr._hint_slot_shape([4], 5))


class TestEncodePreferPlay(unittest.TestCase):
    def test_encodes_playable_unknown(self) -> None:
        settings = create_standard_game_settings(3)
        common = _common(settings)
        hand = [
            Card(Color.RED, Number.FOUR),
            Card(Color.BLUE, Number.FOUR),
            Card(Color.GREEN, Number.FOUR),
            Card(Color.YELLOW, Number.FOUR),
            Card(Color.RED, Number.ONE),
        ]
        belief = fresh_hand_belief(5)
        code, discard_card = dr._encode_peer_code(hand, belief, common, settings)
        self.assertEqual(1, code)  # newest playable → type 1
        self.assertIsNone(discard_card)

    def test_encodes_newest_playable_not_lowest_rank(self) -> None:
        """Among several playables, encode the newest (rightmost), not lowest rank."""
        settings = create_standard_game_settings(3)
        common = _common(settings)
        # Oldest R1 and newest G1 both playable; must pick G1 → type 1.
        hand = [
            Card(Color.RED, Number.ONE),
            Card(Color.BLUE, Number.FOUR),
            Card(Color.YELLOW, Number.FOUR),
            Card(Color.WHITE, Number.FOUR),
            Card(Color.GREEN, Number.ONE),
        ]
        belief = fresh_hand_belief(5)
        code, discard_card = dr._encode_peer_code(hand, belief, common, settings)
        self.assertEqual(1, code)
        self.assertIsNone(discard_card)


class TestDispatch(unittest.TestCase):
    def test_play_before_discard(self) -> None:
        settings = create_standard_game_settings(3)
        player = DynamicRecommendation3P(0)
        player.set_game_settings(settings)
        player.set_common_view(_common(settings))
        player._hand_belief[0].slots[2].playability = Playability.PLAYABLE
        player._hand_belief[0].chop = 0
        player._hand_belief[0].chop_confirmed = True
        move = player.play(_teammate_view())
        self.assertIsInstance(move, Play)
        self.assertEqual(2, move.card)

    def test_confirmed_chop_before_hint(self) -> None:
        settings = create_standard_game_settings(3)
        player = DynamicRecommendation3P(0)
        player.set_game_settings(settings)
        # Discard is illegal at max hint tokens; leave room so chop discard is allowed.
        common = _common(settings)
        player.set_common_view(
            CommonView(
                live_tokens=common.live_tokens,
                hint_tokens=common.hint_tokens - 1,
                cards_to_draw=common.cards_to_draw,
                cards_discarded=common.cards_discarded,
                cards_played=common.cards_played,
            )
        )
        for belief in player._hand_belief[0].slots:
            set_playability(belief, Playability.UNPLAYABLE)
        player._hand_belief[0].chop = 0
        player._hand_belief[0].chop_confirmed = True
        player._hand_belief[0].chop_hinted = True
        # Step-2 must not fire: next seat already has a playable.
        player._hand_belief[1].slots[4].playability = Playability.PLAYABLE
        move = player.play(_teammate_view())
        self.assertIsInstance(move, Discard)
        self.assertEqual(0, move.card)

    def test_double_play_hint_kept_when_chop_default(self) -> None:
        """Default chop: double-play is fine, so still hint."""
        settings = create_standard_game_settings(3)
        player = DynamicRecommendation3P(0)
        player.set_game_settings(settings)
        common = _common(settings)
        player.set_common_view(
            CommonView(
                live_tokens=common.live_tokens,
                hint_tokens=common.hint_tokens - 1,
                cards_to_draw=common.cards_to_draw,
                cards_discarded=common.cards_discarded,
                cards_played=common.cards_played,
            )
        )
        for belief in player._hand_belief[0].slots:
            set_playability(belief, Playability.UNPLAYABLE)
        player._hand_belief[0].chop = 0
        player._hand_belief[0].chop_confirmed = False
        player._hand_belief[0].chop_hinted = False
        junk = Card(Color.BLUE, Number.FOUR)
        r1 = Card(Color.RED, Number.ONE)
        view = PlayerView(
            teammates={
                1: Hand([junk, junk, junk, junk, r1]),
                2: Hand([junk, junk, junk, junk, r1]),
            },
            own_hand_size=5,
        )
        self.assertTrue(
            dr._convention_hint_would_cause_double_play(
                0, view, player.common_view, settings, player._hand_belief
            )
        )
        move = player.play(view)
        self.assertNotIsInstance(move, Discard)

    def test_double_play_hint_prefers_confirmed_chop(self) -> None:
        """Confirmed chop: double-play is fine, so discard that chop."""
        settings = create_standard_game_settings(3)
        player = DynamicRecommendation3P(0)
        player.set_game_settings(settings)
        common = _common(settings)
        player.set_common_view(
            CommonView(
                live_tokens=common.live_tokens,
                hint_tokens=common.hint_tokens - 1,
                cards_to_draw=common.cards_to_draw,
                cards_discarded=common.cards_discarded,
                cards_played=common.cards_played,
            )
        )
        for belief in player._hand_belief[0].slots:
            set_playability(belief, Playability.UNPLAYABLE)
        player._hand_belief[0].chop = 2
        player._hand_belief[0].chop_confirmed = True
        player._hand_belief[0].chop_hinted = True
        junk = Card(Color.BLUE, Number.FOUR)
        r1 = Card(Color.RED, Number.ONE)
        view = PlayerView(
            teammates={
                1: Hand([junk, junk, junk, junk, r1]),
                2: Hand([junk, junk, junk, junk, r1]),
            },
            own_hand_size=5,
        )
        self.assertEqual(ChopClass.CONFIRMED, dr._chop_class(player._hand_belief[0]))
        move = player.play(view)
        self.assertIsInstance(move, Discard)
        self.assertEqual(2, move.card)

    def test_confirmed_chop_before_fine_hint(self) -> None:
        """Confirmed chop: fine hint loses to discard."""
        settings = create_standard_game_settings(3)
        player = DynamicRecommendation3P(0)
        player.set_game_settings(settings)
        common = _common(settings)
        player.set_common_view(
            CommonView(
                live_tokens=common.live_tokens,
                hint_tokens=common.hint_tokens - 1,
                cards_to_draw=common.cards_to_draw,
                cards_discarded=common.cards_discarded,
                cards_played=common.cards_played,
            )
        )
        for belief in player._hand_belief[0].slots:
            set_playability(belief, Playability.UNPLAYABLE)
        player._hand_belief[0].chop = 2
        player._hand_belief[0].chop_confirmed = True
        player._hand_belief[0].chop_hinted = True
        player._hand_belief[1].slots[4].playability = Playability.PLAYABLE
        move = player.play(_teammate_view())
        self.assertIsInstance(move, Discard)
        self.assertEqual(2, move.card)

    def test_default_unhinted_chop_after_hint(self) -> None:
        """Opening/default chop: fine hint before default discard."""
        settings = create_standard_game_settings(3)
        player = DynamicRecommendation3P(0)
        player.set_game_settings(settings)
        common = _common(settings)
        player.set_common_view(
            CommonView(
                live_tokens=common.live_tokens,
                hint_tokens=common.hint_tokens - 1,
                cards_to_draw=common.cards_to_draw,
                cards_discarded=common.cards_discarded,
                cards_played=common.cards_played,
            )
        )
        for belief in player._hand_belief[0].slots:
            set_playability(belief, Playability.UNPLAYABLE)
        player._hand_belief[0].chop = 0
        player._hand_belief[0].chop_confirmed = False
        player._hand_belief[0].chop_hinted = False
        player._hand_belief[1].slots[4].playability = Playability.PLAYABLE
        move = player.play(_teammate_view())
        self.assertNotIsInstance(move, Discard)


class TestHintQualityGoodTrashPlusPrevPlay(unittest.TestCase):
    def test_trash_for_next_and_playable_for_prev_is_good(self) -> None:
        """Next discard useless + prev new playable ⇒ good (beats confirmed chop)."""
        settings = create_standard_game_settings(3)
        player = DynamicRecommendation3P(0)
        player.set_game_settings(settings)
        common = CommonView(
            live_tokens=3,
            hint_tokens=7,
            cards_to_draw=40,
            cards_discarded={},
            cards_played={Color.WHITE: Number.ONE},
        )
        player.set_common_view(common)
        for belief in player._hand_belief[0].slots:
            set_playability(belief, Playability.UNPLAYABLE)
        player._hand_belief[0].chop = 0
        player._hand_belief[0].chop_confirmed = True
        player._hand_belief[0].chop_hinted = True
        # Next (P2): useless W1 at chop; no playables.
        next_hand = [
            Card(Color.WHITE, Number.ONE),
            Card(Color.YELLOW, Number.FOUR),
            Card(Color.BLUE, Number.FOUR),
            Card(Color.GREEN, Number.FOUR),
            Card(Color.RED, Number.FOUR),
        ]
        # Prev (P3): playable R1 newest → play type 1.
        prev_hand = [
            Card(Color.YELLOW, Number.THREE),
            Card(Color.BLUE, Number.THREE),
            Card(Color.GREEN, Number.THREE),
            Card(Color.WHITE, Number.THREE),
            Card(Color.RED, Number.ONE),
        ]
        view = PlayerView(
            teammates={1: Hand(next_hand), 2: Hand(prev_hand)},
            own_hand_size=5,
        )
        self.assertTrue(
            dr._convention_hint_would_trash_next_and_play_prev(
                0, view, common, settings, player._hand_belief
            )
        )
        self.assertEqual(
            HintQuality.GOOD,
            dr._hint_quality(0, view, common, settings, player._hand_belief),
        )
        move = player.play(view)
        self.assertNotIsInstance(move, Discard)
        self.assertIn("trash for next + playable for prev", move.why())


class TestHintChopMatrix(unittest.TestCase):
    def test_matrix_covers_all_cells(self) -> None:
        for quality in HintQuality:
            for chop in ChopClass:
                self.assertIn((quality, chop), _HINT_CHOP_MATRIX)

    def test_matrix_prefers_hint_iff_expected(self) -> None:
        # Spec §9.3: good always hints; bad always discards; confirmed beats fine;
        # default still hints for fine.
        expect_hint = {
            (HintQuality.GOOD, ChopClass.CONFIRMED),
            (HintQuality.GOOD, ChopClass.DEFAULT),
            (HintQuality.FINE, ChopClass.DEFAULT),
        }
        for key, prefer_hint in _HINT_CHOP_MATRIX.items():
            self.assertEqual(key in expect_hint, prefer_hint, msg=key)

    def test_chop_class_partition(self) -> None:
        confirmed = fresh_hand_belief(5)
        confirmed.chop_confirmed = True
        confirmed.chop_hinted = True
        self.assertEqual(ChopClass.CONFIRMED, dr._chop_class(confirmed))
        default = fresh_hand_belief(5)
        self.assertEqual(ChopClass.DEFAULT, dr._chop_class(default))
        hinted_unconfirmed = fresh_hand_belief(5)
        hinted_unconfirmed.chop_hinted = True
        hinted_unconfirmed.chop_confirmed = False
        with self.assertRaises(AssertionError):
            dr._chop_class(hinted_unconfirmed)


class TestHintQualityBadDoubleMidrankDiscard(unittest.TestCase):
    def test_same_g3_discard_on_both_peers_is_bad(self) -> None:
        """Channel recommending both copies of a 3 for discard is bad (§9.2)."""
        settings = create_standard_game_settings(3)
        player = DynamicRecommendation3P(0)
        player.set_game_settings(settings)
        # Match game 33 T13 board shape: both peers' discard decode lands on G3.
        # Use opening blank belief so encode+decode stay on the same n_play boundary.
        common = CommonView(
            live_tokens=3,
            hint_tokens=7,
            cards_to_draw=40,
            cards_discarded={
                Color.RED: Suit({Number.ONE: 1}),
                Color.GREEN: Suit({Number.FOUR: 1}),
                Color.BLUE: Suit({Number.TWO: 1, Number.THREE: 1}),
            },
            cards_played={Color.WHITE: Number.TWO, Color.RED: Number.ONE, Color.GREEN: Number.ONE},
        )
        player.set_common_view(common)
        next_hand = [
            Card(Color.GREEN, Number.FIVE),
            Card(Color.GREEN, Number.THREE),
            Card(Color.BLUE, Number.TWO),
            Card(Color.RED, Number.THREE),
            Card(Color.WHITE, Number.TWO),
        ]
        prev_hand = [
            Card(Color.RED, Number.FIVE),
            Card(Color.GREEN, Number.THREE),
            Card(Color.GREEN, Number.FOUR),
            Card(Color.YELLOW, Number.TWO),
            Card(Color.YELLOW, Number.FIVE),
        ]
        view = PlayerView(teammates={1: Hand(next_hand), 2: Hand(prev_hand)}, own_hand_size=5)
        self.assertTrue(
            dr._convention_hint_would_cause_double_midrank_discard(
                0, view, common, settings, player._hand_belief
            )
        )
        self.assertEqual(
            HintQuality.BAD,
            dr._hint_quality(0, view, common, settings, player._hand_belief),
        )
        self.assertFalse(_HINT_CHOP_MATRIX[(HintQuality.BAD, ChopClass.DEFAULT)])
        move = player.play(view)
        self.assertIsInstance(move, Discard)

    def test_same_one_discard_is_not_bad(self) -> None:
        """Double discard of 1s is outside the mid-rank bad tier."""
        from unittest import mock

        settings = create_standard_game_settings(3)
        common = _common(settings)
        beliefs = [fresh_hand_belief(5) for _ in range(3)]
        filler = [Card(Color.BLUE, Number.FIVE)] * 5
        view = PlayerView(teammates={1: Hand(filler), 2: Hand(filler)}, own_hand_size=5)
        one = Card(Color.RED, Number.ONE)
        with mock.patch.object(
            dr,
            "_newly_decoded_discard_card_from_codes",
            side_effect=[one, one],
        ):
            self.assertFalse(
                dr._convention_hint_would_cause_double_midrank_discard(
                    0, view, common, settings, beliefs
                )
            )


class TestGuiChopConfirmed(unittest.TestCase):
    def test_chop_confirmed_flag(self) -> None:
        settings = create_standard_game_settings(3)
        player = DynamicRecommendation3P(0)
        player.set_game_settings(settings)
        self.assertEqual(0, player.get_gui_chop_slot(0))
        self.assertFalse(player.get_gui_chop_confirmed(0))
        player._hand_belief[0].chop_confirmed = True
        self.assertTrue(player.get_gui_chop_confirmed(0))


class TestDoubleDiscardGuard(unittest.TestCase):
    def test_peer_codes_are_independent_per_hand(self) -> None:
        """Channel peer codes use only that hand + public state (no cross-hand protect)."""
        settings = create_standard_game_settings(3)
        common = _common(settings)
        dup = Card(Color.YELLOW, Number.FOUR)
        alt = Card(Color.YELLOW, Number.TWO)
        next_hand = [
            dup,
            Card(Color.RED, Number.FIVE),
            Card(Color.WHITE, Number.FOUR),
            Card(Color.BLUE, Number.FIVE),
            Card(Color.GREEN, Number.FIVE),
        ]
        prev_hand = [
            dup,
            alt,
            Card(Color.WHITE, Number.FIVE),
            Card(Color.BLUE, Number.THREE),
            Card(Color.GREEN, Number.THREE),
        ]
        beliefs = [fresh_hand_belief(5) for _ in range(3)]
        view = PlayerView(
            teammates={1: Hand(next_hand), 2: Hand(prev_hand)},
            own_hand_size=5,
        )
        codes = dr._peer_codes_next_then_prev(0, view, common, settings, beliefs)
        self.assertEqual(
            dr._peer_code_for_hand(next_hand, beliefs[1], common, settings),
            codes[1],
        )
        self.assertEqual(
            dr._peer_code_for_hand(prev_hand, beliefs[2], common, settings),
            codes[2],
        )
        # Without cross-hand protect, prev prefers the higher-rank dispensable at chop.
        _code, prev_card = dr._encode_peer_code(prev_hand, beliefs[2], common, settings)
        self.assertEqual(dup, prev_card)
        self.assertEqual(_code, codes[2])

    def test_sticky_chop_encode_can_name_useless_beyond_leftmost_window(self) -> None:
        """Game 38 T04 shape: shared chop at slot 2 makes Y1 indicable; blank would not."""
        settings = create_standard_game_settings(3)
        common = CommonView(
            live_tokens=3,
            hint_tokens=8,
            cards_to_draw=40,
            cards_discarded={Color.BLUE: Suit({Number.FOUR: 1})},
            cards_played={Color.YELLOW: Number.ONE},
        )
        hand = [
            Card(Color.BLUE, Number.FOUR),
            Card(Color.WHITE, Number.FIVE),
            Card(Color.GREEN, Number.FIVE),
            Card(Color.RED, Number.THREE),
            Card(Color.YELLOW, Number.ONE),
        ]
        sticky = fresh_hand_belief(5)
        sticky.chop = 2
        sticky.chop_confirmed = True
        sticky.chop_hinted = True
        code, discard_card = dr._encode_peer_code(hand, sticky, common, settings)
        self.assertEqual(Card(Color.YELLOW, Number.ONE), discard_card)
        self.assertEqual(6, code)
        blank_code, blank_discard = dr._encode_peer_code(
            hand, fresh_hand_belief(5), common, settings
        )
        self.assertNotEqual(Card(Color.YELLOW, Number.ONE), blank_discard)
        self.assertNotEqual(code, blank_code)
        self.assertEqual(
            code,
            dr._peer_code_for_hand(hand, sticky, common, settings),
        )

    def test_critical_tiebreak_prefers_fewest_points_lost(self) -> None:
        """Game 95 T19 style: last B2 loses 4 points; B5/G5 lose 1 — prefer a 5."""
        from hanabi.core.card import Suit

        settings = create_standard_game_settings(3)
        common = CommonView(
            live_tokens=3,
            hint_tokens=8,
            cards_to_draw=40,
            cards_discarded={Color.BLUE: Suit({Number.TWO: 1})},
            cards_played={},
        )
        hand = [
            Card(Color.YELLOW, Number.TWO),
            Card(Color.GREEN, Number.TWO),
            Card(Color.BLUE, Number.FIVE),
            Card(Color.BLUE, Number.TWO),
            Card(Color.GREEN, Number.FIVE),
        ]
        self.assertEqual(CardKind.CRITICAL, common.card_kind(hand[2], settings))
        self.assertEqual(CardKind.CRITICAL, common.card_kind(hand[3], settings))
        self.assertEqual(CardKind.CRITICAL, common.card_kind(hand[4], settings))
        self.assertEqual(4, dr._critical_points_lost(hand[3], common, settings))
        self.assertEqual(1, dr._critical_points_lost(hand[2], common, settings))
        self.assertEqual(1, dr._critical_points_lost(hand[4], common, settings))
        s_b5 = dr._discard_option_score(hand, 2, common, settings)
        s_b2 = dr._discard_option_score(hand, 3, common, settings)
        s_g5 = dr._discard_option_score(hand, 4, common, settings)
        self.assertLess(s_b5, s_b2)
        self.assertLess(s_g5, s_b2)
        self.assertLess(s_b5, s_g5)  # same points + rank → older slot
        belief = fresh_hand_belief(5)
        # Keep only the three criticals on the discard chain (skip older trash via playable).
        set_playability(belief.slots[0], Playability.PLAYABLE)
        set_playability(belief.slots[1], Playability.PLAYABLE)
        belief.chop = 2
        code, slot = dr._pick_discard_code(hand, belief, common, settings)
        self.assertEqual(2, slot)
        self.assertEqual(0, code)

    def test_critical_points_lost_skips_already_dead_higher_ranks(self) -> None:
        """Both 4s gone ⇒ discarding last 3 loses only 1 (not 3+4+5)."""
        from hanabi.core.card import Suit

        settings = create_standard_game_settings(3)
        common = CommonView(
            live_tokens=3,
            hint_tokens=8,
            cards_to_draw=40,
            cards_discarded={Color.GREEN: Suit({Number.FOUR: 2, Number.THREE: 1})},
            cards_played={},
        )
        g3 = Card(Color.GREEN, Number.THREE)
        self.assertEqual(CardKind.CRITICAL, common.card_kind(g3, settings))
        self.assertEqual(1, dr._critical_points_lost(g3, common, settings))

    def test_critical_same_points_prefers_lower_rank(self) -> None:
        """Equal loss ⇒ discard lower rank to keep a 5 for hint-token bonus."""
        from hanabi.core.card import Suit

        settings = create_standard_game_settings(3)
        common = CommonView(
            live_tokens=3,
            hint_tokens=8,
            cards_to_draw=40,
            cards_discarded={Color.GREEN: Suit({Number.FOUR: 2, Number.THREE: 1})},
            cards_played={},
        )
        # G3 loses 1 (4/5 dead); B5 loses 1. Prefer G3 even if it is newer.
        hand = [
            Card(Color.BLUE, Number.FIVE),
            Card(Color.RED, Number.FIVE),
            Card(Color.YELLOW, Number.FIVE),
            Card(Color.WHITE, Number.FIVE),
            Card(Color.GREEN, Number.THREE),
        ]
        s_b5 = dr._discard_option_score(hand, 0, common, settings)
        s_g3 = dr._discard_option_score(hand, 4, common, settings)
        self.assertEqual(1, s_b5[1])
        self.assertEqual(1, s_g3[1])
        self.assertLess(s_g3, s_b5)

    def test_discard_chain_wraps_older_than_chop(self) -> None:
        hand = fresh_hand_belief(5)
        hand.chop = 3
        self.assertEqual([3, 4, 0, 1, 2], discard_chain(hand))

    def test_discard_chain_skips_identified_playables(self) -> None:
        """Playability.PLAYABLE slots are never discard candidates / code targets."""
        from hanabi.ai.dr_belief import discard_code_candidates

        hand = fresh_hand_belief(5)
        hand.chop = 0
        set_playability(hand.slots[1], Playability.PLAYABLE)
        set_playability(hand.slots[3], Playability.PLAYABLE)
        self.assertEqual([0, 2, 4], discard_chain(hand))
        # N_play = 3 unknowns → m = 5, but only 3 discard candidates exist.
        self.assertEqual(3, n_play(hand))
        self.assertEqual([0, 2, 4], discard_code_candidates(hand))

    def test_first_m_candidates_include_useless_before_wrap(self) -> None:
        """Game 48 T07 style: chop W3 → candidates W3/Y2/W1; prefer useless W1."""
        settings = create_standard_game_settings(3)
        common = CommonView(
            live_tokens=3,
            hint_tokens=8,
            cards_to_draw=40,
            cards_discarded={},
            cards_played={
                Color.WHITE: Number.ONE,
                Color.RED: Number.ONE,
                Color.GREEN: Number.ONE,
            },
        )
        hand = [
            Card(Color.BLUE, Number.TWO),
            Card(Color.YELLOW, Number.FIVE),
            Card(Color.WHITE, Number.THREE),
            Card(Color.YELLOW, Number.TWO),
            Card(Color.WHITE, Number.ONE),
        ]
        self.assertEqual(CardKind.USELESS, common.card_kind(hand[4], settings))
        belief = fresh_hand_belief(5)
        belief.chop = 2
        from hanabi.ai.dr_belief import discard_code_candidates

        self.assertEqual([2, 3, 4], discard_code_candidates(belief))
        code, slot = dr._pick_discard_code(hand, belief, common, settings)
        self.assertEqual(4, slot)
        self.assertEqual(hand[4], Card(Color.WHITE, Number.ONE))
        self.assertEqual(6, code)

    def test_in_hand_duplicate_beats_lone_dispensable(self) -> None:
        settings = create_standard_game_settings(3)
        common = _common(settings)
        hand = [
            Card(Color.GREEN, Number.FOUR),
            Card(Color.GREEN, Number.FOUR),
            Card(Color.YELLOW, Number.TWO),
            Card(Color.WHITE, Number.FIVE),
            Card(Color.RED, Number.FIVE),
        ]
        self.assertEqual(CardKind.DISPENSABLE, common.card_kind(hand[0], settings))
        self.assertEqual(CardKind.DISPENSABLE, common.card_kind(hand[2], settings))
        s_dup = dr._discard_option_score(hand, 0, common, settings)
        s_lone = dr._discard_option_score(hand, 2, common, settings)
        self.assertLess(s_dup, s_lone)

    def test_in_hand_duplicate_prefers_newest_copy(self) -> None:
        """Game 38 T01 style: two B4s → recommend the rightmost so chop can pivot right."""
        settings = create_standard_game_settings(3)
        common = _common(settings)
        hand = [
            Card(Color.BLUE, Number.FOUR),
            Card(Color.WHITE, Number.FIVE),
            Card(Color.BLUE, Number.FOUR),
            Card(Color.GREEN, Number.FIVE),
            Card(Color.RED, Number.THREE),
        ]
        s_left = dr._discard_option_score(hand, 0, common, settings)
        s_right = dr._discard_option_score(hand, 2, common, settings)
        self.assertLess(s_right, s_left)
        belief = fresh_hand_belief(5)
        code, slot = dr._pick_discard_code(hand, belief, common, settings)
        self.assertEqual(2, slot)
        self.assertEqual(6, code)

    def test_useless_beats_in_hand_duplicate(self) -> None:
        settings = create_standard_game_settings(3)
        common = CommonView(
            live_tokens=3,
            hint_tokens=8,
            cards_to_draw=40,
            cards_discarded={},
            cards_played={Color.BLUE: Number.THREE},  # B2 dead
        )
        hand = [
            Card(Color.BLUE, Number.TWO),  # useless
            Card(Color.GREEN, Number.FOUR),
            Card(Color.GREEN, Number.FOUR),
            Card(Color.WHITE, Number.FIVE),
            Card(Color.RED, Number.FIVE),
        ]
        self.assertEqual(CardKind.USELESS, common.card_kind(hand[0], settings))
        s_useless = dr._discard_option_score(hand, 0, common, settings)
        s_dup = dr._discard_option_score(hand, 1, common, settings)
        self.assertLess(s_useless, s_dup)

    def test_standing_chop_does_not_cross_protect_in_peer_codes(self) -> None:
        """Peer codes ignore the other seat's chop (local encode only)."""
        settings = create_standard_game_settings(3)
        dup = Card(Color.BLUE, Number.FOUR)
        alt = Card(Color.YELLOW, Number.FOUR)
        next_hand = [
            dup,  # already confirmed chop
            Card(Color.YELLOW, Number.FIVE),
            Card(Color.WHITE, Number.FOUR),
            Card(Color.WHITE, Number.THREE),
            Card(Color.RED, Number.FOUR),  # playable → this hint encodes play for next
        ]
        prev_hand = [
            dup,
            alt,
            Card(Color.WHITE, Number.FIVE),
            Card(Color.BLUE, Number.FIVE),
            Card(Color.GREEN, Number.FIVE),
        ]
        common = CommonView(
            live_tokens=3,
            hint_tokens=8,
            cards_to_draw=40,
            cards_discarded={},
            cards_played={Color.RED: Number.THREE},
        )
        self.assertEqual(CardKind.PLAYABLE, common.card_kind(next_hand[4], settings))
        beliefs = [fresh_hand_belief(5) for _ in range(3)]
        beliefs[1].chop = 0
        beliefs[1].chop_confirmed = True
        beliefs[1].chop_hinted = True
        view = PlayerView(
            teammates={1: Hand(next_hand), 2: Hand(prev_hand)},
            own_hand_size=5,
        )
        codes = dr._peer_codes_next_then_prev(0, view, common, settings, beliefs)
        self.assertEqual(1, codes[1])
        _code, card = dr._encode_peer_code(prev_hand, beliefs[2], common, settings)
        self.assertEqual(dup, card)
        self.assertEqual(_code, codes[2])


class TestIndependentOwnDecode(unittest.TestCase):
    def test_decoders_match_public_decode_hinter_updates_teammates_only(self) -> None:
        """Every observer updates both non-hinter hands; hinter never writes own hand."""
        from hanabi.core.moves import ColorHint

        settings = create_standard_game_settings(3)
        common = _common(settings)
        players = [DynamicRecommendation3P(i) for i in range(3)]
        for p in players:
            p.set_game_settings(settings)
            p.set_common_view(common)
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
            dr._peer_code_for_hand(hand_p1, players[0]._hand_belief[1], common, settings)
            + dr._peer_code_for_hand(hand_p2, players[0]._hand_belief[2], common, settings)
        ) % 8
        hint = dr._build_hint_for_encoded(0, views[0], enc)
        self.assertIsNotNone(hint)
        own_before = [copy_hand_belief(players[seat]._hand_belief[seat]) for seat in range(3)]
        hinter_own_before = copy_hand_belief(players[0]._hand_belief[0])
        for player, view in zip(players, views):
            if isinstance(hint, NumberHint):
                player.observe_number_hint_move(0, hint, view)
            else:
                assert isinstance(hint, ColorHint)
                player.observe_color_hint_move(0, hint, view)
        self.assertEqual(hinter_own_before, players[0]._hand_belief[0])
        dr.assert_independent_own_decode_matches(players, 0, hint, views, own_before)
        dr.assert_public_non_hinter_rows_agree(players, 0, hint)

    def test_reopen_keeps_chop_fields(self) -> None:
        """Reopen restores playability only; chop flags stay (§8.1)."""
        from hanabi.ai.dr_belief import reopen_unplayable

        third = fresh_hand_belief(5)
        apply_decoded_value(third, 6)
        self.assertTrue(third.chop_hinted)
        self.assertTrue(third.chop_confirmed)
        reopen_unplayable([third])
        self.assertTrue(third.chop_hinted)
        self.assertTrue(third.chop_confirmed)
        self.assertEqual(2, third.chop)

        confirmed = fresh_hand_belief(5)
        apply_decoded_value(confirmed, 0)
        self.assertTrue(confirmed.chop_confirmed)
        self.assertTrue(confirmed.chop_hinted)
        reopen_unplayable([confirmed])
        self.assertTrue(confirmed.chop_confirmed)
        self.assertTrue(confirmed.chop_hinted)


if __name__ == "__main__":
    unittest.main()
