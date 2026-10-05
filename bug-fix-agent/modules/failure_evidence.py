import re
import subprocess
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class FailureEvidence:
    """
    Generic evidence collected from an Android device.

    This object represents evidence, not a diagnosis.

    It intentionally does not assume:
        - a specific APK
        - a specific package
        - a specific activity
        - a specific source project
        - a specific bug
    """

    timestamp: str = ""
    device_serial: str = ""

    failure_type: str = ""
    package: str = ""
    process: str = ""
    pid: int | None = None

    logcat: str = ""
    activity_dump: str = ""
    package_dump: str = ""
    memory_dump: str = ""
    process_dump: str = ""
    last_anr: str = ""

    bugreport_path: str = ""

    metadata: dict = field(default_factory=dict)

    def combined_text(self):
        """
        Combine all textual evidence into one searchable string.
        """

        sections = []

        evidence_sections = [
            ("LOGCAT", self.logcat),
            ("ACTIVITY DUMP", self.activity_dump),
            ("PACKAGE DUMP", self.package_dump),
            ("MEMORY DUMP", self.memory_dump),
            ("PROCESS DUMP", self.process_dump),
            ("LAST ANR", self.last_anr),
        ]

        for name, text in evidence_sections:

            if not text:
                continue

            sections.append(
                f"\n===== {name} =====\n{text}"
            )

        return "\n".join(sections)


class FailureEvidenceCollector:
    """
    Generic Android failure evidence collector.

    Flow:

        Incident
           |
           v
        Collector
           |
           +--> logcat
           +--> package
           +--> process
           +--> activity
           +--> ANR evidence
           +--> memory evidence
           |
           v
        Structured metadata
    """

    def __init__(
        self,
        serial=None,
        log_lines=500,
        timeout=10,
    ):
        self.serial = serial
        self.log_lines = log_lines
        self.timeout = timeout

    # ==============================================================
    # ADB
    # ==============================================================

    def adb(self, *args, timeout=None):
        """
        Execute an ADB command and return stdout.
        """

        command = ["adb"]

        if self.serial:
            command.extend(
                ["-s", self.serial]
            )

        command.extend(args)

        try:

            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=timeout or self.timeout,
            )

        except subprocess.TimeoutExpired:

            raise RuntimeError(
                "ADB command timed out: "
                + " ".join(command)
            )

        if result.returncode != 0:

            stderr = (
                result.stderr.strip()
                if result.stderr
                else ""
            )

            raise RuntimeError(
                f"ADB command failed ({result.returncode}): "
                f"{' '.join(command)}"
                + (
                    f"\n{stderr}"
                    if stderr
                    else ""
                )
            )

        return result.stdout

    # ==============================================================
    # MAIN COLLECTION
    # ==============================================================

    def collect(self, incident):
        """
        Collect complete failure evidence.

        All evidence is retained internally. Terminal output is
        intentionally suppressed so the VAMP console remains concise.
        """

        evidence = FailureEvidence(
            failure_type=getattr(
                incident,
                "bug_type",
                "",
            )
            or "",
            package=(
                getattr(
                    incident,
                    "package",
                    "",
                )
                or ""
            ),
            process=(
                getattr(
                    incident,
                    "process",
                    "",
                )
                or ""
            ),
            pid=getattr(
                incident,
                "pid",
                None,
            ),
        )

        failure_type = (
            evidence.failure_type
            .strip()
            .upper()
        )

        # ----------------------------------------------------------
        # 1. LOGCAT
        # ----------------------------------------------------------

        try:

            evidence.logcat = self.collect_logcat(
                incident
            )

        except Exception:
            pass

        # ----------------------------------------------------------
        # 2. PACKAGE
        # ----------------------------------------------------------

        if evidence.package:

            try:

                evidence.package_dump = (
                    self.collect_package_info(
                        evidence.package
                    )
                )

            except Exception:
                pass

        # ----------------------------------------------------------
        # 3. PROCESS
        # ----------------------------------------------------------

        if evidence.package:

            try:

                evidence.process_dump = (
                    self.collect_process_info(
                        evidence.package,
                        evidence.pid,
                    )
                )

            except Exception:
                pass

        # ----------------------------------------------------------
        # 4. ACTIVITY
        # ----------------------------------------------------------

        if evidence.package:

            try:

                evidence.activity_dump = (
                    self.collect_activity_info(
                        evidence.package
                    )
                )

            except Exception:
                pass

        # ----------------------------------------------------------
        # 5. FAILURE-SPECIFIC COLLECTION
        # ----------------------------------------------------------

        if failure_type == "ANR":

            try:

                evidence.last_anr = (
                    self.collect_last_anr()
                )

            except Exception:
                pass

        elif failure_type in (
            "CRASH",
            "JAVA_CRASH",
            "KOTLIN_CRASH",
            "NATIVE_CRASH",
            "OOM",
        ):

            try:

                if evidence.package:

                    evidence.memory_dump = (
                        self.collect_memory_info(
                            evidence.package
                        )
                    )

            except Exception:
                pass

        else:

            try:

                if evidence.package:

                    evidence.memory_dump = (
                        self.collect_memory_info(
                            evidence.package
                        )
                    )

            except Exception:
                pass

        # ----------------------------------------------------------
        # 6. STRUCTURED ANALYSIS
        # ----------------------------------------------------------

        evidence.metadata = self.extract_metadata(
            incident,
            evidence,
        )

        return evidence

    # ==============================================================
    # LOGCAT
    # ==============================================================

    def collect_logcat(self, incident):
        """
        Collect recent logcat and targeted failure context.

        The full recent logcat is retained as evidence, but a
        failure-focused section is also generated so downstream
        analysis can avoid unrelated system messages.
        """

        package = (
            getattr(
                incident,
                "package",
                "",
            )
            or ""
        )

        pid = getattr(
            incident,
            "pid",
            None,
        )

        raw = (
            getattr(
                incident,
                "raw_log",
                "",
            )
            or ""
        )

        try:

            output = self.adb(
                "logcat",
                "-d",
                "-v",
                "threadtime",
                "-t",
                str(self.log_lines),
            )

        except Exception:

            output = ""

        sections = []

        if raw:

            sections.append(
                "INCIDENT LOG:\n"
                + raw
            )

        if output:

            sections.append(
                "RECENT LOGCAT:\n"
                + output
            )

        # ----------------------------------------------------------
        # Targeted package/PID context
        # ----------------------------------------------------------

        if output and (package or pid):

            lines = output.splitlines()

            matching = []

            for index, line in enumerate(lines):

                package_match = (
                    bool(package)
                    and package in line
                )

                pid_match = (
                    pid is not None
                    and re.search(
                        rf"\b{re.escape(str(pid))}\b",
                        line,
                    )
                    is not None
                )

                if not (
                    package_match
                    or pid_match
                ):
                    continue

                start = max(
                    0,
                    index - 25,
                )

                end = min(
                    len(lines),
                    index + 26,
                )

                matching.extend(
                    lines[start:end]
                )

            if matching:

                unique = self.unique_lines(
                    matching
                )

                sections.append(
                    "TARGETED CONTEXT:\n"
                    + "\n".join(unique)
                )

        # ----------------------------------------------------------
        # Failure-focused context
        # ----------------------------------------------------------

        failure_lines = self.extract_failure_window(
            output,
            package=package,
            pid=pid,
        )

        if failure_lines:

            sections.append(
                "FAILURE FOCUSED CONTEXT:\n"
                + "\n".join(failure_lines)
            )

        return "\n\n".join(sections)

    # ==============================================================
    # FAILURE WINDOW
    # ==============================================================

    def extract_failure_window(
        self,
        output,
        package="",
        pid=None,
        radius=30,
    ):
        """
        Extract logcat lines around high-confidence failure
        markers.

        This is deliberately conservative.

        It does NOT classify every E/ line as a failure.
        """

        if not output:
            return []

        lines = output.splitlines()

        failure_patterns = [
            r"FATAL EXCEPTION",
            r"AndroidRuntime.*FATAL",
            r"Fatal signal\s+\d+",
            r"SIGSEGV",
            r"SIGABRT",
            r"SIGBUS",
            r"Abort message:",
            r"Input dispatching timed out",
            r"Application Not Responding",
            r"ANR in ",
            r"OutOfMemoryError",
            r"Failed to allocate",
            r"Unable to start activity",
            r"Unable to start service",
            r"SecurityException",
            r"Permission Denial",
            r"ActivityNotFoundException",
        ]

        indexes = []

        for index, line in enumerate(lines):

            for pattern in failure_patterns:

                if re.search(
                    pattern,
                    line,
                    re.IGNORECASE,
                ):

                    indexes.append(index)
                    break

        # If there is no high-confidence marker, fall back
        # to package/PID context rather than unrelated errors.

        if not indexes:

            matching = []

            for index, line in enumerate(lines):

                package_match = (
                    bool(package)
                    and package in line
                )

                pid_match = (
                    pid is not None
                    and re.search(
                        rf"\b{re.escape(str(pid))}\b",
                        line,
                    )
                    is not None
                )

                if package_match or pid_match:

                    start = max(
                        0,
                        index - radius,
                    )

                    end = min(
                        len(lines),
                        index + radius + 1,
                    )

                    matching.extend(
                        lines[start:end]
                    )

            return self.unique_lines(
                matching
            )

        selected = []

        for index in indexes:

            start = max(
                0,
                index - radius,
            )

            end = min(
                len(lines),
                index + radius + 1,
            )

            selected.extend(
                lines[start:end]
            )

        return self.unique_lines(
            selected
        )

    # ==============================================================
    # PACKAGE
    # ==============================================================

    def collect_package_info(self, package):

        if not package:
            return ""

        return self.adb(
            "shell",
            "dumpsys",
            "package",
            package,
        )

    # ==============================================================
    # ACTIVITY
    # ==============================================================

    def collect_activity_info(self, package):

        output = self.adb(
            "shell",
            "dumpsys",
            "activity",
        )

        if not package:
            return output

        lines = output.splitlines()

        matching = []

        for index, line in enumerate(lines):

            if package not in line:
                continue

            start = max(
                0,
                index - 20,
            )

            end = min(
                len(lines),
                index + 60,
            )

            matching.extend(
                lines[start:end]
            )

        if not matching:

            return output

        return "\n".join(
            self.unique_lines(
                matching
            )
        )

    # ==============================================================
    # PROCESS
    # ==============================================================

    def collect_process_info(
        self,
        package,
        pid=None,
    ):

        sections = []

        # ----------------------------------------------------------
        # Process list
        # ----------------------------------------------------------

        try:

            process_list = self.adb(
                "shell",
                "ps",
                "-A",
            )

            if package in process_list:

                sections.append(
                    "PROCESS LIST:\n"
                    + process_list
                )

            elif pid is not None:

                lines = process_list.splitlines()

                matching = []

                for line in lines:

                    if re.search(
                        rf"\b{re.escape(str(pid))}\b",
                        line,
                    ):

                        matching.append(line)

                if matching:

                    sections.append(
                        "PROCESS LIST:\n"
                        + "\n".join(matching)
                    )

        except Exception:
            pass

        # ----------------------------------------------------------
        # ActivityManager process information
        # ----------------------------------------------------------

        try:

            activity_processes = self.adb(
                "shell",
                "dumpsys",
                "activity",
                "processes",
            )

            if package in activity_processes:

                lines = (
                    activity_processes
                    .splitlines()
                )

                matching = []

                for index, line in enumerate(lines):

                    if package not in line:
                        continue

                    start = max(
                        0,
                        index - 10,
                    )

                    end = min(
                        len(lines),
                        index + 35,
                    )

                    matching.extend(
                        lines[start:end]
                    )

                if matching:

                    sections.append(
                        "ACTIVITY PROCESS:\n"
                        + "\n".join(
                            self.unique_lines(
                                matching
                            )
                        )
                    )

        except Exception:
            pass

        return "\n\n".join(sections)

    # ==============================================================
    # MEMORY
    # ==============================================================

    def collect_memory_info(self, package):

        if not package:
            return ""

        return self.adb(
            "shell",
            "dumpsys",
            "meminfo",
            package,
        )

    # ==============================================================
    # LAST ANR
    # ==============================================================

    def collect_last_anr(self):

        return self.adb(
            "shell",
            "dumpsys",
            "activity",
            "lastanr",
        )

    # ==============================================================
    # METADATA EXTRACTION
    # ==============================================================

    def extract_metadata(
        self,
        incident,
        evidence,
    ):
        """
        Extract machine-readable information from the evidence.

        IMPORTANT:

        The extraction is failure-aware.

        For example, an ANR does not treat unrelated audio or
        rendering messages as ANR indicators merely because they
        exist somewhere in the device logcat.
        """

        metadata = {}

        raw = (
            getattr(
                incident,
                "raw_log",
                "",
            )
            or ""
        )

        reason = (
            getattr(
                incident,
                "reason",
                "",
            )
            or ""
        )

        exception = (
            getattr(
                incident,
                "exception",
                "",
            )
            or ""
        )

        process = (
            getattr(
                incident,
                "process",
                "",
            )
            or ""
        )

        # ----------------------------------------------------------
        # Basic fields
        # ----------------------------------------------------------

        metadata["failure_type"] = (
            evidence.failure_type
        )

        metadata["package"] = (
            evidence.package
        )

        metadata["process"] = (
            evidence.process
            or process
        )

        metadata["pid"] = (
            evidence.pid
        )

        metadata["reason"] = reason
        metadata["exception"] = exception

        # ----------------------------------------------------------
        # Build separate evidence scopes
        # ----------------------------------------------------------

        combined = "\n".join(
            [
                raw,
                reason,
                exception,
                process,
                evidence.logcat,
                evidence.activity_dump,
                evidence.package_dump,
                evidence.process_dump,
                evidence.memory_dump,
                evidence.last_anr,
            ]
        )

        failure_context = "\n".join(
            [
                raw,
                reason,
                exception,
                evidence.logcat,
            ]
        )

        if evidence.last_anr:

            failure_context += (
                "\n"
                + evidence.last_anr
            )

        # ----------------------------------------------------------
        # Package extraction
        # ----------------------------------------------------------

        if not metadata["package"]:

            package_patterns = [
                r"Process:\s*([A-Za-z0-9._]+)",
                r"ANR in\s+([A-Za-z0-9._]+)",
                r"Cmdline:\s*([A-Za-z0-9._]+)",
                r"Cmd line:\s*([A-Za-z0-9._]+)",
            ]

            for pattern in package_patterns:

                match = re.search(
                    pattern,
                    combined,
                    re.IGNORECASE,
                )

                if match:

                    metadata["package"] = (
                        match.group(1)
                    )

                    break

        # ----------------------------------------------------------
        # PID extraction
        # ----------------------------------------------------------

        if metadata["pid"] is None:

            pid_patterns = [
                r"\bPID:\s*(\d+)",
                r"\bpid[=:]\s*(\d+)",
                r"\bProcessRecord\{[^}]*\s+(\d+):",
            ]

            for pattern in pid_patterns:

                match = re.search(
                    pattern,
                    combined,
                    re.IGNORECASE,
                )

                if match:

                    try:

                        metadata["pid"] = (
                            int(match.group(1))
                        )

                    except ValueError:
                        pass

                    break

        # ----------------------------------------------------------
        # ANR reason
        # ----------------------------------------------------------

        if evidence.failure_type.upper() == "ANR":

            anr_reason = self.extract_anr_reason(
                incident,
                evidence,
            )

            if anr_reason:

                metadata["anr_reason"] = (
                    anr_reason
                )

        # ----------------------------------------------------------
        # Activity/component
        # ----------------------------------------------------------

        activity_patterns = [
            r"ActivityRecord\{[^}]*\s+"
            r"(?:u\d+\s+)?"
            r"([A-Za-z0-9._$]+/[A-Za-z0-9._$]+)",

            r"Parent:\s*"
            r"([A-Za-z0-9._$]+/[A-Za-z0-9._$]+)",

            r"(?:Activity|cmp)"
            r"[=: ]+"
            r"([A-Za-z0-9._$]+/[A-Za-z0-9._$]+)",
        ]

        for pattern in activity_patterns:

            match = re.search(
                pattern,
                combined,
                re.IGNORECASE,
            )

            if match:

                metadata["activity"] = (
                    match.group(1)
                )

                break

        # ----------------------------------------------------------
        # PACKAGE FALLBACK FROM ACTIVITY/COMPONENT
        # ----------------------------------------------------------
        #
        # Native crashes can sometimes omit the application package
        # even though ActivityManager reports the failing component:
        #
        #     com.example.app/.MainActivity
        #
        # The package is always the component portion before "/".
        #
        # This is intentionally generic. No application/package name
        # is hard-coded here.
        # ----------------------------------------------------------

        if not metadata["package"] and metadata["activity"]:

            activity_value = str(
                metadata["activity"]
            ).strip()

            if "/" in activity_value:

                activity_package = (
                    activity_value.split(
                        "/",
                        1,
                    )[0].strip()
                )

                if activity_package:

                    metadata["package"] = (
                        activity_package
                    )

        # ----------------------------------------------------------
        # Java/Kotlin exception
        # ----------------------------------------------------------

        exception_patterns = [
            r"\b(java\.[A-Za-z0-9_.$]+"
            r"(?:Exception|Error))\b",

            r"\b(kotlin\.[A-Za-z0-9_.$]+"
            r"(?:Exception|Error))\b",

            r"\b(android\.[A-Za-z0-9_.$]+"
            r"(?:Exception|Error))\b",

            r"\b([A-Za-z0-9_.$]+"
            r"(?:NullPointerException|"
            r"IndexOutOfBoundsException|"
            r"IllegalStateException|"
            r"SecurityException|"
            r"RuntimeException))\b",
        ]

        for pattern in exception_patterns:

            match = re.search(
                pattern,
                failure_context,
                re.IGNORECASE,
            )

            if match:

                metadata["detected_exception"] = (
                    match.group(1)
                )

                break

        # ----------------------------------------------------------
        # Exception message
        # ----------------------------------------------------------

        if (
            "detected_exception"
            in metadata
        ):

            exception_name = re.escape(
                metadata["detected_exception"]
            )

            message_match = re.search(
                exception_name
                + r"(?::\s*([^\r\n]+))?",
                failure_context,
                re.IGNORECASE,
            )

            if (
                message_match
                and message_match.group(1)
            ):

                metadata["exception_message"] = (
                    message_match.group(1).strip()
                )

        # ----------------------------------------------------------
        # Native crash signal
        #
        # Native signal evidence is valid only for a native crash.
        # Java/Kotlin crash logs may contain unrelated system signals
        # in the collected evidence window. Do not attach those
        # signals to the Java/Kotlin failure metadata.
        # ----------------------------------------------------------

        if evidence.failure_type.upper() == "NATIVE_CRASH":

            signal_patterns = [
                r"Fatal signal\s+(\d+)"
                r"(?:\s+\(([^)]+)\))?",

                r"signal\s+(\d+)"
                r"(?:\s+\(([^)]+)\))?",
            ]

            for pattern in signal_patterns:

                match = re.search(
                    pattern,
                    failure_context,
                    re.IGNORECASE,
                )

                if match:

                    metadata["signal"] = (
                        int(match.group(1))
                    )

                    if match.group(2):

                        metadata["signal_name"] = (
                            match.group(2)
                        )

                    break

        # ----------------------------------------------------------
        # Native abort message
        # ----------------------------------------------------------

        abort_match = re.search(
            r"Abort message:\s*"
            r"'([^']*)'",
            failure_context,
            re.IGNORECASE,
        )

        if abort_match:

            metadata["abort_message"] = (
                abort_match.group(1)
            )

        # ----------------------------------------------------------
        # Java/Kotlin source frames
        # ----------------------------------------------------------

        source_frames = re.findall(
            r"\bat\s+"
            r"([A-Za-z0-9_.$]+)"
            r"\.([A-Za-z0-9_$<>]+)"
            r"\("
            r"([A-Za-z0-9_.$-]+"
            r"\.(?:java|kt|kts))"
            r":(\d+)"
            r"\)",
            failure_context,
        )

        if source_frames:

            metadata["source_frames"] = []

            seen_frames = set()

            for item in source_frames:

                frame = {
                    "class": item[0],
                    "method": item[1],
                    "file": item[2],
                    "line": int(item[3]),
                }

                key = (
                    frame["class"],
                    frame["method"],
                    frame["file"],
                    frame["line"],
                )

                if key in seen_frames:
                    continue

                seen_frames.add(key)

                metadata["source_frames"].append(
                    frame
                )

        # ----------------------------------------------------------
        # Thread information
        # ----------------------------------------------------------

        thread_patterns = [
            r"\"([^\"]+)\"\s+prio=",
            r"\"([^\"]+)\"\s+tid=",
            r"thread\s*[:=]\s*([A-Za-z0-9_.$-]+)",
        ]

        threads = []

        for pattern in thread_patterns:

            matches = re.findall(
                pattern,
                failure_context,
                re.IGNORECASE,
            )

            for item in matches:

                item = item.strip()

                if (
                    item
                    and item not in threads
                ):

                    threads.append(item)

        if threads:

            metadata["threads"] = threads[:20]

        # ----------------------------------------------------------
        # Main-thread evidence
        # ----------------------------------------------------------

        main_thread_patterns = [
            r"\bmain\b",
            r"main thread",
            r"Looper",
            r"Choreographer",
        ]

        main_thread_detected = False

        for pattern in main_thread_patterns:

            if re.search(
                pattern,
                failure_context,
                re.IGNORECASE,
            ):

                main_thread_detected = True
                break

        metadata["main_thread_evidence"] = (
            main_thread_detected
        )

        # ----------------------------------------------------------
        # Failure-specific indicators
        # ----------------------------------------------------------

        metadata["indicators"] = (
            self.extract_indicators(
                evidence,
                incident,
            )
        )

        # ----------------------------------------------------------
        # Confidence
        # ----------------------------------------------------------

        confidence = self.calculate_confidence(
            evidence,
            metadata,
        )

        metadata["confidence"] = confidence

        return metadata

    # ==============================================================
    # ANR REASON
    # ==============================================================

    @staticmethod
    def extract_anr_reason(
        incident,
        evidence,
    ):
        """
        Extract the actual ANR reason.

        Priority:

            1. Incident reason
            2. Explicit high-confidence ANR patterns
            3. Last ANR reason
            4. Other known ANR reason formats

        This prevents unrelated "Reason:" fields in dumps from
        becoming the ANR reason.
        """

        incident_reason = (
            getattr(
                incident,
                "reason",
                "",
            )
            or ""
        ).strip()

        # ----------------------------------------------------------
        # 1. Incident reason
        # ----------------------------------------------------------

        if incident_reason:

            return incident_reason

        # ----------------------------------------------------------
        # 2. Explicit high-confidence patterns
        # ----------------------------------------------------------

        sources = [
            getattr(
                incident,
                "raw_log",
                "",
            )
            or "",

            evidence.logcat or "",

            evidence.last_anr or "",
        ]

        priority_patterns = [
            r"Input dispatching timed out"
            r"(?:[^\r\n]*)",

            r"Executing service"
            r"(?:[^\r\n]*)",

            r"Broadcast of Intent"
            r"(?:[^\r\n]*)",

            r"ContentProvider not responding"
            r"(?:[^\r\n]*)",
        ]

        for source in sources:

            if not source:
                continue

            for pattern in priority_patterns:

                match = re.search(
                    pattern,
                    source,
                    re.IGNORECASE,
                )

                if match:

                    return match.group(
                        0
                    ).strip()

        # ----------------------------------------------------------
        # 3. Reason field from LAST ANR only
        # ----------------------------------------------------------

        if evidence.last_anr:

            reason_match = re.search(
                r"^[ \t]*Reason[ \t]*:[ \t]*"
                r"([^\r\n]+)$",
                evidence.last_anr,
                re.IGNORECASE | re.MULTILINE,
            )

            if reason_match:

                value = (
                    reason_match.group(1)
                    .strip()
                )

                if value:

                    return value

        return ""

    # ==============================================================
    # INDICATORS
    # ==============================================================

    def extract_indicators(
        self,
        evidence,
        incident,
    ):
        """
        Extract failure indicators using failure-aware rules.

        The method intentionally avoids treating unrelated
        rendering/audio/network logs as indicators for every
        failure.
        """

        failure_type = (
            evidence.failure_type
            .strip()
            .upper()
        )

        raw = (
            getattr(
                incident,
                "raw_log",
                "",
            )
            or ""
        )

        reason = (
            getattr(
                incident,
                "reason",
                "",
            )
            or ""
        )

        exception = (
            getattr(
                incident,
                "exception",
                "",
            )
            or ""
        )

        focused = "\n".join(
            [
                raw,
                reason,
                exception,
                evidence.logcat,
                evidence.last_anr,
            ]
        )

        indicators = []

        def add_if_present(
            name,
            patterns,
        ):

            if isinstance(
                patterns,
                str,
            ):

                patterns = [
                    patterns
                ]

            for pattern in patterns:

                if re.search(
                    pattern,
                    focused,
                    re.IGNORECASE,
                ):

                    indicators.append(
                        name
                    )

                    return

        # ----------------------------------------------------------
        # ANR
        # ----------------------------------------------------------

        if failure_type == "ANR":

            add_if_present(
                "input_dispatch_timeout",
                r"Input dispatching timed out",
            )

            add_if_present(
                "app_not_responding",
                r"Application Not Responding|ANR in ",
            )

            add_if_present(
                "executing_service",
                r"Executing service",
            )

            add_if_present(
                "broadcast_timeout",
                r"Broadcast of Intent",
            )

            add_if_present(
                "content_provider_timeout",
                r"ContentProvider not responding",
            )

        # ----------------------------------------------------------
        # Java/Kotlin crash
        # ----------------------------------------------------------

        elif failure_type in (
            "CRASH",
            "JAVA_CRASH",
            "KOTLIN_CRASH",
        ):

            add_if_present(
                "fatal_exception",
                r"FATAL EXCEPTION",
            )

            add_if_present(
                "android_runtime",
                r"AndroidRuntime",
            )

            add_if_present(
                "null_pointer",
                r"NullPointerException",
            )

            add_if_present(
                "illegal_state",
                r"IllegalStateException",
            )

            add_if_present(
                "index_error",
                r"IndexOutOfBoundsException"
                r"|ArrayIndexOutOfBoundsException",
            )

            add_if_present(
                "security_exception",
                r"SecurityException",
            )

            add_if_present(
                "permission_denied",
                r"Permission Denial"
                r"|permission denied",
            )

            add_if_present(
                "activity_failure",
                r"Unable to start activity"
                r"|ActivityNotFoundException",
            )

            add_if_present(
                "service_failure",
                r"Unable to start service"
                r"|ServiceConnection",
            )

            add_if_present(
                "network_failure",
                r"UnknownHostException"
                r"|ConnectException"
                r"|SocketException",
            )

        # ----------------------------------------------------------
        # Native crash
        # ----------------------------------------------------------

        elif failure_type == "NATIVE_CRASH":

            add_if_present(
                "native_signal",
                r"Fatal signal\s+\d+",
            )

            add_if_present(
                "segmentation_fault",
                r"SIGSEGV",
            )

            add_if_present(
                "abort",
                r"SIGABRT|Abort message",
            )

            add_if_present(
                "bus_error",
                r"SIGBUS",
            )

            add_if_present(
                "native_backtrace",
                r"backtrace:",
            )

        # ----------------------------------------------------------
        # OOM
        # ----------------------------------------------------------

        elif failure_type == "OOM":

            add_if_present(
                "out_of_memory",
                r"OutOfMemoryError"
                r"|Failed to allocate",
            )

        # ----------------------------------------------------------
        # Generic / unknown
        # ----------------------------------------------------------

        else:

            # Only include high-confidence failure indicators.
            # Do not include broad OpenGL/audio/network messages.

            add_if_present(
                "fatal_exception",
                r"FATAL EXCEPTION",
            )

            add_if_present(
                "native_signal",
                r"Fatal signal\s+\d+",
            )

            add_if_present(
                "out_of_memory",
                r"OutOfMemoryError"
                r"|Failed to allocate",
            )

            add_if_present(
                "security_exception",
                r"SecurityException",
            )

            add_if_present(
                "permission_denied",
                r"Permission Denial",
            )

        return indicators

    # ==============================================================
    # CONFIDENCE
    # ==============================================================

    @staticmethod
    def calculate_confidence(
        evidence,
        metadata,
    ):
        """
        Estimate how strongly the collected evidence supports
        the detected failure.

        This is NOT an AI diagnosis.
        It is only evidence confidence.
        """

        score = 0

        if evidence.logcat:
            score += 2

        if evidence.package:
            score += 1

        if evidence.pid is not None:
            score += 1

        if evidence.activity_dump:
            score += 1

        if evidence.process_dump:
            score += 1

        if evidence.last_anr:
            score += 2

        if evidence.memory_dump:
            score += 1

        if metadata.get(
            "detected_exception"
        ):
            score += 2

        if metadata.get(
            "source_frames"
        ):
            score += 3

        if metadata.get(
            "signal"
        ):
            score += 3

        if metadata.get(
            "anr_reason"
        ):
            score += 2

        if score >= 10:
            return "HIGH"

        if score >= 6:
            return "MEDIUM"

        return "LOW"

    # ==============================================================
    # HELPERS
    # ==============================================================

    @staticmethod
    def unique_lines(lines):

        seen = set()
        unique = []

        for line in lines:

            if line in seen:
                continue

            seen.add(line)
            unique.append(line)

        return unique

    # ==============================================================
    # PRINT STRUCTURED RESULT
    # ==============================================================

    @staticmethod
    def print_metadata(evidence):

        metadata = evidence.metadata

        print()
        print(
            "========== STRUCTURED EVIDENCE =========="
        )

        print(
            "Failure Type :",
            metadata.get(
                "failure_type",
                "",
            ),
        )

        print(
            "Package      :",
            metadata.get(
                "package",
                "",
            ) or "<unknown>",
        )

        print(
            "Process      :",
            metadata.get(
                "process",
                "",
            ) or "<unknown>",
        )

        print(
            "PID          :",
            metadata.get(
                "pid",
                "",
            ) or "<unknown>",
        )

        if metadata.get("activity"):

            print(
                "Activity     :",
                metadata["activity"],
            )

        if metadata.get("anr_reason"):

            print()
            print(
                "ANR Reason   :",
                metadata["anr_reason"],
            )

        if metadata.get(
            "detected_exception"
        ):

            print(
                "Exception    :",
                metadata[
                    "detected_exception"
                ],
            )

        if metadata.get(
            "exception_message"
        ):

            print(
                "Message      :",
                metadata[
                    "exception_message"
                ],
            )

        if metadata.get("signal"):

            signal_text = str(
                metadata["signal"]
            )

            if metadata.get(
                "signal_name"
            ):

                signal_text += (
                    " ("
                    + metadata[
                        "signal_name"
                    ]
                    + ")"
                )

            print(
                "Native Signal:",
                signal_text,
            )

        if metadata.get(
            "abort_message"
        ):

            print(
                "Abort Message:",
                metadata[
                    "abort_message"
                ],
            )

        source_frames = metadata.get(
            "source_frames",
            [],
        )

        if source_frames:

            print()
            print(
                "Source Frames:"
            )

            for frame in source_frames[:10]:

                print(
                    "  - "
                    + frame["class"]
                    + "."
                    + frame["method"]
                    + " -> "
                    + frame["file"]
                    + ":"
                    + str(
                        frame["line"]
                    )
                )

        indicators = metadata.get(
            "indicators",
            [],
        )

        if indicators:

            print()
            print(
                "Indicators   :",
                ", ".join(indicators),
            )

        print(
            "Confidence   :",
            metadata.get(
                "confidence",
                "LOW",
            ),
        )

        print(
            "=========================================="
        )


# ==============================================================
# CONVENIENCE FUNCTION
# ==============================================================

def collect_failure_evidence(
    incident,
    serial=None,
):

    collector = FailureEvidenceCollector(
        serial=serial
    )

    return collector.collect(
        incident
    )


# ==============================================================
# STANDALONE TEST
# ==============================================================

if __name__ == "__main__":

    from modules.models import Incident

    serial = "0.0.0.0:6520"

    incident = Incident(
        timestamp=datetime.now().isoformat(),
        device_serial=serial,
        package="com.example.demo",
        process="com.example.demo",
        pid=5479,
        bug_type="ANR",
        reason="Input dispatching timed out",
        raw_log=(
            "ANR in com.example.demo "
            "(com.example.demo/.MainActivity)\n"
            "PID: 5479\n"
            "Reason: Input dispatching timed out"
        ),
    )

    evidence = collect_failure_evidence(
        incident,
        serial=serial,
    )

    print()
    print(
        "========== EVIDENCE SUMMARY =========="
    )

    print(
        "Type:",
        evidence.failure_type,
    )

    print(
        "Package:",
        evidence.package,
    )

    print(
        "Process:",
        evidence.process,
    )

    print(
        "PID:",
        evidence.pid,
    )

    print(
        "Logcat:",
        len(evidence.logcat),
        "characters",
    )

    print(
        "Activity:",
        len(evidence.activity_dump),
        "characters",
    )

    print(
        "Package:",
        len(evidence.package_dump),
        "characters",
    )

    print(
        "Process:",
        len(evidence.process_dump),
        "characters",
    )

    print(
        "Memory:",
        len(evidence.memory_dump),
        "characters",
    )

    print(
        "Last ANR:",
        len(evidence.last_anr),
        "characters",
    )

    print(
        "Metadata:",
        evidence.metadata,
    )
