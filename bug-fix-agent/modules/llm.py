import json
import os
import re
import time

import requests

from config import GEMINI_API_KEY
from modules.patch import Patch


# ============================================================
# PROVIDER CONFIGURATION
# ============================================================

# ------------------------------------------------------------
# GEMINI
# ------------------------------------------------------------

MODEL = "gemini-2.5-flash"

URL = (
    "https://generativelanguage.googleapis.com/"
    "v1beta/models/"
    + MODEL
    + ":generateContent"
)


# ------------------------------------------------------------
# GROQ
# ------------------------------------------------------------

GROQ_API_KEY = os.getenv(
    "GROQ_API_KEY",
    ""
).strip()

GROQ_MODEL = "openai/gpt-oss-120b"

GROQ_URL = (
    "https://api.groq.com/openai/v1/chat/completions"
)


# ------------------------------------------------------------
# OPENROUTER
# ------------------------------------------------------------

OPENROUTER_API_KEY = os.getenv(
    "OPENROUTER_API_KEY",
    ""
).strip()

OPENROUTER_MODEL = "openrouter/free"

OPENROUTER_URL = (
    "https://openrouter.ai/api/v1/chat/completions"
)


# ============================================================
# CONTEXT LIMITS
# ============================================================

# Character limits are deliberately conservative.
#
# Roughly:
#
# 4 characters ~= 1 token
#
# We therefore keep cloud prompts comfortably below
# the 8K-token Groq TPM limit encountered earlier.

CLOUD_LOG_LIMIT = 9000
CLOUD_SOURCE_LIMIT = 11000

STACK_LIMIT = 8000

MAX_SOURCE_FILES = 3


# ============================================================
# RESPONSE SCHEMA
# ============================================================

response_schema = {
    "type": "object",
    "properties": {
        "root_cause": {
            "type": "string"
        },
        "explanation": {
            "type": "string"
        },
        "patch_required": {
            "type": "boolean"
        },
        "old_code": {
            "type": "string"
        },
        "new_code": {
            "type": "string"
        },
        "confidence": {
            "type": "string"
        },
        "can_reproduce": {
            "type": "boolean"
        },
        "tests": {
            "type": "array",
            "items": {
                "type": "string"
            }
        }
    },
    "required": [
        "root_cause",
        "explanation",
        "patch_required",
        "old_code",
        "new_code",
        "confidence",
        "can_reproduce",
        "tests"
    ]
}


# ============================================================
# PATCH QUALITY / AI RETRY HELPERS
# ============================================================

def _is_comment_only_code(value):
    """
    Return True when a proposed source replacement contains
    only comments/whitespace and therefore cannot be executable
    source code.

    This is intentionally conservative. It does NOT replace
    PatchValidator; it only prevents obviously unusable AI
    responses from being accepted by the LLM layer.
    """

    if not isinstance(value, str):
        return True

    text = value.strip()

    if not text:
        return True

    lines = []

    for line in text.splitlines():

        stripped = line.strip()

        if not stripped:
            continue

        if stripped.startswith("//"):
            continue

        if stripped.startswith("/*") and stripped.endswith("*/"):
            continue

        if stripped.startswith("*") and stripped.endswith("*/"):
            continue

        if stripped.startswith("#") and (
            stripped.startswith("# ")
            or stripped.startswith("#pragma")
            or stripped.startswith("#include")
            or stripped.startswith("#define")
        ):
            lines.append(stripped)
            continue

        lines.append(stripped)

    if not lines:
        return True

    return False


def _patch_response_needs_retry(result):
    """
    Determine whether an otherwise valid LLM response needs
    another attempt because the model requested a patch but
    did not provide executable replacement code.
    """

    if not isinstance(result, dict):
        return False

    if not result.get("patch_required"):
        return False

    old_code = str(
        result.get("old_code") or ""
    ).strip()

    new_code = str(
        result.get("new_code") or ""
    ).strip()

    if not old_code:
        return True

    if not new_code:
        return True

    if old_code == new_code:
        return True

    if _is_comment_only_code(new_code):
        return True

    return False


def _build_patch_repair_prompt(
    original_prompt,
    previous_result,
):
    """
    Ask the same provider to repair an incomplete patch response.

    The original source/evidence remains unchanged. The model is
    explicitly told that new_code must contain executable source,
    not an explanation or comment.
    """

    old_code = str(
        previous_result.get("old_code") or ""
    )

    new_code = str(
        previous_result.get("new_code") or ""
    )

    failure = str(
        previous_result.get("root_cause") or ""
    )

    return f"""
{original_prompt}

============================================================
PATCH REPAIR RETRY
============================================================

Your previous response requested a source patch, but the patch
was incomplete or unusable.

Root cause from your previous response:
{failure}

Previous old_code:
{old_code}

Previous new_code:
{new_code}

You MUST correct the patch response now.

IMPORTANT:

- new_code MUST contain actual executable source code.
- new_code MUST NOT contain only comments.
- new_code MUST NOT contain an explanation.
- new_code MUST NOT contain markdown fences.
- new_code MUST NOT contain "before/after" labels.
- new_code MUST NOT contain ellipses.
- new_code MUST NOT contain pseudo-code.
- new_code MUST be the complete replacement for old_code.
- old_code MUST exist exactly in the supplied SOURCE CONTEXT.
- old_code and new_code MUST be different.
- For native crashes, C/C++/JNI source is valid source code.
- Preserve required surrounding syntax.
- Keep the change minimal.
- Do not invent APIs, variables, methods, files, or behavior.

If a safe executable patch can be produced, set:

patch_required = true

and provide the actual executable replacement in new_code.

If a safe executable patch cannot be produced from the supplied
source, set:

patch_required = false

and set old_code and new_code to empty strings.

Return ONLY valid JSON matching the required schema.
""".strip()


def _compact_ai_log_for_patch(log_text):
    """
    Remove high-volume Android framework/UI noise from the AI
    prompt while preserving the original evidence elsewhere.

    This is only prompt compaction. It does not modify raw
    logcat or stored evidence.
    """

    if not isinstance(log_text, str):
        return str(log_text or "")

    noise_markers = (
        "FrameTracker:",
        "jankTypeLegacy:",
        "jankTypeExperimental:",
        "CUJ=",
        "AiSealSystemService:",
        "SplashScreen:",
        "SurfaceControl:",
        "Choreographer:",
        "OpenGLRenderer:",
    )

    important_markers = (
        "FATAL EXCEPTION",
        "Fatal signal",
        "SIGSEGV",
        "SIGABRT",
        "SIGBUS",
        "Abort message",
        "backtrace",
        "ANR in ",
        "Input dispatching timed out",
        "Process:",
        "PID:",
        "Exception",
        "Caused by:",
        "native crash",
        "NATIVE_CRASH",
    )

    lines = log_text.splitlines()

    important = []
    surrounding = []

    for index, line in enumerate(lines):

        stripped = line.strip()

        if not stripped:
            continue

        if any(
            marker in line
            for marker in important_markers
        ):
            important.append(line)

            start = max(0, index - 2)
            end = min(len(lines), index + 3)

            surrounding.extend(
                lines[start:end]
            )

            continue

        if any(
            marker in line
            for marker in noise_markers
        ):
            continue

        # Preserve normal application/runtime evidence.
        surrounding.append(line)

    ordered = []

    for line in important + surrounding:

        if line not in ordered:
            ordered.append(line)

    return "\n".join(ordered).strip()



# ============================================================
# MAIN LLM FUNCTION
# ============================================================

def ask_llm(data):

    if not isinstance(data, dict):
        raise ValueError(
            "LLM input must be a dictionary."
        )

    log_text = (
        data.get("log")
        or data.get("logs")
        or data.get("evidence")
        or ""
    )

    source_text = (
        data.get("source")
        or data.get("source_text")
        or ""
    )

    # --------------------------------------------------------
    # Normalize evidence.
    # --------------------------------------------------------

    if isinstance(log_text, dict):

        log_text = json.dumps(
            log_text,
            indent=2,
            ensure_ascii=False
        )

    elif not isinstance(log_text, str):

        log_text = str(log_text)

    if isinstance(source_text, dict):

        source_text = json.dumps(
            source_text,
            indent=2,
            ensure_ascii=False
        )

    elif not isinstance(source_text, str):

        source_text = str(source_text)

    if not log_text.strip():

        raise ValueError(
            "Failure log/evidence is missing."
        )

    if not source_text.strip():

        raise ValueError(
            "Source context is missing."
        )

    # --------------------------------------------------------
    # Determine whether this is a patch-oriented request.
    # --------------------------------------------------------

    compact_log = compact_evidence(
        log_text,
        CLOUD_LOG_LIMIT
    )

    # Remove only low-value Android/system noise from the AI
    # prompt. Raw evidence/logcat remains unchanged.
    compact_log = _compact_ai_log_for_patch(
        compact_log
    )

    compact_source = compact_source_context(
        source_text,
        CLOUD_SOURCE_LIMIT
    )

    prompt = build_prompt(
        data,
        compact_log,
        compact_source
    )

    # --------------------------------------------------------
    # Provider chain.
    #
    # CLOUD PROVIDERS:
    # Gemini -> Groq -> OpenRouter
    #
    # Providers are tried in this order. If one fails,
    # VAMP automatically tries the next configured provider.
    # --------------------------------------------------------

    providers = []

    if GEMINI_API_KEY:

        providers.append(
            (
                "GEMINI",
                lambda p: _send_gemini_request_wrapper(p)
            )
        )

    if GROQ_API_KEY:

        providers.append(
            (
                "GROQ",
                lambda p: _send_groq_request(p)
            )
        )

    if OPENROUTER_API_KEY:

        providers.append(
            (
                "OPENROUTER",
                lambda p: _send_openrouter_request(p)
            )
        )

    if not providers:

        raise RuntimeError(
            "No AI providers are configured."
        )

    errors = []

    for provider_name, provider_function in providers:

        print(
            f"\n→ Trying AI provider: "
            f"{provider_name}"
        )

        provider_prompt = prompt

        # One repair retry is allowed for an incomplete patch.
        for attempt in range(2):

            try:

                if attempt == 1:

                    print(
                        f"  ↻ {provider_name}: "
                        "requesting executable patch repair..."
                    )

                raw_response = provider_function(
                    provider_prompt
                )

                parsed = parse_llm_response(
                    raw_response
                )

                # Check patch completeness before strict validation.
                # This lets us retry the same provider instead of
                # immediately abandoning it.
                if _patch_response_needs_retry(
                    parsed
                ):

                    if attempt == 0:

                        print(
                            f"  ⚠ {provider_name}: "
                            "patch requested but executable "
                            "new_code is missing/incomplete."
                        )

                        provider_prompt = (
                            _build_patch_repair_prompt(
                                prompt,
                                parsed
                            )
                        )

                        continue

                    raise RuntimeError(
                        f"{provider_name} returned an "
                        "incomplete executable patch after retry."
                    )

                validated = validate_llm_result(
                    parsed
                )

                if validated:

                    print(
                        f"✓ AI provider succeeded: "
                        f"{provider_name}"
                    )

                    patch = Patch(
                        root_cause=validated.get(
                            "root_cause",
                            ""
                        ),
                        explanation=validated.get(
                            "explanation",
                            ""
                        ),
                        patch_required=validated.get(
                            "patch_required",
                            False
                        ),
                        old_code=validated.get(
                            "old_code",
                            ""
                        ),
                        new_code=validated.get(
                            "new_code",
                            ""
                        ),
                        confidence=validated.get(
                            "confidence",
                            "Unknown"
                        ),
                        can_reproduce=validated.get(
                            "can_reproduce",
                            False
                        ),
                        tests=validated.get(
                            "tests",
                            []
                        )
                    )

                    return patch

                raise RuntimeError(
                    "LLM response failed validation."
                )

            except Exception as exc:

                message = str(exc)

                # If this was the first attempt and the response
                # itself was incomplete, the retry logic above
                # handles it. Other errors go to the next provider.
                if attempt == 0:

                    errors.append(
                        f"{provider_name}: {message}"
                    )

                    print(
                        f"\n⚠ {provider_name} failed:"
                    )

                    print(
                        f"  {message}"
                    )

                    break

                errors.append(
                    f"{provider_name} retry: {message}"
                )

                print(
                    f"\n⚠ {provider_name} retry failed:"
                )

                print(
                    f"  {message}"
                )

                break

    # --------------------------------------------------------
    # Final failure.
    # --------------------------------------------------------

    raise RuntimeError(
        "All configured AI providers failed.\n"
        + "\n".join(errors)
    )


# ============================================================
# EVIDENCE COMPACTION
# ============================================================

def compact_evidence(
    text,
    max_chars
):

    if not text:

        return ""

    text = str(text)

    if len(text) <= max_chars:

        return text

    lines = text.splitlines()

    priority = []

    normal = []

    for line in lines:

        stripped = line.strip()

        if not stripped:
            continue

        lower = stripped.lower()

        important = False

        keywords = [
            "fatal exception",
            "androidruntime",
            "exception",
            "caused by",
            "at ",
            "process:",
            "anr in",
            "input dispatching timed out",
            "signal",
            "sigsegv",
            "native crash",
            "runtimeexception",
            "nullpointerexception",
            "illegalstateexception",
            "crash",
            "error",
            "exception message",
            "activity",
            "package"
        ]

        for keyword in keywords:

            if keyword in lower:

                important = True
                break

        if important:

            priority.append(
                stripped
            )

        else:

            normal.append(
                stripped
            )

    result = []

    used = 0

    # --------------------------------------------------------
    # Priority lines first.
    # --------------------------------------------------------

    for line in priority:

        if used + len(line) + 1 > max_chars:

            break

        result.append(line)

        used += len(line) + 1

    # --------------------------------------------------------
    # Add normal lines if space remains.
    # --------------------------------------------------------

    for line in normal:

        if used + len(line) + 1 > max_chars:

            break

        result.append(line)

        used += len(line) + 1

    if len(result) < len(lines):

        result.append(
            "\n[Evidence truncated by VAMP "
            "to protect LLM context size.]"
        )

    return "\n".join(result)


# ============================================================
# SOURCE COMPACTION
# ============================================================

def compact_source_context(
    source_text,
    max_chars
):

    if not source_text:

        return ""

    source_text = str(source_text)

    # --------------------------------------------------------
    # If source is already small, preserve it completely.
    # --------------------------------------------------------

    if len(source_text) <= max_chars:

        return source_text

    lines = source_text.splitlines()

    # --------------------------------------------------------
    # Detect source files/sections.
    # --------------------------------------------------------

    sections = []

    current_name = None
    current_lines = []

    for line in lines:

        # Common markers generated by VAMP source readers.
        marker = re.match(
            r"^\s*(?:FILE|SOURCE FILE|File)\s*[:=]\s*(.+)$",
            line,
            re.IGNORECASE
        )

        if marker:

            if current_lines:

                sections.append(
                    (
                        current_name or "unknown",
                        current_lines
                    )
                )

            current_name = marker.group(1).strip()

            current_lines = []

            continue

        current_lines.append(line)

    if current_lines:

        sections.append(
            (
                current_name or "source",
                current_lines
            )
        )

    # --------------------------------------------------------
    # If sections were not detected, use line-based relevance.
    # --------------------------------------------------------

    if len(sections) <= 1:

        return _compact_source_lines(
            lines,
            max_chars
        )

    # --------------------------------------------------------
    # Rank source sections.
    # --------------------------------------------------------

    ranked = []

    for name, section_lines in sections:

        content = "\n".join(section_lines)

        score = 0

        lower_name = name.lower()

        if "crash" in lower_name:
            score += 10

        if "mainactivity" in lower_name:
            score += 8

        if "activity" in lower_name:
            score += 5

        if "renderer" in lower_name:
            score += 8

        if "fragment" in lower_name:
            score += 5

        if "exception" in lower_name:
            score += 5

        # Stack-frame names appearing in source.
        score += min(
            content.lower().count("throw"),
            5
        )

        score += min(
            content.lower().count("exception"),
            5
        )

        ranked.append(
            (
                score,
                name,
                section_lines
            )
        )

    ranked.sort(
        key=lambda item: item[0],
        reverse=True
    )

    output = []

    used = 0
    selected = 0

    for _, name, section_lines in ranked:

        if selected >= MAX_SOURCE_FILES:

            break

        section = "\n".join(
            section_lines
        )

        header = (
            "\n===== SOURCE FILE: "
            + name
            + " =====\n"
        )

        remaining = (
            max_chars
            - used
            - len(header)
        )

        if remaining <= 100:

            break

        if len(section) > remaining:

            section = _compact_source_lines(
                section_lines,
                remaining
            )

        block = (
            header
            + section
            + "\n"
        )

        output.append(block)

        used += len(block)

        selected += 1

    if not output:

        return _compact_source_lines(
            lines,
            max_chars
        )

    if selected < len(ranked):

        output.append(
            "\n[Additional source files omitted "
            "by VAMP context limiter.]\n"
        )

    return "".join(output)


def _compact_source_lines(
    lines,
    max_chars
):

    if not lines:

        return ""

    # --------------------------------------------------------
    # Score lines based on debugging relevance.
    # --------------------------------------------------------

    important_indexes = []

    for index, line in enumerate(lines):

        lower = line.lower()

        if any(
            keyword in lower
            for keyword in [
                "throw ",
                "exception",
                "error",
                "crash",
                "null",
                "intent",
                "setcontentview",
                "oncreate",
                "onclick",
                "ondraw",
                "onresume",
                "onpause",
                "onstart",
                "onstop",
                "override",
                "try",
                "catch"
            ]
        ):

            important_indexes.append(index)

    # --------------------------------------------------------
    # Build windows around important lines.
    # --------------------------------------------------------

    selected = set()

    for index in important_indexes:

        start = max(
            0,
            index - 5
        )

        end = min(
            len(lines),
            index + 6
        )

        for i in range(start, end):

            selected.add(i)

    # If nothing important was detected,
    # take beginning + end.
    if not selected:

        selected.update(
            range(
                min(
                    len(lines),
                    max_chars // 80
                )
            )
        )

    ordered = sorted(
        selected
    )

    output = []

    used = 0

    for index in ordered:

        line = lines[index]

        candidate = (
            f"{index + 1:04d}: "
            + line
            + "\n"
        )

        if used + len(candidate) > max_chars:

            break

        output.append(candidate)

        used += len(candidate)

    if len(ordered) > len(output):

        output.append(
            "[Source context truncated by VAMP.]\n"
        )

    return "".join(output)


# ============================================================
# PROMPT BUILDER
# ============================================================

def build_prompt(
    data,
    log_text,
    source_text
):
    """
    Build a generic Android debugging and repair prompt.

    Failure evidence and stack-trace location have priority over
    generic source context.
    """

    failure_type = data.get(
        "failure_type",
        data.get(
            "type",
            "UNKNOWN"
        )
    )

    package_name = data.get(
        "package",
        data.get(
            "package_name",
            "UNKNOWN"
        )
    )

    process = data.get(
        "process",
        "UNKNOWN"
    )

    pid = data.get(
        "pid",
        "UNKNOWN"
    )

    activity = data.get(
        "activity",
        "UNKNOWN"
    )

    workspace = data.get(
        "workspace",
        "UNKNOWN"
    )

    source_file = data.get(
        "source_file",
        "UNKNOWN"
    )

    return f"""
You are an Android debugging and automated source-code repair agent.

Analyze the supplied Android failure and source context.

Your task is to:

1. Identify the actual root cause.
2. Explain why the failure occurs.
3. Identify the exact class, method, file, and line responsible when available.
4. Determine whether a source-code patch is required.
5. If a patch is required, provide the exact old code.
6. Provide the exact replacement new code.
7. Keep the patch minimal.
8. Do not invent unrelated files, APIs, classes, methods, or variables.
9. Make the patch compile.
10. Provide useful verification tests.
11. Return ONLY valid JSON.

============================================================
DEBUGGING PRIORITY
============================================================

Use this priority order:

1. Failure stack trace and exception message.
2. Exact file/class/method/line reported by the failure.
3. Code around the reported failure location.
4. Failure type and Android runtime information.
5. Related callers and callees.
6. Other source code only when directly relevant.

The failure evidence is PRIMARY evidence.

DO NOT diagnose the failure from generic lifecycle code alone.

If the stack trace identifies a specific class, method, file, or line,
that location must be treated as the primary evidence.

If the supplied source context does NOT contain the code at the
failure location:

- explain the root cause using the available evidence;
- set patch_required to false;
- set old_code to an empty string;
- set new_code to an empty string;
- do NOT invent missing source code.

============================================================
PATCH RULES
============================================================

A patch is allowed ONLY when:

1. The failure evidence identifies a source-level problem.
2. The supplied source contains the relevant code.
3. The proposed change directly fixes the observed failure.
4. old_code exists EXACTLY in the supplied source context.
5. new_code is a complete replacement for old_code.
6. The change is minimal.
7. The replacement is valid source code for the supplied
   file type, including Kotlin, Java, C, C++, C/C++ JNI, or
   other native source when applicable.
8. The replacement does not depend on invented APIs or variables.

Do NOT patch unrelated code.

Do NOT add a generic null check merely because a variable looks
nullable.

Do NOT modify lifecycle methods unless the failure evidence shows
that the lifecycle method is responsible for the observed failure.

Do NOT modify code merely because it appears suspicious.

If there is insufficient evidence for a safe patch:

patch_required = false

============================================================
EXACT CODE MATCHING
============================================================

old_code must be copied EXACTLY from the supplied SOURCE CONTEXT.

Preserve:

- indentation
- capitalization
- braces
- punctuation
- comments
- annotations
- Kotlin/Java syntax
- statements included in the selected block

new_code must contain the COMPLETE replacement for old_code.

For native C/C++/JNI failures:

- new_code MUST contain executable C/C++ source.
- A comment describing a fix is NOT a patch.
- Removing a statement without providing valid surrounding
  source is NOT a patch.
- If a null pointer dereference is the observed cause, provide
  the actual source-level correction when it can be safely
  derived from the supplied source.
- Preserve valid JNI signatures and surrounding function syntax.

Do NOT return:

- markdown fences
- before/after labels
- explanations inside old_code
- explanations inside new_code
- ellipses such as "..."
- pseudo-code
- placeholders
- invented code

When patch_required is true:

old_code MUST be different from new_code.

If you cannot produce an exact safe replacement:

patch_required = false

============================================================
FAILURE INFORMATION
============================================================

Failure Type:
{failure_type}

Package:
{package_name}

Process:
{process}

PID:
{pid}

Activity:
{activity}

Workspace:
{workspace}

Source File:
{source_file}

============================================================
FAILURE EVIDENCE
============================================================

The following information comes from Android runtime logs,
logcat, failure detection, and/or stack traces.

Treat this as the PRIMARY debugging evidence.

{log_text}

============================================================
SOURCE CONTEXT
============================================================

The following source code was discovered by VAMP.

IMPORTANT:

This source context may contain only part of the application.

Do NOT assume that this is the file where the failure occurred.

Only generate a patch if this source contains the code responsible
for the observed failure.

{source_text}

============================================================
ROOT CAUSE ANALYSIS
============================================================

Determine:

1. What failure actually occurred?
2. What exception or signal occurred?
3. Which class/method/file/line is responsible?
4. Which statement caused the failure?
5. Why does that statement fail?
6. Does the supplied source contain that statement?
7. Is there enough evidence for a safe patch?
8. What is the smallest source change that fixes the issue?

If evidence is insufficient, do not invent a patch.

============================================================
OUTPUT RULES
============================================================

Return ONLY valid JSON.

RETURN EXACTLY THIS JSON STRUCTURE:

{{
  "root_cause": "short root cause",
  "explanation": "technical explanation",
  "patch_required": true,
  "old_code": "exact existing code",
  "new_code": "replacement code",
  "confidence": "HIGH",
  "can_reproduce": true,
  "tests": [
    "test 1",
    "test 2"
  ]
}}

Additional rules:

- patch_required must be false when relevant source is unavailable.
- patch_required must be false when evidence is insufficient.
- patch_required must be false when an exact safe patch cannot be produced.
- When patch_required is false, old_code must be "".
- When patch_required is false, new_code must be "".
- When patch_required is true, old_code and new_code must be different.
- Never fabricate source code.
- Never fabricate a stack-trace location.
- Never invent APIs, classes, methods, variables, or files.
- Keep the patch minimal.
""".strip()

# ============================================================
# GEMINI PROVIDER
# ============================================================

def _send_gemini_request_wrapper(
    prompt
):

    headers = {
        "Content-Type":
            "application/json"
    }

    payload = {
        "contents": [
            {
                "parts": [
                    {
                        "text": prompt
                    }
                ]
            }
        ],

        "generationConfig": {
            "temperature": 0.05,
            "responseMimeType": "application/json",
            "responseSchema": response_schema
        }
    }

    endpoint = (
        URL
        + "?key="
        + GEMINI_API_KEY
    )

    return _send_gemini_request(
        endpoint,
        headers,
        payload
    )


def _send_gemini_request(
    endpoint,
    headers,
    payload
):

    try:

        response = requests.post(
            endpoint,
            headers=headers,
            json=payload,
            timeout=120
        )

    except requests.RequestException as exc:

        raise RuntimeError(
            f"Gemini request failed: {exc}"
        )

    if response.status_code == 429:

        raise RuntimeError(
            "Gemini API quota exhausted. "
            "Daily/project free-tier quota has "
            "been reached. No retry attempted."
        )

    if response.status_code != 200:

        raise RuntimeError(
            "Gemini API returned HTTP "
            f"{response.status_code}: "
            f"{response.text}"
        )

    try:

        response_json = response.json()

    except Exception as exc:

        raise RuntimeError(
            f"Unable to decode Gemini response: {exc}"
        )

    candidates = response_json.get(
        "candidates",
        []
    )

    if not candidates:

        raise RuntimeError(
            "Gemini returned no candidates."
        )

    parts = (
        candidates[0]
        .get("content", {})
        .get("parts", [])
    )

    text_parts = []

    for part in parts:

        if isinstance(part, dict):

            text_value = part.get(
                "text"
            )

            if text_value:

                text_parts.append(
                    text_value
                )

    raw_text = "\n".join(
        text_parts
    ).strip()

    if not raw_text:

        raise RuntimeError(
            "Gemini returned no generated text."
        )

    return raw_text


# ============================================================
# GROQ PROVIDER
# ============================================================

def _send_groq_request(
    prompt
):

    if not GROQ_API_KEY:

        raise RuntimeError(
            "GROQ_API_KEY is not configured."
        )

    # --------------------------------------------------------
    # Extra safety limit for Groq.
    # --------------------------------------------------------

    prompt = _limit_prompt(
        prompt,
        22000
    )

    headers = {
        "Authorization":
            "Bearer "
            + GROQ_API_KEY,

        "Content-Type":
            "application/json"
    }

    payload = {
        "model": GROQ_MODEL,

        "messages": [
            {
                "role": "system",
                "content": (
                    "You are an Android debugging and "
                    "automated repair agent. "
                    "Return ONLY valid JSON matching "
                    "the requested schema."
                )
            },
            {
                "role": "user",
                "content": prompt
            }
        ],

        "temperature": 0.05,

        "max_tokens": 2500,

        "response_format": {
            "type": "json_object"
        }
    }

    try:

        response = requests.post(
            GROQ_URL,
            headers=headers,
            json=payload,
            timeout=120
        )

    except requests.RequestException as exc:

        raise RuntimeError(
            f"Groq request failed: {exc}"
        )

    if response.status_code != 200:

        raise RuntimeError(
            "Groq API returned HTTP "
            f"{response.status_code}: "
            f"{response.text}"
        )

    try:

        response_json = response.json()

    except Exception as exc:

        raise RuntimeError(
            f"Unable to decode Groq response: {exc}"
        )

    choices = response_json.get(
        "choices",
        []
    )

    if not choices:

        raise RuntimeError(
            "Groq returned no choices."
        )

    message = choices[0].get(
        "message",
        {}
    )

    raw_text = message.get(
        "content",
        ""
    )

    if not raw_text:

        raise RuntimeError(
            "Groq returned no generated text."
        )

    return str(
        raw_text
    ).strip()


# ============================================================
# OPENROUTER PROVIDER
# ============================================================

def _send_openrouter_request(
    prompt
):

    if not OPENROUTER_API_KEY:

        raise RuntimeError(
            "OPENROUTER_API_KEY is not configured."
        )

    prompt = _limit_prompt(
        prompt,
        22000
    )

    headers = {
        "Authorization":
            "Bearer "
            + OPENROUTER_API_KEY,

        "Content-Type":
            "application/json",

        "HTTP-Referer":
            "http://localhost:5000",

        "X-Title":
            "VAMP Android Bug Fix Agent"
    }

    payload = {
        "model": OPENROUTER_MODEL,

        "messages": [
            {
                "role": "system",
                "content": (
                    "You are an Android debugging and "
                    "automated repair agent. "
                    "Return ONLY valid JSON matching "
                    "the requested schema."
                )
            },
            {
                "role": "user",
                "content": prompt
            }
        ],

        "temperature": 0.05,

        "max_tokens": 2500,

        "response_format": {
            "type": "json_object"
        }
    }

    try:

        response = requests.post(
            OPENROUTER_URL,
            headers=headers,
            json=payload,
            timeout=90
        )

    except requests.RequestException as exc:

        raise RuntimeError(
            f"OpenRouter request failed: {exc}"
        )

    if response.status_code != 200:

        raise RuntimeError(
            "OpenRouter API returned HTTP "
            f"{response.status_code}: "
            f"{response.text}"
        )

    try:

        response_json = response.json()

    except Exception as exc:

        raise RuntimeError(
            f"Unable to decode OpenRouter response: {exc}"
        )

    choices = response_json.get(
        "choices",
        []
    )

    if not choices:

        raise RuntimeError(
            "OpenRouter returned no choices."
        )

    message = choices[0].get(
        "message",
        {}
    )

    raw_text = message.get(
        "content",
        ""
    )

    # Some OpenRouter models can return structured
    # content rather than a simple string.
    if isinstance(raw_text, list):

        pieces = []

        for item in raw_text:

            if isinstance(item, dict):

                value = item.get(
                    "text"
                )

                if value:

                    pieces.append(
                        value
                    )

        raw_text = "\n".join(
            pieces
        )

    if not raw_text:

        # Some responses expose the generated text
        # through reasoning/content variants.
        raw_text = (
            message.get("reasoning")
            or message.get("refusal")
            or ""
        )

    if not raw_text:

        raise RuntimeError(
            "OpenRouter returned no generated text."
        )

    return str(
        raw_text
    ).strip()


# ============================================================
# PROMPT SIZE SAFETY
# ============================================================

def _limit_prompt(
    prompt,
    max_chars
):

    if not prompt:

        return ""

    if len(prompt) <= max_chars:

        return prompt

    return (
        prompt[:max_chars]
        + "\n\n"
        "[VAMP: prompt truncated to protect "
        "provider context/token limits.]"
    )


# ============================================================
# RESPONSE PARSER
# ============================================================

def parse_llm_response(
    raw_text
):

    if not raw_text:

        raise RuntimeError(
            "LLM returned empty response."
        )

    text = str(
        raw_text
    ).strip()

    # --------------------------------------------------------
    # Remove markdown fences if a provider ignored
    # the JSON-only instruction.
    # --------------------------------------------------------

    text = re.sub(
        r"^```(?:json)?\s*",
        "",
        text,
        flags=re.IGNORECASE
    )

    text = re.sub(
        r"\s*```$",
        "",
        text
    )

    text = text.strip()

    # --------------------------------------------------------
    # Direct JSON parse.
    # --------------------------------------------------------

    try:

        result = json.loads(
            text
        )

    except json.JSONDecodeError:

        # ----------------------------------------------------
        # Attempt to extract the outer JSON object.
        # ----------------------------------------------------

        start = text.find("{")
        end = text.rfind("}")

        if start < 0 or end <= start:

            raise RuntimeError(
                "LLM returned invalid JSON."
            )

        candidate = text[
            start:end + 1
        ]

        try:

            result = json.loads(
                candidate
            )

        except json.JSONDecodeError as exc:

            raise RuntimeError(
                "LLM returned invalid JSON: "
                f"{exc}"
            )

    if not isinstance(result, dict):

        raise RuntimeError(
            "LLM JSON response is not an object."
        )

    return result


# ============================================================
# RESULT VALIDATION
# ============================================================

def _parse_bool_field(value, field_name):
    """
    Safely parse a boolean returned by an LLM.

    Accepts real booleans and common textual representations.
    Rejects ambiguous values instead of silently converting them.
    """

    if isinstance(value, bool):
        return value

    if isinstance(value, str):

        normalized = value.strip().lower()

        if normalized in {
            "true",
            "yes",
            "1",
        }:
            return True

        if normalized in {
            "false",
            "no",
            "0",
        }:
            return False

    if isinstance(value, int) and value in {0, 1}:
        return bool(value)

    raise RuntimeError(
        f"LLM returned invalid boolean for {field_name}: "
        f"{value!r}"
    )


def validate_llm_result(
    result
):

    if not isinstance(result, dict):

        raise RuntimeError(
            "LLM result must be a JSON object."
        )

    required_fields = [
        "root_cause",
        "explanation",
        "patch_required",
        "old_code",
        "new_code",
        "confidence",
        "can_reproduce",
        "tests"
    ]

    for field in required_fields:

        if field not in result:

            raise RuntimeError(
                "LLM response missing required "
                f"field: {field}"
            )

    result["root_cause"] = str(
        result.get(
            "root_cause",
            ""
        )
    ).strip()

    result["explanation"] = str(
        result.get(
            "explanation",
            ""
        )
    ).strip()

    result["old_code"] = str(
        result.get(
            "old_code",
            ""
        )
    )

    result["new_code"] = str(
        result.get(
            "new_code",
            ""
        )
    )

    result["confidence"] = str(
        result.get(
            "confidence",
            ""
        )
    ).strip()

    result["patch_required"] = _parse_bool_field(
        result.get(
            "patch_required",
            False
        ),
        "patch_required"
    )

    result["can_reproduce"] = _parse_bool_field(
        result.get(
            "can_reproduce",
            False
        ),
        "can_reproduce"
    )

    tests = result.get(
        "tests",
        []
    )

    if not isinstance(
        tests,
        list
    ):

        tests = [
            str(tests)
        ]

    result["tests"] = [
        str(item)
        for item in tests
    ]

    # --------------------------------------------------------
    # Basic sanity check.
    # --------------------------------------------------------

    if not result["root_cause"]:

        raise RuntimeError(
            "LLM returned an empty root_cause."
        )

    if not result["explanation"]:

        raise RuntimeError(
            "LLM returned an empty explanation."
        )

    # --------------------------------------------------------
    # No patch means no code modification data.
    # --------------------------------------------------------

    if not result["patch_required"]:

        result["old_code"] = ""
        result["new_code"] = ""

    # --------------------------------------------------------
    # If patch is required, require both code fields.
    # --------------------------------------------------------

    if result["patch_required"]:

        if not result["old_code"].strip():

            raise RuntimeError(
                "LLM requested a patch but "
                "old_code is empty."
            )

        if not result["new_code"].strip():

            raise RuntimeError(
                "LLM requested a patch but "
                "new_code is empty."
            )

        if result["old_code"] == result["new_code"]:

            raise RuntimeError(
                "LLM requested a patch but "
                "old_code and new_code are identical."
            )

    return result


# ============================================================
# MANUAL TEST
# ============================================================

if __name__ == "__main__":

    sample_data = {

        "failure_type":
            "CRASH",

        "package":
            "com.example.test",

        "process":
            "com.example.test",

        "pid":
            "1234",

        "activity":
            "com.example.test/.MainActivity",

        "workspace":
            "/tmp/test",

        "source_file":
            "MainActivity.kt",

        "log":
            """
FATAL EXCEPTION: main
Process: com.example.test, PID: 1234
java.lang.NullPointerException:
Attempt to invoke virtual method
at com.example.test.MainActivity.onCreate(MainActivity.kt:42)
""",

        "source":
            """
class MainActivity : Activity() {

    private var textView: TextView? = null

    override fun onCreate(
        savedInstanceState: Bundle?
    ) {
        super.onCreate(savedInstanceState)

        textView!!.text = "Hello"
    }
}
"""
    }

    try:

        result = ask_llm(
            sample_data
        )

        print(
            json.dumps(
                result,
                indent=2,
                ensure_ascii=False
            )
        )

    except Exception as exc:

        print(
            "LLM test failed:"
        )

        print(
            exc
        )
