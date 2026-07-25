"""Regression guards: honest BasePlayer / convention channel must not cheat."""

from __future__ import annotations

import ast
import inspect
import unittest
from pathlib import Path

from hanabi.ai import dynamic_hand_type_3p as dht
from hanabi.ai import dynamic_recommendation_3p as dr
from hanabi.ai import hint_hand_subtype_3p as hhs
from hanabi.ai.dht_belief import fresh_slot_belief
from hanabi.ai.dr_belief import copy_hand_belief, fresh_hand_belief
from hanabi.ai.dynamic_hand_type_3p import DynamicHandType3P
from hanabi.ai.dynamic_recommendation_3p import DynamicRecommendation3P
from hanabi.ai.hint_hand_subtype_3p import HintHandSubtype3P
from hanabi.core.card import Card
from hanabi.core.enums import Color, Number
from hanabi.core.game import (
    CommonView,
    Game,
    Hand,
    PlayerView,
    create_standard_game_settings,
)
from hanabi.core.moves import NumberHint
from hanabi.core.player import PlayerTeam


def _common(settings=None) -> CommonView:
    settings = settings or create_standard_game_settings(3)
    return CommonView(
        live_tokens=settings.max_live_tokens,
        hint_tokens=settings.max_hint_tokens,
        cards_to_draw=40,
        cards_discarded={},
        cards_played={},
    )


class TestEngineNotifyIsObserveOnly(unittest.TestCase):
    def test_notify_players_source_has_no_belief_sync_hooks(self) -> None:
        """``Game._notify_players`` must not grow AI belief sync / hand_cards oracles."""
        import hanabi.core.game as game_mod

        src = inspect.getsource(game_mod.Game._notify_players)
        banned = (
            "hand_cards",
            "propagate_convention",
            "align_convention",
            "copy_belief",
            "assert_independent",
        )
        for token in banned:
            self.assertNotIn(token, src, f"_notify_players must not reference {token!r}")

    def test_notify_players_ast_only_calls_observe(self) -> None:
        """Body should only invoke ``observe`` on BasePlayer seats (plus isinstance)."""
        import textwrap

        import hanabi.core.game as game_mod

        tree = ast.parse(textwrap.dedent(inspect.getsource(game_mod.Game._notify_players)))
        calls = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
        ]
        attrs = {node.func.attr for node in calls}
        self.assertEqual({"observe", "_get_player_view"}, attrs)

    def test_player_view_omits_own_hand(self) -> None:
        settings = create_standard_game_settings(3)
        players = [DynamicRecommendation3P(i) for i in range(3)]
        game = Game.create(team=PlayerTeam(players), settings=settings)
        for seat in range(3):
            view = game.get_player_view(seat)
            self.assertNotIn(seat, view.teammates)
            self.assertEqual(2, len(view.teammates))


class TestChannelEncodeApisHaveNoCrossHandKwargs(unittest.TestCase):
    def test_dr_encode_peer_code_signature(self) -> None:
        params = inspect.signature(dr._encode_peer_code).parameters
        self.assertNotIn("other_hands", params)
        self.assertNotIn("almost_critical", params)

    def test_dr_discard_option_score_signature(self) -> None:
        params = inspect.signature(dr._discard_option_score).parameters
        self.assertNotIn("other_hands", params)
        self.assertNotIn("almost_critical", params)

    def test_dr_module_has_no_other_hands_in_encode_helpers(self) -> None:
        path = Path(dr.__file__)
        text = path.read_text()
        # Hint-quality trash helper may still take other_hands; encode path must not.
        encode_region = text.split("def _discard_option_score", 1)[1].split(
            "def _is_good_discard_trash", 1
        )[0]
        self.assertNotIn("other_hands", encode_region)
        self.assertNotIn("almost_critical", encode_region)


class TestPeerCodesPubliclyDetermined(unittest.TestCase):
    def _hands(self) -> tuple[list[Card], list[Card]]:
        next_hand = [
            Card(Color.GREEN, Number.TWO),
            Card(Color.GREEN, Number.TWO),
            Card(Color.GREEN, Number.TWO),
            Card(Color.GREEN, Number.TWO),
            Card(Color.RED, Number.ONE),
        ]
        prev_hand = [Card(Color.BLUE, Number.THREE)] * 5
        return next_hand, prev_hand

    def test_dr_peer_code_same_for_any_observer_seeing_the_hand(self) -> None:
        settings = create_standard_game_settings(3)
        common = _common(settings)
        next_hand, prev_hand = self._hands()
        next_belief = fresh_hand_belief(5)
        prev_belief = fresh_hand_belief(5)
        self.assertEqual(
            dr._peer_code_for_hand(next_hand, next_belief, common, settings),
            dr._peer_code_for_hand(list(next_hand), next_belief, common, settings),
        )
        self.assertEqual(
            dr._peer_code_for_hand(prev_hand, prev_belief, common, settings),
            dr._peer_code_for_hand(list(prev_hand), prev_belief, common, settings),
        )

    def test_dht_peer_code_same_for_any_observer_seeing_the_hand(self) -> None:
        settings = create_standard_game_settings(3)
        common = _common(settings)
        next_hand, prev_hand = self._hands()
        next_belief = [fresh_slot_belief() for _ in range(5)]
        prev_belief = [fresh_slot_belief() for _ in range(5)]
        self.assertEqual(
            dht._peer_code_for_hand(next_hand, next_belief, common, settings),
            dht._peer_code_for_hand(list(next_hand), next_belief, common, settings),
        )
        self.assertEqual(
            dht._peer_code_for_hand(prev_hand, prev_belief, common, settings),
            dht._peer_code_for_hand(list(prev_hand), prev_belief, common, settings),
        )

    def test_hhs_peer_code_same_for_any_observer_seeing_the_hand(self) -> None:
        settings = create_standard_game_settings(3)
        common = _common(settings)
        next_hand, prev_hand = self._hands()
        blank = [None] * 5
        self.assertEqual(
            hhs._peer_code_for_hand(next_hand, blank, common, settings),
            hhs._peer_code_for_hand(list(next_hand), blank, common, settings),
        )


class TestIndependentDecodeAfterHint(unittest.TestCase):
    def _views(self, hand_p1: list[Card], hand_p2: list[Card]) -> list[PlayerView]:
        filler = [Card(Color.WHITE, Number.FOUR)] * 5
        return [
            PlayerView(teammates={1: Hand(hand_p1), 2: Hand(hand_p2)}, own_hand_size=5),
            PlayerView(teammates={0: Hand(filler), 2: Hand(hand_p2)}, own_hand_size=5),
            PlayerView(teammates={0: Hand(filler), 1: Hand(hand_p1)}, own_hand_size=5),
        ]

    def _observe_convention_hint(self, players, views, common, settings, hand_p1, hand_p2, mod):
        # Opening deal: shared blank belief rows (same for every seat).
        if isinstance(players[0], DynamicRecommendation3P):
            b1, b2 = players[0]._hand_belief[1], players[0]._hand_belief[2]
        elif isinstance(players[0], DynamicHandType3P):
            b1, b2 = players[0]._slot_belief[1], players[0]._slot_belief[2]
        else:
            b1, b2 = players[0]._inferred_card_kind[1], players[0]._inferred_card_kind[2]
        enc = (
            mod._peer_code_for_hand(hand_p1, b1, common, settings)
            + mod._peer_code_for_hand(hand_p2, b2, common, settings)
        ) % 8
        hint = mod._build_hint_for_encoded(0, views[0], enc)
        self.assertIsNotNone(hint)
        for player, view in zip(players, views):
            if isinstance(hint, NumberHint):
                player.observe_number_hint_move(0, hint, view)
            else:
                player.observe_color_hint_move(0, hint, view)
        return hint

    def test_dr_independent_own_decode(self) -> None:
        settings = create_standard_game_settings(3)
        common = _common(settings)
        players = [DynamicRecommendation3P(i) for i in range(3)]
        for p in players:
            p.set_game_settings(settings)
            p.set_common_view(common)
        hand_p1 = [Card(Color.GREEN, Number.TWO)] * 4 + [Card(Color.RED, Number.ONE)]
        hand_p2 = [Card(Color.BLUE, Number.ONE)] * 5
        views = self._views(hand_p1, hand_p2)
        own_before = [copy_hand_belief(players[s]._hand_belief[s]) for s in range(3)]
        hint = self._observe_convention_hint(players, views, common, settings, hand_p1, hand_p2, dr)
        dr.assert_independent_own_decode_matches(players, 0, hint, views, own_before)
        dr.assert_public_non_hinter_rows_agree(players, 0, hint)

    def test_dht_independent_own_decode(self) -> None:
        settings = create_standard_game_settings(3)
        common = _common(settings)
        players = [DynamicHandType3P(i) for i in range(3)]
        for p in players:
            p.set_game_settings(settings)
            p.set_common_view(common)
        hand_p1 = [Card(Color.GREEN, Number.TWO)] * 4 + [Card(Color.RED, Number.ONE)]
        hand_p2 = [Card(Color.BLUE, Number.ONE)] * 5
        views = self._views(hand_p1, hand_p2)
        own_before = [
            [
                dht.SlotBelief(b.playability, b.legacy_kind, b.rec_state)
                for b in players[s]._slot_belief[s]
            ]
            for s in range(3)
        ]
        hint = self._observe_convention_hint(players, views, common, settings, hand_p1, hand_p2, dht)
        dht.assert_independent_own_decode_matches(players, 0, hint, views, own_before)
        dht.assert_public_non_hinter_rows_agree(players, 0, hint)

    def test_hhs_independent_own_decode(self) -> None:
        settings = create_standard_game_settings(3)
        common = _common(settings)
        players = [HintHandSubtype3P(i) for i in range(3)]
        for p in players:
            p.set_game_settings(settings)
            p.set_common_view(common)
        hand_p1 = [Card(Color.GREEN, Number.TWO)] * 4 + [Card(Color.RED, Number.ONE)]
        hand_p2 = [Card(Color.BLUE, Number.ONE)] * 5
        views = self._views(hand_p1, hand_p2)
        own_before = [list(players[s]._inferred_card_kind[s]) for s in range(3)]
        hint = self._observe_convention_hint(players, views, common, settings, hand_p1, hand_p2, hhs)
        hhs.assert_independent_own_decode_matches(players, 0, hint, views, own_before)
        hhs.assert_public_non_hinter_rows_agree(players, 0, hint)


class TestLiveGamesStayConsistent(unittest.TestCase):
    def test_short_dr_games_complete(self) -> None:
        """Smoke: shared-belief peer codes + local decode finish without assert failures."""
        settings = create_standard_game_settings(3)
        for seed in range(42, 47):
            from hanabi.core.game_field import GameField

            field = GameField.create_from_settings(settings, seed=seed)
            players = [DynamicRecommendation3P(i) for i in range(3)]
            team = PlayerTeam(players)
            result = field._play_game_with_team(team, save_record=False)
            self.assertIsNotNone(result.score)

    def test_replay_t10_marks_reach_all_seats_so_t11_discards(self) -> None:
        """Non-hinter must absorb public decode of both hands (game 12 T10→T11)."""
        from hanabi.ai.dr_belief import Playability
        from hanabi.ai.dynamic_recommendation_3p import (
            ChopClass,
            HintQuality,
            _HINT_CHOP_MATRIX,
            _chop_class,
            _hint_quality,
        )
        from hanabi.core.game_history import GameHistory
        from hanabi.core.moves import Discard

        path = (
            Path(__file__).resolve().parents[2]
            / "game_records"
            / "exp_ai_comparison"
            / "20260725_174417"
            / "3p"
            / "games"
            / "012"
            / "run_012_ai_DynamicRecommendation3P.yaml"
        )
        data = GameHistory({}).load_from_file(str(path))
        players = [DynamicRecommendation3P(i) for i in range(3)]
        game = GameHistory.create_game_from_history(data, PlayerTeam(players))
        for p in players:
            p.set_game_settings(game.settings)
        game._set_common_view_for_players()
        for ms in data["moves"][:10]:
            mover = game.state.current_player
            game.process_move(mover, GameHistory._short_to_move(ms, mover, game))
            game._advance_turn()
        # After T10, every seat knows P3 slot 4 is playable.
        for bot in players:
            self.assertEqual(Playability.PLAYABLE, bot._hand_belief[2].slots[4].playability)
        p2 = players[1]
        own = p2._hand_belief[1]
        pv = game.get_player_view(1)
        hq = _hint_quality(1, pv, game.state.common_view, game.settings, p2._hand_belief)
        chop_class = _chop_class(own)
        self.assertEqual(ChopClass.CONFIRMED, chop_class)
        self.assertNotEqual(HintQuality.GOOD, hq)
        self.assertFalse(_HINT_CHOP_MATRIX[(hq, chop_class)])
        move = p2.play(pv)
        self.assertIsInstance(move, Discard)
        self.assertEqual(2, move.card)


if __name__ == "__main__":
    unittest.main()
