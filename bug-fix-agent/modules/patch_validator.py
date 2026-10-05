import re
from pathlib import Path


class PatchValidationResult:
    """
    Result of validating an AI-generated patch.
    """

    def __init__(
        self,
        valid=False,
        reason="",
        warnings=None,
    ):
        self.valid = valid
        self.reason = reason
        self.warnings = warnings or []

    def __bool__(self):
        return self.valid

    def __str__(self):

        status = (
            "ACCEPT"
            if self.valid
            else "REJECT"
        )

        output = [
            "",
            "=" * 70,
            "                 PATCH VALIDATION",
            "=" * 70,
            "",
            f"Status : {status}",
            f"Reason : {self.reason}",
        ]

        if self.warnings:

            output.append("")
            output.append("Warnings:")

            for warning in self.warnings:

                output.append(
                    f"  - {warning}"
                )

        output.extend(
            [
                "",
                "=" * 70,
            ]
        )

        return "\n".join(output)


class PatchValidator:
    """
    Validates an AI-generated source-code patch before
    any source modification is allowed.

    This validator DOES NOT modify files.
    """

    DANGEROUS_BLOCKING_PATTERNS = [
        r"\bThread\.sleep\s*\(",
        r"\bSystemClock\.sleep\s*\(",
    ]

    # ------------------------------------------------------------
    # Symbols that may require imports.
    #
    # Exact word-boundary matching is used so:
    #
    # rememberCoroutineScope
    #
    # does NOT accidentally match:
    #
    # CoroutineScope
    # ------------------------------------------------------------

    REQUIRED_IMPORTS = {
        "rememberCoroutineScope": (
            "androidx.compose.runtime.rememberCoroutineScope"
        ),

        "launch": (
            "kotlinx.coroutines.launch"
        ),

        "delay": (
            "kotlinx.coroutines.delay"
        ),

        "withContext": (
            "kotlinx.coroutines.withContext"
        ),

        "Dispatchers": (
            "kotlinx.coroutines.Dispatchers"
        ),

        "CoroutineScope": (
            "kotlinx.coroutines.CoroutineScope"
        ),
    }

    # ============================================================
    # MAIN VALIDATION
    # ============================================================

    def validate(
        self,
        patch,
        source_path,
        failure_type="UNKNOWN",
        source_code=None,
    ):
        """
        Validate an AI-generated Patch.

        This function never modifies the source file.
        """

        # --------------------------------------------------------
        # Basic object validation
        # --------------------------------------------------------

        if patch is None:

            return PatchValidationResult(
                False,
                "Patch object is missing."
            )

        if not patch.patch_required:

            return PatchValidationResult(
                False,
                "AI did not request a patch."
            )

        old_code = (
            patch.old_code
            or ""
        )

        new_code = (
            patch.new_code
            or ""
        )

        # --------------------------------------------------------
        # Required patch fields
        # --------------------------------------------------------

        if not old_code.strip():

            return PatchValidationResult(
                False,
                "old_code is empty."
            )

        if not new_code.strip():

            return PatchValidationResult(
                False,
                "new_code is empty."
            )

        if old_code == new_code:

            return PatchValidationResult(
                False,
                "old_code and new_code are identical."
            )

        # --------------------------------------------------------
        # Root cause
        # --------------------------------------------------------

        root_cause = (
            patch.root_cause
            or ""
        ).strip()

        if not root_cause:

            return PatchValidationResult(
                False,
                "AI did not provide a root cause."
            )

        # --------------------------------------------------------
        # Source path
        # --------------------------------------------------------

        if not source_path:

            return PatchValidationResult(
                False,
                "Source path is missing."
            )

        path = Path(
            source_path
        ).resolve()

        if not path.exists():

            return PatchValidationResult(
                False,
                f"Source file does not exist: {path}"
            )

        if not path.is_file():

            return PatchValidationResult(
                False,
                f"Source path is not a file: {path}"
            )

        # --------------------------------------------------------
        # Read source
        # --------------------------------------------------------

        if source_code is None:

            try:

                source_code = path.read_text(
                    encoding="utf-8",
                    errors="ignore",
                )

            except Exception as exc:

                return PatchValidationResult(
                    False,
                    f"Unable to read source file: {exc}"
                )

        if not source_code.strip():

            return PatchValidationResult(
                False,
                "Source file is empty."
            )

        # --------------------------------------------------------
        # old_code must occur exactly once
        # --------------------------------------------------------

        occurrences = source_code.count(
            old_code
        )

        if occurrences == 0:

            return PatchValidationResult(
                False,
                "old_code was not found in the source file."
            )

        if occurrences > 1:

            return PatchValidationResult(
                False,
                (
                    "old_code occurs "
                    f"{occurrences} times in the source file. "
                    "Patch location is ambiguous."
                )
            )

        # --------------------------------------------------------
        # new_code cannot be comments only
        # --------------------------------------------------------

        if self.is_comment_only(
            new_code
        ):

            return PatchValidationResult(
                False,
                (
                    "new_code contains comments only and "
                    "is not executable source code."
                )
            )

        # --------------------------------------------------------
        # new_code must contain actual code
        # --------------------------------------------------------

        if not self.contains_code(
            new_code
        ):

            return PatchValidationResult(
                False,
                (
                    "new_code does not appear to contain "
                    "executable source code."
                )
            )

        # --------------------------------------------------------
        # Failure-specific validation
        # --------------------------------------------------------

        failure_type = (
            failure_type
            or "UNKNOWN"
        ).upper()

        warnings = []

        # --------------------------------------------------------
        # ANR-specific validation
        # --------------------------------------------------------

        if failure_type == "ANR":

            old_has_sleep = (
                re.search(
                    r"\bThread\.sleep\s*\(",
                    old_code,
                )
                is not None
                or
                re.search(
                    r"\bSystemClock\.sleep\s*\(",
                    old_code,
                )
                is not None
            )

            new_has_sleep = (
                re.search(
                    r"\bThread\.sleep\s*\(",
                    new_code,
                )
                is not None
                or
                re.search(
                    r"\bSystemClock\.sleep\s*\(",
                    new_code,
                )
                is not None
            )

            if old_has_sleep and new_has_sleep:

                warnings.append(
                    "Blocking sleep remains in the proposed replacement."
                )

                return PatchValidationResult(
                    False,
                    (
                        "The proposed ANR fix still contains "
                        "a blocking sleep operation."
                    ),
                    warnings,
                )

        # --------------------------------------------------------
        # Dangerous blocking operations
        # --------------------------------------------------------

        dangerous_found = (
            self.find_dangerous_operations(
                new_code
            )
        )

        if dangerous_found:

            warnings.extend(
                [
                    "Potential blocking operation in new_code: "
                    + operation
                    for operation in dangerous_found
                ]
            )

            if failure_type == "ANR":

                return PatchValidationResult(
                    False,
                    (
                        "Potential blocking operation remains "
                        "in the ANR patch."
                    ),
                    warnings,
                )

        # --------------------------------------------------------
        # Import validation
        #
        # Missing imports are now HARD failures.
        # --------------------------------------------------------

        import_errors = (
            self.check_required_imports(
                source_code,
                new_code,
            )
        )

        if import_errors:

            return PatchValidationResult(
                False,
                (
                    "The proposed patch uses symbols whose "
                    "required imports are missing."
                ),
                import_errors,
            )

        # --------------------------------------------------------
        # Patch size sanity check
        # --------------------------------------------------------

        if len(new_code) > max(
            len(old_code) * 20,
            5000,
        ):

            warnings.append(
                "new_code is disproportionately larger than old_code."
            )

        # --------------------------------------------------------
        # Validate the complete resulting source
        #
        # This is intentionally performed on the full source after
        # replacement. Valid-looking new_code can still create
        # invalid surrounding syntax.
        # --------------------------------------------------------

        patched_source = source_code.replace(
            old_code,
            new_code,
            1,
        )

        structure_valid, structure_reason = (
            self.validate_source_structure(
                patched_source
            )
        )

        if not structure_valid:

            return PatchValidationResult(
                False,
                (
                    "Patched source failed structural "
                    "syntax validation: "
                    + structure_reason
                ),
                warnings,
            )

        # --------------------------------------------------------
        # Final acceptance
        # --------------------------------------------------------

        return PatchValidationResult(
            True,
            "Patch passed safety and source-structure validation.",
            warnings,
        )

    # ============================================================
    # SOURCE STRUCTURE VALIDATION
    # ============================================================

    @staticmethod
    def validate_source_structure(
        text,
    ):
        """
        Perform a language-neutral structural validation of source code.

        This intentionally does not try to fully compile the source.
        It catches malformed AI replacements such as:

            class Foo {
                ...
            }
            }

        and other problems involving:

        - unmatched {}
        - unmatched ()
        - unmatched []
        - mismatched closing delimiters
        - unterminated block comments
        - unterminated string literals
        - unterminated character literals

        The scanner understands:
        - // comments
        - /* ... */ comments
        - quoted strings
        - character literals
        - Kotlin triple-quoted strings
        """

        if not isinstance(text, str):
            return False, "Source is not text."

        stack = []

        pairs = {
            "}": "{",
            ")": "(",
            "]": "[",
        }

        opening = {
            "{",
            "(",
            "[",
        }

        i = 0
        length = len(text)

        in_line_comment = False
        in_block_comment = False
        in_string = False
        in_char = False
        in_triple_string = False

        while i < length:

            ch = text[i]
            nxt = (
                text[i + 1]
                if i + 1 < length
                else ""
            )

            # ----------------------------------------------------
            # Line comment
            # ----------------------------------------------------

            if in_line_comment:

                if ch == "\n":
                    in_line_comment = False

                i += 1
                continue

            # ----------------------------------------------------
            # Block comment
            # ----------------------------------------------------

            if in_block_comment:

                if ch == "*" and nxt == "/":
                    in_block_comment = False
                    i += 2
                    continue

                i += 1
                continue

            # ----------------------------------------------------
            # Kotlin triple-quoted string
            # ----------------------------------------------------

            if in_triple_string:

                if (
                    ch == '"'
                    and text[i:i + 3] == '"""'
                ):
                    in_triple_string = False
                    i += 3
                    continue

                i += 1
                continue

            # ----------------------------------------------------
            # Normal string
            # ----------------------------------------------------

            if in_string:

                if ch == "\\":
                    # Skip escaped character.
                    i += 2
                    continue

                if ch == '"':
                    in_string = False

                i += 1
                continue

            # ----------------------------------------------------
            # Character literal
            # ----------------------------------------------------

            if in_char:

                if ch == "\\":
                    # Skip escaped character.
                    i += 2
                    continue

                if ch == "'":
                    in_char = False

                i += 1
                continue

            # ----------------------------------------------------
            # Start comments
            # ----------------------------------------------------

            if ch == "/" and nxt == "/":
                in_line_comment = True
                i += 2
                continue

            if ch == "/" and nxt == "*":
                in_block_comment = True
                i += 2
                continue

            # ----------------------------------------------------
            # Start strings
            # ----------------------------------------------------

            if (
                ch == '"'
                and text[i:i + 3] == '"""'
            ):
                in_triple_string = True
                i += 3
                continue

            if ch == '"':
                in_string = True
                i += 1
                continue

            # ----------------------------------------------------
            # Start character literal
            # ----------------------------------------------------

            if ch == "'":
                in_char = True
                i += 1
                continue

            # ----------------------------------------------------
            # Opening delimiters
            # ----------------------------------------------------

            if ch in opening:
                stack.append(ch)
                i += 1
                continue

            # ----------------------------------------------------
            # Closing delimiters
            # ----------------------------------------------------

            if ch in pairs:

                if not stack:
                    return (
                        False,
                        (
                            "Unexpected closing delimiter "
                            f"'{ch}'."
                        ),
                    )

                expected = pairs[ch]
                actual = stack[-1]

                if actual != expected:
                    return (
                        False,
                        (
                            "Mismatched delimiter: "
                            f"found '{ch}' but expected "
                            f"closing delimiter for '{actual}'."
                        ),
                    )

                stack.pop()

            i += 1

        # --------------------------------------------------------
        # Unterminated lexical constructs
        # --------------------------------------------------------

        if in_block_comment:
            return (
                False,
                "Unterminated block comment."
            )

        if in_string:
            return (
                False,
                "Unterminated string literal."
            )

        if in_triple_string:
            return (
                False,
                "Unterminated triple-quoted string literal."
            )

        if in_char:
            return (
                False,
                "Unterminated character literal."
            )

        # --------------------------------------------------------
        # Remaining opening delimiters
        # --------------------------------------------------------

        if stack:

            return (
                False,
                (
                    "Unclosed delimiter(s): "
                    + ", ".join(stack)
                    + "."
                ),
            )

        return True, "Source structure is valid."

    # ============================================================
    # COMMENT CHECK
    # ============================================================

    @staticmethod
    def is_comment_only(
        text,
    ):

        lines = text.splitlines()

        meaningful = []

        block_comment = False

        for line in lines:

            stripped = line.strip()

            if not stripped:
                continue

            if block_comment:

                if "*/" in stripped:
                    block_comment = False

                continue

            if stripped.startswith(
                "/*"
            ):

                if "*/" not in stripped:
                    block_comment = True

                continue

            if stripped.startswith(
                "//"
            ):
                continue

            if stripped.startswith(
                "#"
            ):
                continue

            if stripped.startswith(
                "*"
            ):
                continue

            meaningful.append(
                stripped
            )

        return len(
            meaningful
        ) == 0

    # ============================================================
    # EXECUTABLE CODE CHECK
    # ============================================================

    @staticmethod
    def contains_code(
        text,
    ):

        lines = text.splitlines()

        block_comment = False

        for line in lines:

            stripped = line.strip()

            if not stripped:
                continue

            if block_comment:

                if "*/" in stripped:
                    block_comment = False

                continue

            if stripped.startswith(
                "/*"
            ):

                if "*/" not in stripped:
                    block_comment = True

                continue

            if stripped.startswith(
                "//"
            ):
                continue

            if stripped.startswith(
                "#"
            ):
                continue

            if stripped.startswith(
                "*"
            ):
                continue

            return True

        return False

    # ============================================================
    # DANGEROUS OPERATIONS
    # ============================================================

    def find_dangerous_operations(
        self,
        text,
    ):

        found = []

        for pattern in (
            self.DANGEROUS_BLOCKING_PATTERNS
        ):

            if re.search(
                pattern,
                text,
                re.IGNORECASE,
            ):

                found.append(
                    pattern
                )

        return found

    # ============================================================
    # IMPORT VALIDATION
    # ============================================================

    @classmethod
    def check_required_imports(
        cls,
        source_code,
        new_code,
    ):

        errors = []

        for symbol, import_name in (
            cls.REQUIRED_IMPORTS.items()
        ):

            # ----------------------------------------------------
            # Use a real identifier boundary.
            #
            # This prevents:
            #
            # CoroutineScope
            #
            # from matching:
            #
            # rememberCoroutineScope
            # ----------------------------------------------------

            symbol_pattern = (
                r"(?<![A-Za-z0-9_])"
                + re.escape(symbol)
                + r"(?![A-Za-z0-9_])"
            )

            if not re.search(
                symbol_pattern,
                new_code,
            ):
                continue

            # ----------------------------------------------------
            # Already imported in source
            # ----------------------------------------------------

            import_pattern = (
                r"^\s*import\s+"
                + re.escape(import_name)
                + r"\s*$"
            )

            if re.search(
                import_pattern,
                source_code,
                re.MULTILINE,
            ):
                continue

            # ----------------------------------------------------
            # Fully qualified reference in patch
            # ----------------------------------------------------

            if import_name in new_code:
                continue

            errors.append(
                (
                    f"new_code uses {symbol} but "
                    f"{import_name} is not imported."
                )
            )

        return errors


# ================================================================
# MANUAL TESTS
# ================================================================

if __name__ == "__main__":

    from modules.patch import Patch

    validator = PatchValidator()

    source = """
package com.example.demo

import androidx.compose.runtime.Composable

@Composable
fun ANRScreen() {

    Button(
        onClick = {
            Thread.sleep(60000)
        }
    ) {
        Text("Generate ANR")
    }
}
"""

    # ------------------------------------------------------------
    # TEST 1
    # Comment-only patch
    # ------------------------------------------------------------

    print()
    print("TEST 1: COMMENT-ONLY PATCH")

    bad_patch = Patch(
        root_cause=(
            "Thread.sleep blocks the UI thread."
        ),
        confidence="High",
        can_reproduce=True,
        patch_required=True,
        old_code="Thread.sleep(60000)",
        new_code=(
            "// Move this operation to a background thread."
        ),
        explanation="Test patch.",
        tests=[],
    )

    result = validator.validate(
        bad_patch,
        source_path=__file__,
        failure_type="ANR",
        source_code=source,
    )

    print(result)

    # ------------------------------------------------------------
    # TEST 2
    # Blocking sleep remains
    # ------------------------------------------------------------

    print()
    print("TEST 2: BLOCKING SLEEP REMAINS")

    unsafe_patch = Patch(
        root_cause=(
            "Thread.sleep blocks the UI thread."
        ),
        confidence="High",
        can_reproduce=True,
        patch_required=True,
        old_code="Thread.sleep(60000)",
        new_code=(
            "scope.launch {\n"
            "    Thread.sleep(60000)\n"
            "}"
        ),
        explanation="Test patch.",
        tests=[],
    )

    result = validator.validate(
        unsafe_patch,
        source_path=__file__,
        failure_type="ANR",
        source_code=source,
    )

    print(result)

    # ------------------------------------------------------------
    # TEST 3
    # Missing imports
    # ------------------------------------------------------------

    print()
    print("TEST 3: MISSING IMPORTS")

    coroutine_patch = Patch(
        root_cause=(
            "Thread.sleep blocks the UI thread."
        ),
        confidence="High",
        can_reproduce=True,
        patch_required=True,
        old_code="Thread.sleep(60000)",
        new_code=(
            "val scope = rememberCoroutineScope()\n"
            "\n"
            "scope.launch {\n"
            "    delay(60000)\n"
            "}"
        ),
        explanation="Test patch.",
        tests=[],
    )

    result = validator.validate(
        coroutine_patch,
        source_path=__file__,
        failure_type="ANR",
        source_code=source,
    )

    print(result)

    # ------------------------------------------------------------
    # TEST 4
    # Correct imports
    # ------------------------------------------------------------

    print()
    print("TEST 4: CORRECT IMPORTS")

    source_with_imports = """
package com.example.demo

import androidx.compose.runtime.Composable
import androidx.compose.runtime.rememberCoroutineScope
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch

@Composable
fun ANRScreen() {

    Button(
        onClick = {
            Thread.sleep(60000)
        }
    ) {
        Text("Generate ANR")
    }
}
"""

    result = validator.validate(
        coroutine_patch,
        source_path=__file__,
        failure_type="ANR",
        source_code=source_with_imports,
    )

    print(result)
