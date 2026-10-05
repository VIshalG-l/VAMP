import subprocess
from pathlib import Path

apps = [
    {
        "name": "ANR",
        "path": Path.home() / "AndroidStudioProjects" / "DEMO",
        "apk": "bug-anr.apk",
    },
    {
        "name": "BUG",
        "path": Path.home() / "AndroidStudioProjects" / "DisplayCrashApp",
        "apk": "bug-display.apk",
    },
]

def run(command, cwd=None):
    print(f"\n$ {' '.join(map(str, command))}")
    subprocess.run(command, cwd=cwd, check=True)

for app in apps:
    project = app["path"]
    apk_path = project / "app" / "build" / "outputs" / "apk" / "debug" / app["apk"]

    print(f"\n===== Building {app['name']} App =====")

    # Build APK
    run(["./gradlew", "clean", "assembleDebug"], cwd=project)

    # Rename APK
    default_apk = project / "app" / "build" / "outputs" / "apk" / "debug" / "app-debug.apk"

    if apk_path.exists():
        apk_path.unlink()

    default_apk.rename(apk_path)

    # Install APK
    run(["adb", "install", "-r", str(apk_path)])

    print(f"===== {app['name']} App Installed Successfully =====")

print("\nBoth APKs installed successfully!")
