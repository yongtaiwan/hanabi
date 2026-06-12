"""
Common-sense full-information (cheater) policy.

See :class:`~hanabi.core.player.Cheater` — :meth:`play` takes :class:`~hanabi.core.game.GameState`.
"""

from __future__ import annotations

import copy
import logging
from typing import Dict, List, Optional, Tuple

from hanabi.core.card import Card
from hanabi.core.enums import CardKind, Color, Number
from hanabi.core.game import GameState, Hand, PlayerView
from hanabi.core.move_generation import generate_all_valid_moves
from hanabi.core.move_validation import is_move_legal_from_view
from hanabi.core.moves import ColorHint, Discard, Move, NumberHint, Play, move_with_why
from hanabi.core.player import Cheater

logger = logging.getLogger(__name__)

_PLAY_RANK_ORDER: Dict[Number, int] = {
    Number.FIVE: 0,
    Number.ONE: 1,
    Number.TWO: 2,
    Number.THREE: 3,
    Number.FOUR: 4,
}

_NONCRITICAL_DISCARD_RANK_ORDER: Dict[Number, int] = {
    Number.FOUR: 0,
    Number.THREE: 1,
    Number.TWO: 2,
    Number.ONE: 3,
    Number.FIVE: 4,
}

_CRITICAL_DISCARD_RANK_ORDER: Dict[Number, int] = {
    Number.FIVE: 0,
    Number.FOUR: 1,
    Number.THREE: 2,
    Number.TWO: 3,
    Number.ONE: 4,
}

_COLOR_SORT_KEY: Dict[Color, int] = {c: i for i, c in enumerate(Color)}


def _player_view_from_state(state: GameState, player_index: int) -> PlayerView:
    teammates: Dict[int, Hand] = {}
    for i, hand in enumerate(state.player_hands):
        if i != player_index:
            teammates[i] = hand
    own_hand_size = len(state.player_hands[player_index].cards)
    return PlayerView(teammates, own_hand_size)


class CommonSenseCheater(Cheater):
    """
    Cheater policy: maximize newly playable cards when playing (tie 51234); discards
    useless, redundant non-critical, hint, solo non-critical, critical; discard ties
    4321 / 54321. Chop not used.

    Hanabi rule: when hint tokens are at the maximum, **discard is illegal** (no discard
    moves exist).     The hand may still contain ``CardKind.USELESS`` cards; in that case we **must**
    spend a hint (or play) before any useless discard
    becomes legal. That can look like "hinting while holding trash" but is forced by the
    rules, not a policy inversion. When discards are legal, USELESS is always preferred
    over hints (see tiers below).
    """

    def play(self, state: GameState) -> Move:
        idx = self.player_index
        player_view = _player_view_from_state(state, idx)
        common = state.common_view
        settings = state.settings
        discard_allowed = common.hint_tokens < settings.max_hint_tokens

        valid_moves = generate_all_valid_moves(player_view, common, settings, idx)
        valid_moves = [m for m in valid_moves if self._is_move_legal(state, player_view, m)]
        assert valid_moves, "CommonSenseCheater: no legal moves"

        playable_plays = [m for m in valid_moves if isinstance(m, Play) and self._play_would_succeed(state, idx, m)]
        if playable_plays:
            chosen = self._choose_play(playable_plays, state, idx)
            return move_with_why(
                chosen, f"tier 1 (playable plays): max newly-playable delta, tiebreak 51234 → Play({chosen.card})"
            )

        # USELESS discards only appear in valid_moves when discard_allowed (see move_generation).
        useless_discards = [
            m
            for m in valid_moves
            if isinstance(m, Discard) and CardKind.USELESS == self._card_kind_at_index(state, idx, m.card)
        ]
        if useless_discards:
            assert discard_allowed, "discard moves present implies discard_allowed"
            chosen = self._pick_discard_by_rank_order(useless_discards, state, idx, _NONCRITICAL_DISCARD_RANK_ORDER)
            return move_with_why(chosen, f"tier 2 (USELESS discard, 4321 rank): Discard({chosen.card})")

        redundant_discards = [
            m
            for m in valid_moves
            if isinstance(m, Discard) and self._is_redundant_non_critical_discard(state, idx, m.card)
        ]
        if redundant_discards:
            assert discard_allowed, "discard moves present implies discard_allowed"
            chosen = self._pick_discard_by_rank_order(redundant_discards, state, idx, _NONCRITICAL_DISCARD_RANK_ORDER)
            return move_with_why(
                chosen, f"tier 3 (redundant non-critical discard, copy elsewhere): Discard({chosen.card})"
            )

        # When not discard_allowed, we often reach here with USELESS cards still in hand;
        # spending a hint is required to unlock discards (or wait for a firework bonus).
        hint_moves = [m for m in valid_moves if isinstance(m, (ColorHint, NumberHint))]
        if hint_moves and 0 < common.hint_tokens:
            legal_hints = [m for m in hint_moves if self._is_move_legal(state, player_view, m)]
            if legal_hints:
                chosen = self._pick_hint_deterministic(legal_hints)
                return move_with_why(chosen, "tier 4 (hint, deterministic tiebreak): spend a hint token")

        solo_noncrit = [
            m
            for m in valid_moves
            if isinstance(m, Discard) and self._is_solo_non_critical_discard(state, idx, m.card)
        ]
        if solo_noncrit:
            assert discard_allowed, "discard moves present implies discard_allowed"
            chosen = self._pick_discard_by_rank_order(solo_noncrit, state, idx, _NONCRITICAL_DISCARD_RANK_ORDER)
            return move_with_why(
                chosen, f"tier 5 (solo non-critical discard, 4321 rank): Discard({chosen.card})"
            )

        critical_discards = [
            m
            for m in valid_moves
            if isinstance(m, Discard) and CardKind.CRITICAL == self._card_kind_at_index(state, idx, m.card)
        ]
        if critical_discards:
            assert discard_allowed, "discard moves present implies discard_allowed"
            chosen = self._pick_discard_by_rank_order(critical_discards, state, idx, _CRITICAL_DISCARD_RANK_ORDER)
            return move_with_why(
                chosen, f"tier 6 (CRITICAL discard, 54321 rank, last resort): Discard({chosen.card})"
            )

        logger.warning("CommonSenseCheater falling back to first valid move")
        return move_with_why(valid_moves[0], "fallback: first valid move (all tiers exhausted)")

    def _is_move_legal(self, state: GameState, player_view: PlayerView, move: Move) -> bool:
        return is_move_legal_from_view(
            move,
            player_view=player_view,
            common_view=state.common_view,
            game_settings=state.settings,
            player_index=self.player_index,
        )

    def _play_would_succeed(self, state: GameState, player_index: int, move: Play) -> bool:
        hand = state.player_hands[player_index].cards
        assert 0 <= move.card < len(hand), "play index out of range"
        card = hand[move.card]
        return CardKind.PLAYABLE == state.common_view.card_kind(card, state.settings)

    def _card_kind_at_index(self, state: GameState, player_index: int, card_index: int) -> CardKind:
        hand = state.player_hands[player_index].cards
        card = hand[card_index]
        return state.common_view.card_kind(card, state.settings)

    def _count_identity_in_hands(self, state: GameState, card: Card) -> int:
        n = 0
        for hand in state.player_hands:
            for c in hand.cards:
                if c.color == card.color and c.number == card.number:
                    n += 1
        return n

    def _is_redundant_non_critical_discard(self, state: GameState, player_index: int, card_index: int) -> bool:
        kind = self._card_kind_at_index(state, player_index, card_index)
        if CardKind.USELESS == kind or CardKind.CRITICAL == kind:
            return False
        card = state.player_hands[player_index].cards[card_index]
        return self._count_identity_in_hands(state, card) >= 2

    def _is_solo_non_critical_discard(self, state: GameState, player_index: int, card_index: int) -> bool:
        kind = self._card_kind_at_index(state, player_index, card_index)
        if CardKind.USELESS == kind or CardKind.CRITICAL == kind:
            return False
        card = state.player_hands[player_index].cards[card_index]
        return 1 == self._count_identity_in_hands(state, card)

    def _count_playable_cards(self, state: GameState) -> int:
        settings = state.settings
        cv = state.common_view
        n = 0
        for hand in state.player_hands:
            for card in hand.cards:
                if CardKind.PLAYABLE == cv.card_kind(card, settings):
                    n += 1
        return n

    def _choose_play(self, playable_plays: List[Play], state: GameState, player_index: int) -> Play:
        before = self._count_playable_cards(state)
        best_delta: Optional[int] = None
        candidates: List[Play] = []

        for move in playable_plays:
            sim = copy.deepcopy(state)
            sim.update(player_index, move)
            delta = self._count_playable_cards(sim) - before
            if best_delta is None or delta > best_delta:
                best_delta = delta
                candidates = [move]
            elif delta == best_delta:
                candidates.append(move)
        assert candidates, "CommonSenseCheater._choose_play: no play candidates"

        def play_sort_key(m: Play) -> Tuple[int, int, int]:
            card = state.player_hands[player_index].cards[m.card]
            ro = _PLAY_RANK_ORDER.get(card.number, 99)
            co = _COLOR_SORT_KEY.get(card.color, 99)
            return (ro, co, m.card)

        candidates.sort(key=play_sort_key)
        return candidates[0]

    def _pick_discard_by_rank_order(
        self,
        discards: List[Discard],
        state: GameState,
        player_index: int,
        rank_order: Dict[Number, int],
    ) -> Discard:
        def sort_key(m: Discard) -> Tuple[int, int, int]:
            card = state.player_hands[player_index].cards[m.card]
            ro = rank_order.get(card.number, 99)
            co = _COLOR_SORT_KEY.get(card.color, 99)
            return (ro, co, m.card)

        discards.sort(key=sort_key)
        return discards[0]

    def _pick_hint_deterministic(self, hints: List[Move]) -> Move:
        def hint_key(m: Move) -> Tuple:
            if isinstance(m, ColorHint):
                return (0, m.teammate, m.color.value, tuple(sorted(m.cards)))
            if isinstance(m, NumberHint):
                return (1, m.teammate, m.number.value, tuple(sorted(m.cards)))
            assert False, f"unexpected hint {type(m)}"

        hints.sort(key=hint_key)
        return hints[0]
