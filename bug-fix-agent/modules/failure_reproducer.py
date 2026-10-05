import time
from dataclasses import dataclass
from typing import Optional

from modules.failure_verifier import FailureVerifier
from modules.ui_action_discoverer import UIActionDiscoverer
from modules.ui_action_selector import UIActionSelector
from modules.ui_action_correlator import UIActionCorrelator
from modules.ui_action_executor import UIActionExecutor


@dataclass
class ReproductionResult:
    success: bool
    action_found: bool
    action_executed: bool
    failure_reproduced: bool
    process_alive: bool
    confidence: float
    reason: str
    logs: str = ""


class FailureReproducer:
    """
    Generic Android failure reproduction engine.

    Responsibilities:

        1. Discover visible UI actions.
        2. Correlate UI actions with the incident.
        3. Apply a safety confidence threshold.
        4. Clear old logcat.
        5. Execute the selected UI action.
        6. Wait for the application to react.
        7. Collect fresh runtime evidence.
        8. Determine whether the original failure returned.

    This module does not know:

        - APK name
        - package name
        - activity name
        - button name
        - source path
        - device serial
        - fixed screen coordinates

    All application-specific information comes from the Incident
    and runtime-discovered UI information.
    """

    def __init__(
        self,
        incident,
        source_context: str = "",
        evidence_text: str = "",
        device_serial: Optional[str] = None,
        minimum_confidence: float = 0.70,
        observation_seconds: int = 8,
    ):
        self.incident = incident

        self.source_context = (
            source_context or ""
        )

        self.evidence_text = (
            evidence_text or ""
        )

        self.device_serial = (
            device_serial
            or getattr(
                incident,
                "device_serial",
                "",
            )
            or ""
        ).strip()

        self.minimum_confidence = max(
            0.0,
            min(
                1.0,
                float(minimum_confidence),
            ),
        )

        self.observation_seconds = max(
            1,
            int(observation_seconds),
        )

        self.discoverer = UIActionDiscoverer(
            device_serial=self.device_serial
        )

    # =========================================================
    # Incident helpers
    # =========================================================

    def get_package(self):
        return (
            getattr(
                self.incident,
                "package",
                "",
            )
            or ""
        ).strip()

    def get_failure_type(self):
        return (
            getattr(
                self.incident,
                "bug_type",
                "",
            )
            or "UNKNOWN"
        ).strip().upper()

    # =========================================================
    # UI discovery
    # =========================================================

    def discover_actions(self):
        print()
        print(
            "[REPRO] Discovering current Android UI..."
        )

        success, actions, message = (
            self.discoverer.discover()
        )

        if not success:
            return (
                False,
                [],
                message,
            )

        self.discoverer.print_actions(
            actions
        )

        return (
            True,
            actions,
            "UI discovery successful.",
        )

    # =========================================================
    # UI correlation
    # =========================================================

    def correlate_action(self, actions):

        print()
        print(
            "[REPRO] Correlating UI actions "
            "with failure evidence..."
        )

        correlator = UIActionCorrelator(
            actions=actions,
            incident=self.incident,
            source_context=self.source_context,
            evidence_text=self.evidence_text,
        )

        result = correlator.correlate()

        correlator.print_result(
            result
        )

        return result

    # =========================================================
    # Safety validation
    # =========================================================

    def validate_confidence(
        self,
        correlation,
    ):
        if correlation is None:
            return (
                False,
                0.0,
                "No correlation result was produced.",
            )

        confidence = float(
            correlation.confidence
        )

        if correlation.candidate is None:
            return (
                False,
                confidence,
                "No actionable UI candidate was found.",
            )

        if confidence < self.minimum_confidence:
            return (
                False,
                confidence,
                (
                    "UI action confidence "
                    f"{confidence:.2f} is below "
                    "the execution threshold "
                    f"{self.minimum_confidence:.2f}."
                ),
            )

        return (
            True,
            confidence,
            "UI action passed confidence gate.",
        )

    # =========================================================
    # Logcat
    # =========================================================

    def clear_logcat(self):

        print()
        print(
            "[REPRO] Clearing old logcat..."
        )

        code, output, error = (
            self.discoverer._adb(
                "logcat",
                "-c",
                timeout=15,
            )
        )

        if code != 0:
            return (
                False,
                error
                or output
                or "Unable to clear logcat.",
            )

        print(
            "✅ Logcat cleared."
        )

        return (
            True,
            "Logcat cleared.",
        )

    # =========================================================
    # UI action execution
    # =========================================================

    def execute_action(
        self,
        candidate,
        confidence,
    ):

        print()
        print(
            "[REPRO] Executing discovered UI action..."
        )

        executor = UIActionExecutor(
            discoverer=self.discoverer,
            minimum_confidence=self.minimum_confidence,
            settle_seconds=0.5,
        )

        result = executor.execute(
            candidate=candidate,
            confidence=confidence,
        )

        return result

    # =========================================================
    # Runtime observation
    # =========================================================

    def collect_runtime_logs(self):

        print()
        print(
            "[REPRO] Monitoring application..."
        )

        print(
            "Observation time:",
            self.observation_seconds,
            "seconds",
        )

        time.sleep(
            self.observation_seconds
        )

        print()
        print(
            "[REPRO] Collecting fresh logcat..."
        )

        code, output, error = (
            self.discoverer._adb(
                "logcat",
                "-d",
                "-v",
                "threadtime",
                timeout=20,
            )
        )

        if code != 0:
            return (
                False,
                "",
                error
                or output
                or "Unable to collect logcat.",
            )

        print(
            "✅ Fresh logcat collected:",
            len(output),
            "characters",
        )

        return (
            True,
            output,
            "Runtime logs collected.",
        )

    # =========================================================
    # Generic failure verification
    # =========================================================

    def verify_failure(
        self,
        logs,
    ):

        package = self.get_package()
        failure_type = self.get_failure_type()

        print()
        print(
            "[REPRO] Checking whether "
            "the original failure returned..."
        )

        verifier = FailureVerifier(
            package=package,
            failure_type=failure_type,
            device_serial=self.device_serial,
            wait_seconds=1,
        )

        failure_reproduced = (
            verifier.detect_failure(
                logs
            )
        )

        process_alive = (
            verifier.is_process_alive()
        )

        return (
            failure_reproduced,
            process_alive,
        )

    # =========================================================
    # Main reproduction flow
    # =========================================================

    def reproduce(self):

        print()
        print("=" * 70)
        print(
            "              GENERIC FAILURE REPRODUCTION"
        )
        print("=" * 70)

        print(
            "Failure Type :",
            self.get_failure_type(),
        )

        print(
            "Package      :",
            self.get_package() or "Unknown",
        )

        print(
            "Device       :",
            self.device_serial
            or "automatic ADB device",
        )

        # -----------------------------------------------------
        # Step 1: UI discovery
        # -----------------------------------------------------

        discovery_ok, actions, discovery_reason = (
            self.discover_actions()
        )

        if not discovery_ok:

            return ReproductionResult(
                success=False,
                action_found=False,
                action_executed=False,
                failure_reproduced=False,
                process_alive=False,
                confidence=0.0,
                reason=discovery_reason,
            )

        if not actions:

            return ReproductionResult(
                success=False,
                action_found=False,
                action_executed=False,
                failure_reproduced=False,
                process_alive=False,
                confidence=0.0,
                reason=(
                    "No actionable UI elements "
                    "were discovered."
                ),
            )

        # -----------------------------------------------------
        # Step 2: UI correlation
        # -----------------------------------------------------

        correlation = self.correlate_action(
            actions
        )

        # -----------------------------------------------------
        # Step 3: Confidence safety gate
        # -----------------------------------------------------

        confidence_ok, confidence, confidence_reason = (
            self.validate_confidence(
                correlation
            )
        )

        print()
        print(
            "Selected confidence:",
            f"{confidence:.2f}",
        )

        if not confidence_ok:

            print(
                "❌ UI action rejected."
            )

            print(
                "Reason:",
                confidence_reason,
            )

            return ReproductionResult(
                success=False,
                action_found=(
                    correlation is not None
                    and correlation.candidate is not None
                ),
                action_executed=False,
                failure_reproduced=False,
                process_alive=False,
                confidence=confidence,
                reason=confidence_reason,
            )

        print(
            "✅ Confidence threshold passed."
        )

        # -----------------------------------------------------
        # Step 4: Clear logcat
        # -----------------------------------------------------

        clear_ok, clear_reason = (
            self.clear_logcat()
        )

        if not clear_ok:

            return ReproductionResult(
                success=False,
                action_found=True,
                action_executed=False,
                failure_reproduced=False,
                process_alive=False,
                confidence=confidence,
                reason=clear_reason,
            )

        # -----------------------------------------------------
        # Step 5: Execute UI action
        # -----------------------------------------------------

        execution = self.execute_action(
            candidate=correlation.candidate,
            confidence=confidence,
        )

        if not execution.success:

            return ReproductionResult(
                success=False,
                action_found=True,
                action_executed=False,
                failure_reproduced=False,
                process_alive=False,
                confidence=confidence,
                reason=execution.reason,
            )

        # -----------------------------------------------------
        # Step 6: Runtime observation
        # -----------------------------------------------------

        logs_ok, logs, logs_reason = (
            self.collect_runtime_logs()
        )

        if not logs_ok:

            return ReproductionResult(
                success=False,
                action_found=True,
                action_executed=True,
                failure_reproduced=False,
                process_alive=False,
                confidence=confidence,
                reason=logs_reason,
            )

        # -----------------------------------------------------
        # Step 7: Failure verification
        # -----------------------------------------------------

        failure_reproduced, process_alive = (
            self.verify_failure(
                logs
            )
        )

        # -----------------------------------------------------
        # Step 8: Final decision
        # -----------------------------------------------------

        print()
        print("=" * 70)
        print(
            "             REPRODUCTION RESULT"
        )
        print("=" * 70)

        print(
            "Action Found       :",
            True,
        )

        print(
            "Action Executed    :",
            True,
        )

        print(
            "Confidence         :",
            f"{confidence:.2f}",
        )

        print(
            "Failure Reproduced :",
            failure_reproduced,
        )

        print(
            "Process Alive      :",
            process_alive,
        )

        if failure_reproduced:

            print()
            print(
                "❌ ORIGINAL FAILURE REPRODUCED"
            )

            print("=" * 70)

            return ReproductionResult(
                success=True,
                action_found=True,
                action_executed=True,
                failure_reproduced=True,
                process_alive=process_alive,
                confidence=confidence,
                reason=(
                    "The discovered UI action was "
                    "executed and the original failure "
                    "was reproduced."
                ),
                logs=logs,
            )

        if not process_alive:

            print()
            print(
                "⚠️ APPLICATION PROCESS NOT ALIVE"
            )

            print(
                "Process state is diagnostic only."
            )

            print(
                "Failure reproduction is determined "
                "from the fresh runtime failure evidence."
            )

            print("=" * 70)

            return ReproductionResult(
                success=True,
                action_found=True,
                action_executed=True,
                failure_reproduced=False,
                process_alive=False,
                confidence=confidence,
                reason=(
                    "UI action executed. The application "
                    "process is not alive, but process state "
                    "is not used as the failure decision."
                ),
                logs=logs,
            )

        print()
        print(
            "✅ ORIGINAL FAILURE NOT REPRODUCED"
        )

        print(
            "✅ APPLICATION PROCESS ALIVE"
        )

        print("=" * 70)

        return ReproductionResult(
            success=True,
            action_found=True,
            action_executed=True,
            failure_reproduced=False,
            process_alive=True,
            confidence=confidence,
            reason=(
                "UI action executed successfully "
                "and the original failure did not recur."
            ),
            logs=logs,
        )


if __name__ == "__main__":

    print(
        "FailureReproducer is a library module."
    )
