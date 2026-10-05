import os
import shutil
import subprocess


def restore_bug_files(workspace, bug_type):
    """
    Restore the injected bug source files before every pipeline run.
    """

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
        return

#    print("\n============================================================")
#    print("        RESTORING BUG FILES")
#    print("============================================================")

    for backup_file, target_file in files:

        backup_path = os.path.join(workspace, backup_file)
        target_path = os.path.join(workspace, target_file)

        if os.path.exists(backup_path):

            shutil.copy2(backup_path, target_path)
 #           print(f"✅ Restored: {os.path.basename(target_file)}")

        else:
#            print(f"⚠ Backup not found: {backup_path}")
            pass

#    print("============================================================")
#    print("Bug files restored.")
#    print("============================================================")


def uninstall_apk(package):
    """
    Uninstall the existing APK from the connected device.
    """

#    print("\n============================================================")
#    print("          UNINSTALLING OLD APK")
#    print("============================================================")

    result = subprocess.run(
        ["adb", "uninstall", package],
        capture_output=True,
        text=True,
    )

    output = (result.stdout + result.stderr).strip()

 #   if "Success" in output:
 #       print("✅ Previous APK removed")#

#    elif "Unknown package" in output:
#        print("ℹ APK was not installed")

#    else:
#        print(output)

#    print("============================================================")

