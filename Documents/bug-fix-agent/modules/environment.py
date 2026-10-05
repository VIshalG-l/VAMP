import sys
from pathlib import Path

# Add project root to Python path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import shutil
import subprocess
import config

def run(cmd):
    return subprocess.run(
        cmd,
        text=True,
        capture_output=True
    )


def check_tool(name):
    """
    Check if a command exists.
    """

    return shutil.which(name) is not None


def check_java():

    if not check_tool("java"):
        return False, "Java not found."

    result = run(["java", "-version"])

    version = result.stderr.splitlines()[0]

    return True, version


def check_adb():

    if not check_tool("adb"):
        return False, "ADB not found."

    result = run(["adb", "version"])

    version = result.stdout.splitlines()[0]

    return True, version


def check_gradle():

    if not check_tool("gradle"):

        # Gradle wrapper will still work.
        return True, "Using Gradle Wrapper"

    result = run(["gradle", "--version"])

    version = result.stdout.splitlines()[0]

    return True, version


def check_android_sdk():

    sdk = Path.home() / "Android" / "Sdk"

    if sdk.exists():

        return True, str(sdk)

    return False, "Android SDK not found."


def check_gemini():

    if config.GEMINI_API_KEY:

        return True, "Gemini API Key Found"

    return False, "Gemini API Key Missing"


def check_device():

    result = run(["adb", "devices"])

    lines = result.stdout.strip().splitlines()

    devices = []

    for line in lines[1:]:

        if "\tdevice" in line:

            devices.append(line.split()[0])

    if devices:

        return True, devices

    return False, "No Android Device Connected"


def check_projects():

    errors = []

    if not Path(config.ANR_WORKSPACE).exists():

        errors.append("ANR Project Missing")

    if not Path(config.CRASH_WORKSPACE).exists():

        errors.append("Crash Project Missing")

    if errors:

        return False, errors

    return True, "Projects Found"


def verify_environment():

    print("\n" + "=" * 60)
    print("        ENVIRONMENT VERIFICATION")
    print("=" * 60)

    checks = [
        ("Java", check_java),
        ("ADB", check_adb),
        ("Gradle", check_gradle),
        ("Android SDK", check_android_sdk),
        ("Gemini", check_gemini),
        ("Device", check_device),
        ("Projects", check_projects),
    ]

    failed = False

    for title, func in checks:

        ok, msg = func()

        if ok:

            print(f"✅ {title:<15} : {msg}")

        else:

            failed = True

            print(f"❌ {title:<15} : {msg}")

    print("=" * 60)

    if failed:

        print("\nEnvironment verification failed.\n")

        return False

    print("\nEnvironment Ready.\n")

    return True


if __name__ == "__main__":

    verify_environment()
