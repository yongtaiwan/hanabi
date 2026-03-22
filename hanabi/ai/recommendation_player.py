"""
Recommendation strategy AI player for Hanabi.

Implements Strategy 1 from the paper "How to Make the Perfect Fireworks Display:
Two Strategies for Hanabi" by Cox et al. (Mathematics Magazine, 2015).

The strategy uses a hat-guessing / network-coding scheme: a single hint encodes
a value 0-7 that allows every other player to decode their personal recommendation
(play C1-C4 or discard C1-C4). Card positions follow the paper: C1 = leftmost (oldest),
C4 = rightmost (newest). In this codebase, index 0 = newest (C4), index hand_size-1 = oldest (C1).

This encoding only supports 4 card positions (0-3 play, 4-7 discard). This player is
only supported for standard 5-player games (4 cards per hand).
"""

from __future__ import annotations

from typing import Dict, List, Optional
from collections import Counter

# Recommendation encoding 0-7 only covers 4 card slots (C1-C4). Used with standard
# 5-player rules (4 cards per hand).
HAND_SIZE_FOR_RECOMMENDATION = 4

from hanabi.core.player import BasePlayer
from hanabi.core.game import PlayerView, CommonView, GameSettings
from hanabi.core.moves import Move, Play, Discard, ColorHint, NumberHint
from hanabi.core.enums import Color, Number
from hanabi.core.card import Card
from hanabi.core.move_generation import generate_all_valid_moves

# Recommendation encoding (paper): 0=Play C1, 1=Play C2, 2=Play C3, 3=Play C4,
# 4=Discard C1, 5=Discard C2, 6=Discard C3, 7=Discard C4.
# Hint encoding: 0-3 = rank hint to player at position 1-4 (clockwise from hinter),
# 4-7 = suit hint to position 1-4.


def rec_to_play_index(rec: int, hand_size: int) -> Optional[int]:
    if 0 <= rec <= 3:
        return (hand_size - 1) - rec
    return None


def rec_to_discard_index(rec: int, hand_size: int) -> Optional[int]:
    if 4 <= rec <= 7:
        return (hand_size - 1) - (rec - 4)
    return None


def _slot_name(internal_idx: int, hand_size: int) -> str:
    """Paper-style slot name: C1 (leftmost/oldest) .. C4 (rightmost/newest)."""
    rec = (hand_size - 1) - internal_idx
    return f"C{rec + 1}"


class RecommendationPlayer(BasePlayer):
    """
    Recommendation strategy from Cox et al. (paper Strategy 1).

    Only for standard 5-player games (4 cards per hand).
    """

    @classmethod
    def supports_game_settings(cls, game_settings: GameSettings) -> bool:
        return game_settings.numPlayers == 5

    def __init__(self, player_index: int):
        super().__init__(player_index)
        self._last_hint_value: Optional[int] = None
        self._last_hinter: Optional[int] = None
        self._last_hint_move: Optional[Move] = None
        self._plays_since_hint: int = 0
        self._last_decision_summary: Optional[str] = None
        # Decoded recommendation at hint time (state when hint was given); used until next hint.
        self._my_decoded_recommendation: Optional[int] = None

    def observe(self, player_index: int, move: Move, **kwargs) -> None:
        assert self.gameSettings.numPlayers == 5, "RecommendationPlayer requires 5-player games"
        super().observe(player_index, move, **kwargs)
        if isinstance(move, (ColorHint, NumberHint)):
            self._last_hinter = player_index
            self._last_hint_move = move
            n = self.gameSettings.numPlayers
            pos = (move.teammate - player_index - 1) % n
            if pos < 0:
                pos += n
            self._last_hint_value = pos if isinstance(move, NumberHint) else (4 + pos)
            self._plays_since_hint = 0
            # Decode our recommendation using state at hint time (critical: hands unchanged yet).
            game = kwargs.get("game")
            if game is not None and self._player_index != player_index:
                view_at_hint = game._getPlayerView(self._player_index)
                self._my_decoded_recommendation = self._decode_recommendation_with_view(
                    view_at_hint, self._last_hint_value, self._last_hinter
                )
            elif player_index == self._player_index:
                # We are the hinter; clear so we don't use a stale recommendation until next hint to us
                self._my_decoded_recommendation = None
        elif isinstance(move, Play):
            self._plays_since_hint += 1

    def _decode_recommendation_with_view(
        self, player_view: PlayerView, hint_value: int, hinter: Optional[int]
    ) -> Optional[int]:
        """Decode my recommendation from hint value using the given view (must be state at hint time)."""
        common = self.commonView
        settings = self.gameSettings
        n = settings.numPlayers
        in_hand = self._count_cards_in_hands(player_view)
        others_sum = 0
        for p in range(n):
            if p == self._player_index:
                continue
            if p not in player_view.teammates:
                continue
            hand = player_view.teammates[p].cards
            rec = self._get_recommendation_for_hand(hand, common, settings, in_hand)
            others_sum += rec
        rec_hinter = 0
        if hinter is not None and hinter in player_view.teammates:
            rec_hinter = self._get_recommendation_for_hand(
                player_view.teammates[hinter].cards,
                common, settings, in_hand,
            )
        return (hint_value - others_sum + rec_hinter) % 8

    def _get_my_recommendation(self, player_view: PlayerView) -> Optional[int]:
        """Return my recommendation: use decoded value from hint time if set, else decode from current view (may be wrong after other moves)."""
        if self._my_decoded_recommendation is not None:
            return self._my_decoded_recommendation
        if self._last_hint_value is None or self._last_hinter is None or self._last_hint_move is None:
            return None
        return self._decode_recommendation_with_view(
            player_view, self._last_hint_value, self._last_hinter
        )

    def _count_cards_in_hands(self, player_view: PlayerView) -> Counter:
        c: Counter = Counter()
        for hand in player_view.teammates.values():
            for card in hand.cards:
                c[card] += 1
        return c

    def _is_playable(self, card: Card, common_view: CommonView) -> bool:
        played = common_view.cardsPlayed
        if card.color not in played:
            return card.number == Number.ONE
        return card.number.value == played[card.color].value + 1

    def _is_dead(self, card: Card, common_view: CommonView) -> bool:
        played = common_view.cardsPlayed
        if card.color not in played:
            return False
        return card.number.value <= played[card.color].value

    def _is_indispensable(
        self,
        card: Card,
        common_view: CommonView,
        settings: GameSettings,
        in_hand_counts: Dict[Card, int],
    ) -> bool:
        total = settings.cards[card.color].cards.get(card.number, 0)
        disc = common_view.cardsDiscarded.get(card.color)
        discarded = disc.cards.get(card.number, 0) if disc else 0
        played = common_view.cardsPlayed.get(card.color)
        if played and played.value >= card.number.value:
            played_copies = 1
        else:
            played_copies = 0
        # Indispensable if this is the last copy (discarding would make perfect score impossible)
        remaining = total - discarded - played_copies
        return remaining <= 1

    def _get_recommendation_for_hand(
        self,
        hand_cards: List[Card],
        common_view: CommonView,
        settings: GameSettings,
        in_hand_counts: Counter,
    ) -> int:
        hand_size = len(hand_cards)
        order_c1_first = list(range(hand_size - 1, -1, -1))

        for idx in order_c1_first:
            card = hand_cards[idx]
            if card.number == Number.FIVE and self._is_playable(card, common_view):
                return (hand_size - 1) - idx
        playable = [
            (idx, hand_cards[idx].number.value)
            for idx in order_c1_first
            if self._is_playable(hand_cards[idx], common_view)
        ]
        if playable:
            playable.sort(key=lambda x: (x[1], x[0]))
            idx = playable[0][0]
            return (hand_size - 1) - idx
        for idx in order_c1_first:
            if self._is_dead(hand_cards[idx], common_view):
                return 4 + ((hand_size - 1) - idx)
        dispensable = [
            (idx, hand_cards[idx].number.value)
            for idx in order_c1_first
            if not self._is_indispensable(
                hand_cards[idx], common_view, settings, dict(in_hand_counts)
            )
        ]
        if dispensable:
            dispensable.sort(key=lambda x: (-x[1], x[0]))
            idx = dispensable[0][0]
            return 4 + ((hand_size - 1) - idx)
        return 4 + (hand_size - 1)

    def play(self, player_view: PlayerView) -> Move:
        common = self.commonView
        settings = self.gameSettings
        hand_size = player_view.ownHandSize
        assert settings.numPlayers == 5, "RecommendationPlayer requires 5-player games"
        assert hand_size == HAND_SIZE_FOR_RECOMMENDATION
        errors = settings.maxLiveTokens - common.liveTokens

        # Get my decoded recommendation
        my_rec = self._get_my_recommendation(player_view)
        valid_moves = generate_all_valid_moves(
            player_view, common, settings, self._player_index
        )
        valid_moves = [m for m in valid_moves if self._is_move_valid(m, player_view)]

        if not valid_moves:
            self._last_decision_summary = "No valid moves; play or discard index 0"
            return Play(0) if hand_size > 0 else Discard(0)

        # Action algorithm (paper order)
        # 1) If most recent recommendation was play and no card played since last hint -> play recommended
        if my_rec is not None and 0 <= my_rec <= 3:
            play_idx = rec_to_play_index(my_rec, hand_size)
            if play_idx is not None and self._plays_since_hint == 0:
                if any(isinstance(m, Play) and m.card == play_idx for m in valid_moves):
                    slot = _slot_name(play_idx, hand_size)
                    self._last_decision_summary = (
                        f"Play {slot}: decoded recommendation={my_rec} (play), "
                        "no card played since last hint → follow recommendation"
                    )
                    return Play(play_idx)

        # 2) If most recent recommendation was play, one card played since hint, and <2 errors -> play recommended
        if my_rec is not None and 0 <= my_rec <= 3 and errors < 2 and self._plays_since_hint == 1:
            play_idx = rec_to_play_index(my_rec, hand_size)
            if play_idx is not None:
                if any(isinstance(m, Play) and m.card == play_idx for m in valid_moves):
                    slot = _slot_name(play_idx, hand_size)
                    self._last_decision_summary = (
                        f"Play {slot}: decoded recommendation={my_rec} (play), "
                        "one card played since hint and <2 errors → follow recommendation"
                    )
                    return Play(play_idx)

        # 3) If hint token available, give hint
        if common.hintTokens > 0:
            hint_move = self._compute_hint(player_view)
            if hint_move is not None:
                self._my_decoded_recommendation = None  # we are giving the hint; no recommendation for us from it
                if isinstance(hint_move, ColorHint):
                    self._last_decision_summary = (
                        f"Hint: give color {hint_move.color.name.lower()} to P{hint_move.teammate + 1} "
                        "(encodes sum of all others' recommendations mod 8; each teammate decodes their own)"
                    )
                else:
                    self._last_decision_summary = (
                        f"Hint: give number {hint_move.number.value} to P{hint_move.teammate + 1} "
                        "(encodes sum of all others' recommendations mod 8; each teammate decodes their own)"
                    )
                return hint_move

        # 4) If most recent recommendation was discard -> discard that card
        if my_rec is not None and 4 <= my_rec <= 7:
            discard_idx = rec_to_discard_index(my_rec, hand_size)
            if discard_idx is not None:
                if any(
                    isinstance(m, Discard) and m.card == discard_idx for m in valid_moves
                ):
                    slot = _slot_name(discard_idx, hand_size)
                    self._last_decision_summary = (
                        f"Discard {slot}: decoded recommendation={my_rec} (discard) → follow recommendation"
                    )
                    return Discard(discard_idx)

        # 5) Discard C1
        c1_idx = hand_size - 1
        for m in valid_moves:
            if isinstance(m, Discard) and m.card == c1_idx:
                self._last_decision_summary = (
                    "Discard C1 (oldest): no hint tokens or action algorithm rule 5 (default discard C1)"
                )
                return m

        # Fallback: first valid move
        m = valid_moves[0]
        if isinstance(m, Play):
            self._last_decision_summary = f"Fallback: play card at index {m.card}"
        elif isinstance(m, Discard):
            self._last_decision_summary = f"Fallback: discard card at index {m.card}"
        else:
            self._last_decision_summary = "Fallback: first valid move (hint)"
        return m

    def _compute_hint(self, player_view: PlayerView) -> Optional[Move]:
        """Compute hint that encodes sum of recommendations mod 8."""
        common = self.commonView
        settings = self.gameSettings
        n = settings.numPlayers
        in_hand = self._count_cards_in_hands(player_view)
        total = 0
        for p in range(n):
            if p == self._player_index:
                continue
            if p not in player_view.teammates:
                continue
            hand = player_view.teammates[p].cards
            rec = self._get_recommendation_for_hand(hand, common, settings, in_hand)
            total += rec
        value = total % 8
        pos_0, is_number = (value, True) if value < 4 else (value - 4, False)
        target = (self._player_index + 1 + pos_0) % n
        if target not in player_view.teammates:
            return None
        hand = player_view.teammates[target]
        if not hand.cards:
            return None
        if is_number:
            # Pick a number that appears in target's hand
            for num in Number:
                indices = [i for i, c in enumerate(hand.cards) if c.number == num]
                if indices:
                    return NumberHint(target, indices, num)
        else:
            for color in Color:
                if color == Color.MULTI:
                    continue
                indices = [i for i, c in enumerate(hand.cards) if c.color == color]
                if indices:
                    return ColorHint(target, indices, color)
        return None

    def get_decision_summary(self) -> Optional[str]:
        """Return a short explanation of the last move for console/GUI display."""
        return self._last_decision_summary

    def _is_move_valid(self, move: Move, player_view: PlayerView) -> bool:
        common = self.commonView
        settings = self.gameSettings
        hand_size = player_view.ownHandSize
        if isinstance(move, Play):
            return 0 <= move.card < hand_size
        if isinstance(move, Discard):
            if move.card < 0 or move.card >= hand_size:
                return False
            return common.hintTokens < settings.maxHintTokens
        if isinstance(move, (ColorHint, NumberHint)):
            if common.hintTokens <= 0:
                return False
            if move.teammate not in player_view.teammates or move.teammate == self._player_index:
                return False
            if not move.cards:
                return False
            thand = player_view.teammates[move.teammate]
            for i in move.cards:
                if i < 0 or i >= len(thand.cards):
                    return False
            if isinstance(move, ColorHint):
                if any(thand.cards[i].color != move.color for i in move.cards):
                    return False
            else:
                if any(thand.cards[i].number != move.number for i in move.cards):
                    return False
            return True
        return False
