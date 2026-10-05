import subprocess
import sys


def run(cmd, capture=True):
    """
    Execute shell command.
    """
    return subprocess.run(
        cmd,
        text=True,
        capture_output=capture
    )


def get_connected_device():
    """
    Detect connected Android device.

    Returns:
        dict or None
    """
#    print("\n" + "=" * 60)
#    print(" Searching for Connected Android Device")
#    print("=" * 60)

    result = run(["adb", "devices"])

    if result.returncode != 0:
        print("❌ adb command failed.")
        return None

    lines = result.stdout.strip().splitlines()
    devices = []

    for line in lines[1:]:
        if "\tdevice" in line:
            devices.append(line.split()[0])

    if len(devices) == 0:
        print("❌ No Android device connected.")
        return None

    serial = devices[0]

    print(f"\nConnected Device : {serial}")

    def prop(name):
        p = run(
            [
                "adb",
                "-s",
                serial,
                "shell",
                "getprop",
                name,
            ]
        )
        return p.stdout.strip()

    info = {
        "serial": serial,
        "manufacturer": prop("ro.product.manufacturer"),
        "model": prop("ro.product.model"),
        "android": prop("ro.build.version.release"),
        "sdk": prop("ro.build.version.sdk"),
        "fingerprint": prop("ro.build.fingerprint"),
    }

    print("\nDevice Information")
    print("-" * 60)
    print(f"Manufacturer : {info['manufacturer']}")
    print(f"Model : {info['model']}")
    print(f"Android : {info['android']}")
    print(f"SDK : {info['sdk']}")
    print(f"Serial : {info['serial']}")
    print("-" * 60)

    print("✅ Device Ready\n")

    return info


if __name__ == "__main__":
    device = get_connected_device()

    if device is None:
        sys.exit(1)

    print(device)
