import subprocess


def run(cmd):
    return subprocess.run(
        cmd,
        text=True,
        capture_output=True
    )


def get_device():
    """
    Returns connected device serial.
    """

    result = run(["adb", "devices"])

    lines = result.stdout.strip().splitlines()

    for line in lines[1:]:

        if "\tdevice" in line:
            return line.split()[0]

    return None


def install_apk(apk_path):
    """
    Install APK using adb.

    Returns:
        success(bool),
        message(str)
    """

    serial = get_device()

    if serial is None:
        msg = "No Android device connected."

        print(f"❌ {msg}")

        return False, msg

#    print(f"Connected Device : {serial}")
#    print(f"APK              : {apk_path}")

    cmd = [
        "adb",
        "-s",
        serial,
        "install",
        "-r",
        apk_path
    ]

    result = run(cmd)

    output = (result.stdout + result.stderr).strip()

    if result.returncode == 0:

        print("\n✅ APK Installed Successfully")
        print(output)

        return True, output

    print("\n❌ APK Installation Failed")
    print(output)

    return False, output


if __name__ == "__main__":

    APK = "/home/vishal/AndroidStudioProjects/DisplayCrashApp/app/build/outputs/apk/debug/app-debug.apk"

    success, message = install_apk(APK)

    print("\nInstallation Status :", success)
    print(message)
