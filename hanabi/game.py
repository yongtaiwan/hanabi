"""
Game state classes for Hanabi.
"""

from typing import Dict, List, TYPE_CHECKING

if TYPE_CHECKING:
    from .moves import Move
    from .player import PlayerTeam

from .enums import Color, Number
from .card import Card, Suit


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
    
    def __init__(self, teammates: Dict[int, Hand]):
        """
        Initialize player view.
        
        Args:
            teammates: Dictionary mapping player index to their Hand
        """
        self._teammates = {k: Hand(v.cards) for k, v in teammates.items()}
    
    @property
    def teammates(self) -> Dict[int, Hand]:
        """Get the teammates' hands (player index -> Hand)."""
        return {k: Hand(v.cards) for k, v in self._teammates.items()}
    
    def __repr__(self) -> str:
        return f"PlayerView(teammates={list(self._teammates.keys())})"


class GameState:
    """Represents the state of a game."""
    
    def __init__(
        self,
        common_view: CommonView,
        player_hands: List[Hand],
        draw_deck_index: int
    ):
        """
        Initialize game state.
        
        Args:
            common_view: The common view visible to all players
            player_hands: List of hands for each player
            draw_deck_index: Current index in the draw deck
        """
        self._common_view = common_view
        self._player_hands = [Hand(h.cards) for h in player_hands]
        self._draw_deck_index = draw_deck_index
    
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
    
    def _validate(self, player_index: int, move: 'Move') -> bool:
        """
        Validate a move for a player.
        
        Args:
            player_index: Index of the player making the move
            move: The move to validate
            
        Returns:
            True if the move is valid, False otherwise
        """
        # Placeholder for validation logic
        # This would contain actual validation rules
        return True
    
    def update(self, player_index: int, move: 'Move') -> None:
        """
        Update the game state with a move.
        
        Args:
            player_index: Index of the player making the move
            move: The move to apply
        """
        if not self._validate(player_index, move):
            raise ValueError(f"Invalid move: {move}")
        # Placeholder for update logic
        # This would contain actual state update logic
    
    def isFinished(self) -> bool:
        """
        Check if the game is finished.
        
        Returns:
            True if the game is finished, False otherwise
        """
        # Placeholder for finish check logic
        # This would contain actual finish conditions
        return False
    
    def score(self) -> int:
        """
        Calculate the game score.
        
        Returns:
            The current game score
        """
        # Placeholder for score calculation
        # This would contain actual scoring logic
        return 0
    
    def __repr__(self) -> str:
        return f"GameState(draw_deck_index={self._draw_deck_index}, finished={self.isFinished()})"


class Game:
    """Represents a single game instance."""
    
    def __init__(self, team: 'PlayerTeam', state: GameState):
        """
        Initialize a game.
        
        Args:
            team: The team of players
            state: The current game state
        """
        self._team = team
        self._state = state
    
    @property
    def team(self) -> 'PlayerTeam':
        """Get the player team."""
        return self._team
    
    @property
    def state(self) -> GameState:
        """Get the game state."""
        return self._state
    
    def __repr__(self) -> str:
        return f"Game(team={self._team.name()}, state={self._state})"


class GameField:
    """Manages multiple games and game initialization."""
    
    def __init__(self, settings: GameSettings, draw_deck: List[Card]):
        """
        Initialize a game field.
        
        Args:
            settings: The game settings
            draw_deck: The draw deck of cards
        """
        self._settings = settings
        self._draw_deck = draw_deck.copy()
        self._games: Dict[str, Game] = {}
    
    @property
    def settings(self) -> GameSettings:
        """Get the game settings."""
        return self._settings
    
    @property
    def drawDeck(self) -> List[Card]:
        """Get the draw deck."""
        return self._draw_deck.copy()
    
    @property
    def games(self) -> Dict[str, Game]:
        """Get the dictionary of games."""
        return self._games.copy()
    
    def _initGame(self) -> Game:
        """
        Initialize a new game.
        
        Returns:
            A new game instance
        """
        # Placeholder for game initialization logic
        # This would create a new game with initial state
        from .player import PlayerTeam
        # Create empty team and state as placeholders
        team = PlayerTeam([])
        common_view = CommonView(
            live_tokens=self._settings.maxLiveTokens,
            hint_tokens=self._settings.maxHintTokens,
            cards_to_draw=len(self._draw_deck),
            cards_discarded={},
            cards_played={}
        )
        state = GameState(
            common_view=common_view,
            player_hands=[],
            draw_deck_index=0
        )
        return Game(team, state)
    
    def _playGame(self) -> None:
        """
        Play a single game.
        """
        # Placeholder for game play logic
        # This would contain the game loop
        pass
    
    def playGames(self, count: int) -> None:
        """
        Play multiple games.
        
        Args:
            count: Number of games to play
        """
        for i in range(count):
            game = self._initGame()
            game_id = f"game_{i}"
            self._games[game_id] = game
            self._playGame()
    
    def __repr__(self) -> str:
        return f"GameField(settings={self._settings}, games={len(self._games)})"

