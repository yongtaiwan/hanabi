"""Tests for :mod:`hanabi.ai.five_player_recommendation`."""

import unittest

from hanabi.ai.five_player_recommendation import (
    CODE_DISPENSABLE_DISCARD_OFFSET,
    CODE_USELESS_DISCARD_OFFSET,
    DEFAULT_PLAY_FOLLOW_GATE,
    NUM_CHANNELS,
    NUM_PLAYERS_FOR_FIVE_PLAYER_RECOMMENDATION,
    FivePlayerRecommendationPlayer,
    HintThresholds,
    PlayFollowGate,
    _RecommendationQueue,
    _HintScore,
    _infer_channel_id,
    _normalize_decoded_code,
    _remap_code_after_removal,
)
from hanabi.core.moves import Discard, Play, ColorHint, NumberHint
from hanabi.core.card import Card
from hanabi.core.enums import Color, Number
from hanabi.core.game import CommonView, Hand, PlayerView, create_standard_game_settings


class TestHintThresholds(unittest.TestCase):
    def test_baseline_strong_gate(self) -> None:
        th = HintThresholds()
        self.assertTrue(th.passes_strong(_HintScore(2, 0, 0, 0, 0)))
        self.assertTrue(th.passes_strong(_HintScore(0, 1, 0, 0, 0)))
        self.assertTrue(th.passes_strong(_HintScore(0, 0, 0, 1, 0)))
        self.assertTrue(th.passes_strong(_HintScore(1, 0, 1, 0, 0)))  # comb>=2
        self.assertFalse(th.passes_strong(_HintScore(1, 0, 0, 0, 0)))

    def test_medium_gate(self) -> None:
        th = HintThresholds()
        self.assertTrue(th.passes_medium(_HintScore(0, 0, 1, 0, 0)))
        self.assertFalse(th.passes_medium(_HintScore(1, 0, 0, 0, 0)))
        self.assertFalse(th.passes_medium(_HintScore(0, 1, 0, 0, 0)))

    def test_weak_gate(self) -> None:
        th = HintThresholds()
        self.assertFalse(th.passes_weak(_HintScore(0, 0, 0, 0, 0)))
        self.assertTrue(th.passes_weak(_HintScore(0, 0, 0, 0, 1)))


class TestFivePlayerRecommendationSettings(unittest.TestCase):
    def test_supports_only_five_players(self) -> None:
        s4 = create_standard_game_settings(4)
        s5 = create_standard_game_settings(5)
        self.assertFalse(FivePlayerRecommendationPlayer.supports_game_settings(s4))
        self.assertTrue(FivePlayerRecommendationPlayer.supports_game_settings(s5))

    def test_constants(self) -> None:
        self.assertEqual(5, NUM_PLAYERS_FOR_FIVE_PLAYER_RECOMMENDATION)
        self.assertEqual(16, NUM_CHANNELS)


class TestChannelInference(unittest.TestCase):
    """Hint shape maps to channel id 0..15 (4 hint shapes × 4 directions)."""

    def test_left_number_to_next_is_channel_0(self) -> None:
        hand = [Card(Color.RED, Number.ONE), Card(Color.RED, Number.TWO)]
        move = NumberHint(teammate=1, cards=[0], number=Number.ONE)
        self.assertEqual(0, _infer_channel_id(0, 1, move, hand))

    def test_left_number_to_next_plus_1_is_channel_1(self) -> None:
        hand = [Card(Color.RED, Number.ONE), Card(Color.RED, Number.TWO)]
        move = NumberHint(teammate=2, cards=[0], number=Number.ONE)
        self.assertEqual(1, _infer_channel_id(0, 2, move, hand))

    def test_left_number_to_previous_is_channel_3(self) -> None:
        hand = [Card(Color.RED, Number.ONE), Card(Color.RED, Number.TWO)]
        move = NumberHint(teammate=4, cards=[0], number=Number.ONE)
        self.assertEqual(3, _infer_channel_id(0, 4, move, hand))

    def test_left_color_to_next_is_channel_4(self) -> None:
        hand = [Card(Color.RED, Number.ONE), Card(Color.BLUE, Number.TWO)]
        move = ColorHint(teammate=1, cards=[0], color=Color.RED)
        self.assertEqual(4, _infer_channel_id(0, 1, move, hand))

    def test_right_number_to_next_is_channel_8(self) -> None:
        hand = [
            Card(Color.RED, Number.TWO),
            Card(Color.YELLOW, Number.THREE),
            Card(Color.BLUE, Number.FOUR),
            Card(Color.RED, Number.ONE),
        ]
        move = NumberHint(teammate=1, cards=[3], number=Number.ONE)
        self.assertEqual(8, _infer_channel_id(0, 1, move, hand))

    def test_right_color_to_next_plus_2_is_channel_14(self) -> None:
        hand = [
            Card(Color.RED, Number.ONE),
            Card(Color.BLUE, Number.TWO),
            Card(Color.GREEN, Number.THREE),
            Card(Color.YELLOW, Number.FOUR),
        ]
        move = ColorHint(teammate=3, cards=[3], color=Color.YELLOW)
        self.assertEqual(14, _infer_channel_id(0, 3, move, hand))

    def test_public_number_no_index0_is_right_number(self) -> None:
        move = NumberHint(teammate=1, cards=[1, 2], number=Number.TWO)
        self.assertEqual(8, _infer_channel_id(0, 1, move, None))

    def test_public_color_no_index0_is_right_color(self) -> None:
        move = ColorHint(teammate=2, cards=[1, 2], color=Color.GREEN)
        self.assertEqual(13, _infer_channel_id(0, 2, move, None))


class TestNormalizeDecodedCode(unittest.TestCase):
    def test_actionable_codes_unchanged(self) -> None:
        for code in range(13):
            self.assertEqual(code, _normalize_decoded_code(code))

    def test_leftover_mod16_values_map_to_zero(self) -> None:
        for code in range(13, 16):
            self.assertEqual(0, _normalize_decoded_code(code))


class TestPeerDiscardCodes(unittest.TestCase):
    """USELESS vs DISPENSABLE peer codes use separate code bands (5–8 vs 9–12)."""

    def test_useless_hand_gets_low_discard_band(self) -> None:
        settings = create_standard_game_settings(5)
        common = CommonView(
            live_tokens=settings.max_live_tokens,
            hint_tokens=3,
            cards_to_draw=40,
            cards_discarded={},
            cards_played={Color.RED: Number.ONE},
        )
        hand = [
            Card(Color.BLUE, Number.TWO),
            Card(Color.BLUE, Number.THREE),
            Card(Color.BLUE, Number.FOUR),
            Card(Color.RED, Number.ONE),
        ]
        code = FivePlayerRecommendationPlayer._rec_useless_slot(hand, common, settings)
        self.assertEqual(CODE_USELESS_DISCARD_OFFSET + 3, code)

    def test_dispensable_only_hand_gets_high_discard_band(self) -> None:
        settings = create_standard_game_settings(5)
        common = CommonView(
            live_tokens=settings.max_live_tokens,
            hint_tokens=3,
            cards_to_draw=40,
            cards_discarded={},
            cards_played={Color.RED: Number.ONE},
        )
        hand = [
            Card(Color.BLUE, Number.TWO),
            Card(Color.BLUE, Number.THREE),
            Card(Color.BLUE, Number.FOUR),
            Card(Color.BLUE, Number.TWO),
        ]
        code = FivePlayerRecommendationPlayer._rec_dispensable_slot(hand, common, settings)
        self.assertEqual(CODE_DISPENSABLE_DISCARD_OFFSET + 3, code)

    def test_remap_dispensable_code_after_removal(self) -> None:
        self.assertEqual(10, _remap_code_after_removal(11, 0))


class TestRecommendationQueue(unittest.TestCase):
    def test_remap_shifts_higher_slots_down(self) -> None:
        self.assertEqual(2, _remap_code_after_removal(3, 0))
        self.assertEqual(6, _remap_code_after_removal(7, 0))

    def test_set_latest_replaces_prior_recommendation(self) -> None:
        queue = _RecommendationQueue()
        queue.set_latest(2)
        queue.set_latest(6)
        self.assertEqual([6], queue.codes())

    def test_default_play_follow_gate_is_paper(self) -> None:
        self.assertEqual(PlayFollowGate.paper(), DEFAULT_PLAY_FOLLOW_GATE)

    def test_gated_play_does_not_follow(self) -> None:
        settings = create_standard_game_settings(5)
        view = PlayerView(
            teammates={
                1: Hand([Card(Color.RED, Number.ONE)] * 4),
                2: Hand([Card(Color.BLUE, Number.TWO)] * 4),
                3: Hand([Card(Color.GREEN, Number.THREE)] * 4),
                4: Hand([Card(Color.YELLOW, Number.FOUR)] * 4),
            },
            own_hand_size=4,
        )
        common = CommonView(
            live_tokens=settings.max_live_tokens,
            hint_tokens=settings.max_hint_tokens,
            cards_to_draw=40,
            cards_discarded={},
            cards_played={},
        )
        player = FivePlayerRecommendationPlayer(0)
        player.set_game_settings(settings)
        player.set_common_view(common)
        player._my_recommendation_queue.set_latest(2)
        player._plays_since_hint = 2
        errors = settings.max_live_tokens - common.live_tokens
        self.assertIsNone(player._try_follow_play_recommendation(view, player._plays_since_hint, errors))
        self.assertEqual([2], player._my_recommendation_queue.codes())

    def test_loose_gate_follows_after_two_plays_with_one_error(self) -> None:
        """Legacy loose gate (not default): ``ps==2`` still follows when ``errors < 2``."""
        settings = create_standard_game_settings(5)
        view = PlayerView(
            teammates={
                1: Hand([Card(Color.RED, Number.ONE)] * 4),
                2: Hand([Card(Color.BLUE, Number.TWO)] * 4),
                3: Hand([Card(Color.GREEN, Number.THREE)] * 4),
                4: Hand([Card(Color.YELLOW, Number.FOUR)] * 4),
            },
            own_hand_size=4,
        )
        common = CommonView(
            live_tokens=settings.max_live_tokens - 1,
            hint_tokens=settings.max_hint_tokens,
            cards_to_draw=40,
            cards_discarded={},
            cards_played={},
        )
        player = FivePlayerRecommendationPlayer(0, play_follow_gate=PlayFollowGate())
        player.set_game_settings(settings)
        player.set_common_view(common)
        player._my_recommendation_queue.set_latest(2)
        player._plays_since_hint = 2
        errors = settings.max_live_tokens - common.live_tokens
        move = player._try_follow_play_recommendation(view, player._plays_since_hint, errors)
        self.assertIsInstance(move, Play)
        self.assertEqual([], player._my_recommendation_queue.codes())

    def test_follow_dispensable_discard(self) -> None:
        settings = create_standard_game_settings(5)
        view = PlayerView(
            teammates={
                1: Hand([Card(Color.RED, Number.ONE)] * 4),
                2: Hand([Card(Color.BLUE, Number.TWO)] * 4),
                3: Hand([Card(Color.GREEN, Number.THREE)] * 4),
                4: Hand([Card(Color.YELLOW, Number.FOUR)] * 4),
            },
            own_hand_size=4,
        )
        common = CommonView(
            live_tokens=settings.max_live_tokens,
            hint_tokens=settings.max_hint_tokens - 1,
            cards_to_draw=40,
            cards_discarded={},
            cards_played={},
        )
        player = FivePlayerRecommendationPlayer(0)
        player.set_game_settings(settings)
        player.set_common_view(common)
        player._my_recommendation_queue.set_latest(CODE_DISPENSABLE_DISCARD_OFFSET + 2)
        move = player._try_follow_dispensable_discard_recommendation(view)
        self.assertIsInstance(move, Discard)
        self.assertEqual(2, move.card)

    def test_get_gui_recommendation_by_slot_maps_queue(self) -> None:
        settings = create_standard_game_settings(5)
        view = PlayerView(
            teammates={
                1: Hand([Card(Color.RED, Number.ONE)] * 4),
                2: Hand([Card(Color.BLUE, Number.TWO)] * 4),
                3: Hand([Card(Color.GREEN, Number.THREE)] * 4),
                4: Hand([Card(Color.YELLOW, Number.FOUR)] * 4),
            },
            own_hand_size=4,
        )
        common = CommonView(
            live_tokens=settings.max_live_tokens,
            hint_tokens=settings.max_hint_tokens - 1,
            cards_to_draw=40,
            cards_discarded={},
            cards_played={},
        )
        player = FivePlayerRecommendationPlayer(0)
        player.set_game_settings(settings)
        player.set_common_view(common)
        player._my_recommendation_queue.set_latest(7)
        self.assertEqual({2: "discard"}, player.get_gui_recommendation_by_slot(view))


class TestMiniRecommendationSmoke(unittest.TestCase):
    def test_play_returns_legal_move_five_player(self) -> None:
        settings = create_standard_game_settings(5)
        view = PlayerView(
            teammates={
                1: Hand([Card(Color.RED, Number.ONE)] * 4),
                2: Hand([Card(Color.BLUE, Number.TWO)] * 4),
                3: Hand([Card(Color.GREEN, Number.THREE)] * 4),
                4: Hand([Card(Color.YELLOW, Number.FOUR)] * 4),
            },
            own_hand_size=4,
        )
        common = CommonView(
            live_tokens=settings.max_live_tokens,
            hint_tokens=settings.max_hint_tokens,
            cards_to_draw=40,
            cards_discarded={},
            cards_played={},
        )
        player = FivePlayerRecommendationPlayer(0)
        player.set_game_settings(settings)
        player.set_common_view(common)
        move = player.play(view)
        self.assertTrue(player.is_move_legal(view, move))


if __name__ == "__main__":
    unittest.main()
