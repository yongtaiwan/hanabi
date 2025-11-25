"""
Player classes for Hanabi game.
"""

from abc import ABC, abstractmethod
import random
from typing import TYPE_CHECKING, List

if TYPE_CHECKING:
    from .game import PlayerView
    from .moves import Move
    from .observer import Observer
    from .game import GameSettings, CommonView

from .observer import Observer
from .game import PlayerView
from .moves import Move, Play, Discard, ColorHint, NumberHint
from .enums import Color, Number


class Player(ABC):
    """Interface for a player in Hanabi."""
    
    @abstractmethod
    def play(self, player_view: PlayerView) -> Move:
        """
        Make a move based on the current player view.
        
        Args:
            player_view: The current view of the game from this player's perspective
            
        Returns:
            The move to make
        """
        pass


class BasePlayer(Observer, Player):
    """Base class for players that implements both Observer and Player."""
    
    def __init__(self, player_index: int):
        """
        Initialize a base player.
        
        Args:
            player_index: The index of this player
        """
        self._player_index = player_index
        self._game_settings = None
        self._common_view = None
    
    @property
    def playerIndex(self) -> int:
        """Get the player index."""
        return self._player_index
    
    @property
    def gameSettings(self) -> 'GameSettings':
        """Get the game settings."""
        if self._game_settings is None:
            raise ValueError("Game settings not set")
        return self._game_settings
    
    @property
    def commonView(self) -> 'CommonView':
        """Get the common view of the game state."""
        if self._common_view is None:
            raise ValueError("Common view not set")
        return self._common_view
    
    def set_game_settings(self, game_settings: 'GameSettings') -> None:
        """Set the game settings."""
        self._game_settings = game_settings
    
    def set_common_view(self, common_view: 'CommonView') -> None:
        """Set the common view."""
        self._common_view = common_view
    
    def observe(self, player_index: int, move: Move) -> None:
        """
        Observe a move made by a player.
        
        Args:
            player_index: Index of the player who made the move
            move: The move that was made
        """
        # Base implementation - can be overridden by subclasses
        pass
    
    @abstractmethod
    def play(self, player_view: PlayerView) -> Move:
        """
        Make a move based on the current player view.
        
        Args:
            player_view: The current view of the game from this player's perspective
            
        Returns:
            The move to make
        """
        pass


class HumanPlayer(BasePlayer):
    """Human player that requires manual input."""
    
    def __init__(self, player_index: int, input_handler=None):
        """
        Initialize a human player.
        
        Args:
            player_index: The index of this player
            input_handler: Optional function to get input (for testing)
        """
        super().__init__(player_index)
        self._input_handler = input_handler
    
    def play(self, player_view: PlayerView) -> Move:
        """
        Make a move (requires human input).
        
        Args:
            player_view: The current view of the game
            
        Returns:
            The move to make
        """
        # This method is not used in console game
        # Console game handles input separately
        raise NotImplementedError(
            "HumanPlayer.play() should not be called directly in console game. "
            "Use ConsoleInput to parse moves instead."
        )


class RandomPlayer(BasePlayer):
    """Player that makes random moves."""
    
    def play(self, player_view: PlayerView) -> Move:
        """
        Make a random move.
        
        Args:
            player_view: The current view of the game
            
        Returns:
            A random move
        """
        # Get own hand (assuming player 0 is self, adjust as needed)
        # For simplicity, we'll make random choices
        common_view = self.commonView
        
        # Randomly choose between play, discard, or hint
        if common_view.hintTokens > 0 and len(player_view.teammates) > 0:
            # Can give a hint
            action = random.choice(['play', 'discard', 'hint'])
        else:
            # Cannot give a hint
            action = random.choice(['play', 'discard'])
        
        if action == 'play':
            # Randomly play a card (assuming hand size)
            # This is a simplified version - you'd need actual hand info
            card_index = random.randint(0, self.gameSettings.maxCardsInHand - 1)
            return Play(card_index)
        elif action == 'discard':
            # Randomly discard a card
            card_index = random.randint(0, self.gameSettings.maxCardsInHand - 1)
            return Discard(card_index)
        else:  # hint
            # Give a random hint to a random teammate
            teammate = random.choice(list(player_view.teammates.keys()))
            hint_type = random.choice(['color', 'number'])
            
            if hint_type == 'color':
                color = random.choice(list(Color))
                # Simplified - would need to calculate matching cards
                matching_cards = []
                return ColorHint(teammate, matching_cards, color)
            else:
                number = random.choice(list(Number))
                # Simplified - would need to calculate matching cards
                matching_cards = []
                return NumberHint(teammate, matching_cards, number)


class StrategyAlphaPlayer(BasePlayer):
    """Strategy player implementing Alpha strategy."""
    
    def play(self, player_view: PlayerView) -> Move:
        """
        Make a move using the Alpha strategy.
        
        Args:
            player_view: The current view of the game
            
        Returns:
            A move based on the Alpha strategy
        """
        # Placeholder for Alpha strategy implementation
        # This would contain the actual strategy logic
        common_view = self.commonView
        
        # Simple strategy: try to play if we have hint tokens, otherwise discard
        if common_view.hintTokens < self.gameSettings.maxHintTokens:
            # Prefer discarding to gain hint tokens
            return Discard(0)  # Simplified - would need actual strategy
        else:
            # Try to play a card
            return Play(0)  # Simplified - would need actual strategy


class PlayerTeam:
    """Represents a team of players."""
    
    def __init__(self, players: List[Player]):
        """
        Initialize a player team.
        
        Args:
            players: List of players in the team
        """
        self._players = players.copy()
    
    @property
    def players(self) -> List[Player]:
        """Get the list of players in the team."""
        return self._players.copy()
    
    def name(self) -> str:
        """
        Get the name of the team.
        
        Returns:
            The team name as a string
        """
        # Default implementation - can be overridden or extended
        return f"Team({len(self._players)} players)"
    
    def __repr__(self) -> str:
        return f"PlayerTeam(players={len(self._players)})"

