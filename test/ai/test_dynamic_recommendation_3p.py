"""Tests for :mod:`hanabi.ai.dynamic_recommendation_3p` and :mod:`hanabi.ai.dr_belief`."""

from __future__ import annotations

import unittest

from hanabi.ai import dynamic_recommendation_3p as dr
from hanabi.ai.dr_belief import (
    Playability,
    apply_decoded_value,
    discard_types_for_n_play,
    fresh_hand_belief,
    indicable_discard_options,
    n_play,
    set_playability,
)
from hanabi.ai.dynamic_recommendation_3p import DynamicRecommendation3P, HintSlotShape
from hanabi.core.card import Card
from hanabi.core.enums import Color, Number
from hanabi.core.game import CommonView, Hand, PlayerView, create_standard_game_settings
from hanabi.core.moves import Discard, Play


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

    def test_catch_all_moves_chop_unconfirmed(self) -> None:
        hand = fresh_hand_belief(5)
        apply_decoded_value(hand, 6)  # catch-all when N_play=5; R={2,3,4}
        self.assertEqual(2, hand.chop)
        self.assertFalse(hand.chop_confirmed)

    def test_catch_all_confirmed_when_remainder_singleton(self) -> None:
        # N_play=3 → D=[0,7,6,5,4]; chain length 5; catch-all remainder = chain[4:] = {4}.
        hand = fresh_hand_belief(5)
        set_playability(hand.slots[0], Playability.UNPLAYABLE)
        set_playability(hand.slots[1], Playability.UNPLAYABLE)
        self.assertEqual(3, n_play(hand))
        apply_decoded_value(hand, 4)
        self.assertEqual(4, hand.chop)
        self.assertTrue(hand.chop_confirmed)


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
        self.assertFalse(opts[2][2])


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
        code = dr._encode_peer_code(hand, belief, common, settings)
        self.assertEqual(1, code)  # newest playable → type 1


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
        # Step-2 must not fire: next seat already has a playable.
        player._hand_belief[1].slots[4].playability = Playability.PLAYABLE
        move = player.play(_teammate_view())
        self.assertIsInstance(move, Discard)
        self.assertEqual(0, move.card)


class TestGuiChopConfirmed(unittest.TestCase):
    def test_chop_confirmed_flag(self) -> None:
        settings = create_standard_game_settings(3)
        player = DynamicRecommendation3P(0)
        player.set_game_settings(settings)
        self.assertEqual(0, player.get_gui_chop_slot(0))
        self.assertFalse(player.get_gui_chop_confirmed(0))
        player._hand_belief[0].chop_confirmed = True
        self.assertTrue(player.get_gui_chop_confirmed(0))


class TestBeliefAlign(unittest.TestCase):
    def test_align_after_hint(self) -> None:
        settings = create_standard_game_settings(3)
        players = [DynamicRecommendation3P(i) for i in range(3)]
        for p in players:
            p.set_game_settings(settings)
        apply_decoded_value(players[0]._hand_belief[1], 0)
        dr.propagate_convention_belief_from_hinter(players, 0)
        dr.assert_convention_beliefs_in_sync(players)
        self.assertTrue(players[1]._hand_belief[1].chop_confirmed)


if __name__ == "__main__":
    unittest.main()
