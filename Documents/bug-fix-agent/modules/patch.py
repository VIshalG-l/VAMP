from dataclasses import dataclass, field
from typing import List


@dataclass
class Patch:
    """
    Represents an AI-generated Root Cause Analysis
    and optional source code patch.
    """

    # -----------------------------
    # RCA
    # -----------------------------
    root_cause: str = ""
    confidence: str = "Unknown"
    can_reproduce: bool = False
    patch_required: bool = False

    # -----------------------------
    # Patch
    # -----------------------------
    old_code: str = ""
    new_code: str = ""

    # -----------------------------
    # Explanation
    # -----------------------------
    explanation: str = ""

    # -----------------------------
    # Suggested validation tests
    # -----------------------------
    tests: List[str] = field(default_factory=list)

    def has_patch(self):
        """
        Returns True only if a valid patch exists.
        """

        return (
            self.patch_required
            and self.old_code.strip() != ""
            and self.new_code.strip() != ""
            and self.old_code != self.new_code
        )

    def summary(self):
        """
        Short summary.
        """

        return (
            f"Root Cause      : {self.root_cause}\n"
            f"Confidence      : {self.confidence}\n"
            f"Patch Required  : {self.patch_required}\n"
            f"Can Reproduce   : {self.can_reproduce}"
        )

    def __str__(self):

        output = f"""
==============================
AI ROOT CAUSE ANALYSIS
==============================

Root Cause:
{self.root_cause}

Confidence:
{self.confidence}

Can Reproduce:
{self.can_reproduce}

Patch Required:
{self.patch_required}
"""

        if self.has_patch():

            output += f"""

==============================
GENERATED PATCH
==============================

Old Code:
{self.old_code}

New Code:
{self.new_code}
"""

        output += f"""

==============================
EXPLANATION
==============================

{self.explanation}
"""

        if self.tests:

            output += "\n==============================\n"
            output += "RECOMMENDED TESTS\n"
            output += "==============================\n\n"

            for test in self.tests:
                output += f"• {test}\n"

        return output
