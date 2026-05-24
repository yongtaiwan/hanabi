"""
Mini recommendation strategy for **4-player** Hanabi.

Direct extension of :class:`~hanabi.ai.three_player_recommendation.ThreePlayerRecommendationPlayer`
with a **mod-9** alphabet over visible hands. **Nine physical channels** (``0``–``8``):
**3 hint shapes × 3 seat directions** ``next``, ``next+1``, ``next+2`` (``next+2`` is the
previous seat for 4p). Right color is **not** used; left number / left color cover every
hand, and right number adds payload spread.

- **0–2:** left number  → next / next+1 / next+2
- **3–5:** left color   → next / next+1 / next+2
- **6–8:** right number → next / next+1 / next+2

**Left vs right (index-based, same as 3p):**

- *Left number / color:* rank / color of the card at hand index ``0``, all matching indices.
- *Right number:* minimum rank on slots ``1 .. n-1``, then every card of that rank on the full
  hand. ``None`` (channel unavailable) when the spec collapses with the left spec.

**Seat offset (matches** :class:`~hanabi.ai.recommendation_player.RecommendationPlayer`):
``pos = (T - H - 1) % 4`` ∈ {0, 1, 2}; channel ``c`` ⇒ direction ``c % 3``.

**Decoded value** (receiver action):

- ``0`` — no info; fall through to default discard.
- ``1`` – ``4`` — play slot ``value - 1``.
- ``5`` – ``8`` — slot ``value - 5`` is the **most useless**: receiver may discard that slot,
  or spend a hint instead, before falling through to the default discard.

The encoder picks code ``5+idx`` from the chop first, otherwise the earliest ``USELESS`` /
``DISPENSABLE`` non-chop slot — so when chop is critical the recommendation steers the
receiver toward a different slot rather than the chop.

**Receiver-as-target ambiguity (same caveat as 3p mini-rec):** when the observer is the hint
target, :class:`~hanabi.core.game.PlayerView` does not list the observer's own hand. Left vs
right is approximated from public fields (``0 in move.cards``); color hints always come from
the left-color shape (right color is unused), so they map directly to ``3 + pos``.
"""

from __future__ import annotations

from typing import List, Optional

NUM_PLAYERS_FOR_FOUR_PLAYER_RECOMMENDATION = 4
NUM_CHANNELS = 9

from hanabi.core.player import BasePlayer
from hanabi.core.game import CommonView, GameSettings, PlayerView
from hanabi.core.moves import Move, Play, Discard, ColorHint, NumberHint, HintMove
from hanabi.core.enums import Color, Number, CardKind
from hanabi.core.card import Card

# Slot indices iterated by recommendation rules. 4p hands hold 4 cards (indices 0..3); the
# fifth slot is included for symmetry with the 3p code so out-of-range checks fall through
# naturally if a hand size ever exceeds 4 in tooling.
_REC_SLOT_ORDER = (0, 1, 2, 3, 4)


class FourPlayerRecommendationPlayer(BasePlayer):
    """
    4-player mini recommendation bot (mod-9 decode, nine hint channels ``0``–``8``).

    Only standard 4-player settings from :func:`~hanabi.core.game.create_standard_game_settings`.
    """

    def __init__(self, player_index: int):
        super().__init__(player_index)
        self._plays_since_hint: int = 0
        self._last_decision_summary: Optional[str] = None
        self._my_decoded_recommendation: Optional[int] = None

    @classmethod
    def supports_game_settings(cls, game_settings: GameSettings) -> bool:
        return NUM_PLAYERS_FOR_FOUR_PLAYER_RECOMMENDATION == game_settings.num_players

    def set_game_settings(self, game_settings: GameSettings) -> None:
        assert NUM_PLAYERS_FOR_FOUR_PLAYER_RECOMMENDATION == game_settings.num_players, (
            "FourPlayerRecommendationPlayer requires 4-player games"
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
        errors = self.game_settings.max_live_tokens - self.common_view.live_tokens
        recommendation = self._get_my_recommendation()

        move = (
            self._try_follow_play_recommendation(player_view, recommendation, self._plays_since_hint, errors)
            or self._try_give_encoded_hint(player_view)
            or self._try_follow_useless_slot_discard(player_view, recommendation)
            or self._try_discard_c1(player_view)
            or self._try_give_encoded_hint(player_view, allow_shift=True)
        )
        assert move is not None
        assert self.is_move_legal(player_view, move), "FourPlayerRecommendationPlayer chooses legal moves only"
        return move

    def get_decision_summary(self) -> Optional[str]:
        return self._last_decision_summary

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
            self._my_decoded_recommendation = (channel_id - others_sum) % NUM_CHANNELS

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

    def _get_my_recommendation(self) -> Optional[int]:
        return self._my_decoded_recommendation

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
        recommendation: Optional[int],
        plays_since_hint: int,
        errors: int,
    ) -> Optional[Move]:
        if recommendation is None:
            return None
        assert 0 <= recommendation < NUM_CHANNELS
        if not (1 <= recommendation <= 4):
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
            f"[4p mod-9] Play card {play_idx + 1} (code {recommendation}) — {detail}"
        )
        return Play(play_idx)

    def _try_give_encoded_hint(self, player_view: PlayerView, *, allow_shift: bool = False) -> Optional[Move]:
        """
        Emit a hint that encodes ``sum_mod``.

        Default (``allow_shift=False``): only the **exact** channel ``cid == sum_mod`` is built;
        if it can't be built (right-number spec collapses with left), we abstain so receivers
        never decode a shifted value. The dispatch chain falls through to discard. Every
        emitted hint therefore carries the intended recommendation exactly.

        Last-resort (``allow_shift=True``): used **only** after the discard path was illegal
        (max hint tokens). We then iterate ``delta`` to find any buildable channel because the
        bot must produce a legal move. Receivers may decode a shifted value (one bomb at most
        before the next strict hint resets state), which we accept since the alternative is no
        legal move at all.
        """
        if 0 == self.common_view.hint_tokens:
            return None
        _, sum_mod, peer_breakdown = self._sum_peer_recommendations(player_view)
        deltas = range(NUM_CHANNELS) if allow_shift else (0,)
        for delta in deltas:
            cid = (sum_mod + delta) % NUM_CHANNELS
            hint_move = _build_channel_hint(self._player_index, player_view, cid)
            if hint_move is None:
                continue
            if not self.is_move_legal(player_view, hint_move):
                continue
            kind = "shifted" if 0 != delta else "exact"
            self._last_decision_summary = (
                f"[4p mod-9] Hint channel {cid} ({kind}, delta={delta}) · "
                f"peer codes sum mod 9 = {sum_mod} · {peer_breakdown}"
            )
            return hint_move
        return None

    def _try_follow_useless_slot_discard(
        self,
        player_view: PlayerView,
        recommendation: Optional[int],
    ) -> Optional[Move]:
        """
        Code ``5``–``8``: ``code - 5`` is the most-useless slot in our hand → discard it.

        Codes ``0`` and ``1``–``4`` (no info / play) fall through to the next move source.
        Returns ``None`` if the indicated slot is out of range or the discard is illegal so
        the caller can try the C1 fallback.
        """
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
            f"[4p mod-9] Discard card {discard_idx + 1} (code {recommendation} · most useless slot)"
        )
        return Discard(discard_idx)

    def _try_discard_c1(self, player_view: PlayerView) -> Optional[Move]:
        """Discard slot 0 if legal. Illegal (and so returns ``None``) at max hint tokens."""
        if not self.is_move_legal(player_view, Discard(0)):
            return None
        self._last_decision_summary = "[4p mod-9] Discard oldest (C1 / index 0) — fallback"
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
    """Map an observed hint to channel index ``0``–``8`` (see module docstring)."""
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

    assert False, "color hint does not match left color spec (right color is unused in mod-9)"


def _infer_channel_id_public(hinter: int, target: int, move: ColorHint | NumberHint) -> int:
    """
    Receiver-as-target fallback (own hand not in :class:`PlayerView`).

    Uses ``pos`` for direction (same as full-hand path). Number hints split left vs right by
    ``0 in move.cards`` (same approximation as 3p mini-rec); color hints always come from the
    left-color shape since right color is unused in the mod-9 alphabet.
    """
    pos = _seat_offset_pos(hinter, target)
    assert 0 <= pos <= 2, f"4p hint must target next, next+1, or next+2 (pos in [0,2]); got {pos}"

    if isinstance(move, NumberHint):
        return (0 + pos) if 0 in move.cards else (6 + pos)
    return 3 + pos


def _build_channel_hint(player_index: int, player_view: PlayerView, channel_id: int) -> Optional[HintMove]:
    """Construct the hint move for ``channel_id`` (``0``–``8``) if legal on ``player_view``."""
    if not (0 <= channel_id < NUM_CHANNELS):
        return None

    hint_kind = channel_id // 3  # 0=left_num, 1=left_color, 2=right_num
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

    assert 2 == hint_kind
    return _build_right_number_hint(target, hand)


# ---------------------------------------------------------------------------
# Hand-shape helpers (parallel to :mod:`hanabi.ai.three_player_recommendation`).
# Kept local so this file is self-contained for structural symmetry with 3p.
# ---------------------------------------------------------------------------


def _left_number_spec(hand: List[Card]) -> tuple[Number, List[int]]:
    """Rank at slot ``0``; all cards of that rank (index-based ``left``)."""
    r = hand[0].number
    indices = sorted(i for i, c in enumerate(hand) if r == c.number)
    return r, indices


def _right_number_spec(hand: List[Card]) -> Optional[tuple[Number, List[int]]]:
    """Min rank in slots ``1 .. n-1``, all cards of that rank. ``None`` when same as left spec."""
    if len(hand) < 2:
        return None
    tail = hand[1:]
    r = min((c.number for c in tail), key=lambda n: n.value)
    indices = sorted(i for i, c in enumerate(hand) if r == c.number)
    ln, li = _left_number_spec(hand)
    if r == ln and indices == li:
        return None
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
