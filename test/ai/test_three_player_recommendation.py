"""Tests for :mod:`hanabi.ai.three_player_recommendation`."""

import unittest

from hanabi.ai.three_player_recommendation import (
    NUM_CHANNELS,
    NUM_PLAYERS_FOR_SIMPLE_RECOMMENDATION,
    ThreePlayerRecommendationPlayer,
    _build_channel_hint,
    _infer_channel_id,
)
from hanabi.core.card import Card
from hanabi.core.enums import Color, Number
from hanabi.core.game import CommonView, Hand, PlayerView, create_standard_game_settings
from hanabi.core.moves import ColorHint, NumberHint, Play


class TestThreePlayerRecommendationSettings(unittest.TestCase):
    def test_supports_only_three_players(self) -> None:
        s3 = create_standard_game_settings(3)
        s5 = create_standard_game_settings(5)
        self.assertTrue(ThreePlayerRecommendationPlayer.supports_game_settings(s3))
        self.assertFalse(ThreePlayerRecommendationPlayer.supports_game_settings(s5))

    def test_num_players_constant(self) -> None:
        self.assertEqual(3, NUM_PLAYERS_FOR_SIMPLE_RECOMMENDATION)
        self.assertEqual(8, NUM_CHANNELS)


class TestHintScoring(unittest.TestCase):
    def test_last_resort_plays_c1(self) -> None:
        settings = create_standard_game_settings(3)
        view = PlayerView(teammates={}, own_hand_size=5)
        player = ThreePlayerRecommendationPlayer(0)
        player.set_game_settings(settings)
        player.set_common_view(CommonView(
            live_tokens=settings.max_live_tokens,
            hint_tokens=settings.max_hint_tokens,
            cards_to_draw=40,
            cards_discarded={},
            cards_played={},
        ))
        move = player._try_play_c1_as_last_resort(view)
        self.assertIsInstance(move, Play)
        self.assertEqual(0, move.card)

    def test_strong_hint_blocked_when_peers_already_tracked(self) -> None:
        settings = create_standard_game_settings(3)
        hand = [Card(Color.RED, Number.ONE)] * 5
        view = PlayerView(
            teammates={1: Hand(hand), 2: Hand(hand)},
            own_hand_size=5,
        )
        common = CommonView(
            live_tokens=settings.max_live_tokens,
            hint_tokens=settings.max_hint_tokens,
            cards_to_draw=40,
            cards_discarded={},
            cards_played={},
        )
        player = ThreePlayerRecommendationPlayer(0)
        player.set_game_settings(settings)
        player.set_common_view(common)
        for seat in (1, 2):
            player._set_recommendation_for_seat(
                seat, player._get_recommendation_for_hand(hand, common, settings)
            )
        score = player._score_candidate_hint(view)
        self.assertEqual(0, score.total())
        self.assertIsNone(player._try_strong_hint(view))

    def test_latest_recommendation_replaces_instead_of_queueing(self) -> None:
        player = ThreePlayerRecommendationPlayer(0)
        player._set_recommendation_for_seat(0, 2)
        player._set_recommendation_for_seat(0, 4)
        self.assertEqual({0: 4}, player._latest_recommendation_by_seat)

    def test_code_six_save_checks_only_the_discard_it_instructs(self) -> None:
        settings = create_standard_game_settings(3)
        common = CommonView(
            live_tokens=settings.max_live_tokens,
            hint_tokens=settings.max_hint_tokens,
            cards_to_draw=40,
            cards_discarded={},
            cards_played={Color.BLUE: Number.ONE},
        )
        safe_c1_critical_c2 = [
            Card(Color.GREEN, Number.THREE),
            Card(Color.RED, Number.FIVE),
            Card(Color.YELLOW, Number.THREE),
            Card(Color.WHITE, Number.THREE),
            Card(Color.BLUE, Number.ONE),
        ]
        unchanged_peer = [Card(Color.GREEN, Number.THREE)] * 5
        view = PlayerView(
            teammates={1: Hand(safe_c1_critical_c2), 2: Hand(unchanged_peer)},
            own_hand_size=5,
        )
        player = ThreePlayerRecommendationPlayer(0)
        player.set_game_settings(settings)
        player.set_common_view(common)
        player._set_recommendation_for_seat(1, 6)
        player._set_recommendation_for_seat(2, 0)

        score = player._score_candidate_hint(view)

        self.assertEqual(0, score.saves)
        self.assertEqual(1, score.flips)

    def test_code_six_save_detects_critical_in_instructed_discard_slot(self) -> None:
        settings = create_standard_game_settings(3)
        common = CommonView(
            live_tokens=settings.max_live_tokens,
            hint_tokens=settings.max_hint_tokens,
            cards_to_draw=40,
            cards_discarded={},
            cards_played={Color.BLUE: Number.ONE},
        )
        critical_c1 = [
            Card(Color.RED, Number.FIVE),
            Card(Color.GREEN, Number.THREE),
            Card(Color.YELLOW, Number.THREE),
            Card(Color.WHITE, Number.THREE),
            Card(Color.BLUE, Number.ONE),
        ]
        unchanged_peer = [Card(Color.GREEN, Number.THREE)] * 5
        view = PlayerView(
            teammates={1: Hand(critical_c1), 2: Hand(unchanged_peer)},
            own_hand_size=5,
        )
        player = ThreePlayerRecommendationPlayer(0)
        player.set_game_settings(settings)
        player.set_common_view(common)
        player._set_recommendation_for_seat(1, 6)
        player._set_recommendation_for_seat(2, 0)

        self.assertEqual(1, player._score_candidate_hint(view).saves)


class TestChannelInference(unittest.TestCase):
    """Hint direction and target map to channel id 0..7."""

    def test_left_number_next_is_channel_0(self) -> None:
        hand = [Card(Color.RED, Number.ONE), Card(Color.RED, Number.TWO)]
        move = NumberHint(teammate=1, cards=[0], number=Number.ONE)
        self.assertEqual(0, _infer_channel_id(0, 1, move, hand))

    def test_right_color_next_is_channel_6(self) -> None:
        """Right color to the next teammate is channel 6."""
        hand = [Card(Color.WHITE, Number.TWO), Card(Color.GREEN, Number.THREE)]
        move = ColorHint(teammate=0, cards=[1], color=Color.GREEN)
        self.assertEqual(6, _infer_channel_id(2, 0, move, hand))

    def test_right_color_previous_is_channel_7(self) -> None:
        hand = [Card(Color.WHITE, Number.TWO), Card(Color.GREEN, Number.THREE)]
        move = ColorHint(teammate=2, cards=[1], color=Color.GREEN)
        self.assertEqual(7, _infer_channel_id(0, 2, move, hand))

    def test_public_right_color_previous_is_channel_7(self) -> None:
        move = ColorHint(teammate=2, cards=[1], color=Color.GREEN)
        self.assertEqual(7, _infer_channel_id(0, 2, move, None))

    def test_left_number_rank_at_slot0_user_example(self) -> None:
        """``R2 Y3 B4 R1 Y2`` → left number is 2’s on slots ``0`` and ``4``."""
        hand = [
            Card(Color.RED, Number.TWO),
            Card(Color.YELLOW, Number.THREE),
            Card(Color.BLUE, Number.FOUR),
            Card(Color.RED, Number.ONE),
            Card(Color.YELLOW, Number.TWO),
        ]
        move = NumberHint(teammate=1, cards=[0, 4], number=Number.TWO)
        self.assertEqual(0, _infer_channel_id(0, 1, move, hand))

    def test_right_number_min_rank_after_slot0_user_example(self) -> None:
        """Same hand → right number is 1’s (min rank among slots ``1``–``4``)."""
        hand = [
            Card(Color.RED, Number.TWO),
            Card(Color.YELLOW, Number.THREE),
            Card(Color.BLUE, Number.FOUR),
            Card(Color.RED, Number.ONE),
            Card(Color.YELLOW, Number.TWO),
        ]
        move = NumberHint(teammate=1, cards=[3], number=Number.ONE)
        self.assertEqual(4, _infer_channel_id(0, 1, move, hand))

    def test_public_number_next_no_index0_aligns_with_right_number(self) -> None:
        move = NumberHint(teammate=1, cards=[1, 2], number=Number.TWO)
        self.assertEqual(4, _infer_channel_id(0, 1, move, None))

    def test_all_eight_channels_build_and_round_trip(self) -> None:
        hand = [
            Card(Color.RED, Number.ONE),
            Card(Color.BLUE, Number.TWO),
            Card(Color.GREEN, Number.THREE),
            Card(Color.YELLOW, Number.FOUR),
            Card(Color.WHITE, Number.FIVE),
        ]
        view = PlayerView(teammates={1: Hand(hand), 2: Hand(hand)}, own_hand_size=5)
        for channel in range(8):
            with self.subTest(channel=channel):
                move = _build_channel_hint(0, view, channel)
                self.assertIsNotNone(move)
                self.assertEqual(channel, _infer_channel_id(0, move.teammate, move, hand))


class TestSimpleRecommendationSmoke(unittest.TestCase):
    def test_code_six_gui_marks_the_same_non_chop_discard_as_play_logic(self) -> None:
        player = ThreePlayerRecommendationPlayer(0)
        player._set_recommendation_for_seat(0, 6)
        view = PlayerView(teammates={}, own_hand_size=5)
        self.assertEqual({0: "discard"}, player.get_gui_recommendation_by_slot(view))

    def test_play_returns_legal_move_three_player(self) -> None:
        settings = create_standard_game_settings(3)
        view = PlayerView(
            teammates={
                1: Hand([Card(Color.RED, Number.ONE)] * 5),
                2: Hand([Card(Color.BLUE, Number.TWO)] * 5),
            },
            own_hand_size=5,
        )
        common = CommonView(
            live_tokens=settings.max_live_tokens,
            hint_tokens=settings.max_hint_tokens,
            cards_to_draw=40,
            cards_discarded={},
            cards_played={},
        )
        player = ThreePlayerRecommendationPlayer(0)
        player.set_game_settings(settings)
        player.set_common_view(common)
        move = player.play(view)
        self.assertTrue(player.is_move_legal(view, move))


if __name__ == "__main__":
    unittest.main()
