# Hanabi Convention Lab

The browser app is a teaching and debugging surface built directly on the Python game engine and strategy classes.

## Hosted site

Open <https://hanabi-convention-lab.youtiisnoob.chatgpt.site>. This is a publicly accessible **testing site**, not the final public launch. The hosted build loads the original Python package into an isolated browser worker, so the lab works without a terminal or persistent server and does not send custom positions to a Hanabi backend.

## Current modes

- **Position lab:** edit hands, fireworks, exact discard counts, tokens, acting seat, the full per-seat Simple Recommendation ledger, and Dynamic Recommendation's public playability/chop state; ask the real bot for its move and a learner-facing explanation of the code mapping, freshness or safety check, hint encoding, and selected priority rule.
- **Watch bots:** generate a seeded all-bot game and step through the complete state and the same natural-language convention explanation for every move.
- **Replay:** load an existing JSON or YAML game record, reconstruct every turn, and compare the recorded move with the current bot implementation.
- **Play with bots:** choose a seed and human seat, play/discard from your hidden hand, or hint a visible teammate from on-board controls. Bots' moves are presented one at a time. Helper mode can review any turn and branch before a human decision; human card identities stay hidden.
- **Help:** terminology, recommendation-number mappings, and physical Simple/Dynamic hint-channel lookup.

The August 30 testing release includes transactional deck editing (Apply/Cancel/Restore original/Shuffle), exact sampled draw orders, readable Helper labels, reserved board regions with contained narrow-screen scrolling, explicit game-ending reasons, and reconstructed replay memory. Save workspace downloads a JSON file containing the position and reproducible game recipes; Load workspace validates and rebuilds it with the current engine. Save replay exports one recipe for the Replay tab. Files are not uploaded to a game server, and no account or automatic durable browser storage is used. Keep downloaded files; the page warns before leaving unsaved work. Later strategy changes can change reconstructed games.

Dynamic Recommendation positions accept explicit inferred-hand memory through the API (`memory.beliefs`) and expose that memory in the graphical position editor.

The testing engine rejects further moves for every game-ending condition, both in the web service and the shared core validator. A package-level regression checks zero lives, a perfect score and final-round exhaustion; the August 30 version 30 safeguard does not change convention decisions or the interface.

The published follow-up preserves Watch/Replay and Helper timeline controls across board updates, restores focus after card/history actions, reserves space beneath the selected hand for its action choices and Cancel, and pauses playback when manually stepping or scrubbing. Hint/life graphics have descriptive accessible names, and all animation descendants respect reduced-motion preferences. The header is smaller with no tagline; Save/Load live in a collapsed Workspace files section in the footer. These changes were published as testing version 29 after the user's August 30 approval. Requested website changes belong on this testing site, not only in a local preview; testing publication is not a final launch.

Testing version 37 aligns Play with Bots Helper history with Watch: first/previous/play-pause/next/last controls replace the former previous/next/**Current turn** layout. Reaching the final frame by button, slider, history entry, or automatic playback restores the live turn immediately. Review playback uses 1.6-second steps so all existing action animations finish before another move appears, and Pause cancels its pending step. The exact boundary, complete playback, and pause behavior were verified both locally and on a fresh published page. Version 36's Ask bot worker/cache fix, version 33's prominent **Current turn · P#** board indicator, and version 32's learner-paced bot-action controls remain.

## Optional local development

From the repository root:

```bash
python3 -m hanabi.web
```

Open <http://127.0.0.1:8765>.

Optional bind and port:

```bash
python3 -m hanabi.web --host 0.0.0.0 --port 8765
```

The server uses Python's standard library. PyYAML remains optional except when loading YAML replay files.

## API surface

- `GET /api/config`
- `GET /api/default-position`
- `POST /api/analyze`
- `POST /api/simulate`
- `POST /api/replay`
- `POST /api/card-kinds`
- `POST /api/likely-position`
- `POST /api/continue-position`
- `POST /api/default-position`
- `POST /api/recommendations`
- `POST /api/validate-position`
- `POST /api/play/start`
- `POST /api/play/move`
- `POST /api/play/ask`
- `POST /api/play/rewind`
- `POST /api/play/restore`
- `POST /api/play/recording` (rebuilds a recording without replacing the active human session)

All strategy decisions come from the existing bot classes. The web adapter preserves each bot's terse technical `why()` string for auditing, then translates it into a natural-language explanation and a short “How the convention got there” sequence for the teaching interface.
