// Host board WebSocket client and game controls

import type {
  BoardClue,
  BoardUpdate,
  ClueSelected,
  BuzzWinner,
  JudgeResult,
  FinalJeopardyClue,
  FinalResult,
  DailyDouble,
  HostEvent,
  GameStateResponse,
} from "./types.js";

// Globals injected by the template
declare const gameId: string;

let ws: WebSocket | null = null;
let boardData: Record<string, BoardClue[]> = {};
let scores: Record<string, number> = {};
let teamNames: Record<string, string> = {};
let currentClueId: string | null = null;
let currentAnswer: string | null = null;

// --- Helpers ---

function $(id: string): HTMLElement {
  return document.getElementById(id)!;
}

function show(id: string): void {
  $(id).classList.remove("hidden");
}

function hide(id: string): void {
  $(id).classList.add("hidden");
}

// --- WebSocket ---

function connect(): void {
  const protocol = location.protocol === "https:" ? "wss:" : "ws:";
  ws = new WebSocket(`${protocol}//${location.host}/ws/host/${gameId}`);

  ws.onopen = (): void => {
    console.log("Host WebSocket connected");
    fetchBoardState();
  };

  ws.onmessage = (event: MessageEvent): void => {
    const data: HostEvent = JSON.parse(event.data as string);
    handleMessage(data);
  };

  ws.onclose = (): void => {
    console.log("Host WebSocket disconnected, reconnecting...");
    setTimeout(connect, 2000);
  };

  ws.onerror = (err: Event): void => {
    console.error("WebSocket error:", err);
  };
}

function handleMessage(data: HostEvent): void {
  switch (data.type) {
    case "BOARD_UPDATE":
      boardData = data.board;
      scores = data.scores;
      teamNames = data.team_names;
      renderBoard();
      renderScoreboard();
      break;

    case "CLUE_SELECTED":
      showClueOverlay(data);
      break;

    case "BUZZ_WINNER":
      showBuzzWinner(data);
      break;

    case "BUZZ_TIMEOUT":
      showBuzzTimeout();
      break;

    case "JUDGE_RESULT":
      showJudgeResult(data);
      break;

    case "SCORE_UPDATE":
      scores = data.scores;
      teamNames = data.team_names;
      renderScoreboard();
      break;

    case "ANSWER_REVEAL":
      currentAnswer = data.answer;
      break;

    case "GAME_STATUS":
      handleStatusChange(data.status);
      break;

    case "FINAL_JEOPARDY_CLUE":
      showFinalJeopardy(data);
      break;

    case "FINAL_REVEAL":
      showFinalResults(data.results);
      break;

    case "TEAM_JOINED":
      fetchBoardState();
      break;

    case "CLUE_COMPLETE":
      hideClueOverlay();
      break;

    case "DAILY_DOUBLE":
      showDailyDouble();
      break;
  }
}

// --- API calls ---

async function fetchBoardState(): Promise<void> {
  try {
    const resp = await fetch(`/api/games/${gameId}`);
    if (resp.ok) {
      const data: GameStateResponse = await resp.json();
      scores = {};
      teamNames = {};
      for (const team of data.teams) {
        scores[team.team_id] = team.score;
        teamNames[team.team_id] = team.name;
      }
      if (Object.keys(data.board).length > 0) {
        boardData = data.board;
        renderBoard();
      }
      renderScoreboard();
    }
  } catch (e) {
    console.error("Failed to fetch board state:", e);
  }
}

async function selectClue(clueId: string): Promise<void> {
  currentClueId = clueId;
  try {
    const resp = await fetch(`/api/games/${gameId}/select`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ clue_id: clueId }),
    });
    if (!resp.ok) {
      const err = await resp.json();
      console.error("Select clue error:", err.detail);
    }
  } catch (e) {
    console.error("Failed to select clue:", e);
  }
}

async function judgeAnswer(correct: boolean): Promise<void> {
  try {
    const resp = await fetch(`/api/games/${gameId}/judge`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ correct }),
    });
    if (!resp.ok) {
      const err = await resp.json();
      console.error("Judge error:", err.detail);
    }
  } catch (e) {
    console.error("Failed to judge:", e);
  }
}

async function skipClue(): Promise<void> {
  try {
    const resp = await fetch(`/api/games/${gameId}/skip`, { method: "POST" });
    if (!resp.ok) {
      const err = await resp.json();
      console.error("Skip error:", err.detail);
    }
  } catch (e) {
    console.error("Failed to skip:", e);
  }
}

async function refetchClues(): Promise<void> {
  try {
    const resp = await fetch(`/api/games/${gameId}/refetch`, { method: "POST" });
    if (!resp.ok) {
      const err = await resp.json();
      console.error("Refetch error:", err.detail);
    }
  } catch (e) {
    console.error("Failed to refetch:", e);
  }
}

async function startFinalJeopardy(): Promise<void> {
  try {
    const resp = await fetch(`/api/games/${gameId}/final-jeopardy/start`, {
      method: "POST",
    });
    if (!resp.ok) {
      const err = await resp.json();
      console.error("Final Jeopardy error:", err.detail);
    }
  } catch (e) {
    console.error("Failed to start Final Jeopardy:", e);
  }
}

async function revealFinalAnswers(): Promise<void> {
  try {
    const resp = await fetch(`/api/games/${gameId}/final-jeopardy/reveal`, {
      method: "POST",
    });
    if (!resp.ok) {
      const err = await resp.json();
      console.error("Reveal error:", err.detail);
    }
  } catch (e) {
    console.error("Failed to reveal:", e);
  }
}

async function judgeFinal(teamId: string, correct: boolean): Promise<void> {
  try {
    const resp = await fetch(
      `/api/games/${gameId}/final-jeopardy/judge/${teamId}`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ correct }),
      }
    );
    if (!resp.ok) {
      const err = await resp.json();
      console.error("Final judge error:", err.detail);
    }
  } catch (e) {
    console.error("Failed to judge final:", e);
  }
}

async function finishGame(): Promise<void> {
  try {
    const resp = await fetch(`/api/games/${gameId}/finish`, { method: "POST" });
    if (!resp.ok) {
      const err = await resp.json();
      console.error("Finish error:", err.detail);
    }
  } catch (e) {
    console.error("Failed to finish:", e);
  }
}

// --- Rendering ---

function renderBoard(): void {
  const boardEl = $("board");
  const categories = Object.keys(boardData);

  if (categories.length === 0) {
    boardEl.innerHTML = '<p class="no-data">Waiting for board data...</p>';
    return;
  }

  // Filter out Final Jeopardy category
  const gameCategories = categories.filter(
    (c) => !c.toLowerCase().startsWith("final")
  );

  // Collect unique dollar values
  const allValues = new Set<number>();
  for (const cat of gameCategories) {
    for (const clue of boardData[cat]) {
      allValues.add(clue.dollar_value);
    }
  }
  const sortedValues = Array.from(allValues).sort((a, b) => a - b);

  let html = `<div class="board-grid" style="grid-template-columns: repeat(${gameCategories.length}, 1fr);">`;

  // Category headers
  for (const cat of gameCategories) {
    html += `<div class="category-header">${cat}</div>`;
  }

  // Clue cells
  for (const value of sortedValues) {
    for (const cat of gameCategories) {
      const clue = boardData[cat].find((c) => c.dollar_value === value);
      if (clue) {
        if (clue.is_answered) {
          const label = clue.answered_by || "";
          html += `<div class="cell answered">${label}</div>`;
        } else {
          html += `<div class="cell" onclick="selectClue('${clue.id}')">$${clue.dollar_value}</div>`;
        }
      } else {
        html += `<div class="cell empty"></div>`;
      }
    }
  }

  html += "</div>";
  boardEl.innerHTML = html;
}

function renderScoreboard(): void {
  const el = $("scoreboard");
  const teamIds = Object.keys(scores);

  if (teamIds.length === 0) {
    el.innerHTML = "";
    return;
  }

  let html = "";
  for (const tid of teamIds) {
    const name = teamNames[tid] || "Unknown";
    const score = scores[tid] || 0;
    const scoreClass = score < 0 ? "negative" : "";
    html += `<div class="score-card">
      <div class="score-name">${name}</div>
      <div class="score-value ${scoreClass}">$${score.toLocaleString()}</div>
    </div>`;
  }
  el.innerHTML = html;
}

// --- Clue overlay ---

function showControls(which: "board" | "clue" | "final" | "none"): void {
  $("bottom-controls").classList.toggle("hidden", which !== "board");
  $("clue-controls").classList.toggle("hidden", which !== "clue");
  $("final-controls").classList.toggle("hidden", which !== "final");
}

function showClueOverlay(data: ClueSelected): void {
  $("clue-category").textContent = data.category;
  $("clue-value").textContent = "$" + data.dollar_value;
  const clueEl = $("clue-text");
  if (data.clue_image_url) {
    clueEl.innerHTML = `<img src="${data.clue_image_url}" alt="Clue" style="width:100%;max-height:60vh;object-fit:contain;border-radius:8px;">`;
    if (data.clue_text) {
      clueEl.innerHTML += `<p style="margin-top:1rem;">${data.clue_text}</p>`;
    }
  } else {
    clueEl.textContent = data.clue_text;
  }
  hide("answer-text");
  hide("buzz-indicator");
  hide("daily-double-indicator");
  hide("btn-correct");
  hide("btn-incorrect");
  show("btn-reveal");
  show("btn-skip");
  show("clue-overlay");
  showControls("clue");

  if (data.is_daily_double) {
    show("daily-double-indicator");
  }
}

function showDailyDouble(): void {
  show("daily-double-indicator");
}

function hideClueOverlay(): void {
  hide("clue-overlay");
  currentClueId = null;
  currentAnswer = null;
  showControls("board");
}

function showBuzzWinner(data: BuzzWinner): void {
  $("buzz-team-name").textContent = data.team_name;
  show("buzz-indicator");
  show("btn-correct");
  show("btn-incorrect");
  hide("btn-skip");
}

function showBuzzTimeout(): void {
  $("buzz-team-name").textContent = "Time's up - no one";
  show("buzz-indicator");
}

function showJudgeResult(data: JudgeResult): void {
  if (!data.correct) {
    hide("btn-correct");
    hide("btn-incorrect");
    hide("buzz-indicator");
    show("btn-skip");
  }
}

function revealAnswer(): void {
  const answerEl = $("answer-text");
  if (currentAnswer) {
    answerEl.textContent = currentAnswer;
    answerEl.classList.remove("hidden");
  }
}

// --- Final Jeopardy ---

function showFinalJeopardy(data: FinalJeopardyClue): void {
  hide("clue-overlay");
  $("final-category").textContent = data.category;
  $("final-clue-text").textContent = data.clue_text;
  show("final-overlay");
  hide("board");
  showControls("final");
}

function showFinalResults(results: FinalResult[]): void {
  const el = $("final-results");
  let html = '<div class="final-results-list">';
  for (const r of results) {
    html += `<div class="final-result-card">
      <div class="final-team-name">${r.team_name}</div>
      <div class="final-team-answer">Answer: ${r.answer || "(none)"}</div>
      <div class="final-team-wager">Wager: $${r.wager || 0}</div>
      <div class="final-team-score">Score: $${r.score}</div>
      <div class="final-judge-btns">
        <button class="btn btn-correct" onclick="judgeFinal('${r.team_id}', true)">Correct</button>
        <button class="btn btn-incorrect" onclick="judgeFinal('${r.team_id}', false)">Incorrect</button>
      </div>
    </div>`;
  }
  html += "</div>";
  el.innerHTML = html;

  if (currentAnswer) {
    const answerEl = $("final-answer-text");
    answerEl.textContent = currentAnswer;
    answerEl.classList.remove("hidden");
  }
}

// --- Status ---

function handleStatusChange(
  status: "lobby" | "in_progress" | "final_jeopardy" | "finished"
): void {
  if (status === "finished") {
    hide("final-overlay");
    hide("clue-overlay");
    $("board").innerHTML =
      '<div class="game-over"><h1>Game Over!</h1></div>';
    showControls("none");
  }
}

// --- Teams modal ---

interface TeamQR {
  team_id: string;
  name: string;
  url: string;
  qr: string;
}

async function loadTeamsList(): Promise<void> {
  const list = $("teams-modal-list");
  list.innerHTML = "<p>Loading...</p>";

  try {
    const resp = await fetch(`/api/games/${gameId}/teams/qr`);
    if (!resp.ok) {
      list.innerHTML = "<p>Failed to load teams</p>";
      return;
    }
    const teams: TeamQR[] = await resp.json();

    let html = "";
    if (teams.length > 0) {
      html += '<div class="teams-qr-grid">';
      for (const t of teams) {
        html += `<div class="team-qr-card">
          <img src="${t.qr}" alt="QR for ${t.name}">
          <div class="team-qr-name">${t.name}</div>
          <div class="team-qr-url">${t.url}</div>
        </div>`;
      }
      html += "</div>";
    } else {
      html += "<p>No teams yet</p>";
    }

    html += `<div class="add-team-row">
      <input type="text" id="add-team-input" placeholder="Team name..." maxlength="30">
      <button class="btn btn-info" onclick="addTeam()">Add team</button>
    </div>`;

    list.innerHTML = html;
  } catch {
    list.innerHTML = "<p>Failed to load teams</p>";
  }
}

async function showTeamsModal(): Promise<void> {
  show("teams-modal");
  await loadTeamsList();
}

async function addTeam(): Promise<void> {
  const input = $("add-team-input") as HTMLInputElement;
  const name = input.value.trim();
  if (!name) return;

  input.disabled = true;
  try {
    const resp = await fetch(`/api/games/${gameId}/teams`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name }),
    });
    if (!resp.ok) {
      const err = await resp.json();
      console.error("Add team error:", err.detail);
      input.disabled = false;
      return;
    }
    await loadTeamsList();
  } catch (e) {
    console.error("Failed to add team:", e);
    input.disabled = false;
  }
}

function closeTeamsModal(): void {
  hide("teams-modal");
}

// --- Expose to global scope for onclick handlers in HTML ---

const w = window as unknown as Record<string, unknown>;
w.selectClue = selectClue;
w.judgeAnswer = judgeAnswer;
w.skipClue = skipClue;
w.refetchClues = refetchClues;
w.revealAnswer = revealAnswer;
w.startFinalJeopardy = startFinalJeopardy;
w.revealFinalAnswers = revealFinalAnswers;
w.judgeFinal = judgeFinal;
w.finishGame = finishGame;
w.showTeamsModal = showTeamsModal;
w.closeTeamsModal = closeTeamsModal;
w.addTeam = addTeam;

// Start connection
connect();
