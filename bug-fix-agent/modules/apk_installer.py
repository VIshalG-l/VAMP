import subprocess
from pathlib import Path


# ============================================================
# COMMAND EXECUTION
# ============================================================

def run(cmd):

    return subprocess.run(
        cmd,
        text=True,
        capture_output=True
    )


# ============================================================
# DEVICE DISCOVERY
# ============================================================

def get_device():

    result = run(
        ["adb", "devices"]
    )

    if result.returncode != 0:
        return None

    lines = (
        result.stdout
        .strip()
        .splitlines()
    )

    for line in lines[1:]:

        if "\tdevice" in line:

            return line.split()[0]

    return None


# ============================================================
# GET INSTALLED PACKAGE PATH
# ============================================================

def get_installed_package_path(
    package,
    serial=None
):

    if not package:
        return None

    if serial:

        cmd = [
            "adb",
            "-s",
            serial,
            "shell",
            "pm",
            "path",
            package
        ]

    else:

        cmd = [
            "adb",
            "shell",
            "pm",
            "path",
            package
        ]

    result = run(cmd)

    if result.returncode != 0:
        return None

    output = (
        result.stdout or ""
    ).strip()

    for line in output.splitlines():

        line = line.strip()

        if line.startswith(
            "package:"
        ):

            return line[
                len("package:"):
            ].strip()

    return None


# ============================================================
# CHECK PACKAGE INSTALLED
# ============================================================

def is_package_installed(
    package,
    serial=None
):

    return (
        get_installed_package_path(
            package,
            serial
        )
        is not None
    )


# ============================================================
# STOP APPLICATION
# ============================================================

def stop_package(
    package,
    serial=None
):

    if not package:
        return False, "Package is missing."

    if serial:

        cmd = [
            "adb",
            "-s",
            serial,
            "shell",
            "am",
            "force-stop",
            package
        ]

    else:

        cmd = [
            "adb",
            "shell",
            "am",
            "force-stop",
            package
        ]

    result = run(cmd)

    output = (
        result.stdout + result.stderr
    ).strip()

    if result.returncode == 0:

        return True, output

    return False, output


# ============================================================
# INSTALL APK
# ============================================================

def install_apk(
    apk_path,
    package=None
):
    """
    Install APK using ADB.

    Parameters
    ----------
    apk_path:
        Path to APK.

    package:
        Optional package name.

        If supplied, the installer verifies that the
        package exists after installation.

    Returns
    -------
    (success, message)
    """

    apk = Path(apk_path)

    # --------------------------------------------------------
    # Validate APK
    # --------------------------------------------------------

    if not apk.exists():

        msg = (
            f"APK does not exist: {apk}"
        )

        print(
            f"❌ {msg}"
        )

        return False, msg

    if not apk.is_file():

        msg = (
            f"APK path is not a file: {apk}"
        )

        print(
            f"❌ {msg}"
        )

        return False, msg

    # --------------------------------------------------------
    # Device
    # --------------------------------------------------------

    serial = get_device()

    if serial is None:

        msg = (
            "No Android device connected."
        )

        print(
            f"❌ {msg}"
        )

        return False, msg

    print()
    print(
        "Connected Device :",
        serial
    )

    print(
        "APK              :",
        apk
    )

    # --------------------------------------------------------
    # Stop old application before replacing it
    # --------------------------------------------------------

    if package:

        print()
        print(
            "→ Stopping existing application..."
        )

        stop_ok, stop_output = stop_package(
            package,
            serial
        )

        if stop_ok:

            print(
                "✅ Existing application stopped."
            )

        elif stop_output:

            print(
                "⚠️ Could not stop existing "
                "application:"
            )

            print(
                stop_output
            )

    # --------------------------------------------------------
    # Install
    # --------------------------------------------------------

    print()
    print(
        "→ Installing patched APK..."
    )

    cmd = [
        "adb",
        "-s",
        serial,
        "install",
        "-r",
        apk_path
    ]

    result = run(cmd)

    output = (
        result.stdout + result.stderr
    ).strip()

    # --------------------------------------------------------
    # ADB installation failure
    # --------------------------------------------------------

    if result.returncode != 0:

        print()
        print(
            "❌ APK Installation Failed"
        )

        print(output)

        return False, output

    # --------------------------------------------------------
    # Verify installation
    # --------------------------------------------------------

    if package:

        print()
        print(
            "→ Verifying installed package..."
        )

        installed_path = (
            get_installed_package_path(
                package,
                serial
            )
        )

        if not installed_path:

            message = (
                output
                + "\n"
                + (
                    "ADB reported installation "
                    "success, but package verification "
                    "failed."
                )
            )

            print()
            print(
                "❌ Installed package could not "
                "be verified."
            )

            return False, message

        print(
            "✅ Package verified:"
        )

        print(
            "   ",
            package
        )

        print(
            "   APK:",
            installed_path
        )

    # --------------------------------------------------------
    # Final success
    # --------------------------------------------------------

    print()
    print(
        "✅ APK Installed Successfully"
    )

    if output:
        print(output)

    return True, output


# ============================================================
# STANDALONE TEST
# ============================================================

if __name__ == "__main__":

    print(
        "This module is intended to be called "
        "by the VAMP pipeline."
    )

    print(
        "Use install_apk(apk_path, package) "
        "from the application pipeline."
    )
