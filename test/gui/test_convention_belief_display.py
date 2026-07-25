"""Tests for :mod:`hanabi.gui.convention_belief_display`."""

from __future__ import annotations

import unittest

from hanabi.ai.dht_belief import Playability, RecState, slot_belief_from_legacy_kind
from hanabi.ai.dynamic_hand_type_3p import DynamicHandType3P
from hanabi.core.enums import CardKind
from hanabi.core.game import Game, create_standard_game_settings
from hanabi.core.player import PlayerTeam
from hanabi.gui.convention_belief_display import convention_overlays_for_seat


class TestConventionBeliefDisplay(unittest.TestCase):
    def test_chop_overlay_on_unknown_leftmost_slot(self) -> None:
        """Unknown chop slot shows overlay with chop and no kind."""
        settings = create_standard_game_settings(3)
        players = [DynamicHandType3P(i) for i in range(3)]
        for player in players:
            player.set_game_settings(settings)
        game = Game.create(team=PlayerTeam(players), settings=settings)
        overlays = convention_overlays_for_seat(game, 0)
        self.assertIn(0, overlays)
        self.assertTrue(overlays[0].is_chop)
        self.assertIsNone(overlays[0].kind)
        self.assertFalse(overlays[0].is_unplayable)
        self.assertFalse(overlays[0].kind_mismatch)
        self.assertIsNone(overlays[0].chop_confirmed)

    def test_kind_mismatch_when_belief_differs_from_actual(self) -> None:
        """Magenta-outline flag when inferred kind disagrees with full information."""
        settings = create_standard_game_settings(3)
        players = [DynamicHandType3P(i) for i in range(3)]
        for player in players:
            player.set_game_settings(settings)
        game = Game.create(team=PlayerTeam(players), settings=settings)
        card = game.state.player_hands[0].cards[0]
        actual = game.state.common_view.card_kind(card, settings)
        wrong = next(k for k in CardKind if k != actual)
        players[0]._slot_belief[0][0] = slot_belief_from_legacy_kind(wrong)
        overlays = convention_overlays_for_seat(game, 0)
        self.assertTrue(overlays[0].kind_mismatch)

    def test_kind_mismatch_suppressed_when_not_comparing_to_actual(self) -> None:
        """Face-down seats must not leak private identities via mismatch outlines."""
        settings = create_standard_game_settings(3)
        players = [DynamicHandType3P(i) for i in range(3)]
        for player in players:
            player.set_game_settings(settings)
        game = Game.create(team=PlayerTeam(players), settings=settings)
        card = game.state.player_hands[0].cards[0]
        actual = game.state.common_view.card_kind(card, settings)
        wrong = next(k for k in CardKind if k != actual)
        players[0]._slot_belief[0][0] = slot_belief_from_legacy_kind(wrong)
        overlays = convention_overlays_for_seat(game, 0, compare_to_actual=False)
        self.assertFalse(overlays[0].kind_mismatch)

    def test_recommended_overlay_without_kind(self) -> None:
        """Recommended discard belief shows trash-can overlay even when legacy kind is unknown."""
        settings = create_standard_game_settings(3)
        players = [DynamicHandType3P(i) for i in range(3)]
        for player in players:
            player.set_game_settings(settings)
        game = Game.create(team=PlayerTeam(players), settings=settings)
        players[0]._slot_belief[0][2].rec_state = RecState.RECOMMENDED
        overlays = convention_overlays_for_seat(game, 0)
        self.assertIn(2, overlays)
        self.assertTrue(overlays[2].is_recommended)
        self.assertIsNone(overlays[2].kind)
        self.assertFalse(overlays[2].is_unplayable)

    def test_unplayable_overlay_without_kind(self) -> None:
        """Unplayable playability shows pause overlay even when legacy kind is unknown."""
        settings = create_standard_game_settings(3)
        players = [DynamicHandType3P(i) for i in range(3)]
        for player in players:
            player.set_game_settings(settings)
        game = Game.create(team=PlayerTeam(players), settings=settings)
        players[0]._slot_belief[0][4].playability = Playability.UNPLAYABLE
        overlays = convention_overlays_for_seat(game, 0)
        self.assertIn(4, overlays)
        self.assertTrue(overlays[4].is_unplayable)
        self.assertIsNone(overlays[4].kind)
        self.assertFalse(overlays[4].is_chop)

    def test_no_overlays_without_dynamic_hand_type_bot(self) -> None:
        """Non-convention teams produce no overlays."""
        from hanabi.ai.random_player import RandomPlayer

        settings = create_standard_game_settings(3)
        team = PlayerTeam([RandomPlayer(i) for i in range(3)])
        game = Game.create(team=team, settings=settings)
        self.assertEqual({}, convention_overlays_for_seat(game, 0))

    def test_dynamic_recommendation_chop_confirmed_flag(self) -> None:
        """DR bot exposes chop_confirmed True/False for / vs X icons."""
        from hanabi.ai.dynamic_recommendation_3p import DynamicRecommendation3P

        settings = create_standard_game_settings(3)
        players = [DynamicRecommendation3P(i) for i in range(3)]
        for player in players:
            player.set_game_settings(settings)
        game = Game.create(team=PlayerTeam(players), settings=settings)
        overlays = convention_overlays_for_seat(game, 0)
        self.assertIn(0, overlays)
        self.assertTrue(overlays[0].is_chop)
        self.assertFalse(overlays[0].chop_confirmed)
        players[0]._hand_belief[0].chop_confirmed = True
        overlays = convention_overlays_for_seat(game, 0)
        self.assertTrue(overlays[0].chop_confirmed)

    def test_overlays_use_target_seat_own_belief(self) -> None:
        """Seat overlays come from that seat's bot, not always seat 0's matrix."""
        from hanabi.ai.dr_belief import Playability as DrPlayability
        from hanabi.ai.dynamic_recommendation_3p import DynamicRecommendation3P

        settings = create_standard_game_settings(3)
        players = [DynamicRecommendation3P(i) for i in range(3)]
        for player in players:
            player.set_game_settings(settings)
        game = Game.create(team=PlayerTeam(players), settings=settings)
        # Only seat 1 knows slot 0 is playable (as after decoding own hint message).
        players[1]._hand_belief[1].slots[0].playability = DrPlayability.PLAYABLE
        players[1]._hand_belief[1].chop = 1
        overlays = convention_overlays_for_seat(game, 1)
        self.assertEqual(CardKind.PLAYABLE, overlays[0].kind)
        self.assertFalse(overlays[0].is_chop)


if __name__ == "__main__":
    unittest.main()
