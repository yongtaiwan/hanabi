"""
Full-information cheater with a fixed index-first action priority list (paper-style tiers).

See :class:`~hanabi.core.player.Cheater` — :meth:`play` takes :class:`~hanabi.core.game.GameState`.
"""

from __future__ import annotations

import logging
from typing import Dict, List

from hanabi.core.card import Card
from hanabi.core.enums import CardKind
from hanabi.core.game import CommonView, GameState, Hand, PlayerView
from hanabi.core.move_generation import generate_all_valid_moves
from hanabi.core.move_validation import is_move_legal_from_view
from hanabi.core.moves import ColorHint, Discard, Move, NumberHint, Play, move_with_why
from hanabi.core.player import Cheater

logger = logging.getLogger(__name__)


def _player_view_from_state(state: GameState, player_index: int) -> PlayerView:
    teammates: Dict[int, Hand] = {}
    for i, hand in enumerate(state.player_hands):
        if i != player_index:
            teammates[i] = hand
    own_hand_size = len(state.player_hands[player_index].cards)
    return PlayerView(teammates, own_hand_size)


def _total_discarded_card_count(common: CommonView) -> int:
    """Total number of cards in the discard piles (all colors)."""
    n = 0
    for suit in common.cards_discarded.values():
        n += sum(suit.cards.values())
    return n


def _pick_hint_deterministic(hints: List[Move]) -> Move:
    def hint_key(m: Move):
        if isinstance(m, ColorHint):
            return (0, m.teammate, m.color.value, tuple(sorted(m.cards)))
        if isinstance(m, NumberHint):
            return (1, m.teammate, m.number.value, tuple(sorted(m.cards)))
        assert False, f"unexpected hint {type(m)}"

    hints.sort(key=hint_key)
    return hints[0]


class PaperCheater(Cheater):
    """
    Cheater policy (priority order):

    1. Play the playable card with the **lowest hand index**.
    2. If fewer than **five** cards have been discarded globally and discards are legal,
       discard a **USELESS** card with the lowest index.
    3. If **hint tokens** remain, give a legal hint (deterministic tie-break).
    4. Discard a **USELESS** card with the lowest index.
    5. Discard a **duplicate** (same color/rank as a card in another player's hand),
       lowest index.
    6. Discard a **non-CRITICAL** card (any kind except ``CardKind.CRITICAL``), lowest index.
    7. Discard hand slot **0** (C1) if that discard is legal.

    Hanabi rule: at maximum hint tokens, discards are not generated; hints or plays are required.
    """

    def play(self, state: GameState) -> Move:
        idx = self.player_index
        player_view = _player_view_from_state(state, idx)
        common = state.common_view
        settings = state.settings
        discard_allowed = common.hint_tokens < settings.max_hint_tokens

        valid_moves = generate_all_valid_moves(player_view, common, settings, idx)
        valid_moves = [m for m in valid_moves if self._is_move_legal(state, player_view, m)]
        assert valid_moves, "PaperCheater: no legal moves"

        winning_plays = [
            m for m in valid_moves if isinstance(m, Play) and self._play_would_succeed(state, idx, m)
        ]
        if winning_plays:
            chosen = min(winning_plays, key=lambda m: m.card)
            return move_with_why(chosen, f"tier 1 (playable, lowest index): Play({chosen.card})")

        if _total_discarded_card_count(common) < 5 and discard_allowed:
            useless = self._useless_discards(valid_moves, state, idx)
            if useless:
                chosen = min(useless, key=lambda m: m.card)
                return move_with_why(
                    chosen, f"tier 2 (early-game USELESS discard, <5 discarded): Discard({chosen.card})"
                )

        if 0 < common.hint_tokens:
            hint_moves = [m for m in valid_moves if isinstance(m, (ColorHint, NumberHint))]
            legal_hints = [m for m in hint_moves if self._is_move_legal(state, player_view, m)]
            if legal_hints:
                chosen = _pick_hint_deterministic(legal_hints)
                return move_with_why(chosen, "tier 3 (hint, deterministic tiebreak): spend a hint token")

        if discard_allowed:
            useless = self._useless_discards(valid_moves, state, idx)
            if useless:
                chosen = min(useless, key=lambda m: m.card)
                return move_with_why(chosen, f"tier 4 (USELESS discard, lowest index): Discard({chosen.card})")

        if discard_allowed:
            duplicate_discards = self._duplicate_teammate_discards(valid_moves, state, idx)
            if duplicate_discards:
                chosen = min(duplicate_discards, key=lambda m: m.card)
                return move_with_why(
                    chosen, f"tier 5 (duplicate-of-teammate discard, lowest index): Discard({chosen.card})"
                )

        if discard_allowed:
            non_critical = [
                m
                for m in valid_moves
                if isinstance(m, Discard)
                and CardKind.CRITICAL != self._card_kind_at_index(state, idx, m.card)
            ]
            if non_critical:
                chosen = min(non_critical, key=lambda m: m.card)
                return move_with_why(
                    chosen, f"tier 6 (non-critical discard, lowest index): Discard({chosen.card})"
                )

        if discard_allowed:
            for m in valid_moves:
                if isinstance(m, Discard) and 0 == m.card:
                    return move_with_why(m, "tier 7 (C1 discard fallback): Discard(0)")

        logger.warning("PaperCheater falling back to first valid move")
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

    def _useless_discards(self, valid_moves: List[Move], state: GameState, player_index: int) -> List[Discard]:
        return [
            m
            for m in valid_moves
            if isinstance(m, Discard) and CardKind.USELESS == self._card_kind_at_index(state, player_index, m.card)
        ]

    def _duplicate_teammate_discards(
        self, valid_moves: List[Move], state: GameState, player_index: int
    ) -> List[Discard]:
        out: List[Discard] = []
        for m in valid_moves:
            if not isinstance(m, Discard):
                continue
            card = state.player_hands[player_index].cards[m.card]
            if self._same_card_in_other_hand(state, player_index, card):
                out.append(m)
        return out

    def _same_card_in_other_hand(self, state: GameState, player_index: int, card: Card) -> bool:
        for i, hand in enumerate(state.player_hands):
            if i == player_index:
                continue
            for c in hand.cards:
                if c == card:
                    return True
        return False
