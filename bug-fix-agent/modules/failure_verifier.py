import subprocess
import time
from dataclasses import dataclass
from typing import Optional


@dataclass
class VerificationResult:
    success: bool
    failure_type: str
    package: str
    process_alive: bool
    failure_reproduced: bool
    reason: str
    logs: str = ""


class FailureVerifier:
    """
    Generic Android runtime failure verifier.

    The verifier does not know:
      - a specific APK
      - a specific package
      - a specific activity
      - a specific button
      - a specific project

    It uses the Incident information supplied by VAMP.
    """

    def __init__(
        self,
        package: str,
        failure_type: str,
        device_serial: Optional[str] = None,
        wait_seconds: int = 8,
    ):
        self.package = (package or "").strip()
        self.failure_type = (
            failure_type or "UNKNOWN"
        ).strip().upper()

        self.device_serial = (
            device_serial or ""
        ).strip()

        self.wait_seconds = max(
            1,
            int(wait_seconds),
        )

    # ============================================================
    # ADB
    # ============================================================

    def _adb(self, *args, timeout=15):

        command = ["adb"]

        if self.device_serial:
            command.extend(
                [
                    "-s",
                    self.device_serial,
                ]
            )

        command.extend(args)

        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=timeout,
            )

            output = (
                result.stdout or ""
            )

            error = (
                result.stderr or ""
            )

            return (
                result.returncode,
                output,
                error,
            )

        except Exception as exc:

            return (
                -1,
                "",
                str(exc),
            )

    # ============================================================
    # LOGCAT
    # ============================================================

    def clear_logs(self):

        code, output, error = self._adb(
            "logcat",
            "-c",
        )

        if code != 0:
            return False, (
                error
                or output
                or "Unable to clear logcat."
            )

        return True, "Logcat cleared."

    def collect_logs(self):

        code, output, error = self._adb(
            "logcat",
            "-d",
            "-v",
            "threadtime",
            timeout=20,
        )

        if code != 0:
            return False, (
                error
                or output
                or "Unable to collect logcat."
            )

        return True, output

    # ============================================================
    # PROCESS
    # ============================================================

    def get_pid(self):

        if not self.package:
            return None

        code, output, error = self._adb(
            "shell",
            "pidof",
            self.package,
        )

        if code != 0:
            return None

        value = output.strip()

        if not value:
            return None

        return value.split()[0]

    def is_process_alive(self):

        return self.get_pid() is not None

    # ============================================================
    # PACKAGE CORRELATION
    # ============================================================

    def package_present_in_log(
        self,
        logs,
    ):

        if not self.package:
            return False

        return self.package in (
            logs or ""
        )

    # ============================================================
    # JAVA / KOTLIN CRASH
    # ============================================================

    def detect_java_crash(
        self,
        logs,
    ):

        if not logs:
            return False

        if not self.package_present_in_log(
            logs
        ):
            return False

        markers = [
            "FATAL EXCEPTION",
            "AndroidRuntime",
        ]

        return any(
            marker in logs
            for marker in markers
        )

    # ============================================================
    # NATIVE CRASH
    # ============================================================

    def detect_native_crash(
        self,
        logs,
    ):

        if not logs:
            return False

        if not self.package_present_in_log(
            logs
        ):
            return False

        markers = [
            "Fatal signal",
            "SIGSEGV",
            "SIGABRT",
            "SIGBUS",
            "SIGILL",
            "SIGFPE",
            "Abort message",
            "backtrace:",
        ]

        return any(
            marker in logs
            for marker in markers
        )

    # ============================================================
    # ANR
    # ============================================================

    def detect_anr(
        self,
        logs,
    ):

        if not logs:
            return False

        package_marker = (
            "ANR in " + self.package
        )

        if (
            package_marker not in logs
        ):
            return False

        anr_markers = [
            "Input dispatching timed out",
            "executing service",
            "Broadcast of Intent",
            "ContentProvider not responding",
            "Executing service",
        ]

        return any(
            marker in logs
            for marker in anr_markers
        )

    # ============================================================
    # PROCESS DEATH
    # ============================================================

    def detect_process_death(
        self,
        logs,
    ):

        if self.is_process_alive():
            return False

        if not logs:
            return True

        death_markers = [
            "Process",
            "killed",
            "Killing",
            "died",
            "has died",
        ]

        return any(
            marker in logs
            for marker in death_markers
        )

    # ============================================================
    # UNKNOWN / GENERIC FAILURE
    # ============================================================

    def detect_generic_failure(
        self,
        logs,
    ):

        if not logs:
            return False

        if not self.package_present_in_log(
            logs
        ):
            return False

        generic_markers = [
            "Exception",
            "Error",
            "FATAL",
            "Fatal",
            "SecurityException",
            "OutOfMemoryError",
            "RuntimeException",
        ]

        return any(
            marker in logs
            for marker in generic_markers
        )

    # ============================================================
    # FAILURE DISPATCH
    # ============================================================

    def detect_failure(
        self,
        logs,
    ):

        failure_type = (
            self.failure_type
        )

        if failure_type == "ANR":
            return self.detect_anr(
                logs
            )

        if failure_type == "CRASH":
            return self.detect_java_crash(
                logs
            )

        if failure_type == "NATIVE_CRASH":
            return self.detect_native_crash(
                logs
            )

        if failure_type in {
            "PROCESS_DEATH",
            "APP_DEATH",
        }:
            return self.detect_process_death(
                logs
            )

        return self.detect_generic_failure(
            logs
        )

    # ============================================================
    # WAIT FOR APPLICATION
    # ============================================================

    def wait_for_process(
        self,
        timeout=10,
    ):

        deadline = (
            time.time()
            + timeout
        )

        while time.time() < deadline:

            if self.is_process_alive():
                return True

            time.sleep(0.5)

        return False

    # ============================================================
    # MAIN VERIFICATION
    # ============================================================

    def verify(self):

        print()
        print("=" * 70)
        print("              GENERIC FAILURE VERIFICATION")
        print("=" * 70)

        print(
            "Failure Type :",
            self.failure_type,
        )

        print(
            "Package      :",
            self.package,
        )

        if self.device_serial:
            print(
                "Device       :",
                self.device_serial,
            )

        # --------------------------------------------------------
        # Step 1
        # Clear old logs
        # --------------------------------------------------------

        print()
        print(
            "[VERIFY 1] Clearing old logcat..."
        )

        clear_ok, clear_message = (
            self.clear_logs()
        )

        if not clear_ok:

            return VerificationResult(
                success=False,
                failure_type=self.failure_type,
                package=self.package,
                process_alive=False,
                failure_reproduced=False,
                reason=clear_message,
            )

        print(
            "✅",
            clear_message,
        )

        # --------------------------------------------------------
        # Step 2
        # Wait for application
        # --------------------------------------------------------

        print()
        print(
            "[VERIFY 2] Waiting for application process..."
        )

        process_started = (
            self.wait_for_process(
                timeout=10
            )
        )

        if process_started:

            print(
                "✅ Application process is running."
            )

            print(
                "PID:",
                self.get_pid(),
            )

        else:

            print(
                "⚠ Application process is not running."
            )

        # --------------------------------------------------------
        # Step 3
        # Observation window
        # --------------------------------------------------------

        print()
        print(
            "[VERIFY 3] Monitoring runtime..."
        )

        print(
            "Observation time:",
            self.wait_seconds,
            "seconds",
        )

        time.sleep(
            self.wait_seconds
        )

        # --------------------------------------------------------
        # Step 4
        # Collect fresh logs
        # --------------------------------------------------------

        print()
        print(
            "[VERIFY 4] Collecting fresh logcat..."
        )

        log_ok, logs = (
            self.collect_logs()
        )

        if not log_ok:

            return VerificationResult(
                success=False,
                failure_type=self.failure_type,
                package=self.package,
                process_alive=self.is_process_alive(),
                failure_reproduced=False,
                reason=logs,
            )

        print(
            "✅ Fresh logcat collected:",
            len(logs),
            "characters",
        )

        # --------------------------------------------------------
        # Step 5
        # Detect same failure
        # --------------------------------------------------------

        print()
        print(
            "[VERIFY 5] Checking for failure recurrence..."
        )

        failure_reproduced = (
            self.detect_failure(
                logs
            )
        )

        process_alive = (
            self.is_process_alive()
        )

        # --------------------------------------------------------
        # Step 6
        # Result
        # --------------------------------------------------------

        if failure_reproduced:

            print()
            print(
                "❌ FAILURE REPRODUCED"
            )

            print(
                "The same failure class "
                "was detected after the patch."
            )

            return VerificationResult(
                success=False,
                failure_type=self.failure_type,
                package=self.package,
                process_alive=process_alive,
                failure_reproduced=True,
                reason=(
                    "Failure signature "
                    "reappeared after patch."
                ),
                logs=logs,
            )

        # --------------------------------------------------------
        # Process state is diagnostic only
        # --------------------------------------------------------

        if not process_alive:

            print()
            print(
                "⚠️ APPLICATION PROCESS NOT ALIVE"
            )

            print(
                "Process state is diagnostic only."
            )

            print(
                "Verification decision is based on "
                "the failure signature in fresh logcat."
            )

        else:

            print()
            print(
                "✅ APPLICATION PROCESS ALIVE"
            )

        print()
        print(
            "✅ FAILURE NOT REPRODUCED"
        )

        print()
        print(
            "=" * 70
        )
        print(
            "             GENERIC VERIFICATION PASSED"
        )
        print(
            "=" * 70
        )

        return VerificationResult(
            success=True,
            failure_type=self.failure_type,
            package=self.package,
            process_alive=process_alive,
            failure_reproduced=False,
            reason=(
                "Failure did not recur during verification. "
                "Process state was treated as diagnostic only."
            ),
            logs=logs,
        )


if __name__ == "__main__":

    print(
        "FailureVerifier is a library module."
    )
