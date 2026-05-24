"""
Team-visible card possibilities per hand slot, driven by public state and hints.

Maintains ``slot_possibilities[player][slot] -> Set[Card]``. Slots can be **known**
(singleton from visible hands) or **unknown** (marginal candidates still consistent
with fireworks, discards, and copies not fixed elsewhere).

**Hints:** a color/number hint lists every matching card in the receiver’s hand at
that moment. Touched indices must have that color/rank; every other index in the
hand must **not** have it (standard Hanabi inference).

**Plays / draws:** update :meth:`PublicKnowledgeTracker.set_common_view`, then
:meth:`PublicKnowledgeTracker.shift_after_remove_and_draw` with the optional face-up
draw if known.
"""

from __future__ import annotations

from collections import Counter
from typing import Dict, List, Optional, Sequence, Set

from hanabi.core.card import Card
from hanabi.core.enums import Color, Number
from hanabi.core.game import CommonView, GameSettings


def _full_deck_counter(settings: GameSettings) -> Counter[Card]:
    ctr: Counter[Card] = Counter()
    for color, suit in settings.cards.items():
        for rank, qty in suit.cards.items():
            ctr.update([Card(color, rank)] * qty)
    return ctr


def _subtract_fireworks(ctr: Counter[Card], cards_played: Dict[Color, Number]) -> None:
    for color, top in cards_played.items():
        for v in range(1, top.value + 1):
            c = Card(color, Number(v))
            assert 0 < ctr[c], f"fireworks impossible: not enough {c} in pool"
            ctr[c] -= 1


def _subtract_discards(ctr: Counter[Card], common_view: CommonView) -> None:
    for color, suit in common_view.cards_discarded.items():
        for rank, qty in suit.cards.items():
            for _ in range(qty):
                c = Card(color, rank)
                assert 0 < ctr[c], f"discard impossible: not enough {c} in pool"
                ctr[c] -= 1


def _marginal_candidates(ctr: Counter[Card]) -> Set[Card]:
    return {c for c, n in ctr.items() if 0 < n}


def _fixed_remaining_counter(
    settings: GameSettings,
    common_view: CommonView,
    slot_masks: Sequence[Sequence[Optional[Card]]],
) -> Counter[Card]:
    ctr = _full_deck_counter(settings)
    _subtract_fireworks(ctr, common_view.cards_played)
    _subtract_discards(ctr, common_view)
    for player_row in slot_masks:
        for fixed in player_row:
            if fixed is not None:
                assert 0 < ctr[fixed], f"too many fixed {fixed} for remaining pool"
                ctr[fixed] -= 1
    return ctr


def _snapshot_masks_from_slots(slots: Sequence[Sequence[Set[Card]]]) -> List[List[Optional[Card]]]:
    return [[_singleton_or_none(s) for s in row] for row in slots]


def _singleton_or_none(s: Set[Card]) -> Optional[Card]:
    if 1 == len(s):
        return next(iter(s))
    return None


class PublicKnowledgeTracker:
    """
    Per-player per-slot possible cards from public information.

    Unknown slots start as every card type that still has a physical copy left after
    fireworks, discards, and known singleton slots elsewhere.
    """

    def __init__(self, settings: GameSettings, common_view: CommonView) -> None:
        self._settings = settings
        self._common_view = common_view
        self._slots: List[List[Set[Card]]] = []

    @property
    def common_view(self) -> CommonView:
        return self._common_view

    def slot_possibilities(self, player_index: int) -> List[Set[Card]]:
        """Copy of possibility sets for ``player_index`` (one set per hand slot)."""
        return [set(s) for s in self._slots[player_index]]

    def bootstrap_from_masks(self, slot_masks: Sequence[Sequence[Optional[Card]]]) -> None:
        """
        Initialize all players from optional known cards per slot.

        ``slot_masks[p][i]`` is the visible card at that slot, or ``None`` if unknown.
        """
        num_players = len(slot_masks)
        assert num_players == self._settings.num_players
        ctr = _fixed_remaining_counter(self._settings, self._common_view, slot_masks)
        marginal = _marginal_candidates(ctr)
        self._slots = []
        for p in range(num_players):
            row: List[Set[Card]] = []
            for i in range(len(slot_masks[p])):
                fixed = slot_masks[p][i]
                row.append({fixed} if fixed is not None else set(marginal))
            self._slots.append(row)

    def set_common_view(self, common_view: CommonView) -> None:
        """After plays/discards, update shared view and prune impossible card types."""
        self._common_view = common_view
        self._prune_impossible_cards()

    def apply_color_hint(self, receiver: int, touched_indices: Sequence[int], color: Color) -> None:
        """Apply one color hint (touched must be ``color``; untouched must not)."""
        row = self._slots[receiver]
        hand_size = len(row)
        touched = set(touched_indices)
        for i in range(hand_size):
            if i in touched:
                row[i] = {c for c in row[i] if color == c.color}
            else:
                row[i] = {c for c in row[i] if color != c.color}
            assert row[i], "empty possibility set after color hint"

    def apply_number_hint(self, receiver: int, touched_indices: Sequence[int], rank: Number) -> None:
        """Apply one number hint (touched must be ``rank``; untouched must not)."""
        row = self._slots[receiver]
        hand_size = len(row)
        touched = set(touched_indices)
        for i in range(hand_size):
            if i in touched:
                row[i] = {c for c in row[i] if rank == c.number}
            else:
                row[i] = {c for c in row[i] if rank != c.number}
            assert row[i], "empty possibility set after number hint"

    def replace_player_row(self, player_index: int, slot_masks: Sequence[Optional[Card]]) -> None:
        """Rebuild one player’s row from known / unknown slots (e.g. after dealing)."""
        full_masks = _snapshot_masks_from_slots(self._slots)
        full_masks[player_index] = list(slot_masks)
        ctr = _fixed_remaining_counter(self._settings, self._common_view, full_masks)
        marginal = _marginal_candidates(ctr)
        row: List[Set[Card]] = []
        for fixed in slot_masks:
            row.append({fixed} if fixed is not None else set(marginal))
        self._slots[player_index] = row

    def shift_after_remove_and_draw(
        self,
        player_index: int,
        removed_index: int,
        new_common_view: CommonView,
        *,
        drawn_card: Optional[Card],
    ) -> None:
        """
        Pop ``removed_index``, shift indices down, append one right slot.

        If ``drawn_card`` is ``None`` (face-down draw), the new slot gets a fresh
        marginal set from updated fireworks/discards; it carries no hint metadata yet.
        """
        self._common_view = new_common_view
        row = self._slots[player_index]
        assert 0 <= removed_index < len(row)
        shifted = [set(row[i]) for i in range(removed_index)] + [set(row[i]) for i in range(removed_index + 1, len(row))]
        full_masks = _snapshot_masks_from_slots(self._slots)
        draw_mask = drawn_card if drawn_card is not None else None
        full_masks[player_index] = [_singleton_or_none(s) for s in shifted] + [draw_mask]
        ctr = _fixed_remaining_counter(self._settings, self._common_view, full_masks)
        new_slot = {drawn_card} if drawn_card is not None else _marginal_candidates(ctr)
        self._slots[player_index] = shifted + [new_slot]
        self._prune_impossible_cards()

    def _prune_impossible_cards(self) -> None:
        masks = _snapshot_masks_from_slots(self._slots)
        ctr = _fixed_remaining_counter(self._settings, self._common_view, masks)
        impossible = {c for c in ctr if ctr[c] <= 0}
        if not impossible:
            return
        for row in self._slots:
            for i in range(len(row)):
                row[i] -= impossible
                assert row[i], "prune eliminated all possibilities for a slot"
