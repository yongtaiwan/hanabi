"""PaperCheater: full-state play() and Game dispatch."""

import unittest

from hanabi.ai.paper_cheater import PaperCheater
from hanabi.core.game import Game, create_standard_game_settings
from hanabi.core.player import PlayerTeam


class PaperCheaterTests(unittest.TestCase):
    def test_team_finishes_games(self) -> None:
        settings = create_standard_game_settings(3)
        team = PlayerTeam([PaperCheater(0), PaperCheater(1), PaperCheater(2)])
        game = Game.create(team, settings)
        game.play()
        self.assertTrue(game.is_finished)
        self.assertGreaterEqual(game.get_score(), 0)


if __name__ == "__main__":
    unittest.main()
