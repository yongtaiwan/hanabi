"""
Game state classes for Hanabi.
"""

from __future__ import annotations

import copy
import logging
from collections import Counter
from typing import Dict, List, Optional, TYPE_CHECKING, Any, Callable

from .hint_rules import is_legal_hint_against_hand_cards

# Set up logger for this module
logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from .moves import Move, Play, Discard, ColorHint, NumberHint, CardMove, Hint
    from .player import PlayerTeam
else:
    from .moves import Move, Play, Discard, ColorHint, NumberHint, CardMove, Hint

from .enums import Color, Number, CardKind
from .card import Card, Suit


class Deck:
    """Represents a deck of cards."""

    def __init__(self, cards: List[Card]):
        """
        Initialize a deck.

        Args:
            cards: List of cards in the deck
        """
        self._cards = cards.copy()

    def __len__(self) -> int:
        """Get the number of cards in the deck."""
        return len(self._cards)

    def __repr__(self) -> str:
        return f"Deck({len(self._cards)} cards)"

    @property
    def cards(self) -> List[Card]:
        """Get the list of cards in the deck."""
        return self._cards.copy()

    def shuffle(self) -> None:
        """
        Shuffle the deck in-place.

        Uses random.shuffle() to randomize the order of cards.
        """
        import random

        random.shuffle(self._cards)


class StartPosition:
    """Represents the starting position of a game (settings and initial deck)."""

    def __init__(self, settings: GameSettings, draw_deck: Deck):
        """
        Initialize a start position.

        Args:
            settings: Game settings
            draw_deck: The initial draw deck
        """
        self._settings = settings
        self._draw_deck = draw_deck

    def __repr__(self) -> str:
        return f"StartPosition(settings={self._settings}, deck={self._draw_deck})"

    @property
    def settings(self) -> GameSettings:
        """Get the game settings."""
        return self._settings

    @property
    def draw_deck(self) -> Deck:
        """Get the initial draw deck."""
        return self._draw_deck


class Hand:
    """A player's hand.

    Indices match left-to-right display: ``0`` is C1 (oldest among held cards); new draws
    append on the right. A short endgame hand only uses indices ``0 .. len-1`` (no C4 slot
    when ``len == 3``, etc.).
    """

    def __init__(self, cards: List[Card]):
        self._cards = cards.copy()

    def __repr__(self) -> str:
        return f"Hand({self._cards})"

    def __len__(self) -> int:
        return len(self._cards)

    @property
    def cards(self) -> List[Card]:
        """Get the list of cards in the hand."""
        return self._cards.copy()


class GameSettings:
    """Game configuration settings."""

    def __init__(
        self,
        num_players: int,
        max_live_tokens: int,
        max_hint_tokens: int,
        max_cards_in_hand: int,
        cards: Dict[Color, Suit],
        auto_end_when_no_points_possible: bool = False,
    ):
        """
        Initialize game settings.

        Args:
            num_players: Number of players in the game
            max_live_tokens: Maximum number of live tokens
            max_hint_tokens: Maximum number of hint tokens
            max_cards_in_hand: Maximum cards a player can hold
            cards: Dictionary mapping Color to Suit
            auto_end_when_no_points_possible: If True, automatically end game when no more points are possible
        """
        self._num_players = num_players
        self._max_live_tokens = max_live_tokens
        self._max_hint_tokens = max_hint_tokens
        self._max_cards_in_hand = max_cards_in_hand
        self._cards = cards.copy()
        self._auto_end_when_no_points_possible = auto_end_when_no_points_possible

    def __repr__(self) -> str:
        return (
            f"GameSettings(players={self._num_players}, "
            f"max_live={self._max_live_tokens}, "
            f"max_hint={self._max_hint_tokens})"
        )

    @property
    def num_players(self) -> int:
        """Get the number of players."""
        return self._num_players

    @property
    def max_live_tokens(self) -> int:
        """Get the maximum number of live tokens."""
        return self._max_live_tokens

    @property
    def max_hint_tokens(self) -> int:
        """Get the maximum number of hint tokens."""
        return self._max_hint_tokens

    @property
    def max_cards_in_hand(self) -> int:
        """Get the maximum cards in hand."""
        return self._max_cards_in_hand

    @property
    def cards(self) -> Dict[Color, Suit]:
        """Get the cards mapping (Color -> Suit)."""
        return self._cards.copy()

    @property
    def auto_end_when_no_points_possible(self) -> bool:
        """Get whether to auto-end when no more points are possible."""
        return self._auto_end_when_no_points_possible


def create_deck_from_settings(settings: GameSettings) -> Deck:
    """
    Create a Deck from GameSettings.

    Args:
        settings: Game settings containing card distribution

    Returns:
        A new Deck instance with cards according to the settings
    """
    from .card import Card

    # Create the deck from settings
    draw_deck: List[Card] = []
    for color, suit in settings.cards.items():
        for number, quantity in suit.cards.items():
            for _ in range(quantity):
                draw_deck.append(Card(color, number))

    return Deck(draw_deck)


def create_standard_game_settings(num_players: int) -> GameSettings:
    """
    Create a GameSettings instance following standard Hanabi rules.

    Standard Hanabi rules:
    - 2-5 players
    - 5 colors: WHITE, RED, BLUE, YELLOW, GREEN
    - Card distribution per color: 1:3, 2:2, 3:2, 4:2, 5:1
    - 8 hint tokens (clock tokens)
    - 3 live tokens (fuse tokens)
    - Cards per hand: 5 for 2-3 players, 4 for 4-5 players

    Args:
        num_players: Number of players (2-5)

    Returns:
        A GameSettings instance configured for standard Hanabi rules

    """
    assert 2 <= num_players <= 5, f"Hanabi requires 2-5 players, got {num_players}"

    # Standard card distribution per color: {Number: quantity}
    standard_distribution = {
        Number.ONE: 3,
        Number.TWO: 2,
        Number.THREE: 2,
        Number.FOUR: 2,
        Number.FIVE: 1,
    }

    # Standard colors for Hanabi (excluding MULTI)
    standard_colors = [
        Color.WHITE,
        Color.RED,
        Color.BLUE,
        Color.YELLOW,
        Color.GREEN,
    ]

    # Create a Suit for each color with the standard distribution
    cards: Dict[Color, Suit] = {}
    for color in standard_colors:
        cards[color] = Suit(standard_distribution.copy())

    # Cards per hand based on player count
    # 2-3 players: 5 cards, 4-5 players: 4 cards
    max_cards_in_hand = 5 if num_players <= 3 else 4

    # Standard token counts
    max_live_tokens = 3  # Fuse tokens
    max_hint_tokens = 8  # Clock tokens

    return GameSettings(
        num_players=num_players,
        max_live_tokens=max_live_tokens,
        max_hint_tokens=max_hint_tokens,
        max_cards_in_hand=max_cards_in_hand,
        cards=cards,
        auto_end_when_no_points_possible=False,  # Default: follow standard rules (game continues)
    )


class CommonView:
    """Common view of the game state visible to all players."""

    def __init__(
        self,
        live_tokens: int,
        hint_tokens: int,
        cards_to_draw: int,
        cards_discarded: Dict[Color, Suit],
        cards_played: Dict[Color, Number],
    ):
        """
        Initialize common view.

        Args:
            live_tokens: Current number of live tokens
            hint_tokens: Current number of hint tokens
            cards_to_draw: Number of cards remaining to draw
            cards_discarded: Dictionary mapping Color to Suit of discarded cards
            cards_played: Dictionary mapping Color to Number of played cards
        """
        self._live_tokens = live_tokens
        self._hint_tokens = hint_tokens
        self._cards_to_draw = cards_to_draw
        self._cards_discarded = cards_discarded.copy()
        self._cards_played = cards_played.copy()

    def __repr__(self) -> str:
        return f"CommonView(live={self._live_tokens}, hint={self._hint_tokens}, to_draw={self._cards_to_draw})"

    @property
    def live_tokens(self) -> int:
        """Get the current number of live tokens."""
        return self._live_tokens

    @property
    def hint_tokens(self) -> int:
        """Get the current number of hint tokens."""
        return self._hint_tokens

    @property
    def cards_to_draw(self) -> int:
        """Get the number of cards remaining to draw."""
        return self._cards_to_draw

    @property
    def cards_discarded(self) -> Dict[Color, Suit]:
        """Get the discarded cards mapping (Color -> Suit)."""
        return self._cards_discarded.copy()

    @property
    def cards_played(self) -> Dict[Color, Number]:
        """Get the played cards mapping (Color -> Number)."""
        return self._cards_played.copy()

    def card_kind(self, card: Card, settings: GameSettings) -> CardKind:
        """
        Classify ``card`` for full-information discard / play heuristics.

        Exactly one of USELESS, PLAYABLE, CRITICAL, or DISPENSABLE (priority order).
        USELESS includes duplicates under the pile top and ranks that can never be
        reached because some lower rank has no copies left.
        """
        if self._card_dead_on_pile(card):
            return CardKind.USELESS
        if self._color_rank_unreachable(card.color, card.number, settings):
            return CardKind.USELESS
        if self._card_playable_now(card):
            return CardKind.PLAYABLE
        if 1 == self._rank_copies_remaining_for_fireworks(card.color, card.number, settings):
            return CardKind.CRITICAL
        return CardKind.DISPENSABLE

    def _card_dead_on_pile(self, card: Card) -> bool:
        """Pile for this color is already at or past this card's rank."""
        if card.color not in self._cards_played:
            return False
        return card.number.value <= self._cards_played[card.color].value

    def _card_playable_now(self, card: Card) -> bool:
        """This card could be played on the fireworks this turn."""
        if card.color not in self._cards_played:
            return card.number == Number.ONE
        return card.number.value == self._cards_played[card.color].value + 1

    def _played_top_value(self, color: Color) -> int:
        p = self._cards_played.get(color)
        return p.value if p else 0

    def _rank_copies_remaining_for_fireworks(self, color: Color, rank: Number, settings: GameSettings) -> int:
        """Copies of (color, rank) not yet discarded and not already on the pile."""
        suit = settings.cards.get(color)
        if suit is None:
            return 0
        total = suit.cards.get(rank, 0)
        disc = self._cards_discarded.get(color)
        discarded = disc.cards.get(rank, 0) if disc else 0
        played_top = self._played_top_value(color)
        on_pile = 1 if played_top >= rank.value else 0
        return total - discarded - on_pile

    def _color_rank_unreachable(self, color: Color, rank: Number, settings: GameSettings) -> bool:
        """True if some rank on the path from pile top to ``rank`` has no copies left."""
        played_top = self._played_top_value(color)
        rv = rank.value
        if rv <= played_top:
            return False
        for m in range(played_top + 1, rv + 1):
            n = Number(m)
            if self._rank_copies_remaining_for_fireworks(color, n, settings) <= 0:
                return True
        return False


class PlayerView:
    """View of the game state from a player's perspective."""

    def __init__(self, teammates: Dict[int, Hand], own_hand_size: int):
        """
        Initialize player view.

        Args:
            teammates: Dictionary mapping player index to their Hand
            own_hand_size: The size of the player's own hand (cards are hidden)
        """
        self._teammates = {k: Hand(v.cards) for k, v in teammates.items()}
        self._own_hand_size = own_hand_size

    def __repr__(self) -> str:
        return f"PlayerView(teammates={list(self._teammates.keys())}, own_hand_size={self._own_hand_size})"

    @property
    def teammates(self) -> Dict[int, Hand]:
        """Get the teammates' hands (player index -> Hand)."""
        return {k: Hand(v.cards) for k, v in self._teammates.items()}

    @property
    def own_hand_size(self) -> int:
        """Get the size of the player's own hand (cards are hidden)."""
        return self._own_hand_size

    def visible_hand_card_counts(self) -> Counter:
        """Multiset of cards visible in teammates' hands (excludes own hidden hand)."""
        c: Counter = Counter()
        for hand in self._teammates.values():
            for card in hand.cards:
                c[card] += 1
        return c


class GameState:
    """Represents the state of a game."""

    def __init__(
        self,
        start_position: StartPosition,
        common_view: CommonView,
        player_hands: List[Hand],
        draw_deck_index: int,
        turn_number: int,
        current_player: int,
        turns_left: Optional[int],
    ):
        """
        Initialize game state.

        Args:
            start_position: The starting position (settings and initial deck)
            common_view: The common view visible to all players
            player_hands: List of hands for each player
            draw_deck_index: Current index in the draw deck
            turn_number: Current turn number (0-based, starts at 0)
            current_player: Index of the current player
            turns_left: Number of turns left (None if deck not exhausted)
        """
        self._start_position = start_position
        self._common_view = common_view
        self._player_hands = [Hand(h.cards) for h in player_hands]
        self._draw_deck_index = draw_deck_index
        self._turn_number = turn_number
        self._current_player = current_player
        self._turns_left = turns_left

    def __copy__(self) -> GameState:
        """
        Support for copy.copy() - creates a shallow copy of the game state.

        Returns:
            A new GameState instance with copied data
        """
        # Create a new CommonView with copies of mutable data
        # This is necessary because CommonView contains mutable dictionaries
        new_common_view = CommonView(
            live_tokens=self._common_view._live_tokens,
            hint_tokens=self._common_view._hint_tokens,
            cards_to_draw=self._common_view._cards_to_draw,
            cards_discarded=self._common_view._cards_discarded,
            cards_played=self._common_view._cards_played,
        )

        return GameState(
            start_position=self._start_position,
            common_view=new_common_view,
            player_hands=self._player_hands,
            draw_deck_index=self._draw_deck_index,
            turn_number=self._turn_number,
            current_player=self._current_player,
            turns_left=self._turns_left,
        )

    def __deepcopy__(self, memo: Dict[int, Any]) -> GameState:
        """Support for copy.deepcopy()."""
        # Create a new instance with deep copies of mutable data
        return GameState(
            start_position=copy.deepcopy(self._start_position, memo),
            common_view=copy.deepcopy(self._common_view, memo),
            player_hands=[Hand(h.cards.copy()) for h in self._player_hands],
            draw_deck_index=self._draw_deck_index,
            turn_number=self._turn_number,
            current_player=self._current_player,
            turns_left=self._turns_left,
        )

    def __repr__(self) -> str:
        return f"GameState(draw_deck_index={self._draw_deck_index})"

    @property
    def start_position(self) -> StartPosition:
        """Get the starting position."""
        return self._start_position

    @property
    def common_view(self) -> CommonView:
        """Get the common view."""
        return self._common_view

    @property
    def player_hands(self) -> List[Hand]:
        """Get the list of player hands."""
        return [Hand(h.cards) for h in self._player_hands]

    @property
    def draw_deck_index(self) -> int:
        """Get the current draw deck index."""
        return self._draw_deck_index

    @property
    def turn_number(self) -> int:
        """Get the current turn number."""
        return self._turn_number

    @property
    def current_player(self) -> int:
        """Get the current player index."""
        return self._current_player

    @property
    def turns_left(self) -> Optional[int]:
        """Get the number of turns left (None if deck not exhausted)."""
        return self._turns_left

    @property
    def settings(self) -> GameSettings:
        """Get the game settings."""
        return self._start_position.settings

    def update(self, player_index: int, move: Move) -> None:
        """
        Update the game state in-place with a move.

        Args:
            player_index: Index of the player making the move
            move: The move to apply
        """
        assert 0 <= player_index < len(self._player_hands), (
            f"player_index {player_index} out of range [0, {len(self._player_hands)})"
        )

        if isinstance(move, Play):
            self._update_play(player_index, move)
        elif isinstance(move, Discard):
            self._update_discard(player_index, move)
        elif isinstance(move, (ColorHint, NumberHint)):
            self._update_hint(player_index, move)
        else:
            assert False, f"Unknown move type: {type(move)}"

    def is_finished(self) -> bool:
        """
        Check if the game is finished.

        Returns:
            True if the game is finished, False otherwise
        """
        logger.debug(
            f"[is_finished] Checking game end conditions: live_tokens={self._common_view.live_tokens}, "
            f"turns_left={self._turns_left}, turn_number={self._turn_number}, "
            f"current_player={self._current_player}"
        )

        # 1. All life tokens are lost
        if self._common_view.live_tokens <= 0:
            logger.debug("[is_finished] Game finished: All life tokens lost")
            return True

        # 2. All fireworks are completed (perfect score)
        cards_played = self._common_view.cards_played
        if 5 == len(cards_played):  # All 5 colors
            all_fives = all(num == Number.FIVE for num in cards_played.values())
            if all_fives:
                logger.debug("[is_finished] Game finished: All fireworks completed (perfect score)")
                return True

        # 3. Deck is exhausted and all players have taken final turn
        # Assert invariant: if deck is exhausted (no cards to draw), turns_left must be set
        original_deck_size = len(self._start_position.draw_deck.cards)
        if self._draw_deck_index >= original_deck_size:
            assert self._turns_left is not None, (
                f"Deck is exhausted (draw_deck_index={self._draw_deck_index} >= {original_deck_size}, "
                f"cards_to_draw={self._common_view._cards_to_draw}) but turns_left is None"
            )
        if 0 == self._turns_left:
            logger.debug(
                f"[is_finished] Game finished: 0 == turns_left (deck exhausted, all players took final turn)"
            )
            return True

        # 4. Auto-end when no more points possible (if setting enabled)
        if self.settings.auto_end_when_no_points_possible:
            if self._is_no_more_points_possible():
                logger.debug("[is_finished] Game finished: No more points possible")
                return True

        logger.debug("[is_finished] Game not finished")
        return False

    def score(self) -> int:
        """
        Calculate the game score.

        Returns:
            The current game score
        """
        cards_played = self._common_view.cards_played
        score = 0
        for number in cards_played.values():
            score += number.value
        return score

    def advance_player(self, num_players: int) -> None:
        """
        Advance to the next player's turn (in-place update).

        Args:
            num_players: Total number of players in the game
        """
        assert num_players > 0, f"num_players must be positive, got {num_players}"
        assert 0 <= self._current_player < num_players, (
            f"current_player {self._current_player} out of range [0, {num_players})"
        )

        old_player = self._current_player
        self._current_player = (self._current_player + 1) % num_players
        logger.debug(f"[advance_player] Player {old_player} -> {self._current_player}, turns_left={self._turns_left}")

        # If deck is exhausted, decrement turns remaining
        # Assert invariant: if deck is exhausted, turns_left must be set
        original_deck_size = len(self._start_position.draw_deck.cards)
        if self._draw_deck_index >= original_deck_size:
            assert self._turns_left is not None, (
                f"Deck is exhausted (draw_deck_index={self._draw_deck_index} >= {original_deck_size}) "
                f"but turns_left is None in advance_player"
            )

        if self._turns_left is not None:
            assert self._turns_left > 0, f"turns_left should be > 0 when deck is exhausted, got {self._turns_left}"
            old_turns_left = self._turns_left
            self._turns_left -= 1
            assert self._turns_left >= 0, f"turns_left became negative: {self._turns_left}"
            logger.debug(f"[advance_player] Decremented turns_left: {old_turns_left} -> {self._turns_left}")
        else:
            logger.debug(f"[advance_player] turns_left is None (deck not exhausted)")

    def _validate(self, player_index: int, move: Move) -> bool:
        """
        Validate a move for a player.

        Args:
            player_index: Index of the player making the move
            move: The move to validate

        Returns:
            True if the move is valid, False otherwise
        """
        # Check if it's the player's turn
        if player_index != self._current_player:
            return False

        # Check if game is over
        if 0 == self._turns_left:
            return False

        if isinstance(move, CardMove):
            return self._validate_card_move(player_index, move)
        if isinstance(move, Hint):
            return self._validate_hint(player_index, move)
        assert False, f"unexpected move type in _validate: {type(move)}"

    def _validate_card_move(self, player_index: int, move: CardMove) -> bool:
        """
        Validate a card move (Play or Discard).

        Args:
            player_index: Index of the player making the move
            move: The card move to validate

        Returns:
            True if the move is valid, False otherwise
        """
        # Check card index is valid
        hand = self._player_hands[player_index]
        if move.card < 0 or move.card >= len(hand.cards):
            return False

        # Discard-specific validation
        if isinstance(move, Discard):
            # Cannot discard if hint tokens are already at maximum
            if self._common_view.hint_tokens >= self.settings.max_hint_tokens:
                return False

        # Play moves don't have additional validation here
        # (validity of the play itself is checked in _update_play)

        return True

    def _validate_hint(self, player_index: int, move: Hint) -> bool:
        """
        Validate a hint move (ColorHint or NumberHint).

        Args:
            player_index: Index of the player making the move
            move: The hint move to validate

        Returns:
            True if the move is valid, False otherwise
        """
        # Check if hint tokens available
        if 0 == self._common_view.hint_tokens:
            return False

        # Check if teammate index is valid
        if move.teammate < 0 or move.teammate >= len(self._player_hands):
            return False

        # Can't hint yourself
        if move.teammate == player_index:
            return False

        # Check if hint has matching cards
        if not move.cards:
            return False

        teammate_hand = self._player_hands[move.teammate]
        if isinstance(move, ColorHint):
            return is_legal_hint_against_hand_cards(move, teammate_hand.cards)
        if isinstance(move, NumberHint):
            return is_legal_hint_against_hand_cards(move, teammate_hand.cards)

        assert False, f"unexpected hint type in _validate_hint: {type(move)}"

    def _get_validation_error_message(self, player_index: int, move: Move) -> str:
        """
        Get a descriptive error message for an invalid move.

        Args:
            player_index: Index of the player making the move
            move: The move that was invalid

        Returns:
            A descriptive error message
        """
        error_msg = f"Invalid move from player {player_index}: {move}"

        if isinstance(move, Discard):
            if self._common_view.hint_tokens >= self.settings.max_hint_tokens:
                error_msg += f" (hint tokens already at maximum: {self.settings.max_hint_tokens})"
            return error_msg
        if isinstance(move, (ColorHint, NumberHint)):
            if 0 == self._common_view.hint_tokens:
                error_msg += " (no hint tokens available)"
            return error_msg
        if isinstance(move, Play):
            if player_index != self._current_player:
                error_msg += f" (not player {player_index}'s turn, current player is {self._current_player})"
            return error_msg
        assert False, f"unexpected move type in _get_validation_error_message: {type(move)}"

    def _update_play(self, player_index: int, move: Play) -> None:
        """Update state for a play move (in-place)."""
        assert 0 <= player_index < len(self._player_hands), (
            f"player_index {player_index} out of range [0, {len(self._player_hands)})"
        )
        hand = self._player_hands[player_index]
        assert 0 <= move.card < len(hand.cards), f"card index {move.card} out of range [0, {len(hand.cards)})"
        card = hand.cards[move.card]

        # Check if card can be played
        cards_played = self._common_view.cards_played
        expected_number = cards_played.get(card.color, Number.ONE)

        # Determine if valid play
        if card.color not in cards_played:
            is_valid = card.number == Number.ONE
        else:
            next_number_value = expected_number.value + 1
            is_valid = card.number.value == next_number_value

        if is_valid:
            self._play_card(player_index, move.card, card)
        else:
            self._handle_invalid_play(player_index, move.card, card)

    def _play_card(self, player_index: int, card_index: int, card: Card) -> None:
        """Play a card successfully (in-place update)."""
        assert 0 <= player_index < len(self._player_hands), (
            f"player_index {player_index} out of range [0, {len(self._player_hands)})"
        )
        hand = self._player_hands[player_index]
        assert 0 <= card_index < len(hand.cards), f"card_index {card_index} out of range [0, {len(hand.cards)})"
        assert hand.cards[card_index] == card, f"Card at index {card_index} does not match provided card"

        # Remove card from hand
        new_hand_cards = hand.cards.copy()
        new_hand_cards.pop(card_index)

        # Update cards played
        previous_value = self._common_view._cards_played.get(card.color)
        self._common_view._cards_played[card.color] = card.number

        # Check if firework is completed
        firework_completed = card.number == Number.FIVE and previous_value == Number.FOUR

        # Standard Hanabi rule: gain a hint token when completing a firework,
        # but only if we are below the maximum. If we're already at max,
        # we simply don't gain an extra token (no assertion).
        if firework_completed and self._common_view._hint_tokens < self.settings.max_hint_tokens:
            self._common_view._hint_tokens += 1

        # Draw a new card if available
        self._draw_card_to_hand(new_hand_cards)

        # Update player hands
        self._player_hands[player_index] = Hand(new_hand_cards)

    def _handle_invalid_play(self, player_index: int, card_index: int, card: Card) -> None:
        """Handle an invalid play (in-place update)."""
        assert 0 <= player_index < len(self._player_hands), (
            f"player_index {player_index} out of range [0, {len(self._player_hands)})"
        )
        assert self._common_view._live_tokens > 0, f"Cannot lose life token: already at 0"

        # Remove card, discard it, and draw new card (same as discard)
        self._remove_card_and_discard(player_index, card_index, card)

        # Lose a life token (invalid play penalty)
        self._common_view._live_tokens -= 1

    def _update_discard(self, player_index: int, move: Discard) -> None:
        """Update state for a discard move (in-place update)."""
        assert 0 <= player_index < len(self._player_hands), (
            f"player_index {player_index} out of range [0, {len(self._player_hands)})"
        )
        # Assert that hint tokens are not already at max (should be validated before calling)
        assert self._common_view._hint_tokens < self.settings.max_hint_tokens, (
            f"Cannot discard when hint tokens are already at maximum: "
            f"{self._common_view._hint_tokens} >= {self.settings.max_hint_tokens}"
        )

        hand = self._player_hands[player_index]
        assert 0 <= move.card < len(hand.cards), f"card index {move.card} out of range [0, {len(hand.cards)})"
        card = hand.cards[move.card]

        # Remove card, discard it, and draw new card
        self._remove_card_and_discard(player_index, move.card, card)

        # Gain a hint token
        self._common_view._hint_tokens += 1

    def _remove_card_and_discard(self, player_index: int, card_index: int, card: Card) -> None:
        """Remove a card from hand, add to discard, and draw a new card (in-place update)."""
        assert 0 <= player_index < len(self._player_hands), (
            f"player_index {player_index} out of range [0, {len(self._player_hands)})"
        )
        hand = self._player_hands[player_index]
        assert 0 <= card_index < len(hand.cards), f"card_index {card_index} out of range [0, {len(hand.cards)})"
        assert hand.cards[card_index] == card, f"Card at index {card_index} does not match provided card"

        # Remove card from hand and add to discard
        new_hand_cards = hand.cards.copy()
        new_hand_cards.pop(card_index)
        self._add_card_to_discard_pile(card)

        # Draw a new card if available
        self._draw_card_to_hand(new_hand_cards)

        # Update player hands
        self._player_hands[player_index] = Hand(new_hand_cards)

    def _update_hint(self, player_index: int, move: Hint) -> None:
        """Update state for a hint move (in-place update)."""
        assert 0 <= player_index < len(self._player_hands), (
            f"player_index {player_index} out of range [0, {len(self._player_hands)})"
        )
        assert 0 <= move.teammate < len(self._player_hands), (
            f"teammate index {move.teammate} out of range [0, {len(self._player_hands)})"
        )
        assert move.teammate != player_index, f"Player {player_index} cannot hint themselves"
        # Assert that hint tokens are available
        assert self._common_view._hint_tokens > 0, (
            f"Cannot give hint: no hint tokens available (current: {self._common_view._hint_tokens})"
        )

        # Check if deck is already exhausted (hints don't draw cards, so we need to check separately)
        self._check_and_set_turns_left_if_deck_exhausted()

        # Assert invariant: if deck is exhausted, turns_left must be set
        original_deck_size = len(self._start_position.draw_deck.cards)
        if self._draw_deck_index >= original_deck_size:
            assert self._turns_left is not None, (
                f"Deck is exhausted (draw_deck_index={self._draw_deck_index} >= {original_deck_size}) "
                f"but turns_left is None after _check_and_set_turns_left_if_deck_exhausted in _update_hint"
            )

        # Use a hint token
        self._common_view._hint_tokens -= 1

    def _check_and_set_turns_left_if_deck_exhausted(self) -> None:
        """
        Check if deck is exhausted and set turns_left if not already set.

        This is called from both _draw_card_to_hand (when drawing would exhaust deck)
        and _update_hint (when deck is already exhausted and a hint is given).
        """
        original_deck_size = len(self._start_position.draw_deck.cards)
        if self._draw_deck_index >= original_deck_size:
            # Deck exhausted - we want each player to take one more turn
            # The current player has just taken their turn (the one that exhausted the deck)
            # So we need num_players more turns (one for each player)
            # After advanceTurn() decrements it, we'll have num_players turns left
            if self._turns_left is None:
                # Set to num_players + 1 because:
                # - The current player has already taken their turn (exhausted deck)
                # - After this move, advanceTurn() will decrement to num_players
                # - This gives us exactly num_players more turns (one for each player)
                # - When it reaches 0, all players have taken their final turn
                self._turns_left = self.settings.num_players + 1
                logger.debug(
                    f"[_check_and_set_turns_left_if_deck_exhausted] Deck exhausted! Set turns_left={self._turns_left} "
                    f"(num_players={self.settings.num_players})"
                )
            else:
                logger.debug(
                    f"[_check_and_set_turns_left_if_deck_exhausted] Deck exhausted but turns_left "
                    f"already set: {self._turns_left}"
                )
            self._common_view._cards_to_draw = 0
            # Assert invariant: if deck is exhausted, turns_left must be set
            assert self._turns_left is not None, (
                f"Deck is exhausted (draw_deck_index={self._draw_deck_index} >= {original_deck_size}) "
                f"but turns_left is None"
            )
            assert self._turns_left > 0, (
                f"Deck is exhausted but turns_left is {self._turns_left} (should be > 0 when deck just exhausted)"
            )

    def _draw_card_to_hand(self, hand_cards: List[Card]) -> None:
        """Draw a new card from the deck and add it to the hand (in-place update)."""
        original_deck_size = len(self._start_position.draw_deck.cards)
        assert 0 <= self._draw_deck_index <= original_deck_size, (
            f"draw_deck_index {self._draw_deck_index} out of range [0, {original_deck_size}]"
        )

        logger.debug(
            f"[_draw_card_to_hand] draw_deck_index={self._draw_deck_index}, original_deck_size={original_deck_size}, "
            f"turns_left={self._turns_left}, num_players={self.settings.num_players}"
        )

        if self._draw_deck_index < original_deck_size:
            # Draw next card from original deck (append on the right; index 0 = C1/left/oldest)
            new_card = self._start_position.draw_deck.cards[self._draw_deck_index]
            hand_cards.append(new_card)
            self._draw_deck_index += 1
            self._common_view._cards_to_draw = original_deck_size - self._draw_deck_index
            assert self._common_view._cards_to_draw >= 0, (
                f"cards_to_draw became negative: {self._common_view._cards_to_draw}"
            )
            logger.debug(
                f"[_draw_card_to_hand] Drew card, new draw_deck_index={self._draw_deck_index}, "
                f"cards_to_draw={self._common_view._cards_to_draw}"
            )
            # Check if deck is now exhausted after drawing
            self._check_and_set_turns_left_if_deck_exhausted()
            # Assert invariant: if no cards to draw, turns_left must be set
            if 0 == self._common_view._cards_to_draw:
                assert self._turns_left is not None, (
                    f"No cards to draw (cards_to_draw=0) but turns_left is None"
                )
        else:
            # Deck already exhausted - just check and set turns_left if needed
            self._check_and_set_turns_left_if_deck_exhausted()
            # Assert invariant: if deck is exhausted, turns_left must be set
            assert self._turns_left is not None, (
                f"Deck is exhausted (draw_deck_index={self._draw_deck_index} >= {original_deck_size}) "
                f"but turns_left is None"
            )

    def _add_card_to_discard_pile(self, card: Card) -> None:
        """Add a card to the discard pile in common view (in-place update)."""
        # Get current counts for this color
        if card.color in self._common_view._cards_discarded:
            current_suit = self._common_view._cards_discarded[card.color]
            new_counts = current_suit.cards.copy()
        else:
            new_counts = {}

        # Increment count for this card
        if card.number in new_counts:
            new_counts[card.number] += 1
        else:
            new_counts[card.number] = 1

        # Update the discard pile dict
        self._common_view._cards_discarded[card.color] = Suit(new_counts)

    def _is_no_more_points_possible(self) -> bool:
        """Check if no more points are possible based on discarded cards."""
        cards_played = self._common_view.cards_played
        cards_discarded = self._common_view.cards_discarded

        # Get discarded counts from CommonView
        discarded_counts: Dict[Color, Dict[Number, int]] = {}
        for color, suit in cards_discarded.items():
            discarded_counts[color] = suit.cards.copy()

        # Check each color
        for color in [Color.WHITE, Color.RED, Color.YELLOW, Color.GREEN, Color.BLUE]:
            # Determine next card needed for this color
            if color in cards_played:
                current_highest = cards_played[color]
                if current_highest == Number.FIVE:
                    continue  # This color is complete
                next_needed = Number(current_highest.value + 1)
            else:
                next_needed = Number.ONE

            # Get total count of this card from settings
            suit = self.settings.cards.get(color)
            if suit is None:
                continue
            total_count = suit.cards.get(next_needed, 0)

            # Count how many are discarded
            discarded_count = discarded_counts.get(color, {}).get(next_needed, 0)

            # If not all copies are discarded, this color can still progress
            if discarded_count < total_count:
                return False

        # All colors are blocked
        return True


class Game:
    """Represents a single game instance and drives the game loop."""

    def __init__(
        self,
        start_position: StartPosition,
        team: PlayerTeam,
        on_move: Optional[Callable[[int, Move, GameState, GameState], None]] = None,
    ):
        """
        Initialize a game.

        Args:
            start_position: The starting position (settings and initial deck)
            team: The team of players (:class:`~hanabi.core.player.BasePlayer` observers and/or
                :class:`~hanabi.core.player.Cheater` full-state agents).
            on_move: Optional callback(player_index, move, old_state, new_state) called after
                     each move is processed. Use for display updates, logging, etc.
        """
        self._start_position = start_position
        self._team = team
        self._on_move: Optional[Callable[[int, Move, GameState, GameState], None]] = on_move
        self._turns: List[GameState] = []

        # Initialize players with game settings
        self._initialize_players()

    def __repr__(self) -> str:
        if not self._turns:
            return f"Game(team={self._team.name()}, turns=0)"
        return f"Game(team={self._team.name()}, turns={len(self._turns)})"

    @property
    def team(self) -> PlayerTeam:
        """Get the player team."""
        return self._team

    @property
    def state(self) -> GameState:
        """Get the current game state (most recent turn)."""
        assert self._turns, "Game not initialized. No turns yet."
        return self._turns[-1]

    @property
    def settings(self) -> GameSettings:
        """Get the game settings."""
        return self._start_position.settings

    @property
    def current_player(self) -> int:
        """Get the current player index."""
        assert self._turns, "Game not initialized. No turns yet."
        return self.state.current_player

    def get_player_view(self, player_index: int) -> PlayerView:
        """Public alias for :meth:`_get_player_view` (tests and tooling)."""
        return self._get_player_view(player_index)

    def process_move(self, player_index: int, move: Move) -> None:
        """Public alias for :meth:`_process_move` (tests and tooling)."""
        self._process_move(player_index, move)

    @property
    def is_finished(self) -> bool:
        """Check if the game is finished."""
        assert self._turns, "Game not initialized. No turns yet."
        return self.state.is_finished()

    def get_score(self) -> int:
        """Calculate the current game score."""
        assert self._turns, "Game not initialized. No turns yet."
        return self.state.score()

    def play(self) -> None:
        """
        Play the game - drives the game loop.

        Calls :meth:`~hanabi.core.player.Player.play` with a :class:`PlayerView` for
        :class:`~hanabi.core.player.BasePlayer` seats, or :meth:`~hanabi.core.player.Cheater.play`
        with :class:`GameState` for cheaters. Notifies :class:`~hanabi.core.player.BasePlayer`
        observers after each move.
        """
        assert self._turns, "Game not initialized. No turns yet."
        from .player import Cheater

        while not self.is_finished:
            current = self.state.current_player
            player = self._team.players[current]

            if isinstance(player, Cheater):
                move = player.play(self.state)
            else:
                player_view = self._get_player_view(current)
                move = player.play(player_view)

            # Process the move; _process_move asserts move legality
            # Note: _process_move calls _notify_players internally before the callback
            self._process_move(current, move)

            # Advance turn
            self._advance_turn()

    @staticmethod
    def create(
        team: PlayerTeam,
        settings: GameSettings,
        on_move: Optional[Callable[[int, Move, GameState, GameState], None]] = None,
    ) -> Game:
        """
        Create and initialize a new game.

        Args:
            team: The team of players (:class:`~hanabi.core.player.BasePlayer` and/or
                :class:`~hanabi.core.player.Cheater`).
            settings: Game settings
            on_move: Optional callback(player_index, move, old_state, new_state) called after
                     each move is processed. Use for display updates, logging, etc.

        Returns:
            A new initialized Game instance
        """
        # Create and shuffle the deck from settings
        original_deck = create_deck_from_settings(settings)
        original_deck.shuffle()

        # Create start position (deck is read-only, we track position via index)
        start_position = StartPosition(settings, original_deck)

        # Deal cards to players (using draw_deck_index to track position)
        num_players = settings.num_players
        cards_per_player = settings.max_cards_in_hand
        player_hands: List[Hand] = []
        draw_deck_index = 0
        deck_cards = original_deck.cards

        # Assert we have enough cards to deal
        required_cards = num_players * cards_per_player
        assert len(deck_cards) >= required_cards, (
            f"Not enough cards in deck: need {required_cards}, have {len(deck_cards)}"
        )

        for player_idx in range(num_players):
            hand_cards: List[Card] = []
            for _ in range(cards_per_player):
                assert draw_deck_index < len(deck_cards), f"Ran out of cards while dealing to player {player_idx}"
                hand_cards.append(deck_cards[draw_deck_index])
                draw_deck_index += 1
            player_hands.append(Hand(hand_cards))

        # Initialize common view
        # cards_to_draw should be remaining cards after dealing
        remaining_cards = len(deck_cards) - draw_deck_index
        common_view = CommonView(
            live_tokens=settings.max_live_tokens,
            hint_tokens=settings.max_hint_tokens,
            cards_to_draw=remaining_cards,
            cards_discarded={},
            cards_played={},
        )

        # Initialize game state (turn 0, player 0 starts, no turns left yet)
        state = GameState(
            start_position=start_position,
            common_view=common_view,
            player_hands=player_hands,
            draw_deck_index=draw_deck_index,
            turn_number=0,
            current_player=0,
            turns_left=None,
        )

        # Create game instance
        game = Game(start_position, team, on_move)

        # Add initial state to turns
        game._turns.append(state)

        # Set common view for all players (they share the same reference, so updates are automatic)
        game._set_common_view_for_players()

        return game

    def _initialize_players(self) -> None:
        """Initialize players with game settings."""
        assert len(self._team.players) == self.settings.num_players, (
            f"Number of players ({len(self._team.players)}) does not match settings ({self.settings.num_players})"
        )
        from .player import BasePlayer

        for player in self._team.players:
            if isinstance(player, BasePlayer):
                player.set_game_settings(self.settings)

    def _set_common_view_for_players(self) -> None:
        """
        Set common view for all players (called after state is created and after each move).

        IMPORTANT: This must be called after each move because GameState.__copy__() creates
        a new CommonView object. Players need to reference the current state's CommonView,
        not a stale one from a previous state.

        Without this, players will see stale hint token counts and may generate invalid moves.
        """
        assert self._turns, "Game not initialized. No turns yet."
        # Set common view - players need the current state's common_view
        # Note: Each GameState has its own CommonView, so we must update players' references
        # after each state transition to ensure they see current values
        from .player import BasePlayer

        for player in self._team.players:
            if isinstance(player, BasePlayer):
                player.set_common_view(self.state.common_view)

    def _notify_players(self, player_index: int, move: Move, state_before_move: GameState) -> None:
        """Notify all :class:`~hanabi.core.player.BasePlayer` seats about a move."""
        from .player import BasePlayer

        for observer_index, player in enumerate(self._team.players):
            if isinstance(player, BasePlayer):
                player.observe(
                    player_index,
                    move,
                    observer_view=self._get_player_view(observer_index),
                )
        _maybe_assert_hint_hand_subtype_beliefs_in_sync(
            self._team.players,
            player_index,
            move,
            cards_played_before=state_before_move.common_view.cards_played,
            hand_cards=[hand.cards for hand in self.state.player_hands],
        )

    def _get_player_view(self, player_index: int) -> PlayerView:
        """
        Get the view of the game from a player's perspective (private).

        Args:
            player_index: Index of the player

        Returns:
            PlayerView showing teammates' hands and own hand size
        """
        assert self._turns, "Game not initialized. No turns yet."
        assert 0 <= player_index < len(self._team.players), (
            f"player_index {player_index} out of range [0, {len(self._team.players)})"
        )

        teammates: Dict[int, Hand] = {}
        for i, hand in enumerate(self.state.player_hands):
            if i != player_index:
                teammates[i] = hand

        own_hand_size = len(self.state.player_hands[player_index].cards)
        return PlayerView(teammates, own_hand_size)

    def _process_move(self, player_index: int, move: Move) -> None:
        """
        Process a move and update the game state.

        Args:
            player_index: Index of the player making the move
            move: The move to process

        """
        assert self._turns, "Game not initialized. No turns yet."
        assert 0 <= player_index < len(self._team.players), (
            f"player_index {player_index} out of range [0, {len(self._team.players)})"
        )

        # Snapshot before appending to history (callback needs pre-move state; self.state changes after append).
        state_before_move = self.state
        logger.debug(
            f"[process_move] Processing move: player={player_index}, move={move}, "
            f"turn_number={state_before_move.turn_number}, current_player={state_before_move.current_player}, "
            f"turns_left={state_before_move.turns_left}, "
            f"cards_to_draw={state_before_move.common_view.cards_to_draw}"
        )

        # Validate the move (callers must supply legal moves; illegal = bug)
        assert self.state._validate(player_index, move), self.state._get_validation_error_message(player_index, move)

        # Clone the current state and update it in-place
        new_state = copy.copy(state_before_move)
        new_state._turn_number += 1  # Increment turn number (0-based)
        logger.debug(f"[process_move] After cloning: new turn_number={new_state._turn_number}")

        # Update the cloned state in-place
        new_state.update(player_index, move)
        logger.debug(
            f"[process_move] After update: turn_number={new_state._turn_number}, "
            f"current_player={new_state.current_player}, turns_left={new_state.turns_left}, "
            f"cards_to_draw={new_state.common_view.cards_to_draw}, "
            f"is_finished={new_state.is_finished()}"
        )

        # Add new state to turns history
        self._turns.append(new_state)

        # Update players' common_view references to point to the new state's common_view
        # This is critical because GameState.__copy__ creates a new CommonView object
        # Players need to see the updated common_view from the current state
        self._set_common_view_for_players()

        # Notify players about the move BEFORE the callback
        # This ensures hints are updated before display is refreshed
        self._notify_players(player_index, move, state_before_move)

        # Notify global callback with old and new state (for display, logging, etc.)
        if self._on_move is not None:
            self._on_move(player_index, move, state_before_move, new_state)

    def _advance_turn(self) -> None:
        """Advance to the next player's turn (internal method)."""
        assert self._turns, "Cannot advance turn: no turns yet"
        num_players = self.settings.num_players
        assert num_players > 0, f"num_players must be positive, got {num_players}"
        last_state = self._turns[-1]
        logger.debug(
            f"[_advance_turn] Before advance: current_player={last_state.current_player}, "
            f"turns_left={last_state.turns_left}, turn_number={last_state.turn_number}"
        )
        last_state.advance_player(num_players)
        logger.debug(
            f"[_advance_turn] After advance: current_player={last_state.current_player}, "
            f"turns_left={last_state.turns_left}, turn_number={last_state.turn_number}, "
            f"is_finished={last_state.is_finished()}"
        )


def _maybe_assert_hint_hand_subtype_beliefs_in_sync(
    players: List[Any],
    hinter_index: int,
    move: Move,
    *,
    cards_played_before: Optional[Dict[Color, Number]] = None,
    hand_cards: Optional[List[List[Card]]] = None,
) -> None:
    """When all seats share a 3p convention bot, propagate beliefs and assert matrices match."""
    if 3 != len(players):
        return
    from hanabi.ai.dynamic_hand_type_3p import (
        DynamicHandType3P,
        align_convention_beliefs_after_move as align_dynamic_hand_type,
    )
    from hanabi.ai.dynamic_recommendation_3p import (
        DynamicRecommendation3P,
        align_convention_beliefs_after_move as align_dynamic_recommendation,
    )
    from hanabi.ai.hint_hand_subtype_3p import (
        HintHandSubtype3P,
        align_convention_beliefs_after_move as align_hint_hand_subtype,
    )

    if all(isinstance(player, DynamicHandType3P) for player in players):
        align = align_dynamic_hand_type
    elif all(isinstance(player, DynamicRecommendation3P) for player in players):
        align = align_dynamic_recommendation
    elif all(isinstance(player, HintHandSubtype3P) for player in players):
        align = align_hint_hand_subtype
    else:
        return
    align(
        players,
        hinter_index,
        move,
        cards_played_before=cards_played_before,
        hand_cards=hand_cards,
    )
