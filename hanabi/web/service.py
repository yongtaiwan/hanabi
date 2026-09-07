"""Web-facing adapter around the real Hanabi engine and convention bots.

The browser never reimplements strategy logic.  This module translates JSON-shaped
positions into the engine's ``CommonView``/``PlayerView`` types and translates the
bot's concrete move plus ``why()`` narrative back into a stable web response.
"""

from __future__ import annotations

from collections import Counter
import copy
from dataclasses import dataclass
import random
import re
from typing import Any, Callable, Dict, Iterable, Optional

from hanabi.ai.dr_belief import InferredHand, InferredSlot, Playability
from hanabi.ai.dynamic_recommendation_3p import DynamicRecommendation3P
from hanabi.ai.five_player_recommendation import FivePlayerRecommendationPlayer
from hanabi.ai.four_player_recommendation import FourPlayerRecommendationPlayer
from hanabi.ai.three_player_recommendation import ThreePlayerRecommendationPlayer
from hanabi.core.card import Card, Suit
from hanabi.core.enums import Color, Number
from hanabi.core.game import (
    CommonView,
    Deck,
    Game,
    GameState,
    Hand,
    PlayerView,
    StartPosition,
    create_deck_from_settings,
    create_standard_game_settings,
)
from hanabi.core.game_field import GameField
from hanabi.core.game_history import GameHistory
from hanabi.core.moves import ColorHint, Discard, HasWhy, Move, NumberHint, Play
from hanabi.core.move_generation import generate_all_valid_moves
from hanabi.core.player import BasePlayer, PlayerTeam


COLORS = (Color.WHITE, Color.RED, Color.YELLOW, Color.GREEN, Color.BLUE)
COLOR_BY_CODE = {"W": Color.WHITE, "R": Color.RED, "Y": Color.YELLOW, "G": Color.GREEN, "B": Color.BLUE}
CODE_BY_COLOR = {value: key for key, value in COLOR_BY_CODE.items()}


@dataclass(frozen=True)
class BotSpec:
    key: str
    label: str
    players: int
    family: str
    modulus: int
    factory: Callable[[int], BasePlayer]
    recommendation_help: str


BOT_SPECS: Dict[str, BotSpec] = {
    "simple-3p": BotSpec(
        "simple-3p",
        "Simple Recommendation · 3 players",
        3,
        "Simple Recommendation",
        8,
        ThreePlayerRecommendationPlayer,
        "0 discard chop · 1–5 play C1–C5 · 6 keep chop and discard the lowest legal non-chop C-position · 7 no action",
    ),
    "simple-4p": BotSpec(
        "simple-4p",
        "Simple Recommendation · 4 players",
        4,
        "Simple Recommendation",
        12,
        FourPlayerRecommendationPlayer,
        "0 no action · 1–4 play C1–C4 · 5–8 discard C1–C4 · 9–11 no action",
    ),
    "simple-5p": BotSpec(
        "simple-5p",
        "Simple Recommendation · 5 players",
        5,
        "Simple Recommendation",
        16,
        FivePlayerRecommendationPlayer,
        "0 no action · 1–4 play C1–C4 · 5–8 discard useless C1–C4 · 9–12 discard dispensable C1–C4 · 13–15 no action",
    ),
    "dynamic-3p": BotSpec(
        "dynamic-3p",
        "Dynamic Recommendation · 3 players",
        3,
        "Dynamic Recommendation",
        8,
        DynamicRecommendation3P,
        "Track each C-position as unknown, playable, or unplayable, plus known 5s, chop, and chop confirmation",
    ),
}


@dataclass
class PlaySession:
    session_id: str
    spec: BotSpec
    game: Game
    players: list[BasePlayer]
    human_seat: int
    timeline: list[Dict[str, Any]]
    snapshots: list[Game]
    seed: int = 42


_PLAY_SESSIONS: Dict[str, PlaySession] = {}
_PLAY_SESSION_COUNTER = 0


def config_payload() -> Dict[str, Any]:
    return {
        "bots": [
            {
                "key": spec.key,
                "label": spec.label,
                "players": spec.players,
                "family": spec.family,
                "modulus": spec.modulus,
                "recommendationHelp": spec.recommendation_help,
            }
            for spec in BOT_SPECS.values()
        ],
        "colors": [{"code": CODE_BY_COLOR[color], "name": color.name.title()} for color in COLORS],
        "ranks": [1, 2, 3, 4, 5],
    }


def default_position(bot_key: str = "simple-3p") -> Dict[str, Any]:
    spec = _bot_spec(bot_key)
    source_hands = [
        ["R2", "Y3", "B4", "G5", "W1"],
        ["R1", "G2", "B3", "W4", "Y5"],
        ["Y1", "B2", "W3", "G4", "R5"],
        ["G1", "W2", "R3", "Y4"],
        ["B1", "Y2", "G3", "R4"],
    ]
    hand_size = 5 if spec.players == 3 else 4
    hands = [hand[:hand_size] for hand in source_hands[: spec.players]]
    remaining = [
        serialize_card(card)["code"]
        for card in create_deck_from_settings(create_standard_game_settings(spec.players)).cards
    ]
    for hand in hands:
        for code in hand:
            remaining.remove(code)
    random.Random(42).shuffle(remaining)
    return {
        "bot": bot_key,
        "seed": 42,
        "deckOrder": remaining,
        "actor": 0,
        "hands": hands,
        "fireworks": {code: 0 for code in COLOR_BY_CODE},
        "discards": [],
        "hintTokens": 8,
        "lifeTokens": 3,
        "deckCount": 50 - spec.players * hand_size,
        "memory": {
            "recommendation": None,
            "recommendations": [None for _ in range(spec.players)],
            "playsSinceHint": 0,
            "beliefs": _default_beliefs(spec.players, hand_size),
        },
    }


def analyze_position(payload: Dict[str, Any]) -> Dict[str, Any]:
    spec = _bot_spec(str(payload.get("bot", "simple-3p")))
    actor = _bounded_int(payload.get("actor", 0), 0, spec.players - 1, "actor")
    settings = create_standard_game_settings(spec.players)
    hands = _parse_hands(payload.get("hands"), spec.players, settings.max_cards_in_hand)
    common_view = _common_view_from_payload(payload, settings)
    _validate_card_multiplicity(hands, common_view, settings)

    player_view = PlayerView(
        teammates={seat: Hand(cards) for seat, cards in enumerate(hands) if seat != actor},
        own_hand_size=len(hands[actor]),
    )
    bot = spec.factory(actor)
    bot.set_game_settings(settings)
    bot.set_common_view(common_view)
    _apply_memory(bot, payload.get("memory") or {}, hands)

    recommendation = _current_recommendation(bot)
    move = bot.play(player_view)
    move_payload = serialize_move(move, hands)
    recommendation_after = _current_recommendation(bot)
    selected_step = _selected_action_step(spec, move, move_payload.get("why", ""), recommendation)
    move_payload = _explain_move_for_lab(
        spec,
        actor,
        move,
        move_payload,
        recommendation,
        common_view,
        bot,
    )
    trace = _action_trace(spec, selected_step)

    visible_hands = []
    for seat, cards in enumerate(hands):
        recommendation_code = None
        if hasattr(bot, "_get_recommendation_for_hand"):
            recommendation_code = bot._get_recommendation_for_hand(  # type: ignore[attr-defined]
                cards, common_view, settings
            )
        visible_hands.append(
            {
                "seat": seat,
                "recommendationCode": recommendation_code,
                "cards": [
                    {
                        **serialize_card(card),
                        "slot": index,
                        "kind": common_view.card_kind(card, settings).value,
                    }
                    for index, card in enumerate(cards)
                ],
            }
        )

    return {
        "bot": _spec_payload(spec),
        "actor": actor,
        "decision": move_payload,
        "selectedStep": selected_step,
        "trace": trace,
        "currentRecommendation": recommendation,
        "remainingRecommendation": recommendation_after,
        "hands": visible_hands,
        "state": serialize_public_state(common_view, hands, actor),
        "notice": (
            "The acting bot cannot see its own card identities. They are shown in the lab "
            "only so the scenario is inspectable."
        ),
    }


def recommendation_codes(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Calculate each visible hand's current Simple Recommendation code.

    This intentionally avoids asking the acting bot to choose a move.  The Lab's
    Auto control only needs the public hand classifier, so an unrelated move or
    memory-state failure should not prevent it from filling the ledger.
    """
    spec = _bot_spec(str(payload.get("bot", "simple-3p")))
    if spec.family != "Simple Recommendation":
        raise ValueError("automatic recommendation numbers are available for Simple Recommendation only")

    settings = create_standard_game_settings(spec.players)
    hands = _parse_hands(payload.get("hands"), spec.players, settings.max_cards_in_hand)
    common_view = _common_view_from_payload(payload, settings)
    _validate_card_multiplicity(hands, common_view, settings)

    bot = spec.factory(0)
    classifier = getattr(bot, "_get_recommendation_for_hand", None)
    if classifier is None:
        raise ValueError("this strategy does not expose Simple Recommendation numbers")

    return {
        "bot": _spec_payload(spec),
        "hands": [
            {
                "seat": seat,
                "recommendationCode": classifier(cards, common_view, settings),
            }
            for seat, cards in enumerate(hands)
        ],
    }


def simulate_game(payload: Dict[str, Any]) -> Dict[str, Any]:
    spec = _bot_spec(str(payload.get("bot", "simple-3p")))
    seed = _bounded_int(payload.get("seed", 42), 0, 2_147_483_647, "seed")
    settings = create_standard_game_settings(spec.players)
    field = GameField.create_from_settings(settings, seed=seed)
    players = [spec.factory(index) for index in range(spec.players)]
    game = GameField._create_game_from_start_position(field.start_position, PlayerTeam(players))

    timeline = [
        {
            "turn": 0,
            "state": serialize_game_state(game.state),
            "memory": _serialize_bot_memory(players, spec),
            "event": None,
        }
    ]
    safety_limit = 180
    while not game.is_finished and len(timeline) <= safety_limit:
        actor = game.current_player
        player = players[actor]
        view = game.get_player_view(actor)
        recommendation = _current_recommendation(player)
        move = player.play(view)
        event = serialize_move(move, game.state.player_hands)
        event = _explain_move_for_lab(
            spec,
            actor,
            move,
            event,
            recommendation,
            game.state.common_view,
            player,
        )
        before_deck = game.state.common_view.cards_to_draw
        before_lives = game.state.common_view.live_tokens
        if isinstance(move, (Play, Discard)):
            event["card"] = serialize_card(game.state.player_hands[actor].cards[move.card])
        game.process_move(actor, move)
        if game.state.common_view.live_tokens < before_lives:
            event["lostLife"] = before_lives - game.state.common_view.live_tokens
        if game.state.common_view.cards_to_draw < before_deck:
            event["drawnCard"] = serialize_card(game.state.player_hands[actor].cards[-1])
        game._advance_turn()
        timeline.append(
            {
                "turn": len(timeline),
                "state": serialize_game_state(game.state),
                "memory": _serialize_bot_memory(players, spec),
                "event": {**event, "actor": actor},
            }
        )

    if len(timeline) > safety_limit and not game.is_finished:
        raise ValueError("simulation exceeded the safety move limit")
    return {
        "bot": _spec_payload(spec),
        "seed": seed,
        "score": game.get_score(),
        "moves": len(timeline) - 1,
        "timeline": timeline,
    }


def start_play_game(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Start a browser-local game with one human seat and convention bots."""
    global _PLAY_SESSION_COUNTER

    spec = _bot_spec(str(payload.get("bot", "simple-3p")))
    seed = _bounded_int(payload.get("seed", 42), 0, 2_147_483_647, "seed")
    human_seat = _bounded_int(payload.get("humanSeat", 0), 0, spec.players - 1, "human seat")
    settings = create_standard_game_settings(spec.players)
    field = GameField.create_from_settings(settings, seed=seed)
    players = [spec.factory(index) for index in range(spec.players)]
    game = GameField._create_game_from_start_position(field.start_position, PlayerTeam(players))

    _PLAY_SESSION_COUNTER += 1
    session_id = f"play-{_PLAY_SESSION_COUNTER}"
    timeline = [
        {
            "turn": 0,
            "state": serialize_game_state(game.state),
            "memory": _serialize_bot_memory(players, spec),
            "event": None,
        }
    ]
    session = PlaySession(session_id, spec, game, players, human_seat, timeline, [copy.deepcopy(game)], seed)
    # A browser tab only needs one active playthrough. Clearing older sessions keeps
    # repeated New game clicks from retaining entire game histories in Pyodide.
    _PLAY_SESSIONS.clear()
    _PLAY_SESSIONS[session_id] = session
    recent_start = len(timeline)
    _run_bots_until_human(session)
    return _play_session_payload(session, recent_start)


def play_game_move(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Apply one legal human move, then let bots act until the human's next turn."""
    session_id = str(payload.get("sessionId", ""))
    session = _PLAY_SESSIONS.get(session_id)
    if session is None:
        raise ValueError("this play session is no longer active; start a new game")
    if session.game.is_finished:
        raise ValueError("this game is already finished")
    if session.game.current_player != session.human_seat:
        raise ValueError("wait for the bots to finish before making another move")

    legal_moves = _legal_human_moves(session)
    selected = _match_human_move(payload.get("move"), legal_moves, session.game.state.player_hands)
    recent_start = len(session.timeline)
    _record_play_session_move(session, session.human_seat, selected, human=True)
    _run_bots_until_human(session)
    return _play_session_payload(session, recent_start)


def ask_play_bot(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Return the configured bot's move for the human seat without changing the game."""
    session_id = str(payload.get("sessionId", ""))
    session = _PLAY_SESSIONS.get(session_id)
    if session is None:
        raise ValueError("this play session is no longer active; start a new game")
    if session.game.is_finished:
        raise ValueError("this game is already finished")
    if session.game.current_player != session.human_seat:
        raise ValueError("wait until it is your turn to ask the bot")

    advisory_game = copy.deepcopy(session.game)
    actor = session.human_seat
    bot = advisory_game.team.players[actor]
    recommendation = _current_recommendation(bot)
    move = bot.play(advisory_game.get_player_view(actor))
    move_payload = serialize_move(move, advisory_game.state.player_hands)
    selected_step = _selected_action_step(
        session.spec, move, move_payload.get("why", ""), recommendation
    )
    move_payload = _explain_move_for_lab(
        session.spec,
        actor,
        move,
        move_payload,
        recommendation,
        advisory_game.state.common_view,
        bot,
    )
    return {
        "bot": _spec_payload(session.spec),
        "actor": actor,
        "decision": move_payload,
        "selectedStep": selected_step,
        "trace": _action_trace(session.spec, selected_step),
        "currentRecommendation": recommendation,
        "remainingRecommendation": _current_recommendation(bot),
    }


def rewind_play_game(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Restore an earlier human decision point and discard the later branch."""
    session_id = str(payload.get("sessionId", ""))
    session = _PLAY_SESSIONS.get(session_id)
    if session is None:
        raise ValueError("this play session is no longer active; start a new game")
    turn = _bounded_int(payload.get("turn", -1), 0, len(session.snapshots) - 1, "turn")
    snapshot = session.snapshots[turn]
    if snapshot.is_finished or snapshot.current_player != session.human_seat:
        raise ValueError("choose a rewind point immediately before one of your moves")

    session.game = copy.deepcopy(snapshot)
    session.players = session.game.team.players
    session.timeline = session.timeline[: turn + 1]
    session.snapshots = session.snapshots[: turn + 1]
    return _play_session_payload(session, len(session.timeline))


def restore_play_game(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Rebuild a downloaded game using its seed and legal human choices, never pickle."""
    moves = payload.get("humanMoves", [])
    if not isinstance(moves, list) or len(moves) > 180:
        raise ValueError("the saved game must contain at most 180 human moves")
    previous = dict(_PLAY_SESSIONS)
    try:
        result = start_play_game(payload)
        for move in moves:
            result = play_game_move({"sessionId": result["sessionId"], "move": move})
        return result
    except Exception:
        _PLAY_SESSIONS.clear()
        _PLAY_SESSIONS.update(previous)
        raise


def recording_play_game(payload: Dict[str, Any]) -> Dict[str, Any]:
    previous = dict(_PLAY_SESSIONS)
    try:
        return restore_play_game(payload)
    finally:
        _PLAY_SESSIONS.clear()
        _PLAY_SESSIONS.update(previous)


def validate_position(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize an imported position without asking a bot to act."""
    spec = _bot_spec(str(payload.get("bot", "simple-3p")))
    settings = create_standard_game_settings(spec.players)
    hands = _parse_hands(payload.get("hands"), spec.players, settings.max_cards_in_hand)
    common = _common_view_from_payload(payload, settings)
    _validate_card_multiplicity(hands, common, settings)
    remaining = create_deck_from_settings(settings).cards
    used = [card for hand in hands for card in hand] + _expanded_discards(common)
    for color, top in common.cards_played.items():
        used.extend(Card(color, Number(rank)) for rank in range(1, top.value + 1))
    for card in used:
        remaining.remove(card)
    order = [_parse_card(code) for code in payload.get("deckOrder", [])]
    if Counter(order) != Counter(remaining):
        raise ValueError("The saved deck must contain every remaining card exactly once.")
    actor = _bounded_int(payload.get("actor", 0), 0, spec.players - 1, "actor")
    players = [spec.factory(seat) for seat in range(spec.players)]
    for player in players:
        player.set_game_settings(settings)
        player.set_common_view(common)
        _apply_memory(player, payload.get("memory") or {}, hands)
    memory = _serialize_bot_memory(players, spec)
    memory.setdefault("beliefs", _default_beliefs(spec.players, settings.max_cards_in_hand))
    memory.setdefault("recommendations", [None] * spec.players)
    memory.setdefault("playsSinceHint", 0)
    return {
        "bot": spec.key, "actor": actor, "seed": _bounded_int(payload.get("seed", 42), 0, 2147483647, "seed"),
        "hands": [[serialize_card(card)["code"] for card in hand] for hand in hands],
        "fireworks": {
            CODE_BY_COLOR[color]: common.cards_played[color].value
            if color in common.cards_played
            else 0
            for color in COLORS
        },
        "discards": [serialize_card(card)["code"] for card in _expanded_discards(common)],
        "hintTokens": common.hint_tokens, "lifeTokens": common.live_tokens,
        "deckCount": len(order), "deckOrder": [serialize_card(card)["code"] for card in order], "memory": memory,
    }


def _run_bots_until_human(session: PlaySession) -> None:
    while not session.game.is_finished and session.game.current_player != session.human_seat:
        actor = session.game.current_player
        move = session.players[actor].play(session.game.get_player_view(actor))
        _record_play_session_move(session, actor, move, human=False)


def _record_play_session_move(session: PlaySession, actor: int, move: Move, *, human: bool) -> None:
    game = session.game
    recommendation = _current_recommendation(session.players[actor])
    event = serialize_move(move, game.state.player_hands)
    if human:
        event["why"] = (
            "You chose this move. Every bot observes the same public action and updates its "
            "convention state before the next turn."
        )
        event["conventionDetails"] = [
            "This action was chosen by you, so no bot decision rule was applied.",
            "The resulting play, discard, or hint is public and updates every bot's stored state.",
        ]
        event["human"] = True
    else:
        event = _explain_move_for_lab(
            session.spec,
            actor,
            move,
            event,
            recommendation,
            game.state.common_view,
            session.players[actor],
        )

    before_deck = game.state.common_view.cards_to_draw
    before_lives = game.state.common_view.live_tokens
    if isinstance(move, (Play, Discard)):
        event["card"] = serialize_card(game.state.player_hands[actor].cards[move.card])
    game.process_move(actor, move)
    if game.state.common_view.live_tokens < before_lives:
        event["lostLife"] = before_lives - game.state.common_view.live_tokens
    if game.state.common_view.cards_to_draw < before_deck:
        event["drawnCard"] = serialize_card(game.state.player_hands[actor].cards[-1])
    game._advance_turn()
    session.timeline.append(
        {
            "turn": len(session.timeline),
            "state": serialize_game_state(game.state),
            "memory": _serialize_bot_memory(session.players, session.spec),
            "event": {**event, "actor": actor},
        }
    )
    session.snapshots.append(copy.deepcopy(game))


def _legal_human_moves(session: PlaySession) -> list[Move]:
    game = session.game
    if game.is_finished or game.current_player != session.human_seat:
        return []
    player_view = game.get_player_view(session.human_seat)
    candidates = generate_all_valid_moves(
        player_view,
        game.state.common_view,
        game.settings,
        session.human_seat,
    )
    advisor = session.players[session.human_seat]
    return [move for move in candidates if advisor.is_move_legal(player_view, move)]


def _match_human_move(value: Any, legal_moves: list[Move], hands: Iterable[Any]) -> Move:
    if not isinstance(value, dict):
        raise ValueError("choose a play, discard, or hint")
    requested_type = str(value.get("type", ""))
    for move in legal_moves:
        candidate = serialize_move(move, hands)
        if requested_type != candidate["type"]:
            continue
        if requested_type in {"play", "discard"}:
            try:
                requested_slot = int(value.get("slot", -1))
            except (TypeError, ValueError):
                continue
            if requested_slot == candidate["slot"]:
                return move
        elif requested_type == "hint":
            try:
                requested_target = int(value.get("target", -1))
            except (TypeError, ValueError):
                continue
            if (
                requested_target == candidate["target"]
                and str(value.get("hintType", "")) == candidate["hintType"]
                and str(value.get("value", "")) == str(candidate["value"])
            ):
                return move
    raise ValueError("that move is not legal in the current position")


def _play_session_payload(session: PlaySession, recent_start: int) -> Dict[str, Any]:
    legal = _legal_human_moves(session)
    return {
        "sessionId": session.session_id,
        "seed": session.seed,
        "resume": {
            "bot": session.spec.key,
            "seed": session.seed,
            "humanSeat": session.human_seat,
            "humanMoves": [frame["event"] for frame in session.timeline if (frame.get("event") or {}).get("human")],
        },
        "bot": _spec_payload(session.spec),
        "humanSeat": session.human_seat,
        "score": session.game.get_score(),
        "moves": len(session.timeline) - 1,
        "finished": session.game.is_finished,
        "timeline": session.timeline,
        "recentEvents": [
            frame["event"]
            for frame in session.timeline[recent_start:]
            if frame.get("event") is not None
        ],
        "legalMoves": [serialize_move(move, session.game.state.player_hands) for move in legal],
    }


def card_kind_matrix(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Classify every color/rank choice from the current public board."""
    spec = _bot_spec(str(payload.get("bot", "simple-3p")))
    settings = create_standard_game_settings(spec.players)
    common = _common_view_from_payload(payload, settings)
    return {
        "kinds": {
            CODE_BY_COLOR[color]: {
                str(number.value): common.card_kind(Card(color, number), settings).value
                for number in Number
            }
            for color in COLORS
        }
    }


def likely_position(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Sample a real midgame frame from a seeded current-bot game history."""
    bot_key = str(payload.get("bot", "simple-3p"))
    seed = _bounded_int(payload.get("seed", 42), 0, 2_147_483_647, "seed")
    simulated = simulate_game({"bot": bot_key, "seed": seed})
    timeline = simulated["timeline"]
    last_playable = max(1, len(timeline) - 2)
    low = min(last_playable, max(4, round(last_playable * 0.18)))
    high = max(low, min(last_playable, round(last_playable * 0.78)))
    index = round(random.Random(seed ^ 0x48414E41).triangular(low, high, (low + high) / 2))
    frame = timeline[index]
    board = frame["state"]
    position = {
        "bot": bot_key,
        "seed": seed,
        "deckOrder": [card["code"] for card in board["deckOrder"]],
        "actor": board["currentPlayer"],
        "hands": [[card["code"] for card in hand] for hand in board["hands"]],
        "fireworks": board["fireworks"],
        "discards": [card["code"] for card in board["discards"]],
        "hintTokens": board["hintTokens"],
        "lifeTokens": board["lifeTokens"],
        "deckCount": board["deckCount"],
        "memory": frame["memory"],
    }
    return {
        "position": position,
        "source": {
            "seed": seed,
            "turn": index,
            "score": board["score"],
            "gameMoves": simulated["moves"],
        },
    }


def continue_position(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Let the selected bot family finish an inspectable custom position."""
    spec = _bot_spec(str(payload.get("bot", "simple-3p")))
    seed = _bounded_int(payload.get("seed", 42), 0, 2_147_483_647, "seed")
    settings = create_standard_game_settings(spec.players)
    hands = _parse_hands(payload.get("hands"), spec.players, settings.max_cards_in_hand)
    common = _common_view_from_payload(payload, settings)
    _validate_card_multiplicity(hands, common, settings)

    used_cards = [card for hand in hands for card in hand]
    used_cards.extend(_expanded_discards(common))
    for color, top in common.cards_played.items():
        used_cards.extend(Card(color, Number(rank)) for rank in range(1, top.value + 1))
    remaining = create_deck_from_settings(settings).cards
    for card in used_cards:
        remaining.remove(card)
    if len(remaining) != common.cards_to_draw:
        raise ValueError(
            f"deck count must be {len(remaining)} for these hands, fireworks, and discards"
        )
    raw_deck_order = payload.get("deckOrder")
    if raw_deck_order is None:
        random.Random(seed).shuffle(remaining)
    else:
        if not isinstance(raw_deck_order, list):
            raise ValueError("deckOrder must be a list of card codes")
        ordered_remaining = [_parse_card(value) for value in raw_deck_order]
        if Counter(ordered_remaining) != Counter(remaining):
            raise ValueError("deckOrder must contain every remaining deck card exactly once")
        remaining = ordered_remaining
    start_position = StartPosition(settings, Deck(used_cards + remaining))
    actor = _bounded_int(payload.get("actor", 0), 0, spec.players - 1, "actor")
    turns_left = spec.players if not remaining else None
    game_state = GameState(
        start_position=start_position,
        common_view=common,
        player_hands=[Hand(hand) for hand in hands],
        draw_deck_index=len(used_cards),
        turn_number=0,
        current_player=actor,
        turns_left=turns_left,
    )
    players = [spec.factory(index) for index in range(spec.players)]
    game = Game(start_position, PlayerTeam(players))
    game._turns.append(game_state)
    game._set_common_view_for_players()
    for player in players:
        _apply_memory(player, payload.get("memory") or {}, hands)

    timeline = [
        {
            "turn": 0,
            "state": serialize_game_state(game.state),
            "memory": _serialize_bot_memory(players, spec),
            "event": None,
        }
    ]
    while not game.is_finished:
        current = game.current_player
        player = players[current]
        recommendation = _current_recommendation(player)
        move = player.play(game.get_player_view(current))
        event = serialize_move(move, game.state.player_hands)
        event = _explain_move_for_lab(
            spec,
            current,
            move,
            event,
            recommendation,
            game.state.common_view,
            player,
        )
        before_deck = game.state.common_view.cards_to_draw
        before_lives = game.state.common_view.live_tokens
        if isinstance(move, (Play, Discard)):
            event["card"] = serialize_card(game.state.player_hands[current].cards[move.card])
        game.process_move(current, move)
        if game.state.common_view.live_tokens < before_lives:
            event["lostLife"] = before_lives - game.state.common_view.live_tokens
        if game.state.common_view.cards_to_draw < before_deck:
            event["drawnCard"] = serialize_card(game.state.player_hands[current].cards[-1])
        game._advance_turn()
        timeline.append(
            {
                "turn": len(timeline),
                "state": serialize_game_state(game.state),
                "memory": _serialize_bot_memory(players, spec),
                "event": {**event, "actor": current},
            }
        )
    return {
        "bot": _spec_payload(spec),
        "seed": seed,
        "score": game.get_score(),
        "moves": len(timeline) - 1,
        "continuedFromPosition": True,
        "truncated": False,
        "timeline": timeline,
    }


def _serialize_bot_memory(players: list[BasePlayer], spec: BotSpec) -> Dict[str, Any]:
    memory: Dict[str, Any] = {
        "recommendation": None,
        "recommendations": [None for _ in players],
        "playsSinceHint": int(getattr(players[0], "_plays_since_hint", 0)),
    }
    if spec.family == "Simple Recommendation":
        memory["recommendations"] = [
            player._recommendation_for_seat(player.player_index)  # type: ignore[attr-defined]
            for player in players
        ]
        return memory

    inferred = players[0]._inferred_hands  # type: ignore[attr-defined]
    memory["beliefs"] = [
        {
            "slots": [
                {
                    "playability": slot.playability.value,
                    "knownFive": slot.known_five,
                }
                for slot in hand.cards
            ],
            "chop": hand.chop,
            "chopConfirmed": hand.chop_confirmed,
        }
        for hand in inferred
    ]
    return memory


def replay_history(payload: Dict[str, Any]) -> Dict[str, Any]:
    history = _history_payload(payload)
    settings = GameHistory.settings_from_history_dict(history)
    spec = _replay_bot_spec(payload.get("bot"), history, settings.num_players)
    players = [spec.factory(index) for index in range(settings.num_players)]
    game = GameHistory.create_game_from_history(history, PlayerTeam(players))
    timeline = [
        {
            "turn": 0,
            "state": serialize_game_state(game.state),
            "memory": _serialize_bot_memory(players, spec),
            "event": None,
        }
    ]
    memory_available = True

    for turn_index, move_text in enumerate(history.get("moves", []), start=1):
        if game.is_finished:
            break
        actor = game.current_player
        predicted = None
        prediction_error = None
        recommendation = _current_recommendation(players[actor])
        # A predicted move may consume its recommendation. Do not mutate the
        # historical player's memory unless that action was actually recorded.
        advisor = copy.deepcopy(players[actor])
        try:
            predicted = advisor.play(game.get_player_view(actor))
        except (AssertionError, ValueError, KeyError) as error:
            prediction_error = str(error)
        recorded = GameHistory._short_to_move(str(move_text), actor, game)
        if recorded is None:
            raise ValueError(f"cannot parse recorded move {turn_index}: {move_text!r}")
        actual = serialize_move(recorded, game.state.player_hands)
        before_deck = game.state.common_view.cards_to_draw
        before_lives = game.state.common_view.live_tokens
        if isinstance(recorded, (Play, Discard)):
            actual["card"] = serialize_card(game.state.player_hands[actor].cards[recorded.card])
        prediction = serialize_move(predicted, game.state.player_hands) if predicted is not None else None
        if prediction is not None:
            prediction = _explain_move_for_lab(
                spec,
                actor,
                predicted,
                prediction,
                recommendation,
                game.state.common_view,
                advisor,
            )
        agrees = _moves_equivalent(predicted, recorded) if predicted is not None else None
        if prediction is None:
            actual["why"] = (
                "Recorded move. A current-strategy explanation is unavailable at this turn because "
                "the saved history does not match the bot's present internal convention state."
            )
        elif agrees:
            actual["why"] = prediction.get("why", "")
            actual["technicalWhy"] = prediction.get("technicalWhy", "")
            actual["conventionDetails"] = prediction.get("conventionDetails", [])
        else:
            actual["why"] = (
                f"Recorded move. Current {spec.label} would choose {prediction['label']}: "
                f"{prediction.get('why', '')}"
            )
            actual["conventionDetails"] = prediction.get("conventionDetails", [])
        actual["agreesWithCurrentBot"] = agrees
        turns_before = len(game._turns)
        observation_error = None
        try:
            game.process_move(actor, recorded)
        except AssertionError as error:
            if len(game._turns) != turns_before + 1:
                raise
            # The state transition succeeded; only a current bot's observation hook rejected
            # a legacy convention signal. Keep the historical replay viewable.
            observation_error = str(error)
        if game.state.common_view.live_tokens < before_lives:
            actual["lostLife"] = before_lives - game.state.common_view.live_tokens
        if game.state.common_view.cards_to_draw < before_deck:
            actual["drawnCard"] = serialize_card(game.state.player_hands[actor].cards[-1])
        if prediction_error or observation_error:
            actual["compatibilityNote"] = prediction_error or observation_error
        if observation_error:
            memory_available = False
        game._advance_turn()
        timeline.append(
            {
                "turn": turn_index,
                "state": serialize_game_state(game.state),
                "memory": _serialize_bot_memory(players, spec) if memory_available else None,
                "event": {**actual, "actor": actor, "recorded": str(move_text)},
            }
        )

    return {
        "bot": _spec_payload(spec),
        "score": game.get_score(),
        "moves": len(timeline) - 1,
        "recordedScore": history.get("final_score"),
        "timeline": timeline,
    }


def serialize_game_state(state) -> Dict[str, Any]:
    common = state.common_view
    settings = state.start_position.settings

    def serialize_visible_card(card: Card) -> Dict[str, Any]:
        return {
            **serialize_card(card),
            "kind": common.card_kind(card, settings).value,
        }

    return {
        "currentPlayer": state.current_player,
        "turnNumber": state.turn_number,
        "hintTokens": common.hint_tokens,
        "lifeTokens": common.live_tokens,
        "deckCount": common.cards_to_draw,
        "score": state.score(),
        "finished": state.is_finished(),
        "turnsLeft": state.turns_left,
        "finishReason": (
            "All lives were lost." if common.live_tokens <= 0 else
            "All five fireworks are complete." if state.score() == 25 else
            "The deck is empty and every final turn has been played." if state.turns_left == 0 else
            "No further points are possible." if state.is_finished() else None
        ),
        "fireworks": {
            CODE_BY_COLOR[color]: common.cards_played[color].value
            if color in common.cards_played
            else 0
            for color in COLORS
        },
        "discards": [serialize_card(card) for card in _expanded_discards(common)],
        "hands": [[serialize_visible_card(card) for card in hand.cards] for hand in state.player_hands],
        "deckOrder": [
            serialize_visible_card(card)
            for card in state.start_position.draw_deck.cards[state.draw_deck_index:]
        ],
    }


def serialize_public_state(common: CommonView, hands: list[list[Card]], actor: int) -> Dict[str, Any]:
    return {
        "currentPlayer": actor,
        "hintTokens": common.hint_tokens,
        "lifeTokens": common.live_tokens,
        "deckCount": common.cards_to_draw,
        "score": sum(number.value for number in common.cards_played.values()),
        "fireworks": {
            CODE_BY_COLOR[color]: common.cards_played[color].value
            if color in common.cards_played
            else 0
            for color in COLORS
        },
        "discards": [serialize_card(card) for card in _expanded_discards(common)],
        "hands": [[serialize_card(card) for card in hand] for hand in hands],
    }


def serialize_card(card: Card) -> Dict[str, Any]:
    code = f"{CODE_BY_COLOR[card.color]}{card.number.value}"
    return {"code": code, "color": CODE_BY_COLOR[card.color], "rank": card.number.value}


def serialize_move(move: Move, hands: Iterable[Any]) -> Dict[str, Any]:
    why = move.why() if isinstance(move, HasWhy) else ""
    if isinstance(move, Play):
        return {"type": "play", "slot": move.card, "label": f"Play C{move.card + 1}", "why": why}
    if isinstance(move, Discard):
        return {"type": "discard", "slot": move.card, "label": f"Discard C{move.card + 1}", "why": why}
    if isinstance(move, ColorHint):
        return {
            "type": "hint",
            "hintType": "color",
            "target": move.teammate,
            "value": CODE_BY_COLOR[move.color],
            "cards": move.cards,
            "label": f"Hint P{move.teammate + 1} {move.color.name.title()}",
            "why": why,
        }
    if isinstance(move, NumberHint):
        return {
            "type": "hint",
            "hintType": "number",
            "target": move.teammate,
            "value": move.number.value,
            "cards": move.cards,
            "label": f"Hint P{move.teammate + 1} {move.number.value}",
            "why": why,
        }
    raise TypeError(f"unsupported move type: {type(move).__name__}")


def _explain_move_for_lab(
    spec: BotSpec,
    actor: int,
    move: Move,
    payload: Dict[str, Any],
    recommendation: Optional[int],
    common: CommonView,
    bot: BasePlayer,
) -> Dict[str, Any]:
    """Replace terse strategy logging with a learner-facing convention explanation."""
    technical = str(payload.get("why", ""))
    if spec.family == "Simple Recommendation":
        why, details = _explain_simple_move(
            spec, actor, move, payload, recommendation, common, technical
        )
    else:
        why, details = _explain_dynamic_move(
            actor, move, payload, common, technical, bot
        )
    payload["technicalWhy"] = technical
    payload["why"] = why
    payload["conventionDetails"] = details
    return payload


def _explain_simple_move(
    spec: BotSpec,
    actor: int,
    move: Move,
    payload: Dict[str, Any],
    recommendation: Optional[int],
    common: CommonView,
    technical: str,
) -> tuple[str, list[str]]:
    player = f"P{actor + 1}"
    modulus = spec.modulus

    if isinstance(move, Play):
        slot = move.card + 1
        if recommendation is not None and recommendation == slot:
            if "one play since hint" in technical:
                freshness = (
                    "Exactly one card has been played since the hint, and the team has lost "
                    "fewer than two lives, so the convention still permits the delayed play."
                )
            else:
                freshness = (
                    "No card has been played since the hint, so the instruction is still fresh."
                )
            why = (
                f"{player} cannot see the identity of C{slot}, but the stored "
                f"recommendation is {recommendation}, and that recommendation number names the "
                f"matching C-position. {freshness} That is why {player} plays C{slot}."
            )
            return why, [
                f"Stored recommendation: {recommendation} → play C{slot}.",
                f"Freshness check: passed with {common.live_tokens} lives remaining.",
                "The play consumes the acting player's stored recommendation; then the hand "
                "positions shift and a replacement enters the rightmost open position if the "
                "deck is nonempty.",
            ]
        why = (
            f"No fresh stored recommendation to play, worthwhile prescribed-channel hint, or legal discard ranked "
            f"above the fallback. The convention therefore uses its last resort and plays "
            f"C{slot}; this is a forced convention fallback, not knowledge of the card's identity."
        )
        return why, [
            "Higher-priority recommendation and hint checks did not produce a legal move.",
            "At a full hint bank, discarding is illegal, so the final fallback is a play.",
        ]

    if isinstance(move, Discard):
        slot = move.card + 1
        if spec.key == "simple-3p" and recommendation == 0:
            why = (
                f"{player}'s stored recommendation is 0. In the three-player convention, "
                f"0 says the chop—currently C{slot}—is safe to discard. {player} follows that "
                "instruction and regains a hint token."
            )
            return why, [
                f"Stored recommendation: 0 → discard the chop at C{slot}.",
                "The discard consumes the acting player's stored recommendation; then the hand positions shift.",
            ]
        if spec.key == "simple-3p" and recommendation == 6:
            why = (
                f"{player}'s stored recommendation is 6. That recommendation number protects the chop and instead "
                f"points to the lowest legal non-chop position, C{slot}. {player} discards C{slot} "
                "and regains a hint token."
            )
            return why, [
                f"Stored recommendation: 6 → keep the chop and discard C{slot}.",
                "The discard consumes the acting player's stored recommendation; then the C-positions shift.",
            ]
        if spec.key == "simple-4p" and recommendation is not None and 5 <= recommendation <= 8:
            why = (
                f"{player}'s stored recommendation is {recommendation}. In the four-player "
                f"mapping, recommendation numbers 5–8 identify a safe discard at C1–C4, so {recommendation} points to "
                f"C{slot}. {player} discards it and regains a hint token."
            )
            return why, [
                f"Stored recommendation: {recommendation} → safe discard at C{slot}.",
                "The discard consumes the acting player's stored recommendation; then the hand positions shift.",
            ]
        if spec.key == "simple-5p" and recommendation is not None and 5 <= recommendation <= 12:
            kind = "useless" if recommendation <= 8 else "dispensable"
            number_range = "5–8" if kind == "useless" else "9–12"
            meaning = (
                "no longer helps any firework"
                if kind == "useless"
                else "has another available copy, so losing this copy does not end the perfect-score path"
            )
            why = (
                f"{player}'s stored recommendation is {recommendation}. Five-player recommendation numbers "
                f"{number_range} mark a {kind} card at C1–C4, so {recommendation} points to C{slot}. "
                f"The convention says that card {meaning}; {player} discards it and regains a hint token."
            )
            return why, [
                f"Stored recommendation: {recommendation} → discard the {kind} card at C{slot}.",
                "The discard consumes the acting player's stored recommendation; then the hand positions shift.",
            ]
        why = (
            f"No fresh stored recommendation to play or useful prescribed-channel hint applies. With room in "
            f"the hint bank, the convention's default is to discard C{slot} and recover a hint token."
        )
        return why, [
            "The bot checked the higher-priority play and hint rules first.",
            f"Default discard: C{slot}; hint tokens before the move: {common.hint_tokens}.",
        ]

    channel_match = re.search(r"Hint channel (\d+)", technical)
    channel = int(channel_match.group(1)) if channel_match else None
    codes = [(int(seat), int(code)) for seat, code in re.findall(r"P(\d+):(\d+)", technical)]
    score = {
        name: int(value)
        for name, value in re.findall(
            r"(new_plays|new_discards|new_useless|new_disp|saves|flips)=(\d+)",
            technical,
        )
    }
    tier_match = re.search(r"\[(strong|medium|weak)\]", technical)
    tier = tier_match.group(1) if tier_match else "useful"
    effects = _simple_hint_effects(score)
    effect_text = _natural_join(effects) if effects else "creates an other change in the public recommendations"
    hint_text = _hint_action_text(actor, payload)
    why = (
        f"{hint_text}. This is an encoded convention hint, not only literal card information. "
        f"The non-givers' public recommendation numbers add to channel {channel} modulo {modulus}, "
        f"and the target, hint value, and touched positions express that exact channel. "
        f"Each receiver can subtract the other visible recommendation numbers to recover the recommendation for "
        f"their own hidden hand. The bot sends it now because it {effect_text}."
    )
    code_values = [code for _, code in codes]
    details = [
        "Public recommendation numbers: " + ", ".join(f"P{seat} = {code}" for seat, code in codes) + ".",
        f"Encoding: ({' + '.join(str(code) for code in code_values)}) modulo {modulus} = channel {channel}.",
        f"Physical hint: {_hint_touch_description(payload)}.",
        f"Priority: {tier} hint because it {effect_text}.",
    ]
    return why, details


def _simple_hint_effects(score: Dict[str, int]) -> list[str]:
    labels = {
        "new_plays": "creates {n} new play{suffix}",
        "new_discards": "creates {n} new discard{suffix}",
        "new_useless": "creates {n} new discard{suffix} for useless cards",
        "new_disp": "creates {n} new discard{suffix} for dispensable cards",
        "saves": "creates {n} save{suffix}",
        "flips": "creates {n} other change{suffix}",
    }
    effects = []
    for key, template in labels.items():
        value = score.get(key, 0)
        if value:
            effects.append(template.format(n=value, suffix="" if value == 1 else "s"))
    return effects


def _explain_dynamic_move(
    actor: int,
    move: Move,
    payload: Dict[str, Any],
    common: CommonView,
    technical: str,
    bot: BasePlayer,
) -> tuple[str, list[str]]:
    player = f"P{actor + 1}"
    own_belief = None
    inferred = getattr(bot, "_inferred_hands", None)
    if isinstance(inferred, list) and actor < len(inferred):
        own_belief = inferred[actor]

    if isinstance(move, Play):
        slot = move.card + 1
        if "identified playable" in technical:
            why = (
                f"The shared Dynamic convention state marks {player}'s C{slot} as playable. "
                f"After first checking whether the next player needs protection, the policy plays "
                f"the leftmost marked playable card. That is why {player} plays C{slot}, even though "
                "the player cannot see its identity."
            )
            return why, [
                f"Public state: C{slot} is marked playable.",
                "Priority order: protect the next player first, then play the leftmost marked playable card.",
            ]
        if "known 5" in technical:
            why = (
                f"Every unfinished firework is waiting for a 5, and the public convention state "
                f"marks C{slot} as a known 5. That makes C{slot} guaranteed playable, so {player} plays it."
            )
            return why, [
                f"Public state: C{slot} is known to be a 5.",
                "Board check: every unfinished color currently needs its 5.",
            ]
        if "Endgame play" in technical:
            why = (
                f"The deck is empty and {common.live_tokens} lives remain. With no known play or "
                f"better final-round hint available, the Dynamic endgame policy uses the spare life "
                f"to try the newest unknown card, C{slot}, for one more point."
            )
            return why, [
                "Final-round goal: maximize remaining scoring chances.",
                f"C{slot} is the newest unknown card; this gamble is allowed only with more than one life.",
            ]
        return (
            f"The Dynamic policy's higher-priority checks select C{slot} as the best available play.",
            [f"Selected public C-position: C{slot}."],
        )

    if isinstance(move, Discard):
        slot = move.card + 1
        confirmed = "confirmed" in technical
        if "token gift" in technical:
            why = (
                f"The next player is about to risk an important card but there are no hint tokens. "
                f"{player}'s confirmed chop is C{slot}, so the convention discards it to create one "
                "hint token. That token changes the next player's safest convention action and protects the card."
            )
            return why, [
                "Protection check: the next player's planned discard is dangerous.",
                f"Token gift: discard confirmed chop C{slot} so the next player can hint instead.",
            ]
        if "no chop assigned" in technical:
            why = (
                f"No higher-priority play, protective move, convention hint, or chop discard is "
                f"available. The Dynamic convention therefore discards the oldest legal card, C{slot}, "
                "and recovers a hint token."
            )
            return why, ["Final fallback: discard the oldest legal C-position."],
        chop_status = "confirmed" if confirmed else "default"
        if common.cards_to_draw == 0:
            context = "The deck is empty, and no remaining play or score-improving hint is available."
        elif common.hint_tokens == 0:
            context = "There is no hint token available, so the hint branch cannot be used."
        else:
            context = "The projected encoded hint does not outrank this chop under the Dynamic hint-versus-chop rule."
        why = (
            f"{player} has no convention-marked playable card to use first. {context} The current "
            f"chop is C{slot} and its status is {chop_status}, so the policy discards C{slot} and "
            "recovers a hint token."
        )
        details = [
            f"Public chop state: C{slot}, {chop_status}.",
            "Dynamic choice: compare the projected hint with the current chop, then take the higher-priority option.",
        ]
        if own_belief is not None:
            marked = [
                f"C{i + 1}"
                for i, belief in enumerate(own_belief.cards)
                if belief.playability.value == "playable"
            ]
            details.append("Marked playable cards: " + (", ".join(marked) if marked else "none") + ".")
        return why, details

    type_match = re.search(r"type=(\d+) \(([0-9+]+)\)", technical)
    if type_match is None:
        type_match = re.search(r"unavailable type=(\d+), ([0-9+]+)", technical)
    channel = int(type_match.group(1)) if type_match else None
    peer_codes = [int(value) for value in type_match.group(2).split("+")] if type_match else []
    if "Protect next" in technical:
        reason = "the next player is otherwise likely to discard a dangerous card, and this decoded update prevents it"
    elif "identifies playable for next" in technical:
        reason = "it newly marks a playable card for the next player"
    elif "trash for next + playable for prev" in technical:
        reason = "it gives the next player a safe trash discard and marks a playable card for the previous player"
    elif "known-5 assist" in technical:
        reason = "the literal 5 information and decoded update together reveal a useful 5 plus a play or safe discard"
    elif "Endgame hint" in technical:
        reason = "the deck is empty and this is the best remaining way to create another scoring chance"
    elif "fine/confirmed" in technical:
        reason = (
            "the projected update is useful enough at this board stage to preserve tempo "
            "despite the confirmed chop"
        )
    elif "fine/default" in technical:
        reason = "a useful projected update is preferred over discarding an unconfirmed default chop"
    else:
        reason = "the projected public-state update is preferred over the current discard option"

    hint_text = _hint_action_text(actor, payload)
    if "literal fallback" in technical or "abandon convention" in technical:
        full_hand = "abandon convention" in technical
        why = (
            f"The Dynamic convention wanted channel {channel}, but that channel cannot be expressed "
            f"legally on the target hand. {hint_text} as a literal fallback instead. "
            + (
                "Because it touches the whole hand, everyone treats it as literal information "
                "and leaves the convention state unchanged."
                if full_hand
                else "Its position band is deliberately outside the unavailable channel, so it "
                "does not send the wrong decoded state."
            )
        )
        return why, [
            f"Unavailable encoded channel: {channel}.",
            f"Literal fallback: {_hint_touch_description(payload)}.",
            "Safety rule: never substitute a different channel and let teammates decode the wrong state.",
        ]

    why = (
        f"{hint_text}. In Dynamic Recommendation, the number or color hint and its old, middle, "
        f"or newest position band form channel {channel}. The two peer values add to that "
        f"channel modulo 8, so each receiver can subtract the other peer value and update the "
        f"playable, unplayable, known-5, and chop state for their own hand. The bot hints now because {reason}."
    )
    details = [
        f"Peer values: {' and '.join(str(code) for code in peer_codes)}.",
        f"Encoding: ({' + '.join(str(code) for code in peer_codes)}) modulo 8 = channel {channel}.",
        f"Physical hint: {_hint_touch_description(payload)}.",
        "Decoded result: update the public position labels and chop state; do not store it "
        "as a Simple Recommendation number.",
    ]
    return why, details


def _hint_action_text(actor: int, payload: Dict[str, Any]) -> str:
    target = int(payload.get("target", 0)) + 1
    value = payload.get("value")
    if payload.get("hintType") == "color":
        color_name = next(
            (color.name.title() for color, code in CODE_BY_COLOR.items() if code == value),
            str(value),
        )
        return f"P{actor + 1} gives P{target} a {color_name} color hint"
    return f"P{actor + 1} gives P{target} a number {value} hint"


def _hint_touch_description(payload: Dict[str, Any]) -> str:
    positions = [f"C{int(slot) + 1}" for slot in payload.get("cards", [])]
    touched = _natural_join(positions) if positions else "no C-position"
    value = payload.get("value")
    kind = "color" if payload.get("hintType") == "color" else "number"
    if kind == "color":
        value = next(
            (color.name.title() for color, code in CODE_BY_COLOR.items() if code == value),
            value,
        )
    return f"{kind} {value} to P{int(payload.get('target', 0)) + 1}, touching {touched}"


def _natural_join(items: list[str]) -> str:
    if not items:
        return ""
    if len(items) == 1:
        return items[0]
    if len(items) == 2:
        return f"{items[0]} and {items[1]}"
    return f"{', '.join(items[:-1])}, and {items[-1]}"


def _common_view_from_payload(payload: Dict[str, Any], settings) -> CommonView:
    fireworks_raw = payload.get("fireworks") or {}
    cards_played: Dict[Color, Number] = {}
    for code, color in COLOR_BY_CODE.items():
        value = _bounded_int(fireworks_raw.get(code, 0), 0, 5, f"fireworks.{code}")
        if value:
            cards_played[color] = Number(value)

    discard_counter = Counter(_parse_card(value) for value in payload.get("discards", []))
    cards_discarded: Dict[Color, Suit] = {}
    for color in COLORS:
        counts = {
            number: discard_counter[Card(color, number)]
            for number in Number
            if discard_counter[Card(color, number)]
        }
        if counts:
            cards_discarded[color] = Suit(counts)
    return CommonView(
        live_tokens=_bounded_int(payload.get("lifeTokens", 3), 1, settings.max_live_tokens, "lifeTokens"),
        hint_tokens=_bounded_int(payload.get("hintTokens", 8), 0, settings.max_hint_tokens, "hintTokens"),
        cards_to_draw=_bounded_int(payload.get("deckCount", 0), 0, 50, "deckCount"),
        cards_discarded=cards_discarded,
        cards_played=cards_played,
    )


def _parse_hands(raw: Any, players: int, max_hand_size: int) -> list[list[Card]]:
    if not isinstance(raw, list) or len(raw) != players:
        raise ValueError(f"hands must contain exactly {players} player hands")
    result: list[list[Card]] = []
    for seat, hand in enumerate(raw):
        if not isinstance(hand, list) or not 1 <= len(hand) <= max_hand_size:
            raise ValueError(f"P{seat + 1} must contain 1–{max_hand_size} cards")
        result.append([_parse_card(value) for value in hand])
    return result


def _parse_card(value: Any) -> Card:
    text = str(value).strip().upper()
    if len(text) != 2 or text[0] not in COLOR_BY_CODE or text[1] not in "12345":
        raise ValueError(f"invalid card {value!r}; use W1, R3, Y5, G2, or B4 style notation")
    return Card(COLOR_BY_CODE[text[0]], Number(int(text[1])))


def _validate_card_multiplicity(hands: list[list[Card]], common: CommonView, settings) -> None:
    used = Counter(card for hand in hands for card in hand)
    for card in _expanded_discards(common):
        used[card] += 1
    for color, top in common.cards_played.items():
        for rank in range(1, top.value + 1):
            used[Card(color, Number(rank))] += 1
    for card, count in used.items():
        allowed = settings.cards[card.color].cards[card.number]
        if count > allowed:
            raise ValueError(f"position uses {count} copies of {serialize_card(card)['code']}; the deck has {allowed}")


def _expanded_discards(common: CommonView) -> list[Card]:
    cards: list[Card] = []
    for color, suit in common.cards_discarded.items():
        for number, count in suit.cards.items():
            cards.extend(Card(color, number) for _ in range(count))
    return cards


def _apply_memory(bot: BasePlayer, memory: Dict[str, Any], hands: list[list[Card]]) -> None:
    plays_since_hint = _bounded_int(memory.get("playsSinceHint", 0), 0, 99, "memory.playsSinceHint")
    if hasattr(bot, "_plays_since_hint"):
        bot._plays_since_hint = plays_since_hint  # type: ignore[attr-defined]

    recommendations_raw = memory.get("recommendations")
    if isinstance(recommendations_raw, list) and len(recommendations_raw) == len(hands):
        recommendations = [None if value in (None, "", "none") else int(value) for value in recommendations_raw]
    else:
        rec_raw = memory.get("recommendation")
        recommendations = [None for _ in hands]
        recommendations[bot.player_index] = None if rec_raw in (None, "", "none") else int(rec_raw)
    if hasattr(bot, "_latest_recommendation_by_seat"):
        bot._latest_recommendation_by_seat.clear()  # type: ignore[attr-defined]
        for seat, code in enumerate(recommendations):
            if code is not None:
                bot._set_recommendation_for_seat(seat, code)  # type: ignore[attr-defined]

    if isinstance(bot, DynamicRecommendation3P):
        beliefs_raw = memory.get("beliefs")
        if beliefs_raw:
            bot._inferred_hands = _parse_beliefs(beliefs_raw, hands)


def _parse_beliefs(raw: Any, hands: list[list[Card]]) -> list[InferredHand]:
    if not isinstance(raw, list) or len(raw) != len(hands):
        raise ValueError("memory.beliefs must contain one entry per seat")
    result = []
    for seat, (item, cards) in enumerate(zip(raw, hands)):
        slots_raw = item.get("slots", []) if isinstance(item, dict) else []
        if len(slots_raw) != len(cards):
            raise ValueError(f"P{seat + 1} beliefs must contain one slot per card")
        slots = []
        for slot in slots_raw:
            state = str(slot.get("playability", "unknown"))
            try:
                playability = Playability(state)
            except ValueError as error:
                raise ValueError(f"invalid playability {state!r}") from error
            slots.append(InferredSlot(playability=playability, known_five=bool(slot.get("knownFive", False))))
        chop_raw = item.get("chop")
        chop = None if chop_raw is None else _bounded_int(chop_raw, 0, len(cards) - 1, f"P{seat + 1} chop")
        result.append(InferredHand(cards=slots, chop=chop, chop_confirmed=bool(item.get("chopConfirmed", False))))
    return result


def _default_beliefs(players: int, hand_size: int) -> list[Dict[str, Any]]:
    return [
        {
            "slots": [{"playability": "unknown", "knownFive": False} for _ in range(hand_size)],
            "chop": 0,
            "chopConfirmed": False,
        }
        for _ in range(players)
    ]


def _current_recommendation(bot: BasePlayer) -> Optional[int]:
    if hasattr(bot, "_recommendation_for_seat"):
        return bot._recommendation_for_seat(bot.player_index)  # type: ignore[attr-defined]
    return None


def _selected_action_step(spec: BotSpec, move: Move, why: str, recommendation: Optional[int]) -> int:
    lower = why.lower()
    if spec.family == "Dynamic Recommendation":
        if "final" in lower or "endgame" in lower:
            return 1
        if "protect" in lower:
            return 2
        if isinstance(move, Play):
            return 3
        if isinstance(move, (ColorHint, NumberHint, Discard)):
            return 4
        return 5
    if spec.key == "simple-5p":
        if isinstance(move, Play):
            return 8 if "last resort" in lower or "fallback" in lower else 1
        if isinstance(move, (ColorHint, NumberHint)):
            if "[strong]" in lower:
                return 2
            if "[medium]" in lower:
                return 4
            return 6
        if isinstance(move, Discard) and recommendation is not None:
            if 5 <= recommendation <= 8:
                return 3
            if 9 <= recommendation <= 12:
                return 5
        return 7
    if "last resort" in lower or "fallback" in lower:
        return 5
    if isinstance(move, Play):
        return 1
    if isinstance(move, (ColorHint, NumberHint)):
        if "strong" in lower or "protect" in lower:
            return 2
        return 4
    if isinstance(move, Discard):
        if spec.key == "simple-3p" and recommendation in (0, 6):
            return 3
        if spec.key == "simple-4p" and recommendation is not None and 5 <= recommendation <= 8:
            return 3
    return 5


def _action_trace(spec: BotSpec, selected: int) -> list[Dict[str, Any]]:
    labels = (
        [
            "When the deck is empty, use the remaining turns for the best scoring chances",
            "Before acting for yourself, stop the next player from losing an important card",
            "Play the leftmost card the shared convention state marks playable",
            "Compare what an encoded hint would teach with the safety of the current chop",
            "If none of those applies, discard the oldest legal card",
        ]
        if spec.family == "Dynamic Recommendation"
        else (
            [
                "Follow a fresh stored recommendation to play",
                "Give a strong recommendation hint that creates valuable new recommendations",
                "Follow a safe stored recommendation to discard a useless card",
                "Give a weaker positive recommendation hint that identifies a dispensable discard",
                "Follow a safe stored recommendation to discard a dispensable card",
                "Give a weaker positive recommendation hint that still creates a useful change",
                "If none applies, discard C1 and recover a hint token",
                "If discarding is illegal, play C1",
            ]
            if spec.key == "simple-5p"
            else [
            "Follow a fresh stored recommendation to play",
            "Give a strong recommendation hint that creates new plays, new discards, or a save",
            "Follow a safe stored recommendation to discard",
            "Give a weaker positive recommendation hint when it still creates a useful change",
            "If none applies, discard C1; if discarding is illegal, play C1",
            ]
        )
    )
    return [
        {
            "step": index,
            "label": label,
            "status": "selected" if index == selected else ("passed" if index < selected else "not-reached"),
        }
        for index, label in enumerate(labels, start=1)
    ]


def _history_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    if isinstance(payload.get("history"), dict):
        return payload["history"]
    text = payload.get("text")
    if not isinstance(text, str) or not text.strip():
        raise ValueError("provide replay history JSON/YAML text")
    filename = str(payload.get("filename", "")).lower()
    if filename.endswith((".yaml", ".yml")):
        try:
            import yaml
        except ImportError as error:
            raise ValueError("PyYAML is required to load YAML replay files") from error
        try:
            history = yaml.safe_load(text)
        except yaml.YAMLError as error:
            mark = getattr(error, "problem_mark", None)
            where = f" at line {mark.line + 1}" if mark else ""
            raise ValueError(f"Invalid YAML{where}. Check the replay file's formatting.") from error
    else:
        import json

        try:
            history = json.loads(text)
        except json.JSONDecodeError as error:
            raise ValueError(
                f"Invalid JSON at line {error.lineno}, column {error.colno}. "
                "Check the replay file's formatting."
            ) from error
    if not isinstance(history, dict):
        raise ValueError("replay file must contain an object")
    return history


def _replay_bot_spec(requested: Any, history: Dict[str, Any], players: int) -> BotSpec:
    if requested and str(requested) in BOT_SPECS:
        spec = BOT_SPECS[str(requested)]
        if spec.players != players:
            raise ValueError(f"{spec.label} does not support {players} players")
        return spec
    saved_names = history.get("players") or []
    mapping = {
        "ThreePlayerRecommendationPlayer": "simple-3p",
        "FourPlayerRecommendationPlayer": "simple-4p",
        "FivePlayerRecommendationPlayer": "simple-5p",
        "DynamicRecommendation3P": "dynamic-3p",
    }
    if saved_names and saved_names[0] in mapping:
        return BOT_SPECS[mapping[saved_names[0]]]
    fallback = {3: "simple-3p", 4: "simple-4p", 5: "simple-5p"}.get(players)
    if fallback is None:
        raise ValueError("the current web explainer supports 3–5 player convention replays")
    return BOT_SPECS[fallback]


def _moves_equivalent(a: Move, b: Move) -> bool:
    if isinstance(a, Play) and isinstance(b, Play):
        return a.card == b.card
    if isinstance(a, Discard) and isinstance(b, Discard):
        return a.card == b.card
    if isinstance(a, ColorHint) and isinstance(b, ColorHint):
        return a.teammate == b.teammate and a.color == b.color
    if isinstance(a, NumberHint) and isinstance(b, NumberHint):
        return a.teammate == b.teammate and a.number == b.number
    return False


def _bot_spec(key: str) -> BotSpec:
    try:
        return BOT_SPECS[key]
    except KeyError as error:
        raise ValueError(f"unknown bot {key!r}") from error


def _spec_payload(spec: BotSpec) -> Dict[str, Any]:
    return {
        "key": spec.key,
        "label": spec.label,
        "players": spec.players,
        "family": spec.family,
        "modulus": spec.modulus,
        "recommendationHelp": spec.recommendation_help,
    }


def _bounded_int(value: Any, low: int, high: int, name: str) -> int:
    try:
        parsed = int(value)
        if isinstance(value, float) and value != parsed:
            raise ValueError("fractional value")
    except (TypeError, ValueError) as error:
        raise ValueError(f"{name} must be an integer") from error
    if not low <= parsed <= high:
        raise ValueError(f"{name} must be between {low} and {high}")
    return parsed
