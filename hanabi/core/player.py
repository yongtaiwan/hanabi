"""
Player classes for Hanabi game.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
import random
from typing import TYPE_CHECKING, List, Dict, Optional, Union

try:
    from typing import assert_never
except ImportError:  # Python 3.10 compatibility (the repository's declared target).
    def assert_never(value) -> None:
        raise AssertionError(f"unhandled value: {value!r}")

if TYPE_CHECKING:
    from .game import PlayerView
    from .moves import Move
    from .observer import Observer
    from .game import GameSettings, CommonView

from .observer import Observer
from .game import GameState, PlayerView, GameSettings
from .move_validation import is_move_legal_from_view
from .moves import (
    Move,
    Play,
    Discard,
    ColorHint,
    NumberHint,
    CardMove,
    Hint,
    FinishedPlay,
    FinishedDiscard,
    ensure_concrete_move,
)
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


class Cheater(ABC):
    """
    Full-information seat: chooses a move from :class:`~hanabi.core.game.GameState`.

    Does not observe moves (sees authoritative state each turn). Not a :class:`Player`.
    """

    def __init__(self, player_index: int) -> None:
        self._player_index = player_index

    @property
    def player_index(self) -> int:
        return self._player_index

    @abstractmethod
    def play(self, state: GameState) -> Move:
        """
        Choose a legal move given full table state (all hands, common view, deck index).

        Must not assume knowledge of undrawn card order beyond what ``state`` exposes.
        """
        pass

    @classmethod
    def supports_game_settings(cls, game_settings: GameSettings) -> bool:
        """Return whether this cheater type is valid for the given game configuration."""
        return True


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
    def player_index(self) -> int:
        """Get the player index."""
        return self._player_index

    @property
    def game_settings(self) -> GameSettings:
        """Get the game settings."""
        assert self._game_settings is not None, "Game settings not set"
        return self._game_settings

    @property
    def common_view(self) -> CommonView:
        """Get the common view of the game state."""
        assert self._common_view is not None, "Common view not set"
        return self._common_view

    def set_game_settings(self, game_settings: GameSettings) -> None:
        """Set the game settings."""
        self._game_settings = game_settings

    def set_common_view(self, common_view: CommonView) -> None:
        """Set the common view (all players share the same reference)."""
        self._common_view = common_view

    def is_move_legal(self, player_view: PlayerView, move: Move) -> bool:
        """Whether ``move`` is legal from this player's view (tokens, indices, hint rules)."""
        return is_move_legal_from_view(
            move,
            player_view=player_view,
            common_view=self.common_view,
            game_settings=self.game_settings,
            player_index=self._player_index,
        )

    @classmethod
    def supports_game_settings(cls, game_settings: GameSettings) -> bool:
        """Return whether this player type is valid for the given game configuration."""
        return True

    def observe(
        self,
        player_index: int,
        move: Move,
        observer_view: PlayerView,
    ) -> None:
        """
        Observe a move made by a player.

        Dispatches to :meth:`observe_play_move`, :meth:`observe_discard_move`,
        :meth:`observe_color_hint_move`, and :meth:`observe_number_hint_move`.
        Subclasses override those hooks (default no-op) instead of replacing
        this method, unless they need a single entry point (e.g. a guard).

        Args:
            player_index: Index of the player who made the move
            move: The move that was made
            observer_view: This player's view after the move (from the engine).
        """
        m = ensure_concrete_move(move)
        match m:
            case FinishedPlay():
                self.observe_play_move(player_index, m, observer_view)
            case FinishedDiscard():
                self.observe_discard_move(player_index, m, observer_view)
            case Play():
                assert False, "engine must notify FinishedPlay (not bare Play) to observers"
            case Discard():
                assert False, "engine must notify FinishedDiscard (not bare Discard) to observers"
            case ColorHint():
                self.observe_color_hint_move(player_index, m, observer_view)
            case NumberHint():
                self.observe_number_hint_move(player_index, m, observer_view)
            case _:
                assert_never(m)

    def observe_play_move(self, player_index: int, move: FinishedPlay, observer_view: PlayerView) -> None:
        """Hook: a player played a card. Default does nothing."""

    def observe_discard_move(
        self, player_index: int, move: FinishedDiscard, observer_view: PlayerView
    ) -> None:
        """Hook: a player discarded a card. Default does nothing."""

    def observe_color_hint_move(self, player_index: int, move: ColorHint, observer_view: PlayerView) -> None:
        """Hook: a color hint was given. Default does nothing."""

    def observe_number_hint_move(self, player_index: int, move: NumberHint, observer_view: PlayerView) -> None:
        """Hook: a number hint was given. Default does nothing."""

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


class HintTrackingPlayer(BasePlayer):
    """Base class for players that track hints about their own hand."""

    def __init__(self, player_index: int):
        """
        Initialize a hint-tracking player.

        Args:
            player_index: The index of this player
        """
        super().__init__(player_index)
        self._hints: Dict[int, Dict[str, Optional[Union[Color, Number]]]] = {}

    def observe_play_move(self, player_index: int, move: FinishedPlay, observer_view: PlayerView) -> None:
        super().observe_play_move(player_index, move, observer_view)
        if player_index == self._player_index:
            self._update_hints_from_card_move(move)

    def observe_discard_move(
        self, player_index: int, move: FinishedDiscard, observer_view: PlayerView
    ) -> None:
        super().observe_discard_move(player_index, move, observer_view)
        if player_index == self._player_index:
            self._update_hints_from_card_move(move)

    def observe_color_hint_move(self, player_index: int, move: ColorHint, observer_view: PlayerView) -> None:
        super().observe_color_hint_move(player_index, move, observer_view)
        if move.teammate == self._player_index:
            self._update_hints_from_hint(move, observer_view)

    def observe_number_hint_move(self, player_index: int, move: NumberHint, observer_view: PlayerView) -> None:
        super().observe_number_hint_move(player_index, move, observer_view)
        if move.teammate == self._player_index:
            self._update_hints_from_hint(move, observer_view)

    def get_hints(self) -> Dict[int, Dict[str, Optional[Union[Color, Number]]]]:
        """
        Get hints for this player's hand.

        Returns:
            Dictionary mapping card index to hint data (color and/or number)
        """
        return {idx: {"color": h.get("color"), "number": h.get("number")} for idx, h in self._hints.items()}

    def _update_hints_from_hint(self, hint: Hint, observer_view: PlayerView) -> None:
        """Update hints when receiving a hint about our hand.

        ``observer_view.own_hand_size`` reflects how many slots are currently visible to us
        (may be below ``max_cards_in_hand`` late in the game).
        """
        hand_size = observer_view.own_hand_size

        for card_idx in hint.cards:
            assert 0 <= card_idx < hand_size, (
                f"[HintTrackingPlayer {self._player_index}] hint has invalid card index {card_idx} "
                f"(hand size: {hand_size})"
            )

            if card_idx not in self._hints:
                self._hints[card_idx] = {"color": None, "number": None}

            if isinstance(hint, ColorHint):
                self._hints[card_idx]["color"] = hint.color
            elif isinstance(hint, NumberHint):
                self._hints[card_idx]["number"] = hint.number

    def _update_hints_from_card_move(self, move: CardMove) -> None:
        """Update hints when playing/discarding a card.

        Hand order is left-to-right: index 0 is C1 (oldest). When a card is removed at
        index ``i`` (``list.pop``), every card strictly to its right shifts down by one.
        If a replacement card is drawn, it is **appended** on the right (new highest index).

        Net effect on hint bookkeeping after the pop (before any draw append):
        - Hints for indices ``< i``: unchanged (same physical card remains in that slot).
        - Hints for indices ``> i``: index decreases by 1 (card slid left).
        The removed slot's hint was deleted above. A new draw does not shift existing
        indices (it only adds a new rightmost slot with no hint yet).
        """
        card_index = move.card

        if card_index in self._hints:
            del self._hints[card_index]

        new_hints = {}
        for old_idx, hint_data in self._hints.items():
            if old_idx < card_index:
                new_hints[old_idx] = hint_data
            elif old_idx > card_index:
                new_hints[old_idx - 1] = hint_data
        self._hints = new_hints


class HumanPlayer(HintTrackingPlayer):
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
        pass


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
        # Simple strategy: try to play if we have hint tokens, otherwise discard
        if self.common_view.hint_tokens < self.game_settings.max_hint_tokens:
            # Prefer discarding to gain hint tokens
            return Discard(0)  # Simplified - would need actual strategy
        else:
            # Try to play a card
            return Play(0)  # Simplified - would need actual strategy


TeamMember = Union[BasePlayer, Cheater]


class PlayerTeam:
    """Team of :class:`BasePlayer` and/or :class:`Cheater` seats."""

    def __init__(self, players: List[TeamMember]):
        """
        Initialize a player team.

        Args:
            players: Each seat is a :class:`BasePlayer` (partial view + observer) or
                :class:`Cheater` (full state, no observation).
        """
        self._players = players.copy()

    def __repr__(self) -> str:
        return f"PlayerTeam(players={len(self._players)})"

    @property
    def players(self) -> List[TeamMember]:
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
