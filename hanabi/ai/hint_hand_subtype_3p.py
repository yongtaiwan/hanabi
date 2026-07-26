"""
3-player Hanabi convention (hint-hand-type encoding, mod ``8``).

Canonical spec (encoding, decode, belief, play strategy):
https://docs.google.com/document/d/1KD2ZClK_OgtcjMIiKBMBUuzlSdV7nrGVEp5-n9IoZus/edit

The upgraded legacy↔recommendation convention lives in
:class:`~hanabi.ai.dynamic_hand_type_3p.DynamicHandType3P`
(``THREE_PLAYER_DYNAMIC_HAND_TYPE.md``).
"""

from __future__ import annotations

from enum import Enum
from typing import Dict, List, Optional, Sequence, Tuple

from hanabi.core.card import Card
from hanabi.core.enums import CardKind, Color, Number
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
from hanabi.core.player import BasePlayer


class HintSlotShape(Enum):
    """Which index band a hint touches (see module docstring)."""

    OLD = "old"
    MID = "mid"
    NEW = "new"


class HintHandSubtype3P(BasePlayer):
    """
    3-player hint-hand-type convention bot.

    Standard 3-player settings from :func:`~hanabi.core.game.create_standard_game_settings`.
    """

    def __init__(self, player_index: int) -> None:
        super().__init__(player_index)
        self._inferred_card_kind: List[List[Optional[CardKind]]] = []
        self._last_decision_summary: Optional[str] = None

    @classmethod
    def supports_game_settings(cls, game_settings: GameSettings) -> bool:
        return 3 == game_settings.num_players

    def set_game_settings(self, game_settings: GameSettings) -> None:
        assert 3 == game_settings.num_players, "HintHandSubtype3P requires 3-player games"
        super().set_game_settings(game_settings)
        self._init_belief_at_deal()

    def _init_belief_at_deal(self) -> None:
        """Initialize unknown belief for every seat and slot at the opening deal."""
        hand_size = self.game_settings.max_cards_in_hand
        num_players = self.game_settings.num_players
        self._inferred_card_kind = [[None for _ in range(hand_size)] for _ in range(num_players)]

    def _hand_size_for_player(self, player_index: int, observer_view: PlayerView) -> int:
        if player_index == self._player_index:
            return observer_view.own_hand_size
        assert player_index in observer_view.teammates
        return len(observer_view.teammates[player_index].cards)

    def observe_play_move(
        self, player_index: int, move: FinishedPlay, observer_view: PlayerView
    ) -> None:
        super().observe_play_move(player_index, move, observer_view)
        if not move.successful:
            _maybe_invalidate_safe_for_moved_card(
                move.moved_card,
                self.common_view,
                self.game_settings,
                self._inferred_card_kind,
            )
        self._shift_kinds_after_removal(player_index, move.card, observer_view)

    def observe_discard_move(
        self, player_index: int, move: FinishedDiscard, observer_view: PlayerView
    ) -> None:
        super().observe_discard_move(player_index, move, observer_view)
        _maybe_invalidate_safe_for_moved_card(
            move.moved_card,
            self.common_view,
            self.game_settings,
            self._inferred_card_kind,
        )
        self._shift_kinds_after_removal(player_index, move.card, observer_view)

    def observe_color_hint_move(self, player_index: int, move: ColorHint, observer_view: PlayerView) -> None:
        super().observe_color_hint_move(player_index, move, observer_view)
        _apply_convention_hint_decodes(
            player_index,
            move,
            observer_view,
            self._player_index,
            self.common_view,
            self.game_settings,
            self._inferred_card_kind,
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
            self._inferred_card_kind,
        )

    def play(self, player_view: PlayerView) -> Move:
        assert player_view.own_hand_size > 0
        self._last_decision_summary = None
        move = (
            self._try_play_oldest_playable(player_view)
            or self._try_hint_if_identifies_new_playable(player_view)
            or self._try_discard_useless(player_view)
            or self._try_discard_safe_chop(player_view)
            or self._try_hint(player_view)
            or self._try_discard_chop(player_view)
            or self._discard_oldest(player_view)
        )
        assert move is not None, (
            "no legal convention move: play, hint, discard useless/safe/chop/oldest"
        )
        assert self.is_move_legal(player_view, move)
        assert self._last_decision_summary is not None
        return move_with_why(move, self._last_decision_summary)

    def _shift_kinds_after_removal(self, player_index: int, removed: int, observer_view: PlayerView) -> None:
        assert self._inferred_card_kind, "belief must be initialized before play/discard observe"
        row = self._inferred_card_kind[player_index]
        shifted = row[:removed] + row[removed + 1 :]
        hand_size_after = self._hand_size_for_player(player_index, observer_view)
        if self.game_settings.max_cards_in_hand == hand_size_after:
            shifted.append(None)
        self._inferred_card_kind[player_index] = shifted

    def _try_play_oldest_playable(self, player_view: PlayerView) -> Optional[Move]:
        for slot, kind in enumerate(self._inferred_card_kind[self._player_index]):
            if CardKind.PLAYABLE != kind:
                continue
            assert self.is_move_legal(player_view, Play(slot))
            self._last_decision_summary = f"[3p type] Play slot {slot} (identified playable)"
            return Play(slot)
        return None

    def _try_hint_if_identifies_new_playable(self, player_view: PlayerView) -> Optional[Move]:
        if 0 == self.common_view.hint_tokens:
            return None
        if not _convention_hint_would_identify_new_playable(
            self._player_index,
            player_view,
            self.common_view,
            self.game_settings,
            self._inferred_card_kind,
        ):
            return None
        return self._try_hint(player_view, why_prefix="[3p type] Hint (identifies playable)")

    def _try_discard_useless(self, player_view: PlayerView) -> Optional[Move]:
        for slot, kind in enumerate(self._inferred_card_kind[self._player_index]):
            if CardKind.USELESS != kind:
                continue
            if not self.is_move_legal(player_view, Discard(slot)):
                continue
            self._last_decision_summary = f"[3p type] Discard slot {slot} (identified useless)"
            return Discard(slot)
        return None

    def _try_discard_safe_chop(self, player_view: PlayerView) -> Optional[Move]:
        chop = _chop_slot_from_belief(self._inferred_card_kind[self._player_index])
        if chop is None:
            return None
        if CardKind.DISPENSABLE != self._inferred_card_kind[self._player_index][chop]:
            return None
        if not self.is_move_legal(player_view, Discard(chop)):
            return None
        self._last_decision_summary = f"[3p type] Discard chop slot {chop} (identified safe)"
        return Discard(chop)

    def _try_hint(
        self, player_view: PlayerView, *, why_prefix: str = "[3p type] Convention hint"
    ) -> Optional[Move]:
        if 0 == self.common_view.hint_tokens:
            return None
        enc_type, type_sum = _channel_encoded_type(
            self._player_index,
            player_view,
            self.common_view,
            self.game_settings,
            self._inferred_card_kind,
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

    def _try_discard_chop(self, player_view: PlayerView) -> Optional[Move]:
        chop = _chop_slot_from_belief(self._inferred_card_kind[self._player_index])
        if chop is None:
            return None
        if not self.is_move_legal(player_view, Discard(chop)):
            return None
        self._last_decision_summary = f"[3p type] Discard chop slot {chop} (fallback)"
        return Discard(chop)

    def _discard_oldest(self, player_view: PlayerView) -> Optional[Move]:
        if not self.is_move_legal(player_view, Discard(0)):
            return None
        self._last_decision_summary = "[3p type] Discard slot 0 (oldest; no chop)"
        return Discard(0)


_MIDDLE_DISCARD_RANKS = frozenset({Number.TWO, Number.THREE, Number.FOUR})


def _peer_code_for_hand(
    hand: List[Card],
    belief: List[Optional[CardKind]],
    common_view: CommonView,
    settings: GameSettings,
) -> int:
    """Peer code from one visible hand + that seat's shared public belief + piles."""
    assert len(hand) == len(belief), f"hand size {len(hand)} != belief slots {len(belief)}"
    return _encode_hand_type(hand, len(hand), common_view, settings, belief)


def _apply_convention_hint_decodes(
    hinter_index: int,
    move: ColorHint | NumberHint,
    observer_view: PlayerView,
    observer_index: int,
    common_view: CommonView,
    settings: GameSettings,
    inferred_card_kind: List[List[Optional[CardKind]]],
) -> None:
    """Update belief from the public channel using shared belief + visible cards.

    Every observer applies the public decode to **both** non-hinter rows and never to the
    hinter's row. Peer codes are snapshotted before either decode mutates belief.
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

    peer_code_by_seat: Dict[int, int] = {}
    for seat in (hint_target, other_non_hinter):
        if seat not in observer_view.teammates:
            continue
        peer_code_by_seat[seat] = _peer_code_for_hand(
            observer_view.teammates[seat].cards,
            inferred_card_kind[seat],
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
        _apply_decoded_hand_type(inferred_card_kind, decoder, decoded)


def assert_independent_own_decode_matches(
    players: Sequence[HintHandSubtype3P],
    hinter_index: int,
    move: ColorHint | NumberHint,
    views: Sequence[PlayerView],
    own_rows_before: Sequence[Sequence[Optional[CardKind]]],
) -> None:
    """After observe, each decoder's own row must equal decode(pre-hint own row)."""
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
                assert list(players[seat]._inferred_card_kind[seat]) == list(own_rows_before[seat]), (
                    f"P{seat + 1} own belief changed on literal fallback hint"
                )
                continue
        peer_code = _peer_code_for_hand(
            view.teammates[peer].cards,
            list(own_rows_before[peer]),
            players[seat].common_view,
            players[seat].game_settings,
        )
        assert peer_code == _peer_code_for_hand(
            views[hinter_index].teammates[peer].cards,
            list(own_rows_before[peer]),
            players[hinter_index].common_view,
            players[hinter_index].game_settings,
        ), f"peer code for P{peer + 1} not publicly determined"
        expected = [row for row in own_rows_before[seat]]
        matrix = [list(expected)]
        _apply_decoded_hand_type(matrix, 0, (enc - peer_code) % 8)
        assert players[seat]._inferred_card_kind[seat] == matrix[0], (
            f"P{seat + 1} own belief after hint != independent decode"
        )


def assert_public_non_hinter_rows_agree(
    players: Sequence[HintHandSubtype3P],
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
        ref = players[0]._inferred_card_kind[seat]
        for player in players[1:]:
            assert player._inferred_card_kind[seat] == ref, (
                f"P{player._player_index + 1} belief for P{seat + 1} != P1 after "
                f"hint from P{hinter_index + 1}"
            )


def _maybe_invalidate_safe_for_moved_card(
    card: Card,
    common_view: CommonView,
    settings: GameSettings,
    inferred_card_kind: List[List[Optional[CardKind]]],
) -> None:
    """Apply safe→unknown when a discard or misplay adds ``card`` to the public discard pile."""
    if _pile_add_invalidates_safe_belief(card, common_view, settings):
        _reset_all_safe_to_unknown(inferred_card_kind)


def _pile_add_invalidates_safe_belief(
    card: Card,
    common_view: CommonView,
    settings: GameSettings,
) -> bool:
    """True when a middle-rank pile add leaves the remaining copy playable or critical."""
    if card.number not in _MIDDLE_DISCARD_RANKS:
        return False
    kind = common_view.card_kind(card, settings)
    return CardKind.PLAYABLE == kind or CardKind.CRITICAL == kind


def _reset_all_safe_to_unknown(inferred_card_kind: List[List[Optional[CardKind]]]) -> None:
    for row in inferred_card_kind:
        for slot, kind in enumerate(row):
            if CardKind.DISPENSABLE == kind:
                row[slot] = None


def _encode_hand_type(
    cards: List[Card],
    hand_size: int,
    common_view: CommonView,
    settings: GameSettings,
    identified_kinds: List[Optional[CardKind]],
) -> int:
    """Return hand **type** ``0``–``7`` for one visible hand."""
    assert hand_size == len(cards)
    assert len(identified_kinds) == len(cards)
    if 0 == hand_size:
        return 0
    kinds = _kinds_for_hand_type_encoding(cards, common_view, settings, identified_kinds)
    playable_slots = [i for i, k in enumerate(kinds) if CardKind.PLAYABLE == k]
    if playable_slots:
        newest_playable = max(playable_slots)
        n_from_new = hand_size - newest_playable
        assert 1 <= n_from_new <= 5, f"playable position from new out of range: {n_from_new}"
        return n_from_new
    return _hand_type_when_no_playable(kinds, identified_kinds)


def _kinds_for_hand_type_encoding(
    cards: List[Card],
    common_view: CommonView,
    settings: GameSettings,
    identified_kinds: List[Optional[CardKind]],
) -> List[CardKind]:
    """
    Effective per-slot kinds for hand-type encoding.

    Slots already identified **playable** in convention belief are omitted from playable
    ordering (treated as useless for type ``1``–``5``). Other identified kinds are kept.
    Duplicate physical cards both playable count only the leftmost as playable.
    """
    assert len(identified_kinds) == len(cards)
    kinds: List[CardKind] = []
    for slot, card in enumerate(cards):
        physical = common_view.card_kind(card, settings)
        identified = identified_kinds[slot]
        if CardKind.PLAYABLE == identified:
            kinds.append(CardKind.USELESS)
        elif identified is not None:
            kinds.append(identified)
        else:
            kinds.append(physical)
    return _collapse_duplicate_playable_cards_for_hand_type(cards, kinds)


def _collapse_duplicate_playable_cards_for_hand_type(
    cards: List[Card],
    kinds: List[CardKind],
) -> List[CardKind]:
    """Only the leftmost slot per card identity counts as ``PLAYABLE`` for hand-type encoding."""
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


def _hand_type_when_no_playable(
    kinds: List[CardKind],
    identified_kinds: List[Optional[CardKind]],
) -> int:
    """
    Hand type ``0`` / ``6`` / ``7`` when no playable card remains.

    Types ``0`` / ``6`` / ``7`` describe **chop** (leftmost unknown/safe), matching decode.
    Type ``0``: chop safe, or no chop. Type ``6``: chop critical. Type ``7``: chop useless.
    """
    assert len(identified_kinds) == len(kinds)
    assert not any(CardKind.PLAYABLE == k for k in kinds), (
        f"no-playable hand type requires no playable slots: {kinds!r}"
    )
    chop = _chop_slot_from_belief(identified_kinds)
    if chop is None:
        return 0
    kind = kinds[chop]
    if CardKind.CRITICAL == kind:
        return 6
    if CardKind.USELESS == kind:
        return 7
    if CardKind.DISPENSABLE == kind:
        return 0
    return 0


def _new_slot(hand_size: int) -> int:
    assert 0 < hand_size
    return hand_size - 1


def _hint_slot_shape(card_indices: List[int], hand_size: int) -> HintSlotShape:
    """Classify touched indices as old / mid / new."""
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
    """Recover encoded hand **type** ``0``–``7`` from hint direction and number/color (not shape)."""
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


def _old_mid_buildable(
    hand: List[Card],
    enc_type: int,
) -> Tuple[bool, bool]:
    """Return ``(old_ok, mid_ok)`` for types ``0``–``3`` on one hand."""
    is_number = enc_type in (0, 1)
    target = 0
    old_ok = _build_shape_hint(target, hand, HintSlotShape.OLD, is_number) is not None
    mid_ok = _build_shape_hint(target, hand, HintSlotShape.MID, is_number) is not None
    if enc_type in (2, 3):
        old_ok = _build_shape_hint(target, hand, HintSlotShape.OLD, False) is not None
        mid_ok = _build_shape_hint(target, hand, HintSlotShape.MID, False) is not None
    return old_ok, mid_ok


def _build_hint_for_encoded(
    hinter: int,
    player_view: PlayerView,
    enc_type: int,
) -> Optional[HintMove]:
    """Build convention hint for encoded type; ``None`` if OLD and MID are both unbuildable (types ``0``–``3``)."""
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
    old_ok, mid_ok = _old_mid_buildable(hand, enc_type)
    assert not old_ok and not mid_ok, (
        f"build_hint_for_encoded enc_type={enc_type}: OLD/MID loop missed buildable shape "
        f"(old_ok={old_ok}, mid_ok={mid_ok})"
    )
    return None


def _hints_match(a: HintMove, b: HintMove) -> bool:
    if isinstance(a, NumberHint) and isinstance(b, NumberHint):
        return a.teammate == b.teammate and set(a.cards) == set(b.cards) and a.number == b.number
    if isinstance(a, ColorHint) and isinstance(b, ColorHint):
        return a.teammate == b.teammate and set(a.cards) == set(b.cards) and a.color == b.color
    return False


def _build_literal_fallback_hint(hinter: int, player_view: PlayerView) -> Optional[HintMove]:
    """Any legal color/number hint that is not a canonical convention encoding."""
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


def _apply_decoded_hand_type(
    inferred_card_kind: List[List[Optional[CardKind]]],
    player_index: int,
    hand_type: int,
) -> None:
    """
    Apply decoded hand **type** to one seat row (types ``0``–``7``; see module docstring gDoc link).

    Conflicting kind transitions are convention bugs; see :func:`_assign_kind_to_matrix`.
    """
    _apply_hand_type_to_row(inferred_card_kind, player_index, hand_type, soft=False)


def _apply_physical_channel_hand_type(
    inferred_card_kind: List[List[Optional[CardKind]]],
    player_index: int,
    hand_type: int,
) -> None:
    """Apply a channel type encoded with physical peer codes; skip illegal transitions.

    Peer encoding ignores stored belief, so a later message may target a slot already
    identified another way — that is not a cheat, just a no-op.
    """
    _apply_hand_type_to_row(inferred_card_kind, player_index, hand_type, soft=True)


def _apply_hand_type_to_row(
    inferred_card_kind: List[List[Optional[CardKind]]],
    player_index: int,
    hand_type: int,
    *,
    soft: bool,
) -> None:
    assert 0 <= hand_type <= 7
    belief = inferred_card_kind[player_index]
    hand_size = len(belief)
    if 1 <= hand_type <= 5:
        newest = _new_slot(hand_size)
        play_slot = newest - (hand_type - 1)
        assert 0 <= play_slot < hand_size, (
            f"type {hand_type} play slot {play_slot} out of range for hand_size {hand_size}"
        )
        if soft and not _transition_allowed(belief[play_slot], CardKind.PLAYABLE):
            return
        _assign_kind_to_matrix(inferred_card_kind, player_index, play_slot, CardKind.PLAYABLE)
        return
    chop = _chop_slot_from_belief(belief)
    if chop is None:
        return
    if 0 == hand_type:
        kind = CardKind.DISPENSABLE
    elif 6 == hand_type:
        kind = CardKind.CRITICAL
    elif 7 == hand_type:
        kind = CardKind.USELESS
    else:
        assert False, f"unexpected hand_type {hand_type}"
    if soft and not _transition_allowed(belief[chop], kind):
        return
    _assign_kind_to_matrix(inferred_card_kind, player_index, chop, kind)


def _assign_kind_to_matrix(
    inferred_card_kind: List[List[Optional[CardKind]]],
    player_index: int,
    slot: int,
    new_kind: CardKind,
) -> None:
    """Write one convention kind into the shared belief matrix; assert valid transitions."""
    current = inferred_card_kind[player_index][slot]
    assert _transition_allowed(current, new_kind), (
        f"invalid kind transition {current!r} -> {new_kind!r} at P{player_index + 1} slot {slot}"
    )
    inferred_card_kind[player_index][slot] = new_kind


def _chop_slot_from_belief(belief: List[Optional[CardKind]]) -> Optional[int]:
    """Leftmost unknown or safe (``DISPENSABLE``) slot; never ``CRITICAL`` / ``PLAYABLE`` / ``USELESS``."""
    for slot, kind in enumerate(belief):
        if kind is None or CardKind.DISPENSABLE == kind:
            return slot
    return None


def _transition_allowed(current: Optional[CardKind], new_kind: CardKind) -> bool:
    if current == new_kind:
        return True
    if CardKind.PLAYABLE == current or CardKind.USELESS == current:
        return False
    if CardKind.CRITICAL == current:
        return CardKind.PLAYABLE == new_kind
    if current is None or CardKind.DISPENSABLE == current:
        return True
    return False


def _channel_encoded_type(
    hinter: int,
    player_view: PlayerView,
    common_view: CommonView,
    settings: GameSettings,
    inferred_card_kind: List[List[Optional[CardKind]]],
) -> Tuple[int, str]:
    """Return ``(enc_type, type_sum)`` — channel type mod ``8`` and ``"t0+t1"`` breakdown."""
    teammate_types: List[int] = []
    for teammate in ((hinter + 1) % 3, (hinter + 2) % 3):
        assert teammate in player_view.teammates, (
            f"hinter P{hinter + 1} must see both teammates to encode convention channel"
        )
        hand = player_view.teammates[teammate].cards
        teammate_types.append(
            _peer_code_for_hand(hand, inferred_card_kind[teammate], common_view, settings)
        )
    type_sum = "+".join(str(t) for t in teammate_types)
    return sum(teammate_types) % 8, type_sum


def _third_player_index(a: int, b: int) -> int:
    for p in range(3):
        if p != a and p != b:
            return p
    assert False, "unreachable"


def _convention_hint_would_identify_new_playable(
    hinter: int,
    player_view: PlayerView,
    common_view: CommonView,
    settings: GameSettings,
    inferred_card_kind: List[List[Optional[CardKind]]],
) -> bool:
    """True when the convention hint would newly mark a physically playable slot for next."""
    next_player = (hinter + 1) % 3
    prev_player = (hinter + 2) % 3
    if any(CardKind.PLAYABLE == k for k in inferred_card_kind[next_player]):
        return False
    enc_type, _type_sum = _channel_encoded_type(
        hinter, player_view, common_view, settings, inferred_card_kind
    )
    hint_move = _build_hint_for_encoded(hinter, player_view, enc_type)
    if hint_move is None:
        return False
    peer_type = _peer_code_for_hand(
        player_view.teammates[prev_player].cards,
        inferred_card_kind[prev_player],
        common_view,
        settings,
    )
    decoded_type = (enc_type - peer_type) % 8
    if not 1 <= decoded_type <= 5:
        return False
    hand_size = len(player_view.teammates[next_player].cards)
    play_slot = _new_slot(hand_size) - (decoded_type - 1)
    if not 0 <= play_slot < hand_size:
        return False
    if CardKind.PLAYABLE == inferred_card_kind[next_player][play_slot]:
        return False
    card = player_view.teammates[next_player].cards[play_slot]
    if CardKind.PLAYABLE != common_view.card_kind(card, settings):
        return False
    # Same identity already marked playable on the other visible seat?
    for slot, held in enumerate(player_view.teammates[prev_player].cards):
        if card == held and CardKind.PLAYABLE == inferred_card_kind[prev_player][slot]:
            return False
    # Both seats would newly mark the same identity?
    prev_peer = _peer_code_for_hand(
        player_view.teammates[next_player].cards,
        inferred_card_kind[next_player],
        common_view,
        settings,
    )
    prev_decoded = (enc_type - prev_peer) % 8
    if 1 <= prev_decoded <= 5:
        prev_size = len(player_view.teammates[prev_player].cards)
        prev_slot = _new_slot(prev_size) - (prev_decoded - 1)
        if 0 <= prev_slot < prev_size:
            if CardKind.PLAYABLE != inferred_card_kind[prev_player][prev_slot]:
                prev_card = player_view.teammates[prev_player].cards[prev_slot]
                if (
                    CardKind.PLAYABLE == common_view.card_kind(prev_card, settings)
                    and card == prev_card
                ):
                    return False
    return True
