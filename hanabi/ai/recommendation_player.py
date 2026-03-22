"""
Recommendation strategy AI player for Hanabi.

Implements Strategy 1 from the paper "How to Make the Perfect Fireworks Display:
Two Strategies for Hanabi" by Cox et al. (Mathematics Magazine, 2015).

The strategy uses a hat-guessing / network-coding scheme: a single hint encodes
a value 0-7 that allows every other player to decode their personal recommendation
(play C1-C4 or discard C1-C4). Card positions follow the paper: C1 = leftmost (oldest),
C4 = rightmost (newest). In this codebase, index 0 = newest (C4), index 3 = oldest (C1).

This encoding only supports 4 card positions (0-3 play, 4-7 discard). This player is
only supported for standard 5-player games (4 cards per hand).
"""

from __future__ import annotations

from typing import List, Optional

NUM_PLAYERS_FOR_RECOMMENDATION = 5

from hanabi.core.player import BasePlayer
from hanabi.core.game import CommonView, GameSettings, PlayerView
from hanabi.core.moves import HintMove, Move, Play, Discard, ColorHint, NumberHint
from hanabi.core.enums import Color, Number, CardKind
from hanabi.core.card import Card

# Recommendation encoding (paper): 0=Play C1, 1=Play C2, 2=Play C3, 3=Play C4,
# 4=Discard C1, 5=Discard C2, 6=Discard C3, 7=Discard C4.
# Hint encoding: 0-3 = rank hint to player at position 1-4 (clockwise from hinter),
# 4-7 = suit hint to position 1-4.

# Slots in paper tie-break order (C1 first through C4): C1=idx 3 ... C4=idx 0.
_REC_SLOT_ORDER = (3, 2, 1, 0)


class RecommendationPlayer(BasePlayer):
    """
    Recommendation strategy from Cox et al. (paper Strategy 1).

    Only for standard 5-player games (4 cards per hand).
    """

    def __init__(self, player_index: int):
        super().__init__(player_index)
        self._last_hint_value: Optional[int] = None
        self._last_hinter: Optional[int] = None
        self._plays_since_hint: int = 0
        self._last_decision_summary: Optional[str] = None
        # Decoded recommendation at hint time (state when hint was given); used until next hint.
        self._my_decoded_recommendation: Optional[int] = None

    @classmethod
    def supports_game_settings(cls, game_settings: GameSettings) -> bool:
        return NUM_PLAYERS_FOR_RECOMMENDATION == game_settings.num_players

    def set_game_settings(self, game_settings: GameSettings) -> None:
        assert NUM_PLAYERS_FOR_RECOMMENDATION == game_settings.num_players, (
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

    def play(self, player_view: PlayerView) -> Move:
        assert 4 == player_view.own_hand_size
        errors = self.game_settings.max_live_tokens - self.common_view.live_tokens

        recommendation = self._get_my_recommendation()

        move = (
            self._try_follow_play_recommendation(player_view, recommendation, self._plays_since_hint, errors)
            or self._try_give_encoded_hint(player_view)
            or self._try_follow_discard_recommendation(player_view, recommendation)
            or self._try_discard_c1(player_view)
        )
        assert move is not None, (
            "paper rules 1–5 should always yield a move when non-empty hands and standard tokens apply"
        )
        assert self.is_move_legal(player_view, move), (
            "RecommendationPlayer should never choose an illegal move"
        )
        return move

    def get_decision_summary(self) -> Optional[str]:
        """Return a short explanation of the last move for console/GUI display."""
        return self._last_decision_summary

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
            else self._decode_recommendation_with_view(observer_view, self._last_hint_value, player_index)
        )

    def _sum_peer_recommendations(
        self, player_view: PlayerView, *, exclude_index: Optional[int] = None
    ) -> int:
        """
        Sum paper recommendations for every visible teammate except ``self``.

        Encoding uses the sum over all such players; decoding excludes the hinter via
        ``exclude_index``.
        """
        return sum(
            self._get_recommendation_for_hand(
                player_view.teammates[p].cards,
                self.common_view,
                self.game_settings,
            )
            for p in range(NUM_PLAYERS_FOR_RECOMMENDATION)
            if p != self._player_index
            and p in player_view.teammates
            and (exclude_index is None or p != exclude_index)
        )

    def _decode_recommendation_with_view(
        self, player_view: PlayerView, hint_value: int, hinter: int
    ) -> int:
        """
        Decode my recommendation from hint value.

        Uses ``player_view`` for visible teammate hands and :attr:`BasePlayer.common_view`
        for shared piles and tokens (no access to full :class:`~hanabi.core.game.Game`).
        """
        others_sum = self._sum_peer_recommendations(player_view, exclude_index=hinter)
        return (hint_value - others_sum) % 8

    def _get_my_recommendation(self) -> Optional[int]:
        """Return recommendation decoded at hint time for receivers; ``None`` if no hint yet or we were the hinter."""
        if self._last_hint_value is None:
            assert self._last_hinter is None
            return None
        if self._my_decoded_recommendation is not None:
            return self._my_decoded_recommendation
        assert self._player_index == self._last_hinter, (
            "hint-time decode should exist for every receiver; only the hinter has no self-recommendation"
        )
        return None

    def _get_recommendation_for_hand(
        self,
        hand_cards: List[Card],
        common_view: CommonView,
        settings: GameSettings,
    ) -> int:
        assert 4 == len(hand_cards)
        # Like ``a or b or ...`` but each rule may legitimately return 0 (play C4).
        for rule in (
            self._rec_play_rank5,
            self._rec_play_lowest_rank,
            self._rec_discard_useless,
            self._rec_discard_dispensable,
            self._rec_discard_c1,
        ):
            r = rule(hand_cards, common_view, settings)
            if r is not None:
                return r
        assert False, "discard C1 (paper priority 5) always applies"

    @staticmethod
    def _rec_play_rank5(
        hand_cards: List[Card], common_view: CommonView, settings: GameSettings
    ) -> Optional[int]:
        """Paper priority 1: play the playable 5 of lowest index (C1 ... C4)."""
        for idx in _REC_SLOT_ORDER:
            card = hand_cards[idx]
            if Number.FIVE == card.number and CardKind.PLAYABLE == common_view.card_kind(card, settings):
                return 3 - idx
        return None

    @staticmethod
    def _rec_play_lowest_rank(
        hand_cards: List[Card], common_view: CommonView, settings: GameSettings
    ) -> Optional[int]:
        """Paper priority 2: play lowest-rank playable; tie -> lowest index."""
        playable = [
            (idx, hand_cards[idx].number.value)
            for idx in _REC_SLOT_ORDER
            if CardKind.PLAYABLE == common_view.card_kind(hand_cards[idx], settings)
        ]
        if not playable:
            return None
        playable.sort(key=lambda x: (x[1], x[0]))
        return 3 - playable[0][0]

    @staticmethod
    def _rec_discard_useless(
        hand_cards: List[Card], common_view: CommonView, settings: GameSettings
    ) -> Optional[int]:
        """Paper priority 3: discard dead (useless) card of lowest index."""
        for idx in _REC_SLOT_ORDER:
            if CardKind.USELESS == common_view.card_kind(hand_cards[idx], settings):
                return 4 + (3 - idx)
        return None

    @staticmethod
    def _rec_discard_dispensable(
        hand_cards: List[Card], common_view: CommonView, settings: GameSettings
    ) -> Optional[int]:
        """Paper priority 4: discard highest-rank non-indispensable; tie -> lowest index."""
        dispensable = [
            (idx, hand_cards[idx].number.value)
            for idx in _REC_SLOT_ORDER
            if CardKind.DISPENSABLE == common_view.card_kind(hand_cards[idx], settings)
        ]
        if not dispensable:
            return None
        dispensable.sort(key=lambda x: (-x[1], x[0]))
        return 4 + (3 - dispensable[0][0])

    @staticmethod
    def _rec_discard_c1(
        hand_cards: List[Card], common_view: CommonView, settings: GameSettings
    ) -> int:
        """Paper priority 5: recommend that C1 be discarded."""
        return 4 + (3 - _REC_SLOT_ORDER[0])

    @staticmethod
    def _four_card_slot_name(internal_idx: int) -> str:
        """Paper-style slot for a 4-card hand: C1 (index 3) .. C4 (index 0)."""
        return f"C{4 - internal_idx}"

    def _try_follow_play_recommendation(
        self,
        player_view: PlayerView,
        recommendation: Optional[int],
        plays_since_hint: int,
        errors: int,
    ) -> Optional[Move]:
        """
        Paper rules 1–2: if recommendation is play (0–3), follow it when
        (1) no play since last hint, or (2) one play since hint and errors < 2.
        """
        if recommendation is None:
            return None
        assert 0 <= recommendation <= 7, "decoded self-recommendation is in 0..7 (mod 8)"
        if recommendation > 3:
            return None
        if 0 != plays_since_hint and 2 == errors:
            return None
        play_idx = 3 - recommendation
        assert self.is_move_legal(player_view, Play(play_idx)), (
            "paper play recommendation should be legal when rules 1–2 apply"
        )
        detail = (
            "no card played since last hint → follow recommendation"
            if 0 == plays_since_hint
            else "<2 errors → follow recommendation"
        )
        self._last_decision_summary = (
            f"Play {self._four_card_slot_name(play_idx)}: decoded recommendation={recommendation} (play), {detail}"
        )
        return Play(play_idx)

    def _try_give_encoded_hint(self, player_view: PlayerView) -> Optional[Move]:
        """
        Paper rule 3: if a hint token can be spent, give the encoding hint.

        The mod-8 value fixes rank vs color and which clockwise partner to hint; with
        non-empty hands (game invariant), :meth:`_compute_hint` always produces a move.
        """
        if 0 == self.common_view.hint_tokens:
            return None
        hint_move = self._compute_hint(player_view)
        self._my_decoded_recommendation = None
        if isinstance(hint_move, ColorHint):
            assert self.is_move_legal(player_view, hint_move), (
                "encoding color hint should be legal when a hint token can be spent"
            )
            self._last_decision_summary = (
                f"Hint: give color {hint_move.color.name.lower()} to P{hint_move.teammate + 1} "
                "(encodes sum of all others' recommendations mod 8; each teammate decodes their own)"
            )
            return hint_move
        if isinstance(hint_move, NumberHint):
            assert self.is_move_legal(player_view, hint_move), (
                "encoding number hint should be legal when a hint token can be spent"
            )
            self._last_decision_summary = (
                f"Hint: give number {hint_move.number.value} to P{hint_move.teammate + 1} "
                "(encodes sum of all others' recommendations mod 8; each teammate decodes their own)"
            )
            return hint_move
        assert False, f"unexpected hint type from _compute_hint: {type(hint_move)}"

    def _try_follow_discard_recommendation(
        self,
        player_view: PlayerView,
        recommendation: Optional[int],
    ) -> Optional[Move]:
        """Paper rule 4: if recommendation is discard (4–7), discard that card."""
        if recommendation is None: return None
        assert 0 <= recommendation <= 7, "decoded self-recommendation is in 0..7 (mod 8)"
        if recommendation < 4:
            return None
        discard_idx = 7 - recommendation
        assert self.is_move_legal(player_view, Discard(discard_idx)), (
            "paper discard recommendation should be legal when rule 4 applies"
        )
        self._last_decision_summary = (
            f"Discard {self._four_card_slot_name(discard_idx)}: decoded recommendation={recommendation} (discard) → follow recommendation"
        )
        return Discard(discard_idx)

    def _try_discard_c1(self, player_view: PlayerView) -> Move:
        """Paper rule 5: discard C1 (oldest, internal index 3)."""
        assert self.is_move_legal(player_view, Discard(3)), (
            "default discard C1 should be legal when rule 5 applies"
        )
        self._last_decision_summary = (
            "Discard C1 (oldest): no hint tokens or action algorithm rule 5 (default discard C1)"
        )
        return Discard(3)

    def _compute_hint(self, player_view: PlayerView) -> HintMove:
        """
        Build the rank or color hint that encodes (sum of others' recommendations) mod 8.

        For 5 players the encoded target is always another player in ``teammates``.
        Hands are never empty in supported games; a legal rank or color hint always exists
        on a standard deck.
        """
        value = self._sum_peer_recommendations(player_view) % 8
        pos_0, is_number = (value, True) if value < 4 else (value - 4, False)
        target = (self._player_index + 1 + pos_0) % NUM_PLAYERS_FOR_RECOMMENDATION
        assert target in player_view.teammates, (
            "5p view should list every other player; encoding target must be a teammate"
        )
        hand = player_view.teammates[target]
        assert hand.cards, "encoding hint requires the target player to have at least one card"
        if is_number:
            for num in Number:
                indices = [i for i, c in enumerate(hand.cards) if num == c.number]
                if indices:
                    return NumberHint(target, indices, num)
            assert False, "non-empty hand has a rank; encoding rank hint should exist"

        for color in Color:
            indices = [i for i, c in enumerate(hand.cards) if color == c.color]
            if indices:
                return ColorHint(target, indices, color)
        assert False, "non-empty standard hand has a non-MULTI suit; encoding color hint should exist"
