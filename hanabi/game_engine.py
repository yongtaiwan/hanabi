"""
Game engine for managing Hanabi game logic and state.
"""

import random
from typing import List, Dict, Optional, Tuple
from .enums import Color, Number
from .card import Card, Suit
from .game import GameSettings, CommonView, GameState, Hand, PlayerView
from .moves import Move, Play, Discard, ColorHint, NumberHint


class GameEngine:
    """Manages the game logic and state for a Hanabi game."""
    
    def __init__(self, settings: GameSettings, players: List):
        """
        Initialize the game engine.
        
        Args:
            settings: Game settings
            players: List of player objects
        """
        self._settings = settings
        self._players = players
        self._draw_deck: List[Card] = []
        self._discard_pile: List[Card] = []
        self._game_state: Optional[GameState] = None
        self._current_player = 0
        self._deck_exhausted = False
        self._final_turns_remaining: Dict[int, bool] = {}
        # Track hints for each player: {player_index: {card_index: {color: bool, number: bool}}}
        self._player_hints: Dict[int, Dict[int, Dict[str, bool]]] = {}
        # Track move history: list of (player, move, result)
        self._move_history: List[Tuple[int, Move, str]] = []
        # Track last turn index for each player (to show only moves since their last turn)
        self._last_turn_index: Dict[int, int] = {}
        
    def initialize(self) -> None:
        """Initialize the game: create deck, shuffle, deal cards."""
        # Initialize last turn index for all players
        for i in range(self._settings.numPlayers):
            self._last_turn_index[i] = -1  # -1 means before first turn
        
        # Create the deck from settings
        self._draw_deck = []
        for color, suit in self._settings.cards.items():
            for number, quantity in suit.cards.items():
                for _ in range(quantity):
                    self._draw_deck.append(Card(color, number))
        
        # Shuffle the deck
        random.shuffle(self._draw_deck)
        
        # Deal cards to players
        num_players = self._settings.numPlayers
        cards_per_player = self._settings.maxCardsInHand
        player_hands: List[Hand] = []
        
        for player_idx in range(num_players):
            hand_cards: List[Card] = []
            for _ in range(cards_per_player):
                if self._draw_deck:
                    hand_cards.append(self._draw_deck.pop(0))
            player_hands.append(Hand(hand_cards))
        
        # Initialize common view
        common_view = CommonView(
            live_tokens=self._settings.maxLiveTokens,
            hint_tokens=self._settings.maxHintTokens,
            cards_to_draw=len(self._draw_deck),
            cards_discarded={},
            cards_played={}
        )
        
        # Initialize game state
        self._game_state = GameState(
            common_view=common_view,
            player_hands=player_hands,
            draw_deck_index=0
        )
        
        # Initialize final turns tracking
        # When deck is exhausted, all players get one final turn
        # Initially, no one needs a final turn (deck not exhausted yet)
        for i in range(num_players):
            self._final_turns_remaining[i] = False
            # Initialize hint tracking for each player (empty initially)
            self._player_hints[i] = {}
    
    @property
    def gameState(self) -> GameState:
        """Get the current game state."""
        if self._game_state is None:
            raise ValueError("Game not initialized. Call initialize() first.")
        return self._game_state
    
    @property
    def currentPlayer(self) -> int:
        """Get the current player index."""
        return self._current_player
    
    @property
    def settings(self) -> GameSettings:
        """Get the game settings."""
        return self._settings
    
    def getPlayerView(self, player_index: int) -> PlayerView:
        """
        Get the view of the game from a player's perspective.
        
        Args:
            player_index: Index of the player
            
        Returns:
            PlayerView showing teammates' hands
        """
        if self._game_state is None:
            raise ValueError("Game not initialized.")
        
        teammates: Dict[int, Hand] = {}
        for i, hand in enumerate(self._game_state.playerHands):
            if i != player_index:
                teammates[i] = hand
        
        return PlayerView(teammates)
    
    def processMove(self, player_index: int, move: Move) -> Tuple[bool, str]:
        """
        Process a move and update the game state.
        
        Args:
            player_index: Index of the player making the move
            move: The move to process
            
        Returns:
            Tuple of (success, message)
        """
        if self._game_state is None:
            raise ValueError("Game not initialized.")
        
        if player_index != self._current_player:
            return False, f"Not player {player_index}'s turn. Current player: {self._current_player}"
        
        # Validate the move
        if not self._validateMove(player_index, move):
            # Provide more specific error message
            if isinstance(move, Discard):
                if self._game_state.commonView.hintTokens >= self._settings.maxHintTokens:
                    return False, f"Cannot discard: hint tokens are already at maximum ({self._settings.maxHintTokens}/{self._settings.maxHintTokens})"
            return False, "Invalid move"
        
        # Process the move
        if isinstance(move, Play):
            result = self._processPlay(player_index, move)
        elif isinstance(move, Discard):
            result = self._processDiscard(player_index, move)
        elif isinstance(move, ColorHint):
            result = self._processColorHint(player_index, move)
        elif isinstance(move, NumberHint):
            result = self._processNumberHint(player_index, move)
        else:
            return False, f"Unknown move type: {type(move)}"
        
        # Record move in history
        if result[0]:  # If successful
            self._move_history.append((player_index, move, result[1]))
        
        return result
    
    def _validateMove(self, player_index: int, move: Move) -> bool:
        """Validate a move."""
        if self._game_state is None:
            return False
        
        state = self._game_state
        common_view = state.commonView
        
        if isinstance(move, Play):
            hand = state.playerHands[player_index]
            if move.card < 0 or move.card >= len(hand.cards):
                return False
        
        elif isinstance(move, Discard):
            hand = state.playerHands[player_index]
            if move.card < 0 or move.card >= len(hand.cards):
                return False
            # Cannot discard if hint tokens are already at maximum
            # (Discarding gains a hint token, so it's not allowed when at max)
            if common_view.hintTokens >= self._settings.maxHintTokens:
                return False
        
        elif isinstance(move, (ColorHint, NumberHint)):
            # Check if hint tokens available
            if common_view.hintTokens <= 0:
                return False
            # Check if teammate index is valid
            if move.teammate < 0 or move.teammate >= len(state.playerHands):
                return False
            if move.teammate == player_index:
                return False  # Can't hint yourself
            # Check if hint has matching cards
            if not move.cards:
                return False
        
        return True
    
    def _processPlay(self, player_index: int, move: Play) -> Tuple[bool, str]:
        """Process a play move."""
        state = self._game_state
        hand = state.playerHands[player_index]
        card = hand.cards[move.card]
        
        # Check if card can be played
        cards_played = state.commonView.cardsPlayed
        expected_number = cards_played.get(card.color, Number.ONE)
        
        # If no card of this color has been played, we need a 1
        if card.color not in cards_played:
            if card.number == Number.ONE:
                # Valid play
                bonus_msg = self._playCard(player_index, move.card, card)
                return True, f"Successfully played {card}!{bonus_msg}"
            else:
                # Invalid play - lose a life token
                return self._handleInvalidPlay(player_index, move.card, card)
        else:
            # Check if this is the next number
            next_number_value = expected_number.value + 1
            if card.number.value == next_number_value:
                # Valid play
                bonus_msg = self._playCard(player_index, move.card, card)
                return True, f"Successfully played {card}!{bonus_msg}"
            else:
                # Invalid play - lose a life token
                return self._handleInvalidPlay(player_index, move.card, card)
    
    def _playCard(self, player_index: int, card_index: int, card: Card) -> str:
        """
        Play a card successfully.
        
        Returns:
            Bonus message if firework was completed, empty string otherwise.
        """
        state = self._game_state
        hand = state.playerHands[player_index]
        
        # Remove card from hand
        new_hand_cards = hand.cards.copy()
        new_hand_cards.pop(card_index)
        # Remove hints for this card
        self._removeCardHints(player_index, card_index)
        
        # Update cards played
        new_cards_played = state.commonView.cardsPlayed.copy()
        previous_value = new_cards_played.get(card.color)
        new_cards_played[card.color] = card.number
        
        # Check if firework is completed (playing a 5 completes the firework)
        # BONUS: When a firework is completed, return a blue hint token to the table
        # Per rules: "When a player completes a firework—i.e. he successfully plays 
        # the card with a value of 5—move a blue token from the lid back to the table."
        firework_completed = (card.number == Number.FIVE and previous_value == Number.FOUR)
        new_hint_tokens = state.commonView.hintTokens
        bonus_message = ""
        
        if firework_completed:
            # Return a hint token (but don't exceed max)
            if new_hint_tokens < self._settings.maxHintTokens:
                new_hint_tokens += 1
                bonus_message = f" Firework completed! Bonus hint token returned. ({new_hint_tokens}/{self._settings.maxHintTokens})"
            # Note: Bonus is lost if all hint tokens are already on the table (per rules)
        
        # Draw a new card if available (add to leftmost position)
        if self._draw_deck:
            new_hand_cards.insert(0, self._draw_deck.pop(0))
            # Shift hints for remaining cards and add new card with no hints
            self._shiftHintsAfterCardRemoval(player_index, card_index, True)
        else:
            # Deck is now exhausted - mark that this player has taken their final turn
            if not self._deck_exhausted:
                # First time deck is exhausted - all players get one final turn
                self._deck_exhausted = True
                for i in range(self._settings.numPlayers):
                    self._final_turns_remaining[i] = True
            # Mark this player as having taken their final turn
            self._final_turns_remaining[player_index] = False
        
        # Update common view
        new_common_view = CommonView(
            live_tokens=state.commonView.liveTokens,
            hint_tokens=new_hint_tokens,
            cards_to_draw=len(self._draw_deck),
            cards_discarded=state.commonView.cardsDiscarded,
            cards_played=new_cards_played
        )
        
        # Update player hands
        new_player_hands = state.playerHands.copy()
        new_player_hands[player_index] = Hand(new_hand_cards)
        
        # Create new game state
        self._game_state = GameState(
            common_view=new_common_view,
            player_hands=new_player_hands,
            draw_deck_index=state.drawDeckIndex
        )
        
        return bonus_message
    
    def _handleInvalidPlay(self, player_index: int, card_index: int, card: Card) -> Tuple[bool, str]:
        """Handle an invalid play (card is discarded, lose a life token)."""
        state = self._game_state
        hand = state.playerHands[player_index]
        
        # Remove card from hand and add to discard
        new_hand_cards = hand.cards.copy()
        new_hand_cards.pop(card_index)
        self._discard_pile.append(card)
        # Remove hints for this card
        self._removeCardHints(player_index, card_index)
        
        # Update discard pile in common view
        new_discarded = self._updateDiscardPile()
        
        # Lose a life token
        new_live_tokens = state.commonView.liveTokens - 1
        
        # Draw a new card if available (add to leftmost position)
        if self._draw_deck:
            new_hand_cards.insert(0, self._draw_deck.pop(0))
            # Shift hints for remaining cards
            self._shiftHintsAfterCardRemoval(player_index, card_index, True)
        else:
            # Deck is now exhausted - mark that this player has taken their final turn
            if not self._deck_exhausted:
                # First time deck is exhausted - all players get one final turn
                self._deck_exhausted = True
                for i in range(self._settings.numPlayers):
                    self._final_turns_remaining[i] = True
            # Mark this player as having taken their final turn
            self._final_turns_remaining[player_index] = False
        
        # Update common view
        new_common_view = CommonView(
            live_tokens=new_live_tokens,
            hint_tokens=state.commonView.hintTokens,
            cards_to_draw=len(self._draw_deck),
            cards_discarded=new_discarded,
            cards_played=state.commonView.cardsPlayed
        )
        
        # Update player hands
        new_player_hands = state.playerHands.copy()
        new_player_hands[player_index] = Hand(new_hand_cards)
        
        # Create new game state
        self._game_state = GameState(
            common_view=new_common_view,
            player_hands=new_player_hands,
            draw_deck_index=state.drawDeckIndex
        )
        
        return True, f"Invalid play! {card} was discarded. Lost a life token. Lives remaining: {new_live_tokens}"
    
    def _processDiscard(self, player_index: int, move: Discard) -> Tuple[bool, str]:
        """Process a discard move."""
        state = self._game_state
        hand = state.playerHands[player_index]
        card = hand.cards[move.card]
        
        # Remove card from hand and add to discard
        new_hand_cards = hand.cards.copy()
        new_hand_cards.pop(move.card)
        self._discard_pile.append(card)
        # Remove hints for this card
        self._removeCardHints(player_index, move.card)
        
        # Update discard pile
        new_discarded = self._updateDiscardPile()
        
        # Gain a hint token (up to max)
        new_hint_tokens = min(
            state.commonView.hintTokens + 1,
            self._settings.maxHintTokens
        )
        
        # Draw a new card if available (add to leftmost position)
        if self._draw_deck:
            new_hand_cards.insert(0, self._draw_deck.pop(0))
            # Shift hints for remaining cards and add new card with no hints
            self._shiftHintsAfterCardRemoval(player_index, move.card, True)
        else:
            # Deck is now exhausted - mark that this player has taken their final turn
            if not self._deck_exhausted:
                # First time deck is exhausted - all players get one final turn
                self._deck_exhausted = True
                for i in range(self._settings.numPlayers):
                    self._final_turns_remaining[i] = True
            # Mark this player as having taken their final turn
            self._final_turns_remaining[player_index] = False
        
        # Update common view
        new_common_view = CommonView(
            live_tokens=state.commonView.liveTokens,
            hint_tokens=new_hint_tokens,
            cards_to_draw=len(self._draw_deck),
            cards_discarded=new_discarded,
            cards_played=state.commonView.cardsPlayed
        )
        
        # Update player hands
        new_player_hands = state.playerHands.copy()
        new_player_hands[player_index] = Hand(new_hand_cards)
        
        # Create new game state
        self._game_state = GameState(
            common_view=new_common_view,
            player_hands=new_player_hands,
            draw_deck_index=state.drawDeckIndex
        )
        
        return True, f"Discarded {card}. Hint tokens: {new_hint_tokens}"
    
    def _processColorHint(self, player_index: int, move: ColorHint) -> Tuple[bool, str]:
        """Process a color hint move."""
        state = self._game_state
        teammate_hand = state.playerHands[move.teammate]
        
        # Record hints for the teammate
        # IMPORTANT: Merge hints - preserve existing hints when adding new ones
        # Ensure hints dict exists for this teammate
        if move.teammate not in self._player_hints:
            self._player_hints[move.teammate] = {}
        
        for card_idx in move.cards:
            # Validate card index is within bounds
            if card_idx >= len(teammate_hand.cards):
                # This should not happen if hint was created correctly, but handle gracefully
                continue
            
            # Initialize hint entry if it doesn't exist, or ensure it has both keys
            if card_idx not in self._player_hints[move.teammate]:
                self._player_hints[move.teammate][card_idx] = {"color": None, "number": None}
            else:
                # Ensure both keys exist (in case hint dict was corrupted or incomplete)
                if "color" not in self._player_hints[move.teammate][card_idx]:
                    self._player_hints[move.teammate][card_idx]["color"] = None
                if "number" not in self._player_hints[move.teammate][card_idx]:
                    self._player_hints[move.teammate][card_idx]["number"] = None
            
            # Merge: update in place to preserve existing number hint
            # This ensures both color and number hints are preserved
            self._player_hints[move.teammate][card_idx]["color"] = move.color
            # Number hint is preserved automatically since we're updating in place
        
        # Use a hint token
        new_hint_tokens = state.commonView.hintTokens - 1
        
        # Update common view
        new_common_view = CommonView(
            live_tokens=state.commonView.liveTokens,
            hint_tokens=new_hint_tokens,
            cards_to_draw=state.commonView.cardsToDraw,
            cards_discarded=state.commonView.cardsDiscarded,
            cards_played=state.commonView.cardsPlayed
        )
        
        # Create new game state (hands don't change)
        self._game_state = GameState(
            common_view=new_common_view,
            player_hands=state.playerHands,
            draw_deck_index=state.drawDeckIndex
        )
        
        # If deck is exhausted, mark that this player has taken their final turn
        # Per rules: when deck is empty, each player gets exactly one more turn
        if self._deck_exhausted:
            self._final_turns_remaining[player_index] = False
        
        # Convert to 1-based indices for display (UI uses 1-5, not 0-4)
        card_indices = ", ".join(str(c + 1) for c in move.cards)
        return True, f"Gave color hint to player {move.teammate + 1}: {move.color.name} (cards at indices: {card_indices}). Hint tokens: {new_hint_tokens}"
    
    def _processNumberHint(self, player_index: int, move: NumberHint) -> Tuple[bool, str]:
        """Process a number hint move."""
        state = self._game_state
        teammate_hand = state.playerHands[move.teammate]
        
        # Record hints for the teammate
        # IMPORTANT: Merge hints - preserve existing hints when adding new ones
        for card_idx in move.cards:
            if card_idx < len(teammate_hand.cards):
                if move.teammate not in self._player_hints:
                    self._player_hints[move.teammate] = {}
                if card_idx not in self._player_hints[move.teammate]:
                    self._player_hints[move.teammate][card_idx] = {"color": None, "number": None}
                else:
                    # Ensure both keys exist (in case hint dict was corrupted or incomplete)
                    if "color" not in self._player_hints[move.teammate][card_idx]:
                        self._player_hints[move.teammate][card_idx]["color"] = None
                    if "number" not in self._player_hints[move.teammate][card_idx]:
                        self._player_hints[move.teammate][card_idx]["number"] = None
                # Merge: update in place to preserve existing color hint
                self._player_hints[move.teammate][card_idx]["number"] = move.number
                # Color hint is preserved automatically since we're updating in place
        
        # Use a hint token
        new_hint_tokens = state.commonView.hintTokens - 1
        
        # Update common view
        new_common_view = CommonView(
            live_tokens=state.commonView.liveTokens,
            hint_tokens=new_hint_tokens,
            cards_to_draw=state.commonView.cardsToDraw,
            cards_discarded=state.commonView.cardsDiscarded,
            cards_played=state.commonView.cardsPlayed
        )
        
        # Create new game state (hands don't change)
        self._game_state = GameState(
            common_view=new_common_view,
            player_hands=state.playerHands,
            draw_deck_index=state.drawDeckIndex
        )
        
        # If deck is exhausted, mark that this player has taken their final turn
        # Per rules: when deck is empty, each player gets exactly one more turn
        if self._deck_exhausted:
            self._final_turns_remaining[player_index] = False
        
        # Convert to 1-based indices for display (UI uses 1-5, not 0-4)
        card_indices = ", ".join(str(c + 1) for c in move.cards)
        return True, f"Gave number hint to player {move.teammate + 1}: {move.number.value} (cards at indices: {card_indices}). Hint tokens: {new_hint_tokens}"
    
    def _updateDiscardPile(self) -> Dict[Color, Suit]:
        """Update the discard pile representation in common view."""
        discarded: Dict[Color, Dict[Number, int]] = {}
        
        for card in self._discard_pile:
            if card.color not in discarded:
                discarded[card.color] = {}
            if card.number not in discarded[card.color]:
                discarded[card.color][card.number] = 0
            discarded[card.color][card.number] += 1
        
        # Convert to Suit objects
        result: Dict[Color, Suit] = {}
        for color, numbers in discarded.items():
            result[color] = Suit(numbers)
        
        return result
    
    def advanceTurn(self) -> None:
        """Advance to the next player's turn."""
        # Update last turn index for the current player before advancing
        current_turn_index = len(self._move_history)
        self._last_turn_index[self._current_player] = current_turn_index
        
        if self._deck_exhausted:
            # Check if all players have taken their final turn
            # When deck is exhausted, final_turns_remaining[player] = True means they still need to take their turn
            # When they take it, we set it to False
            if all(not self._final_turns_remaining.get(i, False) for i in range(self._settings.numPlayers)):
                return  # Game will end - all players have taken their final turn
            # Otherwise, advance to next player who still needs to take their final turn
            num_players = self._settings.numPlayers
            for _ in range(num_players):
                self._current_player = (self._current_player + 1) % num_players
                if self._final_turns_remaining.get(self._current_player, False):
                    return  # This player still needs their final turn
        else:
            num_players = self._settings.numPlayers
            self._current_player = (self._current_player + 1) % num_players
    
    def isFinished(self) -> bool:
        """Check if the game is finished."""
        if self._game_state is None:
            return False
        
        # Game ends if:
        # 1. All life tokens are lost
        if self._game_state.commonView.liveTokens <= 0:
            return True
        
        # 2. All fireworks are completed (perfect score)
        cards_played = self._game_state.commonView.cardsPlayed
        if len(cards_played) == 5:  # All 5 colors
            all_fives = all(num == Number.FIVE for num in cards_played.values())
            if all_fives:
                return True
        
        # 3. Deck is exhausted and all players have taken final turn
        if self._deck_exhausted:
            # All players have taken their final turn if all are False
            if all(not self._final_turns_remaining.get(i, False) for i in range(self._settings.numPlayers)):
                return True
        
        # 4. Auto-end when no more points possible (if setting enabled)
        if self._settings.autoEndWhenNoPointsPossible:
            if self.isNoMorePointsPossible():
                return True
        
        return False
    
    def getScore(self) -> int:
        """Calculate the current game score."""
        if self._game_state is None:
            return 0
        
        cards_played = self._game_state.commonView.cardsPlayed
        score = 0
        for number in cards_played.values():
            score += number.value
        
        return score
    
    def isDeckExhausted(self) -> bool:
        """Check if the draw deck is exhausted."""
        return self._deck_exhausted
    
    def hasFinalTurnRemaining(self, player_index: int) -> bool:
        """Check if a player still has their final turn remaining."""
        return self._final_turns_remaining.get(player_index, False)
    
    def isNoMorePointsPossible(self) -> bool:
        """
        Check if no more points are possible based on discarded cards.
        
        A color can't progress if all copies of the next needed card are discarded.
        If all colors can't progress, no more points are possible.
        
        Returns:
            True if no more points are possible, False otherwise
        """
        if self._game_state is None:
            return False
        
        cards_played = self._game_state.commonView.cardsPlayed
        discard_pile = self._discard_pile
        
        # Count discarded cards by color and number
        discarded_counts: Dict[Color, Dict[Number, int]] = {}
        for card in discard_pile:
            if card.color not in discarded_counts:
                discarded_counts[card.color] = {}
            discarded_counts[card.color][card.number] = discarded_counts[card.color].get(card.number, 0) + 1
        
        # Check each color
        for color in [Color.WHITE, Color.RED, Color.YELLOW, Color.GREEN, Color.BLUE]:
            # Determine next card needed for this color
            if color in cards_played:
                current_highest = cards_played[color]
                if current_highest == Number.FIVE:
                    continue  # This color is complete, can't gain more points
                next_needed = Number(current_highest.value + 1)
            else:
                next_needed = Number.ONE  # Need to start with 1
            
            # Get total count of this card from settings
            suit = self._settings.cards.get(color)
            if suit is None:
                continue
            total_count = suit.cards.get(next_needed, 0)
            
            # Count how many are discarded
            discarded_count = discarded_counts.get(color, {}).get(next_needed, 0)
            
            # If all copies are discarded, this color can't progress
            if discarded_count >= total_count:
                # This color is blocked, check if any other color can still progress
                continue
            
            # At least one color can still progress
            return False
        
        # All colors are either complete or blocked - no more points possible
        return True
    
    def getDiscardPile(self) -> List[Card]:
        """Get the discard pile."""
        return self._discard_pile.copy()
    
    def getPlayerHints(self, player_index: int) -> Dict[int, Dict[str, any]]:
        """Get hints for a player's hand."""
        # Return a deep copy to avoid reference issues
        player_hints = self._player_hints.get(player_index, {})
        return {idx: {"color": h.get("color"), "number": h.get("number")} 
                for idx, h in player_hints.items()}
    
    def getMoveHistory(self, player_index: int) -> List[Tuple[int, Move, str]]:
        """Get move history for a specific player (moves that affected them)."""
        history = []
        for p_idx, move, msg in self._move_history:
            # Include moves made by this player or hints given to this player
            if p_idx == player_index:
                history.append((p_idx, move, msg))
            elif isinstance(move, (ColorHint, NumberHint)) and move.teammate == player_index:
                history.append((p_idx, move, msg))
        return history
    
    def getMoveHistorySinceLastTurn(self, player_index: int) -> List[Tuple[int, Move, str]]:
        """Get move history for a player since their last turn."""
        last_turn_idx = self._last_turn_index.get(player_index, -1)
        all_history = self.getMoveHistory(player_index)
        # Return only moves after the last turn index
        return all_history[last_turn_idx + 1:]
    
    def getRecentMovesFromOtherPlayers(self, current_player: int) -> List[Tuple[int, Move, str]]:
        """
        Get the most recent move from each other player (excluding current player).
        
        In a game with N players, this returns the most recent move from each of the
        other (N-1) players, ordered by player index.
        
        Args:
            current_player: The index of the current player
            
        Returns:
            List of (player_index, move, message) tuples, one per other player
        """
        # Track the most recent move from each other player
        recent_moves: Dict[int, Tuple[int, Move, str]] = {}
        
        # Go through move history in reverse to find the most recent move from each player
        for p_idx, move, msg in reversed(self._move_history):
            # Only consider moves from other players (not current player)
            if p_idx != current_player and p_idx not in recent_moves:
                recent_moves[p_idx] = (p_idx, move, msg)
            
            # Stop when we have moves from all other players
            if len(recent_moves) == self._settings.numPlayers - 1:
                break
        
        # Return moves ordered by player index
        return [recent_moves[p_idx] for p_idx in sorted(recent_moves.keys())]
    
    def _removeCardHints(self, player_index: int, card_index: int) -> None:
        """Remove hints for a card that was played/discarded."""
        if player_index in self._player_hints:
            if card_index in self._player_hints[player_index]:
                del self._player_hints[player_index][card_index]
    
    def _shiftHintsAfterCardRemoval(self, player_index: int, removed_index: int, card_added: bool) -> None:
        """
        Shift hint indices after a card is removed/added.
        
        IMPORTANT: This method preserves ALL hints from previous turns, ensuring that
        hints given to cards in previous turns are not lost when cards are drawn and
        indices shift.
        
        When a card is removed and a new card is added at position 0:
        - Cards at indices < removed_index shift right by 1 (to make room for new card at 0)
        - Cards at indices > removed_index shift left by 1 (because a card was removed)
        - The removed card's hints are deleted
        - The new card at position 0 gets no hints
        
        Args:
            player_index: Index of the player whose hints are being shifted
            removed_index: Index of the card that was removed
            card_added: Whether a new card was added at position 0
        """
        if player_index not in self._player_hints:
            # Initialize if needed
            self._player_hints[player_index] = {}
            if card_added:
                self._player_hints[player_index][0] = {"color": None, "number": None}
            return
        
        # Create new hints dict with shifted indices
        # IMPORTANT: Copy hint dicts to avoid reference issues and preserve all hint data
        new_hints = {}
        for old_idx, hints in self._player_hints[player_index].items():
            # Skip the removed card's hints (should already be removed, but double-check)
            if old_idx == removed_index:
                continue
                
            # Create a deep copy of the hints dict to preserve all hint information
            # This ensures both color and number hints are preserved
            hints_copy = {"color": hints.get("color"), "number": hints.get("number")}
            
            if old_idx < removed_index:
                # Cards before removed card: shift right by 1 if new card added at 0, else stay same
                if card_added:
                    new_hints[old_idx + 1] = hints_copy
                else:
                    new_hints[old_idx] = hints_copy
            elif old_idx > removed_index:
                # Cards after removed card:
                # - First, the removal shifts them left by 1 (old_idx → old_idx - 1)
                # - Then, if a new card is added at 0, everything shifts right by 1
                # - Net effect: if card_added, they stay at old_idx - 1 + 1 = old_idx (no net shift)
                # - If not card_added, they shift left by 1 (old_idx → old_idx - 1)
                if card_added:
                    # Card was removed AND new card added: net effect is shift left by 1, then right by 1 = no change
                    # But wait, that's not right. Let me recalculate:
                    # Remove at removed_index: old_idx > removed_index becomes old_idx - 1
                    # Add at 0: everything shifts right by 1
                    # So: old_idx → (old_idx - 1) + 1 = old_idx (no net change)
                    new_hints[old_idx] = hints_copy
                else:
                    # Only removal, no addition: shift left by 1
                    new_hints[old_idx - 1] = hints_copy
            # old_idx == removed_index is skipped (card was removed)
        
        # If card was added at position 0, add empty hints for it
        if card_added:
            new_hints[0] = {"color": None, "number": None}
        
        self._player_hints[player_index] = new_hints

