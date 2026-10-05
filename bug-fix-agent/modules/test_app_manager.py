import subprocess
from pathlib import Path


class TestAppManager:
    """
    Generic Android application lifecycle manager.

    No device serial, package name, activity name, project path,
    or APK path is hard-coded.

    Information is discovered at runtime.
    """

    def __init__(
        self,
        serial=None,
        package=None,
        activity=None,
    ):
        self.serial = serial
        self.package = package
        self.activity = activity

    # ========================================================
    # ADB
    # ========================================================

    def adb(self, *args):

        if not self.serial:

            self.serial = self.discover_device()

        command = ["adb"]

        if self.serial:
            command.extend([
                "-s",
                self.serial
            ])

        command.extend(args)

        return subprocess.run(
            command,
            capture_output=True,
            text=True,
        )

    # ========================================================
    # DEVICE DISCOVERY
    # ========================================================

    @staticmethod
    def discover_device():

        result = subprocess.run(
            ["adb", "devices"],
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:
            raise RuntimeError(
                "Unable to execute adb devices."
            )

        devices = []

        for line in result.stdout.splitlines():

            line = line.strip()

            if not line or line.startswith("List of devices"):
                continue

            parts = line.split()

            if len(parts) >= 2 and parts[1] == "device":
                devices.append(parts[0])

        if not devices:

            raise RuntimeError(
                "No Android device is connected."
            )

        if len(devices) > 1:

            raise RuntimeError(
                "Multiple Android devices detected: "
                + ", ".join(devices)
                + ". Specify the target device explicitly."
            )

        print()
        print("✅ Android device discovered:")
        print("   ", devices[0])

        return devices[0]

    # ========================================================
    # BUILD
    # ========================================================

    @staticmethod
    def build(workspace):

        workspace = Path(workspace).resolve()

        print()
        print("=" * 70)
        print("                 BUILD TEST APPLICATION")
        print("=" * 70)

        print("Workspace :", workspace)

        gradlew = workspace / "gradlew"

        if not gradlew.exists():

            return (
                False,
                None,
                "Gradle wrapper not found."
            )

        gradlew.chmod(0o755)

        try:

            result = subprocess.run(
                [str(gradlew), "assembleDebug"],
                cwd=workspace,
                capture_output=True,
                text=True,
            )

        except Exception as exc:

            return (
                False,
                None,
                str(exc)
            )

        logs = (
            "========== STDOUT ==========\n"
            + result.stdout
            + "\n\n"
            "========== STDERR ==========\n"
            + result.stderr
        )

        if result.returncode != 0:

            return (
                False,
                None,
                logs
            )

        apk_files = list(
            workspace.rglob("*.apk")
        )

        if not apk_files:

            return (
                False,
                None,
                logs + "\nAPK was not generated."
            )

        apk = max(
            apk_files,
            key=lambda path: path.stat().st_mtime
        )

        print()
        print("✅ APK generated:")
        print(apk)

        return (
            True,
            str(apk),
            logs
        )

    # ========================================================
    # INSTALL
    # ========================================================

    def install(self, apk_path):

        print()
        print("=" * 70)
        print("                 INSTALL APPLICATION")
        print("=" * 70)

        apk = Path(apk_path)

        if not apk.exists():

            print("❌ APK does not exist.")

            return False

        try:

            result = self.adb(
                "install",
                "-r",
                str(apk),
            )

        except Exception as exc:

            print("❌ Installation failed:")
            print(exc)

            return False

        if result.stdout:
            print(result.stdout)

        if result.stderr:
            print(result.stderr)

        if result.returncode != 0:

            print("❌ APK installation failed.")

            return False

        print("✅ APK installed.")

        return True

    # ========================================================
    # PACKAGE DISCOVERY FROM APK
    # ========================================================

    def discover_package(self, apk_path):

        """
        Extract package information from an APK.

        Uses Android SDK's aapt when available.
        """

        commands = [
            ["aapt", "dump", "badging", apk_path],
            ["apkanalyzer", "manifest", "application-id", apk_path],
        ]

        for command in commands:

            try:

                result = subprocess.run(
                    command,
                    capture_output=True,
                    text=True,
                )

            except FileNotFoundError:
                continue

            if result.returncode != 0:
                continue

            output = result.stdout

            for line in output.splitlines():

                if line.startswith("package:"):

                    for field in line.split():

                        if field.startswith("name="):

                            package = field.split(
                                "=",
                                1
                            )[1].strip("'\"")

                            self.package = package

                            print(
                                "✅ Package discovered:",
                                package
                            )

                            return package

                if line.strip():

                    package = line.strip()

                    if (
                        "." in package
                        and " " not in package
                    ):

                        self.package = package

                        print(
                            "✅ Package discovered:",
                            package
                        )

                        return package

        return None

    # ========================================================
    # INSTALLED PACKAGE VERIFICATION
    # ========================================================

    def verify_installed(self):

        if not self.package:

            return False

        try:

            result = self.adb(
                "shell",
                "pm",
                "path",
                self.package,
            )

        except Exception:
            return False

        installed = (
            result.returncode == 0
            and "package:" in result.stdout
        )

        if installed:

            print(
                "✅ Package installed:",
                self.package
            )

        else:

            print(
                "❌ Package not installed:",
                self.package
            )

        return installed

    # ========================================================
    # ACTIVITY DISCOVERY
    # ========================================================

    def discover_activity(self):

        if not self.package:
            return None

        try:

            result = self.adb(
                "shell",
                "cmd",
                "package",
                "resolve-activity",
                "--brief",
                self.package,
            )

        except Exception:
            return None

        if result.returncode != 0:
            return None

        for line in result.stdout.splitlines():

            line = line.strip()

            if "/" in line:

                self.activity = line

                print(
                    "✅ Activity discovered:",
                    line
                )

                return line

        return None

    # ========================================================
    # LAUNCH
    # ========================================================

    def launch(self):

        if not self.package:

            print(
                "❌ Cannot launch: package unknown."
            )

            return False

        try:

            if not self.activity:
                self.discover_activity()

            if self.activity:

                result = self.adb(
                    "shell",
                    "am",
                    "start",
                    "-n",
                    self.activity,
                )

            else:

                result = self.adb(
                    "shell",
                    "monkey",
                    "-p",
                    self.package,
                    "1",
                )

        except Exception as exc:

            print("❌ Launch failed:")
            print(exc)

            return False

        if result.stdout:
            print(result.stdout)

        if result.stderr:
            print(result.stderr)

        if result.returncode != 0:

            print("❌ Application launch failed.")

            return False

        print("✅ Application launched.")

        return True

    # ========================================================
    # COMPLETE PREPARATION
    # ========================================================

    def prepare(
        self,
        workspace,
    ):

        print()
        print("=" * 70)
        print("              PREPARE ANDROID APPLICATION")
        print("=" * 70)

        # ----------------------------------------------------
        # Device
        # ----------------------------------------------------

        try:

            self.serial = (
                self.serial
                or self.discover_device()
            )

        except Exception as exc:

            return {
                "success": False,
                "message": str(exc),
                "apk_path": None,
            }

        # ----------------------------------------------------
        # Build
        # ----------------------------------------------------

        success, apk_path, build_logs = (
            self.build(workspace)
        )

        if not success:

            return {
                "success": False,
                "message": "Build failed.",
                "apk_path": None,
                "build_logs": build_logs,
            }

        # ----------------------------------------------------
        # Discover package
        # ----------------------------------------------------

        if not self.package:

            self.discover_package(
                apk_path
            )

        if not self.package:

            return {
                "success": False,
                "message": (
                    "Unable to determine APK package."
                ),
                "apk_path": apk_path,
                "build_logs": build_logs,
            }

        # ----------------------------------------------------
        # Install
        # ----------------------------------------------------

        if not self.install(apk_path):

            return {
                "success": False,
                "message": "Installation failed.",
                "apk_path": apk_path,
                "build_logs": build_logs,
            }

        # ----------------------------------------------------
        # Verify
        # ----------------------------------------------------

        if not self.verify_installed():

            return {
                "success": False,
                "message": (
                    "Installation verification failed."
                ),
                "apk_path": apk_path,
                "build_logs": build_logs,
            }

        # ----------------------------------------------------
        # Activity
        # ----------------------------------------------------

        self.discover_activity()

        # ----------------------------------------------------
        # Launch
        # ----------------------------------------------------

        if not self.launch():

            return {
                "success": False,
                "message": "Launch failed.",
                "apk_path": apk_path,
                "build_logs": build_logs,
            }

        print()
        print("=" * 70)
        print("        APPLICATION PREPARATION COMPLETE")
        print("=" * 70)

        print("Device  :", self.serial)
        print("Package :", self.package)
        print("Activity:", self.activity)
        print("APK     :", apk_path)

        return {
            "success": True,
            "serial": self.serial,
            "package": self.package,
            "activity": self.activity,
            "apk_path": apk_path,
            "build_logs": build_logs,
        }
