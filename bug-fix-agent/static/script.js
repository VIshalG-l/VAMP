/* ============================================================
   VAMP-SENTINEL
   CEO DASHBOARD FRONTEND

   Backend workflow preserved:
       /run
       /logs

   This file controls presentation only.
   ============================================================ */


/* ============================================================
   ELEMENTS
   ============================================================ */

const terminal =
    document.getElementById("terminal");

const diagnosisBtn =
    document.getElementById("diagnosisBtn");

const clearBtn =
    document.getElementById("clearBtn");

const runCountEl =
    document.getElementById("runCount");

const elapsedEl =
    document.getElementById("elapsedTime");

const fixedCountEl =
    document.getElementById("fixedCount");

const repairMetric =
    document.getElementById("repairMetric");

const elapsedMetric =
    document.getElementById("elapsedMetric");

const monitorMetric =
    document.getElementById("monitorMetric");

const monitorIndicator =
    document.getElementById("monitorIndicator");

const systemStatus =
    document.getElementById("systemStatus");

const incidentTitle =
    document.getElementById("incidentTitle");

const incidentBadge =
    document.getElementById("incidentBadge");

const incidentContent =
    document.getElementById("incidentContent");


/* ============================================================
   STATE
   ============================================================ */

let logTimer = null;

let completionTimer = null;

let clockTimer = null;

let lastText = "";

let runCount = 0;

let fixedCount = 0;

let runStart = null;

let running = false;


/* ============================================================
   STATISTICS
   ============================================================ */

function bumpStatCard(element) {

    if (!element) {
        return;
    }

    const card =
        element.closest(
            ".summary-card, .metric-card"
        );

    if (!card) {
        return;
    }

    card.classList.remove("pulse");

    void card.offsetWidth;

    card.classList.add("pulse");
}


function setRunCount(value) {

    runCount =
        value;

    if (runCountEl) {

        runCountEl.textContent =
            runCount;

        bumpStatCard(
            runCountEl
        );
    }
}


function setFixedCount(value) {

    fixedCount =
        value;

    if (fixedCountEl) {

        fixedCountEl.textContent =
            fixedCount;
    }


    if (repairMetric) {

        repairMetric.textContent =
            fixedCount;
    }


    bumpStatCard(
        fixedCountEl
    );
}


/* ============================================================
   CLOCK
   ============================================================ */

function formatElapsed(milliseconds) {

    const totalSeconds =
        Math.floor(
            milliseconds / 1000
        );


    const minutes =
        String(
            Math.floor(
                totalSeconds / 60
            )
        ).padStart(2, "0");


    const seconds =
        String(
            totalSeconds % 60
        ).padStart(2, "0");


    return `${minutes}:${seconds}`;
}


function updateElapsedDisplay(value) {

    if (elapsedEl) {
        elapsedEl.textContent =
            value;
    }

    if (elapsedMetric) {
        elapsedMetric.textContent =
            value;
    }
}


function startClock() {

    runStart =
        Date.now();


    updateElapsedDisplay(
        "00:00"
    );


    if (clockTimer) {

        clearInterval(
            clockTimer
        );
    }


    clockTimer =
        setInterval(() => {

            const elapsed =
                formatElapsed(
                    Date.now() -
                    runStart
                );

            updateElapsedDisplay(
                elapsed
            );

        }, 1000);
}


function stopClock() {

    if (clockTimer) {

        clearInterval(
            clockTimer
        );

        clockTimer =
            null;
    }


    if (runStart) {

        updateElapsedDisplay(
            formatElapsed(
                Date.now() -
                runStart
            )
        );
    }
}


/* ============================================================
   DASHBOARD STATE
   ============================================================ */

function setMonitoringState() {

    document.body.classList.remove(
        "success",
        "failure"
    );

    document.body.classList.add(
        "running"
    );


    if (systemStatus) {

        systemStatus.textContent =
            "DIAGNOSIS ACTIVE";
    }


    if (monitorMetric) {

        monitorMetric.textContent =
            "ACTIVE";
    }


    if (monitorIndicator) {

        monitorIndicator.className =
            "metric-indicator blue";

        monitorIndicator.textContent =
            "●";
    }


    if (incidentTitle) {

        incidentTitle.textContent =
            "VAMP diagnosis in progress";
    }


    if (incidentBadge) {

        incidentBadge.textContent =
            "● ACTIVE";

        incidentBadge.style.color =
            "#38bdf8";
    }


    if (incidentContent) {

        incidentContent.innerHTML = `

            <div class="monitor-orb">

                <span></span>

            </div>

            <h3>
                Analyzing Android runtime
            </h3>

            <p>
                VAMP is collecting evidence and
                processing the active Android failure.
            </p>

            <div class="failure-types">

                <span>DETECT</span>
                <span>ANALYZE</span>
                <span>REPAIR</span>
                <span>VERIFY</span>

            </div>
        `;
    }
}


function setWaitingState() {

    document.body.classList.remove(
        "running",
        "success",
        "failure"
    );


    if (systemStatus) {

        systemStatus.textContent =
            "SYSTEM OPERATIONAL";
    }


    if (monitorMetric) {

        monitorMetric.textContent =
            "READY";
    }


    if (monitorIndicator) {

        monitorIndicator.className =
            "metric-indicator blue";

        monitorIndicator.textContent =
            "●";
    }


    if (incidentTitle) {

        incidentTitle.textContent =
            "Runtime monitoring";
    }


    if (incidentBadge) {

        incidentBadge.textContent =
            "● MONITORING";

        incidentBadge.style.color =
            "";
    }


    if (incidentContent) {

        incidentContent.innerHTML = `

            <div class="monitor-orb">

                <span></span>

            </div>

            <h3>
                Waiting for Android failure
            </h3>

            <p>
                VAMP is continuously monitoring runtime
                signals from the connected Android device.
            </p>

            <div class="failure-types">

                <span>ANR</span>
                <span>JAVA</span>
                <span>KOTLIN</span>
                <span>NATIVE</span>

            </div>
        `;
    }
}


/* ============================================================
   LOG ANALYSIS
   ============================================================ */

function updateDashboardFromLogs(text) {

    const lower =
        text.toLowerCase();


    /*
     * Failure detected
     */

    const failureDetected =
        lower.includes(
            "failure detected"
        ) ||
        lower.includes(
            "incident detected"
        ) ||
        lower.includes(
            "fatal exception"
        ) ||
        lower.includes(
            "fatal signal"
        ) ||
        lower.includes(
            "anr"
        );


    /*
     * Successful completion
     */

    const successDetected =
        lower.includes(
            "result: success"
        ) ||
        lower.includes(
            "verification completed"
        ) ||
        lower.includes(
            "tests passed"
        );


    /*
     * Failed completion
     */

    const failureResult =
        lower.includes(
            "result: failed"
        ) ||
        lower.includes(
            "verification failed"
        );


    if (failureDetected) {

        document.body.classList.remove(
            "running"
        );

        document.body.classList.add(
            "failure"
        );


        if (incidentTitle) {

            incidentTitle.textContent =
                "Android incident detected";
        }


        if (incidentBadge) {

            incidentBadge.textContent =
                "● INCIDENT";
        }
    }


    if (successDetected) {

        document.body.classList.remove(
            "running",
            "failure"
        );

        document.body.classList.add(
            "success"
        );


        if (systemStatus) {

            systemStatus.textContent =
                "REPAIR VERIFIED";
        }


        if (monitorMetric) {

            monitorMetric.textContent =
                "VERIFIED";
        }


        if (incidentTitle) {

            incidentTitle.textContent =
                "Repair verified successfully";
        }


        if (incidentBadge) {

            incidentBadge.textContent =
                "✓ VERIFIED";
        }
    }


    if (failureResult) {

        document.body.classList.remove(
            "running",
            "success"
        );

        document.body.classList.add(
            "failure"
        );


        if (systemStatus) {

            systemStatus.textContent =
                "REPAIR FAILED";
        }


        if (monitorMetric) {

            monitorMetric.textContent =
                "FAILED";
        }


        if (incidentTitle) {

            incidentTitle.textContent =
                "Verification requires attention";
        }


        if (incidentBadge) {

            incidentBadge.textContent =
                "● FAILED";
        }
    }
}


/* ============================================================
   BUTTON STATE
   ============================================================ */

function setButtonsDisabled(disabled) {

    if (diagnosisBtn) {

        diagnosisBtn.disabled =
            disabled;
    }
}


/* ============================================================
   CURRENT APPLICATION
   ============================================================ */

function setCurrentApplication(packageName) {

    const application =
        document.getElementById(
            "currentApplication"
        );

    const detail =
        document.getElementById(
            "applicationDetail"
        );

    const status =
        document.getElementById(
            "applicationStatus"
        );


    if (!application) {
        return;
    }


    if (!packageName) {

        application.textContent =
            "Waiting for application";

        if (detail) {

            detail.textContent =
                "VAMP will identify the application " +
                "from Android runtime evidence.";
        }

        if (status) {

            status.textContent =
                "WAITING";
        }

        return;
    }


    application.textContent =
        packageName;


    if (detail) {

        detail.textContent =
            "Application discovered dynamically " +
            "from Android runtime evidence.";
    }


    if (status) {

        status.textContent =
            "DISCOVERED";
    }
}


function extractCurrentApplication(text) {

    if (!text) {
        return null;
    }


    /*
     * Prefer explicit package/application information
     * printed by the VAMP pipeline.
     */

    const patterns = [

        /Application\s*:\s*([A-Za-z0-9_.$-]+(?:\.[A-Za-z0-9_.$-]+)+)/i,

        /Package\s*(?:Name)?\s*:\s*([A-Za-z0-9_.$-]+(?:\.[A-Za-z0-9_.$-]+)+)/i,

        /package(?:Name)?\s*=\s*([A-Za-z0-9_.$-]+(?:\.[A-Za-z0-9_.$-]+)+)/i,

        /Process\s*:\s*([A-Za-z0-9_.$-]+(?:\.[A-Za-z0-9_.$-]+)+)/i,

        /(?:FATAL EXCEPTION|ANR).*?\bin\s+([A-Za-z0-9_.$-]+(?:\.[A-Za-z0-9_.$-]+)+)/i
    ];


    for (
        const pattern of patterns
    ) {

        const match =
            text.match(pattern);


        if (
            match &&
            match[1]
        ) {

            return match[1];
        }
    }


    /*
     * Android Java crash format:
     *
     * Process: com.example.app, PID: 1234
     */

    const processMatch =
        text.match(
            /Process:\s*([A-Za-z0-9_.$-]+(?:\.[A-Za-z0-9_.$-]+)+)/i
        );


    if (
        processMatch &&
        processMatch[1]
    ) {

        return processMatch[1];
    }


    /*
     * ANR format:
     *
     * ANR in com.example.app
     */

    const anrMatch =
        text.match(
            /\bANR\s+in\s+([A-Za-z0-9_.$-]+(?:\.[A-Za-z0-9_.$-]+)+)/i
        );


    if (
        anrMatch &&
        anrMatch[1]
    ) {

        return anrMatch[1];
    }


    return null;
}


function updateCurrentApplication(text) {

    const packageName =
        extractCurrentApplication(
            text
        );


    if (packageName) {

        setCurrentApplication(
            packageName
        );
    }
}


/* ============================================================
   LOG POLLING
   ============================================================ */

async function updateLogs() {

    try {

        const response =
            await fetch(
                "/logs",
                {
                    cache: "no-store"
                }
            );


        const text =
            await response.text();


        if (text !== lastText) {

            terminal.innerText =
                text;


            lastText =
                text;


            terminal.scrollTop =
                terminal.scrollHeight;


            updateDashboardFromLogs(
                text
            );

            updateCurrentApplication(
                text
            );
        }

    }

    catch (error) {

        /*
         * Preserve existing behavior:
         * log polling errors do not stop
         * the VAMP workflow.
         */
    }
}


/* ============================================================
   DEMO FALLBACK
   ============================================================ */

const DEMO_LOGS = {

    anr: [

        "Starting VAMP diagnosis...",

        "Connected to Android device",

        "Collecting logs from logcat",

        "Analyzing Android failure",

        "Failure detected",

        "Searching source for offending code",

        "Generating patch...",

        "Building project",

        "Installing updated APK",

        "Running verification",

        "VAMP diagnosis completed successfully"

    ]

};


function simulateRun(type) {

    const lines =
        DEMO_LOGS[type] ||
        DEMO_LOGS.anr;


    let index = 0;


    const push =
        () => {

            if (
                index >=
                lines.length
            ) {

                return;
            }


            const time =
                new Date()
                    .toTimeString()
                    .slice(0, 8);


            terminal.innerText +=
                `${time}  ${lines[index]}\n`;


            terminal.scrollTop =
                terminal.scrollHeight;


            updateDashboardFromLogs(
                terminal.innerText
            );


            index++;


            if (
                index <
                lines.length
            ) {

                setTimeout(
                    push,
                    900 +
                    Math.random() * 700
                );
            }
        };


    push();
}


/* ============================================================
   START VAMP DIAGNOSIS
   ============================================================ */

async function startPipeline() {

    if (running) {
        return;
    }


    running =
        true;


    setButtonsDisabled(
        true
    );


    terminal.innerText =
        "";


    lastText =
        "";


    setRunCount(
        runCount + 1
    );


    startClock();


    setMonitoringState();


    /*
     * GENERIC VAMP BACKEND ENDPOINT.
     *
     * The failure type and application are discovered dynamically.
     */

    fetch("/run")
        .catch(() => {

            /*
             * Existing local demonstration
             * fallback.
             */

            simulateRun(
                "anr"
            );
        });


    if (logTimer) {

        clearInterval(
            logTimer
        );
    }


    logTimer =
        setInterval(
            updateLogs,
            500
        );


    /*
     * Keep monitoring the backend log
     * until it reports completion.
     */

    monitorCompletion();

}


/* ============================================================
   COMPLETION MONITOR
   ============================================================ */

function monitorCompletion() {

    /*
     * IMPORTANT:
     *
     * Result: SUCCESS / Result: FAILED are only terminal
     * messages. They do NOT mean that main.py has exited.
     *
     * The UI continues displaying /logs until the actual
     * backend subprocess exits.
     */

    if (completionTimer) {

        clearInterval(
            completionTimer
        );

        completionTimer =
            null;
    }


    completionTimer =
        setInterval(
            async () => {

                if (!running) {

                    return;
                }


                try {

                    /*
                     * Always fetch the latest terminal output first.
                     */
                    await updateLogs();


                    const response =
                        await fetch(
                            "/status",
                            {
                                cache: "no-store"
                            }
                        );


                    if (!response.ok) {

                        return;
                    }


                    const state =
                        await response.json();


                    /*
                     * ONLY the actual subprocess state can
                     * complete the UI run.
                     */
                    if (
                        state.running === false
                    ) {

                        /*
                         * One final fetch ensures that every
                         * last line written by main.py is visible
                         * in the UI before polling stops.
                         */
                        await updateLogs();


                        clearInterval(
                            completionTimer
                        );

                        completionTimer =
                            null;


                        finishRun(
                            terminal.innerText
                                .toLowerCase()
                                .includes(
                                    "result: success"
                                )
                        );

                    }

                }

                catch (error) {

                    /*
                     * Never stop the VAMP UI because of a
                     * temporary status request failure.
                     */
                }

            },
            500
        );
}


/* ============================================================
   FINISH
   ============================================================ */

function finishRun(success) {

    if (completionTimer) {

        clearInterval(
            completionTimer
        );

        completionTimer =
            null;
    }


    stopClock();


    if (success) {

        setFixedCount(
            fixedCount + 1
        );

    }


    running =
        false;


    /*
     * The actual main.py process has exited at this point.
     * The final /logs fetch has already happened in
     * monitorCompletion(), so it is now safe to stop polling.
     */
    if (logTimer) {

        clearInterval(
            logTimer
        );

        logTimer =
            null;
    }


    setButtonsDisabled(
        false
    );


    if (success) {

        document.body.classList.remove(
            "running",
            "failure"
        );

        document.body.classList.add(
            "success"
        );


        if (systemStatus) {

            systemStatus.textContent =
                "REPAIR VERIFIED";
        }


        if (monitorMetric) {

            monitorMetric.textContent =
                "VERIFIED";
        }


        if (incidentTitle) {

            incidentTitle.textContent =
                "Repair verified successfully";
        }


        if (incidentBadge) {

            incidentBadge.textContent =
                "✓ VERIFIED";
        }

    } else {

        document.body.classList.remove(
            "running",
            "success"
        );

        document.body.classList.add(
            "failure"
        );


        if (systemStatus) {

            systemStatus.textContent =
                "REPAIR FAILED";
        }


        if (monitorMetric) {

            monitorMetric.textContent =
                "FAILED";
        }


        if (incidentTitle) {

            incidentTitle.textContent =
                "Verification requires attention";
        }


        if (incidentBadge) {

            incidentBadge.textContent =
                "● FAILED";
        }
    }
}


/* ============================================================
   DIAGNOSIS BUTTON
   ============================================================ */

if (diagnosisBtn) {

    diagnosisBtn.onclick =
        function () {

            startPipeline();

        };
}


/* ============================================================
   CLEAR ACTIVITY
   ============================================================ */

if (clearBtn) {

    clearBtn.onclick =
        () => {

            if (terminal) {

                terminal.innerText =
                    "Waiting for VAMP activity...";
            }


            lastText =
                "";


            stopClock();


            updateElapsedDisplay(
                "00:00"
            );


            runStart =
                null;


            /*
             * If VAMP is still running, keep monitoring the
             * actual terminal process. Clear Activity only
             * clears the visible UI.
             */
            if (!running) {

                if (logTimer) {

                    clearInterval(
                        logTimer
                    );

                    logTimer =
                        null;
                }


                if (completionTimer) {

                    clearInterval(
                        completionTimer
                    );

                    completionTimer =
                        null;
                }

            }


            setButtonsDisabled(
                !running
            );


            setWaitingState();
        };
}


/* ============================================================
   INITIALIZATION
   ============================================================ */

setWaitingState();

setCurrentApplication(
    null
);

updateElapsedDisplay(
    "00:00"
);

