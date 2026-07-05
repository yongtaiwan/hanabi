"""
3-player Hanabi convention (gDoc v2026/07/04): hint-hand-type encoding.

**Encode (give hint):** sum both teammates' hand **types** mod ``8``, from visible cards and
:meth:`~hanabi.core.game.CommonView.card_kind`, using convention belief: slots already identified
**playable** are excluded from hand-type ordering (types ``1``–``5``).

**Belief:** ``_inferred_card_kind[player][slot] -> Optional[CardKind]`` (``None`` = unknown). One entry
per live card (row length equals current hand size). Initialized at deal; updated on hint decode and
on play/discard (shift + draw/shrink).

**Hint shape (old / mid / new):** by touched indices — old includes slot ``0`` not ``new``;
mid excludes ``0`` and ``new``; new includes ``new`` (``hand_size - 1``).

**Channel:** sum of both teammate hand types mod ``8`` (order irrelevant). Types ``0``–``3`` use
old or mid shape on the hint **target** (who receives the physical hint); pick any buildable
shape (prefer old when both work). Types ``4``–``7`` use new shape.

**Decode:** hinter does not decode. Each non-hinter recovers own hand **type** via mod
arithmetic and applies type marks: chop safe (type ``0``); playable (types ``1``–``5``);
chop critical (type ``6``); chop useless (type ``7``). Subtypes are not used.

**Belief (safe):** all ``DISPENSABLE`` slots revert to unknown when a rank ``2``/``3``/``4`` card
enters the discard pile (discard or misplay) and post-move ``common_view.card_kind`` for that
``(color, rank)`` is ``PLAYABLE`` or ``CRITICAL``.

**Play (v1):** strategy steps ``4``–``9`` only. Play only belief-identified playables (step ``4``);
never blind-play unmarked cards.
Step ``5`` conventional hint when encode would **newly identify** a playable for the hint
target or the other non-hinter (simulate type decode; skip if that slot is already playable).
Step ``9`` discard chop only (no play fallback at max hint tokens).
"""

from __future__ import annotations

from enum import Enum
from typing import Callable, Dict, List, Optional, Tuple

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


class HintHandSubtype3P(BasePlayer):
    """
    3-player hint-hand-type convention bot.

    Standard 3-player settings from :func:`~hanabi.core.game.create_standard_game_settings`.
    """

    def __init__(self, player_index: int) -> None:
        super().__init__(player_index)
        self._inferred_card_kind: List[List[Optional[CardKind]]] = []
        self._discard_pile_snapshot: Dict[Color, Dict[Number, int]] = {}
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
        self._discard_pile_snapshot = {}

    def _hand_size_for_player(self, player_index: int, observer_view: PlayerView) -> int:
        if player_index == self._player_index:
            return observer_view.own_hand_size
        assert player_index in observer_view.teammates
        return len(observer_view.teammates[player_index].cards)

    def observe_play_move(self, player_index: int, move: Play, observer_view: PlayerView) -> None:
        before_discards = self._discard_pile_snapshot
        super().observe_play_move(player_index, move, observer_view)
        _maybe_invalidate_safe_after_discard_pile_change(
            before_discards,
            self.common_view,
            self.game_settings,
            self._inferred_card_kind,
        )
        self._shift_kinds_after_removal(player_index, move.card, observer_view)
        self._discard_pile_snapshot = _flatten_discard_counts(self.common_view.cards_discarded)

    def observe_discard_move(self, player_index: int, move: Discard, observer_view: PlayerView) -> None:
        before_discards = self._discard_pile_snapshot
        super().observe_discard_move(player_index, move, observer_view)
        _maybe_invalidate_safe_after_discard_pile_change(
            before_discards,
            self.common_view,
            self.game_settings,
            self._inferred_card_kind,
        )
        self._shift_kinds_after_removal(player_index, move.card, observer_view)
        self._discard_pile_snapshot = _flatten_discard_counts(self.common_view.cards_discarded)

    def observe_color_hint_move(self, player_index: int, move: ColorHint, observer_view: PlayerView) -> None:
        super().observe_color_hint_move(player_index, move, observer_view)
        self._observe_convention_hint(player_index, move, observer_view)

    def observe_number_hint_move(self, player_index: int, move: NumberHint, observer_view: PlayerView) -> None:
        super().observe_number_hint_move(player_index, move, observer_view)
        self._observe_convention_hint(player_index, move, observer_view)

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

    def _assign_kind(self, player_index: int, slot: int, new_kind: CardKind) -> None:
        """Apply decode narrowing; assert gDoc transitions (convention-homogeneous games)."""
        current = self._inferred_card_kind[player_index][slot]
        assert _transition_allowed(current, new_kind), (
            f"invalid kind transition {current!r} -> {new_kind!r} at P{player_index + 1} slot {slot}"
        )
        self._inferred_card_kind[player_index][slot] = new_kind

    def _observe_convention_hint(
        self,
        hinter_index: int,
        move: ColorHint | NumberHint,
        observer_view: PlayerView,
    ) -> None:
        if hinter_index == self._player_index:
            return
        hint_target = move.teammate
        other_non_hinter = _third_player_index(hinter_index, hint_target)
        if self._player_index not in (hint_target, other_non_hinter):
            return

        if hint_target in observer_view.teammates:
            target_size = len(observer_view.teammates[hint_target].cards)
            target_cards: Optional[List[Card]] = observer_view.teammates[hint_target].cards
        else:
            target_size = observer_view.own_hand_size
            target_cards = None

        encoded_type = _infer_encoded_type_from_hint(
            hinter_index, hint_target, move, target_size, target_cards
        )

        peer_index = other_non_hinter if self._player_index == hint_target else hint_target
        assert peer_index in observer_view.teammates
        peer_hand = observer_view.teammates[peer_index].cards
        peer_type = _encode_hand_type(
            peer_hand,
            len(peer_hand),
            self.common_view,
            self.game_settings,
            self._inferred_card_kind[peer_index],
        )
        my_type = (encoded_type - peer_type) % 8
        assign = lambda slot, kind: self._assign_kind(self._player_index, slot, kind)
        _apply_decoded_hand_type(self._inferred_card_kind[self._player_index], my_type, assign=assign)

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
            return None
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

    def _discard_oldest(self, player_view: PlayerView) -> Move:
        self._last_decision_summary = "[3p type] Discard slot 0 (oldest; no chop)"
        return Discard(0)


_MIDDLE_DISCARD_RANKS = frozenset({Number.TWO, Number.THREE, Number.FOUR})


def _flatten_discard_counts(cards_discarded: Dict[Color, Suit]) -> Dict[Color, Dict[Number, int]]:
    return {color: suit.cards.copy() for color, suit in cards_discarded.items()}


def _card_from_discard_pile_diff(
    before: Dict[Color, Dict[Number, int]],
    after: Dict[Color, Dict[Number, int]],
) -> Card:
    """Return the single card whose discard-pile count increased by one."""
    found: Optional[Card] = None
    for color in set(before) | set(after):
        before_counts = before.get(color, {})
        after_counts = after.get(color, {})
        for number in set(before_counts) | set(after_counts):
            delta = after_counts.get(number, 0) - before_counts.get(number, 0)
            if 0 == delta:
                continue
            assert 1 == delta and found is None, (
                f"expected exactly one new discard, before={before!r} after={after!r}"
            )
            found = Card(color, number)
    assert found is not None, f"no discard-pile change: before={before!r} after={after!r}"
    return found


def _maybe_invalidate_safe_after_discard_pile_change(
    before_discards: Dict[Color, Dict[Number, int]],
    common_view: CommonView,
    settings: GameSettings,
    inferred_card_kind: List[List[Optional[CardKind]]],
) -> None:
    """Apply safe→unknown when a discard or misplay adds a card to the public discard pile."""
    after_discards = _flatten_discard_counts(common_view.cards_discarded)
    if before_discards == after_discards:
        return
    card = _card_from_discard_pile_diff(before_discards, after_discards)
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
    return kinds


def _hand_type_when_no_playable(
    kinds: List[CardKind],
    identified_kinds: List[Optional[CardKind]],
) -> int:
    """
    Hand type ``0`` / ``6`` / ``7`` when no playable card remains.

    Skip belief-identified playable slots. Scan left to right; first remaining slot:
    safe → ``0``, critical → ``6``, useless → ``7``.
    """
    assert len(identified_kinds) == len(kinds)
    assert not any(CardKind.PLAYABLE == k for k in kinds), (
        f"no-playable hand type requires no playable slots: {kinds!r}"
    )
    for slot, kind in enumerate(kinds):
        if CardKind.PLAYABLE == identified_kinds[slot]:
            continue
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
    hand_cards: Optional[List[Card]],
) -> int:
    """Recover encoded hand **type** ``0``–``7`` from hint direction and number/color (not shape)."""
    to_next = target == (hinter + 1) % 3
    is_number = isinstance(move, NumberHint)
    if hand_cards is not None:
        shape = _hint_slot_shape(move.cards, hand_size)
    else:
        shape = _infer_shape_public(move.cards, hand_size)
    if HintSlotShape.NEW == shape:
        if is_number:
            return 4 if to_next else 5
        return 6 if to_next else 7
    if is_number:
        return 0 if to_next else 1
    return 2 if to_next else 3


def _infer_shape_public(cards: List[int], hand_size: int) -> HintSlotShape:
    newest = _new_slot(hand_size)
    if newest in cards:
        return HintSlotShape.NEW
    if 0 in cards:
        return HintSlotShape.OLD
    return HintSlotShape.MID


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
        target_hand,
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
    belief: List[Optional[CardKind]],
    hand_type: int,
    *,
    assign: Callable[[int, CardKind], None],
) -> None:
    """
    Apply decoded hand **type** (gDoc v2026/07/04, type-only).

    Types ``1``–``5``: mark Nth-from-new playable. Type ``0``: chop safe. Type ``6``: chop
    critical. Type ``7``: chop useless.

    Skips assignments that violate gDoc kind transitions (e.g. playable after useless) when
    type-only hints disagree.
    """

    def apply_if_allowed(slot: int, kind: CardKind) -> None:
        if _transition_allowed(belief[slot], kind):
            assign(slot, kind)

    assert 0 <= hand_type <= 7
    hand_size = len(belief)
    if 1 <= hand_type <= 5:
        newest = _new_slot(hand_size)
        play_slot = newest - (hand_type - 1)
        assert 0 <= play_slot < hand_size, (
            f"type {hand_type} play slot {play_slot} out of range for hand_size {hand_size}"
        )
        apply_if_allowed(play_slot, CardKind.PLAYABLE)
        return
    chop = _chop_slot_from_belief(belief)
    if chop is None:
        return
    if 0 == hand_type:
        apply_if_allowed(chop, CardKind.DISPENSABLE)
        return
    if 6 == hand_type:
        apply_if_allowed(chop, CardKind.CRITICAL)
        return
    if 7 == hand_type:
        apply_if_allowed(chop, CardKind.USELESS)
        return
    assert False, f"unexpected hand_type {hand_type}"


def _chop_slot_from_belief(belief: List[Optional[CardKind]]) -> Optional[int]:
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
            _encode_hand_type(hand, len(hand), common_view, settings, inferred_card_kind[teammate])
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
    """
    True when the hinter's convention hint would newly mark a playable slot for a non-hinter.

    Simulates type-only decode for the hint target and the other non-hinter; the hinter does
    not decode. Requires the identified slot to be physically playable on a visible hand.
    """
    enc_type, _type_sum = _channel_encoded_type(
        hinter, player_view, common_view, settings, inferred_card_kind
    )
    hint_move = _build_hint_for_encoded(hinter, player_view, enc_type)
    if hint_move is None:
        return False
    hint_target = hint_move.teammate
    other_non_hinter = _third_player_index(hinter, hint_target)
    for decoder in (hint_target, other_non_hinter):
        peer_index = other_non_hinter if decoder == hint_target else hint_target
        assert peer_index in player_view.teammates
        peer_hand = player_view.teammates[peer_index].cards
        peer_type = _encode_hand_type(
            peer_hand,
            len(peer_hand),
            common_view,
            settings,
            inferred_card_kind[peer_index],
        )
        decoded_type = (enc_type - peer_type) % 8
        if not 1 <= decoded_type <= 5:
            continue
        hand_size = len(player_view.teammates[decoder].cards)
        play_slot = _new_slot(hand_size) - (decoded_type - 1)
        if not 0 <= play_slot < hand_size:
            continue
        if CardKind.PLAYABLE == inferred_card_kind[decoder][play_slot]:
            continue
        card = player_view.teammates[decoder].cards[play_slot]
        if CardKind.PLAYABLE != common_view.card_kind(card, settings):
            continue
        return True
    return False
