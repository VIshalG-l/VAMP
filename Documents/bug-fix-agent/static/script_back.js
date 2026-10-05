/* ---------------- Elements ---------------- */

const terminal = document.getElementById("terminal");

const anrBtn     = document.getElementById("anrBtn");
const displayBtn = document.getElementById("displayBtn");
const clearBtn   = document.getElementById("clearBtn");

const runCountEl   = document.getElementById("runCount");
const elapsedEl    = document.getElementById("elapsedTime");
const fixedCountEl = document.getElementById("fixedCount");

const pipelineSteps = ["collect", "analyze", "search", "patch", "build", "test", "report"];

let logTimer = null;
let clockTimer = null;
let lastText = "";
let runCount = 0;
let fixedCount = 0;
let runStart = null;
let running = false;

/* ---------------- Stats helpers ---------------- */

function bumpStatCard(el) {
    const card = el.closest(".stat-card");
    if (!card) return;
    card.classList.add("pulse");
    setTimeout(() => card.classList.remove("pulse"), 600);
}

function setRunCount(n) {
    runCount = n;
    runCountEl.textContent = runCount;
    bumpStatCard(runCountEl);
}

function setFixedCount(n) {
    fixedCount = n;
    fixedCountEl.textContent = fixedCount;
    bumpStatCard(fixedCountEl);
}

function formatElapsed(ms) {
    const totalSeconds = Math.floor(ms / 1000);
    const mm = String(Math.floor(totalSeconds / 60)).padStart(2, "0");
    const ss = String(totalSeconds % 60).padStart(2, "0");
    return `${mm}:${ss}`;
}

function startClock() {
    runStart = Date.now();
    elapsedEl.textContent = "00:00";
    if (clockTimer) clearInterval(clockTimer);
    clockTimer = setInterval(() => {
        elapsedEl.textContent = formatElapsed(Date.now() - runStart);
    }, 1000);
}

function stopClock() {
    if (clockTimer) {
        clearInterval(clockTimer);
        clockTimer = null;
    }
    if (runStart) {
        elapsedEl.textContent = formatElapsed(Date.now() - runStart);
    }
}

/* ---------------- Pipeline ---------------- */

function resetPipeline() {
    pipelineSteps.forEach(id => {
        const step = document.getElementById(id);
        if (!step) return;
        step.textContent = "○ " + step.textContent.replace(/^✓ |^⏳ |^✖ /, "");
        step.style.color = "#cbd5e1";
        step.style.fontWeight = "500";
    });
}

function runPipelineAnimation(onComplete) {

    resetPipeline();

    let index = 0;

    const animation = setInterval(() => {

        if (index > 0) {
            const prev = document.getElementById(pipelineSteps[index - 1]);
            prev.textContent = "✓ " + prev.textContent.replace(/^○ |^⏳ /, "");
            prev.style.color = "#22c55e";
            prev.style.fontWeight = "700";
        }

        if (index < pipelineSteps.length) {
            const step = document.getElementById(pipelineSteps[index]);
            step.textContent = "⏳ " + step.textContent.replace(/^○ |^✓ /, "");
            step.style.color = "#3b82f6";
            step.style.fontWeight = "700";
            index++;
        } else {
            clearInterval(animation);
            if (typeof onComplete === "function") onComplete();
        }

    }, 2500);

}

/* ---------------- Pipeline Start ---------------- */

async function startPipeline(type) {

    if (running) return; // ignore clicks mid-run

    running = true;
    setButtonsDisabled(true);

    terminal.innerText = "";
    lastText = "";

    setRunCount(runCount + 1);
    startClock();

    runPipelineAnimation(() => {
        stopClock();
        setFixedCount(fixedCount + 1);
        running = false;
        setButtonsDisabled(false);
        if (logTimer) {
            clearInterval(logTimer);
            logTimer = null;
        }
    });

    fetch("/run/" + type).catch(() => {
        // No backend available - fall back to a local demo log stream
        simulateRun(type);
    });

    if (logTimer)
        clearInterval(logTimer);

    logTimer = setInterval(updateLogs, 500);

}

function setButtonsDisabled(disabled) {
    anrBtn.disabled = disabled;
    displayBtn.disabled = disabled;
}

/* ---------------- Console ---------------- */

async function updateLogs() {

    try {

        const response = await fetch("/logs");

        const text = await response.text();

        if (text !== lastText) {

            terminal.innerText = text;

            lastText = text;

            terminal.scrollTop = terminal.scrollHeight;

        }

    }

    catch (e) {

        // handled by simulateRun fallback when /run + /logs endpoints are absent

    }

}

/* ---------------- Demo Simulation (used when no backend is present) ---------------- */

const DEMO_LOGS = {
    anr: [
        "Starting ANR analysis...",
        "Connected to device: emulator-5554",
        "Collecting logs from logcat",
        "Analyzing thread dumps for blocked main thread",
        "Potential ANR detected in com.example.app",
        "Searching source for offending call",
        "Generating patch...",
        "Building project",
        "Running tests",
        "Generating report",
        "ANR analysis completed successfully"
    ],
    display: [
        "Starting crash analysis...",
        "Connected to device: emulator-5554",
        "Collecting logs from logcat",
        "NullPointerException in MainActivity.java:45",
        "Searching source for offending call",
        "Generating patch...",
        "Building project",
        "Running tests",
        "Generating report",
        "Crash analysis completed successfully"
    ]
};

function simulateRun(type) {
    const lines = DEMO_LOGS[type] || DEMO_LOGS.anr;
    let i = 0;

    const push = () => {
        if (i >= lines.length) return;
        const time = new Date().toTimeString().slice(0, 8);
        terminal.innerText += `${time}  ${lines[i]}\n`;
        terminal.scrollTop = terminal.scrollHeight;
        i++;
        if (i < lines.length) setTimeout(push, 900 + Math.random() * 700);
    };

    push();
}

/* ---------------- Buttons ---------------- */

anrBtn.onclick=function(){

    startPipeline("anr");

}

displayBtn.onclick=function(){

    startPipeline("display");

}
clearBtn.onclick = () => {

    terminal.innerText = "Waiting...";
    lastText = "";
    resetPipeline();

    stopClock();
    elapsedEl.textContent = "00:00";
    runStart = null;

    if (logTimer) {
        clearInterval(logTimer);
        logTimer = null;
    }

    running = false;
    setButtonsDisabled(false);

};

/* ---------------- Init ---------------- */

resetPipeline();
