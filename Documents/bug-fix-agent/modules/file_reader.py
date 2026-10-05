from pathlib import Path
import re


def _format_lines(lines, start, end, highlight=None):
    """
    Format source code with line numbers.
    """

    output = []

    for i in range(start, end):

        marker = ">>> " if highlight == (i + 1) else "    "

        output.append(
            f"{marker}{i + 1:4}: {lines[i].rstrip()}"
        )

    return "\n".join(output)


def _extract_by_line(lines, error_line, context=25):
    """
    Extract code around the error line.
    """

    start = max(0, error_line - context - 1)
    end = min(len(lines), error_line + context)

    return _format_lines(
        lines,
        start,
        end,
        highlight=error_line
    )


def _extract_by_method(lines, method):
    """
    Locate Java or Kotlin method.
    """

    patterns = [

        rf"\bfun\s+{re.escape(method)}\b",

        rf"\b(public|private|protected)?\s*"
        rf"(static\s+)?"
        rf"[\w<>\[\]]+\s+"
        rf"{re.escape(method)}\s*\(",
    ]

    for pattern in patterns:

        regex = re.compile(pattern)

        for index, line in enumerate(lines):

            if regex.search(line):

                start = max(0, index - 25)
                end = min(len(lines), index + 100)

                return _format_lines(
                    lines,
                    start,
                    end,
                    highlight=index + 1
                )

    return None


def read_context(
    file_path,
    error_line=None,
    method=None,
    context=25,
):
    """
    Read source context for AI analysis.

    Priority

    1. Crash line
    2. Method
    3. Beginning of file
    """

    path = Path(file_path)

    with open(
        path,
        encoding="utf-8",
        errors="ignore",
    ) as f:

        lines = f.readlines()

    full_code = "".join(lines)

    snippet = ""

    #
    # Crash
    #

    if error_line and error_line <= len(lines):

        snippet = _extract_by_line(
            lines,
            error_line,
            context,
        )

    #
    # Method
    #

    elif method:

        snippet = _extract_by_method(
            lines,
            method,
        )

    #
    # Fallback
    #

    if not snippet:

        snippet = _format_lines(
            lines,
            0,
            min(200, len(lines)),
        )

    print("\n========== SOURCE CONTEXT ==========")
    print(snippet)
    print("====================================\n")

    return {

        "file": path.name,

        "path": str(path.resolve()),

        "code": full_code,

        "snippet": snippet,

        "total_lines": len(lines),
    }
