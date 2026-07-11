"""Tests for :mod:`hanabi.gui.convention_belief_display`."""

from __future__ import annotations

import unittest

from hanabi.ai.h3p_belief import Playability, RecState, slot_belief_from_legacy_kind
from hanabi.ai.hint_hand_subtype_3p import HintHandSubtype3P
from hanabi.core.enums import CardKind
from hanabi.core.game import Game, create_standard_game_settings
from hanabi.core.player import PlayerTeam
from hanabi.gui.convention_belief_display import convention_overlays_for_seat


class TestConventionBeliefDisplay(unittest.TestCase):
    def test_chop_overlay_on_unknown_leftmost_slot(self) -> None:
        """Unknown chop slot shows overlay with chop and no kind."""
        settings = create_standard_game_settings(3)
        players = [HintHandSubtype3P(i) for i in range(3)]
        for player in players:
            player.set_game_settings(settings)
        game = Game.create(team=PlayerTeam(players), settings=settings)
        overlays = convention_overlays_for_seat(game, 0)
        self.assertIn(0, overlays)
        self.assertTrue(overlays[0].is_chop)
        self.assertIsNone(overlays[0].kind)
        self.assertFalse(overlays[0].is_unplayable)
        self.assertFalse(overlays[0].kind_mismatch)

    def test_kind_mismatch_when_belief_differs_from_actual(self) -> None:
        """Magenta-outline flag when inferred kind disagrees with full information."""
        settings = create_standard_game_settings(3)
        players = [HintHandSubtype3P(i) for i in range(3)]
        for player in players:
            player.set_game_settings(settings)
        game = Game.create(team=PlayerTeam(players), settings=settings)
        card = game.state.player_hands[0].cards[0]
        actual = game.state.common_view.card_kind(card, settings)
        wrong = next(k for k in CardKind if k != actual)
        players[0]._slot_belief[0][0] = slot_belief_from_legacy_kind(wrong)
        overlays = convention_overlays_for_seat(game, 0)
        self.assertTrue(overlays[0].kind_mismatch)

    def test_recommended_overlay_without_kind(self) -> None:
        """Recommended discard belief shows trash-can overlay even when legacy kind is unknown."""
        settings = create_standard_game_settings(3)
        players = [HintHandSubtype3P(i) for i in range(3)]
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
        players = [HintHandSubtype3P(i) for i in range(3)]
        for player in players:
            player.set_game_settings(settings)
        game = Game.create(team=PlayerTeam(players), settings=settings)
        players[0]._slot_belief[0][4].playability = Playability.UNPLAYABLE
        overlays = convention_overlays_for_seat(game, 0)
        self.assertIn(4, overlays)
        self.assertTrue(overlays[4].is_unplayable)
        self.assertIsNone(overlays[4].kind)
        self.assertFalse(overlays[4].is_chop)

    def test_no_overlays_without_hint_hand_bot(self) -> None:
        """Non-convention teams produce no overlays."""
        from hanabi.ai.random_player import RandomPlayer

        settings = create_standard_game_settings(3)
        team = PlayerTeam([RandomPlayer(i) for i in range(3)])
        game = Game.create(team=team, settings=settings)
        self.assertEqual({}, convention_overlays_for_seat(game, 0))


if __name__ == "__main__":
    unittest.main()
