"""
Mini recommendation strategy for **3-player** Hanabi.

Encodes a value with **mod-7** arithmetic over visible hands. **Seven physical channels**
(``0``–``6``); there is **no** eighth channel (legacy “right suit to previous” is unused).

- **0–1:** left number — rank of the card at **index 0** (C1 / oldest), all matching indices;
  **next** / **prev** teammate by seat order.
- **2–3:** left color — **color** of the card at **index 0**, all matching indices → next / prev.
- **4–5:** right number — rank of the **rightmost** card whose rank differs from the left-number
  rank (i.e. from slot ``0``'s rank), then hint **every** card of that rank on the full hand
  (same as a normal number hint). Example: ``R2 Y3 B4 R1 Y2`` (indices ``0``–``4``) → left
  number is **2**’s (slots ``0`` and ``4``); right number is the rightmost non-``2`` rank,
  which is ``R1`` at slot ``3`` → **1**’s on slot ``3``. Channel **unavailable** only if every
  card in the hand has the same rank.
- **6:** right color — color of the **rightmost** card whose color differs from the left-color
  (i.e. from slot ``0``'s color), then all cards of that color on the hand. Emitted only toward
  **next** teammate (no “right color to previous” channel). Channel **unavailable** only if
  every card in the hand has the same color.

**Seat offset (same pattern as :class:`~hanabi.ai.recommendation_player.RecommendationPlayer`):**
for hinter ``H`` and hint target ``T``,

``pos = (T - H - 1) % 3`` is ``0`` when ``T`` is the **next** player (clockwise), ``1`` when
``T`` is the **previous** player. No separate “my seat” notion — **global** indices ``0,1,2``.

When the observer is the hint **receiver**, their own hand is **not** in
:class:`~hanabi.core.game.PlayerView` ``teammates``. Channel inference then uses the same
left/right idea **approximated** from public fields (number vs color, ``pos``, whether slot
``0`` is touched); when the target hand is visible (observer not the receiver), inference uses
the full hand lists.

**Chop vs C1 vs :class:`~hanabi.ai.recommendation_player.RecommendationPlayer`:** The paper
**RecommendationPlayer** does **not** track chop: it uses fixed slots C1–C4 (indices ``0``–``3``),
and the default discard is **Discard(0)** = oldest card (**C1**), not the rightmost slot. This bot
matches that for the **fallback** discard. **Decoded** actions ``0`` / ``6`` still refer to
**chop** = ``hand_size - 1`` (newest / rightmost), per your 3p convention.

**Decoded value** (receiver action):

- ``0`` — chop is safe to discard.
- ``1``–``5`` — play slot ``value - 1``.
- ``6`` — chop should **not** be discarded.
"""

from __future__ import annotations

from typing import List, Optional, Dict

NUM_PLAYERS_FOR_MINI_RECOMMENDATION = 3

from hanabi.core.player import BasePlayer
from hanabi.core.game import CommonView, GameSettings, PlayerView
from hanabi.core.moves import Move, Play, Discard, ColorHint, NumberHint, HintMove, move_with_why
from hanabi.core.enums import Color, Number, CardKind
from hanabi.core.card import Card

_REC_SLOT_ORDER = (0, 1, 2, 3, 4)


class ThreePlayerRecommendationPlayer(BasePlayer):
    """
    3-player mini recommendation bot (mod-7 decode, seven hint channels ``0``–``6``).

    Only standard 3-player settings from :func:`~hanabi.core.game.create_standard_game_settings`.
    """

    def __init__(self, player_index: int):
        super().__init__(player_index)
        self._plays_since_hint: int = 0
        self._last_decision_summary: Optional[str] = None
        self._my_decoded_recommendation: Optional[int] = None

    @classmethod
    def supports_game_settings(cls, game_settings: GameSettings) -> bool:
        return NUM_PLAYERS_FOR_MINI_RECOMMENDATION == game_settings.num_players

    def set_game_settings(self, game_settings: GameSettings) -> None:
        assert NUM_PLAYERS_FOR_MINI_RECOMMENDATION == game_settings.num_players, (
            "ThreePlayerRecommendationPlayer requires 3-player games"
        )
        super().set_game_settings(game_settings)

    def observe_play_move(self, player_index: int, move: Play, observer_view: PlayerView) -> None:
        super().observe_play_move(player_index, move, observer_view)
        self._plays_since_hint += 1

    def observe_color_hint_move(self, player_index: int, move: ColorHint, observer_view: PlayerView) -> None:
        super().observe_color_hint_move(player_index, move, observer_view)
        self._observe_encoding_hint(player_index, move, observer_view)

    def observe_number_hint_move(self, player_index: int, move: NumberHint, observer_view: PlayerView) -> None:
        super().observe_number_hint_move(player_index, move, observer_view)
        self._observe_encoding_hint(player_index, move, observer_view)

    def play(self, player_view: PlayerView) -> Move:
        assert player_view.own_hand_size > 0
        # Reset so the post-dispatch assertion catches any branch that returns a move
        # without recording its rationale.
        self._last_decision_summary = None
        errors = self.game_settings.max_live_tokens - self.common_view.live_tokens
        recommendation = self._get_my_recommendation()

        move = (
            self._try_follow_play_recommendation(player_view, recommendation, self._plays_since_hint, errors)
            # IMPORTANT: keep hint BEFORE discard-follow. A given hint isn't just an info
            # token spend — it also broadcasts the next round of play/discard recommendations
            # to every teammate via the encoded channel. Swapping these two saved a hint
            # token but cratered scores on a 500-game batch (3p: 22.61 → 20.31, perfects
            # 18% → 2.4%, worst 15 → 3) because teammates started acting on stale codes.
            or self._try_give_encoded_hint(player_view)
            or self._try_follow_chop_and_discard_recommendation(player_view, recommendation)
            or self._try_discard_c1(player_view)
            or self._try_play_oldest_as_last_resort(player_view)
        )
        assert move is not None
        assert self.is_move_legal(player_view, move), "ThreePlayerRecommendationPlayer chooses legal moves only"
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
            peer_rec = self._peer_recommendation_for_decode(observer_view, exclude_index=player_index)
            self._my_decoded_recommendation = (channel_id - peer_rec) % 7

    def _hand_cards_for_hint_target(self, target: int, observer_view: PlayerView) -> Optional[List[Card]]:
        """Visible cards on the hinted seat, or ``None`` when the observer is the receiver (own hand omitted)."""
        if target != self._player_index:
            return observer_view.teammates[target].cards
        return None

    def _peer_recommendation_for_decode(self, player_view: PlayerView, *, exclude_index: int) -> int:
        for p in range(NUM_PLAYERS_FOR_MINI_RECOMMENDATION):
            if p == self._player_index or p == exclude_index:
                continue
            if p not in player_view.teammates:
                continue
            return self._get_recommendation_for_hand(
                player_view.teammates[p].cards,
                self.common_view,
                self.game_settings,
            )
        assert False, "3p decode requires one visible peer besides hinter"

    def _sum_peer_recommendations(self, player_view: PlayerView) -> tuple[int, int, str]:
        parts: list[str] = []
        total = 0
        for p in range(NUM_PLAYERS_FOR_MINI_RECOMMENDATION):
            if p == self._player_index or p not in player_view.teammates:
                continue
            rec = self._get_recommendation_for_hand(
                player_view.teammates[p].cards,
                self.common_view,
                self.game_settings,
            )
            total += rec
            parts.append(f"P{p + 1}:{rec}")
        return total, total % 7, ", ".join(parts)

    def _get_my_recommendation(self) -> Optional[int]:
        return self._my_decoded_recommendation

    def get_gui_recommendation_by_slot(self, player_view: PlayerView) -> Dict[int, str]:
        """Map hand slot indices to ``play`` or ``discard`` for GUI indicators."""
        rec = self._my_decoded_recommendation
        if rec is None:
            return {}
        if 0 == rec:
            chop = player_view.own_hand_size - 1
            return {chop: "discard"} if 0 <= chop else {}
        if 1 <= rec <= 5:
            slot = rec - 1
            return {slot: "play"} if slot < player_view.own_hand_size else {}
        return {}

    def _get_recommendation_for_hand(
        self,
        hand_cards: List[Card],
        common_view: CommonView,
        settings: GameSettings,
    ) -> int:
        for rule in (
            self._rec_play_rank5,
            self._rec_play_lowest_rank,
            self._rec_discard_chop_safe,
            self._rec_avoid_discarding_chop,
            self._rec_discard_chop_dispensable,
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
                return idx + 1
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
        return playable[0][0] + 1

    @staticmethod
    def _rec_discard_chop_safe(
        hand_cards: List[Card], common_view: CommonView, settings: GameSettings
    ) -> Optional[int]:
        """Code 0: chop is useless."""
        if not hand_cards:
            return None
        chop = _chop_index(len(hand_cards))
        card = hand_cards[chop]
        if CardKind.USELESS == common_view.card_kind(card, settings):
            return 0
        return None

    @staticmethod
    def _rec_avoid_discarding_chop(
        hand_cards: List[Card], common_view: CommonView, settings: GameSettings
    ) -> Optional[int]:
        """Code 6: chop is critical or playable."""
        if not hand_cards:
            return None
        chop = _chop_index(len(hand_cards))
        card = hand_cards[chop]
        kind = common_view.card_kind(card, settings)
        if CardKind.CRITICAL == kind or CardKind.PLAYABLE == kind:
            return 6
        return None

    @staticmethod
    def _rec_discard_chop_dispensable(
        hand_cards: List[Card], common_view: CommonView, settings: GameSettings
    ) -> Optional[int]:
        """Code 0: chop is dispensable (still safe to discard chop)."""
        if not hand_cards:
            return None
        chop = _chop_index(len(hand_cards))
        card = hand_cards[chop]
        if CardKind.DISPENSABLE == common_view.card_kind(card, settings):
            return 0
        return None

    @staticmethod
    def _rec_fallback_code_zero(
        hand_cards: List[Card], _common_view: CommonView, _settings: GameSettings
    ) -> int:
        return 0

    def _try_follow_play_recommendation(
        self,
        player_view: PlayerView,
        recommendation: Optional[int],
        plays_since_hint: int,
        errors: int,
    ) -> Optional[Move]:
        if recommendation is None:
            return None
        assert 0 <= recommendation <= 6
        if not (1 <= recommendation <= 5):
            return None
        play_idx = recommendation - 1
        if play_idx >= player_view.own_hand_size:
            return None
        if not self.is_move_legal(player_view, Play(play_idx)):
            return None
        if 0 == plays_since_hint:
            detail = "no play since last hint → follow"
        elif 1 == plays_since_hint and 2 > errors:
            detail = "one play since hint, <2 errors → follow"
        else:
            return None
        self._last_decision_summary = (
            f"[3p mod-7] Play card {play_idx + 1} (code {recommendation}) — {detail}"
        )
        # Recommendation consumed: clear so we don't act on it again on a future turn
        # before a fresh hint arrives. Stale follow-play is what caused replay-debug
        # misplays like P3 playing slot 0 a second time after only discards in between.
        self._my_decoded_recommendation = None
        return Play(play_idx)

    def _try_give_encoded_hint(self, player_view: PlayerView) -> Optional[Move]:
        """
        Emit a hint that encodes ``sum_mod7`` on the **exact** channel ``cid == sum_mod7``.

        If that channel can't be built on the target's hand (only possible when the target
        hand is entirely one rank or one color — see :func:`_right_number_spec` and
        :func:`_right_color_spec`), we abstain so receivers never decode a shifted value. The
        dispatch chain then falls through to discard / play-slot-0. Every emitted hint
        therefore carries the intended recommendation exactly; there is no shifted-hint mode.
        """
        if 0 == self.common_view.hint_tokens:
            return None
        _, sum_mod7, peer_breakdown = self._sum_peer_recommendations(player_view)
        hint_move = _build_channel_hint(self._player_index, player_view, sum_mod7)
        if hint_move is None:
            return None
        if not self.is_move_legal(player_view, hint_move):
            return None
        self._last_decision_summary = (
            f"[3p mod-7] Hint channel {sum_mod7} (exact) · "
            f"peer codes sum mod 7 = {sum_mod7} · {peer_breakdown}"
        )
        return hint_move

    def _try_play_oldest_as_last_resort(self, player_view: PlayerView) -> Optional[Move]:
        """
        Last-resort fallback for the rare state where no other branch can fire:

        - no play / discard recommendation to follow,
        - exact-channel hint unbuildable (target hand all one rank or all one color),
        - C1 discard illegal (max hint tokens).

        Playing slot ``0`` is always legal as long as the hand is non-empty. The card is
        typically the oldest in the hand (most accumulated hints) and so has the highest
        a-priori chance of being playable. This replaces the old ``allow_shift=True`` branch
        which would broadcast a wrong-channel code to every teammate at once.
        """
        if not self.is_move_legal(player_view, Play(0)):
            return None
        self._last_decision_summary = (
            "[3p mod-7] Play slot 0 (last resort: no exact hint buildable at max tokens)"
        )
        return Play(0)

    def _try_follow_chop_and_discard_recommendation(
        self,
        player_view: PlayerView,
        recommendation: Optional[int],
    ) -> Optional[Move]:
        if recommendation is None:
            return None
        hs = player_view.own_hand_size
        chop = _chop_index(hs)

        if 0 == recommendation:
            if self.is_move_legal(player_view, Discard(chop)):
                self._last_decision_summary = "[3p mod-7] Discard chop (code 0 · chop safe)"
                # Recommendation consumed (see _try_follow_play_recommendation for rationale).
                self._my_decoded_recommendation = None
                return Discard(chop)
            return None

        if 6 == recommendation:
            for idx in _REC_SLOT_ORDER:
                if idx >= hs or idx == chop:
                    continue
                if self.is_move_legal(player_view, Discard(idx)):
                    self._last_decision_summary = "[3p mod-7] Discard non-chop slot (code 6 · keep chop)"
                    # Recommendation consumed (see _try_follow_play_recommendation for rationale).
                    self._my_decoded_recommendation = None
                    return Discard(idx)
            return None

        return None

    def _try_discard_c1(self, player_view: PlayerView) -> Optional[Move]:
        """Discard slot 0 if legal. Illegal (and so returns ``None``) at max hint tokens."""
        if not self.is_move_legal(player_view, Discard(0)):
            return None
        self._last_decision_summary = "[3p mod-7] Discard oldest (C1 / index 0) — fallback"
        return Discard(0)


def _slot_card(hand_cards: List[Card], idx: int) -> Optional[Card]:
    return hand_cards[idx] if idx < len(hand_cards) else None


def _chop_index(hand_size: int) -> int:
    assert 0 < hand_size
    return hand_size - 1


def _seat_offset_pos(hinter: int, target: int) -> int:
    """Same ring offset as :meth:`RecommendationPlayer._observe_recommendation_hint` (``pos``)."""
    return (target - hinter - 1) % NUM_PLAYERS_FOR_MINI_RECOMMENDATION


def _infer_channel_id(
    hinter: int,
    target: int,
    move: ColorHint | NumberHint,
    hand_cards: Optional[List[Card]],
) -> int:
    """Map an observed hint to channel index ``0``–``6`` (see module docstring)."""
    if hand_cards is not None:
        return _infer_channel_id_from_hand(hinter, target, move, hand_cards)
    return _infer_channel_id_public(hinter, target, move)


def _infer_channel_id_from_hand(hinter: int, target: int, move: ColorHint | NumberHint, hand_cards: List[Card]) -> int:
    next_p = (hinter + 1) % NUM_PLAYERS_FOR_MINI_RECOMMENDATION
    to_next = target == next_p
    assert target == next_p or target == (hinter - 1) % NUM_PLAYERS_FOR_MINI_RECOMMENDATION

    sort_idx = sorted(move.cards)

    if isinstance(move, NumberHint):
        ln, li = _left_number_spec(hand_cards)
        if move.number == ln and sort_idx == li:
            return 0 if to_next else 1
        rs = _right_number_spec(hand_cards)
        if rs is not None:
            rn, ri = rs
            if move.number == rn and sort_idx == ri:
                return 4 if to_next else 5
        assert False, "number hint does not match left/right rank specs"

    lc, lci = _left_color_spec(hand_cards)
    if move.color == lc and sort_idx == lci:
        return 2 if to_next else 3

    rcs = _right_color_spec(hand_cards)
    if rcs is not None and to_next:
        rc, rci = rcs
        if move.color == rc and sort_idx == rci:
            return 6

    assert False, "color hint does not match left/right color specs"


def _infer_channel_id_public(hinter: int, target: int, move: ColorHint | NumberHint) -> int:
    """
    Infer channel when the hinted hand is not visible (receiver observer).

    Uses ``pos = (target - hinter - 1) % 3`` for next vs previous (same as RecommendationPlayer’s
    seat offset) and ``0 in move.cards`` to separate left vs right-style channels (see module doc).
    """
    next_p = (hinter + 1) % NUM_PLAYERS_FOR_MINI_RECOMMENDATION
    to_next = target == next_p
    assert target == next_p or target == (hinter - 1) % NUM_PLAYERS_FOR_MINI_RECOMMENDATION
    pos = _seat_offset_pos(hinter, target)
    assert to_next == (0 == pos)

    sort_idx = sorted(move.cards)
    touches_slot0 = 0 in sort_idx

    if isinstance(move, NumberHint):
        if touches_slot0:
            return 0 if to_next else 1
        return 4 if to_next else 5

    if touches_slot0:
        return 2 if to_next else 3
    if to_next:
        return 6
    return 3


def _build_channel_hint(player_index: int, player_view: PlayerView, channel_id: int) -> Optional[HintMove]:
    """Construct the hint move for ``channel_id`` (``0``–``6``) if legal on ``player_view``."""
    if not (0 <= channel_id <= 6):
        return None

    next_t = (player_index + 1) % NUM_PLAYERS_FOR_MINI_RECOMMENDATION
    prev_t = (player_index - 1) % NUM_PLAYERS_FOR_MINI_RECOMMENDATION
    to_next = channel_id in (0, 2, 4, 6)
    target = next_t if to_next else prev_t
    if target not in player_view.teammates:
        return None
    hand = player_view.teammates[target].cards
    if not hand:
        return None

    if channel_id in (0, 1):
        rank, indices = _left_number_spec(hand)
        return NumberHint(target, indices, rank)

    if channel_id in (4, 5):
        built = _build_right_number_hint(target, hand)
        return built

    if channel_id in (2, 3):
        color, indices = _left_color_spec(hand)
        return ColorHint(target, indices, color)

    assert 6 == channel_id
    built = _build_right_color_hint(target, hand)
    return built


def _left_number_spec(hand: List[Card]) -> tuple[Number, List[int]]:
    """Rank at slot ``0`` (index-based left); all cards of that rank."""
    r = hand[0].number
    indices = sorted(i for i, c in enumerate(hand) if r == c.number)
    return r, indices


def _right_number_spec(hand: List[Card]) -> Optional[tuple[Number, List[int]]]:
    """
    Rank of the **rightmost** card whose rank differs from :func:`_left_number_spec`'s rank;
    touch all cards of that rank on the hand.

    Unavailable (returns ``None``) **only** when every card in the hand shares the same rank
    (so no card can carry a "right" hint distinct from the left one). With a standard 5-card
    hand and the standard deck this requires all 5 cards to be the same rank, which is rare.
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
    """Color of the card at index ``0``; all cards of that color."""
    col = hand[0].color
    indices = sorted(i for i, c in enumerate(hand) if col == c.color)
    return col, indices


def _right_color_spec(hand: List[Card]) -> Optional[tuple[Color, List[int]]]:
    """
    Color of the **rightmost** card whose color differs from :func:`_left_color_spec`'s color;
    touch all cards of that color on the hand.

    Unavailable (returns ``None``) **only** when every card in the hand shares the same color.
    With a standard 5-card hand each color only has 10 cards total in the deck, so this case
    is rare but possible.
    """
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
