"""
Simple Recommendation strategy for **5-player** Hanabi.

Extension of :class:`~hanabi.ai.four_player_recommendation.FourPlayerRecommendationPlayer`
with a **mod-16** alphabet over visible hands. **Sixteen hint channels** (``0``–``15``):
**4 hint directions × 4 targets** ``next``, ``next+1``, ``next+2``, ``next+3`` (``next+3`` is
the previous seat for 5p).

- **0–3:** left number  → next / next+1 / next+2 / next+3
- **4–7:** left color   → next / next+1 / next+2 / next+3
- **8–11:** right number → next / next+1 / next+2 / next+3
- **12–15:** right color → next / next+1 / next+2 / next+3

**Left vs right (index-based, same as 3p/4p):**

- *Left number / color:* rank / color of the card at hand index ``0``, all matching indices.
- *Right number / color:* rightmost card whose rank/color differs from slot ``0``; touch all
  matching cards. ``None`` (channel unavailable) when the hand is all one rank/color.

**Seat offset:** ``pos = (T - H - 1) % 5`` ∈ {0, 1, 2, 3}; channel ``c`` ⇒ direction ``c % 4``,
hint kind ``c // 4``.

**Recommendation code** (receiver action; peer codes on the wire are **0**–**12**):

- ``0`` — no info; fall through to default discard.
- ``1`` – ``4`` — play slot ``value - 1``.
- ``5`` – ``8`` — slot ``value - 5`` is a **USELESS** discard (never playable).
- ``9`` – ``12`` — slot ``value - 9`` is a **DISPENSABLE** discard (acceptable, not critical).

Mod-16 decode values **13**–**15** are unused (treated like ``0``). They should not arise when every
peer uses codes ``0``–``12``, but are normalized defensively.

**Receiver-as-target decoding:** when the observer is the hint target, left versus right is
identified from public fields (``0 in move.cards``), as in the 3p/4p strategies.
"""

from __future__ import annotations

from typing import Dict, List, NamedTuple, Optional

NUM_PLAYERS_FOR_FIVE_PLAYER_RECOMMENDATION = 5
NUM_CHANNELS = 16
MAX_ACTIONABLE_REC_CODE = 12
CODE_USELESS_DISCARD_OFFSET = 5
CODE_DISPENSABLE_DISCARD_OFFSET = 9

from hanabi.core.player import BasePlayer
from hanabi.core.game import CommonView, GameSettings, PlayerView
from hanabi.core.moves import (
    ColorHint,
    Discard,
    FinishedDiscard,
    FinishedPlay,
    HintMove,
    Move,
    NumberHint,
    Play,
    move_with_why,
)

from hanabi.core.enums import Color, Number, CardKind
from hanabi.core.card import Card
from hanabi.ai.recommendation_policy import allows_recommended_play, replace_current_recommendation

_REC_SLOT_ORDER = (0, 1, 2, 3, 4)


def _discard_code_offset(code: int) -> Optional[int]:
    if 5 <= code <= 8:
        return CODE_USELESS_DISCARD_OFFSET
    if 9 <= code <= 12:
        return CODE_DISPENSABLE_DISCARD_OFFSET
    return None


class _HintScore(NamedTuple):
    """Per-bucket counters for a candidate hint (5p splits discard by USELESS vs DISPENSABLE)."""

    new_plays: int
    new_useless_discards: int
    new_dispensable_discards: int
    saves: int
    flips: int

    def total(self) -> int:
        return (
            self.new_plays + self.new_useless_discards + self.new_dispensable_discards + self.saves + self.flips
        )

    def fmt(self) -> str:
        return (
            f"new_plays={self.new_plays} new_useless={self.new_useless_discards} "
            f"new_disp={self.new_dispensable_discards} saves={self.saves} flips={self.flips}"
        )


def _is_useless_discard_code(code: int) -> bool:
    return 5 <= code <= 8


def _is_dispensable_discard_code(code: int) -> bool:
    return 9 <= code <= 12


def _is_strong_hint(score: _HintScore) -> bool:
    """The single committed five-player strong-hint rule from the paper."""
    combined_changes = (
        score.new_plays
        + score.new_useless_discards
        + score.new_dispensable_discards
        + score.flips
    )
    return (
        score.saves >= 1
        or score.new_plays >= 2
        or score.new_useless_discards >= 1
        or combined_changes >= 2
    )


def _is_medium_hint(score: _HintScore) -> bool:
    """Medium means at least one new dispensable-discard recommendation."""
    return score.new_dispensable_discards >= 1


def _is_weak_hint(score: _HintScore) -> bool:
    """Weak means any remaining positive recommendation change."""
    return score.total() >= 1


class FivePlayerRecommendationPlayer(BasePlayer):
    """
    5-player Simple Recommendation bot (mod-16 decode, sixteen hint channels ``0``–``15``).

    Only standard 5-player settings from :func:`~hanabi.core.game.create_standard_game_settings`.
    """

    def __init__(self, player_index: int):
        super().__init__(player_index)
        self._plays_since_hint: int = 0
        self._last_decision_summary: Optional[str] = None
        self._latest_recommendation_by_seat: Dict[int, int] = {}

    @classmethod
    def supports_game_settings(cls, game_settings: GameSettings) -> bool:
        return NUM_PLAYERS_FOR_FIVE_PLAYER_RECOMMENDATION == game_settings.num_players

    def set_game_settings(self, game_settings: GameSettings) -> None:
        assert NUM_PLAYERS_FOR_FIVE_PLAYER_RECOMMENDATION == game_settings.num_players, (
            "FivePlayerRecommendationPlayer requires 5-player games"
        )
        super().set_game_settings(game_settings)

    def observe_play_move(self, player_index: int, move: FinishedPlay, observer_view: PlayerView) -> None:
        super().observe_play_move(player_index, move, observer_view)
        self._clear_recommendation_after_hand_change(player_index)
        self._plays_since_hint += 1

    def observe_discard_move(self, player_index: int, move: FinishedDiscard, observer_view: PlayerView) -> None:
        super().observe_discard_move(player_index, move, observer_view)
        self._clear_recommendation_after_hand_change(player_index)

    def observe_color_hint_move(self, player_index: int, move: ColorHint, observer_view: PlayerView) -> None:
        super().observe_color_hint_move(player_index, move, observer_view)
        self._observe_encoding_hint(player_index, move, observer_view)
        self._update_peer_recommendations_from_hint(player_index, observer_view)

    def observe_number_hint_move(self, player_index: int, move: NumberHint, observer_view: PlayerView) -> None:
        super().observe_number_hint_move(player_index, move, observer_view)
        self._observe_encoding_hint(player_index, move, observer_view)
        self._update_peer_recommendations_from_hint(player_index, observer_view)

    def play(self, player_view: PlayerView) -> Move:
        assert player_view.own_hand_size > 0
        self._last_decision_summary = None
        errors = self.game_settings.max_live_tokens - self.common_view.live_tokens

        move = (
            self._try_follow_play_recommendation(player_view, self._plays_since_hint, errors)
            or self._try_strong_hint(player_view)
            or self._try_follow_useless_discard_recommendation(player_view)
            or self._try_medium_hint(player_view)
            or self._try_follow_dispensable_discard_recommendation(player_view)
            or self._try_weak_hint(player_view)
            or self._try_discard_c1(player_view)
            or self._try_play_c1_as_last_resort(player_view)
        )
        assert move is not None
        assert self.is_move_legal(player_view, move), "FivePlayerRecommendationPlayer chooses legal moves only"
        assert self._last_decision_summary is not None, (
            "every _try_* branch that returns a move must set _last_decision_summary"
        )
        return move_with_why(move, self._last_decision_summary)

    def _observe_encoding_hint(
        self,
        player_index: int,
        move: ColorHint | NumberHint,
        observer_view: PlayerView,
    ) -> None:
        self._plays_since_hint = 0
        target = move.teammate
        hand_cards = self._hand_cards_for_hint_target(target, observer_view)
        channel_id = _infer_channel_id(player_index, target, move, hand_cards)
        if self._player_index != player_index:
            others_sum = self._sum_other_peer_recommendations(observer_view, exclude_index=player_index)
            decoded = (channel_id - others_sum) % NUM_CHANNELS
            self._set_recommendation_for_seat(self._player_index, decoded)

    def _recommendation_for_seat(self, seat: int) -> Optional[int]:
        return self._latest_recommendation_by_seat.get(seat)

    def _set_recommendation_for_seat(self, seat: int, code: int) -> None:
        replace_current_recommendation(
            self._latest_recommendation_by_seat,
            seat,
            code,
            minimum_code=1,
            maximum_code=MAX_ACTIONABLE_REC_CODE,
        )

    def _clear_recommendation_after_hand_change(self, seat: int) -> None:
        """A play or discard shifts positions, so that seat's old code is stale."""
        self._latest_recommendation_by_seat.pop(seat, None)

    def _update_peer_recommendations_from_hint(
        self, hinter_index: int, observer_view: PlayerView
    ) -> None:
        for p in range(NUM_PLAYERS_FOR_FIVE_PLAYER_RECOMMENDATION):
            if p == hinter_index or p == self._player_index:
                continue
            if p not in observer_view.teammates:
                continue
            rec = self._get_recommendation_for_hand(
                observer_view.teammates[p].cards,
                self.common_view,
                self.game_settings,
            )
            self._set_recommendation_for_seat(p, rec)

    def _hand_cards_for_hint_target(self, target: int, observer_view: PlayerView) -> Optional[List[Card]]:
        if target != self._player_index:
            return observer_view.teammates[target].cards
        return None

    def _sum_other_peer_recommendations(self, player_view: PlayerView, *, exclude_index: int) -> int:
        """Sum of recommendation codes for non-hinter, non-self peers (three in 5p)."""
        total = 0
        for p in range(NUM_PLAYERS_FOR_FIVE_PLAYER_RECOMMENDATION):
            if p == self._player_index or p == exclude_index:
                continue
            assert p in player_view.teammates, f"5p decode requires peer {p} in PlayerView.teammates"
            total += self._get_recommendation_for_hand(
                player_view.teammates[p].cards,
                self.common_view,
                self.game_settings,
            )
        return total

    def _sum_peer_recommendations(self, player_view: PlayerView) -> tuple[int, int, str]:
        """``(total, total % NUM_CHANNELS, breakdown)`` for the encoder."""
        parts: list[str] = []
        total = 0
        for p in range(NUM_PLAYERS_FOR_FIVE_PLAYER_RECOMMENDATION):
            if p == self._player_index or p not in player_view.teammates:
                continue
            rec = self._get_recommendation_for_hand(
                player_view.teammates[p].cards,
                self.common_view,
                self.game_settings,
            )
            total += rec
            parts.append(f"P{p + 1}:{rec}")
        return total, total % NUM_CHANNELS, ", ".join(parts)

    def get_gui_recommendation_by_slot(self, player_view: PlayerView) -> Dict[int, str]:
        """Map the latest actionable code to one GUI indicator."""
        code = self._recommendation_for_seat(self._player_index)
        if code is None:
            return {}
        if 1 <= code <= 4:
            slot = code - 1
            return {slot: "play"} if slot < player_view.own_hand_size else {}
        offset = (
            CODE_USELESS_DISCARD_OFFSET
            if 5 <= code <= 8
            else CODE_DISPENSABLE_DISCARD_OFFSET
        )
        slot = code - offset
        return {slot: "discard"} if 0 <= slot < player_view.own_hand_size else {}

    def _get_recommendation_for_hand(
        self,
        hand_cards: List[Card],
        common_view: CommonView,
        settings: GameSettings,
    ) -> int:
        for rule in (
            self._rec_play_rank5,
            self._rec_play_lowest_rank,
            self._rec_useless_slot,
            self._rec_dispensable_slot,
            self._rec_fallback_code_zero,
        ):
            r = rule(hand_cards, common_view, settings)
            if r is not None:
                return r
        assert False, "fallback code should always apply"

    @staticmethod
    def _rec_play_rank5(
        hand_cards: List[Card], common_view: CommonView, settings: GameSettings
    ) -> Optional[int]:
        for idx in _REC_SLOT_ORDER:
            card = _slot_card(hand_cards, idx)
            if card is None:
                continue
            if Number.FIVE == card.number and CardKind.PLAYABLE == common_view.card_kind(card, settings):
                return 1 + idx
        return None

    @staticmethod
    def _rec_play_lowest_rank(
        hand_cards: List[Card], common_view: CommonView, settings: GameSettings
    ) -> Optional[int]:
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
        return 1 + playable[0][0]

    @staticmethod
    def _rec_useless_slot(
        hand_cards: List[Card], common_view: CommonView, settings: GameSettings
    ) -> Optional[int]:
        return _most_useless_code(
            hand_cards, common_view, settings, CardKind.USELESS, code_offset=CODE_USELESS_DISCARD_OFFSET
        )

    @staticmethod
    def _rec_dispensable_slot(
        hand_cards: List[Card], common_view: CommonView, settings: GameSettings
    ) -> Optional[int]:
        return _most_useless_code(
            hand_cards, common_view, settings, CardKind.DISPENSABLE, code_offset=CODE_DISPENSABLE_DISCARD_OFFSET
        )

    @staticmethod
    def _rec_fallback_code_zero(
        _hand_cards: List[Card], _common_view: CommonView, _settings: GameSettings
    ) -> int:
        return 0

    def _try_follow_play_recommendation(
        self,
        player_view: PlayerView,
        plays_since_hint: int,
        errors: int,
    ) -> Optional[Move]:
        recommendation = self._recommendation_for_seat(self._player_index)
        if recommendation is None:
            return None
        assert 0 <= recommendation <= MAX_ACTIONABLE_REC_CODE
        if not (1 <= recommendation <= 4):
            return None
        play_idx = recommendation - 1
        if play_idx >= player_view.own_hand_size:
            return None
        if not self.is_move_legal(player_view, Play(play_idx)):
            return None
        if not allows_recommended_play(plays_since_hint, errors):
            return None
        if 0 == plays_since_hint:
            detail = "no play since last hint → follow"
        else:
            detail = "one play since hint, <2 errors → follow"
        self._last_decision_summary = (
            f"[5p mod-16] Play C{play_idx + 1} (code {recommendation}) — {detail}"
        )
        self._latest_recommendation_by_seat.pop(self._player_index, None)
        return Play(play_idx)

    def _try_follow_useless_discard_recommendation(self, player_view: PlayerView) -> Optional[Move]:
        return self._try_follow_discard_recommendation(
            player_view,
            CODE_USELESS_DISCARD_OFFSET,
            CODE_USELESS_DISCARD_OFFSET + 3,
            "USELESS",
        )

    def _try_follow_dispensable_discard_recommendation(self, player_view: PlayerView) -> Optional[Move]:
        return self._try_follow_discard_recommendation(
            player_view,
            CODE_DISPENSABLE_DISCARD_OFFSET,
            CODE_DISPENSABLE_DISCARD_OFFSET + 3,
            "dispensable",
        )

    def _try_follow_discard_recommendation(
        self,
        player_view: PlayerView,
        code_min: int,
        code_max: int,
        kind_label: str,
    ) -> Optional[Move]:
        recommendation = self._recommendation_for_seat(self._player_index)
        if recommendation is None:
            return None
        if not (code_min <= recommendation <= code_max):
            return None
        discard_idx = recommendation - code_min
        if discard_idx >= player_view.own_hand_size:
            return None
        if not self.is_move_legal(player_view, Discard(discard_idx)):
            return None
        self._last_decision_summary = (
            f"[5p mod-16] Discard C{discard_idx + 1} (code {recommendation} · {kind_label.lower()})"
        )
        self._latest_recommendation_by_seat.pop(self._player_index, None)
        return Discard(discard_idx)

    def _try_give_encoded_hint(self, player_view: PlayerView) -> Optional[Move]:
        if 0 == self.common_view.hint_tokens:
            return None
        _, sum_mod, peer_breakdown = self._sum_peer_recommendations(player_view)
        hint_move = _build_channel_hint(self._player_index, player_view, sum_mod)
        if hint_move is None:
            return None
        if not self.is_move_legal(player_view, hint_move):
            return None
        self._last_decision_summary = (
            f"[5p mod-16] Hint channel {sum_mod} (exact) · "
            f"peer codes sum mod 16 = {sum_mod} · {peer_breakdown}"
        )
        return hint_move

    def _try_strong_hint(self, player_view: PlayerView) -> Optional[Move]:
        score = self._score_candidate_hint(player_view)
        if not _is_strong_hint(score):
            return None
        move = self._try_give_encoded_hint(player_view)
        if move is None:
            return None
        self._last_decision_summary = f"{self._last_decision_summary} · {score.fmt()} [strong]"
        return move

    def _try_medium_hint(self, player_view: PlayerView) -> Optional[Move]:
        score = self._score_candidate_hint(player_view)
        if not _is_medium_hint(score):
            return None
        move = self._try_give_encoded_hint(player_view)
        if move is None:
            return None
        self._last_decision_summary = f"{self._last_decision_summary} · {score.fmt()} [medium]"
        return move

    def _try_weak_hint(self, player_view: PlayerView) -> Optional[Move]:
        score = self._score_candidate_hint(player_view)
        if not _is_weak_hint(score):
            return None
        move = self._try_give_encoded_hint(player_view)
        if move is None:
            return None
        self._last_decision_summary = f"{self._last_decision_summary} · {score.fmt()} [weak]"
        return move

    def _score_candidate_hint(self, player_view: PlayerView) -> _HintScore:
        new_plays = new_useless = new_dispensable = saves = flips = 0
        for p in range(NUM_PLAYERS_FOR_FIVE_PLAYER_RECOMMENDATION):
            if p == self._player_index:
                continue
            peer_hand = player_view.teammates[p].cards
            before = self._recommendation_for_seat(p)
            after = self._get_recommendation_for_hand(peer_hand, self.common_view, self.game_settings)

            before_offset = _discard_code_offset(before) if before is not None else None

            is_save = False
            if before in (1, 2, 3, 4) and after != before and (before - 1) < len(peer_hand):
                card_for_play = peer_hand[before - 1]
                if CardKind.PLAYABLE != self.common_view.card_kind(card_for_play, self.game_settings):
                    is_save = True
            elif before_offset is not None and after != before and (before - before_offset) < len(peer_hand):
                card_for_discard = peer_hand[before - before_offset]
                if CardKind.CRITICAL == self.common_view.card_kind(card_for_discard, self.game_settings):
                    is_save = True

            is_new_play = after in (1, 2, 3, 4) and before not in (1, 2, 3, 4)
            is_new_useless = _is_useless_discard_code(after) and (
                before is None or not _is_useless_discard_code(before)
            )
            is_new_dispensable = _is_dispensable_discard_code(after) and (
                before is None or not _is_dispensable_discard_code(before)
            )
            is_flip = before != after and not (is_new_play or is_new_useless or is_new_dispensable or is_save)

            if is_new_play:
                new_plays += 1
            if is_new_useless:
                new_useless += 1
            if is_new_dispensable:
                new_dispensable += 1
            if is_save:
                saves += 1
            if is_flip:
                flips += 1
        return _HintScore(new_plays, new_useless, new_dispensable, saves, flips)

    def _try_play_c1_as_last_resort(self, player_view: PlayerView) -> Optional[Move]:
        """Play C1 as the common Simple-strategy last resort."""
        if not self.is_move_legal(player_view, Play(0)):
            return None
        self._last_decision_summary = (
            "[5p mod-16] Play C1 (last resort: exact channel unavailable at max tokens)"
        )
        return Play(0)

    def _try_discard_c1(self, player_view: PlayerView) -> Optional[Move]:
        if not self.is_move_legal(player_view, Discard(0)):
            return None
        self._last_decision_summary = "[5p mod-16] Discard C1 — default"
        return Discard(0)


def _slot_card(hand_cards: List[Card], idx: int) -> Optional[Card]:
    return hand_cards[idx] if idx < len(hand_cards) else None


def _chop_index(hand_size: int) -> int:
    assert 0 < hand_size
    return hand_size - 1


def _seat_offset_pos(hinter: int, target: int) -> int:
    """``pos = (T - H - 1) % 5`` ∈ {0, 1, 2, 3} for next … next+3."""
    return (target - hinter - 1) % NUM_PLAYERS_FOR_FIVE_PLAYER_RECOMMENDATION


def _infer_channel_id(
    hinter: int,
    target: int,
    move: ColorHint | NumberHint,
    hand_cards: Optional[List[Card]],
) -> int:
    if hand_cards is not None:
        return _infer_channel_id_from_hand(hinter, target, move, hand_cards)
    return _infer_channel_id_public(hinter, target, move)


def _infer_channel_id_from_hand(
    hinter: int, target: int, move: ColorHint | NumberHint, hand_cards: List[Card]
) -> int:
    pos = _seat_offset_pos(hinter, target)
    assert 0 <= pos <= 3, f"5p hint must target next … next+3 (pos in [0,3]); got {pos}"

    sort_idx = sorted(move.cards)

    if isinstance(move, NumberHint):
        ln, li = _left_number_spec(hand_cards)
        if move.number == ln and sort_idx == li:
            return 0 + pos
        rs = _right_number_spec(hand_cards)
        if rs is not None:
            rn, ri = rs
            if move.number == rn and sort_idx == ri:
                return 8 + pos
        assert False, "number hint does not match left/right rank specs"

    lc, lci = _left_color_spec(hand_cards)
    if move.color == lc and sort_idx == lci:
        return 4 + pos

    rcs = _right_color_spec(hand_cards)
    if rcs is not None:
        rc, rci = rcs
        if move.color == rc and sort_idx == rci:
            return 12 + pos

    assert False, "color hint does not match left/right color specs"


def _infer_channel_id_public(hinter: int, target: int, move: ColorHint | NumberHint) -> int:
    """Receiver-as-target fallback when the hinted hand is not visible."""
    pos = _seat_offset_pos(hinter, target)
    assert 0 <= pos <= 3, f"5p hint must target next … next+3 (pos in [0,3]); got {pos}"

    if isinstance(move, NumberHint):
        return (0 + pos) if 0 in move.cards else (8 + pos)
    return (4 + pos) if 0 in move.cards else (12 + pos)


def _build_channel_hint(player_index: int, player_view: PlayerView, channel_id: int) -> Optional[HintMove]:
    if not (0 <= channel_id < NUM_CHANNELS):
        return None

    hint_kind = channel_id // 4  # 0=left_num, 1=left_color, 2=right_num, 3=right_color
    direction = channel_id % 4
    target = (player_index + 1 + direction) % NUM_PLAYERS_FOR_FIVE_PLAYER_RECOMMENDATION
    if target not in player_view.teammates:
        return None
    hand = player_view.teammates[target].cards
    if not hand:
        return None

    if 0 == hint_kind:
        rank, indices = _left_number_spec(hand)
        return NumberHint(target, indices, rank)

    if 1 == hint_kind:
        color, indices = _left_color_spec(hand)
        return ColorHint(target, indices, color)

    if 2 == hint_kind:
        return _build_right_number_hint(target, hand)

    assert 3 == hint_kind
    return _build_right_color_hint(target, hand)


def _left_number_spec(hand: List[Card]) -> tuple[Number, List[int]]:
    r = hand[0].number
    indices = sorted(i for i, c in enumerate(hand) if r == c.number)
    return r, indices


def _right_number_spec(hand: List[Card]) -> Optional[tuple[Number, List[int]]]:
    if len(hand) < 2:
        return None
    left_rank = hand[0].number
    rightmost_other = next((c for c in reversed(hand) if c.number != left_rank), None)
    if rightmost_other is None:
        return None
    r = rightmost_other.number
    indices = sorted(i for i, c in enumerate(hand) if r == c.number)
    return r, indices


def _build_right_number_hint(target: int, hand: List[Card]) -> Optional[NumberHint]:
    spec = _right_number_spec(hand)
    if spec is None:
        return None
    r, indices = spec
    return NumberHint(target, indices, r)


def _left_color_spec(hand: List[Card]) -> tuple[Color, List[int]]:
    col = hand[0].color
    indices = sorted(i for i, c in enumerate(hand) if col == c.color)
    return col, indices


def _right_color_spec(hand: List[Card]) -> Optional[tuple[Color, List[int]]]:
    if len(hand) < 2:
        return None
    left_color = hand[0].color
    rightmost_other = next((c for c in reversed(hand) if c.color != left_color), None)
    if rightmost_other is None:
        return None
    col = rightmost_other.color
    indices = sorted(i for i, c in enumerate(hand) if col == c.color)
    return col, indices


def _build_right_color_hint(target: int, hand: List[Card]) -> Optional[ColorHint]:
    spec = _right_color_spec(hand)
    if spec is None:
        return None
    col, indices = spec
    return ColorHint(target, indices, col)


def _most_useless_code(
    hand_cards: List[Card],
    common_view: CommonView,
    settings: GameSettings,
    target_kind: CardKind,
    *,
    code_offset: int,
) -> Optional[int]:
    if not hand_cards:
        return None
    chop = _chop_index(len(hand_cards))
    if target_kind == common_view.card_kind(hand_cards[chop], settings):
        return code_offset + chop
    for idx in _REC_SLOT_ORDER:
        if idx >= len(hand_cards) or idx == chop:
            continue
        if target_kind == common_view.card_kind(hand_cards[idx], settings):
            return code_offset + idx
    return None
