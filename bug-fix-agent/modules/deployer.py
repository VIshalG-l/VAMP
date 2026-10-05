import subprocess
from pathlib import Path


def adb_devices():
    """
    Check whether an Android device is connected.

    Returns:
        (success, message)
    """

    result = subprocess.run(
        ["adb", "devices"],
        capture_output=True,
        text=True
    )

    devices = []

    for line in result.stdout.splitlines()[1:]:

        if "\tdevice" in line:
            devices.append(line.split()[0])

    if not devices:
        return False, "No Android device connected."

    return True, devices[0]


def install_apk(apk_path):
    """
    Install APK using adb install -r
    """

    apk = Path(apk_path)

    if not apk.exists():
        return False, "APK not found."

    ok, device = adb_devices()

    if not ok:
        return False, device

#    print(f"\nConnected Device : {device}")

    result = subprocess.run(
        [
            "adb",
            "install",
            "-r",
            str(apk)
        ],
        capture_output=True,
        text=True
    )

    logs = result.stdout + result.stderr

    if "Success" in logs:
        return True, logs

    return False, logs


def launch_app(package, activity):
    """
    Launch installed application.
    """

    result = subprocess.run(
        [
            "adb",
            "shell",
            "am",
            "start",
            "-n",
            f"{package}/{activity}"
        ],
        capture_output=True,
        text=True
    )

    return result.returncode == 0, result.stdout + result.stderr
