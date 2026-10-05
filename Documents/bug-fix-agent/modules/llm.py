import json
import requests

from config import GEMINI_API_KEY
from modules.patch import Patch


URL = (
    "https://generativelanguage.googleapis.com/v1beta/"
    f"models/gemini-2.5-flash:generateContent?key={GEMINI_API_KEY}"
)


def ask_llm(data):
    """
    Analyze Android ANR / Crash / Native Crash
    and generate RCA + safe patch.
    """

    report = data["log"]
    source = data["source"]

    bug_type = report.get("type", "UNKNOWN")


    prompt = f"""

You are a Senior Android Framework Engineer.

Analyze the given Android crash/ANR issue.

Your job:

1. Find the root cause.
2. Identify the exact faulty code.
3. Generate the smallest safe fix.


==================================================
BUG TYPE
==================================================

{bug_type}


==================================================
BUG REPORT
==================================================

Package:
{report.get("package")}

Process:
{report.get("process")}

Class:
{report.get("class")}

Method:
{report.get("method")}

File:
{report.get("file")}

Line:
{report.get("line")}

Exception:
{report.get("exception")}

Reason:
{report.get("reason")}

Thread:
{report.get("thread")}


Stack Trace:

{report.get("stacktrace")}



==================================================
SOURCE FILE
==================================================

File:

{source.get("file")}


Relevant Code:

{source.get("snippet")}



==================================================
FULL SOURCE
==================================================

{source.get("code")}



==================================================
ANALYSIS RULES
==================================================


CRASH:

- Find exact crashing statement.
- Explain why it crashes.
- Fix only the faulty code.
- Do not modify unrelated code.


ANR:

- Find blocking operation.
- Explain UI thread blockage.
- Suggest minimum safe optimization.
- Do not patch without evidence.


NATIVE_CRASH:

- Analyze JNI/native interaction.
- Patch only if Java code clearly causes issue.



==================================================
PATCH RULES
==================================================


IMPORTANT:

- Use ONLY supplied source code.
- Never invent classes.
- Never invent methods.
- Never invent variables.
- Never rewrite entire files.
- Keep existing formatting.


When patch_required=true:

old_code:
    MUST exactly match existing source.


new_code:
    MUST NOT be empty.


The patch must compile.


If removing faulty code:

DO NOT generate:

old_code:
throw Exception()

new_code:


Instead generate safe replacement:

Example:

old_code:

throw RuntimeException(
    "Injected Display Failure"
)


new_code:

Log.e(
    "DISPLAY_FAULT",
    "Display error handled safely"
)


If a safe patch cannot be generated:

Set:

patch_required=false



Return ONLY JSON.

FORMAT:

{{
    "bug_type":"",
    "severity":"Critical|High|Medium|Low",
    "root_cause":"",
    "confidence":"High|Medium|Low",
    "can_reproduce":true,
    "patch_required":true,
    "old_code":"",
    "new_code":"",
    "explanation":"",
    "estimated_fix_time":"",
    "tests":[]
}}

"""


    payload = {

        "contents": [

            {

                "parts": [

                    {

                        "text": prompt

                    }

                ]

            }

        ]

    }


#    response = requests.post(
#        URL,
#        json=payload,
#        timeout=120
#    )


 #   response.raise_for_status()
    response = requests.post(
        URL,
        json=payload,
        timeout=120
    )

    if response.status_code != 200:
        print("\n========== GEMINI ERROR ==========")
 #       print("Status :", response.status_code)
 #       print(response.text)
        raise Exception("Gemini request failed")


    result = response.json()


 #   print("\n========== GEMINI RAW RESPONSE ==========\n")
 #   print(json.dumps(result, indent=2))


    text = result["candidates"][0]["content"]["parts"][0]["text"]


    text = (
        text.replace("```json", "")
            .replace("```", "")
            .strip()
    )


    start = text.find("{")
    end = text.rfind("}")


    if start != -1 and end != -1:

        text = text[start:end + 1]


    try:

        response_json = json.loads(text)


    except json.JSONDecodeError:

        print("\n========== INVALID JSON ==========")
        print(text)

        raise



    # ==================================================
    # Patch Validation
    # ==================================================

    patch_required = response_json.get(
        "patch_required",
        False
    )


    old_code = response_json.get(
        "old_code",
        ""
    )


    new_code = response_json.get(
        "new_code",
        ""
    )


    if patch_required:


        if not old_code.strip():


            print(
                "\n⚠ Gemini generated empty old_code"
            )

            patch_required = False



        elif not new_code.strip():


            print(
                "\n⚠ Gemini generated empty new_code"
            )

            patch_required = False



    return Patch(

        root_cause=response_json.get(
            "root_cause",
            ""
        ),


        confidence=response_json.get(
            "confidence",
            "Unknown"
        ),


        can_reproduce=response_json.get(
            "can_reproduce",
            False
        ),


        patch_required=patch_required,


        old_code=old_code,


        new_code=new_code,


        explanation=response_json.get(
            "explanation",
            ""
        ),


        tests=response_json.get(
            "tests",
            []
        )

    )
