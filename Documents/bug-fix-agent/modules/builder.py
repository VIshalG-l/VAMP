import os
import time
import subprocess
from pathlib import Path

from config import MOCK_BUILD


# --------------------------------------------------
# Detect Project Type
# --------------------------------------------------

def detect_project(workspace):

    workspace = Path(workspace)

    if (workspace / "gradlew").exists():
        return "android"

    if (workspace / "pom.xml").exists():
        return "maven"

    if (workspace / "build.gradle").exists():
        return "gradle"

    if (workspace / "package.json").exists():
        return "node"

    if (workspace / "requirements.txt").exists():
        return "python"

    if (workspace / "CMakeLists.txt").exists():
        return "cmake"

    return "unknown"


# --------------------------------------------------
# Find Generated APK
# --------------------------------------------------

def find_apk(workspace):
    """
    Search for the newest generated APK.

    Returns:
        APK path or None
    """

    workspace = Path(workspace)

    apk_files = list(workspace.rglob("*.apk"))

    if not apk_files:
        return None

    apk = max(
        apk_files,
        key=lambda f: f.stat().st_mtime
    )

    return str(apk)


# --------------------------------------------------
# Build Project
# --------------------------------------------------

def build_project(workspace):
    """
    Build the project.

    Returns:
        success(bool),
        apk_path(str),
        logs(str)
    """

    if MOCK_BUILD:
        return True, None, "Mock build successful."

    workspace = Path(workspace)

    project = detect_project(workspace)

    commands = {
        "android": ["./gradlew", "assembleDebug"],
        "gradle": ["gradle", "build"],
        "maven": ["mvn", "package"],
        "python": ["python3", "-m", "pytest"],
        "node": ["npm", "run", "build"],
        "cmake": ["cmake", "--build", "."]
    }

    if project == "unknown":
        return False, None, "Unsupported project."

    cmd = commands[project]

    if project == "android":

        gradlew = workspace / "gradlew"

        if not gradlew.exists():
            return False, None, "gradlew not found."

        os.chmod(gradlew, 0o755)

    start = time.time()

    try:

        result = subprocess.run(
            cmd,
            cwd=workspace,
            capture_output=True,
            text=True
        )

    except Exception as e:
        return False, None, str(e)

    elapsed = round(time.time() - start, 2)

    logs = (
        f"Project Type : {project}\n"
        f"Build Time   : {elapsed} sec\n\n"
        "========== STDOUT ==========\n"
        f"{result.stdout}\n\n"
        "========== STDERR ==========\n"
        f"{result.stderr}"
    )

    if result.returncode != 0:
        return False, None, logs

    # ----------------------------------------------
    # Search generated APK
    # ----------------------------------------------

    apk = find_apk(workspace)

    if apk:

        print("\n✅ APK Generated Successfully")
        print("APK Path :", apk)

    else:

        print("\n⚠ Build succeeded but APK not found.")

    return True, apk, logs
