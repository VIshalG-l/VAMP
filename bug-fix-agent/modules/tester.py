import os
import time
import subprocess
from pathlib import Path

from config import MOCK_BUILD
from modules.builder import detect_project


# ==========================================================
# Test Commands
# ==========================================================

def get_test_command(project):

    commands = {

        "android": ["./gradlew", "test"],

        "maven": ["mvn", "test"],

        "python": ["python3", "-m", "pytest"],

        "node": ["npm", "test"],

        "cmake": ["ctest"]

    }

    return commands.get(project)


# ==========================================================
# Extract Failed Tests
# ==========================================================

def extract_failed_tests(output):

    failed = []

    keywords = [
        "FAILED",
        "FAILURES",
        "AssertionError",
        "Exception",
    ]

    for line in output.splitlines():

        if any(k in line for k in keywords):
            failed.append(line)

    return failed


# ==========================================================
# Run Tests
# ==========================================================

def run_tests(workspace):

    """
    Run automated tests after patching.

    Returns
    -------
    success(bool)
    logs(str)
    """

    if MOCK_BUILD:
        return True, "Mock tests passed."

    workspace = Path(workspace)

    project = detect_project(workspace)

    if project == "unknown":
        return False, "Unsupported project."

    cmd = get_test_command(project)

    if cmd is None:
        return False, "No test command available."

    if project == "android":

        gradlew = workspace / "gradlew"

        if not gradlew.exists():
            return False, "gradlew not found."

        os.chmod(gradlew, 0o755)

    print("\n[TEST] Running automated tests...")

    start = time.time()

    try:

        result = subprocess.run(
            cmd,
            cwd=workspace,
            capture_output=True,
            text=True,
        )

    except Exception as e:

        return False, str(e)

    elapsed = round(time.time() - start, 2)

    failed = extract_failed_tests(
        result.stdout + "\n" + result.stderr
    )

    logs = (
        f"Project Type : {project}\n"
        f"Execution Time : {elapsed} sec\n\n"
        "========== TEST STDOUT ==========\n"
        f"{result.stdout}\n\n"
        "========== TEST STDERR ==========\n"
        f"{result.stderr}\n\n"
        "========== FAILED TESTS ==========\n"
        + ("\n".join(failed) if failed else "None")
    )

    print("\n========== TEST SUMMARY ==========")
    print(f"Project : {project}")
    print(f"Time    : {elapsed} sec")

    if result.returncode == 0:
        print("Status  : PASSED")
    else:
        print("Status  : FAILED")

    if failed:
        print(f"Failures: {len(failed)}")
    else:
        print("Failures: 0")

    print("==================================\n")

    return result.returncode == 0, logs
