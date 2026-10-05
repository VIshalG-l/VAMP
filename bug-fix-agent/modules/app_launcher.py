import subprocess
import time


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
# PROCESS CHECK
# ============================================================

def get_process_id(
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
            "pidof",
            package
        ]

    else:

        cmd = [
            "adb",
            "shell",
            "pidof",
            package
        ]

    result = run(cmd)

    if result.returncode != 0:
        return None

    pid = (
        result.stdout or ""
    ).strip()

    if not pid:
        return None

    return pid


# ============================================================
# CHECK APPLICATION RUNNING
# ============================================================

def is_app_running(
    package,
    serial=None
):

    return (
        get_process_id(
            package,
            serial
        )
        is not None
    )


# ============================================================
# STOP APPLICATION
# ============================================================

def stop_app(
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
# LAUNCH APPLICATION
# ============================================================

def launch_app(
    package,
    activity,
    startup_timeout=8.0,
    poll_interval=0.5
):
    """
    Launch Android application and verify that its process
    actually becomes alive.

    The activity must belong to the supplied package.
    """

    package = (
        package or ""
    ).strip()

    activity = (
        activity or ""
    ).strip()

    if not package:

        message = "Package is missing."

        print(
            f"❌ {message}"
        )

        return False, message

    if not activity:

        message = "Activity is missing."

        print(
            f"❌ {message}"
        )

        return False, message

    # --------------------------------------------------------
    # Normalize Activity
    # --------------------------------------------------------

    if "/" in activity:

        activity_package, activity_class = (
            activity.split("/", 1)
        )

        activity_package = (
            activity_package.strip()
        )

        activity_class = (
            activity_class.strip()
        )

        if activity_package != package:

            message = (
                "Activity package does not match "
                f"application package: "
                f"{activity_package} != {package}"
            )

            print(
                f"❌ {message}"
            )

            return False, message

        activity = activity_class

    if activity.startswith("."):

        activity = (
            package
            + activity
        )

    elif "." not in activity:

        activity = (
            package
            + "."
            + activity
        )

    # --------------------------------------------------------
    # Final package validation
    # --------------------------------------------------------

    if not (
        activity == package
        or activity.startswith(
            package + "."
        )
    ):

        message = (
            "Activity does not belong to "
            f"package {package}: {activity}"
        )

        print(
            f"❌ {message}"
        )

        return False, message

    # --------------------------------------------------------
    # Device
    # --------------------------------------------------------

    serial = get_device()

    if serial is None:

        message = (
            "No Android device connected."
        )

        print(
            f"❌ {message}"
        )

        return False, message

    print()
    print(
        "Connected Device :",
        serial
    )

    print(
        "Package          :",
        package
    )

    print(
        "Activity         :",
        activity
    )

    # --------------------------------------------------------
    # Stop previous instance
    # --------------------------------------------------------

    print()
    print(
        "→ Stopping previous application instance..."
    )

    stop_ok, stop_output = stop_app(
        package,
        serial
    )

    if not stop_ok and stop_output:

        print(
            "⚠️ Stop warning:"
        )

        print(
            stop_output
        )

    # --------------------------------------------------------
    # Start Activity
    # --------------------------------------------------------

    print()
    print(
        "→ Starting application..."
    )

    component = (
        f"{package}/{activity}"
    )

    result = run([
        "adb",
        "-s",
        serial,
        "shell",
        "am",
        "start",
        "-n",
        component
    ])

    stdout = (
        result.stdout or ""
    ).strip()

    stderr = (
        result.stderr or ""
    ).strip()

    output = (
        stdout
        + (
            "\n" + stderr
            if stderr
            else ""
        )
    ).strip()

    # --------------------------------------------------------
    # ActivityManager failure
    # --------------------------------------------------------

    if result.returncode != 0:

        print()
        print(
            "❌ Launch Failed"
        )

        if output:
            print(output)

        return False, output

    failure_markers = [
        "Error:",
        "Exception:",
        "Unable to start",
        "Activity not started",
    ]

    for marker in failure_markers:

        if marker.lower() in output.lower():

            print()
            print(
                "❌ Application launch rejected:"
            )

            print(output)

            return False, output

    print()
    print(
        "✅ Launch command accepted."
    )

    # --------------------------------------------------------
    # Wait for process
    # --------------------------------------------------------

    print()
    print(
        "→ Waiting for application process..."
    )

    deadline = (
        time.time()
        + float(startup_timeout)
    )

    pid = None

    while time.time() < deadline:

        pid = get_process_id(
            package,
            serial
        )

        if pid:

            break

        time.sleep(
            float(poll_interval)
        )

    # --------------------------------------------------------
    # Process did not start
    # --------------------------------------------------------

    if not pid:

        message = (
            output
            + "\n"
            + (
                "Application process did not "
                "become alive after launch."
            )
        ).strip()

        print()
        print(
            "❌ Application process is NOT running."
        )

        if output:
            print(output)

        return False, message

    # --------------------------------------------------------
    # Success
    # --------------------------------------------------------

    print()
    print(
        "✅ Application launched successfully."
    )

    print(
        "PID:",
        pid
    )

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
        "Use launch_app(package, activity) "
        "from the application pipeline."
    )
