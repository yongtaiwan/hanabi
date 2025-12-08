"""
GameField class for managing multiple games.

This module is used for AI performance comparisons and batch game simulations.
GUI/CLI games use Game directly, not GameField.
"""

from __future__ import annotations

from typing import Dict

from .game import Game, StartPosition
from .player import PlayerTeam


class GameField:
    """Manages multiple games and game initialization."""

    def __init__(self, start_position: StartPosition):
        """
        Initialize a game field.

        Args:
            start_position: The starting position (settings and initial deck)
        """
        self._start_position = start_position
        self._games: Dict[str, Game] = {}

    @property
    def startPosition(self) -> StartPosition:
        """Get the starting position."""
        return self._start_position

    @property
    def games(self) -> Dict[str, Game]:
        """Get the dictionary of games."""
        return self._games.copy()

    def _initGame(self, team: PlayerTeam) -> Game:
        """
        Initialize a new game.

        Args:
            team: The team of players (players are also observers)

        Returns:
            A new game instance
        """
        return Game.create(team, self._start_position.settings)

    def _playGame(self, game: Game) -> None:
        """
        Play a single game.

        Args:
            game: The game to play
        """
        game.play()

    def playGames(self, count: int, team: PlayerTeam) -> None:
        """
        Play multiple games.

        Args:
            count: Number of games to play
            team: The team of players (players are also observers)
        """
        for i in range(count):
            game = self._initGame(team)
            game_id = f"game_{i}"
            self._games[game_id] = game
            self._playGame(game)

    def __repr__(self) -> str:
        return f"GameField(start_position={self._start_position}, games={len(self._games)})"

