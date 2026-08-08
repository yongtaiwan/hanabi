"""
3-player Hanabi convention (dynamic-hand-type encoding, mod ``8``).

Canonical spec: ``THREE_PLAYER_DYNAMIC_HAND_TYPE.md`` at the repo root.
"""

from __future__ import annotations

from enum import Enum
from typing import Dict, List, Optional, Sequence, Set, Tuple

from hanabi.ai.dht_belief import (
    HandEncodingMode,
    LegacyDiscardKind,
    Playability,
    RecState,
    SlotBelief,
    apply_decoded_value,
    chop_chain_newer_from_chop,
    chop_slot,
    clear_legacy_safe,
    discard_anchor_slot,
    discard_type_for_slot,
    discard_types_for_n_play,
    fresh_slot_belief,
    hand_encoding_mode,
    legacy_kind_row,
    legacy_kind_to_card_kind,
    n_play,
    play_reopens_playability,
    play_type_for_slot,
    reopen_unplayable_after_play,
    slot_belief_from_legacy_kind,
    slot_for_play_type,
)
from hanabi.core.card import Card
from hanabi.core.enums import CardKind, Color, Number
from hanabi.core.game import CommonView, GameSettings, Hand, PlayerView
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


class DynamicHandType3P(BasePlayer):
    """
    3-player dynamic-hand-type convention bot.

    Standard 3-player settings from :func:`~hanabi.core.game.create_standard_game_settings`.
    """

    def __init__(self, player_index: int) -> None:
        super().__init__(player_index)
        self._slot_belief: List[List[SlotBelief]] = []
        self._last_decision_summary: Optional[str] = None

    @classmethod
    def supports_game_settings(cls, game_settings: GameSettings) -> bool:
        return 3 == game_settings.num_players

    def set_game_settings(self, game_settings: GameSettings) -> None:
        assert 3 == game_settings.num_players, "DynamicHandType3P requires 3-player games"
        super().set_game_settings(game_settings)
        self._init_belief_at_deal()

    def _init_belief_at_deal(self) -> None:
        """Initialize unknown belief for every seat and slot at the opening deal."""
        hand_size = self.game_settings.max_cards_in_hand
        num_players = self.game_settings.num_players
        self._slot_belief = [[fresh_slot_belief() for _ in range(hand_size)] for _ in range(num_players)]

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
                self._slot_belief,
                self.game_settings,
            )
        elif play_reopens_playability(move.moved_card, self.common_view, self.game_settings):
            reopen_unplayable_after_play(self._slot_belief)
        self._shift_belief_after_removal(player_index, move.card, observer_view)

    def observe_discard_move(
        self, player_index: int, move: FinishedDiscard, observer_view: PlayerView
    ) -> None:
        super().observe_discard_move(player_index, move, observer_view)
        _maybe_invalidate_safe_for_moved_card(
            move.moved_card,
            self.common_view,
            self._slot_belief,
            self.game_settings,
        )
        self._shift_belief_after_removal(player_index, move.card, observer_view)

    def observe_color_hint_move(self, player_index: int, move: ColorHint, observer_view: PlayerView) -> None:
        super().observe_color_hint_move(player_index, move, observer_view)
        _apply_convention_hint_decodes(
            player_index,
            move,
            observer_view,
            self._player_index,
            self.common_view,
            self.game_settings,
            self._slot_belief,
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
            self._slot_belief,
        )

    def play(self, player_view: PlayerView) -> Move:
        assert player_view.own_hand_size > 0
        self._last_decision_summary = None
        move = (
            self._try_play_leftmost_playable(player_view)
            or self._try_hint_if_identifies_new_playable(player_view)
            or self._try_discard_useless(player_view)
            or self._try_discard_recommended(player_view)
            # TODO: Prefer safe-chop discard vs a hint that only unlocks a playable in the
            # *previous* player's hand? Step 2 ignores prev-only unlocks (next player can
            # hint). Safe chop here still beats a general hint; worth A/B testing whether
            # prev-only playable hints should outrank safe chop when tokens are plentiful.
            or self._try_discard_safe_chop(player_view)
            or self._try_hint(player_view)
            or self._try_discard_chop(player_view)
            or self._discard_oldest(player_view)
        )
        assert move is not None, (
            "no legal convention move: play, hint, discard useless/recommended/safe/chop/oldest"
        )
        assert self.is_move_legal(player_view, move)
        assert self._last_decision_summary is not None
        return move_with_why(move, self._last_decision_summary)

    def get_gui_inferred_kind_by_slot(self, target_seat: int) -> Dict[int, CardKind]:
        """Return ``{slot: CardKind}`` for ``target_seat`` where legacy kind is known."""
        if not self._slot_belief or target_seat >= len(self._slot_belief):
            return {}
        row = self._slot_belief[target_seat]
        result: Dict[int, CardKind] = {}
        for slot, belief in enumerate(row):
            kind = legacy_kind_to_card_kind(belief)
            if kind is not None:
                result[slot] = kind
        return result

    def get_gui_unplayable_slots(self, target_seat: int) -> Set[int]:
        """Return slots on ``target_seat`` with convention ``playability == unplayable``."""
        if not self._slot_belief or target_seat >= len(self._slot_belief):
            return set()
        return {
            slot
            for slot, belief in enumerate(self._slot_belief[target_seat])
            if Playability.UNPLAYABLE == belief.playability
        }

    def get_gui_recommended_slot(self, target_seat: int) -> Optional[int]:
        """Return the slot with rec ``recommended`` on ``target_seat``, if any."""
        if not self._slot_belief or target_seat >= len(self._slot_belief):
            return None
        for slot, belief in enumerate(self._slot_belief[target_seat]):
            if RecState.RECOMMENDED == belief.rec_state:
                return slot
        return None

    def get_gui_chop_slot(self, target_seat: int) -> Optional[int]:
        """Expected discard slot on ``target_seat`` (§3.4), or ``None``."""
        if not self._slot_belief or target_seat >= len(self._slot_belief):
            return None
        return chop_slot(self._slot_belief[target_seat])

    def _shift_belief_after_removal(self, player_index: int, removed: int, observer_view: PlayerView) -> None:
        assert self._slot_belief, "belief must be initialized before play/discard observe"
        row = self._slot_belief[player_index]
        shifted = row[:removed] + row[removed + 1 :]
        hand_size_after = self._hand_size_for_player(player_index, observer_view)
        if self.game_settings.max_cards_in_hand == hand_size_after:
            shifted.append(fresh_slot_belief())
        self._slot_belief[player_index] = shifted

    def _try_play_leftmost_playable(self, player_view: PlayerView) -> Optional[Move]:
        # Prefer leftmost over FIFO-by-identification-order: ~same score on 1000-game A/B
        # (FIFO ~+0.01), and humans need not memorize which playable was marked first.
        for slot, belief in enumerate(self._slot_belief[self._player_index]):
            if Playability.PLAYABLE != belief.playability:
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
            self._slot_belief,
        ):
            return None
        return self._try_hint(player_view, why_prefix="[3p type] Hint (identifies playable for next)")

    def _try_discard_useless(self, player_view: PlayerView) -> Optional[Move]:
        for slot, belief in enumerate(self._slot_belief[self._player_index]):
            if LegacyDiscardKind.USELESS != belief.legacy_kind:
                continue
            if not self.is_move_legal(player_view, Discard(slot)):
                continue
            self._last_decision_summary = f"[3p type] Discard slot {slot} (identified useless)"
            return Discard(slot)
        return None

    def _try_discard_recommended(self, player_view: PlayerView) -> Optional[Move]:
        for slot, belief in enumerate(self._slot_belief[self._player_index]):
            if RecState.RECOMMENDED != belief.rec_state:
                continue
            if not self.is_move_legal(player_view, Discard(slot)):
                continue
            self._last_decision_summary = f"[3p type] Discard slot {slot} (recommended)"
            return Discard(slot)
        return None

    def _try_discard_safe_chop(self, player_view: PlayerView) -> Optional[Move]:
        row = self._slot_belief[self._player_index]
        chop = chop_slot(row)
        if chop is None:
            return None
        if LegacyDiscardKind.SAFE != row[chop].legacy_kind:
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
            self._slot_belief,
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
        chop = chop_slot(self._slot_belief[self._player_index])
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
    belief: List[SlotBelief],
    common_view: CommonView,
    settings: GameSettings,
) -> int:
    """Peer code from one visible hand + that seat's shared public belief + piles.

    Uses legacy hand-type encoding or recommendation encoding per that hand's mode (§5).
    """
    assert len(hand) == len(belief), f"hand size {len(hand)} != belief slots {len(belief)}"
    if HandEncodingMode.RECOMMENDATION == hand_encoding_mode(belief):
        return _encode_recommendation_peer_code(hand, belief, common_view, settings)
    return _encode_hand_type(hand, len(hand), common_view, settings, belief)


def _apply_convention_hint_decodes(
    hinter_index: int,
    move: ColorHint | NumberHint,
    observer_view: PlayerView,
    observer_index: int,
    common_view: CommonView,
    settings: GameSettings,
    slot_belief: List[List[SlotBelief]],
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

    # Full-hand touch = abandon convention; belief unchanged for every seat.
    if _hint_touches_entire_hand(move.cards, target_size):
        return

    encoded_type = _infer_encoded_type_from_hint(hinter_index, hint_target, move, target_size)

    if hint_target in observer_view.teammates:
        canonical = _build_hint_for_encoded(hinter_index, observer_view, encoded_type)
        if canonical is None or not _hints_match(canonical, move):
            return
    elif not _hint_target_accepts_as_convention(
        hinter_index, move, target_size, encoded_type
    ):
        return

    peer_code_by_seat: Dict[int, int] = {}
    for seat in (hint_target, other_non_hinter):
        if seat not in observer_view.teammates:
            continue
        peer_code_by_seat[seat] = _peer_code_for_hand(
            observer_view.teammates[seat].cards,
            slot_belief[seat],
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
        apply_decoded_value(slot_belief[decoder], decoded)


def _hints_match(a: HintMove, b: HintMove) -> bool:
    if isinstance(a, NumberHint) and isinstance(b, NumberHint):
        return a.teammate == b.teammate and set(a.cards) == set(b.cards) and a.number == b.number
    if isinstance(a, ColorHint) and isinstance(b, ColorHint):
        return a.teammate == b.teammate and set(a.cards) == set(b.cards) and a.color == b.color
    return False


def _maybe_invalidate_safe_for_moved_card(
    card: Card,
    common_view: CommonView,
    slot_belief: List[List[SlotBelief]],
    settings: GameSettings,
) -> None:
    """Clear legacy safe belief when ``card`` entering discard invalidates mid-rank safes."""
    if _pile_add_invalidates_safe_belief(card, common_view, settings):
        clear_legacy_safe(slot_belief)


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


_REC_SLOT_ORDER = (0, 1, 2, 3, 4)


def _belief_row_from_input(
    belief: Sequence[SlotBelief] | List[Optional[CardKind]],
) -> List[SlotBelief]:
    if not belief:
        return []
    if isinstance(belief[0], SlotBelief):
        return list(belief)
    return [slot_belief_from_legacy_kind(k) for k in belief]


def _encode_hand_type(
    cards: List[Card],
    hand_size: int,
    common_view: CommonView,
    settings: GameSettings,
    belief: Sequence[SlotBelief] | List[Optional[CardKind]],
) -> int:
    """Return legacy hand **type** ``0``–``7`` for one visible hand."""
    row = _belief_row_from_input(belief)
    assert hand_size == len(cards)
    assert len(row) == len(cards)
    if 0 == hand_size:
        return 0
    kinds = _kinds_for_hand_type_encoding(cards, common_view, settings, row)
    playable_slots = [
        i
        for i, k in enumerate(kinds)
        if CardKind.PLAYABLE == k and Playability.UNKNOWN == row[i].playability
    ]
    if playable_slots:
        newest_playable = max(playable_slots)
        code = play_type_for_slot(row, newest_playable)
        assert code is not None, (
            f"newest playable slot {newest_playable} must be among unknown playability"
        )
        return code
    return _hand_type_when_no_playable(kinds, row)


def _kinds_for_hand_type_encoding(
    cards: List[Card],
    common_view: CommonView,
    settings: GameSettings,
    belief_row: Sequence[SlotBelief],
) -> List[CardKind]:
    assert len(belief_row) == len(cards)
    kinds: List[CardKind] = []
    for slot, card in enumerate(cards):
        belief = belief_row[slot]
        if Playability.PLAYABLE == belief.playability:
            kinds.append(CardKind.USELESS)
        elif LegacyDiscardKind.USELESS == belief.legacy_kind:
            kinds.append(CardKind.USELESS)
        else:
            kinds.append(common_view.card_kind(card, settings))
    return _collapse_duplicate_playable_cards_for_hand_type(cards, kinds)


def _collapse_duplicate_playable_cards_for_hand_type(
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


def _hand_type_when_no_playable(
    kinds: List[CardKind],
    belief_row: Sequence[SlotBelief] | List[Optional[CardKind]],
) -> int:
    row = _belief_row_from_input(belief_row)
    assert len(row) == len(kinds)
    assert not any(
        CardKind.PLAYABLE == k and Playability.UNKNOWN == row[i].playability
        for i, k in enumerate(kinds)
    ), f"no-playable hand type requires no unknown playable slots: {kinds!r}"
    anchor = discard_anchor_slot(row)
    if anchor is None:
        return 0
    belief = row[anchor]
    # Anchor never has useless/critical (those are exempt from needs_discard_info).
    if LegacyDiscardKind.SAFE == belief.legacy_kind:
        return 0
    kind = kinds[anchor]
    if CardKind.CRITICAL == kind:
        return 6
    if CardKind.USELESS == kind:
        return 7
    if CardKind.DISPENSABLE == kind:
        return 0
    return 0


def _pick_play_slot_for_encoding(
    hand: List[Card],
    row: Sequence[SlotBelief],
    common_view: CommonView,
    settings: GameSettings,
) -> Optional[int]:
    for slot in _REC_SLOT_ORDER:
        if slot >= len(hand):
            continue
        if Playability.UNKNOWN != row[slot].playability:
            continue
        if Number.FIVE == hand[slot].number and CardKind.PLAYABLE == common_view.card_kind(
            hand[slot], settings
        ):
            return slot
    playable: List[Tuple[int, int]] = []
    for slot in _REC_SLOT_ORDER:
        if slot >= len(hand):
            continue
        if Playability.UNKNOWN != row[slot].playability:
            continue
        if CardKind.PLAYABLE == common_view.card_kind(hand[slot], settings):
            playable.append((slot, hand[slot].number.value))
    if not playable:
        return None
    playable.sort(key=lambda item: (item[1], item[0]))
    return playable[0][0]


def _pick_discard_slot_for_encoding(
    hand: List[Card],
    row: Sequence[SlotBelief],
    common_view: CommonView,
    settings: GameSettings,
) -> int:
    """Pick a discard recommendation among slots encodable on the chop chain (§7.2–§7.3).

    Never prefer a physically ``PLAYABLE`` / ``CRITICAL`` card when a safer chain slot exists.
    Stale ``unplayable`` belief can still sit on a live playable; recommending that discard
    is what burned tempo in the 20260710 experiments.
    """
    chop = chop_slot(row)
    assert chop is not None, "non-empty hand must have a chop for discard encoding"
    types = discard_types_for_n_play(n_play(row))
    assert types, "recommendation mode must leave at least one discard type"
    chain = chop_chain_newer_from_chop(row, chop)[: len(types)]
    assert chain, "chop chain must include chop"

    def physical_kind(slot: int) -> CardKind:
        return common_view.card_kind(hand[slot], settings)

    def is_risky_discard(slot: int) -> bool:
        kind = physical_kind(slot)
        return CardKind.PLAYABLE == kind or CardKind.CRITICAL == kind

    useless: List[int] = []
    for slot in chain:
        if is_risky_discard(slot):
            continue
        if LegacyDiscardKind.USELESS == row[slot].legacy_kind:
            useless.append(slot)
            continue
        if (
            LegacyDiscardKind.UNKNOWN == row[slot].legacy_kind
            and CardKind.USELESS == physical_kind(slot)
        ):
            useless.append(slot)
    if useless:
        # Oldest first so a later hint can point at the next-oldest trash.
        return min(useless)
    for slot in chain:
        if is_risky_discard(slot):
            continue
        if RecState.RECOMMENDED == row[slot].rec_state:
            return slot
    dispensable: List[int] = []
    for slot in chain:
        if is_risky_discard(slot):
            continue
        if LegacyDiscardKind.SAFE == row[slot].legacy_kind:
            dispensable.append(slot)
            continue
        if (
            LegacyDiscardKind.UNKNOWN == row[slot].legacy_kind
            and CardKind.DISPENSABLE == physical_kind(slot)
        ):
            dispensable.append(slot)
    if dispensable:
        # Newest among safe discards (sticky chop can pivot right).
        return max(dispensable)
    for slot in chain:
        if not is_risky_discard(slot):
            return slot
    # Entire encodable chain is playable/critical: prefer critical over playable.
    for slot in chain:
        if CardKind.CRITICAL == physical_kind(slot):
            return slot
    return chop


def _encode_recommendation_peer_code(
    hand: List[Card],
    row: Sequence[SlotBelief],
    common_view: CommonView,
    settings: GameSettings,
) -> int:
    play_slot = _pick_play_slot_for_encoding(hand, row, common_view, settings)
    if play_slot is not None:
        code = play_type_for_slot(row, play_slot)
        assert code is not None, f"play slot {play_slot} must map to a recommendation type"
        return code
    discard_slot = _pick_discard_slot_for_encoding(hand, row, common_view, settings)
    code = discard_type_for_slot(row, discard_slot)
    assert code is not None, f"discard slot {discard_slot} must map to a recommendation type"
    return code


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
        # Full-hand NEW (e.g. five 1s) is the abandon-convention signal, not a channel.
        if _hint_touches_entire_hand(hint_move.cards, len(hand)):
            return None
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


def _hint_touches_entire_hand(card_indices: List[int], hand_size: int) -> bool:
    """True when every slot is touched — abandon-convention signal, never a mod-8 channel."""
    return 0 < hand_size and len(set(card_indices)) == hand_size


def _synthetic_view_for_hint_target_canonical(
    hinter: int,
    move: ColorHint | NumberHint,
    hand_size: int,
) -> PlayerView:
    """Rebuild OLD/NEW attribute layout from the touch set for hint-target §8.4 checks."""
    target = move.teammate
    touched = set(move.cards)
    if isinstance(move, NumberHint):
        fillers = [n for n in Number if n != move.number]
        fake: List[Card] = []
        fi = 0
        for i in range(hand_size):
            if i in touched:
                fake.append(Card(Color.RED, move.number))
            else:
                fake.append(Card(Color.RED, fillers[fi % len(fillers)]))
                fi += 1
    else:
        assert isinstance(move, ColorHint)
        fillers = [c for c in Color if c != move.color and Color.MULTI != c]
        fake = []
        fi = 0
        for i in range(hand_size):
            if i in touched:
                fake.append(Card(move.color, Number.ONE))
            else:
                fake.append(Card(fillers[fi % len(fillers)], Number.ONE))
                fi += 1
    return PlayerView(teammates={target: Hand(fake)}, own_hand_size=hand_size)


def _hint_target_accepts_as_convention(
    hinter_index: int,
    move: ColorHint | NumberHint,
    target_size: int,
    encoded_type: int,
) -> bool:
    """Whether the hint target should treat this hint as convention (§8.4).

    Full-hand touches are never convention. OLD/NEW: recreate the search from the touch
    set. MID: bots never emit MID-shaped literal fallbacks, so MID is convention for
    discard/play encodings (types ``0``–``3``).
    """
    if _hint_touches_entire_hand(move.cards, target_size):
        return False
    shape = _hint_slot_shape(move.cards, target_size)
    if HintSlotShape.MID == shape:
        return encoded_type <= 3
    synthetic = _synthetic_view_for_hint_target_canonical(hinter_index, move, target_size)
    canonical = _build_hint_for_encoded(hinter_index, synthetic, encoded_type)
    return canonical is not None and _hints_match(canonical, move)


def _would_be_read_as_convention(
    hinter: int,
    player_view: PlayerView,
    hint_move: HintMove,
) -> bool:
    """True when every observer who sees the target would apply a mod-8 decode."""
    hand_size = len(player_view.teammates[hint_move.teammate].cards)
    if _hint_touches_entire_hand(hint_move.cards, hand_size):
        return False
    inferred = _infer_encoded_type_from_hint(hinter, hint_move.teammate, hint_move, hand_size)
    canonical = _build_hint_for_encoded(hinter, player_view, inferred)
    return canonical is not None and _hints_match(canonical, hint_move)


def _literal_fallback_sort_key(
    hinter: int,
    player_view: PlayerView,
    hint_move: HintMove,
) -> Tuple[int, int]:
    """Lower is better: full-hand ones, then any full-hand, then other true literals."""
    hand_size = len(player_view.teammates[hint_move.teammate].cards)
    full = _hint_touches_entire_hand(hint_move.cards, hand_size)
    if full and isinstance(hint_move, NumberHint) and Number.ONE == hint_move.number:
        primary = 0
    elif full:
        primary = 1
    else:
        primary = 2
    return (primary, 0)


def _build_literal_fallback_hint(hinter: int, player_view: PlayerView) -> Optional[HintMove]:
    """Legal non-convention hint; never MID-shaped (hint target treats MID as convention)."""
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
    non_mid: List[HintMove] = []
    true_literals: List[HintMove] = []
    for hint_move in candidates:
        hand_size = len(player_view.teammates[hint_move.teammate].cards)
        if HintSlotShape.MID == _hint_slot_shape(hint_move.cards, hand_size):
            continue
        non_mid.append(hint_move)
        if _would_be_read_as_convention(hinter, player_view, hint_move):
            continue
        true_literals.append(hint_move)
    if not true_literals:
        return non_mid[0] if non_mid else None
    true_literals.sort(key=lambda h: _literal_fallback_sort_key(hinter, player_view, h))
    return true_literals[0]


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
    matrix: List[List[Optional[CardKind]]],
    player_index: int,
    hand_type: int,
) -> None:
    """Test helper: decode into a legacy ``CardKind`` matrix."""
    row = [slot_belief_from_legacy_kind(k) for k in matrix[player_index]]
    apply_decoded_value(row, hand_type)
    matrix[player_index] = legacy_kind_row(row)


def _chop_slot_from_belief(belief: List[Optional[CardKind]]) -> Optional[int]:
    """Discard anchor from a legacy ``CardKind`` row (tests and encoding)."""
    row = _belief_row_from_input(belief)
    return discard_anchor_slot(row)


def _channel_encoded_type(
    hinter: int,
    player_view: PlayerView,
    common_view: CommonView,
    settings: GameSettings,
    slot_belief: List[List[SlotBelief]],
) -> Tuple[int, str]:
    teammate_types: List[int] = []
    for teammate in ((hinter + 1) % 3, (hinter + 2) % 3):
        assert teammate in player_view.teammates, (
            f"hinter P{hinter + 1} must see both teammates to encode convention channel"
        )
        hand = player_view.teammates[teammate].cards
        teammate_types.append(
            _peer_code_for_hand(hand, slot_belief[teammate], common_view, settings)
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
    slot_belief: List[List[SlotBelief]],
) -> bool:
    """True when the convention hint is step-2-urgent for the **next** player.

    Peer codes use each teammate's shared public belief row plus that hand's cards.
    """
    next_player = (hinter + 1) % 3
    prev_player = (hinter + 2) % 3
    if any(Playability.PLAYABLE == b.playability for b in slot_belief[next_player]):
        return False
    enc_type, _type_sum = _channel_encoded_type(
        hinter, player_view, common_view, settings, slot_belief
    )
    if _build_hint_for_encoded(hinter, player_view, enc_type) is None:
        return False
    next_card = _newly_decoded_playable_card(
        next_player,
        prev_player,
        enc_type,
        player_view,
        common_view,
        settings,
        slot_belief,
    )
    if next_card is None:
        return False
    if _card_already_identified_playable_on_visible_seats(
        next_card, hinter, player_view, slot_belief
    ):
        return False
    prev_card = _newly_decoded_playable_card(
        prev_player,
        next_player,
        enc_type,
        player_view,
        common_view,
        settings,
        slot_belief,
    )
    if prev_card is not None and next_card == prev_card:
        return False
    return True


def _newly_decoded_playable_card(
    decoder: int,
    peer_index: int,
    enc_type: int,
    player_view: PlayerView,
    common_view: CommonView,
    settings: GameSettings,
    slot_belief: List[List[SlotBelief]],
) -> Optional[Card]:
    """Card that ``decoder`` would newly mark playable from ``enc_type``, or ``None``."""
    assert peer_index in player_view.teammates
    assert decoder in player_view.teammates
    peer_type = _peer_code_for_hand(
        player_view.teammates[peer_index].cards,
        slot_belief[peer_index],
        common_view,
        settings,
    )
    decoded_type = (enc_type - peer_type) % 8
    row = slot_belief[decoder]
    if not 1 <= decoded_type <= 5:
        return None
    play_slot = slot_for_play_type(row, decoded_type)
    if play_slot is None:
        return None
    if Playability.PLAYABLE == row[play_slot].playability:
        return None
    card = player_view.teammates[decoder].cards[play_slot]
    if CardKind.PLAYABLE != common_view.card_kind(card, settings):
        return None
    return card


def _card_already_identified_playable_on_visible_seats(
    card: Card,
    hinter: int,
    player_view: PlayerView,
    slot_belief: List[List[SlotBelief]],
) -> bool:
    """True when a visible teammate already has ``card`` convention-marked playable."""
    for seat, hand in player_view.teammates.items():
        assert seat != hinter
        for slot, held in enumerate(hand.cards):
            if card != held:
                continue
            if Playability.PLAYABLE == slot_belief[seat][slot].playability:
                return True
    return False


def assert_independent_own_decode_matches(
    players: Sequence[DynamicHandType3P],
    hinter_index: int,
    move: ColorHint | NumberHint,
    views: Sequence[PlayerView],
    own_rows_before: Sequence[Sequence[SlotBelief]],
) -> None:
    """After observe, each decoder's own row must equal decode(pre-hint own row).

    ``own_rows_before[seat]`` is a deep copy of that seat's own belief before observe.
    """
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
            is_convention = canonical is not None and _hints_match(canonical, move)
        else:
            is_convention = _hint_target_accepts_as_convention(
                hinter_index, move, target_size, enc
            )
        if not is_convention:
            assert list(players[seat]._slot_belief[seat]) == list(own_rows_before[seat]), (
                f"P{seat + 1} own belief changed on literal fallback hint"
            )
            continue
        peer_code = _peer_code_for_hand(
            view.teammates[peer].cards,
            list(own_rows_before[peer]),
            players[seat].common_view,
            players[seat].game_settings,
        )
        # Hinter's view of the same peer hand must agree (public to both).
        assert peer in views[hinter_index].teammates
        assert peer_code == _peer_code_for_hand(
            views[hinter_index].teammates[peer].cards,
            list(own_rows_before[peer]),
            players[hinter_index].common_view,
            players[hinter_index].game_settings,
        ), f"peer code for P{peer + 1} not publicly determined"
        expected_row = [
            SlotBelief(b.playability, b.legacy_kind, b.rec_state) for b in own_rows_before[seat]
        ]
        apply_decoded_value(expected_row, (enc - peer_code) % 8)
        actual = players[seat]._slot_belief[seat]
        assert actual == expected_row, (
            f"P{seat + 1} own belief after hint != independent decode: "
            f"actual={actual!r} expected={expected_row!r}"
        )


def assert_public_non_hinter_rows_agree(
    players: Sequence[DynamicHandType3P],
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
        ref = players[0]._slot_belief[seat]
        for player in players[1:]:
            assert player._slot_belief[seat] == ref, (
                f"P{player._player_index + 1} belief for P{seat + 1} != P1 after "
                f"hint from P{hinter_index + 1}"
            )
