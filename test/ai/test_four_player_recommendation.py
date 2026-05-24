"""Tests for :mod:`hanabi.ai.four_player_recommendation`."""

import unittest

from hanabi.ai.four_player_recommendation import (
    NUM_CHANNELS,
    NUM_PLAYERS_FOR_FOUR_PLAYER_RECOMMENDATION,
    FourPlayerRecommendationPlayer,
    _infer_channel_id,
)
from hanabi.core.card import Card
from hanabi.core.enums import Color, Number
from hanabi.core.game import CommonView, Hand, PlayerView, create_standard_game_settings
from hanabi.core.moves import ColorHint, NumberHint


class TestFourPlayerRecommendationSettings(unittest.TestCase):
    def test_supports_only_four_players(self) -> None:
        s3 = create_standard_game_settings(3)
        s4 = create_standard_game_settings(4)
        s5 = create_standard_game_settings(5)
        self.assertFalse(FourPlayerRecommendationPlayer.supports_game_settings(s3))
        self.assertTrue(FourPlayerRecommendationPlayer.supports_game_settings(s4))
        self.assertFalse(FourPlayerRecommendationPlayer.supports_game_settings(s5))

    def test_constants(self) -> None:
        self.assertEqual(4, NUM_PLAYERS_FOR_FOUR_PLAYER_RECOMMENDATION)
        self.assertEqual(9, NUM_CHANNELS)


class TestChannelInference(unittest.TestCase):
    """Hint shape maps to channel id 0..8 (3 hint shapes × 3 directions)."""

    def test_left_number_to_next_is_channel_0(self) -> None:
        hand = [Card(Color.RED, Number.ONE), Card(Color.RED, Number.TWO)]
        move = NumberHint(teammate=1, cards=[0], number=Number.ONE)
        self.assertEqual(0, _infer_channel_id(0, 1, move, hand))

    def test_left_number_to_next_plus_1_is_channel_1(self) -> None:
        hand = [Card(Color.RED, Number.ONE), Card(Color.RED, Number.TWO)]
        move = NumberHint(teammate=2, cards=[0], number=Number.ONE)
        self.assertEqual(1, _infer_channel_id(0, 2, move, hand))

    def test_left_number_to_next_plus_2_is_channel_2(self) -> None:
        hand = [Card(Color.RED, Number.ONE), Card(Color.RED, Number.TWO)]
        move = NumberHint(teammate=3, cards=[0], number=Number.ONE)
        self.assertEqual(2, _infer_channel_id(0, 3, move, hand))

    def test_left_color_to_next_is_channel_3(self) -> None:
        hand = [Card(Color.RED, Number.ONE), Card(Color.BLUE, Number.TWO)]
        move = ColorHint(teammate=1, cards=[0], color=Color.RED)
        self.assertEqual(3, _infer_channel_id(0, 1, move, hand))

    def test_right_number_index_based_user_example(self) -> None:
        """``R2 Y3 B4 R1`` (4p hand): right number is 1's on slot ``3`` only → channel 6."""
        hand = [
            Card(Color.RED, Number.TWO),
            Card(Color.YELLOW, Number.THREE),
            Card(Color.BLUE, Number.FOUR),
            Card(Color.RED, Number.ONE),
        ]
        move = NumberHint(teammate=1, cards=[3], number=Number.ONE)
        self.assertEqual(6, _infer_channel_id(0, 1, move, hand))

    def test_public_number_no_index0_to_next_is_channel_6(self) -> None:
        """Public fallback (target receiver): number hint missing slot 0 → right number."""
        move = NumberHint(teammate=1, cards=[1, 2], number=Number.TWO)
        self.assertEqual(6, _infer_channel_id(0, 1, move, None))

    def test_public_color_to_next_plus_1_is_channel_4(self) -> None:
        """Public fallback (target receiver): color hints always map to left color."""
        move = ColorHint(teammate=2, cards=[1, 2], color=Color.GREEN)
        self.assertEqual(4, _infer_channel_id(0, 2, move, None))


class TestMiniRecommendationSmoke(unittest.TestCase):
    def test_play_returns_legal_move_four_player(self) -> None:
        settings = create_standard_game_settings(4)
        view = PlayerView(
            teammates={
                1: Hand([Card(Color.RED, Number.ONE)] * 4),
                2: Hand([Card(Color.BLUE, Number.TWO)] * 4),
                3: Hand([Card(Color.GREEN, Number.THREE)] * 4),
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
        player = FourPlayerRecommendationPlayer(0)
        player.set_game_settings(settings)
        player.set_common_view(common)
        move = player.play(view)
        self.assertTrue(player.is_move_legal(view, move))


if __name__ == "__main__":
    unittest.main()
