// Team buzzer WebSocket client
let ws = null;
let buzzEnabled = false;
let hasBuzzed = false;
// --- Helpers ---
function $(id) {
    return document.getElementById(id);
}
function show(id) {
    $(id).classList.remove("hidden");
}
function hide(id) {
    $(id).classList.add("hidden");
}
function setStatus(text) {
    $("status-text").textContent = text;
}
// --- WebSocket ---
function connect() {
    const protocol = location.protocol === "https:" ? "wss:" : "ws:";
    ws = new WebSocket(`${protocol}//${location.host}/ws/team/${gameId}/${teamToken}`);
    ws.onopen = () => {
        console.log("Team WebSocket connected");
        // Status will be set by sync events from server
    };
    ws.onmessage = (event) => {
        const data = JSON.parse(event.data);
        handleMessage(data);
    };
    ws.onclose = () => {
        console.log("Team WebSocket disconnected, reconnecting...");
        setStatus("Disconnected. Reconnecting...");
        disableBuzz();
        setTimeout(connect, 2000);
    };
    ws.onerror = (err) => {
        console.error("WebSocket error:", err);
    };
}
function handleMessage(data) {
    switch (data.type) {
        case "BUZZ_OPEN":
            enableBuzz();
            break;
        case "BUZZ_LOCKED":
            disableBuzz();
            if (hasBuzzed) {
                setStatus("You buzzed in!");
            }
            else {
                setStatus(data.team_name + " buzzed in!");
            }
            break;
        case "BUZZ_TIMEOUT":
            disableBuzz();
            setStatus("Time's up!");
            break;
        case "CLUE_SELECTED":
            showClue(data);
            setStatus("Clue revealed...");
            hasBuzzed = false;
            break;
        case "SCORE_UPDATE":
            updateScore(data.scores);
            break;
        case "JUDGE_RESULT":
            handleJudgeResult(data);
            break;
        case "GAME_STATUS":
            handleStatusChange(data.status);
            break;
        case "FINAL_JEOPARDY_CLUE":
            showFinalJeopardy(data);
            break;
        case "CLUE_COMPLETE":
            hideClue();
            setStatus("Waiting for next clue...");
            disableBuzz();
            break;
        case "DAILY_DOUBLE":
            setStatus("Daily Double!");
            break;
    }
}
// --- Buzz button ---
function enableBuzz() {
    buzzEnabled = true;
    hasBuzzed = false;
    const btn = $("buzz-button");
    btn.disabled = false;
    btn.classList.add("active");
    btn.classList.remove("buzzed", "locked");
    setStatus("BUZZ NOW!");
}
function disableBuzz() {
    buzzEnabled = false;
    const btn = $("buzz-button");
    btn.disabled = true;
    btn.classList.remove("active");
    if (!hasBuzzed) {
        btn.classList.add("locked");
    }
}
function doBuzz() {
    if (!buzzEnabled || hasBuzzed)
        return;
    hasBuzzed = true;
    buzzEnabled = false;
    const btn = $("buzz-button");
    btn.disabled = true;
    btn.classList.remove("active");
    btn.classList.add("buzzed");
    const msg = { type: "BUZZ" };
    ws.send(JSON.stringify(msg));
    setStatus("You buzzed in!");
}
// --- Clue display ---
function showClue(data) {
    $("clue-category-value").textContent =
        data.category + " - $" + data.dollar_value;
    const clueEl = $("clue-text");
    if (data.clue_image_url) {
        clueEl.innerHTML = `<img src="${data.clue_image_url}" alt="Clue" style="max-width:100%;max-height:40vh;border-radius:8px;">`;
        if (data.clue_text) {
            clueEl.innerHTML += `<p style="margin-top:0.5rem;">${data.clue_text}</p>`;
        }
    }
    else {
        clueEl.textContent = data.clue_text;
    }
    show("clue-display");
    hide("final-panel");
}
function hideClue() {
    hide("clue-display");
}
// --- Score ---
function updateScore(allScores) {
    const myScore = allScores[teamId];
    if (myScore !== undefined) {
        $("score-value").textContent = myScore.toLocaleString();
    }
}
// --- Judge result ---
function handleJudgeResult(data) {
    if (data.team_id === teamId) {
        if (data.correct) {
            setStatus("Correct! +$" + data.score_delta);
        }
        else {
            setStatus("Incorrect. -$" + Math.abs(data.score_delta));
        }
    }
}
// --- Game status ---
function handleStatusChange(status) {
    if (status === "in_progress") {
        setStatus("Game started!");
    }
    else if (status === "final_jeopardy") {
        setStatus("Final Jeopardy!");
    }
    else if (status === "finished") {
        setStatus("Game over!");
        disableBuzz();
        hide("final-panel");
        hide("clue-display");
    }
}
// --- Final Jeopardy ---
async function showFinalJeopardy(data) {
    hideClue();
    disableBuzz();
    hide("buzz-container");
    $("final-category").textContent = data.category;
    $("final-clue").textContent = data.clue_text;
    show("final-panel");
    // Restore FJ form state on reconnect
    try {
        const resp = await fetch(`/api/games/${gameId}/team-state/${teamToken}`);
        if (resp.ok) {
            const state = await resp.json();
            if (state.final_wager !== null) {
                $("wager-input").value = state.final_wager;
                $("wager-input").disabled = true;
                $("wager-btn").disabled = true;
                show("answer-form");
                if (state.has_final_answer) {
                    $("answer-input").disabled = true;
                    $("answer-btn").disabled = true;
                    setStatus("Answer submitted! Waiting for results...");
                } else {
                    setStatus("Wager submitted! Enter your answer.");
                }
            }
        }
    } catch (e) {
        console.error("Failed to check team state:", e);
    }
}
async function submitWager() {
    const input = $("wager-input");
    const wager = parseInt(input.value, 10);
    if (isNaN(wager) || wager < 0) {
        setStatus("Enter a valid wager");
        return;
    }
    try {
        const resp = await fetch(`/api/games/${gameId}/final-jeopardy/wager`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ team_token: teamToken, wager }),
        });
        if (!resp.ok) {
            const err = await resp.json();
            setStatus("Error: " + err.detail);
            return;
        }
        $("wager-btn").disabled = true;
        input.disabled = true;
        show("answer-form");
        setStatus("Wager submitted! Enter your answer.");
    }
    catch {
        setStatus("Error submitting wager");
    }
}
async function submitAnswer() {
    const input = $("answer-input");
    const answer = input.value.trim();
    if (!answer) {
        setStatus("Enter an answer");
        return;
    }
    try {
        const resp = await fetch(`/api/games/${gameId}/final-jeopardy/answer`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ team_token: teamToken, answer }),
        });
        if (!resp.ok) {
            const err = await resp.json();
            setStatus("Error: " + err.detail);
            return;
        }
        $("answer-btn").disabled = true;
        input.disabled = true;
        setStatus("Answer submitted! Waiting for results...");
    }
    catch {
        setStatus("Error submitting answer");
    }
}
// --- Event listeners ---
$("buzz-button").addEventListener("click", doBuzz);
$("buzz-button").addEventListener("touchstart", (e) => {
    e.preventDefault();
    doBuzz();
});
// Expose to global scope for onclick handlers in HTML
const w = window;
w.submitWager = submitWager;
w.submitAnswer = submitAnswer;
// Start connection
connect();
export {};
//# sourceMappingURL=buzzer.js.map