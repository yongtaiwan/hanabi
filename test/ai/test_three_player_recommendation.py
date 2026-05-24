"""Tests for :mod:`hanabi.ai.three_player_recommendation`."""

import unittest

from hanabi.ai.three_player_recommendation import (
    NUM_PLAYERS_FOR_MINI_RECOMMENDATION,
    ThreePlayerRecommendationPlayer,
    _infer_channel_id,
)
from hanabi.core.card import Card
from hanabi.core.enums import Color, Number
from hanabi.core.game import CommonView, Hand, PlayerView, create_standard_game_settings
from hanabi.core.moves import ColorHint, NumberHint


class TestThreePlayerRecommendationSettings(unittest.TestCase):
    def test_supports_only_three_players(self) -> None:
        s3 = create_standard_game_settings(3)
        s5 = create_standard_game_settings(5)
        self.assertTrue(ThreePlayerRecommendationPlayer.supports_game_settings(s3))
        self.assertFalse(ThreePlayerRecommendationPlayer.supports_game_settings(s5))

    def test_num_players_constant(self) -> None:
        self.assertEqual(3, NUM_PLAYERS_FOR_MINI_RECOMMENDATION)


class TestChannelInference(unittest.TestCase):
    """Hint shape maps to channel id 0..6."""

    def test_left_number_next_is_channel_0(self) -> None:
        hand = [Card(Color.RED, Number.ONE), Card(Color.RED, Number.TWO)]
        move = NumberHint(teammate=1, cards=[0], number=Number.ONE)
        self.assertEqual(0, _infer_channel_id(0, 1, move, hand))

    def test_right_color_next_is_channel_6(self) -> None:
        """Right color only to **next** teammate; hinter 2’s next is player 0."""
        hand = [Card(Color.WHITE, Number.TWO), Card(Color.GREEN, Number.THREE)]
        move = ColorHint(teammate=0, cards=[1], color=Color.GREEN)
        self.assertEqual(6, _infer_channel_id(2, 0, move, hand))

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


class TestMiniRecommendationSmoke(unittest.TestCase):
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
