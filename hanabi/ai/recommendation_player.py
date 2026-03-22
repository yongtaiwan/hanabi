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

from typing import List, Optional

# Recommendation encoding 0-7 only covers 4 card slots (C1-C4). Used with standard
# 5-player rules (4 cards per hand).
HAND_SIZE_FOR_RECOMMENDATION = 4
NUM_PLAYERS_FOR_RECOMMENDATION = 5

from hanabi.core.player import BasePlayer
from hanabi.core.game import CommonView, GameSettings, PlayerView
from hanabi.core.moves import Move, Play, Discard, ColorHint, NumberHint
from hanabi.core.enums import Color, Number, CardKind
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
        return game_settings.num_players == NUM_PLAYERS_FOR_RECOMMENDATION

    def __init__(self, player_index: int):
        super().__init__(player_index)
        self._last_hint_value: Optional[int] = None
        self._last_hinter: Optional[int] = None
        self._plays_since_hint: int = 0
        self._last_decision_summary: Optional[str] = None
        # Decoded recommendation at hint time (state when hint was given); used until next hint.
        self._my_decoded_recommendation: Optional[int] = None

    def set_game_settings(self, game_settings: GameSettings) -> None:
        assert game_settings.num_players == NUM_PLAYERS_FOR_RECOMMENDATION, (
            "RecommendationPlayer requires 5-player games"
        )
        super().set_game_settings(game_settings)

    def observe_play_move(self, player_index: int, move: Play, observer_view: PlayerView) -> None:
        super().observe_play_move(player_index, move, observer_view)
        self._plays_since_hint += 1

    def observe_color_hint_move(self, player_index: int, move: ColorHint, observer_view: PlayerView) -> None:
        super().observe_color_hint_move(player_index, move, observer_view)
        self._observe_recommendation_hint(player_index, move, observer_view, hint_value_base=4)

    def observe_number_hint_move(self, player_index: int, move: NumberHint, observer_view: PlayerView) -> None:
        super().observe_number_hint_move(player_index, move, observer_view)
        self._observe_recommendation_hint(player_index, move, observer_view, hint_value_base=0)

    def _observe_recommendation_hint(
        self,
        player_index: int,
        move: ColorHint | NumberHint,
        observer_view: PlayerView,
        *,
        hint_value_base: int,
    ) -> None:
        self._last_hinter = player_index
        pos = (move.teammate - player_index - 1) % NUM_PLAYERS_FOR_RECOMMENDATION
        self._last_hint_value = hint_value_base + pos
        self._plays_since_hint = 0
        self._my_decoded_recommendation = (
            None
            if self._player_index == player_index
            else (self._decode_recommendation_with_view(observer_view, self._last_hint_value, self._last_hinter))
        )

    def _decode_recommendation_with_view(
        self, player_view: PlayerView, hint_value: int, hinter: Optional[int]
    ) -> Optional[int]:
        """
        Decode my recommendation from hint value.

        Uses ``player_view`` for visible teammate hands and :attr:`BasePlayer.common_view`
        for shared piles and tokens (no access to full :class:`~hanabi.core.game.Game`).
        """
        others_sum = 0
        for p in range(NUM_PLAYERS_FOR_RECOMMENDATION):
            if p == self._player_index:
                continue
            if p not in player_view.teammates:
                continue
            hand = player_view.teammates[p].cards
            rec = self._get_recommendation_for_hand(
                hand, self.common_view, self.game_settings
            )
            others_sum += rec
        rec_hinter = 0
        if hinter is not None and hinter in player_view.teammates:
            rec_hinter = self._get_recommendation_for_hand(
                player_view.teammates[hinter].cards,
                self.common_view,
                self.game_settings,
            )
        return (hint_value - others_sum + rec_hinter) % 8

    def _get_my_recommendation(self, player_view: PlayerView) -> Optional[int]:
        """Return my recommendation from hint-time decode if set, else from current view.

        The fallback can be wrong after intervening moves.
        """
        if self._my_decoded_recommendation is not None:
            return self._my_decoded_recommendation
        if self._last_hint_value is None or self._last_hinter is None:
            return None
        return self._decode_recommendation_with_view(player_view, self._last_hint_value, self._last_hinter)

    def _get_recommendation_for_hand(
        self,
        hand_cards: List[Card],
        common_view: CommonView,
        settings: GameSettings,
    ) -> int:
        hand_size = len(hand_cards)
        order_c1_first = list(range(hand_size - 1, -1, -1))

        for idx in order_c1_first:
            card = hand_cards[idx]
            if card.number == Number.FIVE and common_view.card_kind(card, settings) == CardKind.PLAYABLE:
                return (hand_size - 1) - idx
        playable = [
            (idx, hand_cards[idx].number.value)
            for idx in order_c1_first
            if common_view.card_kind(hand_cards[idx], settings) == CardKind.PLAYABLE
        ]
        if playable:
            playable.sort(key=lambda x: (x[1], x[0]))
            idx = playable[0][0]
            return (hand_size - 1) - idx
        for idx in order_c1_first:
            if common_view.card_kind(hand_cards[idx], settings) == CardKind.USELESS:
                return 4 + ((hand_size - 1) - idx)
        dispensable = [
            (idx, hand_cards[idx].number.value)
            for idx in order_c1_first
            if common_view.card_kind(hand_cards[idx], settings) == CardKind.DISPENSABLE
        ]
        if dispensable:
            dispensable.sort(key=lambda x: (-x[1], x[0]))
            idx = dispensable[0][0]
            return 4 + ((hand_size - 1) - idx)
        return 4 + (hand_size - 1)

    def _paper_try_follow_play_recommendation(
        self,
        my_rec: Optional[int],
        hand_size: int,
        valid_moves: List[Move],
        *,
        plays_since_hint: int,
        errors: int,
    ) -> Optional[Move]:
        """
        Paper rules 1–2: if recommendation is play (0–3), follow it when
        (1) no play since last hint, or (2) one play since hint and errors < 2.
        """
        if my_rec is None or not (0 <= my_rec <= 3):
            return None
        play_idx = rec_to_play_index(my_rec, hand_size)
        if play_idx is None:
            return None
        if not any(isinstance(m, Play) and m.card == play_idx for m in valid_moves):
            return None

        if plays_since_hint == 0:
            slot = _slot_name(play_idx, hand_size)
            self._last_decision_summary = (
                f"Play {slot}: decoded recommendation={my_rec} (play), "
                "no card played since last hint → follow recommendation"
            )
            return Play(play_idx)
        if plays_since_hint == 1 and errors < 2:
            slot = _slot_name(play_idx, hand_size)
            self._last_decision_summary = (
                f"Play {slot}: decoded recommendation={my_rec} (play), "
                "one card played since hint and <2 errors → follow recommendation"
            )
            return Play(play_idx)
        return None

    def _paper_try_give_encoded_hint(self, player_view: PlayerView) -> Optional[Move]:
        """
        Paper rule 3: if a hint token can be spent, give the encoding hint.

        The mod-8 value fixes rank vs color and which clockwise partner to hint; with
        non-empty hands (game invariant), :meth:`_compute_hint` always produces a move.
        """
        if self.common_view.hint_tokens <= 0:
            return None
        hint_move = self._compute_hint(player_view)
        self._my_decoded_recommendation = None
        if isinstance(hint_move, ColorHint):
            self._last_decision_summary = (
                f"Hint: give color {hint_move.color.name.lower()} to P{hint_move.teammate + 1} "
                "(encodes sum of all others' recommendations mod 8; each teammate decodes their own)"
            )
            return hint_move
        if isinstance(hint_move, NumberHint):
            self._last_decision_summary = (
                f"Hint: give number {hint_move.number.value} to P{hint_move.teammate + 1} "
                "(encodes sum of all others' recommendations mod 8; each teammate decodes their own)"
            )
            return hint_move
        assert False, f"unexpected hint type from _compute_hint: {type(hint_move)}"

    def _paper_try_follow_discard_recommendation(
        self,
        my_rec: Optional[int],
        hand_size: int,
        valid_moves: List[Move],
    ) -> Optional[Move]:
        """Paper rule 4: if recommendation is discard (4–7), discard that card."""
        if my_rec is None or not (4 <= my_rec <= 7):
            return None
        discard_idx = rec_to_discard_index(my_rec, hand_size)
        if discard_idx is None:
            return None
        if not any(isinstance(m, Discard) and m.card == discard_idx for m in valid_moves):
            return None
        slot = _slot_name(discard_idx, hand_size)
        self._last_decision_summary = (
            f"Discard {slot}: decoded recommendation={my_rec} (discard) → follow recommendation"
        )
        return Discard(discard_idx)

    def _paper_try_discard_c1(self, valid_moves: List[Move], hand_size: int) -> Optional[Move]:
        """Paper rule 5: discard C1 (oldest)."""
        c1_idx = hand_size - 1
        for m in valid_moves:
            if isinstance(m, Discard) and m.card == c1_idx:
                self._last_decision_summary = (
                    "Discard C1 (oldest): no hint tokens or action algorithm rule 5 (default discard C1)"
                )
                return m
        return None

    def _emergency_move_when_no_valid_moves(self, hand_size: int) -> Move:
        self._last_decision_summary = "No valid moves; play or discard index 0"
        return Play(0) if hand_size > 0 else Discard(0)

    def play(self, player_view: PlayerView) -> Move:
        hand_size = player_view.own_hand_size
        assert hand_size == HAND_SIZE_FOR_RECOMMENDATION
        errors = self.game_settings.max_live_tokens - self.common_view.live_tokens

        my_rec = self._get_my_recommendation(player_view)
        valid_moves = generate_all_valid_moves(
            player_view, self.common_view, self.game_settings, self._player_index
        )
        valid_moves = [m for m in valid_moves if self.is_move_legal(player_view, m)]

        if not valid_moves:
            return self._emergency_move_when_no_valid_moves(hand_size)

        move = (
            self._paper_try_follow_play_recommendation(
                my_rec,
                hand_size,
                valid_moves,
                plays_since_hint=self._plays_since_hint,
                errors=errors,
            )
            or self._paper_try_give_encoded_hint(player_view)
            or self._paper_try_follow_discard_recommendation(my_rec, hand_size, valid_moves)
            or self._paper_try_discard_c1(valid_moves, hand_size)
        )
        assert move is not None, (
            "paper rules 1–5 should always yield a move when non-empty hands and standard tokens apply"
        )
        return move

    def _compute_hint(self, player_view: PlayerView) -> Move:
        """
        Build the rank or color hint that encodes (sum of others' recommendations) mod 8.

        For 5 players the encoded target is always another player in ``teammates``.
        Hands are never empty in supported games; a legal rank or color hint always exists
        on a standard deck.
        """
        total = 0
        for p in range(NUM_PLAYERS_FOR_RECOMMENDATION):
            if p == self._player_index:
                continue
            if p not in player_view.teammates:
                continue
            hand = player_view.teammates[p].cards
            rec = self._get_recommendation_for_hand(
                hand, self.common_view, self.game_settings
            )
            total += rec
        value = total % 8
        pos_0, is_number = (value, True) if value < 4 else (value - 4, False)
        target = (self._player_index + 1 + pos_0) % NUM_PLAYERS_FOR_RECOMMENDATION
        assert target in player_view.teammates, (
            "5p view should list every other player; encoding target must be a teammate"
        )
        hand = player_view.teammates[target]
        assert hand.cards, "encoding hint requires the target player to have at least one card"
        if is_number:
            for num in Number:
                indices = [i for i, c in enumerate(hand.cards) if c.number == num]
                if indices:
                    return NumberHint(target, indices, num)
            assert False, "non-empty hand has a rank; encoding rank hint should exist"

        for color in Color:
            if color == Color.MULTI:
                continue
            indices = [i for i, c in enumerate(hand.cards) if c.color == color]
            if indices:
                return ColorHint(target, indices, color)
        assert False, "non-empty standard hand has a non-MULTI suit; encoding color hint should exist"

    def get_decision_summary(self) -> Optional[str]:
        """Return a short explanation of the last move for console/GUI display."""
        return self._last_decision_summary
