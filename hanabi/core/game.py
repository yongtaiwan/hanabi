"""
Game state classes for Hanabi.
"""

from __future__ import annotations

import copy
import logging
from typing import Dict, List, Optional, TYPE_CHECKING, Any, Callable

# Set up logger for this module
logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from .moves import Move, Play, Discard, ColorHint, NumberHint, CardMove, Hint
    from .player import PlayerTeam
else:
    from .moves import Move, Play, Discard, ColorHint, NumberHint, CardMove, Hint

from .enums import Color, Number
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

    def __len__(self) -> int:
        """Get the number of cards in the deck."""
        return len(self._cards)

    def __repr__(self) -> str:
        return f"Deck({len(self._cards)} cards)"


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

    @property
    def settings(self) -> GameSettings:
        """Get the game settings."""
        return self._settings

    @property
    def drawDeck(self) -> Deck:
        """Get the initial draw deck."""
        return self._draw_deck

    def __repr__(self) -> str:
        return f"StartPosition(settings={self._settings}, deck={self._draw_deck})"


class Hand:
    """Represents a player's hand of cards."""

    def __init__(self, cards: List[Card]):
        self._cards = cards.copy()

    @property
    def cards(self) -> List[Card]:
        """Get the list of cards in the hand."""
        return self._cards.copy()

    def __repr__(self) -> str:
        return f"Hand({self._cards})"

    def __len__(self) -> int:
        return len(self._cards)


class GameSettings:
    """Game configuration settings."""

    def __init__(
        self,
        num_players: int,
        max_live_tokens: int,
        max_hint_tokens: int,
        max_cards_in_hand: int,
        cards: Dict[Color, Suit],
        auto_end_when_no_points_possible: bool = False
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

    @property
    def numPlayers(self) -> int:
        """Get the number of players."""
        return self._num_players

    @property
    def maxLiveTokens(self) -> int:
        """Get the maximum number of live tokens."""
        return self._max_live_tokens

    @property
    def maxHintTokens(self) -> int:
        """Get the maximum number of hint tokens."""
        return self._max_hint_tokens

    @property
    def maxCardsInHand(self) -> int:
        """Get the maximum cards in hand."""
        return self._max_cards_in_hand

    @property
    def cards(self) -> Dict[Color, Suit]:
        """Get the cards mapping (Color -> Suit)."""
        return self._cards.copy()

    @property
    def autoEndWhenNoPointsPossible(self) -> bool:
        """Get whether to auto-end when no more points are possible."""
        return self._auto_end_when_no_points_possible

    def __repr__(self) -> str:
        return (f"GameSettings(players={self._num_players}, "
                f"max_live={self._max_live_tokens}, "
                f"max_hint={self._max_hint_tokens})")


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

    Raises:
        ValueError: If num_players is not between 2 and 5
    """
    if num_players < 2 or num_players > 5:
        raise ValueError(f"Hanabi requires 2-5 players, got {num_players}")

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
        auto_end_when_no_points_possible=False  # Default: follow standard rules (game continues)
    )


class CommonView:
    """Common view of the game state visible to all players."""

    def __init__(
        self,
        live_tokens: int,
        hint_tokens: int,
        cards_to_draw: int,
        cards_discarded: Dict[Color, Suit],
        cards_played: Dict[Color, Number]
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

    @property
    def liveTokens(self) -> int:
        """Get the current number of live tokens."""
        return self._live_tokens

    @property
    def hintTokens(self) -> int:
        """Get the current number of hint tokens."""
        return self._hint_tokens

    @property
    def cardsToDraw(self) -> int:
        """Get the number of cards remaining to draw."""
        return self._cards_to_draw

    @property
    def cardsDiscarded(self) -> Dict[Color, Suit]:
        """Get the discarded cards mapping (Color -> Suit)."""
        return self._cards_discarded.copy()

    @property
    def cardsPlayed(self) -> Dict[Color, Number]:
        """Get the played cards mapping (Color -> Number)."""
        return self._cards_played.copy()

    def __repr__(self) -> str:
        return (f"CommonView(live={self._live_tokens}, "
                f"hint={self._hint_tokens}, "
                f"to_draw={self._cards_to_draw})")


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

    @property
    def teammates(self) -> Dict[int, Hand]:
        """Get the teammates' hands (player index -> Hand)."""
        return {k: Hand(v.cards) for k, v in self._teammates.items()}

    @property
    def ownHandSize(self) -> int:
        """Get the size of the player's own hand (cards are hidden)."""
        return self._own_hand_size

    def __repr__(self) -> str:
        return f"PlayerView(teammates={list(self._teammates.keys())}, own_hand_size={self._own_hand_size})"


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
        turns_left: Optional[int]
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

    @property
    def startPosition(self) -> StartPosition:
        """Get the starting position."""
        return self._start_position

    @property
    def commonView(self) -> CommonView:
        """Get the common view."""
        return self._common_view

    @property
    def playerHands(self) -> List[Hand]:
        """Get the list of player hands."""
        return [Hand(h.cards) for h in self._player_hands]

    @property
    def drawDeckIndex(self) -> int:
        """Get the current draw deck index."""
        return self._draw_deck_index

    @property
    def turnNumber(self) -> int:
        """Get the current turn number."""
        return self._turn_number

    @property
    def currentPlayer(self) -> int:
        """Get the current player index."""
        return self._current_player

    @property
    def turnsLeft(self) -> Optional[int]:
        """Get the number of turns left (None if deck not exhausted)."""
        return self._turns_left

    @property
    def settings(self) -> GameSettings:
        """Get the game settings."""
        return self._start_position.settings

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
        if self._turns_left == 0:
            return False

        # Delegate to specific validation methods
        if isinstance(move, CardMove):
            return self._validateCardMove(player_index, move)
        elif isinstance(move, Hint):
            return self._validateHint(player_index, move)
        else:
            return False

    def _validateCardMove(self, player_index: int, move: CardMove) -> bool:
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
            if self._common_view.hintTokens >= self.settings.maxHintTokens:
                return False

        # Play moves don't have additional validation here
        # (validity of the play itself is checked in _updatePlay)

        return True

    def _validateHint(self, player_index: int, move: Hint) -> bool:
        """
        Validate a hint move (ColorHint or NumberHint).

        Args:
            player_index: Index of the player making the move
            move: The hint move to validate

        Returns:
            True if the move is valid, False otherwise
        """
        # Check if hint tokens available
        if self._common_view.hintTokens <= 0:
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

        # Validate that the hint actually matches cards in the hand
        teammate_hand = self._player_hands[move.teammate]

        if isinstance(move, ColorHint):
            # Find all cards in the hand that match this color
            matching_indices = [
                idx for idx, card in enumerate(teammate_hand.cards)
                if card.color == move.color
            ]

            # Check that all card indices in the hint are valid and match the color
            for card_idx in move.cards:
                if card_idx < 0 or card_idx >= len(teammate_hand.cards):
                    return False
                if teammate_hand.cards[card_idx].color != move.color:
                    return False

            # CRITICAL RULE: A hint must include ALL matching cards in the hand
            # You cannot give a partial hint (e.g., hinting only 2 of 3 yellow cards)
            if set(move.cards) != set(matching_indices):
                return False

        elif isinstance(move, NumberHint):
            # Find all cards in the hand that match this number
            matching_indices = [
                idx for idx, card in enumerate(teammate_hand.cards)
                if card.number == move.number
            ]

            # Check that all card indices in the hint are valid and match the number
            for card_idx in move.cards:
                if card_idx < 0 or card_idx >= len(teammate_hand.cards):
                    return False
                if teammate_hand.cards[card_idx].number != move.number:
                    return False

            # CRITICAL RULE: A hint must include ALL matching cards in the hand
            # You cannot give a partial hint (e.g., hinting only 2 of 3 "1" cards)
            if set(move.cards) != set(matching_indices):
                return False

        return True

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

        # Add specific error details based on move type
        if isinstance(move, Discard):
            if self._common_view.hintTokens >= self.settings.maxHintTokens:
                error_msg += f" (hint tokens already at maximum: {self.settings.maxHintTokens})"
        elif isinstance(move, (ColorHint, NumberHint)):
            if self._common_view.hintTokens <= 0:
                error_msg += " (no hint tokens available)"
        elif isinstance(move, Play):
            if player_index != self._current_player:
                error_msg += f" (not player {player_index}'s turn, current player is {self._current_player})"

        return error_msg

    def update(
        self,
        player_index: int,
        move: Move
    ) -> None:
        """
        Update the game state in-place with a move.

        Args:
            player_index: Index of the player making the move
            move: The move to apply
        """
        assert 0 <= player_index < len(self._player_hands), \
            f"player_index {player_index} out of range [0, {len(self._player_hands)})"

        if isinstance(move, Play):
            self._updatePlay(player_index, move)
        elif isinstance(move, Discard):
            self._updateDiscard(player_index, move)
        elif isinstance(move, (ColorHint, NumberHint)):
            self._updateHint(player_index, move)
        else:
            assert False, f"Unknown move type: {type(move)}"

    def _updatePlay(
        self,
        player_index: int,
        move: Play
    ) -> None:
        """Update state for a play move (in-place)."""
        assert 0 <= player_index < len(self._player_hands), \
            f"player_index {player_index} out of range [0, {len(self._player_hands)})"
        hand = self._player_hands[player_index]
        assert 0 <= move.card < len(hand.cards), \
            f"card index {move.card} out of range [0, {len(hand.cards)})"
        card = hand.cards[move.card]

        # Check if card can be played
        cards_played = self._common_view.cardsPlayed
        expected_number = cards_played.get(card.color, Number.ONE)

        # Determine if valid play
        if card.color not in cards_played:
            is_valid = (card.number == Number.ONE)
        else:
            next_number_value = expected_number.value + 1
            is_valid = (card.number.value == next_number_value)

        if is_valid:
            self._playCard(player_index, move.card, card)
        else:
            self._handleInvalidPlay(player_index, move.card, card)

    def _playCard(
        self,
        player_index: int,
        card_index: int,
        card: Card
    ) -> None:
        """Play a card successfully (in-place update)."""
        assert 0 <= player_index < len(self._player_hands), \
            f"player_index {player_index} out of range [0, {len(self._player_hands)})"
        hand = self._player_hands[player_index]
        assert 0 <= card_index < len(hand.cards), \
            f"card_index {card_index} out of range [0, {len(hand.cards)})"
        assert hand.cards[card_index] == card, \
            f"Card at index {card_index} does not match provided card"

        # Remove card from hand
        new_hand_cards = hand.cards.copy()
        new_hand_cards.pop(card_index)

        # Update cards played
        previous_value = self._common_view._cards_played.get(card.color)
        self._common_view._cards_played[card.color] = card.number

        # Check if firework is completed
        firework_completed = (card.number == Number.FIVE and previous_value == Number.FOUR)

        # Standard Hanabi rule: gain a hint token when completing a firework,
        # but only if we are below the maximum. If we're already at max,
        # we simply don't gain an extra token (no assertion).
        if firework_completed and self._common_view._hint_tokens < self.settings.maxHintTokens:
            self._common_view._hint_tokens += 1

        # Draw a new card if available
        self._drawCardToHand(new_hand_cards)

        # Update player hands
        self._player_hands[player_index] = Hand(new_hand_cards)

    def _handleInvalidPlay(
        self,
        player_index: int,
        card_index: int,
        card: Card
    ) -> None:
        """Handle an invalid play (in-place update)."""
        assert 0 <= player_index < len(self._player_hands), \
            f"player_index {player_index} out of range [0, {len(self._player_hands)})"
        assert self._common_view._live_tokens > 0, \
            f"Cannot lose life token: already at 0"

        # Remove card, discard it, and draw new card (same as discard)
        self._removeCardAndDiscard(player_index, card_index, card)

        # Lose a life token (invalid play penalty)
        self._common_view._live_tokens -= 1

    def _updateDiscard(
        self,
        player_index: int,
        move: Discard
    ) -> None:
        """Update state for a discard move (in-place update)."""
        assert 0 <= player_index < len(self._player_hands), \
            f"player_index {player_index} out of range [0, {len(self._player_hands)})"
        # Assert that hint tokens are not already at max (should be validated before calling)
        assert self._common_view._hint_tokens < self.settings.maxHintTokens, \
            f"Cannot discard when hint tokens are already at maximum: {self._common_view._hint_tokens} >= {self.settings.maxHintTokens}"

        hand = self._player_hands[player_index]
        assert 0 <= move.card < len(hand.cards), \
            f"card index {move.card} out of range [0, {len(hand.cards)})"
        card = hand.cards[move.card]

        # Remove card, discard it, and draw new card
        self._removeCardAndDiscard(player_index, move.card, card)

        # Gain a hint token
        self._common_view._hint_tokens += 1

    def _removeCardAndDiscard(
        self,
        player_index: int,
        card_index: int,
        card: Card
    ) -> None:
        """Remove a card from hand, add to discard, and draw a new card (in-place update)."""
        assert 0 <= player_index < len(self._player_hands), \
            f"player_index {player_index} out of range [0, {len(self._player_hands)})"
        hand = self._player_hands[player_index]
        assert 0 <= card_index < len(hand.cards), \
            f"card_index {card_index} out of range [0, {len(hand.cards)})"
        assert hand.cards[card_index] == card, \
            f"Card at index {card_index} does not match provided card"

        # Remove card from hand and add to discard
        new_hand_cards = hand.cards.copy()
        new_hand_cards.pop(card_index)
        self._addCardToDiscardPile(card)

        # Draw a new card if available
        self._drawCardToHand(new_hand_cards)

        # Update player hands
        self._player_hands[player_index] = Hand(new_hand_cards)

    def _updateHint(
        self,
        player_index: int,
        move: Hint
    ) -> None:
        """Update state for a hint move (in-place update)."""
        assert 0 <= player_index < len(self._player_hands), \
            f"player_index {player_index} out of range [0, {len(self._player_hands)})"
        assert 0 <= move.teammate < len(self._player_hands), \
            f"teammate index {move.teammate} out of range [0, {len(self._player_hands)})"
        assert move.teammate != player_index, \
            f"Player {player_index} cannot hint themselves"
        # Assert that hint tokens are available
        assert self._common_view._hint_tokens > 0, \
            f"Cannot give hint: no hint tokens available (current: {self._common_view._hint_tokens})"

        # Check if deck is already exhausted (hints don't draw cards, so we need to check separately)
        self._checkAndSetTurnsLeftIfDeckExhausted()

        # Assert invariant: if deck is exhausted, turns_left must be set
        original_deck_size = len(self._start_position.drawDeck.cards)
        if self._draw_deck_index >= original_deck_size:
            assert self._turns_left is not None, \
                f"Deck is exhausted (draw_deck_index={self._draw_deck_index} >= {original_deck_size}) " \
                f"but turns_left is None after _checkAndSetTurnsLeftIfDeckExhausted in _updateHint"

        # Use a hint token
        self._common_view._hint_tokens -= 1

    def _checkAndSetTurnsLeftIfDeckExhausted(self) -> None:
        """
        Check if deck is exhausted and set turns_left if not already set.

        This is called from both _drawCardToHand (when drawing would exhaust deck)
        and _updateHint (when deck is already exhausted and a hint is given).
        """
        original_deck_size = len(self._start_position.drawDeck.cards)
        if self._draw_deck_index >= original_deck_size:
            # Deck exhausted - we want each player to take one more turn
            # The current player has just taken their turn (the one that exhausted the deck)
            # So we need numPlayers more turns (one for each player)
            # After advanceTurn() decrements it, we'll have numPlayers turns left
            if self._turns_left is None:
                # Set to numPlayers + 1 because:
                # - The current player has already taken their turn (exhausted deck)
                # - After this move, advanceTurn() will decrement to numPlayers
                # - This gives us exactly numPlayers more turns (one for each player)
                # - When it reaches 0, all players have taken their final turn
                self._turns_left = self.settings.numPlayers + 1
                logger.debug(f"[_checkAndSetTurnsLeftIfDeckExhausted] Deck exhausted! Set turns_left={self._turns_left} "
                            f"(numPlayers={self.settings.numPlayers})")
            else:
                logger.debug(f"[_checkAndSetTurnsLeftIfDeckExhausted] Deck exhausted but turns_left already set: {self._turns_left}")
            self._common_view._cards_to_draw = 0
            # Assert invariant: if deck is exhausted, turns_left must be set
            assert self._turns_left is not None, \
                f"Deck is exhausted (draw_deck_index={self._draw_deck_index} >= {original_deck_size}) but turns_left is None"
            assert self._turns_left > 0, \
                f"Deck is exhausted but turns_left is {self._turns_left} (should be > 0 when deck just exhausted)"

    def _drawCardToHand(self, hand_cards: List[Card]) -> None:
        """Draw a new card from the deck and add it to the hand (in-place update)."""
        original_deck_size = len(self._start_position.drawDeck.cards)
        assert 0 <= self._draw_deck_index <= original_deck_size, \
            f"draw_deck_index {self._draw_deck_index} out of range [0, {original_deck_size}]"

        logger.debug(f"[_drawCardToHand] draw_deck_index={self._draw_deck_index}, original_deck_size={original_deck_size}, "
                    f"turns_left={self._turns_left}, numPlayers={self.settings.numPlayers}")

        if self._draw_deck_index < original_deck_size:
            # Draw next card from original deck
            new_card = self._start_position.drawDeck.cards[self._draw_deck_index]
            hand_cards.insert(0, new_card)
            self._draw_deck_index += 1
            self._common_view._cards_to_draw = original_deck_size - self._draw_deck_index
            assert self._common_view._cards_to_draw >= 0, \
                f"cards_to_draw became negative: {self._common_view._cards_to_draw}"
            logger.debug(f"[_drawCardToHand] Drew card, new draw_deck_index={self._draw_deck_index}, "
                        f"cards_to_draw={self._common_view._cards_to_draw}")
            # Check if deck is now exhausted after drawing
            self._checkAndSetTurnsLeftIfDeckExhausted()
            # Assert invariant: if no cards to draw, turns_left must be set
            if self._common_view._cards_to_draw == 0:
                assert self._turns_left is not None, \
                    f"No cards to draw (cards_to_draw=0) but turns_left is None"
        else:
            # Deck already exhausted - just check and set turns_left if needed
            self._checkAndSetTurnsLeftIfDeckExhausted()
            # Assert invariant: if deck is exhausted, turns_left must be set
            assert self._turns_left is not None, \
                f"Deck is exhausted (draw_deck_index={self._draw_deck_index} >= {original_deck_size}) but turns_left is None"

    def _addCardToDiscardPile(self, card: Card) -> None:
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

    def isFinished(self) -> bool:
        """
        Check if the game is finished.

        Returns:
            True if the game is finished, False otherwise
        """
        logger.debug(f"[isFinished] Checking game end conditions: liveTokens={self._common_view.liveTokens}, "
                    f"turns_left={self._turns_left}, turn_number={self._turn_number}, "
                    f"current_player={self._current_player}")

        # 1. All life tokens are lost
        if self._common_view.liveTokens <= 0:
            logger.debug("[isFinished] Game finished: All life tokens lost")
            return True

        # 2. All fireworks are completed (perfect score)
        cards_played = self._common_view.cardsPlayed
        if len(cards_played) == 5:  # All 5 colors
            all_fives = all(num == Number.FIVE for num in cards_played.values())
            if all_fives:
                logger.debug("[isFinished] Game finished: All fireworks completed (perfect score)")
                return True

        # 3. Deck is exhausted and all players have taken final turn
        # Assert invariant: if deck is exhausted (no cards to draw), turns_left must be set
        original_deck_size = len(self._start_position.drawDeck.cards)
        if self._draw_deck_index >= original_deck_size:
            assert self._turns_left is not None, \
                f"Deck is exhausted (draw_deck_index={self._draw_deck_index} >= {original_deck_size}, " \
                f"cards_to_draw={self._common_view._cards_to_draw}) but turns_left is None"
        if self._turns_left == 0:
            logger.debug(f"[isFinished] Game finished: turns_left == 0 (deck exhausted, all players took final turn)")
            return True

        # 4. Auto-end when no more points possible (if setting enabled)
        if self.settings.autoEndWhenNoPointsPossible:
            if self._isNoMorePointsPossible():
                logger.debug("[isFinished] Game finished: No more points possible")
                return True

        logger.debug("[isFinished] Game not finished")
        return False

    def _isNoMorePointsPossible(self) -> bool:
        """Check if no more points are possible based on discarded cards."""
        cards_played = self._common_view.cardsPlayed
        cards_discarded = self._common_view.cardsDiscarded

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

    def score(self) -> int:
        """
        Calculate the game score.

        Returns:
            The current game score
        """
        cards_played = self._common_view.cardsPlayed
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
        assert 0 <= self._current_player < num_players, \
            f"current_player {self._current_player} out of range [0, {num_players})"

        old_player = self._current_player
        self._current_player = (self._current_player + 1) % num_players
        logger.debug(f"[advance_player] Player {old_player} -> {self._current_player}, "
                    f"turns_left={self._turns_left}")

        # If deck is exhausted, decrement turns remaining
        # Assert invariant: if deck is exhausted, turns_left must be set
        original_deck_size = len(self._start_position.drawDeck.cards)
        if self._draw_deck_index >= original_deck_size:
            assert self._turns_left is not None, \
                f"Deck is exhausted (draw_deck_index={self._draw_deck_index} >= {original_deck_size}) " \
                f"but turns_left is None in advance_player"

        if self._turns_left is not None:
            assert self._turns_left > 0, \
                f"turns_left should be > 0 when deck is exhausted, got {self._turns_left}"
            old_turns_left = self._turns_left
            self._turns_left -= 1
            assert self._turns_left >= 0, \
                f"turns_left became negative: {self._turns_left}"
            logger.debug(f"[advance_player] Decremented turns_left: {old_turns_left} -> {self._turns_left}")
        else:
            logger.debug(f"[advance_player] turns_left is None (deck not exhausted)")

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
            cards_played=self._common_view._cards_played
        )

        return GameState(
            start_position=self._start_position,
            common_view=new_common_view,
            player_hands=self._player_hands,
            draw_deck_index=self._draw_deck_index,
            turn_number=self._turn_number,
            current_player=self._current_player,
            turns_left=self._turns_left
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
            turns_left=self._turns_left
        )

    def __repr__(self) -> str:
        return f"GameState(draw_deck_index={self._draw_deck_index})"


class Game:
    """Represents a single game instance and drives the game loop."""

    def __init__(
        self,
        start_position: StartPosition,
        team: PlayerTeam,
        on_move: Optional[Callable[[int, Move, GameState, GameState], None]] = None
    ):
        """
        Initialize a game.

        Args:
            start_position: The starting position (settings and initial deck)
            team: The team of players (players are also observers)
            on_move: Optional callback(player_index, move, old_state, new_state) called after
                     each move is processed. Use for display updates, logging, etc.
        """
        self._start_position = start_position
        self._team = team
        self._on_move: Optional[Callable[[int, Move, GameState, GameState], None]] = on_move
        self._turns: List[GameState] = []

        # Initialize players with game settings
        self._initialize_players()

    @property
    def team(self) -> PlayerTeam:
        """Get the player team."""
        return self._team

    @property
    def state(self) -> GameState:
        """Get the current game state (most recent turn)."""
        if not self._turns:
            raise ValueError("Game not initialized. No turns yet.")
        return self._turns[-1]

    @property
    def settings(self) -> GameSettings:
        """Get the game settings."""
        return self._start_position.settings

    @property
    def currentPlayer(self) -> int:
        """Get the current player index."""
        assert self._turns, "Game not initialized. No turns yet."
        return self.state.currentPlayer

    def _initialize_players(self) -> None:
        """Initialize players with game settings."""
        assert len(self._team.players) == self.settings.numPlayers, \
            f"Number of players ({len(self._team.players)}) does not match settings ({self.settings.numPlayers})"
        # Set game settings for all players (they are BasePlayer instances and observe all moves)
        for player in self._team.players:
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
        # Set common view - players need the current state's commonView
        # Note: Each GameState has its own CommonView, so we must update players' references
        # after each state transition to ensure they see current values
        common_view = self.state.commonView
        for player in self._team.players:
            player.set_common_view(common_view)

    def _notify_players(self, player_index: int, move: Move) -> None:
        """Notify all players about a move (all players observe all moves)."""
        for player in self._team.players:
            player.observe(player_index, move)

    def _getPlayerView(self, player_index: int) -> PlayerView:
        """
        Get the view of the game from a player's perspective (private).

        Args:
            player_index: Index of the player

        Returns:
            PlayerView showing teammates' hands and own hand size
        """
        assert self._turns, "Game not initialized. No turns yet."
        assert 0 <= player_index < len(self._team.players), \
            f"player_index {player_index} out of range [0, {len(self._team.players)})"

        teammates: Dict[int, Hand] = {}
        for i, hand in enumerate(self.state.playerHands):
            if i != player_index:
                teammates[i] = hand

        own_hand_size = len(self.state.playerHands[player_index].cards)
        return PlayerView(teammates, own_hand_size)

    def _processMove(self, player_index: int, move: Move) -> None:
        """
        Process a move and update the game state.

        Args:
            player_index: Index of the player making the move
            move: The move to process

        Raises:
            ValueError: If the move is invalid or game state is invalid
        """
        assert self._turns, "Game not initialized. No turns yet."
        assert 0 <= player_index < len(self._team.players), \
            f"player_index {player_index} out of range [0, {len(self._team.players)})"

        current_state = self.state
        logger.debug(f"[processMove] Processing move: player={player_index}, move={move}, "
                    f"turn_number={current_state.turnNumber}, current_player={current_state.currentPlayer}, "
                    f"turns_left={current_state.turnsLeft}, cards_to_draw={current_state.commonView.cardsToDraw}")

        # Validate the move (GameState now has all the state it needs)
        if not self.state._validate(player_index, move):
            error_msg = self.state._get_validation_error_message(player_index, move)
            raise ValueError(error_msg)

        # Clone the current state and update it in-place
        new_state = copy.copy(current_state)
        new_state._turn_number += 1  # Increment turn number (0-based)
        logger.debug(f"[processMove] After cloning: new turn_number={new_state._turn_number}")

        # Update the cloned state in-place
        new_state.update(player_index, move)
        logger.debug(f"[processMove] After update: turn_number={new_state._turn_number}, "
                    f"current_player={new_state.currentPlayer}, turns_left={new_state.turnsLeft}, "
                    f"cards_to_draw={new_state.commonView.cardsToDraw}, "
                    f"isFinished={new_state.isFinished()}")

        # Add new state to turns history
        self._turns.append(new_state)

        # Update players' commonView references to point to the new state's commonView
        # This is critical because GameState.__copy__ creates a new CommonView object
        # Players need to see the updated commonView from the current state
        self._set_common_view_for_players()

        # Notify players about the move BEFORE the callback
        # This ensures hints are updated before display is refreshed
        self._notify_players(player_index, move)

        # Notify global callback with old and new state (for display, logging, etc.)
        if self._on_move is not None:
            self._on_move(player_index, move, current_state, new_state)

    def _advanceTurn(self) -> None:
        """Advance to the next player's turn (internal method)."""
        assert self._turns, "Cannot advance turn: no turns yet"
        num_players = self.settings.numPlayers
        assert num_players > 0, f"num_players must be positive, got {num_players}"
        last_state = self._turns[-1]
        logger.debug(f"[_advanceTurn] Before advance: current_player={last_state.currentPlayer}, "
                    f"turns_left={last_state.turnsLeft}, turn_number={last_state.turnNumber}")
        last_state.advance_player(num_players)
        logger.debug(f"[_advanceTurn] After advance: current_player={last_state.currentPlayer}, "
                    f"turns_left={last_state.turnsLeft}, turn_number={last_state.turnNumber}, "
                    f"isFinished={last_state.isFinished()}")

    @property
    def isFinished(self) -> bool:
        """Check if the game is finished."""
        assert self._turns, "Game not initialized. No turns yet."
        return self.state.isFinished()

    def getScore(self) -> int:
        """Calculate the current game score."""
        assert self._turns, "Game not initialized. No turns yet."
        return self.state.score()

    def play(self) -> None:
        """
        Play the game - drives the game loop.

        This method calls players' play() method to get moves and
        notifies observers about moves made.
        """
        assert self._turns, "Game not initialized. No turns yet."
        while not self.isFinished:
            current_player = self.state.currentPlayer
            player = self._team.players[current_player]

            # Get player view
            player_view = self._getPlayerView(current_player)

            # Get move from player
            # Let AssertionError propagate (fail fast on bugs)
            # Only catch ValueError for invalid moves (game logic, not bugs)
            try:
                move = player.play(player_view)
            except ValueError as e:
                # Invalid move from player - end game with error
                raise RuntimeError(f"Player {current_player} failed to provide a move: {e}") from e

            # Process the move (raises ValueError if invalid)
            # Note: _processMove now calls _notify_players internally before the callback
            try:
                self._processMove(current_player, move)
            except ValueError as e:
                # Invalid move - end game with error
                raise RuntimeError(f"Game ended due to invalid move: {e}") from e

            # Advance turn
            self._advanceTurn()

    @staticmethod
    def create(
        team: PlayerTeam,
        settings: GameSettings,
        on_move: Optional[Callable[[int, Move, GameState, GameState], None]] = None
    ) -> Game:
        """
        Create and initialize a new game.

        Args:
            team: The team of players (players are also observers)
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
        num_players = settings.numPlayers
        cards_per_player = settings.maxCardsInHand
        player_hands: List[Hand] = []
        draw_deck_index = 0
        deck_cards = original_deck.cards

        # Assert we have enough cards to deal
        required_cards = num_players * cards_per_player
        assert len(deck_cards) >= required_cards, \
            f"Not enough cards in deck: need {required_cards}, have {len(deck_cards)}"

        for player_idx in range(num_players):
            hand_cards: List[Card] = []
            for _ in range(cards_per_player):
                assert draw_deck_index < len(deck_cards), \
                    f"Ran out of cards while dealing to player {player_idx}"
                hand_cards.append(deck_cards[draw_deck_index])
                draw_deck_index += 1
            player_hands.append(Hand(hand_cards))

        # Initialize common view
        # cards_to_draw should be remaining cards after dealing
        remaining_cards = len(deck_cards) - draw_deck_index
        common_view = CommonView(
            live_tokens=settings.maxLiveTokens,
            hint_tokens=settings.maxHintTokens,
            cards_to_draw=remaining_cards,
            cards_discarded={},
            cards_played={}
        )

        # Initialize game state (turn 0, player 0 starts, no turns left yet)
        state = GameState(
            start_position=start_position,
            common_view=common_view,
            player_hands=player_hands,
            draw_deck_index=draw_deck_index,
            turn_number=0,
            current_player=0,
            turns_left=None
        )

        # Create game instance
        game = Game(start_position, team, on_move)

        # Add initial state to turns
        game._turns.append(state)

        # Set common view for all players (they share the same reference, so updates are automatic)
        game._set_common_view_for_players()

        return game

    def __repr__(self) -> str:
        if not self._turns:
            return f"Game(team={self._team.name()}, turns=0)"
        return f"Game(team={self._team.name()}, turns={len(self._turns)})"


