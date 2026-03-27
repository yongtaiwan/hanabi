"""
Recommendation strategy AI player for Hanabi.

Implements Strategy 1 from the paper "How to Make the Perfect Fireworks Display:
Two Strategies for Hanabi" by Cox et al. (Mathematics Magazine, 2015).

The strategy uses a hat-guessing / network-coding scheme: a single outbound hint encodes
a value 0–7 so that every *other* player can decode their personal recommendation
(play C1–C4 or discard C1–C4) from the public hint and the sum of everyone else's
paper codes (mod 8).

The engine uses left-to-right indices matching the paper and GUI: **C1 = index 0**
(left / oldest) through **C4 = index 3** (right / newest). Endgame hands may omit
trailing logical slots (e.g. three cards → indices 0, 1, 2 only); empty slots are
skipped in tie-break scans.

This encoding supports four card positions (0–3 play, add 4 for discard). The player
targets standard 5-player table rule-sets (four cards at deal time; hands may shrink).

Multicolor (``Color.MULTI``) cards are not supported; hint encoding uses the same five
standard suits as :func:`hanabi.core.game.create_standard_game_settings`.
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
# 4=Discard C1, 5=Discard C2, 6=Discard C3, 7=Discard C4 (here Ck = slot index k−1).
# Hint encoding: 0–3 = rank hint to player at position 1–4 (clockwise from hinter),
# 4–7 = suit hint to position 1–4.

# Tie-break / scan order: C1 (index 0) first through C4 (index 3).
_REC_SLOT_ORDER = (0, 1, 2, 3)


def _slot_card(hand_cards: List[Card], idx: int) -> Optional[Card]:
    """Return card at slot ``idx`` or ``None`` if that logical slot is empty (hand shorter than 4)."""
    return hand_cards[idx] if idx < len(hand_cards) else None


# Standard suits only (matches ``create_standard_game_settings``); MULTI is not used for hints.
_STANDARD_HINT_COLORS = (
    Color.WHITE,
    Color.RED,
    Color.BLUE,
    Color.YELLOW,
    Color.GREEN,
)


class RecommendationPlayer(BasePlayer):
    """
    Recommendation strategy from Cox et al. (paper Strategy 1).

    Only for standard 5-player games (four cards at deal time; hands may have fewer cards later).
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
        assert player_view.own_hand_size >= 3
        errors = self.game_settings.max_live_tokens - self.common_view.live_tokens

        recommendation = self._get_my_recommendation()

        move = (
            self._try_follow_play_recommendation(player_view, recommendation, self._plays_since_hint, errors)
            or self._try_give_encoded_hint(player_view)
            or self._try_follow_discard_recommendation(player_view, recommendation)
            or self._discard_c1(player_view)

        )
        assert move is not None, "expected a legal play or discard with a non-empty hand"
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
    ) -> tuple[int, int, str]:
        """
        Sum paper-strategy recommendation codes for every visible teammate except ``self``.

        Returns ``(total, total % 8, breakdown)`` where ``breakdown`` logs per-player
        contributions. Decoding a hint excludes the hinter by passing ``exclude_index``.
        """
        parts: list[str] = []
        total = 0
        for p in range(NUM_PLAYERS_FOR_RECOMMENDATION):
            if p == self._player_index or p not in player_view.teammates:
                continue
            if exclude_index is not None and p == exclude_index:
                continue
            rec = self._get_recommendation_for_hand(
                player_view.teammates[p].cards,
                self.common_view,
                self.game_settings,
            )
            total += rec
            parts.append(f"P{p + 1}:{rec}")
        breakdown = ", ".join(parts)
        return total, total % 8, breakdown

    def _decode_recommendation_with_view(
        self, player_view: PlayerView, hint_value: int, hinter: int
    ) -> int:
        """
        Decode this player's recommendation from the public hint value.

        Uses ``player_view`` for visible teammate hands and :attr:`BasePlayer.common_view`
        for shared piles and tokens (no access to full :class:`~hanabi.core.game.Game`).
        """
        others_sum, _, _ = self._sum_peer_recommendations(player_view, exclude_index=hinter)
        return (hint_value - others_sum) % 8

    def _get_my_recommendation(self) -> Optional[int]:
        """Decoded recommendation at hint time for receivers; ``None`` if no hint yet or we gave the hint."""
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
        assert len(hand_cards) >= 3
        # Like ``a or b or ...`` but each rule may legitimately return 0 (play C1).
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
        """Paper priority 1: play a playable rank-5; tie-break C1 → C4 (lowest index first)."""
        for idx in _REC_SLOT_ORDER:
            card = _slot_card(hand_cards, idx)
            if card is None:
                continue
            if Number.FIVE == card.number and CardKind.PLAYABLE == common_view.card_kind(card, settings):
                return idx
        return None

    @staticmethod
    def _rec_play_lowest_rank(
        hand_cards: List[Card], common_view: CommonView, settings: GameSettings
    ) -> Optional[int]:
        """Paper priority 2: play lowest-rank playable; tie-break C1 → C4."""
        playable = []
        for idx in _REC_SLOT_ORDER:
            card = _slot_card(hand_cards, idx)
            if card is None:
                continue
            if CardKind.PLAYABLE == common_view.card_kind(card, settings):
                playable.append((idx, card.number.value))
        if not playable:
            return None
        playable.sort(key=lambda x: (x[1], x[0]))
        return playable[0][0]

    @staticmethod
    def _rec_discard_useless(
        hand_cards: List[Card], common_view: CommonView, settings: GameSettings
    ) -> Optional[int]:
        """Paper priority 3: discard a useless card; tie-break C1 → C4."""
        for idx in _REC_SLOT_ORDER:
            card = _slot_card(hand_cards, idx)
            if card is None:
                continue
            if CardKind.USELESS == common_view.card_kind(card, settings):
                return 4 + idx
        return None

    @staticmethod
    def _rec_discard_dispensable(
        hand_cards: List[Card], common_view: CommonView, settings: GameSettings
    ) -> Optional[int]:
        """Paper priority 4: discard highest-rank dispensable; tie-break C1 → C4."""
        dispensable = []
        for idx in _REC_SLOT_ORDER:
            card = _slot_card(hand_cards, idx)
            if card is None:
                continue
            if CardKind.DISPENSABLE == common_view.card_kind(card, settings):
                dispensable.append((idx, card.number.value))
        if not dispensable:
            return None
        dispensable.sort(key=lambda x: (-x[1], x[0]))
        return 4 + dispensable[0][0]

    @staticmethod
    def _rec_discard_c1(
        hand_cards: List[Card], _common_view: CommonView, _settings: GameSettings
    ) -> int:
        """Paper priority 5: recommend discarding C1 (leftmost occupied slot when hand < 4)."""
        for idx in _REC_SLOT_ORDER:
            if _slot_card(hand_cards, idx) is not None:
                return 4 + idx
        assert False, "non-empty hand has at least one card"

    @staticmethod
    def _four_card_slot_name(internal_idx: int) -> str:
        """Paper-style slot label: ``internal_idx`` 0..3 → C1..C4."""
        return f"C{internal_idx + 1}"

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
        play_idx = recommendation
        if play_idx >= player_view.own_hand_size:
            return None
        if not self.is_move_legal(player_view, Play(play_idx)):
            return None
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
        non-empty hands (game invariant), :meth:`_hint_for_encoded_value` always produces a move.
        """
        if 0 == self.common_view.hint_tokens:
            return None
        _, sum_mod8, peer_breakdown = self._sum_peer_recommendations(player_view)
        hint_move = self._hint_for_encoded_value(player_view, sum_mod8)
        self._my_decoded_recommendation = None
        hint_type = (
            f"rank/number (hint-type band 0–3, value {sum_mod8})"
            if sum_mod8 < 4
            else f"suit/color (hint-type band 4–7, value {sum_mod8})"
        )
        suffix = (
            f"Peer recommendations (paper codes): {peer_breakdown}. "
            f"Sum mod 8 = {sum_mod8}. Encoding: {hint_type}; each teammate decodes their own."
        )
        if isinstance(hint_move, ColorHint):
            assert self.is_move_legal(player_view, hint_move), (
                "encoding color hint should be legal when a hint token can be spent"
            )
            self._last_decision_summary = (
                f"Hint: give color {hint_move.color.name.lower()} to P{hint_move.teammate + 1}. {suffix}"
            )
            return hint_move
        if isinstance(hint_move, NumberHint):
            assert self.is_move_legal(player_view, hint_move), (
                "encoding number hint should be legal when a hint token can be spent"
            )
            self._last_decision_summary = (
                f"Hint: give number {hint_move.number.value} to P{hint_move.teammate + 1}. {suffix}"
            )
            return hint_move
        assert False, f"unexpected hint type from _hint_for_encoded_value: {type(hint_move)}"

    def _try_follow_discard_recommendation(
        self,
        player_view: PlayerView,
        recommendation: Optional[int],
    ) -> Optional[Move]:
        """Paper rule 4: if recommendation is discard (4–7), discard that card."""
        if recommendation is None:
            return None
        assert 0 <= recommendation <= 7, "decoded self-recommendation is in 0..7 (mod 8)"
        if recommendation < 4:
            return None
        discard_idx = recommendation - 4
        if discard_idx >= player_view.own_hand_size:
            return None
        if not self.is_move_legal(player_view, Discard(discard_idx)):
            return None
        self._last_decision_summary = (
            f"Discard {self._four_card_slot_name(discard_idx)}: decoded recommendation={recommendation} "
            "(discard) → follow recommendation"
        )
        return Discard(discard_idx)

    def _discard_c1(self, player_view: PlayerView) -> Optional[Move]:
        """Paper rule 5: discard C1 (oldest card, index 0)."""
        assert self.is_move_legal(player_view, Discard(0))
        self._last_decision_summary = (
            f"Discard {self._four_card_slot_name(0)} (oldest): no hint tokens or rule 5 (default discard C1)"
        )
        return Discard(0)

    
    def _compute_hint(self, player_view: PlayerView) -> HintMove:
        """
        Build the rank or color hint that encodes ``(sum of others' recommendations) mod 8``.

        For 5 players the encoded target is always another player in ``teammates``.
        Hands are never empty in supported games; a legal rank or color hint always exists
        on a standard deck.
        """
        _, value, _ = self._sum_peer_recommendations(player_view)
        return self._hint_for_encoded_value(player_view, value)

    def _hint_for_encoded_value(self, player_view: PlayerView, value: int) -> HintMove:
        """Map encoded value 0..7 to a legal rank or color hint on a teammate's hand."""
        pos_0, is_number = (value, True) if value < 4 else (value - 4, False)
        target = (self._player_index + 1 + pos_0) % NUM_PLAYERS_FOR_RECOMMENDATION
        assert target in player_view.teammates, (
            "5p view should list every other player; encoding target must be a teammate"
        )
        hand = player_view.teammates[target]
        assert hand.cards, "encoding hint requires the target player to have at least one card"
        if is_number:
            for num in Number:
                # Sorted so hint card indices follow C1→C4 (left→right) for stable tests/UI.
                indices = sorted(i for i, c in enumerate(hand.cards) if num == c.number)
                if indices:
                    return NumberHint(target, indices, num)
            assert False, "non-empty hand has a rank; encoding rank hint should exist"

        for color in _STANDARD_HINT_COLORS:
            indices = sorted(i for i, c in enumerate(hand.cards) if color == c.color)  # left→right
            if indices:
                return ColorHint(target, indices, color)
        assert False, "encoding color hint should exist for a non-empty standard-color hand"
