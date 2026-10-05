import subprocess
import time


def run(cmd):
    return subprocess.run(
        cmd,
        text=True,
        capture_output=True
    )


def get_device():
    """
    Return connected Android device serial.
    """

    result = run(["adb", "devices"])

    if result.returncode != 0:
        return None

    lines = result.stdout.strip().splitlines()

    for line in lines[1:]:

        if "\tdevice" in line:
            return line.split()[0]

    return None


def launch_app(package, activity):
    """
    Launch Android application.

    Returns:
        bool
    """

#    print("\n" + "=" * 60)
#    print("               LAUNCHING APPLICATION")
#    print("=" * 60)

    serial = get_device()

    if serial is None:
        print("❌ No Android device connected.")
        return False

#    print(f"Connected Device : {serial}")
#    print(f"Package          : {package}")
#    print(f"Activity         : {activity}")

    result = run([
        "adb",
        "-s",
        serial,
        "shell",
        "am",
        "start",
        "-n",
        f"{package}/{activity}"
    ])

    if result.returncode != 0:
        print("\n❌ Launch Failed")
        print(result.stderr)
        return False
 #   print(result.stdout.strip())

    # Give app time to start
    time.sleep(2)

    # Check if ActivityManager accepted the launch request
    if "Error" not in result.stdout and result.returncode == 0:

 #       print("\n✅ Application Launch Command Sent")

        verify = run([
            "adb",
            "-s",
            serial,
            "shell",
            "pidof",
            package
        ])

        pid = verify.stdout.strip()

       # if pid:
        #    print(f"PID : {pid}")
         #   print("Status : Running")
       # else:
        #    print("Status : App exited (likely crashed immediately).")

        return True, result.stdout

    print("\n❌ Launch Failed")
    return False, result.stderr

if __name__ == "__main__":

    PACKAGE = "com.example.displaycrashapp"
    ACTIVITY = "com.example.displaycrashapp.MainActivity"

    success = launch_app(
        PACKAGE,
        ACTIVITY
    )

    print("\nLaunch Status :", success)
