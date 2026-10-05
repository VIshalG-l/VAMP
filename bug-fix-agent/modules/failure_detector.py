import re


# ============================================================
# FAILURE PATTERNS
# ============================================================

FAILURE_PATTERNS = {
    "CRASH": [
        r"FATAL EXCEPTION",
        r"AndroidRuntime.*FATAL EXCEPTION",
    ],

    "NATIVE_CRASH": [
        r"Fatal signal \d+",
        r"\bSIGSEGV\b",
        r"\bSIGABRT\b",
        r"\bSIGBUS\b",
        r"Abort message:",
        r"backtrace:",
    ],
}


class FailureDetector:

    """
    Generic Android failure detector.

    Designed to work across Android versions, including:

        Android 14 / API 34
        Android 15 / API 35
        Android 16 / API 36
        Android 17 / API 37

    Detection policy:

        ANR
        ---
        A real application ANR must contain strong
        application-specific evidence.

        Strongest form:

            ANR in com.example.app

        Additional accepted form:

            Process: com.example.app, PID: 1234
            Input dispatching timed out

        Also accepted:

            Application Not Responding
            Process: com.example.app, PID: 1234
            Input dispatching timed out

        The following ALONE are NOT enough:

            Application Not Responding

            Input dispatching timed out

            Window ... is unresponsive

        This prevents Android framework/system follow-up
        messages from creating false incidents.

        CRASH
        -----
        Detect Java/Kotlin application crashes from:

            FATAL EXCEPTION

        NATIVE_CRASH
        ------------
        Detect native failures from:

            Fatal signal
            SIGSEGV
            SIGABRT
            SIGBUS
            Abort message
            backtrace

    The detector identifies high-confidence failure
    signatures. Detailed evidence extraction is handled
    by the monitor/evidence pipeline.
    """

    # ========================================================
    # DETECT FAILURE
    # ========================================================

    def detect(self, text):

        if not text or not text.strip():
            return []

        text = str(text)

        # ----------------------------------------------------
        # 1. ANR
        # ----------------------------------------------------

        anr_result = self.detect_anr(text)

        if anr_result:
            return [anr_result]

        # ----------------------------------------------------
        # 2. NATIVE CRASH
        # ----------------------------------------------------

        for pattern in FAILURE_PATTERNS["NATIVE_CRASH"]:

            match = re.search(
                pattern,
                text,
                re.IGNORECASE
            )

            if not match:
                continue

            package = self.extract_package(text)

            return [{
                "type": "NATIVE_CRASH",
                "package": package,
                "pattern": pattern,
                "text": text,
            }]

        # ----------------------------------------------------
        # 3. JAVA / KOTLIN CRASH
        # ----------------------------------------------------

        for pattern in FAILURE_PATTERNS["CRASH"]:

            match = re.search(
                pattern,
                text,
                re.IGNORECASE
            )

            if not match:
                continue

            package = self.extract_package(text)

            return [{
                "type": "CRASH",
                "package": package,
                "pattern": pattern,
                "text": text,
            }]

        return []

    # ========================================================
    # DETECT ANR
    # ========================================================

    @classmethod
    def detect_anr(cls, text):

        """
        Detect a real application ANR.

        Android-version-independent strong forms:

            ANR in com.example.app

        or:

            Process: com.example.app, PID: 1234
            Input dispatching timed out

        or:

            Process: com.example.app
            Application Not Responding
            Input dispatching timed out

        The following are rejected when they appear alone:

            Application Not Responding

            Input dispatching timed out

            Window ... is unresponsive
        """

        # ----------------------------------------------------
        # Pattern 1:
        #
        # Strongest Android ANR signal:
        #
        # ANR in com.example.app
        #
        # Example:
        #
        # E ActivityManager:
        # ANR in com.example.demo
        # ----------------------------------------------------

        match = re.search(
            r"\bANR\s+in\s+([A-Za-z0-9_.$]+)",
            text,
            re.IGNORECASE
        )

        if match:

            package = match.group(1)

            if cls.is_valid_package(package):

                return {
                    "type": "ANR",
                    "package": package,
                    "pattern": match.group(0),
                    "text": text,
                }

        # ----------------------------------------------------
        # Pattern 2:
        #
        # Process + Input dispatch timeout
        #
        # This supports Android versions/log formats where
        # "ANR in <package>" is not available.
        #
        # IMPORTANT:
        #
        # The timeout alone is NOT sufficient.
        # ----------------------------------------------------

        timeout_match = re.search(
            r"\bInput\s+dispatch(?:ing)?\s+timed\s+out\b",
            text,
            re.IGNORECASE
        )

        if timeout_match:

            package = cls.extract_process_package(text)

            if (
                package
                and cls.is_valid_package(package)
                and cls.has_real_process_evidence(
                    text,
                    package
                )
            ):

                return {
                    "type": "ANR",
                    "package": package,
                    "pattern": timeout_match.group(0),
                    "text": text,
                }

        # ----------------------------------------------------
        # Pattern 3:
        #
        # Application Not Responding
        #
        # NEVER accept this phrase alone.
        #
        # Require:
        #
        #   Process/Cmdline package
        #
        # plus:
        #
        #   timeout OR explicit ANR marker
        # ----------------------------------------------------

        app_not_responding = re.search(
            r"\bApplication\s+Not\s+Responding\b",
            text,
            re.IGNORECASE
        )

        if app_not_responding:

            package = cls.extract_process_package(
                text
            )

            has_timeout = bool(
                re.search(
                    r"\bInput\s+dispatch(?:ing)?\s+timed\s+out\b",
                    text,
                    re.IGNORECASE
                )
            )

            has_anr_marker = bool(
                re.search(
                    r"\bANR\b",
                    text,
                    re.IGNORECASE
                )
            )

            if (
                package
                and cls.is_valid_package(package)
                and (has_timeout or has_anr_marker)
                and cls.has_real_process_evidence(
                    text,
                    package
                )
            ):

                return {
                    "type": "ANR",
                    "package": package,
                    "pattern": "Application Not Responding",
                    "text": text,
                }

        # ----------------------------------------------------
        # No high-confidence ANR.
        # ----------------------------------------------------

        return None

    # ========================================================
    # EXTRACT PACKAGE
    # ========================================================

    @staticmethod
    def extract_package(text):

        """
        Extract package from common Android crash/ANR formats.

        Priority:

            1. Process
            2. ANR in
            3. Cmdline
        """

        if not text:
            return None

        # ----------------------------------------------------
        # Java/Kotlin crash
        #
        # Process: com.example.app, PID: 1234
        # ----------------------------------------------------

        match = re.search(
            r"\bProcess:[ \t]*([A-Za-z0-9_.$]+)",
            text,
            re.IGNORECASE
        )

        if match:

            package = match.group(1)

            if FailureDetector.is_valid_package(
                package
            ):
                return package

        # ----------------------------------------------------
        # ANR
        #
        # ANR in com.example.app
        # ----------------------------------------------------

        match = re.search(
            r"\bANR[ \t]+in[ \t]+"
            r"([A-Za-z0-9_.$]+)",
            text,
            re.IGNORECASE
        )

        if match:

            package = match.group(1)

            if FailureDetector.is_valid_package(
                package
            ):
                return package

        # ----------------------------------------------------
        # Native crash
        #
        # Cmdline: com.example.app
        # Cmd line: com.example.app
        # ----------------------------------------------------

        match = re.search(
            r"\b(?:Cmdline|Cmd[ \t]+line):[ \t]*"
            r"([A-Za-z0-9_.$]+)",
            text,
            re.IGNORECASE
        )

        if match:

            package = match.group(1)

            if FailureDetector.is_valid_package(
                package
            ):
                return package

        return None

    # ========================================================
    # EXTRACT PROCESS PACKAGE
    # ========================================================

    @staticmethod
    def extract_process_package(text):

        """
        Extract application package from explicit process
        evidence.

        This deliberately does NOT extract a package from:

            Application Not Responding: <package>

        because that can be a framework/window-manager
        follow-up message rather than a new application ANR.
        """

        if not text:
            return None

        # ----------------------------------------------------
        # Process: com.example.app, PID: 1234
        # ----------------------------------------------------

        match = re.search(
            r"\bProcess:[ \t]*"
            r"([A-Za-z0-9_.$]+)",
            text,
            re.IGNORECASE
        )

        if match:

            package = match.group(1)

            if FailureDetector.is_valid_package(
                package
            ):
                return package

        # ----------------------------------------------------
        # Cmdline: com.example.app
        # ----------------------------------------------------

        match = re.search(
            r"\b(?:Cmdline|Cmd[ \t]+line):[ \t]*"
            r"([A-Za-z0-9_.$]+)",
            text,
            re.IGNORECASE
        )

        if match:

            package = match.group(1)

            if FailureDetector.is_valid_package(
                package
            ):
                return package

        return None

    # ========================================================
    # VALIDATE PACKAGE NAME
    # ========================================================

    @staticmethod
    def is_valid_package(package):

        """
        Validate an Android package name.

        Examples accepted:

            com.example.app
            com.example.demo
            org.test.application
            io.company.product

        Examples rejected:

            Window
            Application
            Not
            Responding
            main
            system_server
        """

        if not package:
            return False

        package = package.strip()

        if "." not in package:
            return False

        if not re.fullmatch(
            r"[A-Za-z0-9_]+"
            r"(?:\.[A-Za-z0-9_]+)+",
            package
        ):
            return False

        rejected = {
            "android.system",
            "android.server",
            "system.server",
            "com.android.system",
        }

        if package.lower() in rejected:
            return False

        return True

    # ========================================================
    # REAL PROCESS EVIDENCE
    # ========================================================

    @staticmethod
    def has_real_process_evidence(
        text,
        package
    ):

        """
        Determine whether the package is supported by
        explicit process/application evidence.

        We intentionally do NOT consider:

            Application Not Responding: <package>

        sufficient by itself.
        """

        if not text or not package:
            return False

        # ----------------------------------------------------
        # Explicit Process record.
        # ----------------------------------------------------

        process_match = re.search(
            r"\bProcess:[ \t]*"
            + re.escape(package)
            + r"(?:[ \t]*,|\s*$)",
            text,
            re.IGNORECASE | re.MULTILINE
        )

        if process_match:
            return True

        # ----------------------------------------------------
        # Explicit Cmdline record.
        # ----------------------------------------------------

        cmdline_match = re.search(
            r"\b(?:Cmdline|Cmd[ \t]+line):[ \t]*"
            + re.escape(package)
            + r"(?:[ \t]*$|\s)",
            text,
            re.IGNORECASE | re.MULTILINE
        )

        if cmdline_match:
            return True

        return False
