#!/usr/bin/env python3


import os
import sys
import subprocess
import time
from pathlib import Path


def run(cmd, check=True):
    result = subprocess.run(cmd)
    if check and result.returncode != 0:
        print(f"[ERROR] Command Failed: {' '.join(cmd)}")
        sys.exit(result.returncode)
    return result


print("=" * 50)
print("        Android CLI APK Builder")
print("=" * 50)

if len(sys.argv) < 2:
    print("\nUsage:")
    print(f"{sys.argv[0]} <Android_Project_Path>")
    sys.exit(1)

PROJECT_DIR = Path(sys.argv[1]).expanduser()

if not PROJECT_DIR.is_dir():
    print("[ERROR] Project directory does not exist.")
    sys.exit(1)

os.chdir(PROJECT_DIR)

##################################################
# Check Java
##################################################

print("\n[INFO] Checking Java...")

if subprocess.run(["which", "java"], capture_output=True).returncode != 0:
    print("Java is not installed.")
#import uiautomator2 as u2if subprocess.run(["which", "java"],
#                  stdout=subprocess.DEVNULL).returncode != 0:

    print("[INFO] Installing Java...")
    run(["sudo", "apt", "update"])
    run(["sudo", "apt", "install", "-y", "openjdk-17-jdk"])

print("[OK] Java Ready")

##################################################
# Check Gradle
##################################################

print("\n[INFO] Checking Gradle...")

if subprocess.run(["which", "gradle"],
                  stdout=subprocess.DEVNULL).returncode != 0:

    print("[INFO] Installing Gradle...")
    run(["sudo", "apt", "update"])
    run(["sudo", "apt", "install", "-y", "gradle"])

print("[OK] Gradle Ready")

##################################################
# Check ADB
##################################################

print("\n[INFO] Searching for ADB...")

if subprocess.run(["which", "adb"],
                  stdout=subprocess.DEVNULL).returncode != 0:

    print("[INFO] Installing ADB...")
    run(["sudo", "apt", "update"])
    run(["sudo", "apt", "install", "-y",
         "android-sdk-platform-tools"])

print("[OK] ADB detected.")

##################################################
# Validate Project
##################################################

print("\n[INFO] Validating Android Project...")

if not (Path("build.gradle").exists() or
        Path("build.gradle.kts").exists()):

    print("[ERROR] Not a Gradle Android Project.")
    sys.exit(1)

print("[OK] Android Project Found.")


##################################################
# Gradle Wrapper
##################################################

if not Path("gradlew").exists():
    print("[INFO] Creating Gradle Wrapper...")
    run(["gradle", "wrapper"])

Path("gradlew").chmod(0o755)


##################################################
# Check and Install uiautomator2
##################################################

print("\n[INFO] Checking uiautomator2...")

try:
    import uiautomator2 as u2
    print("[OK] uiautomator2 is already installed.")

except ImportError:

    print("[INFO] Installing uiautomator2...")

    run([
        sys.executable,
        "-m",
        "pip",
        "install",
        "-U",
        "uiautomator2"
    ])

    print("[INFO] Initializing uiautomator2 on the connected device...")

    run([
        sys.executable,
        "-m",
        "uiautomator2",
        "init"
    ])

    import uiautomator2 as u2



    print("[OK] uiautomator2 installation completed.")

##################################################
# Clean
##################################################

print("\n[INFO] Cleaning Project...")
run(["./gradlew", "clean"])

##################################################
# Build APK
##################################################

print("\n[INFO] APK Build Generation Started...")

run(["./gradlew", "assembleDebug"])

print("[OK] APK Build Generation is Done.")

##################################################
# Find APK
##################################################

apks = list(PROJECT_DIR.rglob("*debug*.apk"))

if not apks:
    print("[ERROR] APK Not Found.")
    sys.exit(1)

apk = apks[0]

print("\n[OK] APK Generated Successfully")
print(f"APK Location : {apk}")

##################################################
# Launch Check Script
##################################################

print("\n[INFO] Starting Autonomous Triage...")

time.sleep(2)

run(["python3",
str(Path.home() /
"Desktop/Triage_project/display_check.py")],
check=False)

         







