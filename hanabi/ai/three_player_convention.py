"""
Three-player Hanabi convention bot (v2025 draft; work in progress).

Targets the informal ``Hanabi Convention for 3 players without sorting hands`` strategy.
Hands use left-to-right indices like :mod:`hanabi.ai.recommendation_player` (**C1 = index 0**,
rightmost = newest). Independent of :class:`~hanabi.ai.recommendation_player.RecommendationPlayer`.

**Hint roles:** For each hint, every seat has a :class:`HintSeatRole` --- giver, receiver, or
observer. Use :meth:`~ThreePlayerConventionPlayer.hint_roles_by_seat`; with more than three players,
everyone who is neither giver nor receiver is an **observer** (several seats when upscaling to
4--5p). Pair with modular / encoding logic later as in Cox et al. mod-8 style strategies.
"""

from __future__ import annotations

from enum import Enum
from typing import Dict, Optional

from hanabi.core.game import CommonView, GameSettings, PlayerView
from hanabi.core.move_generation import generate_all_valid_moves
from hanabi.core.moves import Move
from hanabi.core.player import BasePlayer

# Same pattern as :mod:`hanabi.ai.recommendation_player` (`NUM_PLAYERS_FOR_RECOMMENDATION`).
NUM_PLAYERS_FOR_THREE_PLAYER_CONVENTION = 3


class HintSeatRole(Enum):
    """Seat relative to a single hint event (who gave it and who received it)."""

    GIVER = "giver"
    RECEIVER = "receiver"
    OBSERVER = "observer"


class ThreePlayerConventionPlayer(BasePlayer):
    """
    AI player for the 3-player convention document.

    Strategy hooks will replace the minimal ``play`` dispatch later; for now the bot chooses the
    first move :func:`~hanabi.core.move_generation.generate_all_valid_moves` lists that is still
    legal after filtering with :meth:`~hanabi.core.player.BasePlayer.is_move_legal`.
    """

    def __init__(self, player_index: int):
        super().__init__(player_index)
        self._last_decision_summary: Optional[str] = None

    @classmethod
    def supports_game_settings(cls, game_settings: GameSettings) -> bool:
        return NUM_PLAYERS_FOR_THREE_PLAYER_CONVENTION == game_settings.num_players

    def set_game_settings(self, game_settings: GameSettings) -> None:
        assert NUM_PLAYERS_FOR_THREE_PLAYER_CONVENTION == game_settings.num_players, (
            "ThreePlayerConventionPlayer requires 3-player games"
        )
        super().set_game_settings(game_settings)

    def play(self, player_view: PlayerView) -> Move:
        assert player_view.own_hand_size > 0
        candidates = generate_all_valid_moves(
            player_view=player_view,
            common_view=self.common_view,
            game_settings=self.game_settings,
            player_index=self._player_index,
        )
        for move in candidates:
            if self.is_move_legal(player_view, move):
                self._last_decision_summary = None
                return move
        assert False, "expected at least one legal move with a non-empty hand"

    def get_decision_summary(self) -> Optional[str]:
        """Return a short explanation of the last move for console/GUI display."""
        return self._last_decision_summary

    @staticmethod
    def chop_slot_from_public_information(*, hand_size: int) -> int:
        """Placeholder chop index: rightmost slot (``hand_size - 1``)."""
        assert hand_size > 0, "chop requires a non-empty hand"
        return hand_size - 1

    @staticmethod
    def hint_roles_by_seat(*, giver_index: int, receiver_index: int, num_players: int) -> Dict[int, HintSeatRole]:
        """
        Map each seat ``0 .. num_players - 1`` to :class:`HintSeatRole` for one hint.

        Any seat that is neither giver nor receiver is an **observer** (one seat in 3p; several in
        larger games).
        """
        assert 2 <= num_players
        assert 0 <= giver_index < num_players
        assert 0 <= receiver_index < num_players
        assert giver_index != receiver_index, "giver and receiver must differ"
        roles: Dict[int, HintSeatRole] = {}
        for seat in range(num_players):
            if seat == giver_index:
                roles[seat] = HintSeatRole.GIVER
            elif seat == receiver_index:
                roles[seat] = HintSeatRole.RECEIVER
            else:
                roles[seat] = HintSeatRole.OBSERVER
        return roles
