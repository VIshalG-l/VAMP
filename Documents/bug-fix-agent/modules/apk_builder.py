import subprocess
import time
from pathlib import Path


def build_apk(workspace):
    """
    Build Android APK.

    Returns:
        success(bool),
        apk_path(str|None),
        build_log(str)
    """

    workspace = Path(workspace)

    gradlew = workspace / "gradlew"

    if not gradlew.exists():
        return False, None, "gradlew not found."

    start = time.time()

    cmd = [
        "./gradlew",
        "clean",
        "assembleDebug"
    ]

#@    print("Running:")
#    print(" ".join(cmd))
#    print()

    result = subprocess.run(
        cmd,
        cwd=workspace,
        text=True,
        capture_output=True
    )

    elapsed = round(time.time() - start, 2)

    if result.returncode != 0:

        print("❌ BUILD FAILED\n")

        print(result.stderr)

        return (
            False,
            None,
            result.stdout + "\n" + result.stderr
        )

#    print("✅ BUILD SUCCESSFUL")
#    print(f"Build Time : {elapsed} sec")

    apk = None

    apk_dir = workspace / "app" / "build" / "outputs" / "apk"

    if apk_dir.exists():

        apks = list(apk_dir.rglob("*.apk"))

        if apks:
            apks.sort(
                key=lambda f: f.stat().st_mtime,
                reverse=True
            )

            apk = apks[0]

    if apk:

#        print("\nAPK Generated Successfully")
#        print(apk)

        return (
            True,
            str(apk),
            result.stdout
        )

    print("\n⚠ Build completed but APK not found.")

    return (
        True,
        None,
        result.stdout
    )


if __name__ == "__main__":

    WORKSPACE = "/home/vishal/AndroidStudioProjects/DisplayCrashApp"

    success, apk, logs = build_apk(WORKSPACE)

    print("\nSuccess :", success)
    print("APK     :", apk)
