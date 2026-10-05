import re
from dataclasses import dataclass, field


@dataclass
class EvidenceAnalysis:
    """
    Structured interpretation of FailureEvidence.

    This class does NOT modify source code.

    It converts raw device evidence into information that
    the source resolver and AI layer can consume safely.
    """

    failure_type: str = ""
    package: str = ""
    process: str = ""
    pid: int | None = None

    activity: str = ""

    exception: str = ""
    exception_message: str = ""

    native_signal: str = ""
    native_signal_name: str = ""
    abort_message: str = ""

    anr_reason: str = ""

    source_frames: list = field(default_factory=list)

    indicators: list = field(default_factory=list)

    likely_area: str = ""
    likely_cause: str = ""

    confidence: str = "LOW"

    evidence_summary: str = ""


class EvidenceAnalyzer:
    """
    Analyze FailureEvidence without making a source-code change.

    Architecture:

        FailureEvidence
              |
              v
        EvidenceAnalyzer
              |
              v
        EvidenceAnalysis
    """

    def analyze(self, evidence):
        """
        Analyze a FailureEvidence object.
        """

        metadata = (
            getattr(
                evidence,
                "metadata",
                {},
            )
            or {}
        )

        analysis = EvidenceAnalysis()

        analysis.failure_type = (
            metadata.get(
                "failure_type",
                getattr(
                    evidence,
                    "failure_type",
                    "UNKNOWN",
                ),
            )
            or "UNKNOWN"
        ).upper()

        analysis.package = (
            metadata.get(
                "package",
                getattr(
                    evidence,
                    "package",
                    "",
                ),
            )
            or ""
        )

        analysis.process = (
            metadata.get(
                "process",
                getattr(
                    evidence,
                    "process",
                    "",
                ),
            )
            or ""
        )

        analysis.pid = metadata.get(
            "pid",
            getattr(
                evidence,
                "pid",
                None,
            ),
        )

        # Accept an activity only when it belongs to the
        # detected failure package. ActivityManager output can
        # contain unrelated system components.
        activity = (
            metadata.get(
                "activity",
                "",
            )
            or ""
        ).strip()

        if activity and analysis.package:

            activity_package = (
                activity.split("/", 1)[0]
                .strip()
            )

            if activity_package == analysis.package:
                analysis.activity = activity
            else:
                analysis.activity = ""

        else:
            analysis.activity = activity

        analysis.exception = (
            metadata.get(
                "detected_exception",
                metadata.get(
                    "exception",
                    "",
                ),
            )
            or ""
        )

        analysis.exception_message = (
            metadata.get(
                "exception_message",
                "",
            )
            or ""
        )

        analysis.native_signal = str(
            metadata.get(
                "signal",
                "",
            )
            or ""
        )

        analysis.native_signal_name = (
            metadata.get(
                "signal_name",
                "",
            )
            or ""
        )

        analysis.abort_message = (
            metadata.get(
                "abort_message",
                "",
            )
            or ""
        )

        # ----------------------------------------------------------
        # ANR reason is meaningful only for an ANR.
        #
        # A crash incident may contain unrelated WindowManager,
        # ActivityManager, or stale ANR information in the collected
        # evidence. Do not attach that information to a CRASH.
        # ----------------------------------------------------------

        if analysis.failure_type == "ANR":

            analysis.anr_reason = (
                metadata.get(
                    "anr_reason",
                    metadata.get(
                        "reason",
                        "",
                    ),
                )
                or ""
            )

        else:

            analysis.anr_reason = ""

        analysis.source_frames = (
            metadata.get(
                "source_frames",
                [],
            )
            or []
        )

        analysis.indicators = (
            metadata.get(
                "indicators",
                [],
            )
            or []
        )

        analysis.likely_area = (
            self.determine_area(
                analysis
            )
        )

        analysis.likely_cause = (
            self.determine_cause(
                analysis,
                evidence,
            )
        )

        analysis.confidence = (
            self.determine_confidence(
                analysis,
                evidence,
            )
        )

        analysis.evidence_summary = (
            self.build_summary(
                analysis,
                evidence,
            )
        )

        return analysis

    # ==============================================================
    # AREA
    # ==============================================================

    @staticmethod
    def determine_area(analysis):
        """
        Determine the most likely application area involved.

        This is intentionally conservative.

        Important classification priority:
            1. ANR is handled before native-signal evidence.
            2. Native signal is supplementary evidence for an ANR.
            3. Native crash is classified as native code.
        """

        failure_type = analysis.failure_type

        # ----------------------------------------------------------
        # ANR MUST TAKE PRIORITY OVER NATIVE SIGNAL
        # ----------------------------------------------------------
        if failure_type == "ANR":

            reason = (
                analysis.anr_reason
                .lower()
            )

            if "input dispatch" in reason:
                return "UI/main thread"

            if "broadcast" in reason:
                return "broadcast receiver"

            if "service" in reason:
                return "service"

            if "contentprovider" in reason:
                return "content provider"

            return "application responsiveness"

        # ----------------------------------------------------------
        # Application exceptions
        # ----------------------------------------------------------
        if analysis.exception:

            exception = (
                analysis.exception
                .lower()
            )

            exception_message = (
                analysis.exception_message
                .lower()
            )

            combined_exception = (
                exception
                + " "
                + exception_message
            )

            if "securityexception" in exception:
                return "permissions/security"

            if "outofmemoryerror" in exception:
                return "memory"

            if "indexoutofbound" in exception:
                return "application logic"

            if "nullpointerexception" in exception:
                return "application logic"

            if "illegalstateexception" in exception:
                return "application state"

            # Network failures are not always represented by a
            # network-specific exception class. Check both the
            # exception type and its message.
            if (
                "network" in combined_exception
                or "socket" in combined_exception
                or "unknownhost" in combined_exception
                or "connectexception" in combined_exception
                or "connecttimeout" in combined_exception
                or "connection refused" in combined_exception
                or "connection reset" in combined_exception
                or "connection timed out" in combined_exception
                or "cleartext http" in combined_exception
                or "http traffic" in combined_exception
                or "dns" in combined_exception
            ):
                return "network"

            if "activity" in exception:
                return "activity/lifecycle"

            if "service" in exception:
                return "service"

        # ----------------------------------------------------------
        # Native signal is meaningful only for a native crash.
        #
        # A Java/Kotlin CRASH can contain unrelated signal/system
        # evidence in the collected log buffer. Do not allow that
        # evidence to override the Java/Kotlin failure classification.
        # ----------------------------------------------------------
        if (
            failure_type == "NATIVE_CRASH"
            and analysis.native_signal
        ):
            return "native code"

        if failure_type == "OOM":
            return "memory"

        if failure_type in (
            "CRASH",
            "JAVA_CRASH",
            "KOTLIN_CRASH",
        ):
            return "application code"

        if failure_type == "NATIVE_CRASH":
            return "native code"

        return "unknown"

    # ==============================================================
    # ROOT CAUSE CATEGORY
    # ==============================================================

    @staticmethod
    def determine_cause(
        analysis,
        evidence,
    ):
        """
        Produce a conservative root-cause hypothesis.

        This is NOT the final AI diagnosis.

        Important classification priority:
            1. ANR is evaluated before native-signal evidence.
            2. Native Signal 3 or similar data is supplementary
               evidence and must not override an ANR.
        """

        # ----------------------------------------------------------
        # ANR MUST TAKE PRIORITY OVER NATIVE SIGNAL
        # ----------------------------------------------------------
        if analysis.failure_type == "ANR":

            reason = (
                analysis.anr_reason
                .lower()
            )

            if "input dispatch" in reason:

                return (
                    "The application stopped responding "
                    "to input events. The UI/main thread "
                    "is a primary investigation target."
                )

            if "broadcast" in reason:

                return (
                    "A broadcast receiver did not complete "
                    "within the Android response timeout."
                )

            if "service" in reason:

                return (
                    "An application service did not respond "
                    "within the Android service timeout."
                )

            return (
                "The application became unresponsive. "
                "Thread-level evidence is required to "
                "identify the blocking operation."
            )

        # ----------------------------------------------------------
        # NATIVE CRASH
        #
        # Native/framework stack frames are supplementary evidence.
        # They must NOT be automatically classified as application
        # source.
        #
        # Native source resolution is performed later by
        # BugFixAgent.locate_source().
        # ----------------------------------------------------------

        if analysis.failure_type == "NATIVE_CRASH":

            signal = (
                analysis.native_signal_name
                or analysis.native_signal
                or "unknown native signal"
            )

            return (
                "A native process failure was detected "
                f"with signal {signal}. "
                "Native/framework stack frames are treated "
                "as supporting evidence; application native "
                "source must be resolved from the failing "
                "application's JNI/native implementation."
            )

        # ----------------------------------------------------------
        # Source frames provide stronger localization for
        # non-ANR failures.
        #
        # Prefer frames belonging to the failing application
        # package. Android/framework/runtime frames may appear
        # before the application frame and must not become the
        # primary root-cause location.
        # ----------------------------------------------------------

        if analysis.source_frames:

            application_package = (
                str(analysis.package or "")
                .strip()
                .lower()
            )

            application_frame = None

            # First preference: frame whose class belongs to
            # the detected application package.
            if application_package:

                for frame in analysis.source_frames:

                    frame_class = (
                        str(
                            frame.get(
                                "class",
                                "",
                            )
                        )
                        .strip()
                        .lower()
                    )

                    if (
                        frame_class == application_package
                        or frame_class.startswith(
                            application_package + "."
                        )
                    ):
                        application_frame = frame
                        break

            # Second preference: if no package-matching frame
            # exists, use the first available frame. This keeps
            # the analyzer useful when package information is
            # incomplete.
            if application_frame is None:

                application_frame = (
                    analysis.source_frames[0]
                )

            return (
                "Failure is associated with "
                "application source frame "
                f"{application_frame.get('class', '')}."
                f"{application_frame.get('method', '')} "
                f"at {application_frame.get('file', '')}:"
                f"{application_frame.get('line', '')}."
            )

        # ----------------------------------------------------------
        # Java/Kotlin application exceptions
        # ----------------------------------------------------------
        if analysis.exception:

            if "nullpointerexception" in analysis.exception.lower():

                return (
                    "Application code attempted "
                    "to access a null object reference."
                )

            if "indexoutofbound" in analysis.exception.lower():

                return (
                    "Application code accessed "
                    "an invalid array or collection index."
                )

            if "outofmemoryerror" in analysis.exception.lower():

                return (
                    "The application or process "
                    "exceeded available memory limits."
                )

            if "securityexception" in analysis.exception.lower():

                return (
                    "The application attempted an "
                    "operation without sufficient permission "
                    "or security authorization."
                )

            if "illegalstateexception" in analysis.exception.lower():

                return (
                    "Application code entered or used "
                    "an invalid application state."
                )

            return (
                "A Java/Kotlin application exception "
                "caused the failure."
            )

        # ----------------------------------------------------------
        # Native signal applies to native failures, not ANRs.
        # ----------------------------------------------------------
        if analysis.native_signal:

            signal = (
                analysis.native_signal_name
                or analysis.native_signal
            )

            return (
                "A native process failure was detected "
                f"with signal {signal}."
            )

        return (
            "The collected evidence identifies a failure, "
            "but does not yet provide enough information "
            "to determine the root cause."
        )

    # ==============================================================
    # CONFIDENCE
    # ==============================================================

    @staticmethod
    def determine_confidence(
        analysis,
        evidence,
    ):
        """
        Determine confidence in the structured analysis.

        HIGH:
            Strong device evidence and source information.

        MEDIUM:
            Strong failure evidence but source location
            is not yet known.

        LOW:
            Weak or ambiguous evidence.
        """

        score = 0

        if analysis.failure_type:
            score += 1

        if analysis.package:
            score += 1

        if analysis.pid is not None:
            score += 1

        if analysis.activity:
            score += 1

        if analysis.anr_reason:
            score += 2

        if analysis.exception:
            score += 2

        if analysis.native_signal:
            score += 2

        if analysis.source_frames:
            score += 4

        if getattr(
            evidence,
            "logcat",
            "",
        ):
            score += 1

        if getattr(
            evidence,
            "process_dump",
            "",
        ):
            score += 1

        if getattr(
            evidence,
            "activity_dump",
            "",
        ):
            score += 1

        if getattr(
            evidence,
            "last_anr",
            "",
        ):
            score += 2

        if score >= 10:
            return "HIGH"

        if score >= 6:
            return "MEDIUM"

        return "LOW"

    # ==============================================================
    # SUMMARY
    # ==============================================================

    @staticmethod
    def build_summary(
        analysis,
        evidence,
    ):
        """
        Build a compact evidence summary for logging and
        future LLM input.
        """

        lines = []

        lines.append(
            f"Failure Type: {analysis.failure_type}"
        )

        lines.append(
            f"Package: {analysis.package or '<unknown>'}"
        )

        lines.append(
            f"Process: {analysis.process or '<unknown>'}"
        )

        lines.append(
            f"PID: {analysis.pid or '<unknown>'}"
        )

        if analysis.activity:

            lines.append(
                f"Activity: {analysis.activity}"
            )

        if analysis.exception:

            lines.append(
                f"Exception: {analysis.exception}"
            )

        if analysis.exception_message:

            lines.append(
                "Exception Message: "
                + analysis.exception_message
            )

        if analysis.anr_reason:

            lines.append(
                f"ANR Reason: {analysis.anr_reason}"
            )

        if analysis.native_signal:

            signal_text = (
                analysis.native_signal
            )

            if analysis.native_signal_name:

                signal_text += (
                    " ("
                    + analysis.native_signal_name
                    + ")"
                )

            lines.append(
                f"Native Signal: {signal_text}"
            )

        if analysis.abort_message:

            lines.append(
                "Abort Message: "
                + analysis.abort_message
            )

        lines.append(
            f"Likely Area: {analysis.likely_area}"
        )

        lines.append(
            f"Likely Cause: {analysis.likely_cause}"
        )

        if analysis.source_frames:

            lines.append(
                "Source Frames:"
            )

            for frame in analysis.source_frames[:10]:

                lines.append(
                    "  "
                    + frame.get(
                        "class",
                        "",
                    )
                    + "."
                    + frame.get(
                        "method",
                        "",
                    )
                    + " -> "
                    + frame.get(
                        "file",
                        "",
                    )
                    + ":"
                    + str(
                        frame.get(
                            "line",
                            "",
                        )
                    )
                )

        if analysis.indicators:

            lines.append(
                "Indicators: "
                + ", ".join(
                    analysis.indicators
                )
            )

        lines.append(
            f"Confidence: {analysis.confidence}"
        )

        return "\n".join(lines)

    # ==============================================================
    # PRINT
    # ==============================================================

    @staticmethod
    def print_analysis(analysis):

        print()
        print("=" * 70)
        print(
            "                 EVIDENCE ANALYSIS"
        )
        print("=" * 70)

        print(
            "Failure Type :",
            analysis.failure_type,
        )

        print(
            "Package      :",
            analysis.package or "<unknown>",
        )

        print(
            "Process      :",
            analysis.process or "<unknown>",
        )

        print(
            "PID          :",
            analysis.pid or "<unknown>",
        )

        if analysis.activity:

            print(
                "Activity     :",
                analysis.activity,
            )

        if analysis.exception:

            print(
                "Exception    :",
                analysis.exception,
            )

        if analysis.exception_message:

            print(
                "Message      :",
                analysis.exception_message,
            )

        if analysis.anr_reason:

            print(
                "ANR Reason   :",
                analysis.anr_reason,
            )

        if analysis.native_signal:

            signal_text = (
                analysis.native_signal
            )

            if analysis.native_signal_name:

                signal_text += (
                    " ("
                    + analysis.native_signal_name
                    + ")"
                )

            print(
                "Native Signal:",
                signal_text,
            )

        print(
            "Likely Area  :",
            analysis.likely_area,
        )

        print(
            "Likely Cause :",
            analysis.likely_cause,
        )

        if analysis.source_frames:

            print()
            print(
                "Source Frames:"
            )

            for frame in analysis.source_frames[:10]:

                print(
                    "  - "
                    + frame.get(
                        "class",
                        "",
                    )
                    + "."
                    + frame.get(
                        "method",
                        "",
                    )
                    + " -> "
                    + frame.get(
                        "file",
                        "",
                    )
                    + ":"
                    + str(
                        frame.get(
                            "line",
                            "",
                        )
                    )
                )

        if analysis.indicators:

            print()
            print(
                "Indicators   :",
                ", ".join(
                    analysis.indicators
                ),
            )

        print(
            "Confidence   :",
            analysis.confidence,
        )

        print("=" * 70)


def analyze_failure_evidence(evidence):
    """
    Convenience function.
    """

    analyzer = EvidenceAnalyzer()

    return analyzer.analyze(
        evidence
    )


if __name__ == "__main__":

    from datetime import datetime

    from modules.failure_evidence import (
        FailureEvidence,
    )

    evidence = FailureEvidence(
        timestamp=datetime.now().isoformat(),
        device_serial="0.0.0.0:6520",
        failure_type="ANR",
        package="com.example.demo",
        process="com.example.demo",
        pid=5479,
        logcat=(
            "ActivityManager: ANR in "
            "com.example.demo "
            "(com.example.demo/.MainActivity)"
        ),
        activity_dump=(
            "ActivityRecord{... "
            "com.example.demo/.MainActivity}"
        ),
        last_anr=(
            "Reason: Input dispatching timed out "
            "(com.example.demo/.MainActivity)"
        ),
        metadata={
            "failure_type": "ANR",
            "package": "com.example.demo",
            "process": "com.example.demo",
            "pid": 5479,
            "reason": "Input dispatching timed out",
            "anr_reason": "Input dispatching timed out",
            "activity": "com.example.demo/.MainActivity",
            "indicators": [
                "input_dispatch_timeout"
            ],
            "confidence": "HIGH",
        },
    )

    analysis = analyze_failure_evidence(
        evidence
    )

    EvidenceAnalyzer.print_analysis(
        analysis
    )

    print()
    print(
        "========== ANALYSIS SUMMARY =========="
    )

    print(
        analysis.evidence_summary
    )
