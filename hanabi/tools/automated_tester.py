"""
Automated testing system for Hanabi game.
Plays games automatically and validates game state consistency.
"""

import random
from typing import List, Dict, Tuple, Optional
from hanabi.core.game import create_standard_game_settings, Game
from hanabi.ai import RandomPlayer
from hanabi.core.moves import Play, Discard, ColorHint, NumberHint
from hanabi.core.enums import Color, Number
from hanabi.core.card import Card


class GameStateValidator:
    """Validates game state consistency."""

    def __init__(self, game: Game):
        self.game = game
        self.errors: List[str] = []

    def validate_all(self) -> List[str]:
        """Run all validation checks."""
        self.errors = []
        self.validate_hint_alignment()
        self.validate_card_ordering()
        self.validate_hint_persistence()
        return self.errors

    def validate_hint_alignment(self) -> None:
        """Validate that hints are aligned with correct cards."""
        state = self.game.state

        from hanabi.core.player import HintTrackingPlayer
        for player_idx in range(self.game.settings.numPlayers):
            hand = state.playerHands[player_idx]
            player = self.game.team.players[player_idx]
            hints = player.getHints() if isinstance(player, HintTrackingPlayer) else {}

            # Check each card position
            for card_idx in range(len(hand.cards)):
                card = hand.cards[card_idx]
                hint = hints.get(card_idx, {})

                # If there's a color hint, verify the card matches
                color_hint = hint.get("color")
                if color_hint and card.color != color_hint:
                    self.errors.append(
                        f"BUG: Player {player_idx}, card at index {card_idx} (1-based: {card_idx+1}) "
                        f"has color hint {color_hint.name} but card is {card.color.name}. "
                        f"Card: {card}"
                    )

                # If there's a number hint, verify the card matches
                number_hint = hint.get("number")
                if number_hint and card.number != number_hint:
                    self.errors.append(
                        f"BUG: Player {player_idx}, card at index {card_idx} (1-based: {card_idx+1}) "
                        f"has number hint {number_hint.value} but card is {number_hint.value}. "
                        f"Card: {card}"
                    )

    def validate_card_ordering(self) -> None:
        """Validate that card ordering is maintained correctly."""
        # This is more of a sanity check - cards should be in a valid list
        state = self.game.state

        for player_idx in range(self.game.settings.numPlayers):
            hand = state.playerHands[player_idx]

            # Check hand size is correct
            expected_size = self.game.settings.maxCardsInHand
            if len(hand.cards) > expected_size:
                self.errors.append(
                    f"BUG: Player {player_idx} has {len(hand.cards)} cards, "
                    f"but max is {expected_size}"
                )

    def validate_hint_persistence(self) -> None:
        """Validate that hints persist correctly across moves."""
        # This would require tracking hints across moves
        # For now, we'll just check that hints are valid
        state = self.game.state

        from hanabi.core.player import HintTrackingPlayer
        for player_idx in range(self.game.settings.numPlayers):
            player = self.game.team.players[player_idx]
            hints = player.getHints() if isinstance(player, HintTrackingPlayer) else {}
            hand = state.playerHands[player_idx]

            # Check that hint indices are valid
            for hint_idx in hints.keys():
                if hint_idx < 0 or hint_idx >= len(hand.cards):
                    self.errors.append(
                        f"BUG: Player {player_idx} has hint at invalid index {hint_idx}, "
                        f"but hand has {len(hand.cards)} cards"
                    )


class AutomatedGamePlayer:
    """Plays games automatically and validates state."""

    def __init__(self, num_players: int = 2, max_games: int = 10):
        self.num_players = num_players
        self.max_games = max_games
        self.bugs_found: List[Dict] = []

    def play_and_validate(self) -> Dict:
        """Play a single game and validate state after each move."""
        from hanabi.core.game import Game
        from hanabi.core.player import PlayerTeam

        settings = create_standard_game_settings(self.num_players)
        players = [RandomPlayer(i) for i in range(self.num_players)]
        team = PlayerTeam(players)
        game = Game.create(team, settings)

        validator = GameStateValidator(game)
        move_count = 0
        max_moves = 200  # Prevent infinite loops

        game_log = {
            "moves": [],
            "errors": [],
            "final_score": 0,
            "finished": False
        }

        while not game.isFinished and move_count < max_moves:
            current_player = game.currentPlayer
            state = game.state

            # Validate state before move
            errors_before = validator.validate_all()
            if errors_before:
                game_log["errors"].extend([
                    f"Before move {move_count + 1}: {err}" for err in errors_before
                ])

            # Make a move
            move = self._make_move(game, current_player)
            if move is None:
                break

            try:
                game._processMove(current_player, move)
                result_msg = "Move successful"  # Game doesn't return messages anymore
                move_count += 1

                # Validate state after move
                validator = GameStateValidator(game)  # Recreate validator with new state
                errors_after = validator.validate_all()
                if errors_after:
                    game_log["errors"].extend([
                        f"After move {move_count} (player {current_player}, {move}): {err}"
                        for err in errors_after
                    ])
                    game_log["moves"].append({
                        "move": move_count,
                        "player": current_player,
                        "move_type": type(move).__name__,
                        "result": result_msg,
                        "errors": errors_after.copy()
                    })
                else:
                    game_log["moves"].append({
                        "move": move_count,
                        "player": current_player,
                        "move_type": type(move).__name__,
                        "result": result_msg
                    })
            except AssertionError as e:
                # Illegal move or invariant failure (bug in automated player / engine)
                game_log["errors"].append(f"Invalid move or assertion: {e}")
                break

        game_log["final_score"] = game.getScore()
        game_log["finished"] = game.isFinished

        return game_log

    def _make_move(self, game: Game, player_index: int) -> Optional:
        """Make a move for the given player."""
        state = game.state
        common_view = state.commonView
        hand = state.playerHands[player_index]

        if not hand.cards:
            return None

        # Try to give a hint if possible
        if common_view.hintTokens > 0:
            # Find a teammate
            for teammate_idx in range(self.num_players):
                if teammate_idx != player_index:
                    teammate_hand = state.playerHands[teammate_idx]
                    if teammate_hand.cards:
                        # Try color hint
                        colors = [Color.WHITE, Color.RED, Color.YELLOW, Color.GREEN, Color.BLUE]
                        random.shuffle(colors)
                        for color in colors:
                            matching = [i for i, c in enumerate(teammate_hand.cards) if c.color == color]
                            if matching:
                                return ColorHint(teammate_idx, matching, color)

                        # Try number hint
                        numbers = [Number.ONE, Number.TWO, Number.THREE, Number.FOUR, Number.FIVE]
                        random.shuffle(numbers)
                        for number in numbers:
                            matching = [i for i, c in enumerate(teammate_hand.cards) if c.number == number]
                            if matching:
                                return NumberHint(teammate_idx, matching, number)

        # Try to play a card (random choice)
        if random.random() < 0.5:
            return Play(random.randint(0, len(hand.cards) - 1))
        else:
            # Discard if we can't hint
            if common_view.hintTokens < game.settings.maxHintTokens:
                return Discard(random.randint(0, len(hand.cards) - 1))
            else:
                return Play(random.randint(0, len(hand.cards) - 1))

    def run_tests(self) -> Dict:
        """Run multiple games and collect bugs."""
        all_errors = []
        games_with_errors = 0

        for game_num in range(self.max_games):
            print(f"Playing game {game_num + 1}/{self.max_games}...", end=" ")
            game_log = self.play_and_validate()

            if game_log["errors"]:
                games_with_errors += 1
                all_errors.append({
                    "game": game_num + 1,
                    "errors": game_log["errors"],
                    "final_score": game_log["final_score"],
                    "moves": len(game_log["moves"])
                })
                print(f"❌ Found {len(game_log['errors'])} errors")
            else:
                print(f"✓ Score: {game_log['final_score']}")

        return {
            "total_games": self.max_games,
            "games_with_errors": games_with_errors,
            "total_errors": sum(len(g["errors"]) for g in all_errors),
            "error_details": all_errors
        }


def main():
    """Run automated tests."""
    print("=" * 70)
    print("Hanabi Automated Testing System")
    print("=" * 70)
    print()

    tester = AutomatedGamePlayer(num_players=2, max_games=20)
    results = tester.run_tests()

    print()
    print("=" * 70)
    print("Test Results")
    print("=" * 70)
    print(f"Total games played: {results['total_games']}")
    print(f"Games with errors: {results['games_with_errors']}")
    print(f"Total errors found: {results['total_errors']}")
    print()

    if results['error_details']:
        print("Error Details:")
        print("-" * 70)
        for game_info in results['error_details'][:10]:  # Show first 10 games with errors
            print(f"\nGame {game_info['game']} (Score: {game_info['final_score']}, Moves: {game_info['moves']}):")
            for error in game_info['errors'][:5]:  # Show first 5 errors per game
                print(f"  - {error}")
    else:
        print("✓ No errors found! Game appears to be bug-free.")


if __name__ == "__main__":
    main()

