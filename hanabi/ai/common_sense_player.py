"""
Common Sense AI player for Hanabi game.

This player uses simple heuristics to make reasonable decisions:
- Tracks possible cards for each position in hand
- Never plays cards that could lose a life
- Prioritizes finishing suits with 5s
- Gives useful hints to teammates
- Discards strategically
"""

from typing import List, Set, Dict, Optional, TYPE_CHECKING
from collections import Counter

from hanabi.core.player import HintTrackingPlayer
from hanabi.core.game import PlayerView
from hanabi.core.moves import Move, Play, Discard, ColorHint, NumberHint
from hanabi.core.enums import Color, Number
from hanabi.core.card import Card
from hanabi.core.move_generation import generate_all_valid_moves

if TYPE_CHECKING:
    pass


class CommonSensePlayer(HintTrackingPlayer):
    """
    AI player that uses common sense rules to make decisions.

    Rules:
    0. Track possible cards for each position, filtering seen cards and using hints
    1. Never play a card that could lose a life
    2. Play a 5 to finish a suit (highest priority)
    3. Play a playable card (prioritize cards we've received hints about)
    4. Hint that identifies most new playable cards, tiebreak by player playing soon
       (avoid duplicate hints - don't give hints teammates already have)
    5. Discard least likely to cause suit unfinishable, tiebreak by oldest
       (NEVER discard a card that is definitely playable)
       (NEVER discard a card we have hints about if it could be playable)
    6. Give hint that covers most cards, tiebreak by player playing soon
       (avoid duplicate hints - don't give hints teammates already have)

    Additional common sense:
    - Track hints given to teammates and avoid giving duplicate hints
    - If we received hints on cards, prioritize playing those cards
    """

    def __init__(self, player_index: int):
        """
        Initialize a common sense AI player.

        Args:
            player_index: The index of this player
        """
        super().__init__(player_index)
        self._seen_cards: Set[Card] = set()
        self._all_possible_cards: List[Card] = []
        self._last_decision_summary: Optional[str] = None
        # Track hints we received to infer negative information
        self._received_hints: List[Move] = []
        # Track hints given to teammates: teammate_idx -> list of hints they've received
        # Each hint is stored as (hint_type, value) where hint_type is 'color' or 'number'
        self._teammate_hints: Dict[int, List[tuple]] = {}

    def observe(self, player_index: int, move: Move, **kwargs) -> None:
        """
        Observe moves to track seen cards, received hints, and hints given to teammates.

        Args:
            player_index: Index of the player who made the move
            move: The move that was made
        """
        super().observe(player_index, move, **kwargs)

        # Track hints we received (for negative hint inference)
        if isinstance(move, (ColorHint, NumberHint)) and move.teammate == self._player_index:
            self._received_hints.append(move)

        # Track hints given to teammates (by anyone, including ourselves)
        if isinstance(move, (ColorHint, NumberHint)):
            teammate_idx = move.teammate
            if teammate_idx != self._player_index:  # Don't track hints to ourselves here
                if teammate_idx not in self._teammate_hints:
                    self._teammate_hints[teammate_idx] = []

                # Store hint information
                if isinstance(move, ColorHint):
                    self._teammate_hints[teammate_idx].append(('color', move.color))
                elif isinstance(move, NumberHint):
                    self._teammate_hints[teammate_idx].append(('number', move.number))

    def _get_all_possible_cards(self) -> List[Card]:
        """Get all possible cards in the game from settings."""
        if not self._all_possible_cards:
            settings = self.gameSettings
            cards = []
            for color, suit in settings.cards.items():
                for number, quantity in suit.cards.items():
                    for _ in range(quantity):
                        cards.append(Card(color, number))
            self._all_possible_cards = cards
        return self._all_possible_cards.copy()

    def _update_seen_cards(self, player_view: PlayerView) -> None:
        """Update the set of cards we've seen."""
        common_view = self.commonView

        # Add all cards from teammates' hands
        for teammate_idx, hand in player_view.teammates.items():
            for card in hand.cards:
                self._seen_cards.add(card)

        # Add all discarded cards (reconstruct from cardsDiscarded structure)
        for color, suit in common_view.cardsDiscarded.items():
            # Suit.cards is a Dict[Number, int] mapping number to count
            for number, count in suit.cards.items():
                for _ in range(count):
                    self._seen_cards.add(Card(color, number))

    def _get_possible_cards_for_position(
        self,
        position: int,
        player_view: PlayerView
    ) -> Set[Card]:
        """
        Get possible cards for a given position in hand.

        Uses hints (both positive and negative) and filters seen cards.

        Args:
            position: Card position in hand (0-based)
            player_view: Current player view

        Returns:
            Set of possible cards for this position
        """
        hints = self.getHints()
        card_hints = hints.get(position, {})

        all_cards = set(self._get_all_possible_cards())

        # Start with all cards, then filter
        possible = all_cards.copy()

        # Count how many of each card we've seen
        from collections import Counter
        seen_card_counts = Counter(self._seen_cards)
        all_card_counts = Counter(self._get_all_possible_cards())

        # Remove cards only if we've seen ALL copies of that card
        # (e.g., if there are 3 white 1s and we've seen 3, we can't have any more)
        for card in list(possible):
            if card in seen_card_counts:
                if seen_card_counts[card] >= all_card_counts[card]:
                    # We've seen all copies of this card, remove it
                    possible.discard(card)

        # Apply positive hints (what we know this card IS)
        if card_hints.get("color") is not None:
            color = card_hints["color"]
            possible = {c for c in possible if c.color == color}

        if card_hints.get("number") is not None:
            number = card_hints["number"]
            possible = {c for c in possible if c.number == number}

        # Apply negative hints (what we know this card is NOT)
        # If a position doesn't have a hint, but other positions do, we can infer
        # that this position doesn't have those properties (if the hint covered all
        # cards with that property, which hints always do)
        hand_size = player_view.ownHandSize

        # Get all positions that have color hints
        positions_with_color_hints = {
            pos: hints.get(pos, {}).get("color")
            for pos in range(hand_size)
            if hints.get(pos, {}).get("color") is not None
        }

        # Get all positions that have number hints
        positions_with_number_hints = {
            pos: hints.get(pos, {}).get("number")
            for pos in range(hand_size)
            if hints.get(pos, {}).get("number") is not None
        }

        # If this position doesn't have a color hint, but we know which colors
        # other positions have, we can't exclude colors without knowing the full
        # distribution. However, if we received a hint that said "N cards are color X"
        # and exactly N positions have that hint, then other positions are NOT that color.
        # For simplicity, we'll use a heuristic: if only some positions have hints,
        # we can't be certain about negatives without tracking the original hint counts.

        # For now, we rely primarily on positive hints (what we know cards ARE)
        # Negative hints require more complex tracking of position shifts

        return possible

    def _is_card_playable(self, card: Card, common_view) -> bool:
        """
        Check if a card is playable given the current game state.

        Args:
            card: The card to check
            common_view: The common view of the game

        Returns:
            True if the card is playable
        """
        cards_played = common_view.cardsPlayed

        if card.color not in cards_played:
            # Color not started - need a 1
            return card.number == Number.ONE
        else:
            # Color started - need next number
            next_number_value = cards_played[card.color].value + 1
            return card.number.value == next_number_value

    def _could_lose_life(self, position: int, player_view: PlayerView) -> bool:
        """
        Check if playing a card at this position could lose a life.

        Args:
            position: Card position in hand
            player_view: Current player view

        Returns:
            True if playing this card could lose a life
        """
        possible_cards = self._get_possible_cards_for_position(position, player_view)
        common_view = self.commonView

        # If ANY possible card is not playable, we could lose a life
        for card in possible_cards:
            if not self._is_card_playable(card, common_view):
                return True

        return False

    def _is_card_definitely_playable(self, position: int, player_view: PlayerView) -> bool:
        """
        Check if a card at this position is definitely playable.

        Args:
            position: Card position in hand
            player_view: Current player view

        Returns:
            True if all possible cards for this position are playable
        """
        possible_cards = self._get_possible_cards_for_position(position, player_view)
        if not possible_cards:
            return False

        common_view = self.commonView

        # All possible cards must be playable
        for card in possible_cards:
            if not self._is_card_playable(card, common_view):
                return False

        return True

    def _could_be_playable(self, position: int, player_view: PlayerView) -> bool:
        """
        Check if a card at this position could be playable (at least some possible cards are playable).

        This is useful when we have partial hints - if any possible card is playable,
        we should not discard it.

        Args:
            position: Card position in hand
            player_view: Current player view

        Returns:
            True if at least one possible card for this position is playable
        """
        possible_cards = self._get_possible_cards_for_position(position, player_view)
        if not possible_cards:
            return False

        common_view = self.commonView

        # Check if ANY possible card is playable
        for card in possible_cards:
            if self._is_card_playable(card, common_view):
                return True

        return False

    def _is_card_finishing_five(self, position: int, player_view: PlayerView) -> bool:
        """
        Check if a card at this position is a 5 that would finish a suit.

        Args:
            position: Card position in hand
            player_view: Current player view

        Returns:
            True if this is definitely a 5 that finishes a suit
        """
        possible_cards = self._get_possible_cards_for_position(position, player_view)
        if not possible_cards:
            return False

        common_view = self.commonView
        cards_played = common_view.cardsPlayed

        # Check if all possible cards are 5s that finish suits
        for card in possible_cards:
            if card.number != Number.FIVE:
                return False
            # Check if this 5 would finish the suit (4 is already played)
            if card.color not in cards_played:
                return False
            if cards_played[card.color].value != 4:
                return False

        return True

    def _count_new_playable_cards_from_hint(
        self,
        hint: Move,
        player_view: PlayerView
    ) -> int:
        """
        Count how many new playable cards a hint would identify.

        Args:
            hint: The hint move (ColorHint or NumberHint)
            player_view: Current player view

        Returns:
            Number of newly identified playable cards
        """
        if not isinstance(hint, (ColorHint, NumberHint)):
            return 0

        teammate_idx = hint.teammate
        if teammate_idx not in player_view.teammates:
            return 0

        teammate_hand = player_view.teammates[teammate_idx]
        common_view = self.commonView

        # Count cards that would be identified as playable by this hint
        count = 0
        for card_idx in hint.cards:
            if card_idx >= len(teammate_hand.cards):
                continue
            card = teammate_hand.cards[card_idx]

            # Check if this card is playable
            if self._is_card_playable(card, common_view):
                # Check if teammate already knows this card is playable
                # (We can't know for sure, but we can estimate)
                # For now, assume any playable card identified is "new"
                count += 1

        return count

    def _get_hint_card_count(self, hint: Move, player_view: PlayerView) -> int:
        """
        Get the number of cards a hint covers.

        Args:
            hint: The hint move
            player_view: Current player view

        Returns:
            Number of cards the hint covers
        """
        if isinstance(hint, (ColorHint, NumberHint)):
            return len(hint.cards)
        return 0

    def _get_turns_until_player(self, player_idx: int, current_player: int, num_players: int) -> int:
        """
        Get number of turns until a player plays.

        Args:
            player_idx: The player index
            current_player: Current player index
            num_players: Total number of players

        Returns:
            Number of turns until this player plays
        """
        if player_idx > current_player:
            return player_idx - current_player
        else:
            return num_players - current_player + player_idx

    def _get_discard_risk_score(self, position: int, player_view: PlayerView) -> float:
        """
        Calculate how risky it is to discard a card (lower = safer to discard).

        Risk is based on how likely discarding this card would make a suit unfinishable.

        Args:
            position: Card position in hand
            player_view: Current player view

        Returns:
            Risk score (lower = safer to discard)
        """
        possible_cards = self._get_possible_cards_for_position(position, player_view)
        if not possible_cards:
            return 0.0  # Unknown card, medium risk

        common_view = self.commonView
        cards_played = common_view.cardsPlayed

        # Calculate risk based on:
        # - Cards that are needed to finish suits (especially 5s)
        # - Cards that are the last copy of a needed number
        risk = 0.0

        for card in possible_cards:
            # High risk if it's a 5 that's needed
            if card.number == Number.FIVE:
                if card.color in cards_played:
                    if cards_played[card.color].value == 4:
                        risk += 10.0  # This 5 is needed to finish the suit
                else:
                    # Suit not started, but 5s are always valuable
                    risk += 5.0

            # Medium risk if it's a 4 and we need it
            elif card.number == Number.FOUR:
                if card.color in cards_played:
                    if cards_played[card.color].value == 3:
                        risk += 3.0

        # Normalize by number of possible cards
        if possible_cards:
            risk /= len(possible_cards)

        return risk

    def _has_hints_about_position(self, position: int, player_view: PlayerView) -> bool:
        """
        Check if we've received hints about a card at this position.

        Args:
            position: Card position in hand
            player_view: Current player view

        Returns:
            True if we have hints about this position
        """
        hints = self.getHints()
        card_hints = hints.get(position, {})

        # Check if we have any hints (color or number) for this position
        return card_hints.get("color") is not None or card_hints.get("number") is not None

    def _is_duplicate_hint(self, hint: Move, player_view: PlayerView) -> bool:
        """
        Check if a hint would be a duplicate (teammate already has this hint).

        Args:
            hint: The hint move to check
            player_view: Current player view

        Returns:
            True if this hint would be a duplicate
        """
        if not isinstance(hint, (ColorHint, NumberHint)):
            return False

        teammate_idx = hint.teammate
        if teammate_idx not in self._teammate_hints:
            return False  # No previous hints, not a duplicate

        # Check if teammate already has this type of hint
        previous_hints = self._teammate_hints[teammate_idx]

        if isinstance(hint, ColorHint):
            # Check if teammate already has a color hint for this color
            for hint_type, value in previous_hints:
                if hint_type == 'color' and value == hint.color:
                    # They already have this color hint - check if it's for the same cards
                    # We can't know exact positions, but if they have the hint, they likely
                    # already know what to do with it
                    return True
        elif isinstance(hint, NumberHint):
            # Check if teammate already has a number hint for this number
            for hint_type, value in previous_hints:
                if hint_type == 'number' and value == hint.number:
                    # They already have this number hint
                    return True

        return False

    def play(self, player_view: PlayerView) -> Move:
        """
        Make a move using common sense rules.

        Args:
            player_view: The current view of the game from this player's perspective

        Returns:
            A move selected using common sense rules
        """
        # Update seen cards
        self._update_seen_cards(player_view)

        # Generate all valid moves
        common_view = self.commonView
        game_settings = self.gameSettings
        valid_moves = generate_all_valid_moves(
            player_view=player_view,
            common_view=common_view,
            game_settings=game_settings,
            player_index=self._player_index
        )

        # Filter to actually valid moves
        valid_moves = [m for m in valid_moves if self._is_move_valid(m, player_view)]

        if not valid_moves:
            # Fallback: return a play move
            hand_size = player_view.ownHandSize
            return Play(0) if hand_size > 0 else Play(0)

        # Rule 1: Never play a card that could lose a life
        # EXCEPTION: If a card is definitely playable, it's always safe (all possible cards are playable)
        safe_play_moves = []
        for move in valid_moves:
            if isinstance(move, Play):
                # If definitely playable, it's always safe (all possible cards are playable)
                if self._is_card_definitely_playable(move.card, player_view):
                    safe_play_moves.append(move)
                elif not self._could_lose_life(move.card, player_view):
                    safe_play_moves.append(move)

        # Rule 2: Play a 5 to finish a suit (highest priority)
        finishing_five_moves = []
        for move in safe_play_moves:
            if self._is_card_finishing_five(move.card, player_view):
                finishing_five_moves.append(move)

        if finishing_five_moves:
            self._last_decision_summary = "Play 5 to finish suit (highest priority)"
            return finishing_five_moves[0]  # Pick first one

        # Rule 3: Play a playable card
        # Prioritize cards we've received hints about (teammates are likely hinting us to play them)
        playable_moves = []
        hinted_playable_moves = []
        for move in safe_play_moves:
            if self._is_card_definitely_playable(move.card, player_view):
                # Check if we've received hints about this card
                if self._has_hints_about_position(move.card, player_view):
                    hinted_playable_moves.append(move)
                else:
                    playable_moves.append(move)

        # Prioritize hinted cards
        if hinted_playable_moves:
            self._last_decision_summary = "Play hinted playable card"
            return hinted_playable_moves[0]  # Pick first one

        if playable_moves:
            self._last_decision_summary = "Play safe playable card"
            return playable_moves[0]  # Pick first one

        # Rule 4: Hint that identifies most new playable cards, tiebreak by player playing soon
        # Avoid duplicate hints (don't give hints teammates already have)
        hint_moves = [m for m in valid_moves if isinstance(m, (ColorHint, NumberHint))]
        if hint_moves and common_view.hintTokens > 0:
            # Filter out duplicate hints
            non_duplicate_hints = []
            for hint in hint_moves:
                if not self._is_duplicate_hint(hint, player_view):
                    non_duplicate_hints.append(hint)

            # If no non-duplicate hints, still consider all hints (better than nothing)
            hints_to_consider = non_duplicate_hints if non_duplicate_hints else hint_moves

            # Score hints by number of new playable cards
            best_hint = None
            best_score = -1
            num_players = game_settings.numPlayers

            for hint in hints_to_consider:
                playable_count = self._count_new_playable_cards_from_hint(hint, player_view)
                if playable_count > 0:
                    # Score = playable_count * 100 - turns_until_player
                    # Bonus for non-duplicate hints
                    duplicate_penalty = 0 if hint in non_duplicate_hints else 50
                    turns_until = self._get_turns_until_player(
                        hint.teammate, self._player_index, num_players
                    )
                    score = playable_count * 100 - turns_until - duplicate_penalty
                    if score > best_score:
                        best_score = score
                        best_hint = hint

            if best_hint:
                playable_count = self._count_new_playable_cards_from_hint(best_hint, player_view)
                if isinstance(best_hint, ColorHint):
                    self._last_decision_summary = f"Hint color {best_hint.color.name.lower()} to P{best_hint.teammate + 1} (identifies {playable_count} new playable cards)"
                else:
                    self._last_decision_summary = f"Hint number {best_hint.number.value} to P{best_hint.teammate + 1} (identifies {playable_count} new playable cards)"
                return best_hint

        # Rule 5: Discard least risky card, tiebreak by oldest
        # NEVER discard a card that is definitely playable
        # NEVER discard a card that we have hints about AND could be playable
        # (If teammate hinted us about a card, they likely want us to play it)
        if common_view.hintTokens < game_settings.maxHintTokens:
            discard_moves = [m for m in valid_moves if isinstance(m, Discard)]
            # Filter out playable cards - never discard cards we know are playable
            safe_discard_moves = []
            for discard in discard_moves:
                # Don't discard if definitely playable
                if self._is_card_definitely_playable(discard.card, player_view):
                    continue
                # Don't discard if we have hints about it AND it could be playable
                # This prevents discarding cards teammates hinted us about
                if self._has_hints_about_position(discard.card, player_view):
                    if self._could_be_playable(discard.card, player_view):
                        continue  # Teammate hinted this, and it could be playable - don't discard
                safe_discard_moves.append(discard)

            if safe_discard_moves:
                # Score discards: lower risk = better, older position = better (tiebreak)
                best_discard = None
                best_risk = float('inf')

                for discard in safe_discard_moves:
                    risk = self._get_discard_risk_score(discard.card, player_view)
                    # Lower position = older card (drawn earlier)
                    age_bonus = discard.card  # Lower index = older
                    score = risk - age_bonus * 0.1  # Prefer older cards

                    if score < best_risk:
                        best_risk = score
                        best_discard = discard

                if best_discard:
                    self._last_decision_summary = f"Discard card at position {best_discard.card + 1} (least risky, oldest)"
                    return best_discard

        # Rule 6: Give hint that covers most cards, tiebreak by player playing soon
        # Avoid duplicate hints
        if hint_moves and common_view.hintTokens > 0:
            # Filter out duplicate hints
            non_duplicate_hints = []
            for hint in hint_moves:
                if not self._is_duplicate_hint(hint, player_view):
                    non_duplicate_hints.append(hint)

            # If no non-duplicate hints, still consider all hints (better than nothing)
            hints_to_consider = non_duplicate_hints if non_duplicate_hints else hint_moves

            best_hint = None
            best_score = -1
            num_players = game_settings.numPlayers

            for hint in hints_to_consider:
                card_count = self._get_hint_card_count(hint, player_view)
                if card_count > 0:
                    # Bonus for non-duplicate hints
                    duplicate_penalty = 0 if hint in non_duplicate_hints else 20
                    turns_until = self._get_turns_until_player(
                        hint.teammate, self._player_index, num_players
                    )
                    score = card_count * 10 - turns_until - duplicate_penalty
                    if score > best_score:
                        best_score = score
                        best_hint = hint

            if best_hint:
                card_count = self._get_hint_card_count(best_hint, player_view)
                if isinstance(best_hint, ColorHint):
                    self._last_decision_summary = f"Hint color {best_hint.color.name.lower()} to P{best_hint.teammate + 1} (covers {card_count} cards)"
                else:
                    self._last_decision_summary = f"Hint number {best_hint.number.value} to P{best_hint.teammate + 1} (covers {card_count} cards)"
                return best_hint

        # Fallback: return first valid move
        self._last_decision_summary = "Fallback: first valid move"
        return valid_moves[0]

    def _is_move_valid(self, move: Move, player_view: PlayerView) -> bool:
        """
        Check if a move is valid (same logic as RandomPlayer).

        Args:
            move: The move to validate
            player_view: The current player view

        Returns:
            True if the move is valid
        """
        common_view = self.commonView
        hand_size = player_view.ownHandSize

        if isinstance(move, Play):
            if move.card < 0 or move.card >= hand_size:
                return False
            return True

        if isinstance(move, Discard):
            if move.card < 0 or move.card >= hand_size:
                return False
            if common_view.hintTokens >= self.gameSettings.maxHintTokens:
                return False
            return True

        if isinstance(move, (ColorHint, NumberHint)):
            hint_tokens = common_view.hintTokens
            if hint_tokens <= 0:
                return False

            if move.teammate not in player_view.teammates:
                return False

            if move.teammate == self._player_index:
                return False

            if not move.cards:
                return False

            teammate_hand = player_view.teammates[move.teammate]

            if isinstance(move, ColorHint):
                matching_indices = [
                    idx for idx, card in enumerate(teammate_hand.cards)
                    if card.color == move.color
                ]

                for card_idx in move.cards:
                    if card_idx < 0 or card_idx >= len(teammate_hand.cards):
                        return False
                    if teammate_hand.cards[card_idx].color != move.color:
                        return False

                if set(move.cards) != set(matching_indices):
                    return False

            elif isinstance(move, NumberHint):
                matching_indices = [
                    idx for idx, card in enumerate(teammate_hand.cards)
                    if card.number == move.number
                ]

                for card_idx in move.cards:
                    if card_idx < 0 or card_idx >= len(teammate_hand.cards):
                        return False
                    if teammate_hand.cards[card_idx].number != move.number:
                        return False

                if set(move.cards) != set(matching_indices):
                    return False

            return True

        return False

    def get_decision_summary(self) -> Optional[str]:
        """
        Get a summary of the last decision made.

        Returns:
            Summary string describing the reasoning, or None if no decision made yet
        """
        return self._last_decision_summary

