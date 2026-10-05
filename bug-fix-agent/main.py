import sys
import time

from modules.device import get_connected_device
from modules.environment import verify_environment
from modules.bug_monitor import BugMonitor


# ============================================================
# CONFIGURATION
# ============================================================

MONITOR_CONTEXT_LINES = 30

MONITOR_COLLECTION_TIMEOUT = 3.0

MONITOR_INCIDENT_COOLDOWN = 2.0


# ============================================================
# DEVICE INFORMATION
# ============================================================

def get_device_info():
    """
    Detect the connected Android device.

    The device serial is discovered dynamically.
    No Android device is hard-coded.
    """

    device = get_connected_device()

    if not device:

        print()
        print(
            "❌ No Android device connected."
        )

        print(
            "Connect an Android device or "
            "Android Cuttlefish instance."
        )

        return None

    print()
    print("=" * 70)
    print("                    ANDROID DEVICE")
    print("=" * 70)

    print(
        f"Model   : {device.get('model')}"
    )

    print(
        f"Android : {device.get('android')}"
    )

    print(
        f"SDK     : {device.get('sdk')}"
    )

    serial = (
        device.get("serial")
        or device.get("device_serial")
    )

    print(
        f"Serial  : {serial}"
    )

    print("=" * 70)

    return device


# ============================================================
# VAMP MONITOR
# ============================================================

def start_vamp_monitor(device):
    """
    Start the generic VAMP Android failure monitor.

    BugMonitor owns:
        - adb logcat
        - rolling evidence
        - failure detection
        - incident creation
        - VAMP integration

    VAMPIntegration owns:
        - BugFixAgent creation
        - AI analysis
        - patching
        - build
        - install
        - launch
        - tests
        - runtime verification
    """

    serial = None

    if device:

        serial = (
            device.get("serial")
            or device.get("device_serial")
        )

    print()
    print("=" * 70)
    print("                 VAMP ANDROID")
    print("=" * 70)

    print()
    print(
        "VAMP will automatically discover the failed "
        "application from Android runtime logs."
    )

    print()
    print(
        "No package name is hard-coded."
    )

    print(
        "No APK path is required."
    )

    print(
        "No source path is required."
    )

    print(
        "No launcher activity is hard-coded."
    )

    print("=" * 70)

    monitor = BugMonitor(
        serial=serial,
        context_lines=MONITOR_CONTEXT_LINES,
        collection_timeout=MONITOR_COLLECTION_TIMEOUT,
        incident_cooldown=MONITOR_INCIDENT_COOLDOWN
    )

    try:

        monitor.start()

    except KeyboardInterrupt:

        print()
        print(
            "⚠ VAMP monitor interrupted."
        )

        monitor.stop()

    except Exception as exc:

        print()
        print(
            "❌ VAMP monitor failed:"
        )

        print(exc)

        monitor.stop()

        return False

    # --------------------------------------------------------
    # If the monitor stopped because of Ctrl+C or another
    # external condition, allow an already-running VAMP
    # repair pipeline to finish.
    # --------------------------------------------------------

    if monitor.vamp:

        if monitor.vamp.is_active():

            print()
            print("=" * 70)
            print("          VAMP REPAIR STILL RUNNING")
            print("=" * 70)

            print(
                "The Android monitor has stopped."
            )

            print(
                "Waiting for the active VAMP repair pipeline "
                "to finish..."
            )

            print("=" * 70)

            monitor.vamp.wait()

        result = monitor.vamp.get_last_result()

        error = monitor.vamp.get_last_error()

        if error:

            print()
            print("=" * 70)
            print("             VAMP PIPELINE ERROR")
            print("=" * 70)

            print(error)

            print("=" * 70)

            return False

        if result is not None:

            print()
            print("=" * 70)
            print("              VAMP FINAL RESULT")
            print("=" * 70)

            print(
                "Result:",
                result
            )

            print("=" * 70)

            return bool(result)

    return True


# ============================================================
# MAIN PIPELINE
# ============================================================

def run_pipeline():
    """
    Main VAMP Android runtime pipeline.

    Architecture:

        Android Device
              |
              v
        BugMonitor
              |
              v
       FailureDetector
              |
              v
           Incident
              |
              v
       VAMPIntegration
              |
              v
         BugFixAgent
              |
              v
      Analyze -> Patch
              |
              v
      Build -> Install
              |
              v
       Launch -> Test
              |
              v
          Verify
    """

    start_time = time.time()

    print()
    print("=" * 70)
    print("             VAMP ANDROID BUG FIX AGENT")
    print("=" * 70)

    print()
    print(
        "Generic Android runtime failure detection and "
        "AI-assisted repair."
    )

    print("=" * 70)

    # ========================================================
    # STEP 1: DEVICE
    # ========================================================

    print()
    print(
        "[1] Checking Android device..."
    )

    device = get_device_info()

    if not device:

        print()
        print(
            "❌ VAMP cannot start without an Android device."
        )

        return False

    print()
    print(
        "✅ Android device detected."
    )

    # ========================================================
    # STEP 2: START GENERIC MONITOR
    # ========================================================

    print()
    print(
        "[2] Starting generic Android failure monitoring..."
    )

    print()
    print(
        "The monitor will detect:"
    )

    print(
        "  • ANR"
    )

    print(
        "  • Java/Kotlin crashes"
    )

    print(
        "  • Native crashes"
    )

    print()
    print(
        "The application will be identified automatically "
        "from runtime evidence."
    )

    print()

    result = start_vamp_monitor(
        device
    )

    # ========================================================
    # SUMMARY
    # ========================================================

    elapsed = round(
        time.time() - start_time,
        2
    )

    print()
    print("=" * 70)
    print("                 VAMP EXECUTION SUMMARY")
    print("=" * 70)

    print(
        f"Device Model : {device.get('model')}"
    )

    print(
        f"Android      : {device.get('android')}"
    )

    print(
        f"SDK          : {device.get('sdk')}"
    )

    print(
        f"Result       : "
        f"{'SUCCESS' if result else 'FAILED'}"
    )

    print(
        f"Time         : {elapsed} sec"
    )

    print("=" * 70)

    return result


# ============================================================
# COMMAND LINE
# ============================================================

def main():
    """
    VAMP command-line entry point.

    Any supplied APK/project argument is ignored because
    application discovery is performed from Android runtime
    failure evidence.
    """

    # --------------------------------------------------------
    # Verify local VAMP environment.
    # --------------------------------------------------------

    if not verify_environment():

        print()
        print(
            "❌ VAMP environment verification failed."
        )

        return

    # --------------------------------------------------------
    # Legacy command-line arguments are no longer required.
    # --------------------------------------------------------

    if len(sys.argv) > 1:

        print()
        print(
            "⚠ Command-line APK/project arguments are "
            "no longer required."
        )

        print(
            "VAMP will ignore the supplied path and "
            "monitor the connected Android device."
        )

    # --------------------------------------------------------
    # Start the complete VAMP runtime pipeline.
    # --------------------------------------------------------

    run_pipeline()


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":

    main()
