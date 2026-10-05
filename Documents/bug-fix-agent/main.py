import sys
import os
import time
import subprocess
from modules.device import get_connected_device
from modules.apk_builder import build_apk
from modules.apk_installer import install_apk
from modules.app_launcher import launch_app
from modules.trigger_bug import trigger_bug
from modules.log_collector import collect_logs

from modules.log_parser import parse_log
from modules.code_search import find_source
from modules.file_reader import read_context
from modules.llm import ask_llm
from modules.patcher import apply_patch, rollback
from modules.builder import build_project
from modules.tester import run_tests
from modules.environment import verify_environment
from config import (
    ANR_WORKSPACE,
    CRASH_WORKSPACE,
    ANR_LOG_FILE,
    CRASH_LOG_FILE,
)
from modules.reset_environment import (
    restore_bug_files,
    uninstall_all_apks
)
#WORKSPACE = "/home/vishal/AndroidStudioProjects/DEMO"
def run_pipeline(choice):

    start = time.time()
    subprocess.run(["adb", "shell", "input", "keyevent", "KEYCODE_WAKEUP"])
    time.sleep(1)
    subprocess.run(["adb", "shell", "input", "swipe", "500", "1800", "500", "500", "300"])
    if choice == "1":

        bug_type = "ANR"
        workspace = ANR_WORKSPACE
        package = "com.example.demo"
        activity = "com.example.demo.MainActivity"

    elif choice == "2":

        bug_type = "DISPLAY"
        workspace = CRASH_WORKSPACE
        package = "com.example.displaycrashapp"
        activity = "com.example.displaycrashapp.MainActivity"

    else:
        print("Invalid Choice")
        return
    ###################################################
    # RESET TEST ENVIRONMENT
    ###################################################

#    uninstall_apk(package)
    uninstall_all_apks()
    restore_bug_files(
        workspace,
        bug_type
    )
    ###################################################
    # STEP 1
    ###################################################

#    print("Connecting Device...")

    device = get_connected_device()

    if not device:

        print("No Android Device Connected.")
        return

    ###################################################
    # STEP 2
    ###################################################

#    print("\n Building APK...")
#    print("\n========== BUILD DEBUG ==========")
#    print("Bug Type :", bug_type)
#    print("Workspace:", workspace)
#    print("Package  :", package)
#    print("=================================\n")
    success, apk_path, build_logs = build_apk(workspace)

#    if not success:#

#        print("APK Build Failed.")
#        return
    if not success:
        print("❌ Build Failed")
#        print(build_logs)
        return

#    print("✅ Build Successful")

#    if build_logs.strip():
#        print(build_logs)

#    if apk_path:
#        print("\n✅ APK Generated Successfully")
#        print(f"APK Path : {apk_path}")
#    else:
#        print("\n❌ APK not found.")
#        return
    ###################################################
    # STEP 3
    ###################################################

 #   print("\n Installing APK...")

    success, msg = install_apk(apk_path)

#    if not success:

#        print(msg)
 #       return
   # print("✅ APK Installed Successfully")
    ###################################################
    # STEP 4
    ###################################################

#    print("\nClearing old logcat...")
    subprocess.run(["adb", "logcat", "-c"])

    print("\nLaunching APK...")

    success = launch_app(
        package,
        activity
    )

    if not success:
        print("❌ Failed to launch application.")
        return

# Give the renderer time to crash
    time.sleep(2)
    ###################################################
    # STEP 5
    ###################################################

    print("\n Triggering Bug...")

#    trigger_bug(bug_type)
    if not trigger_bug(bug_type):
        print("Bug trigger failed.")
        return
    ###################################################
    # STEP 6
    ###################################################

    print("\n Collecting Logs...")
    log_dir = collect_logs(bug_type)

    if not log_dir:

        print("⚠ Log collection failed.")
        print("Continuing pipeline...")

        log_dir = "logs"
    if bug_type == "ANR":

        LOG_FILE = os.path.join(
            log_dir,
            "anr_trace.txt"
        )

    else:

        LOG_FILE = os.path.join(
            log_dir,
            "logcat.txt"
        )

    print("\nCollected Log File")
    print(LOG_FILE)

    ###################################################
    # STEP 7
    ###################################################

    print("\n Parsing Logs...")

    report = parse_log(LOG_FILE)

    print("Done.\n")

#    print("Parsed Report")
#    print(report)
    print("\n========== DEBUG SOURCE SEARCH ==========")
    print("Workspace :", workspace)
    print("File      :", report.get("file"))
    print("Class     :", report.get("class"))
    print("Package   :", report.get("package"))
    print("Method    :", report.get("method"))
    print("Line      :", report.get("line"))
    print("========================================")
    # ---------------------------------------------------
    # Step 2 : Locate Source
    # ---------------------------------------------------

#    print("\n[2] Searching Source File...")

    source = find_source(workspace, report)
#    source = find_source(WORKSPACE, report)

    if not source:
        print("❌ Source file not found.")
        return

    print("✅ Source Found")
    print(source["path"])

    # ---------------------------------------------------
    # Step 3 : Read Context
    # ---------------------------------------------------

    print("\n[3] Reading Source Context...")

    context = read_context(
        source["path"],
	error_line=report.get("line"),
	method=report.get("method")
#        report.get("line")
    )

    print("✅ Context Loaded")
    print(f"Source File : {context['file']}")
    print(f"Total Lines : {context['total_lines']}")

    # ---------------------------------------------------
    # Step 4 : Gemini RCA
    # ---------------------------------------------------

    print("\n[4] Running AI Root Cause Analysis...")

    patch = ask_llm({
        "log": report,
        "source": context
    })

#    print("\n==============================")
#    print(" AI ROOT CAUSE ANALYSIS")
#    print("==============================")

#    print(patch.explanation)

    if not patch.has_patch():

        print("\n⚠ No patch generated.")
        print("Stopping pipeline.")

        return

    print("\n==============================")
    print(" OLD CODE")
    print("==============================")

    print(patch.old_code)

    print("\n==============================")
    print(" NEW CODE")
    print("==============================")

    print(patch.new_code)

    # ---------------------------------------------------
    # Step 5 : Apply Patch
    # ---------------------------------------------------

    print("\n[5] Applying Patch...")

    success, message = apply_patch(
        source["path"],
        patch
    )

    if not success:

        print("❌", message)
        return

    print("✅", message)

    ###################################################
    # STEP 6 : Rebuild APK
    ###################################################

    print("\n[6] Rebuilding Patched APK...")

    success, apk_path,  build_logs = build_apk(workspace)

    if not success:

        print("Build Failed")

        rollback(source["path"])
        return

    print("Patched APK Generated")
    print(apk_path)
   # print("✅ Build Successful")
   # print(build_logs)
    if apk_path:
        print("\n✅ APK Generated Successfully")
        print(f"APK Path : {apk_path}")
    else:
        print("\n⚠ Build succeeded but APK not found.")


    ###################################################
    # STEP 7 : Install Patched APK
    ###################################################

    print("\n[7] Installing Patched APK...")

    success = install_apk(apk_path)

    if not success:

        print(msg)

        rollback(source["path"])
        return

    ###################################################
    # STEP 8 : Launch Patched APK
     ###################################################

    print("\n[8] Launching Patched APK...")

    success = launch_app(
        package,
        activity
    )

    if not success:

        print(msg)

    ###################################################
    # STEP 9 : Run Tests
    ###################################################

    print("\n[9] Running Tests...")

    success, test_logs = run_tests(workspace)

    if not success:

        print(test_logs)

        rollback(source["path"])
        return

    print("Tests Passed")

    ###################################################
    # SUMMARY
    ###################################################

    elapsed = round(time.time() - start, 2)

    print("\n" + "=" * 60)
    print("           EXECUTION SUMMARY")
    print("=" * 60)

    print(f"Bug Type     : {report['type']}")
    print(f"Package      : {package}")
    print(f"Device       : {device['model']}")
    print(f"Android      : {device['android']}")
    print(f"SDK          : {device['sdk']}")
    print(f"Source File  : {source['path']}")
    print("Patch        : Applied")
    print("Build        : Success")
    print("Install      : Success")
    print("Tests        : Passed")
    print(f"Time         : {elapsed} sec")

    print("\n✔ VAMP-SENTINEL completed successfully.")
def main():

    if not verify_environment():
        return

    if len(sys.argv) > 1:
        choice = sys.argv[1]
    else:
        print("\nSelect Bug Type")
        print("1. ANR")
        print("2. Display")
        choice = input("\nEnter choice (1/2): ").strip()

    run_pipeline(choice)


if __name__ == "__main__":
    main()

