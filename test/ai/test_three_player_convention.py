"""Tests for :mod:`hanabi.ai.three_player_convention`."""

import unittest

from hanabi.ai.three_player_convention import (
    NUM_PLAYERS_FOR_THREE_PLAYER_CONVENTION,
    HintSeatRole,
    ThreePlayerConventionPlayer,
)
from hanabi.core.card import Card
from hanabi.core.enums import Color, Number
from hanabi.core.game import CommonView, create_standard_game_settings


class TestThreePlayerConventionPlayerSettings(unittest.TestCase):
    """Player only registers for 3-player games."""

    def test_supports_only_three_players(self) -> None:
        s3 = create_standard_game_settings(3)
        s5 = create_standard_game_settings(5)
        self.assertTrue(ThreePlayerConventionPlayer.supports_game_settings(s3))
        self.assertFalse(ThreePlayerConventionPlayer.supports_game_settings(s5))

    def test_set_game_settings_rejects_non_three(self) -> None:
        p = ThreePlayerConventionPlayer(0)
        s5 = create_standard_game_settings(5)
        with self.assertRaises(AssertionError):
            p.set_game_settings(s5)

    def test_num_players_constant(self) -> None:
        self.assertEqual(3, NUM_PLAYERS_FOR_THREE_PLAYER_CONVENTION)


class TestChopPlaceholder(unittest.TestCase):
    """Chop placeholder on the player class."""

    def test_chop_is_last_slot_for_five_card_hand(self) -> None:
        self.assertEqual(4, ThreePlayerConventionPlayer.chop_slot_from_public_information(hand_size=5))

    def test_chop_is_last_slot_for_single_card_hand(self) -> None:
        self.assertEqual(0, ThreePlayerConventionPlayer.chop_slot_from_public_information(hand_size=1))

    def test_empty_hand_asserts(self) -> None:
        with self.assertRaises(AssertionError):
            ThreePlayerConventionPlayer.chop_slot_from_public_information(hand_size=0)


class TestHintRolesBySeat(unittest.TestCase):
    """Per-seat giver / receiver / observer for one hint event."""

    def test_three_players_one_observer_each_pair(self) -> None:
        G, R, O = HintSeatRole.GIVER, HintSeatRole.RECEIVER, HintSeatRole.OBSERVER
        cases = [
            ((0, 1), {0: G, 1: R, 2: O}),
            ((0, 2), {0: G, 1: O, 2: R}),
            ((1, 0), {0: R, 1: G, 2: O}),
            ((1, 2), {0: O, 1: G, 2: R}),
            ((2, 0), {0: R, 1: O, 2: G}),
            ((2, 1), {0: O, 1: R, 2: G}),
        ]
        for (giver, receiver), expected in cases:
            self.assertEqual(
                expected,
                ThreePlayerConventionPlayer.hint_roles_by_seat(
                    giver_index=giver,
                    receiver_index=receiver,
                    num_players=NUM_PLAYERS_FOR_THREE_PLAYER_CONVENTION,
                ),
            )

    def test_four_players_two_observers(self) -> None:
        G, R, O = HintSeatRole.GIVER, HintSeatRole.RECEIVER, HintSeatRole.OBSERVER
        roles = ThreePlayerConventionPlayer.hint_roles_by_seat(
            giver_index=0,
            receiver_index=1,
            num_players=4,
        )
        self.assertEqual({0: G, 1: R, 2: O, 3: O}, roles)

    def test_giver_same_as_receiver_asserts(self) -> None:
        with self.assertRaises(AssertionError):
            ThreePlayerConventionPlayer.hint_roles_by_seat(
                giver_index=0,
                receiver_index=0,
                num_players=3,
            )


class TestMinimalPlayLoop(unittest.TestCase):
    """Smoke-test ``play`` picks a legal move when wired."""

    def test_play_returns_legal_move_three_player_smoke(self) -> None:
        from hanabi.core.game import Hand, PlayerView

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
        player = ThreePlayerConventionPlayer(0)
        player.set_game_settings(settings)
        player.set_common_view(common)
        move = player.play(view)
        self.assertTrue(player.is_move_legal(view, move))


if __name__ == "__main__":
    unittest.main()
