"""
3-player Hanabi convention (dynamic recommendation encoding, mod ``8``).

Canonical spec: ``THREE_PLAYER_DYNAMIC_RECOMMENDATION.md`` at the repo root.
"""

from __future__ import annotations

from enum import Enum
from typing import Dict, List, Optional, Sequence, Set, Tuple

from hanabi.ai.dr_belief import (
    HandBelief,
    Playability,
    apply_decoded_value,
    copy_hand_belief,
    ensure_default_chop,
    finalize_chop_after_shift,
    fresh_hand_belief,
    fresh_slot_belief,
    indicable_discard_options,
    n_play,
    play_reopens_playability,
    play_type_for_slot,
    reopen_unplayable,
    reset_chop_after_removal,
    slot_for_play_type,
)
from hanabi.core.card import Card, Suit
from hanabi.core.enums import CardKind, Color, Number
from hanabi.core.game import CommonView, GameSettings, PlayerView
from hanabi.core.moves import ColorHint, Discard, HintMove, Move, NumberHint, Play, move_with_why
from hanabi.core.player import BasePlayer


class HintSlotShape(Enum):
    """Which index band a hint touches (see module docstring)."""

    OLD = "old"
    MID = "mid"
    NEW = "new"


class ChopClass(Enum):
    """Own-hand chop urgency for the hint×chop matrix (§9)."""

    CONFIRMED = "confirmed"
    DEFAULT = "default"


class HintQuality(Enum):
    """Would-be convention hint quality for the hint×chop matrix (§9)."""

    GOOD = "good"
    FINE = "fine"
    BAD = "bad"


# True → prefer hint; False → prefer discard chop. Keys: (HintQuality, ChopClass).
_HINT_CHOP_MATRIX: Dict[Tuple[HintQuality, ChopClass], bool] = {
    (HintQuality.GOOD, ChopClass.CONFIRMED): True,
    (HintQuality.GOOD, ChopClass.DEFAULT): True,
    (HintQuality.FINE, ChopClass.CONFIRMED): False,
    (HintQuality.FINE, ChopClass.DEFAULT): True,
    (HintQuality.BAD, ChopClass.CONFIRMED): False,
    (HintQuality.BAD, ChopClass.DEFAULT): False,
}


class DynamicRecommendation3P(BasePlayer):
    """
    3-player dynamic-recommendation convention bot.

    Standard 3-player settings from :func:`~hanabi.core.game.create_standard_game_settings`.
    """

    def __init__(self, player_index: int) -> None:
        super().__init__(player_index)
        self._hand_belief: List[HandBelief] = []
        self._discard_pile_snapshot: Dict[Color, Dict[Number, int]] = {}
        self._cards_played_snapshot: Dict[Color, Number] = {}
        self._last_decision_summary: Optional[str] = None

    @classmethod
    def supports_game_settings(cls, game_settings: GameSettings) -> bool:
        return 3 == game_settings.num_players

    def set_game_settings(self, game_settings: GameSettings) -> None:
        assert 3 == game_settings.num_players, "DynamicRecommendation3P requires 3-player games"
        super().set_game_settings(game_settings)
        self._init_belief_at_deal()

    def _init_belief_at_deal(self) -> None:
        hand_size = self.game_settings.max_cards_in_hand
        num_players = self.game_settings.num_players
        self._hand_belief = [fresh_hand_belief(hand_size) for _ in range(num_players)]
        self._discard_pile_snapshot = {}
        self._cards_played_snapshot = {}

    def _hand_size_for_player(self, player_index: int, observer_view: PlayerView) -> int:
        if player_index == self._player_index:
            return observer_view.own_hand_size
        assert player_index in observer_view.teammates
        return len(observer_view.teammates[player_index].cards)

    def observe_play_move(self, player_index: int, move: Play, observer_view: PlayerView) -> None:
        cards_played_before = self._cards_played_snapshot
        super().observe_play_move(player_index, move, observer_view)
        played_card = _card_from_successful_play(cards_played_before, self.common_view.cards_played)
        if (
            played_card is not None
            and play_reopens_playability(
                played_card, cards_played_before, self.common_view, self.game_settings
            )
        ):
            reopen_unplayable(self._hand_belief)
        self._shift_belief_after_removal(player_index, move.card, observer_view)
        self._discard_pile_snapshot = _flatten_discard_counts(self.common_view.cards_discarded)
        self._cards_played_snapshot = dict(self.common_view.cards_played)

    def observe_discard_move(self, player_index: int, move: Discard, observer_view: PlayerView) -> None:
        super().observe_discard_move(player_index, move, observer_view)
        self._shift_belief_after_removal(player_index, move.card, observer_view)
        self._discard_pile_snapshot = _flatten_discard_counts(self.common_view.cards_discarded)
        self._cards_played_snapshot = dict(self.common_view.cards_played)

    def observe_color_hint_move(self, player_index: int, move: ColorHint, observer_view: PlayerView) -> None:
        super().observe_color_hint_move(player_index, move, observer_view)
        _apply_convention_hint_decodes(
            player_index,
            move,
            observer_view,
            self._player_index,
            self.common_view,
            self.game_settings,
            self._hand_belief,
        )

    def observe_number_hint_move(self, player_index: int, move: NumberHint, observer_view: PlayerView) -> None:
        super().observe_number_hint_move(player_index, move, observer_view)
        _apply_convention_hint_decodes(
            player_index,
            move,
            observer_view,
            self._player_index,
            self.common_view,
            self.game_settings,
            self._hand_belief,
        )

    def play(self, player_view: PlayerView) -> Move:
        assert player_view.own_hand_size > 0
        self._last_decision_summary = None
        own = self._hand_belief[self._player_index]
        ensure_default_chop(own)
        # TODO(hint-bank): At max-1 tokens, playing a 5 refunds to max and discard-locks the
        # next seat — consider deferring that 5 when a safe discard exists and the would-be
        # forced hint is not good (see §9 token-banking notes).
        move = self._try_play_leftmost_playable(player_view)
        if move is None:
            can_hint = 0 < self.common_view.hint_tokens
            can_discard = self.common_view.hint_tokens < self.game_settings.max_hint_tokens
            if can_hint and can_discard and own.chop is not None:
                chop_class = _chop_class(own)
                hint_quality = _hint_quality(
                    self._player_index,
                    player_view,
                    self.common_view,
                    self.game_settings,
                    self._hand_belief,
                )
                prefer_hint = _HINT_CHOP_MATRIX[(hint_quality, chop_class)]
                # TODO(hint-bank): When tokens == max-1, discard (even default chop) unless
                # quality is good — avoid filling the bank via discard. Optional later: soft
                # caution at max-2; endgame/short deck may ignore banking.
                if prefer_hint:
                    if HintQuality.GOOD == hint_quality:
                        why_prefix = (
                            "[3p DR] Hint (identifies playable for next)"
                            if _convention_hint_would_identify_new_playable(
                                self._player_index,
                                player_view,
                                self.common_view,
                                self.game_settings,
                                self._hand_belief,
                            )
                            else "[3p DR] Hint (trash for next + playable for prev)"
                        )
                    else:
                        why_prefix = f"[3p DR] Hint ({hint_quality.value}/{chop_class.value})"
                    move = self._give_convention_hint(player_view, why_prefix=why_prefix)
                else:
                    move = self._discard_chop(player_view, chop_class)
            elif can_hint:
                # TODO(hint-bank): At max tokens discard is illegal. Prefer playable if any
                # (already tried above). If hinting, avoid harmful convention when quality is
                # bad — literal escape instead of double mid-rank discard (§9.3 deferred).
                move = self._give_convention_hint(player_view)
            else:
                chop_class = _chop_class(own) if own.chop is not None else None
                move = (
                    self._discard_chop(player_view, chop_class)
                    if chop_class is not None
                    else None
                )
        if move is None:
            move = self._discard_oldest(player_view)
        assert move is not None, "no legal convention move: play, hint, discard chop/oldest"
        assert self.is_move_legal(player_view, move)
        assert self._last_decision_summary is not None
        return move_with_why(move, self._last_decision_summary)

    def get_gui_inferred_kind_by_slot(self, target_seat: int) -> Dict[int, CardKind]:
        """Return ``{slot: CardKind.PLAYABLE}`` where convention playability is playable."""
        if not self._hand_belief or target_seat >= len(self._hand_belief):
            return {}
        result: Dict[int, CardKind] = {}
        for slot, belief in enumerate(self._hand_belief[target_seat].slots):
            if Playability.PLAYABLE == belief.playability:
                result[slot] = CardKind.PLAYABLE
        return result

    def get_gui_unplayable_slots(self, target_seat: int) -> Set[int]:
        if not self._hand_belief or target_seat >= len(self._hand_belief):
            return set()
        return {
            slot
            for slot, belief in enumerate(self._hand_belief[target_seat].slots)
            if Playability.UNPLAYABLE == belief.playability
        }

    def get_gui_chop_slot(self, target_seat: int) -> Optional[int]:
        if not self._hand_belief or target_seat >= len(self._hand_belief):
            return None
        hand = self._hand_belief[target_seat]
        ensure_default_chop(hand)
        return hand.chop

    def get_gui_chop_confirmed(self, target_seat: int) -> Optional[bool]:
        """``True``/``False`` when chop exists; ``None`` if no chop."""
        if not self._hand_belief or target_seat >= len(self._hand_belief):
            return None
        hand = self._hand_belief[target_seat]
        ensure_default_chop(hand)
        if hand.chop is None:
            return None
        return hand.chop_confirmed

    def _shift_belief_after_removal(self, player_index: int, removed: int, observer_view: PlayerView) -> None:
        assert self._hand_belief, "belief must be initialized before play/discard observe"
        hand = self._hand_belief[player_index]
        reset_chop_after_removal(hand, removed)
        shifted = hand.slots[:removed] + hand.slots[removed + 1 :]
        hand_size_after = self._hand_size_for_player(player_index, observer_view)
        if self.game_settings.max_cards_in_hand == hand_size_after:
            shifted.append(fresh_slot_belief())
        hand.slots = shifted
        finalize_chop_after_shift(hand)

    def _try_play_leftmost_playable(self, player_view: PlayerView) -> Optional[Move]:
        for slot, belief in enumerate(self._hand_belief[self._player_index].slots):
            if Playability.PLAYABLE != belief.playability:
                continue
            assert self.is_move_legal(player_view, Play(slot))
            self._last_decision_summary = f"[3p DR] Play slot {slot} (identified playable)"
            return Play(slot)
        return None

    def _give_convention_hint(
        self, player_view: PlayerView, *, why_prefix: str = "[3p DR] Convention hint"
    ) -> Optional[Move]:
        if 0 == self.common_view.hint_tokens:
            return None
        enc_type, type_sum = _channel_encoded_type(
            self._player_index,
            player_view,
            self.common_view,
            self.game_settings,
            self._hand_belief,
        )
        hint_move = _build_hint_for_encoded(self._player_index, player_view, enc_type)
        if hint_move is None:
            hint_move = _build_literal_fallback_hint(self._player_index, player_view)
            assert hint_move is not None, (
                f"literal fallback hint must exist when convention type {enc_type} is unbuildable"
            )
            assert self.is_move_legal(player_view, hint_move), (
                f"literal fallback hint is illegal: {hint_move!r}"
            )
            self._last_decision_summary = (
                f"{why_prefix} literal fallback (unbuildable type={enc_type}, {type_sum})"
            )
            return hint_move
        assert self.is_move_legal(player_view, hint_move), (
            f"built convention hint is illegal: {hint_move!r} enc_type={enc_type}"
        )
        self._last_decision_summary = f"{why_prefix} type={enc_type} ({type_sum})"
        return hint_move

    def _discard_chop(self, player_view: PlayerView, chop_class: Optional[ChopClass]) -> Optional[Move]:
        hand = self._hand_belief[self._player_index]
        ensure_default_chop(hand)
        if hand.chop is None:
            return None
        if not self.is_move_legal(player_view, Discard(hand.chop)):
            return None
        label = chop_class.value if chop_class is not None else (
            "confirmed" if hand.chop_confirmed else "unconfirmed"
        )
        self._last_decision_summary = f"[3p DR] Discard chop slot {hand.chop} ({label})"
        return Discard(hand.chop)

    def _discard_oldest(self, player_view: PlayerView) -> Optional[Move]:
        if not self.is_move_legal(player_view, Discard(0)):
            return None
        self._last_decision_summary = "[3p DR] Discard slot 0 (oldest; no chop)"
        return Discard(0)


def _card_from_successful_play(
    before_played: Dict[Color, Number],
    after_played: Dict[Color, Number],
) -> Optional[Card]:
    found: Optional[Card] = None
    for color in set(before_played) | set(after_played):
        before_top = before_played.get(color)
        after_top = after_played.get(color)
        if before_top == after_top:
            continue
        assert after_top is not None and found is None, (
            f"expected exactly one pile advance: before={before_played!r} after={after_played!r}"
        )
        found = Card(color, after_top)
    return found


def _flatten_discard_counts(cards_discarded: Dict[Color, Suit]) -> Dict[Color, Dict[Number, int]]:
    return {color: suit.cards.copy() for color, suit in cards_discarded.items()}


def _peer_code_for_hand(
    hand: List[Card],
    belief: HandBelief,
    common_view: CommonView,
    settings: GameSettings,
) -> int:
    """Peer code from one visible hand + that seat's shared public belief + piles.

    Does not read any other hand. Callers must pass the convention belief row for
    ``hand`` (chop / playability), not a fresh blank row.
    """
    assert len(hand) == len(belief.slots), (
        f"hand size {len(hand)} != belief slots {len(belief.slots)}"
    )
    code, _discard_card = _encode_peer_code(hand, belief, common_view, settings)
    return code


def _peer_codes_next_then_prev(
    hinter: int,
    player_view: PlayerView,
    common_view: CommonView,
    settings: GameSettings,
    hand_belief: List[HandBelief],
) -> Dict[int, int]:
    """Encode each visible teammate from shared belief + that hand's cards only."""
    next_seat = (hinter + 1) % 3
    prev_seat = (hinter + 2) % 3
    assert next_seat in player_view.teammates and prev_seat in player_view.teammates
    return {
        next_seat: _peer_code_for_hand(
            player_view.teammates[next_seat].cards,
            hand_belief[next_seat],
            common_view,
            settings,
        ),
        prev_seat: _peer_code_for_hand(
            player_view.teammates[prev_seat].cards,
            hand_belief[prev_seat],
            common_view,
            settings,
        ),
    }


def _apply_convention_hint_decodes(
    hinter_index: int,
    move: ColorHint | NumberHint,
    observer_view: PlayerView,
    observer_index: int,
    common_view: CommonView,
    settings: GameSettings,
    hand_belief: List[HandBelief],
) -> None:
    """Update belief from the public channel using shared belief + visible cards.

    Every observer applies the public decode to **both** non-hinter hands and never to the
    hinter's hand. Peer codes are snapshotted before either decode mutates belief (§4.2).
    When the peer hand is the observer's own (invisible), ``enc = peer_next + peer_prev``
    implies the other seat's message equals that seat's peer code.
    """
    hint_target = move.teammate
    other_non_hinter = _third_player_index(hinter_index, hint_target)

    if hint_target in observer_view.teammates:
        target_size = len(observer_view.teammates[hint_target].cards)
    else:
        target_size = observer_view.own_hand_size

    encoded_type = _infer_encoded_type_from_hint(hinter_index, hint_target, move, target_size)

    if hint_target in observer_view.teammates:
        canonical = _build_hint_for_encoded(hinter_index, observer_view, encoded_type)
        if canonical is None or not _hints_match(canonical, move):
            return

    # Snapshot peer codes for every visible non-hinter before mutating either row.
    peer_code_by_seat: Dict[int, int] = {}
    for seat in (hint_target, other_non_hinter):
        if seat not in observer_view.teammates:
            continue
        peer_code_by_seat[seat] = _peer_code_for_hand(
            observer_view.teammates[seat].cards,
            hand_belief[seat],
            common_view,
            settings,
        )

    decoded_by_seat: Dict[int, int] = {}
    for decoder in (hint_target, other_non_hinter):
        peer_index = other_non_hinter if decoder == hint_target else hint_target
        if peer_index in peer_code_by_seat:
            decoded_by_seat[decoder] = (encoded_type - peer_code_by_seat[peer_index]) % 8
        else:
            assert decoder in peer_code_by_seat, (
                f"P{observer_index + 1} must see decoder P{decoder + 1} to apply public decode"
            )
            decoded_by_seat[decoder] = peer_code_by_seat[decoder]

    for decoder, decoded in decoded_by_seat.items():
        apply_decoded_value(hand_belief[decoder], decoded)


def assert_independent_own_decode_matches(
    players: Sequence[DynamicRecommendation3P],
    hinter_index: int,
    move: ColorHint | NumberHint,
    views: Sequence[PlayerView],
    own_rows_before: Sequence[HandBelief],
) -> None:
    """After observe, each decoder's own hand belief must equal decode(pre-hint own)."""
    assert 3 == len(players) == len(views) == len(own_rows_before)
    if not isinstance(move, (ColorHint, NumberHint)):
        return
    hint_target = move.teammate
    other_non_hinter = _third_player_index(hinter_index, hint_target)
    for seat in (hint_target, other_non_hinter):
        peer = other_non_hinter if seat == hint_target else hint_target
        view = views[seat]
        assert peer in view.teammates
        if hint_target in view.teammates:
            target_size = len(view.teammates[hint_target].cards)
        else:
            target_size = view.own_hand_size
        enc = _infer_encoded_type_from_hint(hinter_index, hint_target, move, target_size)
        if hint_target in view.teammates:
            canonical = _build_hint_for_encoded(hinter_index, view, enc)
            if canonical is None or not _hints_match(canonical, move):
                assert players[seat]._hand_belief[seat] == own_rows_before[seat], (
                    f"P{seat + 1} own belief changed on literal fallback hint"
                )
                continue
        peer_code = _peer_code_for_hand(
            view.teammates[peer].cards,
            own_rows_before[peer],
            players[seat].common_view,
            players[seat].game_settings,
        )
        assert peer_code == _peer_code_for_hand(
            views[hinter_index].teammates[peer].cards,
            own_rows_before[peer],
            players[hinter_index].common_view,
            players[hinter_index].game_settings,
        ), f"peer code for P{peer + 1} not publicly determined"
        expected = copy_hand_belief(own_rows_before[seat])
        apply_decoded_value(expected, (enc - peer_code) % 8)
        assert players[seat]._hand_belief[seat] == expected, (
            f"P{seat + 1} own belief after hint != independent decode: "
            f"actual={players[seat]._hand_belief[seat]!r} expected={expected!r}"
        )


def assert_public_non_hinter_rows_agree(
    players: Sequence[DynamicRecommendation3P],
    hinter_index: int,
    move: ColorHint | NumberHint,
) -> None:
    """After a convention hint, all seats must share the same next/prev belief rows."""
    assert 3 == len(players)
    if not isinstance(move, (ColorHint, NumberHint)):
        return
    hint_target = move.teammate
    other_non_hinter = _third_player_index(hinter_index, hint_target)
    for seat in (hint_target, other_non_hinter):
        ref = players[0]._hand_belief[seat]
        for player in players[1:]:
            assert player._hand_belief[seat] == ref, (
                f"P{player._player_index + 1} belief for P{seat + 1} != P1 after "
                f"hint from P{hinter_index + 1}: {player._hand_belief[seat]!r} vs {ref!r}"
            )


def _hints_match(a: HintMove, b: HintMove) -> bool:
    if isinstance(a, NumberHint) and isinstance(b, NumberHint):
        return a.teammate == b.teammate and set(a.cards) == set(b.cards) and a.number == b.number
    if isinstance(a, ColorHint) and isinstance(b, ColorHint):
        return a.teammate == b.teammate and set(a.cards) == set(b.cards) and a.color == b.color
    return False


def _kinds_for_encoding(
    cards: List[Card],
    common_view: CommonView,
    settings: GameSettings,
    belief: HandBelief,
) -> List[CardKind]:
    assert len(belief.slots) == len(cards)
    kinds: List[CardKind] = []
    for slot, card in enumerate(cards):
        if Playability.PLAYABLE == belief.slots[slot].playability:
            kinds.append(CardKind.USELESS)
        else:
            kinds.append(common_view.card_kind(card, settings))
    return _collapse_duplicate_playable_cards(cards, kinds)


def _collapse_duplicate_playable_cards(
    cards: List[Card],
    kinds: List[CardKind],
) -> List[CardKind]:
    assert len(cards) == len(kinds)
    seen: set[Card] = set()
    collapsed: List[CardKind] = []
    for slot, kind in enumerate(kinds):
        if CardKind.PLAYABLE != kind:
            collapsed.append(kind)
            continue
        card = cards[slot]
        if card in seen:
            collapsed.append(CardKind.USELESS)
        else:
            seen.add(card)
            collapsed.append(CardKind.PLAYABLE)
    return collapsed


def _pick_play_slot_for_encoding(
    hand: List[Card],
    belief: HandBelief,
    common_view: CommonView,
    settings: GameSettings,
) -> Optional[int]:
    """Newest physically playable unknown (§5.1 / §6.1)."""
    kinds = _kinds_for_encoding(hand, common_view, settings, belief)
    for slot in range(len(hand) - 1, -1, -1):
        if Playability.UNKNOWN != belief.slots[slot].playability:
            continue
        if CardKind.PLAYABLE == kinds[slot]:
            return slot
    return None


def _in_hand_copy_count(hand: Sequence[Card], card: Card) -> int:
    return sum(1 for c in hand if c == card)


def _has_cross_hand_copy(card: Card, other_hands: Sequence[Sequence[Card]]) -> bool:
    """True when ``card`` appears in another visible hand (hinter hint-quality only)."""
    return any(card == c for other in other_hands for c in other)


def _discard_option_score(
    hand: List[Card],
    chop_slot: int,
    common_view: CommonView,
    settings: GameSettings,
) -> Tuple[int, int, int, int]:
    """Lower is better.

    Ranking (single hand + public piles only — channel-safe):
    useless > in-hand duplicate > dispensable > critical > playable.

    Among criticals: any critical already costs a perfect score, so only prefer the **newest**
    slot (sticky chop can pivot to later non-criticals on a later hint).

    Among in-hand duplicates that otherwise tie: prefer the **newest** copy so sticky chop
    advances into later candidates after that discard.
    """
    card = hand[chop_slot]
    kind = common_view.card_kind(card, settings)
    in_hand_dup = 2 <= _in_hand_copy_count(hand, card)
    if CardKind.PLAYABLE == kind:
        tier = 4
    elif CardKind.USELESS == kind:
        tier = 0
    elif in_hand_dup:
        tier = 1
    elif CardKind.CRITICAL == kind:
        tier = 3
    else:
        assert CardKind.DISPENSABLE == kind, f"unexpected card kind for discard rank: {kind}"
        tier = 2
    if CardKind.CRITICAL == kind:
        return (tier, -chop_slot, 0, 0)
    prefer_high_rank = tier in (1, 2)
    rank_key = -card.number.value if prefer_high_rank else card.number.value
    # In-hand dups: newest first; otherwise older slot wins residual ties.
    slot_key = -chop_slot if in_hand_dup else chop_slot
    return (tier, rank_key, 0, slot_key)


def _pick_discard_code(
    hand: List[Card],
    belief: HandBelief,
    common_view: CommonView,
    settings: GameSettings,
) -> Tuple[int, int]:
    """Return ``(code, chop_slot)`` for the best indicable discard option."""
    options = indicable_discard_options(belief)
    assert options, "discard encoding requires at least one indicable option"
    # Prefer non-playable targets when any exist.
    non_playable = [
        opt
        for opt in options
        if CardKind.PLAYABLE != common_view.card_kind(hand[opt[1]], settings)
    ]
    pool = non_playable if non_playable else options
    best = min(
        pool,
        key=lambda opt: _discard_option_score(hand, opt[1], common_view, settings),
    )
    return best[0], best[1]


def _encode_peer_code(
    hand: List[Card],
    belief: HandBelief,
    common_view: CommonView,
    settings: GameSettings,
) -> Tuple[int, Optional[Card]]:
    """Return ``(peer_code, discard_card_or_none)`` for one visible hand."""
    play_slot = _pick_play_slot_for_encoding(hand, belief, common_view, settings)
    if play_slot is not None:
        code = play_type_for_slot(belief, play_slot)
        assert code is not None, f"play slot {play_slot} must map to a play type"
        return code, None
    code, chop_slot = _pick_discard_code(hand, belief, common_view, settings)
    return code, hand[chop_slot]


def _new_slot(hand_size: int) -> int:
    assert 0 < hand_size
    return hand_size - 1


def _hint_slot_shape(card_indices: List[int], hand_size: int) -> HintSlotShape:
    newest = _new_slot(hand_size)
    idx = set(card_indices)
    assert idx, "hint must touch at least one card"
    if newest in idx:
        return HintSlotShape.NEW
    if 0 in idx:
        return HintSlotShape.OLD
    return HintSlotShape.MID


def _infer_encoded_type_from_hint(
    hinter: int,
    target: int,
    move: ColorHint | NumberHint,
    hand_size: int,
) -> int:
    to_next = target == (hinter + 1) % 3
    is_number = isinstance(move, NumberHint)
    shape = _hint_slot_shape(move.cards, hand_size)
    if HintSlotShape.NEW == shape:
        if is_number:
            return 4 if to_next else 5
        return 6 if to_next else 7
    if is_number:
        return 0 if to_next else 1
    return 2 if to_next else 3


def _build_hint_for_encoded(
    hinter: int,
    player_view: PlayerView,
    enc_type: int,
) -> Optional[HintMove]:
    assert 0 <= enc_type <= 7
    to_next = enc_type in (0, 2, 4, 6)
    target = (hinter + 1) % 3 if to_next else (hinter - 1) % 3
    assert target in player_view.teammates, "encoding hint target must be a visible teammate"
    hand = player_view.teammates[target].cards
    assert hand, "encoding hint requires a non-empty target hand"
    if enc_type >= 4:
        is_number = enc_type in (4, 5)
        hint_move = _build_shape_hint(target, hand, HintSlotShape.NEW, is_number)
        assert hint_move is not None, f"build_shape_hint failed for enc_type={enc_type} shape=NEW"
        _assert_encoded_hint_round_trip(hinter, enc_type, hint_move, hand)
        return hint_move
    is_number = enc_type in (0, 1)
    for shape in (HintSlotShape.OLD, HintSlotShape.MID):
        hint_move = _build_shape_hint(target, hand, shape, is_number)
        if hint_move is not None:
            _assert_encoded_hint_round_trip(hinter, enc_type, hint_move, hand)
            return hint_move
    return None


def _build_literal_fallback_hint(hinter: int, player_view: PlayerView) -> Optional[HintMove]:
    candidates: List[HintMove] = []
    for offset in (1, 2):
        target = (hinter + offset) % 3
        if target not in player_view.teammates:
            continue
        hand = player_view.teammates[target].cards
        if not hand:
            continue
        for num in Number:
            indices = sorted(i for i, c in enumerate(hand) if num == c.number)
            if indices:
                candidates.append(NumberHint(target, indices, num))
        for col in Color:
            if Color.MULTI == col:
                continue
            indices = sorted(i for i, c in enumerate(hand) if col == c.color)
            if indices:
                candidates.append(ColorHint(target, indices, col))
    for hint_move in candidates:
        inferred = _infer_encoded_type_from_hint(
            hinter, hint_move.teammate, hint_move, len(player_view.teammates[hint_move.teammate].cards)
        )
        canonical = _build_hint_for_encoded(hinter, player_view, inferred)
        if canonical is not None and _hints_match(canonical, hint_move):
            continue
        return hint_move
    return candidates[0] if candidates else None


def _assert_encoded_hint_round_trip(
    hinter: int,
    enc_type: int,
    hint_move: HintMove,
    target_hand: List[Card],
) -> None:
    inferred_type = _infer_encoded_type_from_hint(
        hinter,
        hint_move.teammate,
        hint_move,
        len(target_hand),
    )
    assert enc_type == inferred_type, (
        f"hint type round-trip mismatch: sent {enc_type} inferred {inferred_type}"
    )


def _build_shape_hint(
    target: int,
    hand: List[Card],
    shape: HintSlotShape,
    is_number: bool,
) -> Optional[HintMove]:
    hand_size = len(hand)
    newest = _new_slot(hand_size)
    if HintSlotShape.NEW == shape:
        if is_number:
            num = hand[newest].number
            indices = sorted(i for i, c in enumerate(hand) if num == c.number)
            return NumberHint(target, indices, num)
        col = hand[newest].color
        indices = sorted(i for i, c in enumerate(hand) if col == c.color)
        return ColorHint(target, indices, col)
    if HintSlotShape.OLD == shape:
        if is_number:
            num = hand[0].number
            indices = sorted(i for i, c in enumerate(hand) if num == c.number)
            if newest in indices:
                return None
            return NumberHint(target, indices, num)
        col = hand[0].color
        indices = sorted(i for i, c in enumerate(hand) if col == c.color)
        if newest in indices:
            return None
        return ColorHint(target, indices, col)
    middle = [i for i in range(hand_size) if i not in (0, newest)]
    if not middle:
        return None
    if is_number:
        for num in Number:
            all_indices = sorted(i for i, c in enumerate(hand) if num == c.number)
            if all_indices and all(i in middle for i in all_indices):
                return NumberHint(target, all_indices, num)
        return None
    for col in Color:
        if Color.MULTI == col:
            continue
        all_indices = sorted(i for i, c in enumerate(hand) if col == c.color)
        if all_indices and all(i in middle for i in all_indices):
            return ColorHint(target, all_indices, col)
    return None


def _channel_encoded_type(
    hinter: int,
    player_view: PlayerView,
    common_view: CommonView,
    settings: GameSettings,
    hand_belief: List[HandBelief],
) -> Tuple[int, str]:
    peer_codes = _peer_codes_next_then_prev(hinter, player_view, common_view, settings, hand_belief)
    next_seat = (hinter + 1) % 3
    prev_seat = (hinter + 2) % 3
    teammate_types = [peer_codes[next_seat], peer_codes[prev_seat]]
    type_sum = "+".join(str(t) for t in teammate_types)
    return sum(teammate_types) % 8, type_sum


def _third_player_index(a: int, b: int) -> int:
    for p in range(3):
        if p != a and p != b:
            return p
    assert False, "unreachable"


def _chop_class(hand: HandBelief) -> ChopClass:
    """Classify own chop for the hint×chop matrix (§9.1)."""
    ensure_default_chop(hand)
    assert hand.chop is not None, "chop class requires a chop slot"
    if hand.chop_confirmed:
        return ChopClass.CONFIRMED
    assert not hand.chop_hinted, "discard decode always sets chop_confirmed with chop_hinted"
    return ChopClass.DEFAULT


def _hint_quality(
    hinter: int,
    player_view: PlayerView,
    common_view: CommonView,
    settings: GameSettings,
    hand_belief: List[HandBelief],
) -> HintQuality:
    """Classify the would-be convention channel (§9.2). Unbuildable → fine."""
    peer_codes = _peer_codes_next_then_prev(hinter, player_view, common_view, settings, hand_belief)
    enc_type = sum(peer_codes.values()) % 8
    if _build_hint_for_encoded(hinter, player_view, enc_type) is None:
        return HintQuality.FINE
    if _convention_hint_would_identify_new_playable(
        hinter, player_view, common_view, settings, hand_belief
    ):
        return HintQuality.GOOD
    if _convention_hint_would_trash_next_and_play_prev(
        hinter, player_view, common_view, settings, hand_belief
    ):
        return HintQuality.GOOD
    if _convention_hint_would_cause_double_midrank_discard(
        hinter, player_view, common_view, settings, hand_belief
    ):
        return HintQuality.BAD
    return HintQuality.FINE


def _convention_hint_would_cause_double_midrank_discard(
    hinter: int,
    player_view: PlayerView,
    common_view: CommonView,
    settings: GameSettings,
    hand_belief: List[HandBelief],
) -> bool:
    """True when both peers' discard decodes recommend the same 2/3/4 identity (§9.2 ``bad``).

    Ones are excluded (three copies; double-chop is not suit-killing the same way).
    Fives cannot appear twice. Forced-hint (max tokens) still emits the channel for now.
    """
    next_player = (hinter + 1) % 3
    prev_player = (hinter + 2) % 3
    peer_codes = _peer_codes_next_then_prev(hinter, player_view, common_view, settings, hand_belief)
    enc_type = sum(peer_codes.values()) % 8
    next_card = _newly_decoded_discard_card_from_codes(
        next_player,
        peer_codes[prev_player],
        enc_type,
        player_view,
        hand_belief,
    )
    if next_card is None:
        return False
    if next_card.number not in (Number.TWO, Number.THREE, Number.FOUR):
        return False
    prev_card = _newly_decoded_discard_card_from_codes(
        prev_player,
        peer_codes[next_player],
        enc_type,
        player_view,
        hand_belief,
    )
    return prev_card is not None and next_card == prev_card


def _convention_hint_would_cause_double_play(
    hinter: int,
    player_view: PlayerView,
    common_view: CommonView,
    settings: GameSettings,
    hand_belief: List[HandBelief],
) -> bool:
    """True when next and prev would both newly mark the same playable identity."""
    next_player = (hinter + 1) % 3
    prev_player = (hinter + 2) % 3
    peer_codes = _peer_codes_next_then_prev(hinter, player_view, common_view, settings, hand_belief)
    enc_type = sum(peer_codes.values()) % 8
    next_card = _newly_decoded_playable_card_from_codes(
        next_player,
        peer_codes[prev_player],
        enc_type,
        player_view,
        common_view,
        settings,
        hand_belief,
    )
    if next_card is None:
        return False
    prev_card = _newly_decoded_playable_card_from_codes(
        prev_player,
        peer_codes[next_player],
        enc_type,
        player_view,
        common_view,
        settings,
        hand_belief,
    )
    return prev_card is not None and next_card == prev_card


def _convention_hint_would_identify_new_playable(
    hinter: int,
    player_view: PlayerView,
    common_view: CommonView,
    settings: GameSettings,
    hand_belief: List[HandBelief],
) -> bool:
    next_player = (hinter + 1) % 3
    prev_player = (hinter + 2) % 3
    peer_codes = _peer_codes_next_then_prev(hinter, player_view, common_view, settings, hand_belief)
    enc_type = sum(peer_codes.values()) % 8
    if _build_hint_for_encoded(hinter, player_view, enc_type) is None:
        return False
    if any(Playability.PLAYABLE == b.playability for b in hand_belief[next_player].slots):
        return False
    if _convention_hint_would_cause_double_play(
        hinter, player_view, common_view, settings, hand_belief
    ):
        return False
    next_card = _newly_decoded_playable_card_from_codes(
        next_player,
        peer_codes[prev_player],
        enc_type,
        player_view,
        common_view,
        settings,
        hand_belief,
    )
    if next_card is None:
        return False
    if _card_already_identified_playable_on_visible_seats(
        next_card, hinter, player_view, hand_belief
    ):
        return False
    return True


def _convention_hint_would_trash_next_and_play_prev(
    hinter: int,
    player_view: PlayerView,
    common_view: CommonView,
    settings: GameSettings,
    hand_belief: List[HandBelief],
) -> bool:
    """Good: next gets a useless/dup discard recommendation and prev a new playable (§9.2)."""
    next_player = (hinter + 1) % 3
    prev_player = (hinter + 2) % 3
    peer_codes = _peer_codes_next_then_prev(hinter, player_view, common_view, settings, hand_belief)
    enc_type = sum(peer_codes.values()) % 8
    if _build_hint_for_encoded(hinter, player_view, enc_type) is None:
        return False
    if any(Playability.PLAYABLE == b.playability for b in hand_belief[prev_player].slots):
        return False
    next_hand = player_view.teammates[next_player].cards
    prev_hand = player_view.teammates[prev_player].cards
    trash = _newly_decoded_discard_card_from_codes(
        next_player,
        peer_codes[prev_player],
        enc_type,
        player_view,
        hand_belief,
    )
    if trash is None:
        return False
    if not _is_good_discard_trash(trash, next_hand, [prev_hand], common_view, settings):
        return False
    prev_card = _newly_decoded_playable_card_from_codes(
        prev_player,
        peer_codes[next_player],
        enc_type,
        player_view,
        common_view,
        settings,
        hand_belief,
    )
    if prev_card is None:
        return False
    if _card_already_identified_playable_on_visible_seats(
        prev_card, hinter, player_view, hand_belief
    ):
        return False
    return True


def _newly_decoded_discard_card_from_codes(
    decoder: int,
    peer_type: int,
    enc_type: int,
    player_view: PlayerView,
    hand_belief: List[HandBelief],
) -> Optional[Card]:
    """Card implied by a discard decode for ``decoder``, or ``None`` if play / unusable."""
    assert decoder in player_view.teammates
    decoded_type = (enc_type - peer_type) % 8
    n = n_play(hand_belief[decoder])
    if 1 <= decoded_type <= n:
        return None
    for code, slot, _confirmed in indicable_discard_options(hand_belief[decoder]):
        if code == decoded_type:
            return player_view.teammates[decoder].cards[slot]
    return None


def _is_good_discard_trash(
    card: Card,
    hand: Sequence[Card],
    other_hands: Sequence[Sequence[Card]],
    common_view: CommonView,
    settings: GameSettings,
) -> bool:
    """True for useless or duplicate identities (safe convention trash)."""
    kind = common_view.card_kind(card, settings)
    if CardKind.USELESS == kind:
        return True
    if 2 <= _in_hand_copy_count(hand, card):
        return True
    if (
        _has_cross_hand_copy(card, other_hands)
        and CardKind.CRITICAL != kind
        and CardKind.PLAYABLE != kind
    ):
        return True
    return False


def _newly_decoded_playable_card_from_codes(
    decoder: int,
    peer_type: int,
    enc_type: int,
    player_view: PlayerView,
    common_view: CommonView,
    settings: GameSettings,
    hand_belief: List[HandBelief],
) -> Optional[Card]:
    assert decoder in player_view.teammates
    decoded_type = (enc_type - peer_type) % 8
    n = n_play(hand_belief[decoder])
    if not 1 <= decoded_type <= n:
        return None
    play_slot = slot_for_play_type(hand_belief[decoder], decoded_type)
    if play_slot is None:
        return None
    if Playability.PLAYABLE == hand_belief[decoder].slots[play_slot].playability:
        return None
    card = player_view.teammates[decoder].cards[play_slot]
    if CardKind.PLAYABLE != common_view.card_kind(card, settings):
        return None
    return card


def _newly_decoded_playable_card(
    decoder: int,
    peer_index: int,
    enc_type: int,
    player_view: PlayerView,
    common_view: CommonView,
    settings: GameSettings,
    hand_belief: List[HandBelief],
) -> Optional[Card]:
    """Peer code from visible peer hand + shared belief for that seat."""
    assert peer_index in player_view.teammates
    peer_type = _peer_code_for_hand(
        player_view.teammates[peer_index].cards,
        hand_belief[peer_index],
        common_view,
        settings,
    )
    return _newly_decoded_playable_card_from_codes(
        decoder, peer_type, enc_type, player_view, common_view, settings, hand_belief
    )


def _card_already_identified_playable_on_visible_seats(
    card: Card,
    hinter: int,
    player_view: PlayerView,
    hand_belief: List[HandBelief],
) -> bool:
    for seat, hand in player_view.teammates.items():
        assert seat != hinter
        for slot, held in enumerate(hand.cards):
            if card != held:
                continue
            if Playability.PLAYABLE == hand_belief[seat].slots[slot].playability:
                return True
    return False
