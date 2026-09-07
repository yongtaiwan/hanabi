import copy
import unittest

from hanabi.core.moves import Discard
from hanabi.web.service import (
    BOT_SPECS,
    _selected_action_step,
    analyze_position,
    ask_play_bot,
    card_kind_matrix,
    continue_position,
    default_position,
    likely_position,
    play_game_move,
    rewind_play_game,
    recommendation_codes,
    replay_history,
    simulate_game,
    start_play_game,
    restore_play_game,
    recording_play_game,
    validate_position,
)


class TestPositionAnalysis(unittest.TestCase):
    def test_each_simple_strategy_returns_explained_legal_decision(self):
        for key in ("simple-3p", "simple-4p", "simple-5p"):
            with self.subTest(bot=key):
                result = analyze_position(default_position(key))
                self.assertIn(result["decision"]["type"], {"play", "discard", "hint"})
                self.assertTrue(result["decision"]["why"])
                self.assertTrue(result["decision"]["conventionDetails"])
                self.assertNotIn("new_plays=", result["decision"]["why"])
                self.assertIn("technicalWhy", result["decision"])
                expected_steps = 8 if key == "simple-5p" else 5
                self.assertEqual(len(result["trace"]), expected_steps)
                self.assertEqual(sum(step["status"] == "selected" for step in result["trace"]), 1)

    def test_duplicate_cards_are_rejected(self):
        payload = default_position("simple-3p")
        payload["hands"][0] = ["R5"] * 5
        with self.assertRaisesRegex(ValueError, "deck has 1"):
            analyze_position(payload)

    def test_dynamic_strategy_accepts_explicit_belief_state(self):
        payload = default_position("dynamic-3p")
        payload["memory"]["beliefs"][0]["slots"][4]["playability"] = "playable"
        result = analyze_position(payload)
        self.assertEqual(result["decision"]["type"], "play")
        self.assertIn("shared Dynamic convention state marks P1's C5 as playable", result["decision"]["why"])
        self.assertIn("Public state: C5 is marked playable.", result["decision"]["conventionDetails"])

    def test_simple_play_explains_code_mapping_and_freshness_in_plain_language(self):
        payload = default_position("simple-3p")
        payload["memory"]["recommendations"][0] = 3
        result = analyze_position(payload)
        self.assertEqual("Play C3", result["decision"]["label"])
        self.assertIn("stored recommendation is 3", result["decision"]["why"])
        self.assertIn("No card has been played since the hint", result["decision"]["why"])
        self.assertNotIn("[3p mod-8]", result["decision"]["why"])
        self.assertIn("[3p mod-8]", result["decision"]["technicalWhy"])

    def test_simple_hint_explains_encoding_and_decoding(self):
        result = analyze_position(default_position("simple-3p"))
        self.assertEqual("hint", result["decision"]["type"])
        self.assertIn("encoded convention hint", result["decision"]["why"])
        self.assertIn("subtract the other visible recommendation numbers", result["decision"]["why"])
        self.assertIn("Encoding: (1 + 1) modulo 8 = channel 2.", result["decision"]["conventionDetails"])

    def test_card_kind_matrix_covers_every_card_identity(self):
        payload = default_position("simple-3p")
        result = card_kind_matrix(payload)
        self.assertEqual({"W", "R", "Y", "G", "B"}, set(result["kinds"]))
        self.assertTrue(all(len(by_rank) == 5 for by_rank in result["kinds"].values()))

    def test_auto_recommendations_do_not_require_a_bot_move(self):
        payload = default_position("simple-3p")
        payload["hintTokens"] = 0
        payload["memory"]["recommendations"] = [7, 7, 7]
        result = recommendation_codes(payload)
        self.assertEqual([5, 1, 1], [hand["recommendationCode"] for hand in result["hands"]])

    def test_auto_recommendations_reject_dynamic_strategy(self):
        with self.assertRaisesRegex(ValueError, "Simple Recommendation only"):
            recommendation_codes(default_position("dynamic-3p"))

    def test_likely_position_is_a_real_analyzable_history_frame(self):
        result = likely_position({"bot": "simple-3p", "seed": 91})
        self.assertGreater(result["source"]["turn"], 0)
        analyzed = analyze_position(result["position"])
        self.assertIn(analyzed["decision"]["type"], {"play", "discard", "hint"})

    def test_dynamic_likely_position_carries_sampled_convention_state(self):
        result = likely_position({"bot": "dynamic-3p", "seed": 91})
        beliefs = result["position"]["memory"]["beliefs"]
        self.assertEqual(3, len(beliefs))
        self.assertTrue(
            any(
                belief["chopConfirmed"]
                or belief["chop"] != 0
                or any(slot["playability"] != "unknown" for slot in belief["slots"])
                for belief in beliefs
            )
        )
        analyzed = analyze_position(result["position"])
        self.assertIn(analyzed["decision"]["type"], {"play", "discard", "hint"})

    def test_continue_position_finishes_the_game(self):
        payload = default_position("simple-3p")
        payload.update({"seed": 91})
        result = continue_position(payload)
        self.assertGreater(result["moves"], 3)
        self.assertTrue(result["timeline"][-1]["state"]["finished"])
        self.assertFalse(result["truncated"])
        self.assertTrue(result["continuedFromPosition"])

    def test_continue_position_respects_an_explicit_deck_order(self):
        payload = default_position("simple-3p")
        copies = {1: 3, 2: 2, 3: 2, 4: 2, 5: 1}
        remaining = [f"{color}{rank}" for color in "WRYGB" for rank, count in copies.items() for _ in range(count)]
        for hand in payload["hands"]:
            for code in hand:
                remaining.remove(code)
        payload.update({"seed": 91, "deckOrder": list(reversed(remaining))})
        result = continue_position(payload)
        first_draw = next(frame["event"]["drawnCard"]["code"] for frame in result["timeline"] if (frame.get("event") or {}).get("drawnCard"))
        self.assertEqual(payload["deckOrder"][0], first_draw)

    def test_continue_position_rejects_an_incomplete_deck_order(self):
        payload = default_position("simple-3p")
        payload.update({"seed": 91, "deckOrder": ["W1"]})
        with self.assertRaisesRegex(ValueError, "every remaining deck card exactly once"):
            continue_position(payload)


class TestSimpleActionTrace(unittest.TestCase):
    def test_three_player_code_zero_is_recommended_discard_step(self):
        step = _selected_action_step(BOT_SPECS["simple-3p"], Discard(4), "discard chop", 0)
        self.assertEqual(3, step)

    def test_five_player_useless_discard_is_step_three(self):
        step = _selected_action_step(BOT_SPECS["simple-5p"], Discard(1), "useless slot", 6)
        self.assertEqual(3, step)

    def test_five_player_dispensable_discard_is_step_five(self):
        step = _selected_action_step(BOT_SPECS["simple-5p"], Discard(1), "dispensable slot", 10)
        self.assertEqual(5, step)


class TestTimelines(unittest.TestCase):
    def test_saved_draw_order_and_memory_match_the_sampled_frame(self):
        for key in BOT_SPECS:
            sample = likely_position({"bot": key, "seed": 91})
            game = simulate_game({"bot": key, "seed": 91})
            frame = game["timeline"][sample["source"]["turn"]]
            self.assertEqual([card["code"] for card in frame["state"]["deckOrder"]], sample["position"]["deckOrder"])
            self.assertEqual(91, sample["position"]["seed"])
            restored = validate_position(sample["position"])
            self.assertEqual(sample["position"]["deckOrder"], restored["deckOrder"])
            continued = continue_position(restored)
            self.assertTrue(continued["timeline"][-1]["state"]["finished"])

    def test_default_positions_are_complete_portable_and_reject_bad_imports(self):
        for key in BOT_SPECS:
            position = default_position(key)
            self.assertEqual(position["deckCount"], len(position["deckOrder"]))
            self.assertEqual(position["deckOrder"], validate_position(position)["deckOrder"])
            bad = copy.deepcopy(position)
            bad["deckOrder"].pop()
            with self.assertRaisesRegex(ValueError, "every remaining card"):
                validate_position(bad)
        with self.assertRaisesRegex(ValueError, "seed must be an integer"):
            simulate_game({"seed": 1.5})

    def test_terminal_metadata_and_final_round_countdown(self):
        seen_final_round = False
        for key in BOT_SPECS:
            game = simulate_game({"bot": key, "seed": 1})
            final = game["timeline"][-1]["state"]
            self.assertTrue(final["finished"])
            self.assertTrue(final["finishReason"])
            for frame in game["timeline"][:-1]:
                board = frame["state"]
                self.assertIsNone(board["finishReason"])
                if board["turnsLeft"] is not None:
                    seen_final_round = True
                    self.assertGreater(board["turnsLeft"], 0)
        self.assertTrue(seen_final_round)

    def test_replay_reconstructs_exact_simulated_memory_without_mutating_predictions(self):
        for key in BOT_SPECS:
            game = simulate_game({"bot": key, "seed": 91})
            initial = game["timeline"][0]["state"]
            moves = []
            for frame in game["timeline"][1:]:
                event = frame["event"]
                moves.append(f"h{event['target'] + 1}{str(event['value']).lower()}" if event["type"] == "hint" else f"{event['type'][0]}{event['slot'] + 1}")
            history = {"settings": {"num_players": game["bot"]["players"]}, "deck": [card["code"] for hand in initial["hands"] for card in hand] + [card["code"] for card in initial["deckOrder"]], "moves": moves}
            replay = replay_history({"bot": key, "history": history})
            self.assertEqual(len(game["timeline"]), len(replay["timeline"]))
            for expected, actual in zip(game["timeline"], replay["timeline"]):
                self.assertEqual(expected["memory"], actual["memory"], (key, actual["turn"]))
                self.assertEqual(expected["state"], actual["state"])

    def test_malformed_replay_reports_a_short_parse_error(self):
        with self.assertRaisesRegex(ValueError, "Invalid JSON"):
            replay_history({"filename": "bad.json", "text": '{"moves": ['})

    def test_simulation_returns_explained_timeline(self):
        result = simulate_game({"bot": "simple-3p", "seed": 42})
        self.assertGreater(result["moves"], 0)
        self.assertGreaterEqual(result["score"], 0)
        self.assertLessEqual(result["score"], 25)
        self.assertIsNone(result["timeline"][0]["event"])
        self.assertEqual(3, len(result["timeline"][0]["memory"]["recommendations"]))
        self.assertTrue(result["timeline"][1]["event"]["why"])
        self.assertTrue(result["timeline"][1]["event"]["conventionDetails"])
        self.assertNotIn("new_plays=", result["timeline"][1]["event"]["why"])
        initial_state = result["timeline"][0]["state"]
        self.assertEqual(initial_state["deckCount"], len(initial_state["deckOrder"]))
        self.assertTrue(all("kind" in card for hand in initial_state["hands"] for card in hand))
        self.assertTrue(all("kind" in card for card in initial_state["deckOrder"]))
        self.assertTrue(
            all(frame["state"]["deckCount"] == len(frame["state"]["deckOrder"]) for frame in result["timeline"])
        )
        first_draw = next(
            frame["event"]["drawnCard"]["code"]
            for frame in result["timeline"]
            if (frame.get("event") or {}).get("drawnCard")
        )
        self.assertEqual(initial_state["deckOrder"][0]["code"], first_draw)
        card_event = next(
            frame for frame in result["timeline"][1:]
            if frame["event"]["type"] in {"play", "discard"}
        )
        self.assertIn("card", card_event["event"])
        previous = result["timeline"][card_event["turn"] - 1]["state"]
        if card_event["state"]["deckCount"] < previous["deckCount"]:
            self.assertIn("drawnCard", card_event["event"])

    def test_failed_play_marks_the_lost_life_for_animation(self):
        result = simulate_game({"bot": "simple-3p", "seed": 1})
        loss = next(frame for frame in result["timeline"] if (frame.get("event") or {}).get("lostLife"))
        previous = result["timeline"][loss["turn"] - 1]["state"]
        self.assertEqual(1, loss["event"]["lostLife"])
        self.assertEqual(previous["lifeTokens"] - 1, loss["state"]["lifeTokens"])

    def test_existing_json_record_can_be_replayed(self):
        deck = []
        for color in "WRYGB":
            deck.extend([f"{color}1"] * 3)
            for rank in (2, 3, 4):
                deck.extend([f"{color}{rank}"] * 2)
            deck.append(f"{color}5")
        history = {
            "settings": {"num_players": 3},
            "deck": deck,
            "players": ["ThreePlayerRecommendationPlayer"] * 3,
            "moves": ["h2w", "h3r"],
        }
        result = replay_history({"history": history})
        self.assertEqual(result["moves"], 2)
        self.assertEqual(len(result["timeline"]), result["moves"] + 1)


class TestPlayWithBots(unittest.TestCase):
    def test_helper_advice_is_explained_repeatable_and_does_not_change_the_game(self):
        for key in BOT_SPECS:
            with self.subTest(bot=key):
                started = start_play_game({"bot": key, "seed": 91, "humanSeat": 1})
                before_timeline = copy.deepcopy(started["timeline"])
                first = ask_play_bot({"sessionId": started["sessionId"]})
                second = ask_play_bot({"sessionId": started["sessionId"]})
                self.assertEqual(first, second)
                self.assertEqual(1, first["actor"])
                self.assertTrue(first["decision"]["why"])
                self.assertTrue(first["decision"]["conventionDetails"])
                self.assertIn(first["decision"]["type"], {"play", "discard", "hint"})
                self.assertEqual(
                    1,
                    sum(step["status"] == "selected" for step in first["trace"]),
                )
                advanced = play_game_move(
                    {"sessionId": started["sessionId"], "move": started["legalMoves"][0]}
                )
                self.assertEqual(before_timeline, advanced["timeline"][: len(before_timeline)])

    def test_helper_advice_requires_a_live_human_turn(self):
        started = start_play_game({"bot": "simple-3p", "seed": 42, "humanSeat": 2})
        started["sessionId"] = "missing"
        with self.assertRaisesRegex(ValueError, "no longer active"):
            ask_play_bot({"sessionId": started["sessionId"]})

    def test_saved_human_games_restore_exactly_and_recording_import_keeps_live_game(self):
        for key in BOT_SPECS:
            result = start_play_game({"bot": key, "seed": 91, "humanSeat": 1})
            for _ in range(3):
                if result["finished"]:
                    break
                move = next((move for move in result["legalMoves"] if move["type"] == "hint"), result["legalMoves"][0])
                result = play_game_move({"sessionId": result["sessionId"], "move": move})
            restored = restore_play_game(result["resume"])
            self.assertEqual(result["timeline"], restored["timeline"])
            self.assertEqual(result["legalMoves"], restored["legalMoves"])
            recording = recording_play_game(result["resume"])
            self.assertEqual(result["timeline"], recording["timeline"])
            bad = copy.deepcopy(result["resume"])
            bad["humanMoves"].append({"type": "hint", "target": 1, "hintType": "number", "value": 1})
            with self.assertRaises(ValueError):
                restore_play_game(bad)
            if not restored["finished"]:
                previous_length = len(restored["timeline"])
                next_state = play_game_move({"sessionId": restored["sessionId"], "move": restored["legalMoves"][0]})
                self.assertGreater(len(next_state["timeline"]), previous_length)

    def test_start_runs_bots_until_the_selected_human_seat(self):
        result = start_play_game({"bot": "simple-3p", "seed": 42, "humanSeat": 2})
        self.assertFalse(result["finished"])
        self.assertEqual(2, result["humanSeat"])
        self.assertEqual(2, result["timeline"][-1]["state"]["currentPlayer"])
        self.assertEqual(2, len(result["recentEvents"]))
        self.assertTrue(result["legalMoves"])
        self.assertIn("memory", result["timeline"][-1])

    def test_human_move_is_followed_by_bots_and_returns_to_the_human(self):
        started = start_play_game({"bot": "dynamic-3p", "seed": 91, "humanSeat": 0})
        selected = next(move for move in started["legalMoves"] if move["type"] == "play")
        result = play_game_move({"sessionId": started["sessionId"], "move": selected})
        self.assertGreaterEqual(len(result["recentEvents"]), 1)
        self.assertTrue(result["recentEvents"][0]["human"])
        self.assertTrue(result["finished"] or result["timeline"][-1]["state"]["currentPlayer"] == 0)
        self.assertEqual("Dynamic Recommendation", result["bot"]["family"])

    def test_rejects_a_move_that_is_not_currently_legal(self):
        started = start_play_game({"bot": "simple-3p", "seed": 7, "humanSeat": 0})
        with self.assertRaisesRegex(ValueError, "not legal"):
            play_game_move(
                {
                    "sessionId": started["sessionId"],
                    "move": {"type": "hint", "hintType": "number", "target": 0, "value": 5},
                }
            )

    def test_helper_can_rewind_to_before_a_human_move_and_continue(self):
        started = start_play_game({"bot": "simple-3p", "seed": 42, "humanSeat": 2})
        checkpoint = started["timeline"][-1]["turn"]
        selected = started["legalMoves"][0]
        advanced = play_game_move({"sessionId": started["sessionId"], "move": selected})
        self.assertGreater(advanced["moves"], checkpoint)

        rewound = rewind_play_game({"sessionId": started["sessionId"], "turn": checkpoint})
        self.assertEqual(checkpoint, rewound["moves"])
        self.assertEqual(2, rewound["timeline"][-1]["state"]["currentPlayer"])
        self.assertTrue(rewound["legalMoves"])
        resumed = play_game_move({"sessionId": started["sessionId"], "move": rewound["legalMoves"][0]})
        self.assertGreater(resumed["moves"], checkpoint)

    def test_helper_rejects_a_bot_only_rewind_point(self):
        started = start_play_game({"bot": "simple-3p", "seed": 42, "humanSeat": 2})
        with self.assertRaisesRegex(ValueError, "immediately before one of your moves"):
            rewind_play_game({"sessionId": started["sessionId"], "turn": 0})


if __name__ == "__main__":
    unittest.main()
