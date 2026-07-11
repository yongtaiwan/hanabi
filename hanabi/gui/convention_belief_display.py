"""GUI overlays for HintHandSubtype3P inferred card kinds and chop."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional, TYPE_CHECKING

from hanabi.core.enums import CardKind

if TYPE_CHECKING:
    from hanabi.core.game import Game


@dataclass(frozen=True)
class ConventionSlotOverlay:
    """Per-slot belief overlay for :class:`~hanabi.ai.hint_hand_subtype_3p.HintHandSubtype3P`."""

    kind: Optional[CardKind]
    is_chop: bool
    is_unplayable: bool
    is_recommended: bool
    kind_mismatch: bool


def _hint_hand_subtype_bot_for_team(game: Game):
    from hanabi.ai.hint_hand_subtype_3p import HintHandSubtype3P

    for player in game.team.players:
        if isinstance(player, HintHandSubtype3P):
            return player
    return None


def convention_overlays_for_seat(game: Game, target_seat: int) -> Dict[int, ConventionSlotOverlay]:
    """
    Return overlays for each hand slot on ``target_seat`` that has a known kind and/or is chop.

    ``kind_mismatch`` is set when inferred kind is known and differs from full-information
    :meth:`~hanabi.core.game.CommonView.card_kind` for that card.
    """
    bot = _hint_hand_subtype_bot_for_team(game)
    if bot is None:
        return {}

    state = game.state
    hand = state.player_hands[target_seat]
    if not hand.cards:
        return {}

    kinds = bot.get_gui_inferred_kind_by_slot(target_seat)
    unplayable_slots = bot.get_gui_unplayable_slots(target_seat)
    chop_slot = bot.get_gui_chop_slot(target_seat)
    recommended_slot = bot.get_gui_recommended_slot(target_seat)
    settings = game.settings
    common_view = state.common_view

    overlays: Dict[int, ConventionSlotOverlay] = {}
    for slot, card in enumerate(hand.cards):
        kind = kinds.get(slot)
        is_chop = chop_slot == slot
        is_unplayable = slot in unplayable_slots
        is_recommended = recommended_slot == slot
        if kind is None and not is_chop and not is_unplayable and not is_recommended:
            continue
        kind_mismatch = False
        if kind is not None:
            actual = common_view.card_kind(card, settings)
            kind_mismatch = kind != actual
        overlays[slot] = ConventionSlotOverlay(
            kind=kind,
            is_chop=is_chop,
            is_unplayable=is_unplayable,
            is_recommended=is_recommended,
            kind_mismatch=kind_mismatch,
        )
    return overlays
