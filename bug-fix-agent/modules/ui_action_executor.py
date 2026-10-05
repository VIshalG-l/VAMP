import time
from dataclasses import dataclass
from typing import Optional

from modules.ui_action_discoverer import UIAction
from modules.ui_action_selector import UIActionCandidate


@dataclass
class ActionExecutionResult:
    success: bool
    action_index: Optional[int]
    coordinates: Optional[tuple]
    reason: str


class UIActionExecutor:
    """
    Safely executes a UI action discovered from Android.

    Safety rules:
        1. A candidate must exist.
        2. The UI element must be clickable.
        3. The UI element must be enabled.
        4. Valid screen bounds must exist.
        5. Correlation confidence must meet the threshold.
        6. The action is executed using discovered coordinates.

    This module contains no application-specific UI names.
    """

    def __init__(
        self,
        discoverer,
        minimum_confidence: float = 0.70,
        settle_seconds: float = 1.0,
    ):
        self.discoverer = discoverer

        self.minimum_confidence = max(
            0.0,
            min(
                1.0,
                float(minimum_confidence),
            ),
        )

        self.settle_seconds = max(
            0.0,
            float(settle_seconds),
        )

    @staticmethod
    def _parse_bounds(bounds):
        if not bounds:
            return None

        text = str(bounds).strip()

        if not text.startswith("["):
            return None

        try:
            first = text.index("]")
            second = text.index(
                "[",
                first,
            )
            last = text.index(
                "]",
                second,
            )

            first_part = text[
                1:first
            ]

            second_part = text[
                second + 1:last
            ]

            x1, y1 = map(
                int,
                first_part.split(","),
            )

            x2, y2 = map(
                int,
                second_part.split(","),
            )

        except (
            ValueError,
            IndexError,
        ):
            return None

        if x2 <= x1 or y2 <= y1:
            return None

        return (
            (x1 + x2) // 2,
            (y1 + y2) // 2,
        )

    def validate_candidate(
        self,
        candidate: Optional[
            UIActionCandidate
        ],
        confidence: float,
    ):
        if candidate is None:
            return False, (
                "No UI action candidate supplied."
            )

        if confidence < (
            self.minimum_confidence
        ):
            return False, (
                "UI action confidence "
                f"{confidence:.2f} is below "
                "the execution threshold "
                f"{self.minimum_confidence:.2f}."
            )

        action = candidate.action

        if not isinstance(
            action,
            UIAction,
        ):
            return False, (
                "Invalid UI action object."
            )

        if not action.clickable:
            return False, (
                "Selected UI element is "
                "not clickable."
            )

        if not action.enabled:
            return False, (
                "Selected UI element is "
                "disabled."
            )

        coordinates = (
            self._parse_bounds(
                action.bounds
            )
        )

        if coordinates is None:
            return False, (
                "Selected UI element has "
                "invalid screen bounds."
            )

        x, y = coordinates

        if x < 0 or y < 0:
            return False, (
                "Calculated UI coordinates "
                "are invalid."
            )

        return True, (
            "UI action passed all safety checks."
        )

    def execute(
        self,
        candidate: Optional[
            UIActionCandidate
        ],
        confidence: float,
    ):
        print()
        print(
            "========== SAFE UI ACTION EXECUTION =========="
        )

        valid, message = (
            self.validate_candidate(
                candidate,
                confidence,
            )
        )

        if not valid:
            print(
                "❌ Action rejected."
            )
            print(
                "Reason:",
                message,
            )
            print(
                "=============================================="
            )

            return ActionExecutionResult(
                success=False,
                action_index=(
                    candidate.action.index
                    if candidate is not None
                    else None
                ),
                coordinates=None,
                reason=message,
            )

        action = candidate.action

        coordinates = (
            self._parse_bounds(
                action.bounds
            )
        )

        x, y = coordinates

        print(
            "Action Index :",
            action.index,
        )

        print(
            "Class        :",
            action.class_name
            or "Unknown",
        )

        print(
            "Text         :",
            action.text
            or "None",
        )

        print(
            "Bounds       :",
            action.bounds,
        )

        print(
            "Confidence   :",
            f"{confidence:.2f}",
        )

        print(
            "Threshold    :",
            f"{self.minimum_confidence:.2f}",
        )

        print(
            "Coordinates   :",
            f"({x}, {y})",
        )

        print()
        print(
            "Safety checks: PASSED"
        )

        print()
        print(
            "[ACTION] Executing discovered UI action..."
        )

        try:
            success, result = (
                self.discoverer.click_action(
                    action
                )
            )
        except Exception as exc:
            success = False
            result = str(exc)

        if not success:
            print()
            print(
                "❌ UI action execution failed."
            )
            print(
                "Reason:",
                result,
            )

            print(
                "=============================================="
            )

            return ActionExecutionResult(
                success=False,
                action_index=action.index,
                coordinates=coordinates,
                reason=(
                    result
                    or "UI action execution failed."
                ),
            )

        if self.settle_seconds > 0:
            time.sleep(
                self.settle_seconds
            )

        print()
        print(
            "✅ UI action executed successfully."
        )

        print(
            "=============================================="
        )

        return ActionExecutionResult(
            success=True,
            action_index=action.index,
            coordinates=coordinates,
            reason=(
                "UI action executed successfully."
            ),
        )


if __name__ == "__main__":

    print()
    print("=" * 70)
    print("           SAFE UI ACTION EXECUTOR")
    print("=" * 70)

    from modules.ui_action_discoverer import (
        UIActionDiscoverer,
    )
    from modules.ui_action_correlator import (
        UIActionCorrelator,
    )

    discoverer = (
        UIActionDiscoverer()
    )

    success, actions, message = (
        discoverer.discover()
    )

    if not success:
        print()
        print(
            "❌ UI discovery failed."
        )
        raise SystemExit(1)

    class TestIncident:
        bug_type = "ANR"
        exception = ""
        reason = (
            "Input dispatching timed out"
        )
        thread = ""
        stack_trace = ""

    source_context = """
    Button onClick handler.
    The UI thread performs a blocking operation.
    """

    evidence_text = """
    Application became unresponsive.
    Input dispatching timed out.
    """

    correlator = UIActionCorrelator(
        actions=actions,
        incident=TestIncident(),
        source_context=source_context,
        evidence_text=evidence_text,
    )

    correlation = (
        correlator.correlate()
    )

    correlator.print_result(
        correlation
    )

    executor = UIActionExecutor(
        discoverer=discoverer,
        minimum_confidence=0.70,
    )

    print()
    print(
        "Execution threshold:",
        "0.70",
    )

    result = executor.execute(
        candidate=correlation.candidate,
        confidence=correlation.confidence,
    )

    print()
    print(
        "========== EXECUTION RESULT =========="
    )

    print(
        "Success      :",
        result.success,
    )

    print(
        "Action Index :",
        result.action_index,
    )

    print(
        "Coordinates  :",
        result.coordinates,
    )

    print(
        "Reason       :",
        result.reason,
    )

    print(
        "======================================="
    )
