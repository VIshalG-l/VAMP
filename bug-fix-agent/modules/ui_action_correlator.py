from dataclasses import dataclass
from typing import Any, List, Optional

from modules.ui_action_discoverer import UIAction
from modules.ui_action_selector import UIActionCandidate


@dataclass
class UIActionCorrelationResult:
    candidate: Optional[UIActionCandidate]
    confidence: float
    score: int
    decision: str
    reasons: List[str]


class UIActionCorrelator:
    """
    Intelligent generic correlation engine between discovered
    Android UI actions and failure evidence.

    The correlator does not know:

        - package name
        - APK name
        - activity name
        - button name
        - fixed coordinates
        - source path

    It dynamically correlates:

        UI action
            +
        nested UI elements
            +
        incident evidence
            +
        source context

    The important improvement over the previous implementation
    is that clickable parent views can inherit semantic information
    from child elements contained inside their bounds.

    Example:

        clickable View
            [222,568][499,664]

                contains

        TextView
            "Generate ANR"
            [270,596][451,636]

    The clickable parent therefore receives the semantic identity
    of the visible child.
    """

    GENERIC_TOKENS = {
        "android",
        "view",
        "widget",
        "java",
        "kotlin",
        "class",
        "object",
        "true",
        "false",
        "none",
        "null",
        "unknown",
        "main",
        "activity",
        "application",
        "app",
        "com",
        "example",
        "ui",
        "text",
        "id",
    }

    def __init__(
        self,
        actions,
        incident=None,
        source_context=None,
        evidence_text=None,
    ):
        self.actions = actions or []
        self.incident = incident
        self.source_context = source_context
        self.evidence_text = evidence_text

    # ============================================================
    # GENERIC VALUE NORMALIZATION
    # ============================================================

    @staticmethod
    def _value_to_text(value: Any) -> str:
        if value is None:
            return ""

        if isinstance(value, str):
            return value

        if isinstance(value, dict):
            parts = []

            for key, item in value.items():
                key_text = UIActionCorrelator._value_to_text(key)
                item_text = UIActionCorrelator._value_to_text(item)

                if key_text:
                    parts.append(key_text)

                if item_text:
                    parts.append(item_text)

            return " ".join(parts)

        if isinstance(value, (list, tuple, set)):
            return " ".join(
                UIActionCorrelator._value_to_text(item)
                for item in value
            )

        if isinstance(value, bool):
            return "true" if value else "false"

        if isinstance(value, (int, float)):
            return str(value)

        try:
            return str(value)
        except Exception:
            return ""

    # ============================================================
    # TOKENIZATION
    # ============================================================

    @classmethod
    def _tokens(cls, value: Any):
        text = cls._value_to_text(value).strip().lower()

        if not text:
            return set()

        tokens = set()
        current = ""

        for character in text:
            if character.isalnum() or character == "_":
                current += character
            else:
                if current:
                    tokens.add(current)
                    current = ""

        if current:
            tokens.add(current)

        return {
            token
            for token in tokens
            if token not in cls.GENERIC_TOKENS
            and len(token) >= 2
        }

    # ============================================================
    # BOUNDS PARSING
    # ============================================================

    @staticmethod
    def _parse_bounds(bounds):
        if not bounds:
            return None

        text = str(bounds).strip()

        try:
            first_end = text.index("]")
            second_start = text.index("[", first_end)
            second_end = text.index("]", second_start)

            first_part = text[1:first_end]
            second_part = text[second_start + 1:second_end]

            x1, y1 = map(int, first_part.split(","))
            x2, y2 = map(int, second_part.split(","))

            return x1, y1, x2, y2

        except (ValueError, IndexError):
            return None

    @classmethod
    def _bounds_contains(cls, parent_bounds, child_bounds):
        parent = cls._parse_bounds(parent_bounds)
        child = cls._parse_bounds(child_bounds)

        if parent is None or child is None:
            return False

        px1, py1, px2, py2 = parent
        cx1, cy1, cx2, cy2 = child

        return (
            cx1 >= px1
            and cy1 >= py1
            and cx2 <= px2
            and cy2 <= py2
        )

    # ============================================================
    # EVIDENCE
    # ============================================================

    def _build_evidence_text(self):
        values = []

        if self.source_context:
            values.append(
                self._value_to_text(
                    self.source_context
                )
            )

        if self.evidence_text:
            values.append(
                self._value_to_text(
                    self.evidence_text
                )
            )

        if self.incident is not None:

            fields = [
                "package",
                "process",
                "bug_type",
                "exception",
                "reason",
                "thread",
                "stack_trace",
                "raw_log",
            ]

            for field in fields:
                try:
                    value = getattr(
                        self.incident,
                        field,
                        "",
                    )
                except Exception:
                    value = ""

                if value:
                    values.append(
                        self._value_to_text(value)
                    )

        return " ".join(
            value
            for value in values
            if value
        )

    # ============================================================
    # ACTION TEXT
    # ============================================================

    def _action_text(self, action):
        if action is None:
            return ""

        values = [
            getattr(action, "class_name", ""),
            getattr(action, "text", ""),
            getattr(action, "content_desc", ""),
            getattr(action, "resource_id", ""),
        ]

        return " ".join(
            self._value_to_text(value)
            for value in values
            if value
        )

    # ============================================================
    # CHILD SEMANTIC INFORMATION
    # ============================================================

    def _get_nested_semantics(self, action):
        """
        Find UI elements physically contained inside the candidate.

        This allows a clickable parent View to inherit the visible
        text/content-description of its child TextView.
        """

        if action is None:
            return []

        parent_bounds = getattr(
            action,
            "bounds",
            "",
        )

        if not parent_bounds:
            return []

        nested = []

        for other in self.actions:

            if other is None:
                continue

            if other is action:
                continue

            child_bounds = getattr(
                other,
                "bounds",
                "",
            )

            if not child_bounds:
                continue

            if not self._bounds_contains(
                parent_bounds,
                child_bounds,
            ):
                continue

            text = self._value_to_text(
                getattr(other, "text", "")
            ).strip()

            content_desc = self._value_to_text(
                getattr(other, "content_desc", "")
            ).strip()

            resource_id = self._value_to_text(
                getattr(other, "resource_id", "")
            ).strip()

            if text or content_desc or resource_id:
                nested.append(other)

        return nested

    # ============================================================
    # SEMANTIC ACTION TEXT
    # ============================================================

    def _build_action_semantic_text(self, action):
        values = []

        direct_text = self._action_text(action)

        if direct_text:
            values.append(direct_text)

        nested_actions = self._get_nested_semantics(
            action
        )

        for child in nested_actions:

            child_text = self._action_text(child)

            if child_text:
                values.append(child_text)

        return " ".join(values)

    # ============================================================
    # CANDIDATE CORRELATION
    # ============================================================

    def _correlate_candidate(
        self,
        action,
        evidence_tokens,
    ):
        score = 0
        reasons = []

        if action is None:
            return 0, reasons

        # --------------------------------------------------------
        # BASIC SAFETY
        # --------------------------------------------------------

        if getattr(action, "clickable", False):
            score += 20
            reasons.append(
                "UI element is clickable."
            )

        if getattr(action, "enabled", False):
            score += 10
            reasons.append(
                "UI element is enabled."
            )

        # --------------------------------------------------------
        # DIRECT + NESTED SEMANTICS
        # --------------------------------------------------------

        semantic_text = (
            self._build_action_semantic_text(
                action
            )
        )

        action_tokens = self._tokens(
            semantic_text
        )

        overlap = (
            action_tokens
            & evidence_tokens
        )

        if overlap:
            token_score = min(
                50,
                len(overlap) * 15
            )

            score += token_score

            reasons.append(
                "UI action shares meaningful "
                "evidence tokens: "
                + ", ".join(
                    sorted(overlap)
                )
            )

        # --------------------------------------------------------
        # CHILD ELEMENT BONUS
        # --------------------------------------------------------

        nested_actions = (
            self._get_nested_semantics(
                action
            )
        )

        if nested_actions:
            score += 15

            reasons.append(
                "Clickable UI element contains "
                "a semantic child element."
            )

            child_descriptions = []

            for child in nested_actions:

                text = self._value_to_text(
                    getattr(
                        child,
                        "text",
                        "",
                    )
                ).strip()

                content_desc = self._value_to_text(
                    getattr(
                        child,
                        "content_desc",
                        "",
                    )
                ).strip()

                if text:
                    child_descriptions.append(
                        f"text='{text}'"
                    )

                if content_desc:
                    child_descriptions.append(
                        f"description='{content_desc}'"
                    )

            if child_descriptions:
                reasons.append(
                    "Nested UI semantics: "
                    + ", ".join(
                        child_descriptions
                    )
                )

        # --------------------------------------------------------
        # VISIBLE TEXT
        # --------------------------------------------------------

        direct_text = self._value_to_text(
            getattr(
                action,
                "text",
                "",
            )
        ).strip()

        if direct_text:
            score += 5

            reasons.append(
                "UI element has visible text."
            )

        # --------------------------------------------------------
        # CONTENT DESCRIPTION
        # --------------------------------------------------------

        content_desc = self._value_to_text(
            getattr(
                action,
                "content_desc",
                "",
            )
        ).strip()

        if content_desc:
            score += 5

            reasons.append(
                "UI element has a content description."
            )

        # --------------------------------------------------------
        # RESOURCE ID
        # --------------------------------------------------------

        resource_id = self._value_to_text(
            getattr(
                action,
                "resource_id",
                "",
            )
        ).strip()

        if resource_id:
            score += 5

            reasons.append(
                "UI element has a resource ID."
            )

        return min(score, 100), reasons

    # ============================================================
    # CORRELATION
    # ============================================================

    def correlate(self):

        evidence_text = (
            self._build_evidence_text()
        )

        evidence_tokens = self._tokens(
            evidence_text
        )

        candidates = []

        for action in self.actions:

            if action is None:
                continue

            if not getattr(
                action,
                "clickable",
                False,
            ):
                continue

            if not getattr(
                action,
                "enabled",
                False,
            ):
                continue

            score, reasons = (
                self._correlate_candidate(
                    action,
                    evidence_tokens,
                )
            )

            candidate = UIActionCandidate(
                action=action,
                score=score,
                reasons=reasons,
            )

            candidates.append(
                candidate
            )

        if not candidates:

            return UIActionCorrelationResult(
                candidate=None,
                confidence=0.0,
                score=0,
                decision="NO_ACTION",
                reasons=[
                    "No enabled clickable UI "
                    "actions were discovered."
                ],
            )

        candidates.sort(
            key=lambda item: item.score,
            reverse=True,
        )

        best = candidates[0]

        confidence = (
            best.score / 100.0
        )

        if confidence >= 0.85:
            decision = "HIGH_CONFIDENCE"

        elif confidence >= 0.70:
            decision = "MEDIUM_CONFIDENCE"

        elif confidence >= 0.50:
            decision = "LOW_CONFIDENCE"

        else:
            decision = "REJECT"

        reasons = list(
            best.reasons or []
        )

        if evidence_tokens:
            reasons.append(
                "Meaningful failure/source "
                "evidence was available."
            )
        else:
            reasons.append(
                "No meaningful textual evidence "
                "was available."
            )

        return UIActionCorrelationResult(
            candidate=best,
            confidence=confidence,
            score=best.score,
            decision=decision,
            reasons=reasons,
        )

    # ============================================================
    # RESULT DISPLAY
    # ============================================================

    @staticmethod
    def print_result(result):

        print()
        print(
            "========== UI ACTION CORRELATION =========="
        )

        if result is None:

            print(
                "Decision   : NO_RESULT"
            )

            print(
                "=========================================="
            )

            return

        print(
            "Decision   :",
            result.decision,
        )

        print(
            "Confidence :",
            f"{result.confidence:.2f}",
        )

        print(
            "Score      :",
            result.score,
        )

        if result.candidate is None:

            print(
                "UI Action  : None"
            )

        else:

            action = (
                result.candidate.action
            )

            print(
                "UI Index   :",
                getattr(
                    action,
                    "index",
                    "Unknown",
                ),
            )

            print(
                "Class      :",
                getattr(
                    action,
                    "class_name",
                    "",
                )
                or "Unknown",
            )

            print(
                "Text       :",
                getattr(
                    action,
                    "text",
                    "",
                )
                or "None",
            )

            print(
                "Bounds     :",
                getattr(
                    action,
                    "bounds",
                    "",
                )
                or "Unknown",
            )

        print()
        print("Reasons:")

        for reason in result.reasons:

            print(
                "  -",
                reason,
            )

        print(
            "=========================================="
        )


# ================================================================
# STANDALONE TEST
# ================================================================

if __name__ == "__main__":

    from modules.ui_action_discoverer import (
        UIActionDiscoverer,
    )

    print("=" * 70)
    print(
        "             UI ACTION CORRELATOR TEST"
    )
    print("=" * 70)

    discoverer = UIActionDiscoverer()

    success, actions, message = (
        discoverer.discover()
    )

    if not success:

        print(
            "❌ UI discovery failed:"
        )

        print(message)

        raise SystemExit(1)

    discoverer.print_actions(
        actions
    )

    class TestIncident:

        package = "com.example.demo"
        process = "com.example.demo"
        bug_type = "ANR"
        exception = ""
        reason = (
            "Input dispatching timed out"
        )
        thread = ""
        stack_trace = ""

        raw_log = {
            "type": "ANR",
            "reason": (
                "Input dispatching timed out"
            ),
        }

    source_context = """
    class MainActivity : ComponentActivity {

        Button(
            onClick = {
                Thread.sleep(60000)
            }
        ) {
            Text("Generate ANR")
        }
    }
    """

    evidence_text = {
        "failure": "ANR",
        "reason": (
            "Input dispatching timed out"
        ),
    }

    correlator = (
        UIActionCorrelator(
            actions=actions,
            incident=TestIncident(),
            source_context=source_context,
            evidence_text=evidence_text,
        )
    )

    result = correlator.correlate()

    correlator.print_result(
        result
    )
