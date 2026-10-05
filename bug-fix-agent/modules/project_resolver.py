from pathlib import Path
import os
import re


class ProjectResolver:
    """
    Dynamically resolve an Android package to its host source project.
    """

    def __init__(self, source_roots=None):
        if source_roots is not None:
            roots = [
                Path(root).expanduser().resolve()
                for root in source_roots
                if root
            ]
        else:
            roots = self.discover_source_roots()

        self.source_roots = self._normalize_roots(roots)

    def discover_source_roots(self):
        roots = []

        configured = os.environ.get(
            "VAMP_SOURCE_ROOTS",
            ""
        ).strip()

        if configured:
            for value in configured.split(os.pathsep):
                value = value.strip()

                if not value:
                    continue

                path = Path(value).expanduser()

                if path.is_dir():
                    roots.append(path.resolve())

        home = Path.home()

        if home.is_dir():
            roots.append(home.resolve())

        return self._normalize_roots(roots)

    @staticmethod
    def _normalize_roots(roots):
        result = []
        seen = set()

        for root in roots:
            try:
                path = Path(root).expanduser().resolve()
            except Exception:
                continue

            if not path.is_dir():
                continue

            if path in seen:
                continue

            seen.add(path)
            result.append(path)

        return result

    def resolve(self, package):
        if not package:
            return None

        print(f"Resolving source project: {package}")

        candidates = []

        for root in self.source_roots:
            if not root.exists():
                continue

            for project in self.find_projects(root):
                score = self.score_project(
                    project,
                    package
                )

                if score <= 0:
                    continue

                candidates.append(
                    (score, project)
                )

                if score >= 500:
                    result = self._build_result(
                        project,
                        package,
                        score
                    )

                    print(
                        f"Project found: {result['workspace']}"
                    )

                    return result

        if not candidates:
            print(
                f"Project not found: {package}"
            )
            return None

        unique_candidates = {}

        for score, project in candidates:
            project = project.resolve()

            previous = unique_candidates.get(project)

            if previous is None or score > previous:
                unique_candidates[project] = score

        candidates = [
            (score, project)
            for project, score
            in unique_candidates.items()
        ]

        candidates.sort(
            key=lambda item: item[0],
            reverse=True
        )

        score, module = candidates[0]

        result = self._build_result(
            module,
            package,
            score
        )

        print(
            f"Project found: {result['workspace']}"
        )

        return result

    @staticmethod
    def _build_result(
        module,
        package,
        score
    ):
        project_root = ProjectResolver.find_project_root(
            module
        )

        return {
            "workspace": str(project_root),
            "module": str(module),
            "package": package,
            "score": score
        }

    def find_projects(self, root):
        root = Path(root).resolve()

        excluded_names = {
            ".cache",
            ".cargo",
            ".config",
            ".git",
            ".gradle",
            ".idea",
            ".local",
            ".mozilla",
            ".npm",
            ".rustup",
            ".sdkman",
            ".venv",
            "build",
            "cache",
            "node_modules",
            "proc",
            "snap",
            "sys",
            "tmp",
            "venv",
        }

        projects = []
        seen = set()

        def add_project(path):
            try:
                path = Path(path).resolve()
            except Exception:
                return

            if path in seen:
                return

            if not path.is_dir():
                return

            if self.looks_like_android_project(path):
                seen.add(path)
                projects.append(path)

        add_project(root)

        try:
            children = list(root.iterdir())
        except (PermissionError, OSError):
            children = []

        for child in children:
            if not child.is_dir():
                continue

            if child.name in excluded_names:
                continue

            if child.name.startswith("."):
                continue

            add_project(child)

            try:
                grandchildren = list(child.iterdir())
            except (PermissionError, OSError):
                continue

            for grandchild in grandchildren:
                if not grandchild.is_dir():
                    continue

                if grandchild.name in excluded_names:
                    continue

                if grandchild.name.startswith("."):
                    continue

                add_project(grandchild)

        if projects:
            return projects

        try:
            for current, dirs, files in os.walk(
                root,
                topdown=True,
                followlinks=False
            ):
                current_path = Path(current)

                dirs[:] = [
                    directory
                    for directory in dirs
                    if directory not in excluded_names
                    and not directory.startswith(".")
                ]

                file_set = set(files)

                if not (
                    "build.gradle" in file_set
                    or "build.gradle.kts" in file_set
                    or "AndroidManifest.xml" in file_set
                    or "gradlew" in file_set
                ):
                    continue

                if self.looks_like_android_project(
                    current_path
                ):
                    add_project(current_path)

        except (PermissionError, OSError):
            pass

        return projects

    @staticmethod
    def looks_like_android_project(path):
        path = Path(path)

        has_gradle = (
            (path / "build.gradle").is_file()
            or
            (path / "build.gradle.kts").is_file()
        )

        has_wrapper = (
            (path / "gradlew").is_file()
        )

        manifest_locations = [
            path
            / "src"
            / "main"
            / "AndroidManifest.xml",

            path
            / "app"
            / "src"
            / "main"
            / "AndroidManifest.xml",
        ]

        has_manifest = any(
            manifest.is_file()
            for manifest in manifest_locations
        )

        return bool(
            has_gradle
            or has_wrapper
            or has_manifest
        )

    def score_project(
        self,
        project,
        package
    ):
        """
        Score an Android project using package-specific evidence.

        No project names, source roots, or application packages are
        hard-coded here. Generic Android structure alone is not enough
        to produce a strong match.
        """

        score = 0

        package_path = package.replace(".", "/")

        build_files = [
            project / "build.gradle",
            project / "build.gradle.kts",
        ]

        existing_build_files = [
            file
            for file in build_files
            if file.is_file()
        ]

        manifest_files = list(
            project.rglob("AndroidManifest.xml")
        )

        manifest_exact = False
        manifest_contains = False

        for manifest in manifest_files:
            try:
                text = manifest.read_text(
                    encoding="utf-8",
                    errors="ignore"
                )
            except Exception:
                continue

            if re.search(
                rf'\bpackage\s*=\s*["\']'
                rf'{re.escape(package)}'
                rf'["\']',
                text
            ):
                manifest_exact = True

            if package in text:
                manifest_contains = True

        build_exact = False
        namespace_exact = False

        for build_file in existing_build_files:
            try:
                text = build_file.read_text(
                    encoding="utf-8",
                    errors="ignore"
                )
            except Exception:
                continue

            if re.search(
                rf'applicationId\s*[=:]\s*'
                rf'["\']{re.escape(package)}["\']',
                text
            ):
                build_exact = True

            if re.search(
                rf'namespace\s*[=:]\s*'
                rf'["\']{re.escape(package)}["\']',
                text
            ):
                namespace_exact = True

        source_matches = []

        package_parts = package_path.split("/")
        current = project

        for part in package_parts:
            current = current / part

        if current.is_dir():
            source_matches.append(current)

        # Exact package evidence is the primary requirement.
        if manifest_exact:
            score += 500

        if build_exact:
            score += 500

        if namespace_exact:
            score += 300

        if source_matches:
            score += 300

        if manifest_contains and not manifest_exact:
            score += 100

        # Generic Android structure is only a small tie-breaker.
        if existing_build_files:
            score += 10

        if (project / "gradlew").is_file():
            score += 5

        return score

    def find_manifests(project):
        manifests = []

        preferred = [
            project
            / "src"
            / "main"
            / "AndroidManifest.xml",

            project
            / "app"
            / "src"
            / "main"
            / "AndroidManifest.xml",
        ]

        for manifest in preferred:
            if manifest.is_file():
                manifests.append(manifest)

        try:
            for current, dirs, files in os.walk(
                project,
                topdown=True,
                followlinks=False
            ):
                dirs[:] = [
                    directory
                    for directory in dirs
                    if directory not in {
                        ".gradle",
                        ".idea",
                        "build",
                        ".git",
                    }
                ]

                if "AndroidManifest.xml" not in files:
                    continue

                manifest = (
                    Path(current)
                    / "AndroidManifest.xml"
                )

                if manifest not in manifests:
                    manifests.append(manifest)

        except (PermissionError, OSError):
            pass

        return manifests

    @staticmethod
    def find_package_directories(
        project,
        package_path
    ):
        matches = []

        source_roots = [
            project
            / "src"
            / "main"
            / "java",

            project
            / "src"
            / "main"
            / "kotlin",

            project
            / "src"
            / "main"
            / "cpp",
        ]

        for source_root in source_roots:
            package_dir = (
                source_root
                / package_path
            )

            if package_dir.is_dir():
                matches.append(package_dir)

        return matches

    @staticmethod
    def find_project_root(module):
        current = module.resolve()

        while True:
            gradlew = current / "gradlew"
            settings = current / "settings.gradle"
            settings_kts = current / "settings.gradle.kts"

            if (
                gradlew.is_file()
                or settings.is_file()
                or settings_kts.is_file()
            ):
                return current

            parent = current.parent

            if parent == current:
                break

            current = parent

        return module.resolve()


if __name__ == "__main__":
    package = input(
        "Enter package name: "
    ).strip()

    resolver = ProjectResolver()
    result = resolver.resolve(package)

    if result:
        print(f"Workspace: {result['workspace']}")
        print(f"Module: {result['module']}")
        print(f"Package: {result['package']}")
        print(f"Score: {result['score']}")
    else:
        print("Project could not be resolved.")
