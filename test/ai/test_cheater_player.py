"""CommonSenseCheater: full-state play() and Game dispatch."""

import unittest

from hanabi.ai.common_sense_cheater import CommonSenseCheater
from hanabi.ai.random_player import RandomPlayer
from hanabi.core.enums import CardKind
from hanabi.core.game import Game, create_standard_game_settings
from hanabi.core.game_field import GameField
from hanabi.core.moves import ColorHint, NumberHint
from hanabi.core.player import PlayerTeam


class CommonSenseCheaterTests(unittest.TestCase):
    def test_team_of_cheaters_finishes_games(self) -> None:
        settings = create_standard_game_settings(3)
        team = PlayerTeam([CommonSenseCheater(0), CommonSenseCheater(1), CommonSenseCheater(2)])
        game = Game.create(team, settings)
        game.play()
        self.assertTrue(game.is_finished)
        self.assertGreaterEqual(game.get_score(), 0)

    def test_cheater_outscores_random_on_same_seeds_small_sample(self) -> None:
        settings = create_standard_game_settings(3)
        cheat_field = GameField.create_from_settings(settings, seed=42)
        random_field = GameField.create_from_settings(settings, seed=42)

        cheat_results = cheat_field.run_experiment(
            ai_factories={"CommonSenseCheater": CommonSenseCheater},
            num_runs=15,
            save_records=False,
            random_seed=0,
            experiment_id="test_cheater_vs_self",
        )
        random_results = random_field.run_experiment(
            ai_factories={"RandomPlayer": RandomPlayer},
            num_runs=15,
            save_records=False,
            random_seed=0,
            experiment_id="test_random_baseline",
        )
        c = cheat_results.summary["CommonSenseCheater"].average_score
        r = random_results.summary["RandomPlayer"].average_score
        self.assertGreater(c, r)

    def test_never_hints_when_discard_legal_and_hand_has_useless(self) -> None:
        """If a useless discard is legal, policy must not choose a hint (Hanabi max-token case is separate)."""
        settings = create_standard_game_settings(3)
        field = GameField.create_from_settings(settings, seed=0)
        for run_id in range(25):
            deck_seed = run_id
            start = GameField._create_start_position(settings, seed=deck_seed)
            run_field = GameField(start)
            team = PlayerTeam([CommonSenseCheater(i) for i in range(3)])
            game = run_field._create_game_from_start_position(start, team)
            while not game.is_finished:
                st = game.state
                idx = st.current_player
                can_discard = st.common_view.hint_tokens < settings.max_hint_tokens
                has_useless = any(
                    CardKind.USELESS == st.common_view.card_kind(c, settings)
                    for c in st.player_hands[idx].cards
                )
                move = CommonSenseCheater(idx).play(st)
                if can_discard and has_useless:
                    self.assertNotIsInstance(move, (ColorHint, NumberHint), msg=f"run_id={run_id} turn={st.turn_number}")
                game.process_move(idx, move)
                game._advance_turn()


if __name__ == "__main__":
    unittest.main()
