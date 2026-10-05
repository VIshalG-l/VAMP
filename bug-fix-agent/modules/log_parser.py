import re


def parse_log(log_file):
    """
    Generic Android failure log parser.

    Supports:
        - ANR
        - Java/Kotlin crash
        - Native crash

    Supports:
        - Raw Android logs
        - VAMP-generated Incident logs

    Generic application stack resolution:
        1. Identify the failing package/process.
        2. Prefer stack frames from the failing application package.
        3. Prefer frames inside the FATAL EXCEPTION block.
        4. Ignore unrelated Android/framework/launcher traces when
           selecting the primary application source location.

    No application package, class, file, or activity is hard-coded.
    """

    with open(log_file, "r", errors="ignore") as f:
        text = f.read()

    report = {
        "type": "UNKNOWN",
        "package": None,
        "process": None,
        "pid": None,
        "reason": None,
        "exception": None,
        "thread": None,
        "class": None,
        "method": None,
        "file": None,
        "line": None,
        "stacktrace": "",
        "timestamp": None,
    }

    if not text.strip():
        return report

    # ============================================================
    # INTERNAL HELPERS
    # ============================================================

    def clean_android_log_line(line):
        """
        Remove the normal logcat prefix and Android log tag.

        Example:

        09-11 12:49:14.723  8848  8848 E AndroidRuntime:
            at com.example.demo.MainActivityKt...(MainActivity.kt:56)

        becomes:

            at com.example.demo.MainActivityKt...(MainActivity.kt:56)
        """

        value = line.rstrip("\r\n")

        value = re.sub(
            r"^\s*"
            r"\d{2}-\d{2}\s+"
            r"\d{2}:\d{2}:\d{2}\.\d+\s+"
            r"\d+\s+\d+\s+"
            r"[VDIWEF]\s+"
            r"[^:]+:\s?",
            "",
            value,
        )

        return value.strip()

    def normalize_package(value):
        if not value:
            return None

        value = value.strip()

        value = value.rstrip(",:;")

        if not re.match(
            r"^[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z0-9_$]+)+$",
            value,
        ):
            return None

        return value

    def is_valid_stack_class(class_name):
        if not class_name:
            return False

        class_name = class_name.strip()

        if class_name.startswith(
            (
                "android.",
                "androidx.",
                "com.android.",
                "java.",
                "javax.",
                "kotlin.",
                "kotlinx.",
                "dalvik.",
                "sun.",
                "libcore.",
            )
        ):
            return False

        return True

    def parse_stack_frame(line):
        """
        Parse a Java/Kotlin stack frame.

        Examples:

            at com.example.demo.MainActivityKt.foo(MainActivity.kt:56)

            at androidx.compose.ui.Node.foo(Clickable.kt:935)

            com.example.demo.MainActivityKt.foo(MainActivity.kt:56)
        """

        value = clean_android_log_line(line)

        value = value.strip()

        if value.startswith("at "):
            value = value[3:].strip()

        match = re.match(
            r"^([A-Za-z0-9_.$]+)"
            r"\.([A-Za-z0-9_$<>-]+)"
            r"\(([^:()\r\n]+):(\d+)\)"
            r"$",
            value,
        )

        if not match:
            return None

        class_name = match.group(1)
        method_name = match.group(2)
        file_name = match.group(3)
        line_number = match.group(4)

        try:
            line_number = int(line_number)
        except ValueError:
            return None

        return {
            "class": class_name,
            "method": method_name,
            "file": file_name,
            "line": line_number,
        }

    def extract_stack_frames(block):
        frames = []

        for line in block.splitlines():

            frame = parse_stack_frame(line)

            if frame:
                frames.append(frame)

        return frames

    def package_matches_class(package_name, class_name):
        if not package_name or not class_name:
            return False

        return (
            class_name == package_name
            or class_name.startswith(package_name + ".")
        )

    def select_best_application_frame(
        frames,
        package_name=None,
    ):
        """
        Rank stack frames instead of selecting the first frame.

        Highest priority:
            application package frame

        Lower priority:
            normal non-framework frame

        Rejected/low priority:
            Android framework
            AndroidX
            Java/Kotlin runtime
            Launcher/system classes

        This is intentionally package-driven and therefore generic.
        """

        if not frames:
            return None

        ranked = []

        for index, frame in enumerate(frames):

            class_name = frame.get("class")

            if not class_name:
                continue

            score = 0

            # ----------------------------------------------------
            # Strongest evidence:
            # frame belongs to the failed application package
            # ----------------------------------------------------

            if package_matches_class(
                package_name,
                class_name,
            ):
                score += 1000

            # ----------------------------------------------------
            # Framework/system filtering
            # ----------------------------------------------------

            if class_name.startswith(
                (
                    "com.android.",
                    "android.",
                    "androidx.",
                    "java.",
                    "javax.",
                    "kotlin.",
                    "kotlinx.",
                    "dalvik.",
                    "sun.",
                    "libcore.",
                )
            ):
                score -= 500

            elif is_valid_stack_class(class_name):
                score += 100

            # ----------------------------------------------------
            # Prefer frames that have a real source line.
            # ----------------------------------------------------

            if frame.get("file"):
                score += 50

            if frame.get("line") is not None:
                score += 50

            # Earlier application frame is normally closer to the
            # actual throw site.
            score += max(0, 20 - index)

            ranked.append(
                (
                    score,
                    index,
                    frame,
                )
            )

        if not ranked:
            return None

        ranked.sort(
            key=lambda item: (
                item[0],
                -item[1],
            ),
            reverse=True,
        )

        return ranked[0][2]

    # ============================================================
    # 1. FAILURE TYPE
    # ============================================================

    if (
        re.search(
            r"\bANR in\b",
            text,
            re.IGNORECASE,
        )
        or re.search(
            r"Application Not Responding",
            text,
            re.IGNORECASE,
        )
        or re.search(
            r"Input dispatching timed out",
            text,
            re.IGNORECASE,
        )
        or re.search(
            r"Bug Type\s*:\s*ANR",
            text,
            re.IGNORECASE,
        )
    ):
        report["type"] = "ANR"

    elif re.search(
        r"FATAL EXCEPTION",
        text,
        re.IGNORECASE,
    ):
        report["type"] = "CRASH"

    elif (
        re.search(
            r"Fatal signal\s+\d+",
            text,
            re.IGNORECASE,
        )
        or re.search(
            r"\bSIGSEGV\b",
            text,
            re.IGNORECASE,
        )
        or re.search(
            r"\bSIGABRT\b",
            text,
            re.IGNORECASE,
        )
        or re.search(
            r"\bSIGBUS\b",
            text,
            re.IGNORECASE,
        )
        or re.search(
            r"Abort message:",
            text,
            re.IGNORECASE,
        )
        or re.search(
            r"\bbacktrace:",
            text,
            re.IGNORECASE,
        )
    ):
        report["type"] = "NATIVE_CRASH"

    # ============================================================
    # 2. VAMP INCIDENT FIELD READER
    # ============================================================

    def get_field(name):

        pattern = (
            r"^[ \t]*"
            + re.escape(name)
            + r"[ \t]*:[ \t]*([^\r\n]*)$"
        )

        return re.search(
            pattern,
            text,
            re.IGNORECASE | re.MULTILINE,
        )

    package_match = get_field("Package")
    process_match = get_field("Process")
    pid_match = get_field("PID")
    type_match = get_field("Bug Type")
    reason_match = get_field("Reason")
    exception_match = get_field("Exception")
    thread_match = get_field("Thread")
    timestamp_match = get_field("Timestamp")

    # ============================================================
    # 3. PACKAGE
    # ============================================================

    if package_match:

        value = package_match.group(1).strip()

        if value:
            report["package"] = normalize_package(value)

    # ============================================================
    # 4. PROCESS
    # ============================================================

    if process_match:

        value = process_match.group(1).strip()

        if value:
            report["process"] = value

    # ============================================================
    # 5. PID
    # ============================================================

    if pid_match:

        value = pid_match.group(1).strip()

        if value.isdigit():
            report["pid"] = int(value)

    # ============================================================
    # 6. BUG TYPE
    # ============================================================

    if type_match:

        value = type_match.group(1).strip()

        if value:
            report["type"] = value.upper()

    # ============================================================
    # 7. REASON
    # ============================================================

    if reason_match:

        value = reason_match.group(1).strip()

        if value:
            report["reason"] = value

    # ============================================================
    # 8. EXCEPTION
    # ============================================================

    if exception_match:

        value = exception_match.group(1).strip()

        if value and not re.fullmatch(r"=+", value):
            report["exception"] = value

    # ============================================================
    # 9. THREAD
    # ============================================================

    if thread_match:

        value = thread_match.group(1).strip()

        if value and not re.fullmatch(r"=+", value):
            report["thread"] = value

    # ============================================================
    # 10. TIMESTAMP
    # ============================================================

    if timestamp_match:

        value = timestamp_match.group(1).strip()

        if value:
            report["timestamp"] = value

    # ============================================================
    # 11. PACKAGE FALLBACK FOR RAW ANDROID LOGS
    # ============================================================

    if not report["package"]:

        package_patterns = [
            r"Process:\s*([A-Za-z0-9._$-]+)",
            r"Cmd line:\s*([A-Za-z0-9._$-]+)",
            r"Cmdline:\s*([A-Za-z0-9._$-]+)",
            r"Package:\s*([A-Za-z0-9._$-]+)",
            r"ANR in\s+([A-Za-z0-9._$-]+)",
        ]

        for pattern in package_patterns:

            match = re.search(
                pattern,
                text,
                re.IGNORECASE,
            )

            if not match:
                continue

            candidate = normalize_package(
                match.group(1)
            )

            if not candidate:
                continue

            if candidate.lower() in {
                "thread",
                "process",
                "pid",
                "none",
                "unknown",
            }:
                continue

            report["package"] = candidate
            break

    # ============================================================
    # 12. PROCESS FALLBACK
    # ============================================================

    if not report["process"]:

        match = re.search(
            r"Process:\s*([A-Za-z0-9._$-]+)",
            text,
            re.IGNORECASE,
        )

        if match:
            report["process"] = match.group(1).strip()

    if not report["process"] and report["package"]:
        report["process"] = report["package"]

    # ============================================================
    # 13. PID FALLBACK
    # ============================================================

    if report["pid"] is None:

        pid_patterns = [
            r"PID:\s*(\d+)",
            r"pid[:= ]+(\d+)",
            r"PID\s*=\s*(\d+)",
        ]

        for pattern in pid_patterns:

            match = re.search(
                pattern,
                text,
                re.IGNORECASE,
            )

            if match:
                report["pid"] = int(match.group(1))
                break

    # ============================================================
    # 14. ANR REASON FALLBACK
    # ============================================================

    if report["type"] == "ANR" and not report["reason"]:

        match = re.search(
            r"Reason:[ \t]*([^\r\n]+)",
            text,
            re.IGNORECASE,
        )

        if match:
            report["reason"] = match.group(1).strip()

        else:

            match = re.search(
                r"Input dispatching timed out\s*\((.*?)\)",
                text,
                re.IGNORECASE | re.DOTALL,
            )

            if match:
                report["reason"] = match.group(1).strip()

    # ============================================================
    # 15. JAVA / KOTLIN EXCEPTION FALLBACK
    # ============================================================

    if report["type"] == "CRASH" and not report["exception"]:

        exception_patterns = [
            r"(java\.[A-Za-z0-9_.$]+Exception(?::[^\r\n]*)?)",
            r"(kotlin\.[A-Za-z0-9_.$]+Exception(?::[^\r\n]*)?)",
            r"([A-Za-z0-9_.$]+Exception(?::[^\r\n]*)?)",
        ]

        for pattern in exception_patterns:

            match = re.search(
                pattern,
                text,
                re.IGNORECASE,
            )

            if match:
                report["exception"] = match.group(1).strip()
                break

    # ============================================================
    # 16. THREAD FALLBACK
    # ============================================================

    if not report["thread"]:

        match = re.search(
            r"FATAL EXCEPTION:[ \t]*([^\r\n]+)",
            text,
            re.IGNORECASE,
        )

        if match:
            report["thread"] = match.group(1).strip()

    # ============================================================
    # 17. CRASH-SPECIFIC STACK EXTRACTION
    #
    # IMPORTANT:
    #
    # Do NOT search the complete log for the first stack frame.
    #
    # Android logs can contain unrelated stack traces before or
    # after the real application crash.
    #
    # Example:
    #
    # LauncherStateManager.java:547
    #
    # appears before:
    #
    # FATAL EXCEPTION
    # Process: com.example.demo
    # MainActivity.kt:56
    #
    # Therefore CRASH source selection starts from the actual
    # FATAL EXCEPTION block.
    # ============================================================

    crash_frames = []

    if report["type"] == "CRASH":

        fatal_matches = list(
            re.finditer(
                r"FATAL EXCEPTION:[^\r\n]*",
                text,
                re.IGNORECASE,
            )
        )

        selected_crash_block = ""

        if fatal_matches:

            # Normally the final FATAL EXCEPTION is the actual
            # crash block captured by AndroidRuntime.
            #
            # If multiple crash blocks exist, inspect all blocks
            # and prefer the one matching the identified package.
            candidate_blocks = []

            for index, fatal_match in enumerate(
                fatal_matches
            ):

                start = fatal_match.start()

                if index + 1 < len(fatal_matches):
                    end = fatal_matches[index + 1].start()
                else:
                    # Limit the block so unrelated later system
                    # traces do not become part of this crash.
                    end = min(
                        len(text),
                        start + 12000,
                    )

                block = text[start:end]

                candidate_blocks.append(block)

            # Prefer a block containing the failing package.
            matching_blocks = []

            for block in candidate_blocks:

                if (
                    report["package"]
                    and report["package"] in block
                ):
                    matching_blocks.append(block)

            if matching_blocks:
                selected_crash_block = matching_blocks[-1]

            else:
                selected_crash_block = candidate_blocks[-1]

        if selected_crash_block:

            crash_frames = extract_stack_frames(
                selected_crash_block
            )

    # ============================================================
    # 18. SOURCE LOCATION
    #
    # First preference:
    #     actual CRASH block
    #
    # Second preference:
    #     all stack frames, but ranked by application package.
    # ============================================================

    selected_frame = None

    if crash_frames:

        selected_frame = select_best_application_frame(
            crash_frames,
            report["package"],
        )

    # Fallback for ANR/native/VAMP logs or unusual crash formats.
    if selected_frame is None:

        all_frames = extract_stack_frames(text)

        selected_frame = select_best_application_frame(
            all_frames,
            report["package"],
        )

    if selected_frame:

        report["class"] = selected_frame["class"]
        report["method"] = selected_frame["method"]
        report["file"] = selected_frame["file"]
        report["line"] = selected_frame["line"]

    # ============================================================
    # 19. STACK TRACE
    #
    # Build a clean stack trace from Android logcat lines.
    # ============================================================

    stack_lines = []

    for line in text.splitlines():

        cleaned = clean_android_log_line(line)

        if (
            cleaned.startswith("at ")
            or cleaned.startswith("Caused by:")
            or cleaned.startswith("FATAL EXCEPTION")
        ):
            stack_lines.append(cleaned)

    if stack_lines:
        report["stacktrace"] = "\n".join(
            stack_lines
        )

    # ============================================================
    # 20. TIMESTAMP FALLBACK
    # ============================================================

    if not report["timestamp"]:

        timestamp_patterns = [
            r"(\d\d-\d\d\s+\d\d:\d\d:\d+\.\d+)",
            (
                r"(\d{4}-\d{2}-\d{2}"
                r"[T ]\d{2}:\d{2}:\d{2}"
                r"(?:\.\d+)?)"
            ),
        ]

        for pattern in timestamp_patterns:

            match = re.search(
                pattern,
                text,
            )

            if match:
                report["timestamp"] = match.group(1)
                break

    return report
