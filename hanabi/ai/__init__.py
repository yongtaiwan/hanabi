"""
AI players for Hanabi game.
"""

from typing import Dict, Type

from .random_player import RandomPlayer
from .common_sense_player import CommonSensePlayer
from .monte_carlo_player import MonteCarloPlayer, MonteCarloConfig
from .recommendation_player import RecommendationPlayer
from .three_player_recommendation import ThreePlayerRecommendationPlayer
from .four_player_recommendation import FourPlayerRecommendationPlayer
from .five_player_recommendation import FivePlayerRecommendationPlayer
from .hint_hand_subtype_3p import HintHandSubtype3P
from .common_sense_cheater import CommonSenseCheater
from .paper_cheater import PaperCheater

# Registry mapping class name → class for every replay-instantiable AI seat type.
# Used by the GUI's debug-replay feature to resurrect the original bots from the
# saved ``players: [...]`` list and re-run their decisions to surface ``move.why()``.
# Add new AI classes here when they become replay-capable.
PLAYER_CLASSES: Dict[str, Type] = {
    cls.__name__: cls
    for cls in (
        RandomPlayer,
        CommonSensePlayer,
        MonteCarloPlayer,
        RecommendationPlayer,
        ThreePlayerRecommendationPlayer,
        FourPlayerRecommendationPlayer,
        FivePlayerRecommendationPlayer,
        HintHandSubtype3P,
        CommonSenseCheater,
        PaperCheater,
    )
}

__all__ = [
    "RandomPlayer",
    "CommonSensePlayer",
    "MonteCarloPlayer",
    "MonteCarloConfig",
    "RecommendationPlayer",
    "ThreePlayerRecommendationPlayer",
    "FourPlayerRecommendationPlayer",
    "FivePlayerRecommendationPlayer",
    "HintHandSubtype3P",
    "CommonSenseCheater",
    "PaperCheater",
    "PLAYER_CLASSES",
]
