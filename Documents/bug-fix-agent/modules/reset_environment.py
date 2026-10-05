import os
import shutil
import subprocess


# ============================================================
# APK PACKAGE NAMES
# ============================================================

# Change these if your actual applicationId is different.

ANR_PACKAGE = "com.example.demo"

DISPLAY_PACKAGE = "com.example.displaycrashapp"


# ============================================================
# HELPER: RUN ADB COMMAND
# ============================================================

def run_adb(command):
    """
    Run an ADB command and return the result.
    """

    try:

        result = subprocess.run(
            ["adb"] + command,
            capture_output=True,
            text=True
        )

        return result

    except FileNotFoundError:

        print("❌ ADB command not found.")
        print("Please make sure Android SDK platform-tools are installed.")

        return None


# ============================================================
# CHECK ADB DEVICE
# ============================================================

def check_device():

    print("\n============================================================")
    print("              CHECKING ANDROID DEVICE")
    print("============================================================")

    result = run_adb(
        [
            "devices"
        ]
    )

    if result is None:
        return False

    lines = result.stdout.strip().splitlines()

    devices = []

    for line in lines[1:]:

        line = line.strip()

        if line and "\tdevice" in line:

            devices.append(line)

    if not devices:

        print("❌ No Android device connected.")

        print("\nRun:")
        print("adb devices")

        return False

    print("✅ Android device connected.")

    for device in devices:

        print("   ", device)

    return True


# ============================================================
# RESTORE BUG FILES
# ============================================================

def restore_bug_files(workspace, bug_type):
    """
    Restore the injected bug source files before every pipeline run.
    """

    bug_type = bug_type.upper()

    if bug_type == "DISPLAY":

        files = [

            (
                "app/src/main/java/com/example/displaycrashapp/CrashRenderer.kt.bak",
                "app/src/main/java/com/example/displaycrashapp/CrashRenderer.kt",
            ),

            (
                "app/src/main/java/com/example/displaycrashapp/CrashGLSurfaceView.kt.bak",
                "app/src/main/java/com/example/displaycrashapp/CrashGLSurfaceView.kt",
            ),

        ]

    elif bug_type == "ANR":

        files = [

            (
                "app/src/main/java/com/example/demo/MainActivity.kt.bak",
                "app/src/main/java/com/example/demo/MainActivity.kt",
            ),

        ]

    else:

        print(f"⚠ Unknown bug type: {bug_type}")

        return False

    print("\n============================================================")
    print("              RESTORING BUG FILES")
    print("============================================================")

    restored = False

    for backup_file, target_file in files:

        backup_path = os.path.join(
            workspace,
            backup_file
        )

        target_path = os.path.join(
            workspace,
            target_file
        )

        if os.path.exists(backup_path):

            try:

                shutil.copy2(
                    backup_path,
                    target_path
                )

                print(
                    f"✅ Restored: {target_file}"
                )

                restored = True

            except Exception as e:

                print(
                    f"❌ Failed to restore: {target_file}"
                )

                print(
                    f"   Error: {e}"
                )

        else:

            print(
                f"⚠ Backup not found:"
            )

            print(
                f"   {backup_path}"
            )

    print("============================================================")

    return restored


# ============================================================
# CHECK IF APK IS INSTALLED
# ============================================================

def is_apk_installed(package):

    """
    Check whether an APK package is installed on the device.
    """

    result = run_adb(
        [
            "shell",
            "pm",
            "list",
            "packages",
            package
        ]
    )

    if result is None:

        return False

    for line in result.stdout.splitlines():

        line = line.strip()

        if line == f"package:{package}":

            return True

    return False


# ============================================================
# UNINSTALL ONE APK
# ============================================================

def uninstall_apk(package):

    """
    Uninstall an APK from the connected Android device.

    If the APK is not installed, nothing is done.

    Returns:
        True  -> APK is not installed or successfully uninstalled
        False -> Uninstall failed
    """

    print(
        f"\nChecking package: {package}"
    )

    # --------------------------------------------------------
    # CHECK PACKAGE
    # --------------------------------------------------------

    if not is_apk_installed(package):

        print(
            f"ℹ Not installed: {package}"
        )

        return True

    print(
        f"📦 Package found: {package}"
    )

    print(
        f"🗑 Uninstalling: {package}"
    )

    # --------------------------------------------------------
    # UNINSTALL
    # --------------------------------------------------------

    result = run_adb(
        [
            "uninstall",
            package
        ]
    )

    if result is None:

        return False

    output = (
        result.stdout +
        result.stderr
    ).strip()

    # --------------------------------------------------------
    # SUCCESS
    # --------------------------------------------------------

    if result.returncode == 0:

        if "Success" in output:

            print(
                f"✅ Successfully uninstalled: {package}"
            )

            # Verify uninstall
            if not is_apk_installed(package):

                print(
                    f"✅ Verified removed: {package}"
                )

                return True

            else:

                print(
                    f"⚠ Uninstall reported success,"
                    f" but package is still present:"
                )

                print(
                    f"   {package}"
                )

                return False

    # --------------------------------------------------------
    # FAILURE
    # --------------------------------------------------------

    print(
        f"❌ Failed to uninstall: {package}"
    )

    print(
        f"ADB output:"
    )

    print(
        output
    )

    return False


# ============================================================
# UNINSTALL BOTH APKS
# ============================================================

def uninstall_all_apks():

    """
    Uninstall both ANR and Display applications
    if they are installed.
    """

    print("\n============================================================")
    print("          UNINSTALLING EXISTING APPLICATIONS")
    print("============================================================")

    packages = [

        ANR_PACKAGE,

        DISPLAY_PACKAGE,

    ]

    results = {}

    for package in packages:

        results[package] = uninstall_apk(
            package
        )

    # --------------------------------------------------------
    # SUMMARY
    # --------------------------------------------------------

    print("\n============================================================")
    print("              UNINSTALL SUMMARY")
    print("============================================================")

    for package, success in results.items():

        if success:

            print(
                f"✅ {package}"
            )

        else:

            print(
                f"❌ {package}"
            )

    print("============================================================")

    return all(results.values())


# ============================================================
# MAIN CLEANUP FUNCTION
# ============================================================

def reset_environment(
    workspace=None,
    bug_type=None
):

    """
    Complete environment reset.

    Steps:
        1. Check Android device
        2. Uninstall ANR APK
        3. Uninstall Display APK
        4. Restore bug files if workspace and bug_type are provided
    """

    print("\n")
    print("============================================================")
    print("              RESETTING ENVIRONMENT")
    print("============================================================")

    # --------------------------------------------------------
    # STEP 1: CHECK DEVICE
    # --------------------------------------------------------

    if not check_device():

        print(
            "\n❌ Environment reset aborted."
        )

        return False

    # --------------------------------------------------------
    # STEP 2: UNINSTALL BOTH APKS
    # --------------------------------------------------------

    uninstall_success = uninstall_all_apks()

    # --------------------------------------------------------
    # STEP 3: RESTORE BUG FILES
    # --------------------------------------------------------

    if workspace and bug_type:

        restore_bug_files(
            workspace,
            bug_type
        )

    # --------------------------------------------------------
    # FINAL STATUS
    # --------------------------------------------------------

    print("\n============================================================")

    if uninstall_success:

        print(
            "✅ ENVIRONMENT RESET COMPLETE"
        )

    else:

        print(
            "⚠ ENVIRONMENT RESET COMPLETED WITH ERRORS"
        )

    print("============================================================")

    return uninstall_success


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":

    print("\n============================================================")
    print("              BUG-FIX AGENT RESET")
    print("============================================================")

    # --------------------------------------------------------
    # Check device
    # --------------------------------------------------------

    if not check_device():

        exit(1)

    # --------------------------------------------------------
    # Uninstall both applications
    # --------------------------------------------------------

    uninstall_all_apks()

    print("\nReset process finished.")
