import os
import re
import subprocess
import tempfile
from pathlib import Path


class APKDiscoveryError(Exception):
    pass


class APKDiscovery:

    """
    Generic Android APK / Android Studio project discovery.

    Supported input:

        1. Android Studio project directory
        2. APK file
        3. Installed package name

    The discovery process attempts to determine:

        - APK path
        - installed APK path on device
        - package name
        - application label
        - launcher activity
        - Android project root
        - source root
        - Gradle build system

    No application-specific package names or paths are hard-coded.
    """

    def __init__(
        self,
        input_path=None,
        serial=None
    ):

        self.input_path = (
            os.path.abspath(
                os.path.expanduser(input_path)
            )
            if input_path
            and (
                os.path.exists(
                    os.path.expanduser(input_path)
                )
            )
            else input_path
        )

        self.serial = serial

        self.result = {
            "input": self.input_path,
            "apk_path": None,
            "installed_apk_path": None,
            "project_root": None,
            "source_root": None,
            "package": None,
            "application_label": None,
            "activity": None,
            "manifest": None,
            "build_system": None,
            "device_serial": self.serial,
        }

    # =========================================================
    # PUBLIC API
    # =========================================================

    def discover(self):

        if not self.input_path:

            raise APKDiscoveryError(
                "No APK, Android project, or package was supplied."
            )

        # -----------------------------------------------------
        # Existing filesystem input
        # -----------------------------------------------------

        if os.path.exists(self.input_path):

            # -------------------------------------------------
            # APK input
            # -------------------------------------------------

            if os.path.isfile(self.input_path):

                if not self.input_path.lower().endswith(".apk"):

                    raise APKDiscoveryError(
                        "Input file is not an APK."
                    )

                self.result["apk_path"] = (
                    self.input_path
                )

                self._discover_from_apk(
                    self.input_path
                )

                return self.result

            # -------------------------------------------------
            # Android project input
            # -------------------------------------------------

            if os.path.isdir(self.input_path):

                self.result["project_root"] = (
                    self._find_project_root(
                        self.input_path
                    )
                )

                if not self.result["project_root"]:

                    raise APKDiscoveryError(
                        "Android project root could not be identified."
                    )

                self.result["build_system"] = (
                    self._detect_build_system(
                        self.result["project_root"]
                    )
                )

                self.result["manifest"] = (
                    self._find_manifest(
                        self.result["project_root"]
                    )
                )

                if self.result["manifest"]:

                    self._discover_from_manifest(
                        self.result["manifest"]
                    )

                self.result["source_root"] = (
                    self._find_source_root(
                        self.result["project_root"]
                    )
                )

                self.result["apk_path"] = (
                    self._find_existing_apk(
                        self.result["project_root"]
                    )
                )

                # If package was not found from the manifest,
                # try APK metadata if an APK exists.

                if (
                    not self.result["package"]
                    and self.result["apk_path"]
                ):

                    self._discover_from_apk(
                        self.result["apk_path"]
                    )

                return self.result

            raise APKDiscoveryError(
                "Unsupported filesystem input."
            )

        # -----------------------------------------------------
        # Runtime package input
        # -----------------------------------------------------

        # If the supplied value does not exist on the host,
        # treat it as a possible Android package name.
        #
        # Example:
        #
        #     com.example.application
        #
        # No package name is hard-coded here.

        if self._looks_like_package_name(
            self.input_path
        ):

            return self._discover_installed_package(
                self.input_path
            )

        raise APKDiscoveryError(
            f"Input does not exist and is not a valid "
            f"Android package name: {self.input_path}"
        )

    # =========================================================
    # INSTALLED PACKAGE DISCOVERY
    # =========================================================

    def _discover_installed_package(
        self,
        package
    ):

        print()
        print("=" * 60)
        print("        INSTALLED APK DISCOVERY")
        print("=" * 60)
        print(
            f"Package : {package}"
        )

        # -----------------------------------------------------
        # Confirm package exists on device.
        # -----------------------------------------------------

        package_dump = self._adb_shell(
            [
                "dumpsys",
                "package",
                package,
            ]
        )

        if package_dump is None:

            raise APKDiscoveryError(
                "Could not query Android package manager."
            )

        if (
            f"Package [{package}]" not in package_dump
            and f"Package: {package}" not in package_dump
        ):

            # Some Android versions format dumpsys differently.
            # Fall back to pm path before deciding that the
            # package is unavailable.

            apk_paths = self._get_installed_apk_paths(
                package
            )

            if not apk_paths:

                raise APKDiscoveryError(
                    f"Package is not installed on the connected device: "
                    f"{package}"
                )

        else:

            apk_paths = self._get_installed_apk_paths(
                package
            )

        if not apk_paths:

            raise APKDiscoveryError(
                f"Could not determine installed APK path for package: "
                f"{package}"
            )

        self.result["package"] = package

        # Prefer base.apk when split APKs are installed.

        base_apk = None

        for path in apk_paths:

            if path.endswith("/base.apk"):

                base_apk = path
                break

        self.result["installed_apk_path"] = (
            base_apk or apk_paths[0]
        )

        # -----------------------------------------------------
        # Extract runtime metadata.
        # -----------------------------------------------------

        self._discover_runtime_metadata(
            package_dump,
            package
        )

        print(
            f"Installed APK : "
            f"{self.result['installed_apk_path']}"
        )

        if self.result["activity"]:

            print(
                f"Launcher      : "
                f"{self.result['activity']}"
            )

        if self.result["application_label"]:

            print(
                f"Application   : "
                f"{self.result['application_label']}"
            )

        print("=" * 60)

        return self.result

    # =========================================================
    # ADB
    # =========================================================

    def _adb_command(
        self,
        arguments
    ):

        command = ["adb"]

        if self.serial:

            command.extend(
                [
                    "-s",
                    self.serial,
                ]
            )

        command.extend(arguments)

        return command

    def _adb_shell(
        self,
        arguments,
        timeout=30
    ):

        command = self._adb_command(
            ["shell"] + arguments
        )

        try:

            result = subprocess.run(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=timeout,
            )

        except Exception:

            return None

        if result.returncode != 0:

            return None

        return result.stdout or ""

    # =========================================================
    # INSTALLED APK PATH
    # =========================================================

    def _get_installed_apk_paths(
        self,
        package
    ):

        output = self._adb_shell(
            [
                "pm",
                "path",
                package,
            ]
        )

        if not output:

            return []

        paths = []

        for line in output.splitlines():

            line = line.strip()

            if not line.startswith(
                "package:"
            ):

                continue

            path = line[
                len("package:"):
            ].strip()

            if path:

                paths.append(path)

        return paths

    # =========================================================
    # RUNTIME METADATA
    # =========================================================

    def _discover_runtime_metadata(
        self,
        package_dump,
        package
    ):

        # -----------------------------------------------------
        # Application label
        # -----------------------------------------------------

        label_patterns = [
            r"application-label='([^']*)'",
            r"application-label=([^\s]+)",
            r"label=([^\s]+)",
        ]

        for pattern in label_patterns:

            match = re.search(
                pattern,
                package_dump,
                re.IGNORECASE
            )

            if match:

                label = match.group(1).strip()

                if label:

                    self.result[
                        "application_label"
                    ] = label

                    break

        # -----------------------------------------------------
        # Launcher activity
        # -----------------------------------------------------

        activity = (
            self._find_launcher_activity(
                package_dump,
                package
            )
        )

        if activity:

            self.result["activity"] = (
                self._normalize_activity(
                    activity,
                    package
                )
            )

        # -----------------------------------------------------
        # Package
        # -----------------------------------------------------

        if not self.result["package"]:

            self.result["package"] = package

    # =========================================================
    # LAUNCHER ACTIVITY
    # =========================================================

    def _find_launcher_activity(
        self,
        package_dump,
        package
    ):

        # -----------------------------------------------------
        # Preferred method:
        # Ask Android Package Manager directly.
        # -----------------------------------------------------

        resolved = self._adb_shell(
            [
                "cmd",
                "package",
                "resolve-activity",
                "--brief",
                "-a",
                "android.intent.action.MAIN",
                "-c",
                "android.intent.category.LAUNCHER",
                package,
            ]
        )

        if resolved:

            lines = [
                line.strip()
                for line in resolved.splitlines()
                if line.strip()
            ]

            for line in reversed(lines):

                if "/" not in line:
                    continue

                if line.startswith("priority="):
                    continue

                if line.startswith(
                    package + "/"
                ):

                    return line

        # -----------------------------------------------------
        # Fallback to dumpsys parser.
        # -----------------------------------------------------

        return self._find_launcher_activity_from_dump(
            package_dump,
            package
        )

    # =========================================================
    # LAUNCHER ACTIVITY FROM DUMPSYS
    # =========================================================

    @staticmethod
    def _find_launcher_activity_from_dump(
        package_dump,
        package
    ):

        lines = package_dump.splitlines()

        # -----------------------------------------------------
        # MAIN resolver table.
        # -----------------------------------------------------

        for index, line in enumerate(lines):

            if (
                "android.intent.action.MAIN"
                not in line
            ):
                continue

            window_start = max(
                0,
                index - 20
            )

            window_end = min(
                len(lines),
                index + 40
            )

            window = "\n".join(
                lines[
                    window_start:window_end
                ]
            )

            activity_match = re.search(
                rf"\b{re.escape(package)}/"
                rf"([A-Za-z0-9_.$]+)",
                window
            )

            if activity_match:

                return (
                    package
                    + "/"
                    + activity_match.group(1)
                )

        # -----------------------------------------------------
        # Generic component fallback.
        # -----------------------------------------------------

        component_matches = re.findall(
            rf"\b{re.escape(package)}/"
            rf"([A-Za-z0-9_.$]+)",
            package_dump
        )

        for component in component_matches:

            if not component:
                continue

            if (
                "Activity" in component
                or component.endswith(
                    "$Activity"
                )
            ):

                return (
                    package
                    + "/"
                    + component
                )

        return None


    # =========================================================
    # APK DISCOVERY
    # =========================================================

    def _discover_from_apk(
        self,
        apk_path
    ):

        aapt = self._find_aapt()

        if not aapt:

            raise APKDiscoveryError(
                "aapt was not found. "
                "Make sure Android SDK build-tools are installed."
            )

        command = [
            aapt,
            "dump",
            "badging",
            apk_path,
        ]

        try:

            result = subprocess.run(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=30,
            )

        except Exception as exc:

            raise APKDiscoveryError(
                f"Failed to inspect APK: {exc}"
            )

        if result.returncode != 0:

            raise APKDiscoveryError(
                "aapt could not inspect APK:\n"
                + result.stderr
            )

        output = result.stdout

        # -----------------------------------------------------
        # Package
        # -----------------------------------------------------

        package_match = re.search(
            r"package:\s+name='([^']+)'",
            output
        )

        if package_match:

            self.result["package"] = (
                package_match.group(1)
            )

        # -----------------------------------------------------
        # Application label
        # -----------------------------------------------------

        label_match = re.search(
            r"application-label:'([^']*)'",
            output
        )

        if label_match:

            self.result["application_label"] = (
                label_match.group(1)
            )

        # -----------------------------------------------------
        # Launcher activity
        # -----------------------------------------------------

        activity_match = re.search(
            r"launchable-activity:\s+name='([^']+)'",
            output
        )

        if activity_match:

            self.result["activity"] = (
                activity_match.group(1)
            )

        if not self.result["package"]:

            raise APKDiscoveryError(
                "Package name could not be extracted from APK."
            )

    # =========================================================
    # MANIFEST DISCOVERY
    # =========================================================

    def _discover_from_manifest(
        self,
        manifest
    ):

        try:

            with open(
                manifest,
                "r",
                encoding="utf-8",
                errors="ignore"
            ) as file:

                text = file.read()

        except Exception:

            return

        # -----------------------------------------------------
        # Package
        # -----------------------------------------------------

        package_match = re.search(
            r'<manifest[^>]+package\s*=\s*"([^"]+)"',
            text,
            re.IGNORECASE
        )

        if package_match:

            self.result["package"] = (
                package_match.group(1)
            )

        # -----------------------------------------------------
        # Activity
        #
        # Look for an activity containing MAIN + LAUNCHER.
        # -----------------------------------------------------

        activity_blocks = re.findall(
            r"<activity\b.*?</activity>",
            text,
            re.IGNORECASE | re.DOTALL
        )

        for block in activity_blocks:

            has_main = re.search(
                r'android\.intent\.action\.MAIN',
                block,
                re.IGNORECASE
            )

            has_launcher = re.search(
                r'android\.intent\.category\.LAUNCHER',
                block,
                re.IGNORECASE
            )

            if not (
                has_main
                and has_launcher
            ):

                continue

            name_match = re.search(
                r'android:name\s*=\s*"([^"]+)"',
                block
            )

            if not name_match:
                continue

            activity = name_match.group(1)

            self.result["activity"] = (
                self._normalize_activity(
                    activity,
                    self.result["package"]
                )
            )

            break

    # =========================================================
    # PROJECT ROOT
    # =========================================================

    @staticmethod
    def _find_project_root(
        path
    ):

        current = Path(path).resolve()

        candidates = [
            current,
        ]

        # Search upward in case a module directory
        # was supplied.

        candidates.extend(
            current.parents
        )

        for candidate in candidates:

            settings = (
                candidate
                / "settings.gradle"
            )

            settings_kts = (
                candidate
                / "settings.gradle.kts"
            )

            gradlew = (
                candidate
                / "gradlew"
            )

            if (
                settings.exists()
                or settings_kts.exists()
                or gradlew.exists()
            ):

                return str(candidate)

        return None

    # =========================================================
    # MANIFEST
    # =========================================================

    @staticmethod
    def _find_manifest(
        project_root
    ):

        preferred = [
            os.path.join(
                project_root,
                "app",
                "src",
                "main",
                "AndroidManifest.xml",
            ),
            os.path.join(
                project_root,
                "src",
                "main",
                "AndroidManifest.xml",
            ),
        ]

        for path in preferred:

            if os.path.isfile(path):

                return path

        # Generic search

        for root, dirs, files in os.walk(
            project_root
        ):

            # Avoid build directories.

            dirs[:] = [
                d
                for d in dirs
                if d not in {
                    ".gradle",
                    ".idea",
                    "build",
                }
            ]

            if "AndroidManifest.xml" in files:

                return os.path.join(
                    root,
                    "AndroidManifest.xml"
                )

        return None

    # =========================================================
    # SOURCE ROOT
    # =========================================================

    @staticmethod
    def _find_source_root(
        project_root
    ):

        candidates = [
            os.path.join(
                project_root,
                "app",
                "src",
                "main",
            ),
            os.path.join(
                project_root,
                "src",
                "main",
            ),
        ]

        for path in candidates:

            if os.path.isdir(path):

                return path

        # Generic source search

        for root, dirs, files in os.walk(
            project_root
        ):

            dirs[:] = [
                d
                for d in dirs
                if d not in {
                    ".gradle",
                    ".idea",
                    "build",
                }
            ]

            if (
                "AndroidManifest.xml" in files
                and (
                    "java" in dirs
                    or "kotlin" in dirs
                    or "cpp" in dirs
                )
            ):

                return root

        return None

    # =========================================================
    # BUILD SYSTEM
    # =========================================================

    @staticmethod
    def _detect_build_system(
        project_root
    ):

        if os.path.isfile(
            os.path.join(
                project_root,
                "gradlew"
            )
        ):

            return "gradle"

        if os.path.isfile(
            os.path.join(
                project_root,
                "build.gradle"
            )
        ):

            return "gradle"

        if os.path.isfile(
            os.path.join(
                project_root,
                "build.gradle.kts"
            )
        ):

            return "gradle"

        return None

    # =========================================================
    # APK SEARCH
    # =========================================================

    @staticmethod
    def _find_existing_apk(
        project_root
    ):

        apk_candidates = []

        for root, dirs, files in os.walk(
            project_root
        ):

            dirs[:] = [
                d
                for d in dirs
                if d not in {
                    ".gradle",
                    ".idea",
                }
            ]

            for filename in files:

                if not filename.endswith(
                    ".apk"
                ):

                    continue

                if "debug" in filename.lower():

                    apk_candidates.append(
                        os.path.join(
                            root,
                            filename
                        )
                    )

        if not apk_candidates:

            for root, dirs, files in os.walk(
                project_root
            ):

                dirs[:] = [
                    d
                    for d in dirs
                    if d not in {
                        ".gradle",
                        ".idea",
                    }
                ]

                for filename in files:

                    if filename.endswith(
                        ".apk"
                    ):

                        apk_candidates.append(
                            os.path.join(
                                root,
                                filename
                            )
                        )

        if not apk_candidates:

            return None

        # Prefer the newest APK.

        apk_candidates.sort(
            key=lambda path: os.path.getmtime(
                path
            ),
            reverse=True
        )

        return apk_candidates[0]

    # =========================================================
    # AAPT
    # =========================================================

    @staticmethod
    def _find_aapt():

        # First try PATH.

        try:

            result = subprocess.run(
                ["which", "aapt"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=5,
            )

            if result.returncode == 0:

                path = result.stdout.strip()

                if path:

                    return path

        except Exception:

            pass

        # Try Android SDK environment.

        sdk = (
            os.environ.get("ANDROID_HOME")
            or os.environ.get("ANDROID_SDK_ROOT")
        )

        if sdk:

            build_tools = os.path.join(
                sdk,
                "build-tools"
            )

            if os.path.isdir(
                build_tools
            ):

                versions = sorted(
                    os.listdir(
                        build_tools
                    ),
                    reverse=True
                )

                for version in versions:

                    path = os.path.join(
                        build_tools,
                        version,
                        "aapt"
                    )

                    if os.path.isfile(path):

                        return path

        # Common Linux Android SDK location.

        home_sdk = os.path.expanduser(
            "~/Android/Sdk"
        )

        build_tools = os.path.join(
            home_sdk,
            "build-tools"
        )

        if os.path.isdir(
            build_tools
        ):

            versions = sorted(
                os.listdir(
                    build_tools
                ),
                reverse=True
            )

            for version in versions:

                path = os.path.join(
                    build_tools,
                    version,
                    "aapt"
                )

                if os.path.isfile(path):

                    return path

        return None

    # =========================================================
    # PACKAGE NAME DETECTION
    # =========================================================

    @staticmethod
    def _looks_like_package_name(
        value
    ):

        if not value:

            return False

        # Android application IDs normally consist of
        # dot-separated Java-style identifiers.

        return bool(
            re.fullmatch(
                r"[A-Za-z_][A-Za-z0-9_]*"
                r"(?:\.[A-Za-z_][A-Za-z0-9_]*)+",
                value.strip()
            )
        )

    # =========================================================
    # ACTIVITY NORMALIZATION
    # =========================================================

    @staticmethod
    def _normalize_activity(
        activity,
        package
    ):

        if not activity:

            return None

        # Handle package/class component form:
        #
        # com.example.app/.MainActivity

        if "/" in activity:

            activity = activity.split(
                "/",
                1
            )[1]

        if activity.startswith("."):

            if package:

                return (
                    package
                    + activity
                )

        if "." not in activity:

            if package:

                return (
                    package
                    + "."
                    + activity
                )

        return activity


# =============================================================
# CONVENIENCE FUNCTION
# =============================================================

def discover_android(
    input_path,
    serial=None
):

    discovery = APKDiscovery(
        input_path,
        serial=serial
    )

    return discovery.discover()
