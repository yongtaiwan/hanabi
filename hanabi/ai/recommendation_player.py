"""
Recommendation strategy AI player for Hanabi.

Implements Strategy 1 from the paper "How to Make the Perfect Fireworks Display:
Two Strategies for Hanabi" by Cox et al. (Mathematics Magazine, 2015).

The strategy uses a hat-guessing / network-coding scheme: a single outbound hint encodes
a value 0–7 so that every *other* player can decode their personal recommendation
(play C1–C4 or discard C1–C4) from the public hint and the sum of everyone else's
paper codes (mod 8).

The engine uses left-to-right indices matching the paper and GUI: **C1 = index 0**
(left / oldest) through **C4 = index 3** (right / newest). New draws **append** to the
hand list (``GameState._draw_card_to_hand``), so the card you just
drew is always the **rightmost** slot (highest index), never index 0. Rule 5 “discard C1”
therefore uses ``Discard(0)`` and does **not** discard the newly drawn card on the next
turn. Endgame hands may omit trailing logical slots (e.g. three cards → indices 0, 1, 2
only); empty slots are skipped in tie-break scans.

This encoding supports four card positions (0–3 play, add 4 for discard). The player
targets standard 5-player table rule-sets (four cards at deal time; hands may shrink).

Multicolor (``Color.MULTI``) cards are not supported; hint encoding uses the same five
standard suits as :func:`hanabi.core.game.create_standard_game_settings`.

**Paper vs engine vocabulary (recommendation priorities 1–5):** Cox et al. use *playable*,
*dead*, and *indispensable*. This code uses :meth:`~hanabi.core.game.CommonView.card_kind`:
*dead* aligns with ``CardKind.USELESS`` for cards already passed on the fireworks, but
``USELESS`` also includes unreachable ranks (stricter pile logic than “dead” alone).
*Indispensable* aligns with ``CardKind.CRITICAL``. Priority 4 uses only ``DISPENSABLE``
cards (not critical); after priorities 1–3, that matches “highest rank among
non-indispensable” for typical hands with no playable or useless card left.

**Follow-play (paper action rules 1--2):** If the decoded recommendation is a play (0--3)
and the move is legal, follow only when no **Play** has occurred since the last encoding
hint, or when exactly one **Play** has occurred and the team has made fewer than two
errors (misplay strikes). ``plays_since_hint`` counts **Play** moves globally since the
hint; discards do not increment it.
"""

from __future__ import annotations

from enum import IntEnum
from typing import Dict, List, Optional

NUM_PLAYERS_FOR_RECOMMENDATION = 5
# Cox et al. count “errors” against standard three fuse tokens; ``1 == live_tokens`` is “two errors”.
MAX_LIVE_TOKENS_FOR_RECOMMENDATION = 3

from hanabi.core.player import BasePlayer
from hanabi.core.game import CommonView, GameSettings, PlayerView
from hanabi.core.moves import (
    HintMove,
    Move,
    Play,
    Discard,
    ColorHint,
    NumberHint,
    ExplainedPlay,
    ExplainedDiscard,
    ExplainedColorHint,
    ExplainedNumberHint,
    FinishedPlay,
    FinishedDiscard,
)
from hanabi.core.enums import Color, Number, CardKind
from hanabi.core.card import Card

# Recommendation encoding (paper): 0=Play C1, 1=Play C2, 2=Play C3, 3=Play C4,
# 4=Discard C1, 5=Discard C2, 6=Discard C3, 7=Discard C4 (here Ck = slot index k−1).
# Hint encoding: 0–3 = rank hint to player at position 1–4 (clockwise from hinter),
# 4–7 = suit hint to position 1–4.

class Slot(IntEnum):
    """Paper C1–C4 (Cox et al.): left-to-right; C1 is oldest (index 0).

    Members are ``int`` subclasses—use ``Slot.C1`` etc. as hand indices (no ``.value``).
    """

    C1 = 0
    C2 = 1
    C3 = 2
    C4 = 3


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

    Only for standard 5-player games with three fuse tokens (four cards at deal time; hands may shrink).
    """

    def __init__(self, player_index: int):
        super().__init__(player_index)
        self._last_hint_value: Optional[int] = None
        self._last_hinter: Optional[int] = None
        # Global: count of :class:`~hanabi.core.moves.Play` moves since last encoding hint.
        self._plays_since_hint: int = 0
        # Paper "most recent recommendation": decoded self-code (0--7) when this seat *receives* an
        # encoding hint. The hinter does not recommend to themselves, so we do not overwrite this on
        # observe when ``self`` gave the hint---it stays the previous value, if any.
        self._my_decoded_recommendation: Optional[int] = None

    @classmethod
    def supports_game_settings(cls, game_settings: GameSettings) -> bool:
        return NUM_PLAYERS_FOR_RECOMMENDATION == game_settings.num_players and (
            MAX_LIVE_TOKENS_FOR_RECOMMENDATION == game_settings.max_live_tokens
        )

    def set_game_settings(self, game_settings: GameSettings) -> None:
        assert NUM_PLAYERS_FOR_RECOMMENDATION == game_settings.num_players, (
            "RecommendationPlayer requires 5-player games"
        )
        assert MAX_LIVE_TOKENS_FOR_RECOMMENDATION == game_settings.max_live_tokens, (
            "RecommendationPlayer requires standard three fuse tokens (Cox et al.)"
        )
        super().set_game_settings(game_settings)

    def observe_play_move(self, player_index: int, move: FinishedPlay, observer_view: PlayerView) -> None:
        super().observe_play_move(player_index, move, observer_view)
        self._plays_since_hint += 1

    def observe_color_hint_move(self, player_index: int, move: ColorHint, observer_view: PlayerView) -> None:
        super().observe_color_hint_move(player_index, move, observer_view)
        self._observe_recommendation_hint(
            player_index, move, observer_view, hint_value_base=len(Slot)
        )

    def observe_number_hint_move(self, player_index: int, move: NumberHint, observer_view: PlayerView) -> None:
        super().observe_number_hint_move(player_index, move, observer_view)
        self._observe_recommendation_hint(player_index, move, observer_view, hint_value_base=0)

    def play(self, player_view: PlayerView) -> Move:
        recommendation = self._get_my_recommendation()
        move = (
            self._try_follow_play_recommendation(player_view, recommendation, self._plays_since_hint)
            or self._try_give_encoded_hint(player_view)
            or self._try_follow_discard_recommendation(player_view, recommendation)
            or self._discard_c1()
        )
        assert move is not None, "expected a legal play or discard with a non-empty hand"
        assert self.is_move_legal(player_view, move), (
            "RecommendationPlayer should never choose an illegal move"
        )
        return move

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
        # Receivers update "most recent recommendation"; the hinter does not overwrite theirs.
        if self._player_index != player_index:
            self._my_decoded_recommendation = self._decode_recommendation_with_view(
                observer_view, self._last_hint_value, player_index
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
        """
        Paper "most recent recommendation": decoded self-code from the last time this seat updated it.

        After an encoding hint, every receiver refreshes their decode; the hinter does not (they are
        not recommending to themselves), so the cached value stays whatever it was---typically still
        the previous most recent recommendation. ``None`` only when no hint has been seen yet, or
        the last hint was ours and we never had a prior decode.
        """
        if self._last_hint_value is None:
            assert self._last_hinter is None
            return None
        if self._my_decoded_recommendation is not None:
            return self._my_decoded_recommendation
        assert self._player_index == self._last_hinter, (
            "hint-time decode should exist for every receiver; only the hinter has no self-recommendation"
        )
        return None

    def get_gui_recommendation_by_slot(self, player_view: PlayerView) -> Dict[int, str]:
        """Map hand slot indices to ``play`` or ``discard`` for GUI indicators."""
        rec = self._get_my_recommendation()
        if rec is None:
            return {}
        if rec < len(Slot):
            return {rec: "play"} if rec < player_view.own_hand_size else {}
        discard_idx = rec - len(Slot)
        return {discard_idx: "discard"} if discard_idx < player_view.own_hand_size else {}

    def _get_recommendation_for_hand(
        self,
        hand_cards: List[Card],
        common_view: CommonView,
        settings: GameSettings,
    ) -> int:
        assert len(hand_cards) >= 3
        # Like ``a or b or ...`` but each rule may legitimately return 0 (play C1 / ``Slot.C1``).
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
        for slot in Slot:
            card = _slot_card(hand_cards, slot)
            if card is None:
                continue
            if Number.FIVE == card.number and CardKind.PLAYABLE == common_view.card_kind(card, settings):
                return slot
        return None

    @staticmethod
    def _rec_play_lowest_rank(
        hand_cards: List[Card], common_view: CommonView, settings: GameSettings
    ) -> Optional[int]:
        """Paper priority 2: play lowest-rank playable; tie-break C1 → C4."""
        playable = []
        for slot in Slot:
            card = _slot_card(hand_cards, slot)
            if card is None:
                continue
            if CardKind.PLAYABLE == common_view.card_kind(card, settings):
                playable.append((slot, card.number.value))
        if not playable:
            return None
        playable.sort(key=lambda x: (x[1], x[0]))
        return playable[0][0]

    @staticmethod
    def _rec_discard_useless(
        hand_cards: List[Card], common_view: CommonView, settings: GameSettings
    ) -> Optional[int]:
        """Paper priority 3: discard a useless card; tie-break C1 → C4."""
        for slot in Slot:
            card = _slot_card(hand_cards, slot)
            if card is None:
                continue
            if CardKind.USELESS == common_view.card_kind(card, settings):
                return len(Slot) + slot
        return None

    @staticmethod
    def _rec_discard_dispensable(
        hand_cards: List[Card], common_view: CommonView, settings: GameSettings
    ) -> Optional[int]:
        """Paper priority 4: discard highest-rank dispensable; tie-break C1 → C4."""
        dispensable = []
        for slot in Slot:
            card = _slot_card(hand_cards, slot)
            if card is None:
                continue
            if CardKind.DISPENSABLE == common_view.card_kind(card, settings):
                dispensable.append((slot, card.number.value))
        if not dispensable:
            return None
        dispensable.sort(key=lambda x: (-x[1], x[0]))
        return len(Slot) + dispensable[0][0]

    @staticmethod
    def _rec_discard_c1(
        hand_cards: List[Card], _common_view: CommonView, _settings: GameSettings
    ) -> int:
        """Paper priority 5: recommend discarding C1 (leftmost occupied slot when hand < 4)."""
        for slot in Slot:
            if _slot_card(hand_cards, slot) is not None:
                return len(Slot) + slot
        assert False, "non-empty hand has at least one card"

    def _try_follow_play_recommendation(
        self,
        player_view: PlayerView,
        recommendation: Optional[int],
        plays_since_hint: int,
    ) -> Optional[Move]:
        """
        Paper action rules 1--2: if the decoded recommendation is a play (0--3), follow only when:

        1. No **Play** since the last encoding hint (``plays_since_hint == 0``), or
        2. Exactly one **Play** since the hint (``plays_since_hint == 1``) and ``errors < 2``.

        If two or more **Play** moves have occurred since the hint, do not follow.
        Paper rules 1–2: if recommendation is play (0–3), follow it when
        (1) no play since last hint, or (2) one play since hint and fewer than two errors.
        """
        if recommendation is None:
            return None
        assert 0 <= recommendation <= 7, "decoded self-recommendation is in 0..7 (mod 8)"
        if recommendation >= len(Slot):
            return None
        assert recommendation < player_view.own_hand_size, (
            "decoded play recommendation must index a card in the current hand"
        )
        assert self.is_move_legal(player_view, Play(recommendation)), (
            "decoded play recommendation must be a legal Play move"
        )
        # After one intervening play, skip only when two errors so far (here: one fuse left).
        if 0 != plays_since_hint and 1 == self.common_view.live_tokens:
            return None
        if recommendation > 3:
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
        return ExplainedPlay(recommendation, why=f"Play {Slot(recommendation).name}: decoded recommendation={recommendation} (play), {detail}")

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
        hint_type = (
            f"rank/number (hint-type band 0–3, value {sum_mod8})"
            if sum_mod8 < len(Slot)
            else f"suit/color (hint-type band 4–7, value {sum_mod8})"
        )
        suffix = (
            f"Peer recommendations (paper codes): {peer_breakdown}. "
            f"Sum mod 8 = {sum_mod8}. Encoding: {hint_type}; each teammate decodes their own."
        )
        if isinstance(hint_move, ColorHint):
            return ExplainedColorHint(
                hint_move.teammate, hint_move.cards, hint_move.color, why=f"Hint: give color {hint_move.color.name.lower()} to P{hint_move.teammate + 1}. {suffix}"
            )
        if isinstance(hint_move, NumberHint):
            return ExplainedNumberHint(
                hint_move.teammate, hint_move.cards, hint_move.number, why=f"Hint: give number {hint_move.number.value} to P{hint_move.teammate + 1}. {suffix}"
            )
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
        if recommendation < len(Slot):
            return None
        discard_idx = recommendation - len(Slot)
        if discard_idx >= player_view.own_hand_size:
            return None
        if not self.is_move_legal(player_view, Discard(discard_idx)):
            return None
        return ExplainedDiscard(discard_idx, why=f"Discard {Slot(discard_idx).name}: decoded recommendation={recommendation} (discard) → follow recommendation")

    def _discard_c1(self) -> Optional[Move]:
        """Paper rule 5: discard C1 (oldest card, index 0)."""
        return ExplainedDiscard(Slot.C1, why=f"Discard {Slot.C1.name} (oldest): no hint tokens or rule 5 (default discard C1)")

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
        pos_0, is_number = (
            (value, True) if value < len(Slot) else (value - len(Slot), False)
        )
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
