"""GUI helpers for showing recommendation-player play/discard indicators on cards."""

from __future__ import annotations

from typing import Dict, Literal, TYPE_CHECKING

if TYPE_CHECKING:
    from hanabi.core.game import Game
    from hanabi.core.player import BasePlayer

RecommendationAction = Literal["play", "discard"]


def recommendations_by_slot_for_seat(game: Game, seat: int) -> Dict[int, RecommendationAction]:
    """Return ``{slot_index: 'play'|'discard'}`` for a seat, or ``{}`` if not a rec player."""
    from hanabi.ai.recommendation_player import RecommendationPlayer
    from hanabi.ai.three_player_recommendation import ThreePlayerRecommendationPlayer
    from hanabi.ai.four_player_recommendation import FourPlayerRecommendationPlayer

    player = game.team.players[seat]
    if not isinstance(
        player,
        (RecommendationPlayer, ThreePlayerRecommendationPlayer, FourPlayerRecommendationPlayer),
    ):
        return {}
    return player.get_gui_recommendation_by_slot(game.get_player_view(seat))
