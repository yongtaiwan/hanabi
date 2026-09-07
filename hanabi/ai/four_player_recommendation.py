"""
Simple Recommendation strategy for **4-player** Hanabi.

Direct extension of :class:`~hanabi.ai.three_player_recommendation.ThreePlayerRecommendationPlayer`
with a **mod-12** alphabet over visible hands. **Twelve hint channels** (``0``–``11``):
**4 hint directions × 3 targets** ``next``, ``next+1``, ``next+2`` (``next+2`` is the
previous seat for 4p).

- **0–2:** left number  → next / next+1 / next+2
- **3–5:** left color   → next / next+1 / next+2
- **6–8:** right number → next / next+1 / next+2
- **9–11:** right color → next / next+1 / next+2

**Left vs right (index-based, same as 3p):**

- *Left number / color:* rank / color of the card at hand index ``0``, all matching indices.
- *Right number / color:* the rightmost card whose rank / color differs from the left spec,
  then every matching card. The channel is unavailable only when the entire hand shares
  that rank / color.

**Seat offset (matches** :class:`~hanabi.ai.recommendation_player.RecommendationPlayer`):
``pos = (T - H - 1) % 4`` ∈ {0, 1, 2}; channel ``c`` ⇒ direction ``c % 3``.

**Recommendation code** (receiver action):

- ``0`` — no info; fall through to default discard.
- ``1`` – ``4`` — play slot ``value - 1``.
- ``5`` – ``8`` — slot ``value - 5`` is the **most useless**: receiver may discard that slot,
  or spend a hint instead, before falling through to the default discard.
- ``9`` – ``11`` — unused; no new action.

The encoder picks code ``5+idx`` from the chop first, otherwise the earliest ``USELESS`` /
``DISPENSABLE`` non-chop slot — so when chop is critical the recommendation steers the
receiver toward a different slot rather than the chop.

**Receiver-as-target decoding:** when the observer is the hint
target, :class:`~hanabi.core.game.PlayerView` does not list the observer's own hand. Left vs
right is inferred from public touched positions (``0 in move.cards``): left directions touch
C1 and right directions do not.
"""

from __future__ import annotations

from typing import Dict, List, NamedTuple, Optional

NUM_PLAYERS_FOR_FOUR_PLAYER_RECOMMENDATION = 4
NUM_CHANNELS = 12
MAX_ACTIONABLE_REC_CODE = 8

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
from hanabi.ai.recommendation_policy import (
    allows_recommended_play,
    is_positive_hint,
    is_shared_strong_hint,
    replace_current_recommendation,
)

# Slot indices iterated by recommendation rules. 4p hands hold 4 cards (indices 0..3); the
# fifth slot is included for symmetry with the 3p code so out-of-range checks fall through
# naturally if a hand size ever exceeds 4 in tooling.
_REC_SLOT_ORDER = (0, 1, 2, 3, 4)


class _HintScore(NamedTuple):
    """Per-bucket counters for a candidate hint (see :meth:`FourPlayerRecommendationPlayer._score_candidate_hint`).

    Buckets are independent: a single peer-transition may contribute to more than one of
    them (e.g. ``play_K → discard_L`` is always both ``new_discards += 1`` *and*
    ``saves += 1``). See the four-player Simple Recommendation specification for the full
    classification.
    """

    new_plays: int
    new_discards: int
    saves: int
    flips: int

    def total(self) -> int:
        return self.new_plays + self.new_discards + self.saves + self.flips

    def fmt(self) -> str:
        return (
            f"new_plays={self.new_plays} new_discards={self.new_discards} "
            f"saves={self.saves} flips={self.flips}"
        )


class FourPlayerRecommendationPlayer(BasePlayer):
    """
    4-player Simple Recommendation bot (mod-12 decode, twelve hint channels ``0``–``11``).

    Only standard 4-player settings from :func:`~hanabi.core.game.create_standard_game_settings`.
    """

    def __init__(self, player_index: int):
        super().__init__(player_index)
        self._plays_since_hint: int = 0
        self._last_decision_summary: Optional[str] = None
        self._latest_recommendation_by_seat: Dict[int, int] = {}

    @classmethod
    def supports_game_settings(cls, game_settings: GameSettings) -> bool:
        return NUM_PLAYERS_FOR_FOUR_PLAYER_RECOMMENDATION == game_settings.num_players

    def set_game_settings(self, game_settings: GameSettings) -> None:
        assert NUM_PLAYERS_FOR_FOUR_PLAYER_RECOMMENDATION == game_settings.num_players, (
            "FourPlayerRecommendationPlayer requires 4-player games"
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
        # Reset so the post-dispatch assertion catches any branch that returns a move
        # without recording its rationale.
        self._last_decision_summary = None
        errors = self.game_settings.max_live_tokens - self.common_view.live_tokens

        move = (
            self._try_follow_play_recommendation(player_view, self._plays_since_hint, errors)
            # A strong hint stays above discard-follow because it refreshes every receiver.
            or self._try_strong_hint(player_view)
            or self._try_follow_safe_discard_recommendation(player_view)
            # Weak hint catches "any non-useless effect" before we fall through to the
            # blind C1 discard. A low-info hint is still preferable to a last-resort play.
            or self._try_weak_hint(player_view)
            or self._try_discard_c1(player_view)
            or self._try_play_c1_as_last_resort(player_view)
        )
        assert move is not None
        assert self.is_move_legal(player_view, move), "FourPlayerRecommendationPlayer chooses legal moves only"
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
        """Replace each visible peer's latest actionable code after a new hint."""
        for p in range(NUM_PLAYERS_FOR_FOUR_PLAYER_RECOMMENDATION):
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
        """Visible cards on the hinted seat, or ``None`` when the observer is the receiver."""
        if target != self._player_index:
            return observer_view.teammates[target].cards
        return None

    def _sum_other_peer_recommendations(self, player_view: PlayerView, *, exclude_index: int) -> int:
        """
        Sum of recommendation codes for non-hinter, non-self peers.

        Two such peers exist in 4p; both their hands are visible to ``self`` in
        :class:`~hanabi.core.game.PlayerView`.
        """
        total = 0
        for p in range(NUM_PLAYERS_FOR_FOUR_PLAYER_RECOMMENDATION):
            if p == self._player_index or p == exclude_index:
                continue
            assert p in player_view.teammates, f"4p decode requires peer {p} in PlayerView.teammates"
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
        for p in range(NUM_PLAYERS_FOR_FOUR_PLAYER_RECOMMENDATION):
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
        slot = code - 5
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
        """Codes ``1``–``4``: play a playable 5."""
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
        """Codes ``1``–``4``: play the lowest-rank playable card (slot tiebreak)."""
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
        """Code ``5 + idx``: an already-useless slot (chop preferred, else earliest non-chop)."""
        return _most_useless_code(hand_cards, common_view, settings, CardKind.USELESS)

    @staticmethod
    def _rec_dispensable_slot(
        hand_cards: List[Card], common_view: CommonView, settings: GameSettings
    ) -> Optional[int]:
        """Code ``5 + idx``: a dispensable slot (chop preferred, else earliest non-chop)."""
        return _most_useless_code(hand_cards, common_view, settings, CardKind.DISPENSABLE)

    @staticmethod
    def _rec_fallback_code_zero(
        _hand_cards: List[Card], _common_view: CommonView, _settings: GameSettings
    ) -> int:
        """Code ``0``: no info; receiver falls through to default discard."""
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
        assert 1 <= recommendation <= MAX_ACTIONABLE_REC_CODE
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
            f"[4p mod-12] Play C{play_idx + 1} (code {recommendation}) — {detail}"
        )
        self._latest_recommendation_by_seat.pop(self._player_index, None)
        return Play(play_idx)

    def _try_follow_safe_discard_recommendation(self, player_view: PlayerView) -> Optional[Move]:
        recommendation = self._recommendation_for_seat(self._player_index)
        if recommendation is None:
            return None
        if not (5 <= recommendation <= 8):
            return None
        discard_idx = recommendation - 5
        if discard_idx >= player_view.own_hand_size:
            return None
        if not self.is_move_legal(player_view, Discard(discard_idx)):
            return None
        self._last_decision_summary = (
            f"[4p mod-12] Discard C{discard_idx + 1} (code {recommendation} · safe discard)"
        )
        self._latest_recommendation_by_seat.pop(self._player_index, None)
        return Discard(discard_idx)

    def _try_give_encoded_hint(self, player_view: PlayerView) -> Optional[Move]:
        """
        Emit a hint that encodes ``sum_mod`` on the **exact** channel ``cid == sum_mod``.

        If that channel can't be built on the target's hand (only possible when the target
        hand is entirely one rank or one color — see the right-direction helpers), we abstain so receivers
        never decode a shifted value. The dispatch chain then falls through to discard /
        play-slot-0. Every emitted hint therefore carries the intended recommendation
        exactly; there is no shifted-hint mode.
        """
        if 0 == self.common_view.hint_tokens:
            return None
        _, sum_mod, peer_breakdown = self._sum_peer_recommendations(player_view)
        hint_move = _build_channel_hint(self._player_index, player_view, sum_mod)
        if hint_move is None:
            return None
        if not self.is_move_legal(player_view, hint_move):
            return None
        self._last_decision_summary = (
            f"[4p mod-12] Hint channel {sum_mod} (exact) · "
            f"peer codes sum mod 12 = {sum_mod} · {peer_breakdown}"
        )
        return hint_move

    def _try_strong_hint(self, player_view: PlayerView) -> Optional[Move]:
        """Strong-hint threshold: two new plays, one new discard, or one save.

        Sits above discard-follow so life/critical saves and meaningful new teammate
        codes preempt our own discard recommendation (weak hint still follows discard-follow).
        """
        score = self._score_candidate_hint(player_view)
        if not is_shared_strong_hint(score.new_plays, score.new_discards, score.saves):
            return None
        move = self._try_give_encoded_hint(player_view)
        if move is None:
            return None
        self._last_decision_summary = f"{self._last_decision_summary} · {score.fmt()} [strong]"
        return move

    def _try_weak_hint(self, player_view: PlayerView) -> Optional[Move]:
        """Weak-hint threshold: any positive effect from the candidate hint.

        Sits above the C1-discard fallback so even a low-info hint is preferred over
        a blind slot-0 discard.
        """
        score = self._score_candidate_hint(player_view)
        if not is_positive_hint(score.total()):
            return None
        move = self._try_give_encoded_hint(player_view)
        if move is None:
            return None
        self._last_decision_summary = f"{self._last_decision_summary} · {score.fmt()} [weak]"
        return move

    def _score_candidate_hint(self, player_view: PlayerView) -> _HintScore:
        """Project the four bucket counters for the hint this seat would send right now.

        For each non-hinter peer ``p``, the latest stored code is ``before(p)`` and
        :meth:`_get_recommendation_for_hand` supplies ``after(p)``.

        Bucket predicates (independent — a transition can hit multiple):

        - ``new_play``      : ``after`` ∈ play codes AND ``before`` ∉ play codes
        - ``new_discard``   : ``after`` ∈ discard codes AND ``before`` ∉ discard codes
        - ``save``          : ``before`` is a play of a non-playable card (life save) or a
                              discard of a critical card (critical save), AND ``after`` ≠ ``before``
        - ``flip``          : ``before`` ≠ ``after`` AND none of the above hit
        """
        new_plays = new_discards = saves = flips = 0
        for p in range(NUM_PLAYERS_FOR_FOUR_PLAYER_RECOMMENDATION):
            if p == self._player_index:
                continue
            peer_hand = player_view.teammates[p].cards
            before = self._recommendation_for_seat(p)
            after = self._get_recommendation_for_hand(peer_hand, self.common_view, self.game_settings)

            is_save = False
            if before in (1, 2, 3, 4) and after != before and (before - 1) < len(peer_hand):
                card_for_play = peer_hand[before - 1]
                if CardKind.PLAYABLE != self.common_view.card_kind(card_for_play, self.game_settings):
                    is_save = True
            elif before in (5, 6, 7, 8) and after != before and (before - 5) < len(peer_hand):
                card_for_discard = peer_hand[before - 5]
                if CardKind.CRITICAL == self.common_view.card_kind(card_for_discard, self.game_settings):
                    is_save = True

            is_new_play = after in (1, 2, 3, 4) and before not in (1, 2, 3, 4)
            is_new_discard = after in (5, 6, 7, 8) and before not in (5, 6, 7, 8)
            is_flip = before != after and not (is_new_play or is_new_discard or is_save)

            if is_new_play:
                new_plays += 1
            if is_new_discard:
                new_discards += 1
            if is_save:
                saves += 1
            if is_flip:
                flips += 1
        return _HintScore(new_plays, new_discards, saves, flips)

    def _try_play_c1_as_last_resort(self, player_view: PlayerView) -> Optional[Move]:
        """
        Last-resort fallback. Reached only when no recommendation is followable, no exact
        hint can be encoded for ``sum_mod``, and the C1 discard is illegal at max hint tokens.
        Plays C1, matching the three- and five-player Simple strategies.
        """
        if not self.is_move_legal(player_view, Play(0)):
            return None
        self._last_decision_summary = (
            "[4p mod-12] Play C1 (last resort: exact channel unavailable at max tokens)"
        )
        return Play(0)

    def _try_discard_c1(self, player_view: PlayerView) -> Optional[Move]:
        """Discard slot 0 if legal. Illegal (and so returns ``None``) at max hint tokens."""
        if not self.is_move_legal(player_view, Discard(0)):
            return None
        self._last_decision_summary = "[4p mod-12] Discard C1 — default"
        return Discard(0)


def _slot_card(hand_cards: List[Card], idx: int) -> Optional[Card]:
    return hand_cards[idx] if idx < len(hand_cards) else None


def _chop_index(hand_size: int) -> int:
    assert 0 < hand_size
    return hand_size - 1


def _seat_offset_pos(hinter: int, target: int) -> int:
    """``pos = (T - H - 1) % 4`` ∈ {0, 1, 2} for next, next+1, next+2."""
    return (target - hinter - 1) % NUM_PLAYERS_FOR_FOUR_PLAYER_RECOMMENDATION


def _infer_channel_id(
    hinter: int,
    target: int,
    move: ColorHint | NumberHint,
    hand_cards: Optional[List[Card]],
) -> int:
    """Map an observed hint to channel index ``0``–``11`` (see module docstring)."""
    if hand_cards is not None:
        return _infer_channel_id_from_hand(hinter, target, move, hand_cards)
    return _infer_channel_id_public(hinter, target, move)


def _infer_channel_id_from_hand(
    hinter: int, target: int, move: ColorHint | NumberHint, hand_cards: List[Card]
) -> int:
    pos = _seat_offset_pos(hinter, target)
    assert 0 <= pos <= 2, f"4p hint must target next, next+1, or next+2 (pos in [0,2]); got {pos}"

    sort_idx = sorted(move.cards)

    if isinstance(move, NumberHint):
        ln, li = _left_number_spec(hand_cards)
        if move.number == ln and sort_idx == li:
            return 0 + pos
        rs = _right_number_spec(hand_cards)
        if rs is not None:
            rn, ri = rs
            if move.number == rn and sort_idx == ri:
                return 6 + pos
        assert False, "number hint does not match left/right rank specs"

    lc, lci = _left_color_spec(hand_cards)
    if move.color == lc and sort_idx == lci:
        return 3 + pos

    rcs = _right_color_spec(hand_cards)
    if rcs is not None:
        rc, rci = rcs
        if move.color == rc and sort_idx == rci:
            return 9 + pos

    assert False, "color hint does not match left/right color specs"


def _infer_channel_id_public(hinter: int, target: int, move: ColorHint | NumberHint) -> int:
    """
    Receiver-as-target fallback (own hand not in :class:`PlayerView`).

    Uses ``pos`` for direction (same as full-hand path). Number and color hints split left
    versus right by whether the public touched positions include C1.
    """
    pos = _seat_offset_pos(hinter, target)
    assert 0 <= pos <= 2, f"4p hint must target next, next+1, or next+2 (pos in [0,2]); got {pos}"

    if isinstance(move, NumberHint):
        return (0 + pos) if 0 in move.cards else (6 + pos)
    return (3 + pos) if 0 in move.cards else (9 + pos)


def _build_channel_hint(player_index: int, player_view: PlayerView, channel_id: int) -> Optional[HintMove]:
    """Construct the hint move for ``channel_id`` (``0``–``11``) if legal on ``player_view``."""
    if not (0 <= channel_id < NUM_CHANNELS):
        return None

    hint_kind = channel_id // 3  # 0=left_num, 1=left_color, 2=right_num, 3=right_color
    direction = channel_id % 3
    target = (player_index + 1 + direction) % NUM_PLAYERS_FOR_FOUR_PLAYER_RECOMMENDATION
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


# ---------------------------------------------------------------------------
# Hint-direction helpers (parallel to :mod:`hanabi.ai.three_player_recommendation`).
# Kept local so this file is self-contained for structural symmetry with 3p.
# ---------------------------------------------------------------------------


def _left_number_spec(hand: List[Card]) -> tuple[Number, List[int]]:
    """Rank at slot ``0``; all cards of that rank (index-based ``left``)."""
    r = hand[0].number
    indices = sorted(i for i, c in enumerate(hand) if r == c.number)
    return r, indices


def _right_number_spec(hand: List[Card]) -> Optional[tuple[Number, List[int]]]:
    """
    Rank of the **rightmost** card whose rank differs from :func:`_left_number_spec`'s rank;
    touch all cards of that rank on the hand. ``None`` only when every card shares the same
    rank (with a standard 5-card hand this requires all 5 cards to be the same rank).
    """
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
    """Color at slot ``0``; all cards of that color."""
    col = hand[0].color
    indices = sorted(i for i, c in enumerate(hand) if col == c.color)
    return col, indices


def _right_color_spec(hand: List[Card]) -> Optional[tuple[Color, List[int]]]:
    """Rightmost color distinct from C1's color; all cards of that color."""
    if len(hand) < 2:
        return None
    left_color = hand[0].color
    rightmost_other = next((c for c in reversed(hand) if c.color != left_color), None)
    if rightmost_other is None:
        return None
    color = rightmost_other.color
    indices = sorted(i for i, c in enumerate(hand) if color == c.color)
    return color, indices


def _build_right_color_hint(target: int, hand: List[Card]) -> Optional[ColorHint]:
    spec = _right_color_spec(hand)
    if spec is None:
        return None
    color, indices = spec
    return ColorHint(target, indices, color)


def _most_useless_code(
    hand_cards: List[Card],
    common_view: CommonView,
    settings: GameSettings,
    target_kind: CardKind,
) -> Optional[int]:
    """
    Return ``5 + idx`` for the slot we most want the receiver to drop.

    Prefers the **chop** (``hand_size - 1``) when its kind matches ``target_kind``; otherwise
    scans :data:`_REC_SLOT_ORDER` for the earliest non-chop slot whose kind matches. Returns
    ``None`` when no slot in the hand has ``target_kind``.
    """
    if not hand_cards:
        return None
    chop = _chop_index(len(hand_cards))
    if target_kind == common_view.card_kind(hand_cards[chop], settings):
        return 5 + chop
    for idx in _REC_SLOT_ORDER:
        if idx >= len(hand_cards) or idx == chop:
            continue
        if target_kind == common_view.card_kind(hand_cards[idx], settings):
            return 5 + idx
    return None
