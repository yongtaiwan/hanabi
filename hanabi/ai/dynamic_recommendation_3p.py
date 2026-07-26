"""
3-player Hanabi convention (dynamic recommendation encoding, mod ``8``).

Canonical spec: ``THREE_PLAYER_DYNAMIC_RECOMMENDATION.md`` at the repo root.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional, Sequence, Set, Tuple

from hanabi.ai.dr_belief import (
    InferredHand,
    Playability,
    any_five_possibly_playable,
    apply_decoded_value,
    copy_inferred_hand,
    decoded_value_is_applicable,
    ensure_default_chop,
    finalize_chop_after_shift,
    fresh_inferred_hand,
    fresh_inferred_slot,
    indicable_discard_options,
    is_play_unknown,
    mark_known_fives,
    n_play,
    play_reopens_playability,
    play_type_for_slot,
    reopen_unplayable,
    reset_chop_after_removal,
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
    HasWhy,
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
        self._inferred_hands: List[InferredHand] = []

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
        self._inferred_hands = [fresh_inferred_hand(hand_size) for _ in range(num_players)]

    def _hand_size_for_player(self, player_index: int, observer_view: PlayerView) -> int:
        if player_index == self._player_index:
            return observer_view.own_hand_size
        assert player_index in observer_view.teammates
        return len(observer_view.teammates[player_index].cards)

    def observe_play_move(
        self, player_index: int, move: FinishedPlay, observer_view: PlayerView
    ) -> None:
        super().observe_play_move(player_index, move, observer_view)
        if move.successful and play_reopens_playability(
            move.moved_card, self.common_view, self.game_settings
        ):
            reopen_unplayable(self._inferred_hands)
        self._shift_belief_after_removal(player_index, move.card, observer_view)

    def observe_discard_move(
        self, player_index: int, move: FinishedDiscard, observer_view: PlayerView
    ) -> None:
        super().observe_discard_move(player_index, move, observer_view)
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
            self._inferred_hands,
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
            self._inferred_hands,
        )
        # After convention decode: literal 5 touches are public for every seat.
        _apply_known_five_marks_from_number_hint(move, self._inferred_hands)

    def play(self, player_view: PlayerView) -> Move:
        assert player_view.own_hand_size > 0
        own = self._inferred_hands[self._player_index]
        ensure_default_chop(own)
        # Final round: score attempts beat chop/protect; see ``_play_final_round``.
        if _in_final_round_score_mode(self.common_view):
            move = self._play_final_round(player_view)
            assert move is not None, "final-round policy must return a legal move"
            assert self.is_move_legal(player_view, move)
            assert isinstance(move, HasWhy), "every DR move branch must attach a why via move_with_why"
            return move
        # TODO(hint-bank): At max-1 tokens, playing a 5 refunds to max and discard-locks the
        # next seat — consider deferring that 5 when a safe discard exists and the would-be
        # forced hint is not good (see §9 token-banking notes).
        move = self._try_protect_next_player(player_view)
        if move is None:
            move = self._try_play_leftmost_playable(player_view)
        if move is None:
            can_hint = 0 < self.common_view.hint_tokens
            can_discard = self.common_view.hint_tokens < self.game_settings.max_hint_tokens
            if can_hint and can_discard and own.chop is not None:
                chop_class = _chop_class(own)
                channel = _project_channel(
                    self._player_index,
                    player_view,
                    self.common_view,
                    self.game_settings,
                    self._inferred_hands,
                )
                prefer_hint = _HINT_CHOP_MATRIX[(channel.quality, chop_class)]
                # TODO(hint-bank): When tokens == max-1, discard (even default chop) unless
                # quality is good — avoid filling the bank via discard. Optional later: soft
                # caution at max-2; endgame/short deck may ignore banking.
                if prefer_hint:
                    if HintQuality.GOOD == channel.quality:
                        if channel.identifies_new_playable_for_next:
                            why_prefix = "[3p DR] Hint (identifies playable for next)"
                        elif channel.trash_next_and_play_prev:
                            why_prefix = "[3p DR] Hint (trash for next + playable for prev)"
                        else:
                            why_prefix = "[3p DR] Hint (known-5 assist with playable/trash)"
                    else:
                        why_prefix = f"[3p DR] Hint ({channel.quality.value}/{chop_class.value})"
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
        assert isinstance(move, HasWhy), "every DR move branch must attach a why via move_with_why"
        return move

    def get_gui_inferred_kind_by_slot(self, target_seat: int) -> Dict[int, CardKind]:
        """Return ``{slot: CardKind.PLAYABLE}`` where convention playability is playable."""
        if not self._inferred_hands or target_seat >= len(self._inferred_hands):
            return {}
        result: Dict[int, CardKind] = {}
        for slot, belief in enumerate(self._inferred_hands[target_seat].cards):
            if Playability.PLAYABLE == belief.playability:
                result[slot] = CardKind.PLAYABLE
        return result

    def get_gui_unplayable_slots(self, target_seat: int) -> Set[int]:
        if not self._inferred_hands or target_seat >= len(self._inferred_hands):
            return set()
        return {
            slot
            for slot, belief in enumerate(self._inferred_hands[target_seat].cards)
            if Playability.UNPLAYABLE == belief.playability
        }

    def get_gui_chop_slot(self, target_seat: int) -> Optional[int]:
        if not self._inferred_hands or target_seat >= len(self._inferred_hands):
            return None
        hand = self._inferred_hands[target_seat]
        ensure_default_chop(hand)
        return hand.chop

    def get_gui_chop_confirmed(self, target_seat: int) -> Optional[bool]:
        """``True``/``False`` when chop exists; ``None`` if no chop."""
        if not self._inferred_hands or target_seat >= len(self._inferred_hands):
            return None
        hand = self._inferred_hands[target_seat]
        ensure_default_chop(hand)
        if hand.chop is None:
            return None
        return hand.chop_confirmed

    def _shift_belief_after_removal(self, player_index: int, removed: int, observer_view: PlayerView) -> None:
        assert self._inferred_hands, "belief must be initialized before play/discard observe"
        hand = self._inferred_hands[player_index]
        reset_chop_after_removal(hand, removed)
        shifted = hand.cards[:removed] + hand.cards[removed + 1 :]
        hand_size_after = self._hand_size_for_player(player_index, observer_view)
        if self.game_settings.max_cards_in_hand == hand_size_after:
            shifted.append(fresh_inferred_slot())
        hand.cards = shifted
        finalize_chop_after_shift(hand)

    def _play_final_round(self, player_view: PlayerView) -> Optional[Move]:
        """Deck empty + lives left: maximize score; skip protect and non-good hints.

        Order: known playable / safe known-5 → good hint → newest unknown →
        any remaining hint → chop / oldest discard (last resort only).
        """
        move = self._try_play_leftmost_playable(player_view)
        if move is not None:
            return move
        can_hint = 0 < self.common_view.hint_tokens
        if can_hint:
            channel = _project_channel(
                self._player_index,
                player_view,
                self.common_view,
                self.game_settings,
                self._inferred_hands,
            )
            if HintQuality.GOOD == channel.quality:
                if channel.identifies_new_playable_for_next:
                    why_prefix = "[3p DR] Endgame hint (identifies playable for next)"
                elif channel.trash_next_and_play_prev:
                    why_prefix = "[3p DR] Endgame hint (trash for next + playable for prev)"
                else:
                    why_prefix = "[3p DR] Endgame hint (known-5 assist with playable/trash)"
                return self._give_convention_hint(player_view, why_prefix=why_prefix)
        move = self._try_play_newest_unknown(player_view)
        if move is not None:
            return move
        if can_hint:
            return self._give_convention_hint(
                player_view, why_prefix="[3p DR] Endgame hint (no play candidate)"
            )
        own = self._inferred_hands[self._player_index]
        chop_class = _chop_class(own) if own.chop is not None else None
        if chop_class is not None:
            move = self._discard_chop(player_view, chop_class)
            if move is not None:
                return move
        return self._discard_oldest(player_view)

    def _try_protect_next_player(self, player_view: PlayerView) -> Optional[Move]:
        """Save next from discarding a last-copy critical/playable before own tempo (§9.0)."""
        if not _next_would_discard_danger(
            self._player_index,
            player_view,
            self.common_view,
            self.game_settings,
            self._inferred_hands,
        ):
            return None
        tokens = self.common_view.hint_tokens
        if 0 < tokens:
            if not _channel_protects_next(
                self._player_index,
                player_view,
                self.common_view,
                self.game_settings,
                self._inferred_hands,
            ):
                return None
            return self._give_convention_hint(
                player_view, why_prefix="[3p DR] Protect next (save-hint)"
            )
        # Token gift: only when a single token would stop next burning (§9.0.2).
        if _next_would_discard_danger(
            self._player_index,
            player_view,
            self.common_view,
            self.game_settings,
            self._inferred_hands,
            hint_tokens=1,
        ):
            return None
        own = self._inferred_hands[self._player_index]
        ensure_default_chop(own)
        if own.chop is None or not own.chop_confirmed:
            return None
        if not self.is_move_legal(player_view, Discard(own.chop)):
            return None
        return move_with_why(
            Discard(own.chop),
            f"[3p DR] Protect next (token gift; discard confirmed chop slot {own.chop})",
        )

    def _try_play_known_five(
        self,
        player_view: PlayerView,
        *,
        why: str,
    ) -> Optional[Move]:
        """Play leftmost known-5 when every incomplete color awaits a 5 (guaranteed)."""
        if not _known_five_is_guaranteed_playable(self.common_view, self.game_settings):
            return None
        for slot, belief in enumerate(self._inferred_hands[self._player_index].cards):
            if not belief.known_five:
                continue
            if Playability.PLAYABLE == belief.playability:
                continue  # already handled by convention-playable branch
            assert self.is_move_legal(player_view, Play(slot))
            return move_with_why(Play(slot), f"{why} slot {slot}")
        return None

    def _try_play_leftmost_playable(self, player_view: PlayerView) -> Optional[Move]:
        for slot, belief in enumerate(self._inferred_hands[self._player_index].cards):
            if Playability.PLAYABLE != belief.playability:
                continue
            assert self.is_move_legal(player_view, Play(slot))
            return move_with_why(Play(slot), f"[3p DR] Play slot {slot} (identified playable)")
        return self._try_play_known_five(
            player_view,
            why="[3p DR] Play known 5 (all incomplete colors await a 5)",
        )

    def _try_play_newest_unknown(self, player_view: PlayerView) -> Optional[Move]:
        """Play newest ``UNKNOWN`` slot (convention play order); endgame score attempt."""
        own = self._inferred_hands[self._player_index]
        for slot in range(len(own.cards) - 1, -1, -1):
            if Playability.UNKNOWN != own.cards[slot].playability:
                continue
            if own.cards[slot].known_five:
                continue
            assert self.is_move_legal(player_view, Play(slot))
            return move_with_why(
                Play(slot), f"[3p DR] Endgame play slot {slot} (unknown; score attempt)"
            )
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
            self._inferred_hands,
        )
        hint_move = _build_hint_for_encoded(self._player_index, player_view, enc_type)
        if hint_move is None:
            hint_move = _build_literal_fallback_hint(
                self._player_index, player_view, avoid_enc_type=enc_type
            )
            assert hint_move is not None, (
                f"literal fallback hint must exist when convention type {enc_type} is unbuildable"
            )
            assert self.is_move_legal(player_view, hint_move), (
                f"literal fallback hint is illegal: {hint_move!r}"
            )
            hand_size = len(player_view.teammates[hint_move.teammate].cards)
            if _hint_touches_entire_hand(hint_move.cards, hand_size):
                why = (
                    f"{why_prefix} abandon convention (full-hand; "
                    f"unbuildable type={enc_type}, {type_sum})"
                )
            else:
                why = f"{why_prefix} literal fallback (unbuildable type={enc_type}, {type_sum})"
            return move_with_why(hint_move, why)
        assert self.is_move_legal(player_view, hint_move), (
            f"built convention hint is illegal: {hint_move!r} enc_type={enc_type}"
        )
        return move_with_why(hint_move, f"{why_prefix} type={enc_type} ({type_sum})")

    def _discard_chop(self, player_view: PlayerView, chop_class: Optional[ChopClass]) -> Optional[Move]:
        hand = self._inferred_hands[self._player_index]
        ensure_default_chop(hand)
        if hand.chop is None:
            return None
        if not self.is_move_legal(player_view, Discard(hand.chop)):
            return None
        label = chop_class.value if chop_class is not None else (
            "confirmed" if hand.chop_confirmed else "unconfirmed"
        )
        return move_with_why(
            Discard(hand.chop), f"[3p DR] Discard chop slot {hand.chop} ({label})"
        )

    def _discard_oldest(self, player_view: PlayerView) -> Optional[Move]:
        if not self.is_move_legal(player_view, Discard(0)):
            return None
        return move_with_why(Discard(0), "[3p DR] Discard slot 0 (oldest; no chop)")


def _in_final_round_score_mode(common_view: CommonView) -> bool:
    """True when the deck is empty and at least one life remains (score > chop)."""
    return 0 == common_view.cards_to_draw and 0 < common_view.live_tokens


def _apply_known_five_marks_from_number_hint(
    move: NumberHint,
    inferred_hands: List[InferredHand],
) -> None:
    """Public number-5 touches: every observer marks the same slots on the target seat."""
    if Number.FIVE != move.number:
        return
    mark_known_fives(inferred_hands[move.teammate], move.cards)


def _colors_awaiting_five(common_view: CommonView, settings: GameSettings) -> List[Color]:
    return [
        color
        for color in settings.cards
        if Number.FIVE != common_view.cards_played.get(color)
    ]


def _known_five_is_guaranteed_playable(common_view: CommonView, settings: GameSettings) -> bool:
    """True when every incomplete color is at 4, so any remaining 5 must play."""
    awaiting = _colors_awaiting_five(common_view, settings)
    if not awaiting:
        return False
    return all(Number.FOUR == common_view.cards_played.get(color) for color in awaiting)


def _peer_code_for_hand(
    hand: List[Card],
    inferred_hand: InferredHand,
    common_view: CommonView,
    settings: GameSettings,
) -> int:
    """Peer code from one visible hand + that seat's shared public belief + piles.

    Does not read any other hand. Callers must pass the convention belief row for
    ``hand`` (chop / playability), not a fresh blank row.
    """
    assert len(hand) == len(inferred_hand.cards), (
        f"hand size {len(hand)} != belief slots {len(inferred_hand.cards)}"
    )
    code, _discard_card = _encode_peer_code(hand, inferred_hand, common_view, settings)
    return code


def _peer_codes_next_then_prev(
    hinter: int,
    player_view: PlayerView,
    common_view: CommonView,
    settings: GameSettings,
    inferred_hands: List[InferredHand],
) -> Dict[int, int]:
    """Encode each visible teammate from shared belief + that hand's cards only."""
    next_seat = (hinter + 1) % 3
    prev_seat = (hinter + 2) % 3
    assert next_seat in player_view.teammates and prev_seat in player_view.teammates
    return {
        next_seat: _peer_code_for_hand(
            player_view.teammates[next_seat].cards,
            inferred_hands[next_seat],
            common_view,
            settings,
        ),
        prev_seat: _peer_code_for_hand(
            player_view.teammates[prev_seat].cards,
            inferred_hands[prev_seat],
            common_view,
            settings,
        ),
    }


def _synthetic_view_for_hint_target_canonical(
    hinter: int,
    move: ColorHint | NumberHint,
    hand_size: int,
) -> PlayerView:
    """Rebuild OLD/NEW attribute layout from the touch set for hint-target §8.4 checks.

    Non-touched slots use distinct filler attributes so OLD is not spuriously blocked by
    “same identity on newest” (which the touch set cannot reveal). Not used for MID: that
    preference depends on whether OLD was legal, which fillers cannot decide safely.
    """
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

    Full-hand touches are never convention (abandon signal). OLD/NEW: recreate the search
    from the touch set (safe). MID: bots never emit MID-shaped literal fallbacks, so a MID
    shape with discard/play encoding is convention.
    """
    if _hint_touches_entire_hand(move.cards, target_size):
        return False
    shape = _hint_slot_shape(move.cards, target_size)
    if HintSlotShape.MID == shape:
        return encoded_type <= 3
    synthetic = _synthetic_view_for_hint_target_canonical(hinter_index, move, target_size)
    canonical = _build_hint_for_encoded(hinter_index, synthetic, encoded_type)
    return canonical is not None and _hints_match(canonical, move)


def _apply_convention_hint_decodes(
    hinter_index: int,
    move: ColorHint | NumberHint,
    observer_view: PlayerView,
    observer_index: int,
    common_view: CommonView,
    settings: GameSettings,
    inferred_hands: List[InferredHand],
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

    # Full-hand touch = abandon convention (e.g. five 1s); belief unchanged for every seat.
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

    # Snapshot peer codes for every visible non-hinter before mutating either row.
    peer_code_by_seat: Dict[int, int] = {}
    for seat in (hint_target, other_non_hinter):
        if seat not in observer_view.teammates:
            continue
        peer_code_by_seat[seat] = _peer_code_for_hand(
            observer_view.teammates[seat].cards,
            inferred_hands[seat],
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

    fives_possible = any_five_possibly_playable(common_view, settings)
    for decoder, decoded in decoded_by_seat.items():
        if not decoded_value_is_applicable(inferred_hands[decoder], decoded, fives_possible):
            return

    for decoder, decoded in decoded_by_seat.items():
        apply_decoded_value(inferred_hands[decoder], decoded, fives_possible)


def assert_independent_own_decode_matches(
    players: Sequence[DynamicRecommendation3P],
    hinter_index: int,
    move: ColorHint | NumberHint,
    views: Sequence[PlayerView],
    own_rows_before: Sequence[InferredHand],
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
            is_convention = canonical is not None and _hints_match(canonical, move)
        else:
            is_convention = _hint_target_accepts_as_convention(
                hinter_index, move, target_size, enc
            )
        if not is_convention:
            assert players[seat]._inferred_hands[seat] == own_rows_before[seat], (
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
        decoded = (enc - peer_code) % 8
        fives_possible = any_five_possibly_playable(
            players[seat].common_view, players[seat].game_settings
        )
        if not decoded_value_is_applicable(own_rows_before[seat], decoded, fives_possible):
            assert players[seat]._inferred_hands[seat] == own_rows_before[seat], (
                f"P{seat + 1} own belief changed on inapplicable decode"
            )
            continue
        expected = copy_inferred_hand(own_rows_before[seat])
        apply_decoded_value(expected, decoded, fives_possible)
        assert players[seat]._inferred_hands[seat] == expected, (
            f"P{seat + 1} own belief after hint != independent decode: "
            f"actual={players[seat]._inferred_hands[seat]!r} expected={expected!r}"
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
        ref = players[0]._inferred_hands[seat]
        for player in players[1:]:
            assert player._inferred_hands[seat] == ref, (
                f"P{player._player_index + 1} belief for P{seat + 1} != P1 after "
                f"hint from P{hinter_index + 1}: {player._inferred_hands[seat]!r} vs {ref!r}"
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
    inferred_hand: InferredHand,
) -> List[CardKind]:
    assert len(inferred_hand.cards) == len(cards)
    kinds: List[CardKind] = []
    for slot, card in enumerate(cards):
        if Playability.PLAYABLE == inferred_hand.cards[slot].playability:
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
    inferred_hand: InferredHand,
    common_view: CommonView,
    settings: GameSettings,
) -> Optional[int]:
    """Newest physically playable play-unknown (§5.1 / §6.1).

    Known 5s participate only while some pile is at 4 (a 5 can be playable); otherwise
    they are outside the play-code set and never physically playable anyway.
    """
    fives_possible = any_five_possibly_playable(common_view, settings)
    kinds = _kinds_for_encoding(hand, common_view, settings, inferred_hand)
    for slot in range(len(hand) - 1, -1, -1):
        if not is_play_unknown(inferred_hand.cards[slot], fives_possible):
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
    inferred_hand: InferredHand,
    common_view: CommonView,
    settings: GameSettings,
) -> Tuple[int, int]:
    """Return ``(code, chop_slot)`` for the best indicable discard option."""
    options = indicable_discard_options(inferred_hand, any_five_possibly_playable(common_view, settings))
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
    inferred_hand: InferredHand,
    common_view: CommonView,
    settings: GameSettings,
) -> Tuple[int, Optional[Card]]:
    """Return ``(peer_code, discard_card_or_none)`` for one visible hand."""
    play_slot = _pick_play_slot_for_encoding(hand, inferred_hand, common_view, settings)
    if play_slot is not None:
        code = play_type_for_slot(
            inferred_hand, play_slot, any_five_possibly_playable(common_view, settings)
        )
        assert code is not None, f"play slot {play_slot} must map to a play type"
        return code, None
    code, chop_slot = _pick_discard_code(hand, inferred_hand, common_view, settings)
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


def _hint_touches_entire_hand(card_indices: List[int], hand_size: int) -> bool:
    """True when every slot is touched — abandon-convention signal, never a mod-8 channel."""
    return 0 < hand_size and len(set(card_indices)) == hand_size


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
        # Full-hand NEW (e.g. five 1s) is the abandon-convention signal, not a channel.
        if _hint_touches_entire_hand(hint_move.cards, len(hand)):
            return None
        _assert_encoded_hint_round_trip(hinter, enc_type, hint_move, hand)
        return hint_move
    is_number = enc_type in (0, 1)
    # Types 0–3: prefer OLD, else MID (same as classic 3p / DHT).
    for shape in (HintSlotShape.OLD, HintSlotShape.MID):
        hint_move = _build_shape_hint(target, hand, shape, is_number)
        if hint_move is not None:
            _assert_encoded_hint_round_trip(hinter, enc_type, hint_move, hand)
            return hint_move
    return None


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
    *,
    avoid_enc_type: Optional[int],
) -> Tuple[int, int]:
    """Lower is better: full-hand ones, then any full-hand, then other true literals."""
    hand_size = len(player_view.teammates[hint_move.teammate].cards)
    full = _hint_touches_entire_hand(hint_move.cards, hand_size)
    is_ones = isinstance(hint_move, NumberHint) and Number.ONE == hint_move.number
    if full and is_ones:
        primary = 0
    elif full:
        primary = 1
    else:
        primary = 2
    inferred = _infer_encoded_type_from_hint(hinter, hint_move.teammate, hint_move, hand_size)
    avoid_penalty = 1 if avoid_enc_type is not None and inferred == avoid_enc_type else 0
    return (primary, avoid_penalty)


def _build_literal_fallback_hint(
    hinter: int,
    player_view: PlayerView,
    *,
    avoid_enc_type: Optional[int] = None,
) -> Optional[HintMove]:
    """Legal non-convention hint; never MID-shaped (hint target treats MID as convention).

    Prefers a full-hand number-1 hint when available (clear abandon-convention + tempo).
    Prefer true non-convention hints; only if none exist, fall back to a non-MID candidate
    (may still be read as convention — rare when no full-hand abandon signal is available).
    """
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
    # MID cannot be verified from the touch set alone when OLD was preferred; bots never use
    # MID-shaped literals so the hint target may treat MID as convention (§8.4 / encode).
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
        # Rare: every non-MID hint round-trips as some channel and no full-hand abandon
        # signal exists. Last resort keeps the bot legal at max tokens; receivers may
        # still decode it as convention (same risk as before the full-hand rule).
        return non_mid[0] if non_mid else None
    true_literals.sort(
        key=lambda h: _literal_fallback_sort_key(
            hinter, player_view, h, avoid_enc_type=avoid_enc_type
        )
    )
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


def _channel_encoded_type(
    hinter: int,
    player_view: PlayerView,
    common_view: CommonView,
    settings: GameSettings,
    inferred_hands: List[InferredHand],
) -> Tuple[int, str]:
    peer_codes = _peer_codes_next_then_prev(hinter, player_view, common_view, settings, inferred_hands)
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


def _chop_class(hand: InferredHand) -> ChopClass:
    """Classify own chop for the hint×chop matrix (§9.1)."""
    ensure_default_chop(hand)
    assert hand.chop is not None, "chop class requires a chop slot"
    if hand.chop_confirmed:
        return ChopClass.CONFIRMED
    return ChopClass.DEFAULT


def _seat_has_convention_playable(hand: InferredHand) -> bool:
    return any(Playability.PLAYABLE == b.playability for b in hand.cards)


def _prev_has_unidentified_physical_playable(
    prev_seat: int,
    player_view: PlayerView,
    common_view: CommonView,
    settings: GameSettings,
    inferred_hands: List[InferredHand],
) -> bool:
    """True when prev has an ``unknown`` slot that is physically playable now."""
    assert prev_seat in player_view.teammates
    prev_cards = player_view.teammates[prev_seat].cards
    prev_belief = inferred_hands[prev_seat]
    assert len(prev_cards) == len(prev_belief.cards)
    for slot, belief in enumerate(prev_belief.cards):
        if Playability.UNKNOWN != belief.playability:
            continue
        if CardKind.PLAYABLE == common_view.card_kind(prev_cards[slot], settings):
            return True
    return False


def _next_likely_good(
    hinter: int,
    player_view: PlayerView,
    common_view: CommonView,
    settings: GameSettings,
    inferred_hands: List[InferredHand],
    *,
    hint_tokens: Optional[int] = None,
) -> bool:
    """Approx that next would get §9.2 ``good`` via playable-for-prev (§9.0.1)."""
    tokens = common_view.hint_tokens if hint_tokens is None else hint_tokens
    if 0 == tokens:
        return False
    prev_seat = (hinter + 2) % 3
    if _seat_has_convention_playable(inferred_hands[prev_seat]):
        return False
    return _prev_has_unidentified_physical_playable(
        prev_seat, player_view, common_view, settings, inferred_hands
    )


def _chop_card_is_dangerous(
    seat: int,
    player_view: PlayerView,
    common_view: CommonView,
    settings: GameSettings,
    inferred_hands: List[InferredHand],
) -> bool:
    hand = inferred_hands[seat]
    ensure_default_chop(hand)
    if hand.chop is None:
        return False
    assert seat in player_view.teammates
    card = player_view.teammates[seat].cards[hand.chop]
    kind = common_view.card_kind(card, settings)
    return CardKind.CRITICAL == kind or CardKind.PLAYABLE == kind


def _next_would_discard_danger(
    hinter: int,
    player_view: PlayerView,
    common_view: CommonView,
    settings: GameSettings,
    inferred_hands: List[InferredHand],
    *,
    hint_tokens: Optional[int] = None,
) -> bool:
    """True when next is about to discard a last-copy critical/playable (§9.0.1)."""
    tokens = common_view.hint_tokens if hint_tokens is None else hint_tokens
    next_seat = (hinter + 1) % 3
    next_hand = inferred_hands[next_seat]
    if _seat_has_convention_playable(next_hand):
        return False
    if not _chop_card_is_dangerous(next_seat, player_view, common_view, settings, inferred_hands):
        return False
    if 0 == tokens:
        return True
    ensure_default_chop(next_hand)
    if not next_hand.chop_confirmed:
        return False
    if _next_likely_good(
        hinter,
        player_view,
        common_view,
        settings,
        inferred_hands,
        hint_tokens=tokens,
    ):
        return False
    return True


def _channel_protects_next(
    hinter: int,
    player_view: PlayerView,
    common_view: CommonView,
    settings: GameSettings,
    inferred_hands: List[InferredHand],
) -> bool:
    """True when the standard convention channel stops next burning (§9.0.1)."""
    channel = _project_channel(hinter, player_view, common_view, settings, inferred_hands)
    if not channel.buildable:
        return False
    hands = [copy_inferred_hand(h) for h in inferred_hands]
    decoded_next = (channel.enc_type - channel.peer_codes[channel.prev_seat]) % 8
    decoded_prev = (channel.enc_type - channel.peer_codes[channel.next_seat]) % 8
    fives_possible = any_five_possibly_playable(common_view, settings)
    if not decoded_value_is_applicable(hands[channel.next_seat], decoded_next, fives_possible):
        return False
    if not decoded_value_is_applicable(hands[channel.prev_seat], decoded_prev, fives_possible):
        return False
    apply_decoded_value(hands[channel.next_seat], decoded_next, fives_possible)
    apply_decoded_value(hands[channel.prev_seat], decoded_prev, fives_possible)
    return not _next_would_discard_danger(
        hinter, player_view, common_view, settings, hands
    )


@dataclass(frozen=True)
class _ChannelProjection:
    """Would-be convention channel outcomes for one hinter decision (§9.2)."""

    next_seat: int
    prev_seat: int
    peer_codes: Dict[int, int]
    enc_type: int
    type_sum: str
    buildable: bool
    next_new_playable: Optional[Card]
    prev_new_playable: Optional[Card]
    next_discard: Optional[Card]
    prev_discard: Optional[Card]
    causes_double_play: bool
    identifies_new_playable_for_next: bool
    trash_next_and_play_prev: bool
    known_five_assist: bool
    causes_double_midrank_discard: bool
    quality: HintQuality


def _project_channel(
    hinter: int,
    player_view: PlayerView,
    common_view: CommonView,
    settings: GameSettings,
    inferred_hands: List[InferredHand],
) -> _ChannelProjection:
    """Compute peer codes and projected decode cards once for hint quality / logging."""
    next_seat = (hinter + 1) % 3
    prev_seat = (hinter + 2) % 3
    peer_codes = _peer_codes_next_then_prev(hinter, player_view, common_view, settings, inferred_hands)
    enc_type = sum(peer_codes.values()) % 8
    type_sum = f"{peer_codes[next_seat]}+{peer_codes[prev_seat]}"
    physical_hint = _build_hint_for_encoded(hinter, player_view, enc_type)
    buildable = physical_hint is not None
    next_new_playable = _newly_decoded_playable_card_from_codes(
        next_seat,
        peer_codes[prev_seat],
        enc_type,
        player_view,
        common_view,
        settings,
        inferred_hands,
    )
    prev_new_playable = _newly_decoded_playable_card_from_codes(
        prev_seat,
        peer_codes[next_seat],
        enc_type,
        player_view,
        common_view,
        settings,
        inferred_hands,
    )
    next_discard = _newly_decoded_discard_card_from_codes(
        next_seat,
        peer_codes[prev_seat],
        enc_type,
        player_view,
        common_view,
        settings,
        inferred_hands,
    )
    prev_discard = _newly_decoded_discard_card_from_codes(
        prev_seat,
        peer_codes[next_seat],
        enc_type,
        player_view,
        common_view,
        settings,
        inferred_hands,
    )
    causes_double_play = (
        next_new_playable is not None
        and prev_new_playable is not None
        and next_new_playable == prev_new_playable
    )
    identifies_new_playable_for_next = False
    if (
        buildable
        and not any(Playability.PLAYABLE == b.playability for b in inferred_hands[next_seat].cards)
        and not causes_double_play
        and next_new_playable is not None
        and not _card_already_identified_playable_on_visible_seats(
            next_new_playable, hinter, player_view, inferred_hands
        )
    ):
        identifies_new_playable_for_next = True
    trash_next_and_play_prev = False
    if (
        buildable
        and not any(Playability.PLAYABLE == b.playability for b in inferred_hands[prev_seat].cards)
        and next_discard is not None
        and prev_new_playable is not None
    ):
        next_hand = player_view.teammates[next_seat].cards
        prev_hand = player_view.teammates[prev_seat].cards
        if _is_good_discard_trash(next_discard, next_hand, [prev_hand], common_view, settings):
            if not _card_already_identified_playable_on_visible_seats(
                prev_new_playable, hinter, player_view, inferred_hands
            ):
                trash_next_and_play_prev = True
    known_five_assist = False
    if buildable and physical_hint is not None:
        known_five_assist = _known_five_assist_is_good(
            hinter,
            next_seat,
            prev_seat,
            physical_hint,
            next_new_playable,
            prev_new_playable,
            next_discard,
            prev_discard,
            causes_double_play,
            player_view,
            common_view,
            settings,
            inferred_hands,
        )
    causes_double_midrank_discard = (
        next_discard is not None
        and next_discard.number in (Number.TWO, Number.THREE, Number.FOUR)
        and prev_discard is not None
        and next_discard == prev_discard
    )
    if not buildable:
        quality = HintQuality.FINE
    elif identifies_new_playable_for_next or trash_next_and_play_prev or known_five_assist:
        quality = HintQuality.GOOD
    elif causes_double_midrank_discard or (
        causes_double_play and 1 == common_view.live_tokens
    ):
        # Double-play is fine with spare lives (tempo over bomb risk); bad on the last life.
        quality = HintQuality.BAD
    else:
        quality = HintQuality.FINE
    return _ChannelProjection(
        next_seat=next_seat,
        prev_seat=prev_seat,
        peer_codes=peer_codes,
        enc_type=enc_type,
        type_sum=type_sum,
        buildable=buildable,
        next_new_playable=next_new_playable,
        prev_new_playable=prev_new_playable,
        next_discard=next_discard,
        prev_discard=prev_discard,
        causes_double_play=causes_double_play,
        identifies_new_playable_for_next=identifies_new_playable_for_next,
        trash_next_and_play_prev=trash_next_and_play_prev,
        known_five_assist=known_five_assist,
        causes_double_midrank_discard=causes_double_midrank_discard,
        quality=quality,
    )


def _hint_quality(
    hinter: int,
    player_view: PlayerView,
    common_view: CommonView,
    settings: GameSettings,
    inferred_hands: List[InferredHand],
) -> HintQuality:
    """Classify the would-be convention channel (§9.2). Unbuildable → fine."""
    return _project_channel(hinter, player_view, common_view, settings, inferred_hands).quality


def _convention_hint_would_cause_double_midrank_discard(
    hinter: int,
    player_view: PlayerView,
    common_view: CommonView,
    settings: GameSettings,
    inferred_hands: List[InferredHand],
) -> bool:
    """True when both peers' discard decodes recommend the same 2/3/4 identity (§9.2 ``bad``)."""
    return _project_channel(
        hinter, player_view, common_view, settings, inferred_hands
    ).causes_double_midrank_discard


def _convention_hint_would_cause_double_play(
    hinter: int,
    player_view: PlayerView,
    common_view: CommonView,
    settings: GameSettings,
    inferred_hands: List[InferredHand],
) -> bool:
    """True when next and prev would both newly mark the same playable identity."""
    return _project_channel(
        hinter, player_view, common_view, settings, inferred_hands
    ).causes_double_play


def _convention_hint_would_identify_new_playable(
    hinter: int,
    player_view: PlayerView,
    common_view: CommonView,
    settings: GameSettings,
    inferred_hands: List[InferredHand],
) -> bool:
    return _project_channel(
        hinter, player_view, common_view, settings, inferred_hands
    ).identifies_new_playable_for_next


def _convention_hint_would_trash_next_and_play_prev(
    hinter: int,
    player_view: PlayerView,
    common_view: CommonView,
    settings: GameSettings,
    inferred_hands: List[InferredHand],
) -> bool:
    """Good: next gets a useless/dup discard recommendation and prev a new playable (§9.2)."""
    return _project_channel(
        hinter, player_view, common_view, settings, inferred_hands
    ).trash_next_and_play_prev


def _convention_hint_would_known_five_assist(
    hinter: int,
    player_view: PlayerView,
    common_view: CommonView,
    settings: GameSettings,
    inferred_hands: List[InferredHand],
) -> bool:
    """Good: number-5 newly marks known_five and decode has playable or useless/dup trash (§9.2)."""
    return _project_channel(
        hinter, player_view, common_view, settings, inferred_hands
    ).known_five_assist


def _newly_decoded_discard_card_from_codes(
    decoder: int,
    peer_type: int,
    enc_type: int,
    player_view: PlayerView,
    common_view: CommonView,
    settings: GameSettings,
    inferred_hands: List[InferredHand],
) -> Optional[Card]:
    """Card implied by a discard decode for ``decoder``, or ``None`` if play / unusable."""
    assert decoder in player_view.teammates
    decoded_type = (enc_type - peer_type) % 8
    fives_possible = any_five_possibly_playable(common_view, settings)
    n = n_play(inferred_hands[decoder], fives_possible)
    if 1 <= decoded_type <= n:
        return None
    for code, slot, _confirmed in indicable_discard_options(inferred_hands[decoder], fives_possible):
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
    inferred_hands: List[InferredHand],
) -> Optional[Card]:
    assert decoder in player_view.teammates
    decoded_type = (enc_type - peer_type) % 8
    fives_possible = any_five_possibly_playable(common_view, settings)
    n = n_play(inferred_hands[decoder], fives_possible)
    if not 1 <= decoded_type <= n:
        return None
    play_slot = slot_for_play_type(inferred_hands[decoder], decoded_type, fives_possible)
    if play_slot is None:
        return None
    if Playability.PLAYABLE == inferred_hands[decoder].cards[play_slot].playability:
        return None
    card = player_view.teammates[decoder].cards[play_slot]
    if CardKind.PLAYABLE != common_view.card_kind(card, settings):
        return None
    return card


def _card_already_identified_playable_on_visible_seats(
    card: Card,
    hinter: int,
    player_view: PlayerView,
    inferred_hands: List[InferredHand],
) -> bool:
    for seat, hand in player_view.teammates.items():
        assert seat != hinter
        for slot, held in enumerate(hand.cards):
            if card != held:
                continue
            if Playability.PLAYABLE == inferred_hands[seat].cards[slot].playability:
                return True
    return False


def _physical_hint_newly_marks_known_five(
    hint_move: HintMove,
    inferred_hands: List[InferredHand],
) -> bool:
    """True when a number-5 touch would set known_five on a slot that is not already marked."""
    if not isinstance(hint_move, NumberHint) or Number.FIVE != hint_move.number:
        return False
    target = hint_move.teammate
    return any(not inferred_hands[target].cards[slot].known_five for slot in hint_move.cards)


def _assist_qualifying_new_playable(
    card: Optional[Card],
    seat: int,
    hinter: int,
    causes_double_play: bool,
    player_view: PlayerView,
    inferred_hands: List[InferredHand],
) -> bool:
    """Playable half of known-5 assist: same exclusions as §9.2 playable clauses."""
    if card is None or causes_double_play:
        return False
    if any(Playability.PLAYABLE == b.playability for b in inferred_hands[seat].cards):
        return False
    return not _card_already_identified_playable_on_visible_seats(
        card, hinter, player_view, inferred_hands
    )


def _known_five_assist_is_good(
    hinter: int,
    next_seat: int,
    prev_seat: int,
    physical_hint: HintMove,
    next_new_playable: Optional[Card],
    prev_new_playable: Optional[Card],
    next_discard: Optional[Card],
    prev_discard: Optional[Card],
    causes_double_play: bool,
    player_view: PlayerView,
    common_view: CommonView,
    settings: GameSettings,
    inferred_hands: List[InferredHand],
) -> bool:
    """§9.2: newly mark known_five on either peer plus playable or useless/dup trash decode."""
    if not _physical_hint_newly_marks_known_five(physical_hint, inferred_hands):
        return False
    next_hand = player_view.teammates[next_seat].cards
    prev_hand = player_view.teammates[prev_seat].cards
    has_playable = _assist_qualifying_new_playable(
        next_new_playable, next_seat, hinter, causes_double_play, player_view, inferred_hands
    ) or _assist_qualifying_new_playable(
        prev_new_playable, prev_seat, hinter, causes_double_play, player_view, inferred_hands
    )
    if has_playable:
        return True
    if next_discard is not None and _is_good_discard_trash(
        next_discard, next_hand, [prev_hand], common_view, settings
    ):
        return True
    if prev_discard is not None and _is_good_discard_trash(
        prev_discard, prev_hand, [next_hand], common_view, settings
    ):
        return True
    return False
