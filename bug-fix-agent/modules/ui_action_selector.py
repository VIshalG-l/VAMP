from dataclasses import dataclass
from typing import List, Optional

from modules.ui_action_discoverer import UIAction


@dataclass
class UIActionCandidate:
    action: UIAction
    score: int
    reasons: List[str]


class UIActionSelector:
    """
    Generic UI action candidate selector.

    The selector does not know:
        - a specific package
        - a specific APK
        - a specific button name
        - a specific activity
        - a specific project path

    It uses runtime UI information plus optional failure/source
    evidence to rank possible actions.
    """

    def __init__(
        self,
        actions: Optional[List[UIAction]] = None,
        evidence_text: str = "",
        source_context: str = "",
        incident_reason: str = "",
    ):
        self.actions = actions or []

        self.evidence_text = (
            evidence_text or ""
        ).lower()

        self.source_context = (
            source_context or ""
        ).lower()

        self.incident_reason = (
            incident_reason or ""
        ).lower()

    @staticmethod
    def _combined_text(action: UIAction):
        return " ".join(
            [
                action.text or "",
                action.content_desc or "",
                action.resource_id or "",
                action.class_name or "",
            ]
        ).lower()

    @staticmethod
    def _is_clickable(action: UIAction):
        return bool(
            action.clickable
            and action.enabled
        )

    @staticmethod
    def _is_valid_bounds(action: UIAction):
        return bool(
            action.bounds
            and action.bounds.startswith("[")
        )

    def _score_action(self, action: UIAction):
        """
        Assign a generic confidence score.

        Higher score means the element is a stronger candidate
        for an executable UI action.
        """

        score = 0
        reasons = []

        if not self._is_clickable(action):
            return (
                -1000,
                ["Not clickable."]
            )

        if not action.enabled:
            return (
                -1000,
                ["Disabled UI element."]
            )

        score += 50
        reasons.append(
            "Element is clickable and enabled."
        )

        if self._is_valid_bounds(action):
            score += 20
            reasons.append(
                "Element has valid screen bounds."
            )

        combined = self._combined_text(
            action
        )

        if action.text:
            score += 10
            reasons.append(
                "Element has visible text."
            )

        if action.content_desc:
            score += 10
            reasons.append(
                "Element has content description."
            )

        if action.resource_id:
            score += 5
            reasons.append(
                "Element has a resource ID."
            )

        # Evidence correlation.
        #
        # We deliberately use complete tokens rather than
        # hard-coded application-specific strings.
        evidence_sources = [
            self.evidence_text,
            self.source_context,
            self.incident_reason,
        ]

        for evidence in evidence_sources:
            if not evidence:
                continue

            text_tokens = self._tokens(combined)
            evidence_tokens = self._tokens(
                evidence
            )

            overlap = (
                text_tokens
                & evidence_tokens
            )

            if overlap:
                score += min(
                    len(overlap) * 5,
                    20,
                )

                reasons.append(
                    "UI metadata correlates with "
                    "failure/source evidence."
                )

        return score, reasons

    @staticmethod
    def _tokens(text):
        """
        Convert text into simple normalized tokens.

        This is intentionally lightweight and does not depend
        on an NLP package.
        """

        if not text:
            return set()

        separators = (
            " ",
            "\n",
            "\t",
            "_",
            "-",
            "/",
            ":",
            ".",
            "(",
            ")",
            "[",
            "]",
            "{",
            "}",
        )

        normalized = text.lower()

        for separator in separators:
            normalized = normalized.replace(
                separator,
                " ",
            )

        tokens = {
            token.strip()
            for token in normalized.split()
            if len(token.strip()) >= 3
        }

        return tokens

    def rank_candidates(self):
        """
        Rank only genuinely clickable/enabled UI elements.
        """

        candidates = []

        for action in self.actions:

            score, reasons = (
                self._score_action(action)
            )

            if score < 0:
                continue

            candidates.append(
                UIActionCandidate(
                    action=action,
                    score=score,
                    reasons=reasons,
                )
            )

        candidates.sort(
            key=lambda candidate: (
                candidate.score,
                candidate.action.index,
            ),
            reverse=True,
        )

        return candidates

    def select_best_candidate(self):
        """
        Return the highest-ranked executable UI action.

        Returns:
            UIActionCandidate or None
        """

        candidates = (
            self.rank_candidates()
        )

        if not candidates:
            return None

        return candidates[0]

    @staticmethod
    def print_candidates(candidates):
        print()
        print(
            "========== UI ACTION CANDIDATES =========="
        )

        if not candidates:
            print(
                "No executable UI candidates found."
            )
            print(
                "=========================================="
            )
            return

        for position, candidate in enumerate(
            candidates,
            start=1,
        ):
            action = candidate.action

            print()
            print(
                f"[Candidate {position}]"
            )

            print(
                "  UI Index    :",
                action.index,
            )

            print(
                "  Score       :",
                candidate.score,
            )

            print(
                "  Class       :",
                action.class_name
                or "Unknown",
            )

            print(
                "  Text        :",
                action.text
                or "None",
            )

            print(
                "  Description :",
                action.content_desc
                or "None",
            )

            print(
                "  Resource ID :",
                action.resource_id
                or "None",
            )

            print(
                "  Bounds      :",
                action.bounds
                or "Unknown",
            )

            print(
                "  Reasons:"
            )

            for reason in candidate.reasons:
                print(
                    "    -",
                    reason,
                )

        print()
        print(
            "=========================================="
        )

    @staticmethod
    def print_selection(candidate):
        print()
        print(
            "========== SELECTED UI ACTION =========="
        )

        if candidate is None:
            print(
                "No suitable UI action selected."
            )
            print(
                "========================================"
            )
            return

        action = candidate.action

        print(
            "UI Index    :",
            action.index,
        )

        print(
            "Score       :",
            candidate.score,
        )

        print(
            "Class       :",
            action.class_name
            or "Unknown",
        )

        print(
            "Text        :",
            action.text
            or "None",
        )

        print(
            "Description :",
            action.content_desc
            or "None",
        )

        print(
            "Resource ID :",
            action.resource_id
            or "None",
        )

        print(
            "Bounds      :",
            action.bounds
            or "Unknown",
        )

        print(
            "========================================"
        )


if __name__ == "__main__":

    print()
    print("=" * 70)
    print("             GENERIC UI ACTION SELECTOR")
    print("=" * 70)

    from modules.ui_action_discoverer import (
        UIActionDiscoverer,
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
            "❌ Unable to discover UI actions."
        )
        raise SystemExit(1)

    selector = UIActionSelector(
        actions=actions,
        evidence_text="",
        source_context="",
        incident_reason="",
    )

    candidates = (
        selector.rank_candidates()
    )

    selector.print_candidates(
        candidates
    )

    best = (
        selector.select_best_candidate()
    )

    selector.print_selection(
        best
    )

    print()

    if best is None:
        print(
            "Selection Status : NO ACTION"
        )
    else:
        print(
            "Selection Status : SUCCESS"
        )
