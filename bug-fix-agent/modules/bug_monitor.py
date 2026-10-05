import subprocess
import threading
import queue
import time
import re
from datetime import datetime

from modules.failure_detector import FailureDetector
from modules.models import Incident
from modules.vamp_integration import VAMPIntegration


class BugMonitor:
    """
    Generic Android failure monitor.

    Architecture:

        Android DTU
             |
             v
        adb logcat
             |
             v
        BugMonitor
             |
             v
      Rolling Evidence Buffer
             |
             v
        FailureDetector
             |
             v
          Incident
             |
             v
       VAMPIntegration
             |
             v
        BugFixAgent

    The monitor does NOT know:
        - application package
        - project path
        - APK name
        - launcher activity
        - source file
        - bug type

    All failure identification is delegated to FailureDetector.

    The implementation is Android-version independent and
    supports modern Android/Cuttlefish log formats.
    """

    def __init__(
        self,
        serial=None,
        context_lines=30,
        on_incident=None,
        collection_timeout=3.0,
        source_roots=None,
        incident_cooldown=2.0
    ):
        """
        Args:
            serial:
                Optional ADB device serial.

            context_lines:
                Number of recent log lines retained as evidence.

            on_incident:
                Optional external incident callback.
                If omitted, incidents are automatically sent to VAMP.

            collection_timeout:
                Additional time used to collect failure evidence.

            source_roots:
                Optional source roots passed to VAMP/BugFixAgent.

            incident_cooldown:
                Minimum time between generated incidents.
        """

        self.serial = serial

        self.context_lines = max(
            int(context_lines),
            10
        )

        self.collection_timeout = max(
            float(collection_timeout),
            0.5
        )

        self.incident_cooldown = max(
            float(incident_cooldown),
            0.0
        )

        self.detector = FailureDetector()

        self.process = None
        self.running = False

        self.log_queue = queue.Queue()

        self.reader_thread = None

        # Rolling logcat evidence.
        self.log_buffer = []

        self.last_incident_time = 0

        # -----------------------------------------------------
        # VAMP integration
        # -----------------------------------------------------

        self.vamp = VAMPIntegration(
            source_roots=source_roots
        )

        self.on_incident = (
            on_incident
            if on_incident is not None
            else self.vamp.handle_incident
        )

    # =========================================================
    # ADB
    # =========================================================

    def adb_prefix(self):
        """
        Build the ADB command prefix.

        No device serial is hard-coded.
        """

        command = [
            "adb"
        ]

        if self.serial:

            command += [
                "-s",
                self.serial
            ]

        return command

    # =========================================================
    # START MONITOR
    # =========================================================

    def start(self):
        """
        Start adb logcat and continuously monitor failures.
        """

        if self.running:

            print(
                "⚠ Monitor is already running."
            )

            return

        print()
        print("=" * 70)
        print("                 VAMP LOG MONITOR")
        print("=" * 70)

        if self.serial:

            print(
                "Device :",
                self.serial
            )

        else:

            print(
                "Device : Automatic ADB device"
            )

        print(
            "Status : STARTING"
        )

        print("=" * 70)

        self.clear_logcat()

        command = self.adb_prefix() + [
            "logcat",
            "-v",
            "threadtime"
        ]

        print()
        print(
            "Starting:"
        )

        print(
            " ".join(command)
        )

        try:

            self.process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1
            )

        except Exception as e:

            print()
            print(
                "❌ Unable to start adb logcat:"
            )

            print(e)

            return

        self.running = True

        self.reader_thread = threading.Thread(
            target=self.read_logcat,
            daemon=True,
            name="VAMP-Logcat-Reader"
        )

        self.reader_thread.start()

        print()
        print(
            "✅ VAMP monitor started."
        )

        print(
            "Waiting for Android failures..."
        )

        print(
            "Press Ctrl+C to stop."
        )

        print()

        self.monitor_loop()

    # =========================================================
    # CLEAR LOGCAT
    # =========================================================

    def clear_logcat(self):
        """
        Clear old Android logcat entries before monitoring.
        """

        try:

            subprocess.run(
                self.adb_prefix() + [
                    "logcat",
                    "-c"
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=10
            )

            print(
                "✅ Old logcat entries cleared."
            )

        except Exception as e:

            print(
                "⚠ Unable to clear logcat:"
            )

            print(e)

    # =========================================================
    # LOGCAT READER
    # =========================================================

    def read_logcat(self):
        """
        Read adb logcat in a dedicated thread.

        The reader thread only reads data and places it into
        the queue. Failure analysis happens in monitor_loop().
        """

        if not self.process:

            return

        try:

            for line in iter(
                self.process.stdout.readline,
                ""
            ):

                if not self.running:

                    break

                line = line.rstrip()

                if not line:

                    continue

                self.log_queue.put(
                    line
                )

        except Exception as e:

            if self.running:

                print(
                    "⚠ Logcat reader error:",
                    e
                )

        finally:

            self.log_queue.put(
                None
            )

    # =========================================================
    # MONITOR LOOP
    # =========================================================

    def monitor_loop(self):
        """
        Consume logcat entries and analyze them.
        """

        try:

            while self.running:

                try:

                    line = self.log_queue.get(
                        timeout=1
                    )

                except queue.Empty:

                    continue

                if line is None:

                    if self.running:

                        print(
                            "⚠ Log monitor stopped."
                        )

                    break

                self.process_line(
                    line
                )

        except KeyboardInterrupt:

            print(
                "\n\n⚠ Monitor interrupted."
            )

        finally:

            self.stop()

    # =========================================================
    # PROCESS LOG LINE
    # =========================================================

    def process_line(self, line):
        """
        Add a log line to the rolling evidence window and
        check the complete window for a failure.

        Multi-line failures are handled using the rolling
        evidence buffer.

        ANR detection is Android-version independent.

        A valid ANR does NOT require a PID. Android versions
        may report:

            ANR in com.example.app
            Reason: Input dispatching timed out

        without placing a PID in the same evidence block.
        """

        if not line:

            return

        self.log_buffer.append(
            line
        )

        self.trim_log_buffer()

        evidence_text = "\n".join(
            self.log_buffer
        )

        failures = self.detector.detect(
            evidence_text
        )

        if not failures:

            return

        current_time = time.time()

        if (
            current_time
            - self.last_incident_time
            < self.incident_cooldown
        ):

            return

        self.last_incident_time = (
            current_time
        )

        failure = failures[0]

        print("✓ Failure detected")

        # -----------------------------------------------------
        # Collect additional evidence.
        # -----------------------------------------------------

        if failure.get("type") == "ANR":

            collection_timeout = 5.0

        else:

            collection_timeout = (
                self.collection_timeout
            )

        failure_lines = list(
            self.log_buffer
        )

        deadline = (
            time.time()
            + collection_timeout
        )

        while time.time() < deadline:

            try:

                next_line = self.log_queue.get(
                    timeout=0.05
                )

            except queue.Empty:

                continue

            if next_line is None:

                break

            failure_lines.append(
                next_line
            )

            self.log_buffer.append(
                next_line
            )

            self.trim_log_buffer()

            block = "\n".join(
                failure_lines
            )

            # -------------------------------------------------
            # ANR completion condition
            # -------------------------------------------------
            #
            # PID is intentionally OPTIONAL.
            #
            # Required:
            #
            #   package
            #   reason
            #
            # This supports Android 17 and other versions.
            # -------------------------------------------------

            if failure.get("type") == "ANR":

                anr_package = (
                    self.extract_package(
                        block
                    )
                )

                anr_reason = (
                    self.extract_reason(
                        block
                    )
                )

                if (
                    anr_package
                    and anr_reason
                ):

                    break

            # -------------------------------------------------
            # Java crash completion condition
            # -------------------------------------------------

            elif failure.get("type") == "CRASH":

                # -------------------------------------------------
                # Java/Kotlin crash completion condition
                #
                # Do not create the Incident until the crash block
                # contains enough information to identify the
                # affected application and failure.
                #
                # Required:
                #
                #   package/process
                #   PID
                #   exception
                #   stack frame
                #
                # This remains completely generic and does not
                # depend on any application name.
                # -------------------------------------------------

                crash_package = (
                    self.extract_package(block)
                )

                crash_process = (
                    self.extract_process(block)
                )

                crash_pid = (
                    self.extract_pid(block)
                )

                crash_exception = (
                    self.extract_exception(block)
                )

                has_stack = (
                    "    at " in block
                    or "\tat " in block
                )

                if (
                    crash_package
                    and crash_process
                    and crash_pid is not None
                    and crash_exception
                    and has_stack
                ):

                    break

            # -------------------------------------------------
            # Native crash completion condition
            # -------------------------------------------------

            elif failure.get("type") == "NATIVE_CRASH":

                has_signal = (
                    re.search(
                        r"Fatal signal\s+\d+",
                        block,
                        re.IGNORECASE
                    )
                    is not None
                )

                has_native_evidence = (
                    re.search(
                        r"\b(?:SIGSEGV|SIGABRT|SIGBUS)\b",
                        block,
                        re.IGNORECASE
                    )
                    is not None
                    or
                    re.search(
                        r"backtrace:",
                        block,
                        re.IGNORECASE
                    )
                    is not None
                )

                if (
                    has_signal
                    and has_native_evidence
                ):

                    break

        # -----------------------------------------------------
        # Final evidence block
        # -----------------------------------------------------

        failure_text = "\n".join(
            failure_lines
        )

        failure["text"] = (
            failure_text
        )

        # -----------------------------------------------------
        # Create Incident
        # -----------------------------------------------------

        incident = self.create_incident(
            failure
        )

        # -----------------------------------------------------
        # Send Incident to VAMP
        # -----------------------------------------------------

        self.handle_incident(
            incident
        )

        # Start a fresh evidence window after an incident.
        self.log_buffer = []

    # =========================================================
    # TRIM LOG BUFFER
    # =========================================================

    def trim_log_buffer(self):
        """
        Keep the rolling evidence buffer bounded.
        """

        max_buffer = max(
            self.context_lines * 3,
            100
        )

        if len(self.log_buffer) > max_buffer:

            self.log_buffer = (
                self.log_buffer[-max_buffer:]
            )

    # =========================================================
    # CREATE INCIDENT
    # =========================================================

    def create_incident(self, failure):
        """
        Convert detector output into the Incident model.

        No application-specific information is inserted here.
        """

        raw_log = failure.get(
            "text",
            ""
        )

        failure_type = failure.get(
            "type",
            "UNKNOWN"
        )

        package = (
            self.extract_package(
                raw_log
            )
            or failure.get(
                "package"
            )
            or ""
        )

        if failure_type == "ANR":

            process = package

        else:

            process = (
                self.extract_process(
                    raw_log
                )
                or package
            )

        pid = self.extract_pid(
            raw_log
        )

        exception = self.extract_exception(
            raw_log
        )

        reason = self.extract_reason(
            raw_log
        )

        thread = self.extract_thread(
            raw_log
        )

        incident = Incident(

            timestamp=datetime.now().isoformat(),

            device_serial=(
                self.serial
                or ""
            ),

            package=package,

            process=process,

            pid=pid,

            bug_type=failure_type,

            exception=exception,

            reason=reason,

            thread=thread,

            stack_trace=raw_log,

            raw_log=raw_log
        )

        return incident

    # =========================================================
    # INCIDENT HANDLER
    # =========================================================

    def handle_incident(self, incident):
        """
        Forward the complete incident to VAMP.

        Incident data is preserved unchanged.
        Terminal output is intentionally kept minimal.
        """

        print("✓ Failure detected")

        if getattr(incident, "bug_type", None):
            print(
                "  Type:",
                incident.bug_type
            )

        if getattr(incident, "package", None):
            print(
                "  Package:",
                incident.package
            )

        if not self.on_incident:
            print("⚠ No VAMP incident handler configured.")
            return

        try:
            self.on_incident(incident)

        except Exception as exc:
            print(
                "✗ VAMP incident handling failed:",
                exc
            )

    def stop(self):
        """
        Stop adb logcat and the monitor.
        """

        if not self.running:

            return

        print(
            "\nStopping VAMP monitor..."
        )

        self.running = False

        if self.process:

            try:

                self.process.terminate()

                self.process.wait(
                    timeout=3
                )

            except subprocess.TimeoutExpired:

                try:

                    self.process.kill()

                except Exception:

                    pass

            except Exception:

                pass

        self.process = None

        print(
            "✅ Monitor stopped."
        )

    # =========================================================
    # PACKAGE EXTRACTION
    # =========================================================

    @staticmethod
    def extract_package(text):
        """
        Extract an Android package name from failure evidence.
        """

        if not text:

            return None

        # -----------------------------------------------------
        # Strong ANR form
        # -----------------------------------------------------

        match = re.search(
            r"(?:ActivityManager:\s*)?"
            r"ANR\s+in\s+"
            r"([A-Za-z0-9._$]+)"
            r"\s*(?:\(|$)",
            text,
            re.IGNORECASE
        )

        if match:

            return match.group(1)

        # -----------------------------------------------------
        # Java crash
        # -----------------------------------------------------

        match = re.search(
            r"(?:^|\n)\s*"
            r"Process:\s*"
            r"([A-Za-z0-9._$]+)",
            text,
            re.IGNORECASE
        )

        if match:

            return match.group(1)

        # -----------------------------------------------------
        # Native crash
        # -----------------------------------------------------

        match = re.search(
            r"(?:Cmdline|Cmd line):\s*"
            r"([A-Za-z0-9._$]+)",
            text,
            re.IGNORECASE
        )

        if match:

            return match.group(1)

        return None

    # =========================================================
    # PROCESS EXTRACTION
    # =========================================================

    @staticmethod
    def extract_process(text):
        """
        Extract affected process name.
        """

        if not text:

            return ""

        # -----------------------------------------------------
        # ANR
        # -----------------------------------------------------

        match = re.search(
            r"(?:ActivityManager:\s*)?"
            r"ANR\s+in\s+"
            r"([A-Za-z0-9._$]+)",
            text,
            re.IGNORECASE
        )

        if match:

            return match.group(1)

        # -----------------------------------------------------
        # Java crash
        # -----------------------------------------------------

        match = re.search(
            r"(?:^|\n)\s*"
            r"Process:\s*"
            r"([A-Za-z0-9._$]+)"
            r"(?:\s*,|\s*$)",
            text,
            re.IGNORECASE
        )

        if match:

            return match.group(1)

        # -----------------------------------------------------
        # Native crash
        # -----------------------------------------------------

        match = re.search(
            r"(?:Cmdline|Cmd line):\s*"
            r"([A-Za-z0-9._$]+)",
            text,
            re.IGNORECASE
        )

        if match:

            return match.group(1)

        return ""

    # =========================================================
    # PID EXTRACTION
    # =========================================================

    @staticmethod
    def extract_pid(text):
        """
        Extract PID from failure evidence.

        PID is optional for ANR detection.
        """

        if not text:

            return None

        # -----------------------------------------------------
        # Standard PID
        # -----------------------------------------------------

        match = re.search(
            r"(?:ActivityManager:\s*)?"
            r"PID:\s*(\d+)",
            text,
            re.IGNORECASE
        )

        if match:

            return int(
                match.group(1)
            )

        # -----------------------------------------------------
        # Process + PID
        # -----------------------------------------------------

        match = re.search(
            r"Process:\s*"
            r"[A-Za-z0-9._$]+\s*,\s*"
            r"PID:\s*(\d+)",
            text,
            re.IGNORECASE
        )

        if match:

            return int(
                match.group(1)
            )

        # -----------------------------------------------------
        # Generic pid= / pid:
        # -----------------------------------------------------

        match = re.search(
            r"\bpid[=:]\s*(\d+)",
            text,
            re.IGNORECASE
        )

        if match:

            return int(
                match.group(1)
            )

        return None

    # =========================================================
    # EXCEPTION EXTRACTION
    # =========================================================

    @staticmethod
    def extract_exception(text):
        """
        Extract Java/Kotlin exception or error information.
        """

        if not text:

            return ""

        matches = re.findall(
            r"\b("
            r"(?:[\w$]+\.)*"
            r"[\w$]+"
            r"(?:Exception|Error)"
            r")"
            r"(?::\s*([^\n]+))?",
            text,
            re.IGNORECASE
        )

        if not matches:

            return ""

        for exception, message in matches:

            if exception.lower() in {
                "error",
                "exception"
            }:

                continue

            result = (
                exception.strip()
            )

            if message:

                result += (
                    ": "
                    + message.strip()
                )

            return result

        return ""

    # =========================================================
    # REASON EXTRACTION
    # =========================================================

    @staticmethod
    def extract_reason(text):
        """
        Extract the failure reason.

        Supports modern Android ANR formats such as:

            Reason: Input dispatching timed out

        and:

            Input dispatching timed out

        and:

            Window ... is unresponsive
        """

        if not text:

            return ""

        # -----------------------------------------------------
        # Explicit Reason field
        # -----------------------------------------------------

        match = re.search(
            r"(?:ActivityManager:\s*)?"
            r"Reason:\s*(.+)",
            text,
            re.IGNORECASE
        )

        if match:

            return match.group(1).strip()

        # -----------------------------------------------------
        # Input dispatch timeout
        # -----------------------------------------------------

        match = re.search(
            r"Input\s+dispatch(?:ing)?\s+timed\s+out.*",
            text,
            re.IGNORECASE
        )

        if match:

            return match.group(0).strip()

        # -----------------------------------------------------
        # Window unresponsive
        # -----------------------------------------------------

        match = re.search(
            r"Window\s+.*?\s+is\s+unresponsive.*",
            text,
            re.IGNORECASE
        )

        if match:

            return match.group(0).strip()

        # -----------------------------------------------------
        # Native signal
        # -----------------------------------------------------

        match = re.search(
            r"Fatal signal\s+\d+.*",
            text,
            re.IGNORECASE
        )

        if match:

            return match.group(0).strip()

        # -----------------------------------------------------
        # Abort message
        # -----------------------------------------------------

        match = re.search(
            r"Abort message:.*",
            text,
            re.IGNORECASE
        )

        if match:

            return match.group(0).strip()

        return ""

    # =========================================================
    # THREAD EXTRACTION
    # =========================================================

    @staticmethod
    def extract_thread(text):
        """
        Extract Java crash thread name.
        """

        if not text:

            return ""

        match = re.search(
            r"FATAL EXCEPTION:\s*(.+)",
            text,
            re.IGNORECASE
        )

        if match:

            return match.group(1).strip()

        return ""


# ============================================================
# STANDALONE REAL DEVICE TEST
# ============================================================

if __name__ == "__main__":

    print()
    print("=" * 70)
    print("             VAMP REAL DEVICE MONITOR")
    print("=" * 70)

    print()
    print(
        "Starting monitor using the default ADB device."
    )

    print(
        "For a specific device use:"
    )

    print(
        "    BugMonitor(serial='<device-serial>')"
    )

    monitor = BugMonitor()

    try:

        monitor.start()

    except KeyboardInterrupt:

        print()
        print(
            "Stopping VAMP monitor..."
        )

        monitor.stop()

        print(
            "✅ Monitor stopped."
        )

    except Exception as e:

        print()
        print(
            "❌ Monitor error:"
        )

        print(e)

        monitor.stop()
