const state = {
  config: null,
  position: null,
  cardKinds: null,
  randomSeed: 137,
  timelines: { watch: null, replay: null },
  timelineIndexes: { watch: 0, replay: 0 },
  timers: { watch: null, replay: null },
  playSession: null,
  playFrameIndex: null,
  playSequenceEnd: null,
  playReviewing: false,
  playReviewTimer: null,
  playAdvice: null,
  playAdviceLoading: false,
  debugMode: false,
  lastAnimatedTurns: { watch: null, replay: null, play: null },
  playActionMenu: null,
  deckOrderSelection: null,
  draggedDeckIndex: null,
  deckDragClickUntil: 0,
  positionResult: null,
  watchDeckOpen: false,
  replayDeckOpen: false,
  deckDraft: null,
  deckOriginal: null,
  activeMode: "position",
  unsaved: false,
  restoring: false,
};

const useLocalServer = location.pathname === "/" || location.pathname.endsWith("/index.html");
const engineWorker = useLocalServer ? null : new Worker(`/engine-worker.js?v=${Date.now()}`, { type: "module" });
const engineRequests = new Map();
let engineRequestId = 0;

engineWorker?.addEventListener("message", event => {
  const pending = engineRequests.get(event.data.id);
  if (!pending) return;
  engineRequests.delete(event.data.id);
  if (event.data.error) pending.reject(new Error(readableError(event.data.error)));
  else pending.resolve(event.data.result);
});

engineWorker?.addEventListener("error", event => {
  const message = event.message || "The in-browser strategy engine could not start.";
  engineRequests.forEach(pending => pending.reject(new Error(message)));
  engineRequests.clear();
});

const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => [...document.querySelectorAll(selector)];

// Keep keyboard focus on the same control when a board is refreshed.
function rememberBoardFocus(container) {
  const focused = document.activeElement;
  if (!focused || !container.contains(focused)) return () => {};
  const attribute = ["data-timeline-action", "data-timeline-range", "data-watch-deck", "data-close-watch-deck", "data-export-timeline", "data-play-card", "data-play-review", "data-play-review-action", "data-play-review-range", "data-play-rewind", "data-play-sequence-next", "data-ask-play-bot", "data-play-move", "data-close-play-actions"].find(name => focused.hasAttribute(name));
  if (!attribute) return () => {};
  const value = focused.getAttribute(attribute);
  return () => {
    const replacement = [...container.querySelectorAll(`[${attribute}]`)].find(item => item.getAttribute(attribute) === value);
    const fallback = attribute === "data-close-watch-deck"
      ? "[data-watch-deck]"
      : attribute === "data-play-sequence-next"
        ? "[data-play-card]:not([disabled])"
        : "[data-timeline-range], [data-play-review-range]";
    const target = replacement && !replacement.disabled ? replacement : container.querySelector(fallback);
    if (target && !target.disabled) target.focus({ preventScroll: true });
  };
}

// Timeline sliders must stay mounted while dragged; replacing them on every
// input event drops both pointer capture and keyboard focus.
function updateViewerMarkup(shell, html, controlsSelector) {
  const controls = shell.querySelector(controlsSelector);
  if (!controls) { shell.innerHTML = html; return; }
  const staging = document.createElement("div");
  staging.innerHTML = html;
  const freshControls = staging.querySelector(controlsSelector);
  const existing = [...controls.querySelectorAll("button, input, span")];
  const fresh = [...freshControls.querySelectorAll("button, input, span")];
  existing.forEach((control, index) => {
    const next = fresh[index];
    for (const attribute of [...control.attributes]) control.removeAttribute(attribute.name);
    for (const attribute of [...next.attributes]) control.setAttribute(attribute.name, attribute.value);
    if (control.tagName === "INPUT") control.value = next.value;
    else control.textContent = next.textContent;
  });
  while (controls.previousSibling) controls.previousSibling.remove();
  while (controls.nextSibling) controls.nextSibling.remove();
  while (freshControls.previousSibling) shell.insertBefore(staging.firstChild, controls);
  while (freshControls.nextSibling) shell.append(freshControls.nextSibling);
}

async function api(path, payload) {
  if (useLocalServer) {
    const response = await fetch(path, {
      method: payload ? "POST" : "GET",
      headers: payload ? { "Content-Type": "application/json" } : {},
      body: payload ? JSON.stringify(payload) : undefined,
    });
    const data = await response.json();
    if (!response.ok) throw new Error(readableError(data.error || `Request failed (${response.status})`));
    return data;
  }
  return new Promise((resolve, reject) => {
    const id = ++engineRequestId;
    engineRequests.set(id, { resolve, reject });
    engineWorker.postMessage({ id, path, payload: payload ?? {} });
  });
}

function readableError(error) {
  const message = String(error);
  const summary = message.match(/(?:[\w.]*Error|Exception):\s*([^\n]+)\s*$/);
  if (summary) return summary[1];
  return message.includes("Traceback") ? "The engine could not read this state. Check the file or reset the position." : message;
}

function botOptions(select, filter = () => true) {
  select.innerHTML = state.config.bots.filter(filter).map(bot => `<option value="${bot.key}">${bot.label}</option>`).join("");
}

function switchMode(mode) {
  state.activeMode = mode;
  if (mode !== "play") { stopPlaySequence(true); stopPlayReview(); }
  Object.keys(state.timers).forEach(timelineMode => {
    if (timelineMode !== mode) stopTimeline(timelineMode);
  });
  $$(".mode-tab").forEach(button => {
    button.classList.toggle("active", button.dataset.mode === mode);
    button.setAttribute("aria-pressed", String(button.dataset.mode === mode));
  });
  $$(".mode-panel").forEach(panel => panel.classList.toggle("active", panel.id === `mode-${mode}`));
  if (mode === "play" && state.playSession) renderPlayGame();
  if (["watch", "replay"].includes(mode) && state.timelines[mode]) renderTimeline(mode);
}

function stopTimeline(mode) {
  if (!state.timers[mode]) return;
  clearInterval(state.timers[mode]);
  state.timers[mode] = null;
}

function stopPlaySequence(showLatest = false) {
  state.playSequenceEnd = null;
  if (showLatest) {
    state.playFrameIndex = null;
    state.playReviewing = false;
  }
}

function stopPlayReview() {
  if (!state.playReviewTimer) return;
  clearTimeout(state.playReviewTimer);
  state.playReviewTimer = null;
}

function nextRandomSeed() {
  state.randomSeed = ((state.randomSeed * 1664525 + 1013904223) >>> 0) % 2147483648;
  return state.randomSeed;
}

function randomizeSeed(inputId) {
  const input = $(`#${inputId}`);
  input.value = nextRandomSeed();
  input.dispatchEvent(new Event("change", { bubbles: true }));
}

function cardOptionValues(selected, type, color = null) {
  const values = type === "color" ? state.config.colors.map(c => c.code) : state.config.ranks;
  return values.map(value => {
    const kind = type === "rank" && color ? state.cardKinds?.[color]?.[String(value)] : null;
    return `<option value="${value}" class="${kind ? `kind-option-${kind}` : ""}" ${String(value) === String(selected) ? "selected" : ""}>${value}</option>`;
  }).join("");
}

function calculatedDeckCount() {
  const cardsInHands = state.position.hands.reduce((total, hand) => total + hand.length, 0);
  const cardsPlayed = Object.values(state.position.fireworks).reduce((total, rank) => total + Number(rank), 0);
  const cardsDiscarded = state.position.discards.length;
  return Math.max(0, 50 - cardsInHands - cardsPlayed - cardsDiscarded);
}

function updateDeckCount() {
  state.position.deckCount = calculatedDeckCount();
  if (Array.isArray(state.position.deckOrder)) reconcileDeckOrder();
  const deck = $("#deck-count");
  if (deck) {
    deck.querySelector("b").textContent = state.position.deckCount;
    deck.title = `Open deck order · ${state.position.deckCount} cards`;
    deck.setAttribute("aria-label", `Open deck order; ${state.position.deckCount} cards in deck`);
  }
}

function cardCopies(rank) {
  return Number(rank) === 1 ? 3 : Number(rank) === 5 ? 1 : 2;
}

function cardCount(cards, code) {
  return cards.filter(card => card === code).length;
}

function cardUsage(code, position = state.position) {
  const locations = [];
  position.hands.forEach((hand, seat) => hand.forEach((card, slot) => {
    if (card === code) locations.push(`P${seat + 1} C${slot + 1}`);
  }));
  const played = Number(position.fireworks[code[0]]) >= Number(code[1]) ? 1 : 0;
  const discarded = cardCount(position.discards, code);
  const total = locations.length + played + discarded;
  if (played) locations.push("fireworks");
  if (discarded) locations.push(`discard ×${discarded}`);
  return { total, allowed: cardCopies(code[1]), locations };
}

function positionInventoryError(position = state.position) {
  for (const color of state.config.colors) {
    for (const rank of state.config.ranks) {
      const { total, allowed, locations } = cardUsage(`${color.code}${rank}`, position);
      if (total > allowed) return `${color.name} ${rank}: ${total} copies are in use, but only ${allowed} exist (${locations.join("; ")}). Choose another card or return a copy from discard first.`;
    }
  }
  return "";
}

function tryPositionEdit(change) {
  const before = structuredClone(state.position);
  try {
    change(state.position);
    const problem = positionInventoryError();
    if (problem) throw new Error(problem);
    // Non-hand edits also transfer copies to/from the implicit remaining deck.
    if (Array.isArray(state.position.deckOrder)) reconcileDeckOrder();
    state.position.deckCount = calculatedDeckCount();
  } catch (error) {
    state.position = before;
    $("#position-error").textContent = readableError(error.message);
    return false;
  }
  $("#position-error").textContent = "";
  $("#position-transfer").textContent = "";
  const source = $("#history-source");
  source.textContent = source.textContent.replace(/^Real game/, "Edited game");
  if (state.deckDraft && JSON.stringify(before.deckOrder) !== JSON.stringify(state.position.deckOrder)) {
    closeDeckOrder();
    $("#position-transfer").textContent = "Deck draft cancelled because the card inventory changed.";
  }
  return true;
}

function cardChoiceAvailable(code, currentCode) {
  if (code === currentCode) return true;
  return handCardSource(code) !== null;
}

function handCardSource(code, position = state.position) {
  if (!/^[WRYGB][1-5]$/.test(code)) return null;
  const usage = cardUsage(code, position);
  if (usage.total < usage.allowed) return { type: "deck", index: position.deckOrder?.indexOf(code) ?? -1 };
  const discardIndex = position.discards.indexOf(code);
  if (discardIndex >= 0) return { type: "discard", index: discardIndex };
  for (let seat = 0; seat < position.hands.length; seat++) {
    const slot = position.hands[seat].indexOf(code);
    if (slot >= 0) return { type: "hand", seat, slot };
  }
  if (Number(position.fireworks[code[0]]) >= Number(code[1])) return { type: "firework", color: code[0], rank: Number(code[1]) };
  return null;
}

function swapHandCard(position, seat, slot, nextCode) {
  const previous = position.hands[seat]?.[slot];
  if (!previous) throw new Error("Choose an existing hand position to edit.");
  if (nextCode === previous) return "";
  const source = handCardSource(nextCode, position);
  if (!source) throw new Error("Choose a standard Hanabi card.");
  const target = `P${seat + 1} C${slot + 1}`;
  let message;
  if (source.type === "deck") {
    if (Array.isArray(position.deckOrder)) {
      if (source.index < 0) throw new Error("The draw order is missing that card. Reset its order and try again.");
      position.deckOrder[source.index] = previous;
    }
    const origin = source.index >= 0 ? `draw ${source.index + 1}` : "the deck";
    message = `${target}: ${nextCode} from ${origin}; ${previous} moved to ${origin}.`;
  } else if (source.type === "discard") {
    position.discards[source.index] = previous;
    message = `${target}: ${nextCode} from discard; ${previous} moved to discard.`;
  } else if (source.type === "hand") {
    position.hands[source.seat][source.slot] = previous;
    message = `${target}: ${nextCode} from P${source.seat + 1} C${source.slot + 1}; ${previous} moved there.`;
  } else {
    const top = Number(position.fireworks[source.color]);
    const returned = [previous];
    for (let rank = source.rank + 1; rank <= top; rank++) returned.push(`${source.color}${rank}`);
    position.fireworks[source.color] = source.rank - 1;
    if (Array.isArray(position.deckOrder)) position.deckOrder.push(...returned);
    message = `${target}: ${nextCode} from fireworks; ${returned.join(", ")} returned to the deck. ${source.color} firework is now ${source.rank - 1}.`;
  }
  position.hands[seat][slot] = nextCode;
  return message;
}

function editHandCard(seat, slot, nextCode) {
  let message = "";
  const accepted = tryPositionEdit(position => { message = swapHandCard(position, seat, slot, nextCode); });
  if (accepted) $("#position-transfer").textContent = message;
  return accepted;
}

function fireworkChoiceAvailable(color, height) {
  return state.config.ranks.every(rank => {
    const code = `${color}${rank}`;
    const hands = state.position.hands.reduce((count, hand) => count + cardCount(hand, code), 0);
    return hands + cardCount(state.position.discards, code) + (rank <= height ? 1 : 0) <= cardCopies(rank);
  });
}

function updatePositionOptions() {
  $$(".card-editor").forEach(editor => {
    const colorSelect = editor.querySelector("[data-card-color]");
    const rankSelect = editor.querySelector("[data-card-rank]");
    const current = `${colorSelect.value}${rankSelect.value}`;
    [...colorSelect.options].forEach(option => {
      option.disabled = !cardChoiceAvailable(`${option.value}${rankSelect.value}`, current);
      option.title = "Swaps a copy from the deck, discard, another hand, or fireworks";
    });
    [...rankSelect.options].forEach(option => {
      option.disabled = !cardChoiceAvailable(`${colorSelect.value}${option.value}`, current);
      option.title = "Swaps a copy from the deck, discard, another hand, or fireworks";
    });
  });
  $$('[data-firework]').forEach(select => [...select.options].forEach(option => {
    option.disabled = !fireworkChoiceAvailable(select.dataset.firework, Number(option.value));
  }));
}

function deckBankCount(code) {
  const color = code[0], rank = Number(code[1]);
  const inHands = state.position.hands.reduce((total, hand) => total + cardCount(hand, code), 0);
  const played = Number(state.position.fireworks[color]) >= rank ? 1 : 0;
  return Math.max(0, cardCopies(rank) - inHands - played - cardCount(state.position.discards, code));
}

function availableDeckCards() {
  return state.config.colors.flatMap(color => state.config.ranks.flatMap(rank => {
    const code = `${color.code}${rank}`;
    return Array.from({ length: deckBankCount(code) }, () => code);
  }));
}

function reconcileDeckOrder() {
  const available = availableDeckCards();
  const counts = new Map();
  available.forEach(code => counts.set(code, (counts.get(code) || 0) + 1));
  const reconciled = [];
  (state.position.deckOrder || []).forEach(code => {
    if ((counts.get(code) || 0) <= 0) return;
    reconciled.push(code);
    counts.set(code, counts.get(code) - 1);
  });
  available.forEach(code => {
    if ((counts.get(code) || 0) <= 0) return;
    reconciled.push(code);
    counts.set(code, counts.get(code) - 1);
  });
  state.position.deckOrder = reconciled;
  return reconciled;
}

function bankCard(code, count, side, otherCount) {
  const direction = side === "deck"
    ? (count > 0 ? "discard" : "return")
    : (count > 0 ? "return" : "discard");
  const disabled = count === 0 && otherCount === 0 ? "disabled" : "";
  const emptyClass = count === 0 ? " empty-slot" : "";
  const title = direction === "discard" ? `Move ${code} to discard` : `Move ${code} to deck`;
  return `<button type="button" class="card-bank-card card-${code[0]}${emptyClass}" data-bank-${direction}="${code}" ${disabled} title="${title}" aria-label="${title}; ${count} on this side"><b>${code[1]}</b><span>×${count}</span></button>`;
}

function bankSuitColumns(side) {
  return `<div class="card-bank-columns">${state.config.colors.map(color => `
    <div class="bank-suit-column">
      <span class="bank-suit-label card-${color.code}" title="${color.name}">${color.code}</span>
      ${state.config.ranks.map(rank => {
        const code = `${color.code}${rank}`;
        const deckCount = deckBankCount(code);
        const discardCount = cardCount(state.position.discards, code);
        const count = side === "deck" ? deckCount : discardCount;
        const otherCount = side === "deck" ? discardCount : deckCount;
        return bankCard(code, count, side, otherCount);
      }).join("")}
    </div>`).join("")}</div>`;
}

function renderCardBank() {
  $("#discard-editor").innerHTML = `
    <div class="bank-column"><div class="bank-heading"><b>Deck</b><button type="button" class="bank-order-button" id="open-deck-order">Order draws →</button></div>${bankSuitColumns("deck")}</div>
    <div class="bank-arrow" aria-hidden="true"><span>↓</span><b>click to move</b><span>↑</span></div>
    <div class="bank-column"><div class="bank-heading"><b>Discard</b><span>Click any square to move one</span></div>${bankSuitColumns("discard")}</div>`;
  $$('[data-bank-discard]').forEach(button => button.addEventListener("click", () => {
    if (!tryPositionEdit(position => position.discards.push(button.dataset.bankDiscard))) return;
    renderCardBank();
    updateDeckCount();
    refreshCardKinds();
  }));
  $$('[data-bank-return]').forEach(button => button.addEventListener("click", () => {
    const index = state.position.discards.lastIndexOf(button.dataset.bankReturn);
    if (index >= 0 && !tryPositionEdit(position => position.discards.splice(index, 1))) return;
    renderCardBank();
    updateDeckCount();
    refreshCardKinds();
  }));
  $("#open-deck-order").addEventListener("click", openDeckOrder);
  updatePositionOptions();
}

function moveDeckCard(from, to) {
  const order = state.deckDraft;
  if (!order || from === to || from < 0 || from >= order.length || to < 0 || to > order.length) return;
  const [card] = order.splice(from, 1);
  const target = from < to ? to - 1 : to;
  order.splice(target, 0, card);
}

function swapDeckCards(first, second) {
  const order = state.deckDraft;
  if (!order || first === second) return;
  [order[first], order[second]] = [order[second], order[first]];
}

function bindDeckDrag(card) {
  let gesture = null;
  const clearTarget = () => $$('[data-deck-drop-target]').forEach(target => target.removeAttribute('data-deck-drop-target'));
  const destination = event => {
    const target = document.elementFromPoint(event.clientX, event.clientY)?.closest('[data-deck-order-index], [data-deck-order-end]');
    if (!target) return null;
    return { target, index: target.hasAttribute('data-deck-order-end') ? state.deckDraft.length : Number(target.dataset.deckOrderIndex) };
  };
  card.addEventListener('pointerdown', event => {
    if (event.button !== 0 || event.isPrimary === false) return;
    gesture = { x: event.clientX, y: event.clientY, from: Number(card.dataset.deckOrderIndex), pointerId: event.pointerId, active: false };
    card.setPointerCapture(event.pointerId);
    document.addEventListener('pointermove', move);
    document.addEventListener('pointerup', up);
    document.addEventListener('pointercancel', cancel);
  });
  const move = event => {
    if (!gesture || event.pointerId !== gesture.pointerId) return;
    if (!gesture.active && Math.hypot(event.clientX - gesture.x, event.clientY - gesture.y) < 6) return;
    event.preventDefault();
    gesture.active = true;
    state.draggedDeckIndex = gesture.from;
    card.classList.add('dragging');
    $('[data-deck-order-end]').disabled = false;
    clearTarget();
    const drop = destination(event);
    if (drop && drop.index !== gesture.from) drop.target.setAttribute('data-deck-drop-target', '');
  };
  const finish = (event, cancelled = false) => {
    if (!gesture || event.pointerId !== gesture.pointerId) return;
    const finished = gesture;
    gesture = null;
    document.removeEventListener('pointermove', move);
    document.removeEventListener('pointerup', up);
    document.removeEventListener('pointercancel', cancel);
    clearTarget();
    card.classList.remove('dragging');
    state.draggedDeckIndex = null;
    $('[data-deck-order-end]').disabled = state.deckOrderSelection === null;
    if (!finished.active) return;
    // Suppress the compatibility click after a touch/mouse drag, not keyboard use.
    state.deckDragClickUntil = Date.now() + 250;
    const drop = cancelled ? null : destination(event);
    if (drop) moveDeckCard(finished.from, drop.index);
    state.deckOrderSelection = null;
    renderDeckOrder();
    const index = drop ? (finished.from < drop.index ? drop.index - 1 : drop.index) : finished.from;
    $(`[data-deck-order-index="${index}"]`)?.focus();
  };
  const up = event => finish(event);
  const cancel = event => finish(event, true);
  card.addEventListener('lostpointercapture', cancel);
}

function renderDeckOrder() {
  const order = state.deckDraft || [];
  $("#deck-order-list").innerHTML = `${order.map((code, index) => {
    const color = state.config.colors.find(item => item.code === code[0]);
    return `<button type="button" class="deck-order-card card-${code[0]} ${state.deckOrderSelection === index ? "selected" : ""}" draggable="false" aria-pressed="${state.deckOrderSelection === index}" data-deck-order-index="${index}" aria-label="Draw ${index + 1}: ${color?.name || code[0]} ${code[1]}. Drag or use arrow keys to reorder"><span>${index + 1}</span><b>${code[1]}</b><i>${code[0]}</i></button>`;
  }).join("")}<button type="button" class="deck-order-end" data-deck-order-end>Move to end</button>`;

  $$('[data-deck-order-index]').forEach(card => {
    bindDeckDrag(card);
    card.addEventListener("click", event => {
      if (event.detail !== 0 && Date.now() < state.deckDragClickUntil) return;
      const index = Number(card.dataset.deckOrderIndex);
      if (state.deckOrderSelection === null) state.deckOrderSelection = index;
      else if (state.deckOrderSelection === index) state.deckOrderSelection = null;
      else {
        swapDeckCards(state.deckOrderSelection, index);
        state.deckOrderSelection = null;
      }
      renderDeckOrder();
    });
    card.addEventListener("keydown", event => {
      if (!["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown"].includes(event.key)) return;
      event.preventDefault();
      const index = Number(card.dataset.deckOrderIndex);
      const cards = $$('[data-deck-order-index]');
      const rowWidth = cards.filter(item => item.offsetTop === cards[0].offsetTop).length || 1;
      const delta = { ArrowLeft: -1, ArrowRight: 1, ArrowUp: -rowWidth, ArrowDown: rowWidth }[event.key];
      const other = index + delta;
      if (other < 0 || other >= order.length) return;
      swapDeckCards(index, other);
      renderDeckOrder();
      $(`[data-deck-order-index="${other}"]`)?.focus();
    });
  });
  $("[data-deck-order-end]").disabled = state.deckOrderSelection === null && state.draggedDeckIndex === null;
  $("[data-deck-order-end]").addEventListener("click", () => {
    if (state.deckOrderSelection === null) return;
    moveDeckCard(state.deckOrderSelection, order.length);
    state.deckOrderSelection = null;
    renderDeckOrder();
  });
}

function openDeckOrder() {
  syncPositionControls();
  state.deckOriginal = [...(state.position.deckOrder || availableDeckCards())];
  state.deckDraft = [...state.deckOriginal];
  state.deckOrderSelection = null;
  $(".table-workspace").classList.add("deck-order-open");
  $("#deck-order-workspace").hidden = false;
  renderDeckOrder();
}

function closeDeckOrder() {
  state.deckDraft = null;
  state.deckOriginal = null;
  state.deckOrderSelection = null;
  $(".table-workspace").classList.remove("deck-order-open");
  $("#deck-order-workspace").hidden = true;
}

function applyDeckOrder() {
  if (state.deckDraft && JSON.stringify(state.deckOriginal) !== JSON.stringify(state.position.deckOrder || availableDeckCards())) {
    closeDeckOrder();
    $("#position-error").textContent = "The position changed. Open the deck again to edit its current order.";
    return;
  }
  if (state.deckDraft) {
    state.position.deckOrder = [...state.deckDraft];
    markUnsaved();
  }
  closeDeckOrder();
}

function shuffledCards(cards) {
  const result = [...cards];
  for (let i = result.length - 1; i > 0; i--) {
    const j = nextRandomSeed() % (i + 1);
    [result[i], result[j]] = [result[j], result[i]];
  }
  return result;
}

function recommendationEditor(spec, recommendations, seat, maxCode) {
  if (spec.family === "Dynamic Recommendation") return "";
  const rec = recommendations[seat];
  return `<div class="table-recommendation-row"><span>Stored rec</span><select data-ledger-seat="${seat}" aria-label="P${seat + 1} stored recommendation"><option value="none">—</option>${Array.from({ length: maxCode + 1 }, (_, i) => `<option value="${i}" ${i === rec ? "selected" : ""}>${i}</option>`).join("")}</select><button type="button" data-auto-recommendation="${seat}" title="Calculate this hand's public recommendation number">Auto</button></div>`;
}

function cardKindCopy(kind) {
  return ({ playable: "playable", useless: "useless", critical: "critical", dispensable: "dispensable" })[kind] || "unknown";
}

function seatCoordinates(seat, total) {
  const layouts = {
    3: [[50, 84], [23, 16], [77, 16]],
    4: [[50, 84], [18, 50], [50, 16], [82, 50]],
    5: [[50, 84], [18, 64], [34, 16], [66, 16], [82, 64]],
  };
  return layouts[total][seat];
}

function timelineCard(card, extraClass = "") {
  const color = state.config.colors.find(item => item.code === card.color)?.name || card.color;
  return `<div class="hanabi-card card-${card.color} ${extraClass}" role="img" aria-label="${color} ${card.rank}"><span>${card.rank}</span><small class="card-suit-letter" aria-hidden="true">${card.color}</small></div>`;
}

function watchTimelineCard(card, extraClass = "", slot = null) {
  const kind = card.kind || "unknown";
  return `<div class="watch-card-debug">${slot === null ? "" : `<span class="card-position">C${slot + 1}</span>`}${timelineCard(card, extraClass)}<span class="timeline-card-kind debug-only kind-${kind}">${cardKindCopy(kind)}</span></div>`;
}

function timelineDeck(board) {
  const title = state.debugMode ? `Show the next ${board.deckCount} cards in draw order` : `${board.deckCount} cards in deck · turn on Debug / helper to inspect the order`;
  return `<button type="button" class="deck-stack timeline-deck" data-watch-deck title="${title}" aria-label="${title}" ${state.debugMode ? "" : "disabled"}><i></i><i></i><i></i><b>${board.deckCount}</b></button>`;
}

function watchDeckInspector(board, mode = "watch") {
  if (!state.debugMode || !state[`${mode}DeckOpen`]) return "";
  const order = board.deckOrder || [];
  return `<section class="watch-deck-inspector debug-only" aria-label="Upcoming deck order"><div class="watch-deck-header"><div><p>Draw order</p><span>1 is next</span></div><button type="button" class="watch-deck-close" data-close-watch-deck aria-label="Close draw order">← Close</button></div><div class="watch-deck-list">${order.length ? order.map((card, index) => `<div class="watch-deck-card card-${card.color}" title="Draw ${index + 1}: ${card.code}"><span>${index + 1}</span><b>${card.rank}</b></div>`).join("") : `<p class="watch-deck-empty">The deck is empty.</p>`}</div></section>`;
}

function tokenIcons(count, maximum, symbol, className) {
  const label = `${className === "hint-token-pool" ? "Hint tokens" : "Lives"}: ${count} of ${maximum}`;
  return `<div class="token-pool ${className}" role="img" title="${label}" aria-label="${label}">${Array.from({ length: maximum }, (_, index) => `<i aria-hidden="true" class="${index < count ? "active" : ""}">${symbol}</i>`).join("")}</div>`;
}

function dynamicBeliefSummary(belief) {
  const marked = (belief?.slots || []).flatMap((slot, index) => {
    const labels = [];
    if (slot.playability === "playable") labels.push(`C${index + 1} play`);
    if (slot.playability === "unplayable") labels.push(`C${index + 1} unplayable`);
    if (slot.knownFive) labels.push(`C${index + 1} is 5`);
    return labels;
  });
  if (Number.isInteger(belief?.chop)) marked.push(`chop C${belief.chop + 1}${belief.chopConfirmed ? " ✓" : ""}`);
  return marked.length ? marked.join(" · ") : "No marked cards";
}

function conventionState(frame, data) {
  const memory = frame?.memory;
  if (!memory) return '<p class="helper-notice debug-only">Convention memory is unavailable after an incompatible legacy move. “?” does not mean an empty recommendation.</p>';
  if (data.bot.family === "Simple Recommendation") return "";
  const beliefs = memory.beliefs || [];
  return `<section class="timeline-memory dynamic-memory debug-only" aria-label="Public Dynamic convention state"><p>Public convention state</p><div class="dynamic-memory-list">${beliefs.map((belief, seat) => `<span class="dynamic-memory-seat ${seat === frame.state.currentPlayer ? "next" : ""}"><b>P${seat + 1}</b>${escapeHtml(dynamicBeliefSummary(belief))}</span>`).join("")}</div></section>`;
}

function storedRecommendationBadge(frame, data, seat) {
  if (data.bot.family !== "Simple Recommendation") return "";
  const value = frame?.memory?.recommendations?.[seat];
  const display = !frame?.memory ? "?" : value === null || value === undefined ? "—" : value;
  return `<span class="stored-recommendation debug-only" aria-label="P${seat + 1} stored recommendation: ${display}" title="P${seat + 1} stored recommendation"><i>Rec</i><b>${display}</b></span>`;
}

function positionTokenButtons(count, maximum, kind, singular) {
  return Array.from({ length: maximum }, (_, index) => {
    const active = index < count;
    const nextCount = active ? Math.max(kind === "life" ? 1 : 0, index) : index + 1;
    return `<button type="button" class="position-token ${kind}-token ${active ? "active" : ""}" data-position-token="${kind}" data-token-count="${nextCount}" aria-pressed="${active}" aria-label="Set ${singular} count to ${nextCount}" title="Set ${singular} count to ${nextCount}"></button>`;
  }).join("");
}

function renderPositionTokens() {
  $("#hint-tokens").innerHTML = positionTokenButtons(state.position.hintTokens, 8, "hint", "hint token");
  $("#life-tokens").innerHTML = positionTokenButtons(state.position.lifeTokens, 3, "life", "life");
  $$('[data-position-token]').forEach(button => button.addEventListener("click", () => {
    const key = button.dataset.positionToken === "hint" ? "hintTokens" : "lifeTokens";
    state.position[key] = Number(button.dataset.tokenCount);
    renderPositionTokens();
  }));
}

function timelineFireworks(fireworks) {
  return state.config.colors.map(color => {
    const top = Number(fireworks[color.code] || 0);
    if (!top) return `<div class="played-suit card-${color.code}" title="${color.name} firework: empty"><i class="empty">—</i></div>`;
    return `<div class="played-suit card-${color.code}" title="${color.name} firework: ${top}" style="--firework-depth:${top}"><div class="firework-stack">${Array.from({ length: top }, (_, index) => {
      const rank = index + 1;
      return `<i class="firework-card ${rank === top ? "top-card" : "lower-card"}" style="--firework-rank:${rank};--firework-offset:${(top - rank) * 4}px">${rank === top ? `<b>${rank}</b>` : ""}</i>`;
    }).join("")}</div></div>`;
  }).join("");
}

function timelineDiscards(discards) {
  const counts = new Map();
  discards.forEach(card => counts.set(card.code, (counts.get(card.code) || 0) + 1));
  if (!counts.size) return `<span class="empty-discard">—</span>`;
  return [...counts.entries()].map(([code, count]) => `<div class="discard-card card-${code[0]}"><b>${code[1]}</b>${count > 1 ? `<span>×${count}</span>` : ""}</div>`).join("");
}

function actionAnimation(event, players, mode, turn) {
  if (!event || state.lastAnimatedTurns[mode] === turn) return "";
  if (event.type === "hint" && Number.isInteger(event.target)) {
    state.lastAnimatedTurns[mode] = turn;
    const [actorX, actorY] = seatCoordinates(event.actor, players);
    const [targetX, targetY] = seatCoordinates(event.target, players);
    const dx = targetX - actorX, dy = targetY - actorY;
    const distance = Math.hypot(dx, dy) || 1;
    const startX = actorX + (dx / distance) * 6, startY = actorY + (dy / distance) * 6;
    const endX = targetX - (dx / distance) * 8, endY = targetY - (dy / distance) * 8;
    const markerId = `hint-arrowhead-${mode}`;
    return `<div class="hint-arrow-animation" data-animation-actor="${event.actor}" data-animation-target="${event.target}" role="status" aria-label="P${event.actor + 1} hinted P${event.target + 1}"><svg viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true"><defs><marker id="${markerId}" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse"><path d="M 0 0 L 10 5 L 0 10 z"></path></marker></defs><line x1="${startX}" y1="${startY}" x2="${endX}" y2="${endY}" pathLength="1" marker-end="url(#${markerId})"></line></svg><span style="--hint-x:${actorX}%;--hint-y:${actorY}%">P${event.actor + 1} hinted</span></div>`;
  }
  if (!event.card || !["play", "discard"].includes(event.type)) return "";
  state.lastAnimatedTurns[mode] = turn;
  const [x, y] = seatCoordinates(event.actor, players);
  const lifeLoss = event.lostLife
    ? `<div class="life-loss-animation" role="status" aria-label="Life lost"><span>♥</span><b>Life lost</b></div>`
    : "";
  const actionName = event.type === "play" ? "Play" : "Discard";
  return `<div data-animation-actor="${event.actor}" data-animation-slot="${Number.isInteger(event.slot) ? event.slot : ""}" data-animation-destination="${event.type}" class="action-card hanabi-card card-${event.card.color} action-${event.type}" style="--action-x:${x}%;--action-y:${y}%"><span>${event.card.rank}</span><small class="action-label">${actionName}</small></div>${lifeLoss}`;
}

function renderPositionEditor() {
  const spec = state.config.bots.find(bot => bot.key === state.position.bot);
  $("#position-bot").value = state.position.bot;
  renderPositionTokens();
  $("#plays-since-hint").value = state.position.memory.playsSinceHint;
  $("#recommendation-help").textContent = spec.recommendationHelp;
  const maxCode = spec.modulus - 1;
  const recommendations = state.position.memory.recommendations || Array.from({ length: spec.players }, (_, seat) => seat === state.position.actor ? state.position.memory.recommendation : null);
  state.position.memory.recommendations = recommendations;
  $("#hanabi-table").dataset.players = spec.players;
  $("#beliefs-details").hidden = spec.family !== "Dynamic Recommendation";
  if (spec.family === "Dynamic Recommendation") renderBeliefEditor();
  else $("#belief-editor").innerHTML = "";

  $("#fireworks-editor").innerHTML = state.config.colors.map(color => {
    const value = state.position.fireworks[color.code];
    return `<div class="firework-control card-${color.code}"><label>${color.name}<select data-firework="${color.code}">${[0,1,2,3,4,5].map(rank => `<option value="${rank}" ${rank === value ? "selected" : ""}>${rank || "—"}</option>`).join("")}</select></label></div>`;
  }).join("");

  $("#hands-editor").innerHTML = state.position.hands.map((hand, seat) => `
    <div class="hand-editor" data-position-seat="${seat}">
      <button type="button" class="seat-marker ${seat === state.position.actor ? "acting" : ""}" data-acting-seat="${seat}" aria-pressed="${seat === state.position.actor}" title="Make P${seat + 1} the acting seat"><span>P${seat + 1}</span><i aria-hidden="true"></i></button>
      <div class="position-hand-body"><div class="hand-stack cards-${hand.length}">${hand.map((code, slot) => {
        const color = code[0], rank = code[1];
        const kind = state.cardKinds?.[color]?.[String(rank)] || "unknown";
        return `<div class="editable-card"><span class="card-position">C${slot + 1}</span><div class="hanabi-card card-editor card-${color}" data-seat="${seat}" data-slot="${slot}">
          <select data-card-color class="card-color-picker" aria-label="P${seat + 1} C${slot + 1} color; click the card background to change">${cardOptionValues(color, "color")}</select>
          <select data-card-rank class="card-rank-picker kind-select-${kind}" aria-label="P${seat + 1} C${slot + 1} number; click the center number to change">${cardOptionValues(rank, "rank", color)}</select>
        </div><span class="card-kind-label debug-only kind-${kind}">${cardKindCopy(kind)}</span></div>`;
      }).join("")}</div>${spec.family === "Simple Recommendation" ? `<div class="seat-recommendation-editor debug-only">${recommendationEditor(spec, recommendations, seat, maxCode)}</div>` : ""}</div>
    </div>`).join("");

  renderCardBank();

  $$('[data-firework]').forEach(input => input.addEventListener("change", event => {
    const color = event.target.dataset.firework;
    if (!tryPositionEdit(position => { position.fireworks[color] = Number(event.target.value); })) {
      event.target.value = String(state.position.fireworks[color]);
      return;
    }
    renderCardBank();
    updateDeckCount();
    refreshCardKinds();
  }));
  $$(".card-editor select").forEach(input => input.addEventListener("change", () => {
    const editor = input.closest(".card-editor");
    const seat = Number(editor.dataset.seat), slot = Number(editor.dataset.slot);
    const color = editor.querySelector("[data-card-color]");
    const rank = editor.querySelector("[data-card-rank]");
    editHandCard(seat, slot, `${color.value}${rank.value}`);
    refreshCardVisuals();
    renderCardBank();
    updateDeckCount();
    refreshCardKinds();
  }));
  $$('[data-ledger-seat]').forEach(input => input.addEventListener("change", event => {
    const seat = Number(event.target.dataset.ledgerSeat);
    state.position.memory.recommendations[seat] = event.target.value === "none" ? null : Number(event.target.value);
    if (seat === state.position.actor) state.position.memory.recommendation = state.position.memory.recommendations[seat];
  }));
  $$('[data-auto-recommendation]').forEach(button => button.addEventListener("click", () => autoRecommendation(Number(button.dataset.autoRecommendation), button)));
  $$('[data-acting-seat]').forEach(button => button.addEventListener("click", () => {
    syncPositionControls();
    state.position.actor = Number(button.dataset.actingSeat);
    state.position.memory.recommendation = state.position.memory.recommendations[state.position.actor] ?? null;
    renderPositionEditor();
  }));
  updateDeckCount();
  refreshCardKinds();
}

function renderBeliefEditor() {
  const beliefs = state.position.memory.beliefs;
  $("#belief-editor").innerHTML = beliefs.map((belief, seat) => `<div class="belief-seat belief-seat-${seat + 1}" data-belief-seat="${seat}"><b>P${seat + 1}${seat === state.position.actor ? " · acting" : ""}</b><div class="belief-slots">${belief.slots.map((slot, index) => `<div class="belief-slot"><span class="${slot.knownFive ? "known-five" : ""}">C${index + 1}${slot.knownFive ? " · known 5" : ""}</span><select aria-label="P${seat + 1} C${index + 1} inferred playability" class="belief-state-${slot.playability}" data-belief-slot="${index}"><option value="unknown" ${slot.playability === "unknown" ? "selected" : ""}>Unknown</option><option value="playable" ${slot.playability === "playable" ? "selected" : ""}>Playable</option><option value="unplayable" ${slot.playability === "unplayable" ? "selected" : ""}>Unplayable</option></select><label class="belief-five ${slot.knownFive ? "known-five" : ""}"><input type="checkbox" data-belief-five="${index}" aria-label="P${seat + 1} C${index + 1} known 5" ${slot.knownFive ? "checked" : ""}/> Known 5</label></div>`).join("")}</div><div class="belief-meta"><label>Chop<select class="${belief.chop === null ? "belief-chop-none" : "belief-chop-active"}" data-belief-chop><option value="none">None</option>${belief.slots.map((_, i) => `<option value="${i}" ${belief.chop === i ? "selected" : ""}>C${i + 1}</option>`).join("")}</select></label><label class="belief-confirmed ${belief.chopConfirmed ? "active" : ""}"><input data-belief-confirmed type="checkbox" ${belief.chopConfirmed ? "checked" : ""}/> confirmed</label></div></div>`).join("");
  updateBeliefControlColors();
  $$("#belief-editor select, #belief-editor input").forEach(input => input.addEventListener("change", updateBeliefControlColors));
}

function updateBeliefControlColors() {
  $$('[data-belief-slot]').forEach(input => { input.className = `belief-state-${input.value}`; });
  $$('[data-belief-chop]').forEach(input => { input.className = input.value === "none" ? "belief-chop-none" : "belief-chop-active"; });
  $$('[data-belief-confirmed]').forEach(input => { input.closest(".belief-confirmed").classList.toggle("active", input.checked); });
  $$('[data-belief-five]').forEach(input => { input.closest("label").classList.toggle("known-five", input.checked); });
}

function syncHandsFromEditor() {
  $$(".card-editor").forEach(editor => {
    const seat = Number(editor.dataset.seat), slot = Number(editor.dataset.slot);
    state.position.hands[seat][slot] = `${editor.querySelector("[data-card-color]").value}${editor.querySelector("[data-card-rank]").value}`;
  });
}

function refreshCardVisuals() {
  $$(".card-editor").forEach(editor => {
    // A swap may change a donor hand too; update every affected control in place.
    const code = state.position.hands[Number(editor.dataset.seat)][Number(editor.dataset.slot)];
    const color = code[0];
    editor.querySelector("[data-card-color]").value = color;
    editor.querySelector("[data-card-rank]").value = code[1];
    state.config.colors.forEach(item => editor.classList.remove(`card-${item.code}`));
    editor.classList.add(`card-${color}`);
  });
  $$('[data-firework]').forEach(select => { select.value = String(state.position.fireworks[select.dataset.firework]); });
  updateCardKindLabels();
}

function updateCardKindLabels() {
  $$(".card-editor").forEach(editor => {
    const color = editor.querySelector("[data-card-color]").value;
    const rankSelect = editor.querySelector("[data-card-rank]");
    const rank = rankSelect.value;
    // Keep the live select and its options stable while it has keyboard focus.
    [...rankSelect.options].forEach(option => {
      const optionKind = state.cardKinds?.[color]?.[option.value];
      option.className = optionKind ? `kind-option-${optionKind}` : "";
    });
    const kind = state.cardKinds?.[color]?.[String(rank)] || "unknown";
    rankSelect.className = `card-rank-picker kind-select-${kind}`;
    editor.dataset.kind = kind;
    const label = editor.closest(".editable-card").querySelector(".card-kind-label");
    label.className = `card-kind-label debug-only kind-${kind}`;
    label.textContent = cardKindCopy(kind);
  });
}

async function refreshCardKinds() {
  if (!state.position) return;
  const position = state.position;
  const publicState = JSON.stringify([position.fireworks, position.discards]);
  try {
    const result = await api("/api/card-kinds", position);
    if (state.position !== position || publicState !== JSON.stringify([position.fireworks, position.discards])) return;
    state.cardKinds = result.kinds;
    updateCardKindLabels();
  } catch {
    // The primary Analyze action will surface any invalid public-state error.
  }
}

function syncPositionControls() {
  syncHandsFromEditor();
  const problem = positionInventoryError();
  if (problem) throw new Error(problem);
  state.position.memory.playsSinceHint = Number($("#plays-since-hint").value);
  $$('[data-ledger-seat]').forEach(input => { state.position.memory.recommendations[Number(input.dataset.ledgerSeat)] = input.value === "none" ? null : Number(input.value); });
  state.position.memory.recommendation = state.position.memory.recommendations[state.position.actor] ?? null;
  $$("[data-belief-seat]").forEach(seatEl => {
    const seat = Number(seatEl.dataset.beliefSeat), belief = state.position.memory.beliefs[seat];
    seatEl.querySelectorAll("[data-belief-slot]").forEach(input => { belief.slots[Number(input.dataset.beliefSlot)].playability = input.value; });
    seatEl.querySelectorAll("[data-belief-five]").forEach(input => { belief.slots[Number(input.dataset.beliefFive)].knownFive = input.checked; });
    const chop = seatEl.querySelector("[data-belief-chop]").value;
    belief.chop = chop === "none" ? null : Number(chop);
    belief.chopConfirmed = seatEl.querySelector("[data-belief-confirmed]").checked;
  });
  updateDeckCount();
}

function positionResultCard(result, seat, card) {
  const move = result.decision;
  const selected = (seat === result.actor && ["play", "discard"].includes(move.type) && move.slot === card.slot)
    || (move.type === "hint" && move.target === seat && move.cards?.includes(card.slot));
  return `<div class="position-result-card"><span class="card-position">C${card.slot + 1}</span>${timelineCard(card, selected ? "recommended-card" : "")}<span class="card-kind-label debug-only kind-${card.kind}">${cardKindCopy(card.kind)}</span></div>`;
}

function positionClassifications(result) {
  return `<section class="position-classifications debug-only"><p>Card status by C-position</p>${result.hands.map(hand => `<div class="classification-seat"><b>P${hand.seat + 1}</b><div>${hand.cards.map(card => `<span class="kind-${card.kind}"><i>C${card.slot + 1}</i>${cardKindCopy(card.kind)}</span>`).join("")}</div></div>`).join("")}<div class="classification-key"><span class="kind-playable">Playable now</span><span class="kind-useless">Useless · safe discard</span><span class="kind-critical">Critical · last useful copy</span><span class="kind-dispensable">Dispensable · extra useful copy</span></div></section>`;
}

function showPositionEditor() {
  state.positionResult = null;
  $(".position-layout").classList.remove("showing-result");
  $("#hanabi-table").hidden = false;
  $("#position-result-board").hidden = true;
  $(".table-note").hidden = false;
  $("#decision-panel").hidden = true;
}

function renderPositionResult(result) {
  state.positionResult = result;
  closeDeckOrder();
  const board = result.state;
  const frame = { state: board, memory: state.position.memory };
  const data = { bot: result.bot };
  $("#position-result-board").dataset.players = result.bot.players;
  $("#position-result-board").innerHTML = `
    <div class="timeline-table-center">
      <div class="visual-status">
        ${tokenIcons(board.hintTokens, 8, "●", "hint-token-pool")}
        ${tokenIcons(board.lifeTokens, 3, "♥", "life-token-pool")}
        <div class="deck-stack" title="${board.deckCount} cards in deck" aria-label="${board.deckCount} cards in deck"><i></i><i></i><i></i><b>${board.deckCount}</b></div>
        <div class="score-orb" title="Score"><b>${board.score}</b><span>/25</span></div>
      </div>
      <div class="played-cards" aria-label="Played cards">${timelineFireworks(board.fireworks)}</div>
      <div class="discard-tray" aria-label="Discard pile">${timelineDiscards(board.discards)}</div>
    </div>
    ${result.hands.map(hand => `<div class="timeline-hand position-result-hand" data-position-seat="${hand.seat}"><div class="seat-meta"><div class="seat-label">P${hand.seat + 1}${hand.seat === result.actor ? `<span class="acting">acting</span>` : ""}</div>${storedRecommendationBadge(frame, data, hand.seat)}</div><div class="mini-card-row cards-${hand.cards.length}">${hand.cards.map(card => positionResultCard(result, hand.seat, card)).join("")}</div></div>`).join("")}`;

  const panel = $("#decision-panel");
  panel.innerHTML = `
    <div class="position-result-actions"><button type="button" class="secondary-button" id="edit-position">← Edit position</button><button type="button" class="secondary-button" id="result-continue">Continue from position</button></div>
    <p class="error-message" id="result-position-error" role="alert"></p>
    ${conventionState(frame, data)}
    <div class="timeline-event position-decision-event"><p class="eyebrow">P${result.actor + 1} · selected at step ${result.selectedStep}</p><h3>${escapeHtml(result.decision.label)}</h3><h4>Why this move</h4><p>${escapeHtml(result.decision.why || "The bot returned a legal move without an attached explanation.")}</p>${conventionDetails(result.decision.conventionDetails)}</div>
    <section class="decision-priority"><p>Where it sits in the priority order</p><div class="trace">${result.trace.map(item => `<div class="trace-step ${item.status}"><b>${item.step}</b><span>${item.label}</span></div>`).join("")}</div></section>
    <section class="hand-types debug-only"><h4>Public recommendation numbers</h4>${result.hands.map(hand => `<div class="hand-type-row"><span>P${hand.seat + 1}</span><b>${hand.recommendationCode === null ? "public state" : hand.recommendationCode}</b></div>`).join("")}</section>
    ${positionClassifications(result)}`;
  $(".position-layout").classList.add("showing-result");
  $("#hanabi-table").hidden = true;
  $("#position-result-board").hidden = false;
  $(".table-note").hidden = true;
  panel.hidden = false;
  $("#edit-position").addEventListener("click", showPositionEditor);
  $("#result-continue").addEventListener("click", () => continueFromPosition($("#result-continue")));
}

function conventionDetails(items, compact = false) {
  if (!Array.isArray(items) || items.length === 0) return "";
  return `<div class="convention-details ${compact ? "compact" : ""}"><b>How the convention got there</b><ol>${items.map(item => `<li>${escapeHtml(item)}</li>`).join("")}</ol></div>`;
}

function playAdvicePanel(available) {
  if (!available) return "";
  const result = state.playAdvice;
  return `<section class="play-advisor debug-only" aria-live="polite">
    <div class="play-advisor-heading"><div><p>Ask the bot</p><span>What would the bot do from your seat?</span></div><button type="button" data-ask-play-bot ${state.playAdviceLoading ? "disabled" : ""}>${state.playAdviceLoading ? "Thinking…" : result ? "Ask again" : "Ask bot"}</button></div>
    ${result ? `<div class="play-advisor-result"><p class="eyebrow violet">Action algorithm · step ${result.selectedStep}</p><h3>${escapeHtml(result.decision.label)}</h3><p>${escapeHtml(result.decision.why)}</p>${conventionDetails(result.decision.conventionDetails)}</div>` : `<p class="play-advisor-empty">${state.playAdviceLoading ? "The bot is checking the current convention state." : "Get a recommendation without changing the game."}</p>`}
  </section>`;
}

async function askPlayBot() {
  if (!state.playSession || state.playAdviceLoading) return;
  const sessionId = state.playSession.sessionId;
  state.playAdviceLoading = true;
  $("#play-error").textContent = "";
  renderPlayGame();
  try {
    const result = await api("/api/play/ask", { sessionId });
    if (state.playSession?.sessionId === sessionId) state.playAdvice = result;
  } catch (err) {
    $("#play-error").textContent = err.message;
  } finally {
    if (state.playSession?.sessionId === sessionId) {
      state.playAdviceLoading = false;
      renderPlayGame();
    }
  }
}

async function resetPosition(botKey = $("#position-bot").value || "simple-3p") {
  const base = await api("/api/default-position", { bot: botKey });
  state.position = base;
  $("#position-transfer").textContent = "";
  state.cardKinds = null;
  showPositionEditor();
  closeDeckOrder();
  $("#history-source").hidden = true;
  renderPositionEditor();
}

async function autoRecommendation(seat, button) {
  const error = $("#position-error");
  error.textContent = "";
  try {
    syncPositionControls();
    delete button.dataset.result;
    button.disabled = true;
    button.textContent = "…";
    const result = await api("/api/recommendations", state.position);
    const hand = result.hands.find(item => item.seat === seat);
    if (!hand || hand.recommendationCode === null) throw new Error("Automatic recommendation numbers are available for Simple Recommendation only.");
    state.position.memory.recommendations[seat] = hand.recommendationCode;
    if (seat === state.position.actor) state.position.memory.recommendation = hand.recommendationCode;
    const select = $(`[data-ledger-seat="${seat}"]`);
    if (select) select.value = String(hand.recommendationCode);
    button.textContent = `${hand.recommendationCode} ✓`;
    button.dataset.result = "ready";
    setTimeout(() => {
      if (!button.isConnected || button.disabled) return;
      delete button.dataset.result;
      button.textContent = "Auto";
    }, 1400);
  } catch (err) {
    error.textContent = err.message;
  } finally {
    button.disabled = false;
    if (button.dataset.result !== "ready") button.textContent = "Auto";
  }
}

async function randomizeLikelyPosition() {
  const button = $("#randomize-position"), error = $("#position-error");
  error.textContent = "";
  try {
    button.disabled = true;
    button.textContent = "Sampling game…";
    const result = await api("/api/likely-position", {
      bot: $("#position-bot").value,
      seed: nextRandomSeed(),
    });
    const sampledSpec = state.config.bots.find(bot => bot.key === result.position.bot);
    const sampledBeliefs = result.position.memory?.beliefs;
    if (sampledSpec.family === "Dynamic Recommendation" && (!Array.isArray(sampledBeliefs) || sampledBeliefs.length !== sampledSpec.players)) {
      throw new Error("The sampled Dynamic position did not include its convention state.");
    }
    state.position = result.position;
    $("#position-transfer").textContent = "";
    closeDeckOrder();
    state.cardKinds = null;
    showPositionEditor();
    renderPositionEditor();
    if (sampledSpec.family === "Dynamic Recommendation") $("#beliefs-details").open = true;
    const source = $("#history-source");
    source.hidden = false;
    source.textContent = `Real game · seed ${result.source.seed} · turn ${result.source.turn} · score ${result.source.score}${sampledSpec.family === "Dynamic Recommendation" ? " · convention state updated" : ""}`;
    markUnsaved();
    $("#decision-panel").innerHTML = `<div class="empty-decision"><span class="spark">✦</span><h3>Likely state</h3><p>Sampled from a real bot game.</p></div>`;
  } catch (err) {
    error.textContent = err.message;
  } finally {
    button.disabled = false;
    button.textContent = "Likely random state";
  }
}

async function analyzePosition() {
  const button = $("#analyze-position"), error = $("#position-error");
  error.textContent = "";
  try {
    if (state.deckDraft) throw new Error("Apply or cancel the deck changes before asking the bot.");
    syncPositionControls();
    button.disabled = true;
    button.firstChild.textContent = "Thinking… ";
    const result = await api("/api/analyze", state.position);
    renderPositionResult(result);
  } catch (err) {
    error.textContent = err.message;
  } finally {
    button.disabled = false;
    button.firstChild.textContent = "Ask the bot ";
  }
}

async function continueFromPosition(button = $("#continue-position")) {
  const error = button.id === "result-continue" ? $("#result-position-error") : $("#position-error");
  const idleLabel = button.textContent;
  error.textContent = "";
  try {
    if (state.deckDraft) throw new Error("Apply or cancel the deck changes before continuing.");
    syncPositionControls();
    stopTimeline("watch");
    button.disabled = true;
    button.textContent = "Continuing…";
    state.timelines.watch = await api("/api/continue-position", {
      ...state.position,
      seed: state.position.seed ?? 42,
    });
    state.timelines.watch.source = { type: "position", payload: JSON.parse(JSON.stringify(state.position)) };
    $("#watch-bot").value = state.position.bot;
    $("#watch-seed").value = state.timelines.watch.seed;
    state.watchDeckOpen = false;
    markUnsaved();
    state.lastAnimatedTurns.watch = null;
    state.timelineIndexes.watch = 0;
    switchMode("watch");
    renderTimeline("watch");
  } catch (err) {
    error.textContent = err.message;
  } finally {
    button.disabled = false;
    button.textContent = idleLabel;
  }
}

function gameProgress(board, lastFrame = false) {
  if (board.finished) return `<div class="game-progress finished" role="status"><b>Game complete · ${board.score}/25</b><span>${escapeHtml(board.finishReason || (board.lifeTokens === 0 ? "All lives were lost." : board.score === 25 ? "All five fireworks are complete." : "The final round is over."))}</span></div>`;
  if (lastFrame) return `<div class="game-progress"><b>End of saved recording</b><span>This recording stops before the game finishes.</span></div>`;
  if (board.turnsLeft !== null && board.turnsLeft !== undefined) return `<div class="game-progress"><b>Final round</b><span>${board.turnsLeft} turn${board.turnsLeft === 1 ? "" : "s"} remaining</span></div>`;
  return "";
}

function boardTurnIndicator(board) {
  if (board.finished) return '<div class="board-turn-indicator finished" role="status"><span>Game</span><b>Complete</b></div>';
  return `<div class="board-turn-indicator" role="status" aria-label="P${board.currentPlayer + 1}'s turn"><span>Current turn</span><b>P${board.currentPlayer + 1}</b></div>`;
}

function cardStatusKey() {
  return `<section class="watch-kind-key debug-only" aria-label="Card status key"><span class="kind-playable">Playable now</span><span class="kind-useless">Useless · safe discard</span><span class="kind-critical">Critical · last useful copy</span><span class="kind-dispensable">Dispensable · extra useful copy</span></section>`;
}

function positionTurnAnimation(shell) {
  const board = shell.querySelector(".timeline-board");
  if (!board) return;
  const bounds = board.getBoundingClientRect();
  const seatPoint = seat => {
    const hand = board.querySelector(`[data-position-seat="${seat}"]`);
    if (!hand) return null;
    const box = hand.getBoundingClientRect();
    return { x: 100 * (box.x + box.width / 2 - bounds.x) / bounds.width, y: 100 * (box.y + box.height / 2 - bounds.y) / bounds.height };
  };
  const animation = board.querySelector('[data-animation-actor]');
  if (!animation) return;
  const actor = Number(animation.dataset.animationActor);
  const slot = Number(animation.dataset.animationSlot);
  const exactCard = Number.isInteger(slot) ? board.querySelector(`[data-play-card="${actor}:${slot}"]`) : null;
  const exactBox = exactCard?.getBoundingClientRect();
  const from = exactBox
    ? { x: 100 * (exactBox.x + exactBox.width / 2 - bounds.x) / bounds.width, y: 100 * (exactBox.y + exactBox.height / 2 - bounds.y) / bounds.height }
    : seatPoint(actor);
  if (!from) return;
  animation.style.setProperty("--action-x", `${from.x}%`);
  animation.style.setProperty("--action-y", `${from.y}%`);
  const destination = animation.dataset.animationDestination
    ? board.querySelector(animation.dataset.animationDestination === "play" ? ".played-cards" : ".discard-tray")
    : null;
  if (destination) {
    const box = destination.getBoundingClientRect();
    const end = { x: 100 * (box.x + box.width / 2 - bounds.x) / bounds.width, y: 100 * (box.y + box.height / 2 - bounds.y) / bounds.height };
    const lift = animation.dataset.animationDestination === "play" ? -10 : 7;
    animation.style.setProperty("--action-mid-x", `${(from.x + end.x) / 2}%`);
    animation.style.setProperty("--action-mid-y", `${(from.y + end.y) / 2 + lift}%`);
    animation.style.setProperty("--action-end-x", `${end.x}%`);
    animation.style.setProperty("--action-end-y", `${end.y}%`);
  }
  const to = seatPoint(animation.dataset.animationTarget);
  if (to) {
    const line = animation.querySelector("line");
    line.setAttribute("x1", from.x); line.setAttribute("y1", from.y);
    line.setAttribute("x2", to.x); line.setAttribute("y2", to.y);
    animation.querySelector("span").style.setProperty("--hint-x", `${from.x}%`);
    animation.querySelector("span").style.setProperty("--hint-y", `${from.y}%`);
  }
}

function renderTimeline(mode) {
  const data = state.timelines[mode];
  const shell = $(`#${mode}-viewer`);
  const restoreFocus = rememberBoardFocus(shell);
  shell.classList.toggle("awaiting-replay", mode === "replay" && !data);
  if (!data) {
    shell.innerHTML = mode === "replay"
      ? '<button type="button" class="timeline-empty replay-upload" data-choose-replay><span><span class="spark" aria-hidden="true">✦</span><span class="replay-upload-title">Open a saved replay</span><span class="replay-upload-caption">Click to choose a JSON or YAML file.</span></span></button>'
      : '<div class="timeline-empty"><div><span class="spark">✦</span><h3>Generate a bot game</h3><p>The shared turn-by-turn viewer will appear here.</p></div></div>';
    shell.querySelector("[data-choose-replay]")?.addEventListener("click", () => $("#replay-file").click());
    return;
  }
  const index = Math.max(0, Math.min(state.timelineIndexes[mode], data.timeline.length - 1));
  state.timelineIndexes[mode] = index;
  const frame = data.timeline[index], board = frame.state, event = frame.event;
  const players = data.bot.players;
  const animateEvent = Boolean(event && state.lastAnimatedTurns[mode] !== frame.turn);
  const playing = Boolean(state.timers[mode]);
  updateViewerMarkup(shell, `
    <div class="recording-heading"><span>Viewing: <b>${escapeHtml(data.bot.label)}</b>${data.seed === undefined ? " · imported replay" : ` · seed ${data.seed}`}${data.continuedFromPosition ? " · custom position" : ""}</span><div class="recording-actions">${mode === "replay" ? '<button type="button" class="secondary-button" data-choose-replay>Load another replay</button>' : ""}<button type="button" class="secondary-button" data-export-timeline>Save replay</button></div></div>
    ${gameProgress(board, index === data.timeline.length - 1)}
    <div class="timeline-toolbar">
      <button data-timeline-action="first" aria-label="First turn" ${index === 0 ? "disabled" : ""}>|‹</button><button data-timeline-action="prev" aria-label="Previous turn" ${index === 0 ? "disabled" : ""}>‹</button><button class="timeline-play-toggle ${playing ? "playing" : ""}" data-timeline-action="play" aria-label="${playing ? "Pause timeline" : "Play timeline"}" aria-pressed="${playing}">${playing ? "Ⅱ" : "▶"}</button><button data-timeline-action="next" aria-label="Next turn" ${index === data.timeline.length - 1 ? "disabled" : ""}>›</button><button data-timeline-action="last" aria-label="Last turn" ${index === data.timeline.length - 1 ? "disabled" : ""}>›|</button>
      <input type="range" min="0" max="${data.timeline.length - 1}" value="${index}" data-timeline-range aria-label="${mode === "watch" ? "Watch" : "Replay"} turn" />
      <span class="timeline-count">Turn ${index} / ${data.timeline.length - 1}</span>
    </div>
    <div class="timeline-content">
      <div class="board-scroll" role="region" aria-label="Game board; scroll horizontally on small screens" tabindex="0"><div class="game-board position-board-layout timeline-board" data-players="${players}">
        <div class="timeline-table-center">
          ${boardTurnIndicator(board)}
          <div class="visual-status">
            ${tokenIcons(board.hintTokens, 8, "●", "hint-token-pool")}
            ${tokenIcons(board.lifeTokens, 3, "♥", "life-token-pool")}
            ${timelineDeck(board, mode)}
            <div class="score-orb" title="Score"><b>${board.score}</b><span>/25</span></div>
          </div>
          <div class="played-cards" aria-label="Played cards">${timelineFireworks(board.fireworks)}</div>
          <div class="discard-tray" aria-label="Discard pile">${timelineDiscards(board.discards)}</div>
        </div>
        ${board.hands.map((hand, seat) => `<div class="timeline-hand" data-position-seat="${seat}"><div class="seat-meta"><div class="seat-label">P${seat + 1}</div>${storedRecommendationBadge(frame, data, seat)}</div><div class="mini-card-row cards-${hand.length}">${hand.map((card, slot) => {
          const classes = [];
          if (animateEvent && event?.drawnCard && event.actor === seat && slot === hand.length - 1) classes.push("drawn-card");
          if (event?.type === "hint" && event.target === seat && event.cards?.includes(slot)) {
            classes.push("hinted-card-current");
            if (animateEvent) classes.push("hinted-card");
          }
          return watchTimelineCard(card, classes.join(" "), slot);
        }).join("")}</div></div>`).join("")}
        ${actionAnimation(event, players, mode, frame.turn)}
      </div></div>
      <div class="timeline-side">
        ${conventionState(frame, data)}
        ${cardStatusKey()}
        ${watchDeckInspector(board, mode)}
        <div class="timeline-event">${event ? `<p class="eyebrow">P${event.actor + 1} · turn ${index}</p><h3>${escapeHtml(event.label)}</h3><p>${escapeHtml(event.why || "No explanation recorded.")}</p>${conventionDetails(event.conventionDetails, true)}${event.agreesWithCurrentBot === undefined ? "" : `<span class="agreement ${event.agreesWithCurrentBot === true ? "" : "changed"}">${event.agreesWithCurrentBot === true ? "Current bot agrees" : event.agreesWithCurrentBot === false ? "Current bot differs" : "Legacy state"}</span>`}` : `<p class="eyebrow">${data.continuedFromPosition ? "Custom position" : "Initial deal"}</p><h3>${data.bot.label}</h3><p>${data.continuedFromPosition ? "This is the position you built. Step forward to see the bots continue it using the exact draw order shown in Position." : "Start at the initial position, then step forward to watch the convention update after each public action."}</p>`}</div>
      </div>
    </div>`, ".timeline-toolbar");
  shell.querySelectorAll("[data-timeline-action]").forEach(button => { button.onclick = () => timelineAction(mode, button.dataset.timelineAction); });
  shell.querySelector("[data-timeline-range]").oninput = event => { stopTimeline(mode); state.timelineIndexes[mode] = Number(event.target.value); renderTimeline(mode); };
  shell.querySelector("[data-watch-deck]")?.addEventListener("click", () => { state[`${mode}DeckOpen`] = !state[`${mode}DeckOpen`]; renderTimeline(mode); });
  shell.querySelector("[data-close-watch-deck]")?.addEventListener("click", () => { state[`${mode}DeckOpen`] = false; renderTimeline(mode); });
  shell.querySelector("[data-export-timeline]").addEventListener("click", () => downloadJSON({ format: "hanabi-lab-recording", version: 1, source: data.source }, `hanabi-${mode}.json`));
  shell.querySelector("[data-choose-replay]")?.addEventListener("click", () => $("#replay-file").click());
  positionTurnAnimation(shell);
  restoreFocus();
}

function timelineAction(mode, action) {
  const length = state.timelines[mode].timeline.length;
  if (action !== "play") stopTimeline(mode);
  if (action === "first") state.timelineIndexes[mode] = 0;
  if (action === "prev") state.timelineIndexes[mode] = Math.max(0, state.timelineIndexes[mode] - 1);
  if (action === "next") state.timelineIndexes[mode] = Math.min(length - 1, state.timelineIndexes[mode] + 1);
  if (action === "last") state.timelineIndexes[mode] = length - 1;
  if (action === "play") {
    if (state.timers[mode]) stopTimeline(mode);
    else {
      if (state.timelineIndexes[mode] >= length - 1) state.timelineIndexes[mode] = 0;
      state.timers[mode] = setInterval(() => {
        state.timelineIndexes[mode] = Math.min(length - 1, state.timelineIndexes[mode] + 1);
        if (state.timelineIndexes[mode] >= length - 1) stopTimeline(mode);
        renderTimeline(mode);
      }, 1200);
    }
  }
  renderTimeline(mode);
}

async function generateGame() {
  const error = $("#watch-error"), button = $("#generate-game");
  error.textContent = ""; button.disabled = true; button.textContent = "Generating…";
  try {
    stopTimeline("watch");
    state.watchDeckOpen = false;
    state.timelines.watch = await api("/api/simulate", { bot: $("#watch-bot").value, seed: Number($("#watch-seed").value) });
    state.timelines.watch.source = { type: "simulation", payload: { bot: state.timelines.watch.bot.key, seed: state.timelines.watch.seed } };
    markUnsaved();
    state.lastAnimatedTurns.watch = null;
    state.timelineIndexes.watch = 0;
    renderTimeline("watch");
  } catch (err) { error.textContent = err.message; }
  finally { button.disabled = false; button.textContent = "Generate game"; }
}

async function loadReplay(file) {
  const error = $("#replay-error"); error.textContent = "";
  try {
    stopTimeline("replay");
    const text = await file.text();
    let saved = null;
    try { saved = JSON.parse(text); } catch { /* The engine explains malformed JSON or parses YAML. */ }
    const source = saved?.format === "hanabi-lab-recording" ? saved.source : { type: "replay", payload: { filename: file.name, text } };
    state.timelines.replay = await restoreRecording(source);
    state.replayDeckOpen = false;
    markUnsaved();
    state.lastAnimatedTurns.replay = null;
    state.timelineIndexes.replay = 0;
    renderTimeline("replay");
  } catch (err) { error.textContent = err.message; }
}

function updatePlaySeatOptions() {
  const spec = state.config.bots.find(bot => bot.key === $("#play-bot").value) || state.config.bots[0];
  const current = Math.min(Number($("#play-seat").value || 0), spec.players - 1);
  $("#play-seat").innerHTML = Array.from({ length: spec.players }, (_, seat) => `<option value="${seat}" ${seat === current ? "selected" : ""}>P${seat + 1}</option>`).join("");
}

function boardActionMenu(data, seat, slot, card) {
  const legal = (data.legalMoves || []).map((move, index) => ({ move, index }));
  let actions;
  if (seat === data.humanSeat) {
    actions = legal.filter(item => item.move.slot === slot && ["play", "discard"].includes(item.move.type));
  } else {
    actions = legal.filter(item => item.move.type === "hint" && item.move.target === seat && (
      (item.move.hintType === "number" && String(item.move.value) === String(card.rank)) ||
      (item.move.hintType === "color" && String(item.move.value) === String(card.color))
    ));
  }
  if (!actions.length) return `<div class="board-action-menu unavailable">No legal action</div>`;
  return `<div class="board-action-menu" id="play-actions-${seat}-${slot}" role="group" aria-label="Actions for P${seat + 1} C${slot + 1}"><span class="action-position">C${slot + 1}</span>${actions.map(({ move, index }) => {
    if (move.type === "play" || move.type === "discard") {
      return `<button type="button" class="board-action ${move.type}" data-play-move="${index}">${move.type === "play" ? "Play" : "Discard"}</button>`;
    }
    const label = move.hintType === "number"
      ? `Hint ${move.value}`
      : `Hint ${state.config.colors.find(item => item.code === move.value)?.name || move.value}`;
    return `<button type="button" class="board-action hint ${move.hintType === "color" ? `card-${move.value}` : ""}" data-play-move="${index}">${escapeHtml(label)}</button>`;
  }).join("")}<button type="button" class="board-action cancel" data-close-play-actions>Cancel</button></div>`;
}

function closePlayActions() {
  const selected = state.playActionMenu;
  if (!selected) return;
  state.playActionMenu = null;
  renderPlayGame();
  $(`[data-play-card="${selected.seat}:${selected.slot}"]`)?.focus({ preventScroll: true });
}

function playBoardCard(data, card, seat, slot, classes, interactive) {
  const selected = state.playActionMenu?.seat === seat && state.playActionMenu?.slot === slot;
  const clickable = interactive && !data.finished && (data.legalMoves || []).some(move => seat === data.humanSeat
    ? move.slot === slot && ["play", "discard"].includes(move.type)
    : move.type === "hint" && move.target === seat && (
      (move.hintType === "number" && String(move.value) === String(card.rank)) ||
      (move.hintType === "color" && String(move.value) === String(card.color))
    ));
  const face = seat === data.humanSeat
    ? `<div class="hidden-card ${classes}"><span>?</span></div>`
    : timelineCard(card, classes);
  return `<div class="board-card-slot ${selected ? "selected" : ""}"><span class="card-position">C${slot + 1}</span><button type="button" class="board-card-button" data-play-card="${seat}:${slot}" ${clickable ? "" : "disabled"} aria-expanded="${selected}" ${selected ? `aria-controls="play-actions-${seat}-${slot}"` : ""} aria-label="${seat === data.humanSeat ? `Choose an action for C${slot + 1}` : `Choose a hint from P${seat + 1} C${slot + 1}`}" ${classes.includes("hinted-card-current") ? 'aria-description="Touched by this hint"' : ""}>${face}</button>${seat === data.humanSeat ? `<span class="timeline-card-kind debug-only kind-unknown">Hidden</span>` : `<span class="timeline-card-kind debug-only kind-${card.kind}">${cardKindCopy(card.kind)}</span>`}</div>`;
}

function renderPlayHistory(data, visibleIndex, inSequence) {
  const allFrames = data.timeline.slice(1).filter(frame => frame.event);
  const frames = inSequence ? allFrames.filter(frame => frame.turn <= visibleIndex) : allFrames;
  return `<section class="play-history" aria-label="Game history"><div class="play-history-heading"><div><p>Game history</p><b>${frames.length} move${frames.length === 1 ? "" : "s"}</b></div><span>${inSequence ? "Playing turns" : "Newest last"}</span></div><p class="history-helper debug-only">Click any move to replay its animation and inspect that state. Use Branch on one of your moves to change the game from before that decision.</p><ol>${frames.map(frame => {
    const item = frame.event;
    const canReview = state.debugMode;
    const canBranch = state.debugMode && item.human && frame.turn > 0;
    const action = item.type === "hint" ? "Hint" : item.type === "play" ? "Play" : "Discard";
    const touch = item.type === "hint" ? ` · touches ${(item.cards || []).map(slot => `C${slot + 1}`).join(", ")}` : "";
    const isViewing = (inSequence || state.playReviewing) && frame.turn === visibleIndex;
    return `<li class="${item.human ? "human" : ""} ${isViewing ? "reviewing" : ""} ${frame.turn === data.timeline.length - 1 ? "latest" : ""}"><div class="play-history-row"><button type="button" class="play-history-entry" ${canReview ? `data-play-review="${frame.turn}" title="Replay move ${frame.turn} and inspect its state"` : "disabled"}><span class="history-move-number">Move ${frame.turn}</span><b>P${item.actor + 1}</b><span class="history-move-copy"><i>${action}</i>${escapeHtml(item.label + touch)}</span><em class="debug-only">${isViewing ? "Viewing" : "View"}</em></button>${canBranch ? `<button type="button" class="play-branch-rewind debug-only" data-play-rewind="${frame.turn - 1}" title="Rewind the game to before move ${frame.turn}">↶ Branch</button>` : ""}</div></li>`;
  }).join("") || `<li class="empty">No moves yet.</li>`}</ol></section>`;
}

function playReviewToolbar(data, index) {
  const latest = data.timeline.length - 1;
  const playing = Boolean(state.playReviewTimer);
  return `<div class="play-review-toolbar debug-only" aria-label="Helper timeline controls"><button type="button" data-play-review-action="first" ${index <= 0 ? "disabled" : ""} aria-label="First move">|‹</button><button type="button" data-play-review-action="prev" ${index <= 0 ? "disabled" : ""} aria-label="Previous move">‹</button><button type="button" class="timeline-play-toggle ${playing ? "playing" : ""}" data-play-review-action="play" aria-label="${playing ? "Pause move playback" : "Play moves"}" aria-pressed="${playing}">${playing ? "Ⅱ" : "▶"}</button><button type="button" data-play-review-action="next" ${index >= latest ? "disabled" : ""} aria-label="Next move">›</button><button type="button" data-play-review-action="last" ${index >= latest ? "disabled" : ""} aria-label="Last move">›|</button><input type="range" min="0" max="${latest}" value="${index}" data-play-review-range aria-label="Review move" /><span class="timeline-count">Turn ${index} / ${latest}</span></div>`;
}

function setPlayReviewFrame(index) {
  if (!state.playSession) return;
  stopPlaySequence();
  state.playActionMenu = null;
  const latest = state.playSession.timeline.length - 1;
  const frame = Math.max(0, Math.min(index, latest));
  state.playReviewing = frame < latest;
  state.playFrameIndex = frame < latest ? frame : null;
  state.lastAnimatedTurns.play = null;
}

function viewPlayFrame(index) {
  if (!state.debugMode || !state.playSession) return;
  stopPlayReview();
  setPlayReviewFrame(index);
  renderPlayGame();
}

function schedulePlayReviewStep() {
  state.playReviewTimer = setTimeout(() => {
    state.playReviewTimer = null;
    if (!state.debugMode || !state.playSession) return;
    const latest = state.playSession.timeline.length - 1;
    const current = Number.isInteger(state.playFrameIndex) ? state.playFrameIndex : latest;
    const next = Math.min(latest, current + 1);
    setPlayReviewFrame(next);
    if (next < latest) schedulePlayReviewStep();
    renderPlayGame();
  }, 1600);
}

function playReviewAction(action) {
  if (!state.debugMode || !state.playSession) return;
  const latest = state.playSession.timeline.length - 1;
  const current = Number.isInteger(state.playFrameIndex) ? state.playFrameIndex : latest;
  if (action === "play") {
    if (state.playReviewTimer) {
      stopPlayReview();
      renderPlayGame();
      return;
    }
    if (current >= latest) setPlayReviewFrame(0);
    schedulePlayReviewStep();
    renderPlayGame();
    return;
  }
  stopPlayReview();
  if (action === "first") setPlayReviewFrame(0);
  if (action === "prev") setPlayReviewFrame(current - 1);
  if (action === "next") setPlayReviewFrame(current + 1);
  if (action === "last") setPlayReviewFrame(latest);
  renderPlayGame();
}

function advancePlaySequence() {
  if (!state.playSession || !Number.isInteger(state.playSequenceEnd)) return;
  if (state.playFrameIndex < state.playSequenceEnd) {
    state.playFrameIndex += 1;
    state.lastAnimatedTurns.play = null;
    renderPlayGame();
    return;
  }
    state.playSequenceEnd = null;
    state.playFrameIndex = null;
    state.playReviewing = false;
    renderPlayGame();
}

function playNewFrames(firstIndex) {
  stopPlayReview();
  stopPlaySequence();
  const latest = state.playSession.timeline.length - 1;
  state.playActionMenu = null;
  state.playReviewing = false;
  if (firstIndex > latest) {
    state.playFrameIndex = null;
    renderPlayGame();
    return;
  }
  state.playFrameIndex = firstIndex;
  state.playSequenceEnd = latest;
  state.lastAnimatedTurns.play = null;
  renderPlayGame();
}

function renderPlayGame() {
  const shell = $("#play-shell"), data = state.playSession;
  const restoreFocus = rememberBoardFocus(shell);
  $("#export-play").disabled = !data;
  if (!data) return;
  const latestIndex = data.timeline.length - 1;
  const frameIndex = Number.isInteger(state.playFrameIndex) ? Math.max(0, Math.min(state.playFrameIndex, latestIndex)) : latestIndex;
  const frame = data.timeline[frameIndex], board = frame.state, event = frame.event;
  const inSequence = Number.isInteger(state.playSequenceEnd);
  const reviewing = state.debugMode && !inSequence && state.playReviewing;
  const adviceAvailable = !inSequence && !reviewing && frameIndex === latestIndex && !data.finished;
  const interactive = adviceAvailable && !state.playAdviceLoading;
  const finished = interactive && data.finished;
  const animateEvent = Boolean(event && state.lastAnimatedTurns.play !== frame.turn);
  const statusLabel = inSequence
    ? event?.human ? "Your move" : event ? `P${event.actor + 1} is moving` : "Dealing"
    : reviewing ? `Reviewing move ${frame.turn}`
      : finished ? "Game complete" : `Your turn · P${data.humanSeat + 1}`;
  const sequenceButton = inSequence
    ? `<button type="button" class="play-next-move" data-play-sequence-next>${frameIndex < state.playSequenceEnd ? "Next bot move" : data.finished ? "Show final position" : "Continue to your turn"} <span aria-hidden="true">→</span></button>`
    : "";
  updateViewerMarkup(shell, `
    <div class="play-status ${finished ? "finished" : ""} ${inSequence ? "animating" : ""} ${reviewing ? "reviewing" : ""}"><b>${statusLabel}</b><span>${data.bot.label} · turn ${board.turnNumber} · score ${board.score}/25</span>${sequenceButton}</div>
    ${playReviewToolbar(data, frameIndex)}
    ${gameProgress(board)}
    ${event?.type === "hint" ? `<p class="hint-announcement" role="status">P${event.actor + 1} hinted P${event.target + 1} · ${escapeHtml(String(event.value))} · touched ${(event.cards || []).map(slot => `C${slot + 1}`).join(", ")}</p>` : ""}
    <div class="play-layout">
      <div class="board-scroll" role="region" aria-label="Game board; scroll horizontally on small screens" tabindex="0"><div class="game-board play-board position-board-layout timeline-board" data-players="${data.bot.players}">
        <div class="timeline-table-center">
          ${boardTurnIndicator(board)}
          <div class="visual-status">
            ${tokenIcons(board.hintTokens, 8, "●", "hint-token-pool")}
            ${tokenIcons(board.lifeTokens, 3, "♥", "life-token-pool")}
            <div class="deck-stack" title="${board.deckCount} cards in deck" aria-label="${board.deckCount} cards in deck"><i></i><i></i><i></i><b>${board.deckCount}</b></div>
            <div class="score-orb" title="Score"><b>${board.score}</b><span>/25</span></div>
          </div>
          <div class="played-cards" aria-label="Played cards">${timelineFireworks(board.fireworks)}</div>
          <div class="discard-tray" aria-label="Discard pile">${timelineDiscards(board.discards)}</div>
        </div>
        ${board.hands.map((hand, seat) => `<div class="timeline-hand ${seat === data.humanSeat ? "human-hand" : ""}" data-position-seat="${seat}"><div class="seat-meta"><div class="seat-label">P${seat + 1}${seat === data.humanSeat ? `<span class="you">you</span>` : ""}</div>${storedRecommendationBadge(frame, data, seat)}</div><div class="mini-card-row cards-${hand.length}">${hand.map((card, slot) => {
          const hinted = event?.type === "hint" && event.target === seat && event.cards?.includes(slot);
          const classes = hinted ? `hinted-card-current${animateEvent ? " hinted-card" : ""}` : "";
          return playBoardCard(data, card, seat, slot, classes, interactive);
        }).join("")}</div>${interactive && state.playActionMenu?.seat === seat && hand[state.playActionMenu.slot] ? boardActionMenu(data, seat, state.playActionMenu.slot, hand[state.playActionMenu.slot]) : ""}</div>`).join("")}
        ${finished ? `<div class="play-finished-board"><b>Game complete</b><span>${board.score} / 25</span></div>` : `<div class="board-action-prompt">${inSequence ? "This move is paused until you continue above" : reviewing ? `Reviewing move ${frame.turn} · use the purple controls or choose another history point` : "Click your card to play or discard · click a teammate card to hint"}</div>`}
        ${actionAnimation(event, data.bot.players, "play", frame.turn)}
      </div></div>
      <aside class="play-side">
        ${playAdvicePanel(adviceAvailable)}
        ${cardStatusKey()}
        <p class="helper-notice debug-only">Your card identities stay hidden. Status labels describe only visible teammate cards.</p>
        ${conventionState(frame, data)}
        ${renderPlayHistory(data, frameIndex, inSequence)}
      </aside>
    </div>`, ".play-review-toolbar");
  shell.querySelectorAll("[data-play-move]").forEach(button => button.addEventListener("click", () => playGameMove(Number(button.dataset.playMove))));
  shell.querySelectorAll("[data-play-card]").forEach(button => button.addEventListener("click", () => {
    const [seat, slot] = button.dataset.playCard.split(":").map(Number);
    state.playActionMenu = state.playActionMenu?.seat === seat && state.playActionMenu?.slot === slot ? null : { seat, slot };
    renderPlayGame();
    if (state.playActionMenu) shell.querySelector("[data-play-move]")?.focus({ preventScroll: true });
  }));
  shell.querySelector("[data-close-play-actions]")?.addEventListener("click", closePlayActions);
  shell.querySelector("[data-ask-play-bot]")?.addEventListener("click", askPlayBot);
  shell.querySelector("[data-play-sequence-next]")?.addEventListener("click", advancePlaySequence);
  shell.querySelectorAll("[data-play-rewind]").forEach(button => button.addEventListener("click", () => rewindPlayGame(Number(button.dataset.playRewind))));
  shell.querySelectorAll("[data-play-review]").forEach(button => button.addEventListener("click", () => viewPlayFrame(Number(button.dataset.playReview))));
  shell.querySelectorAll("[data-play-review-action]").forEach(button => { button.onclick = () => playReviewAction(button.dataset.playReviewAction); });
  shell.querySelector("[data-play-review-range]").oninput = event => viewPlayFrame(Number(event.target.value));
  const history = shell.querySelector(".play-history ol"), selectedHistory = shell.querySelector(".play-history li.reviewing");
  if (history && selectedHistory) history.scrollTop = Math.max(0, selectedHistory.offsetTop - history.offsetTop - history.clientHeight / 2);
  else if (history) history.scrollTop = history.scrollHeight;
  positionTurnAnimation(shell);
  restoreFocus();
}

async function startPlayGame() {
  const button = $("#start-play"), error = $("#play-error");
  error.textContent = ""; button.disabled = true; button.textContent = "Dealing…";
  try {
    stopPlayReview();
    stopPlaySequence(true);
    state.playActionMenu = null;
    state.playAdvice = null;
    state.playAdviceLoading = false;
    state.lastAnimatedTurns.play = null;
    state.playSession = await api("/api/play/start", {
      bot: $("#play-bot").value,
      seed: Number($("#play-seed").value),
      humanSeat: Number($("#play-seat").value),
    });
    markUnsaved();
    playNewFrames(1);
  } catch (err) { error.textContent = err.message; }
  finally { button.disabled = false; button.textContent = "New game"; }
}

async function rewindPlayGame(turn) {
  if (!state.debugMode || !state.playSession) return;
  const error = $("#play-error");
  error.textContent = "";
  $("#play-shell").querySelectorAll("button").forEach(button => { button.disabled = true; });
  try {
    stopPlayReview();
    stopPlaySequence();
    state.playSession = await api("/api/play/rewind", { sessionId: state.playSession.sessionId, turn });
    markUnsaved();
    state.playActionMenu = null;
    state.playAdvice = null;
    state.playAdviceLoading = false;
    state.playFrameIndex = null;
    state.playReviewing = false;
    state.lastAnimatedTurns.play = turn;
    renderPlayGame();
  } catch (err) {
    error.textContent = err.message;
    renderPlayGame();
  }
}

async function playGameMove(index) {
  const error = $("#play-error"), move = state.playSession?.legalMoves?.[index];
  if (!move) return;
  error.textContent = "";
  $("#play-shell").querySelectorAll("button").forEach(button => { button.disabled = true; });
  try {
    stopPlayReview();
    stopPlaySequence();
    const firstNewFrame = state.playSession.timeline.length;
    state.playSession = await api("/api/play/move", { sessionId: state.playSession.sessionId, move });
    markUnsaved();
    state.playActionMenu = null;
    state.playAdvice = null;
    state.playAdviceLoading = false;
    playNewFrames(firstNewFrame);
  } catch (err) {
    error.textContent = err.message;
    renderPlayGame();
  }
}

function escapeHtml(value) {
  return String(value).replace(/[&<>'"]/g, char => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;" })[char]);
}

function markUnsaved() {
  if (state.restoring) return;
  state.unsaved = true;
  const status = $("#workspace-status");
  if (status) status.textContent = "Unsaved changes · Save workspace before leaving";
}

function downloadJSON(value, filename) {
  const url = URL.createObjectURL(new Blob([JSON.stringify(value, null, 2)], { type: "application/json" }));
  const link = document.createElement("a");
  link.href = url; link.download = filename;
  document.body.append(link); link.click(); link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

async function restoreRecording(source) {
  const routes = { simulation: "/api/simulate", position: "/api/continue-position", replay: "/api/replay", human: "/api/play/recording" };
  if (!source || !Object.hasOwn(routes, source.type) || !source.payload || typeof source.payload !== "object") throw new Error("This file does not contain a supported Lab recording.");
  const result = await api(routes[source.type], source.payload);
  result.source = source;
  return result;
}

function saveWorkspace() {
  try {
    if (state.deckDraft) throw new Error("Apply or cancel the deck changes before saving.");
    syncPositionControls();
    downloadJSON({
      format: "hanabi-lab-workspace", version: 1,
      position: state.position, watch: state.timelines.watch?.source || null,
      replay: state.timelines.replay?.source || null, play: state.playSession?.resume || null,
      indexes: state.timelineIndexes, mode: state.activeMode,
    }, "hanabi-workspace.json");
    state.unsaved = false;
    $("#workspace-status").textContent = "Workspace download requested · keep the file to resume on this or another device";
  } catch (error) { $("#workspace-status").textContent = readableError(error.message); }
}

async function loadWorkspace(file) {
  const button = $("#load-workspace");
  button.disabled = true;
  const status = $("#workspace-status");
  status.textContent = "Restoring workspace…";
  try {
    if (file.size > 6 * 1024 * 1024) throw new Error("Please choose a workspace file smaller than 6 MB.");
    let saved;
    try { saved = JSON.parse(await file.text()); } catch { throw new Error("This is not a valid JSON workspace file."); }
    if (saved?.format !== "hanabi-lab-workspace" || saved.version !== 1) throw new Error("Choose a file downloaded with Save workspace. Game recordings belong in Replay.");
    // Validate and rebuild before replacing any visible state.
    const position = await api("/api/validate-position", saved.position);
    const watch = saved.watch ? await restoreRecording(saved.watch) : null;
    const replay = saved.replay ? await restoreRecording(saved.replay) : null;
    const play = saved.play ? await api("/api/play/restore", saved.play) : null;
    state.restoring = true;
    stopTimeline("watch"); stopTimeline("replay"); stopPlayReview(); stopPlaySequence(true); closeDeckOrder();
    state.position = position; state.cardKinds = null;
    state.timelines = { watch, replay }; state.playSession = play; state.playActionMenu = null;
    state.playAdvice = null; state.playAdviceLoading = false;
    state.watchDeckOpen = false; state.replayDeckOpen = false;
    state.timelineIndexes = Object.fromEntries(["watch", "replay"].map(mode => [mode, Math.max(0, Math.min(Number.isInteger(saved.indexes?.[mode]) ? saved.indexes[mode] : 0, (state.timelines[mode]?.timeline.length || 1) - 1))]));
    state.lastAnimatedTurns = { watch: null, replay: null, play: play?.timeline.length - 1 };
    showPositionEditor(); renderPositionEditor();
    $("#history-source").hidden = true;
    if (watch) { $("#watch-bot").value = watch.bot.key; $("#watch-seed").value = watch.seed ?? 42; }
    if (play) { $("#play-bot").value = play.bot.key; updatePlaySeatOptions(); $("#play-seat").value = play.humanSeat; $("#play-seed").value = play.seed; }
    renderTimeline("watch"); renderTimeline("replay");
    $("#export-play").disabled = !play;
    if (play) renderPlayGame(); else $("#play-shell").innerHTML = '<div class="timeline-empty"><h3>Start a game</h3></div>';
    switchMode(["position", "watch", "replay", "play", "help"].includes(saved.mode) ? saved.mode : "position");
    state.unsaved = false;
    status.textContent = "Workspace restored · games use the current strategy engine";
  } catch (error) { status.textContent = `Could not restore: ${readableError(error.message)}`; }
  finally { state.restoring = false; button.disabled = false; $("#workspace-file").value = ""; }
}

function setDebugMode(enabled) {
  state.debugMode = enabled;
  if (!enabled) state.watchDeckOpen = false;
  if (!enabled) state.replayDeckOpen = false;
  if (!enabled) stopPlayReview();
  if (!enabled && !Number.isInteger(state.playSequenceEnd)) {
    state.playFrameIndex = null;
    state.playReviewing = false;
  }
  document.body.classList.toggle("debug-mode", state.debugMode);
  $$(".card-editor[data-debug-title]").forEach(editor => {
    editor.title = state.debugMode ? editor.dataset.debugTitle : "";
  });
  if (state.playSession) renderPlayGame();
  if (state.timelines.watch) renderTimeline("watch");
  if (state.timelines.replay) renderTimeline("replay");
}

async function init() {
  state.config = await api("/api/config");
  const debugToggle = $("#debug-mode");
  debugToggle.checked = state.debugMode;
  setDebugMode(state.debugMode);
  debugToggle.addEventListener("change", () => setDebugMode(debugToggle.checked));
  const engineStatus = $("#engine-status");
  engineStatus.classList.remove("loading");
  engineStatus.lastChild.textContent = " Strategy engine ready";
  botOptions($("#position-bot"));
  botOptions($("#watch-bot"));
  botOptions($("#play-bot"));
  updatePlaySeatOptions();
  $("#position-bot").addEventListener("change", event => resetPosition(event.target.value));
  $("#reset-position").addEventListener("click", () => resetPosition());
  $("#randomize-position").addEventListener("click", randomizeLikelyPosition);
  $("#analyze-position").addEventListener("click", analyzePosition);
  $("#continue-position").addEventListener("click", () => continueFromPosition($("#continue-position")));
  $("#deck-count").addEventListener("click", openDeckOrder);
  $("#close-deck-order").addEventListener("click", applyDeckOrder);
  $("#cancel-deck-order").addEventListener("click", closeDeckOrder);
  $("#reset-deck-order").addEventListener("click", () => {
    state.deckDraft = [...state.deckOriginal];
    state.deckOrderSelection = null;
    renderDeckOrder();
  });
  $("#shuffle-deck-order").addEventListener("click", () => { state.deckDraft = shuffledCards(state.deckDraft); state.deckOrderSelection = null; renderDeckOrder(); });
  $("#save-workspace").addEventListener("click", saveWorkspace);
  $("#load-workspace").addEventListener("click", () => $("#workspace-file").click());
  $("#workspace-file").addEventListener("change", event => event.target.files[0] && loadWorkspace(event.target.files[0]));
  $("#export-play").addEventListener("click", () => {
    if (!state.playSession) return;
    downloadJSON({ format: "hanabi-lab-recording", version: 1, source: { type: "human", payload: state.playSession.resume } }, "hanabi-human-game.json");
  });
  $("#generate-game").addEventListener("click", generateGame);
  $("#random-watch-seed").addEventListener("click", () => randomizeSeed("watch-seed"));
  $("#play-bot").addEventListener("change", updatePlaySeatOptions);
  $("#random-play-seed").addEventListener("click", () => randomizeSeed("play-seed"));
  $("#start-play").addEventListener("click", startPlayGame);
  $("#replay-file").addEventListener("change", async event => { if (event.target.files[0]) await loadReplay(event.target.files[0]); event.target.value = ""; });
  await resetPosition("simple-3p");
  renderTimeline("watch"); renderTimeline("replay");
  if (matchMedia("(max-width: 1180px)").matches) $("#card-bank-details").open = false;
  $("#mode-position").addEventListener("change", markUnsaved);
  $("#mode-position").addEventListener("click", event => {
    if (event.target.closest('[data-position-token], [data-acting-seat], [data-bank-discard], [data-bank-return], [data-auto-recommendation], #reset-position')) markUnsaved();
  });
}

// Static Help stays available while the Python engine loads or if it cannot start.
$$(".mode-tab").forEach(button => button.addEventListener("click", () => switchMode(button.dataset.mode)));
window.addEventListener("beforeunload", event => {
  const draftChanged = state.deckDraft && JSON.stringify(state.deckDraft) !== JSON.stringify(state.deckOriginal);
  if (!state.unsaved && !draftChanged) return;
  event.preventDefault(); event.returnValue = "";
});
document.addEventListener("keydown", event => {
  if (event.key !== "Escape") return;
  if (state.deckDraft) closeDeckOrder();
  if (state.playActionMenu) closePlayActions();
});
init().catch(error => {
  $("#engine-status").classList.remove("loading");
  $("#engine-status").lastChild.textContent = " Strategy engine unavailable";
  $("#position-error").textContent = `Could not start the lab: ${error.message}. Help is still available.`;
});
