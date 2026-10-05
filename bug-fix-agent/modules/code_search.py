from pathlib import Path


# Generic Android + native source support.
SOURCE_EXTENSIONS = {
    ".kt",
    ".java",
    ".c",
    ".cc",
    ".cpp",
    ".cxx",
    ".h",
    ".hpp",
}

NATIVE_EXTENSIONS = {
    ".c",
    ".cc",
    ".cpp",
    ".cxx",
    ".h",
    ".hpp",
}


def _normalize(value):
    return str(value or "").replace("\\", "/")


def _simple_classname(classname):
    if not classname:
        return ""
    return classname.split(".")[-1]


def _is_framework_class(classname):
    if not classname:
        return False

    normalized = classname.strip()

    framework_prefixes = (
        "android.",
        "androidx.",
        "com.android.",
        "java.",
        "javax.",
        "kotlin.",
    )

    return normalized.startswith(framework_prefixes)


def score_candidate(path, report):
    score = 0

    package = report.get("package") or ""
    classname = report.get("class") or ""
    filename = report.get("file") or ""

    package_path = package.replace(".", "/")
    path_str = _normalize(path)

    if filename and path.name == filename:
        score += 500

    simple_classname = _simple_classname(classname)

    if simple_classname and path.stem == simple_classname:
        score += 400

    if package_path:
        if f"/{package_path}/" in path_str:
            score += 300

    if "/src/main/" in path_str:
        score += 100

    if path.suffix in SOURCE_EXTENSIONS:
        score += 50

    # Framework classes are useful evidence, but should not override
    # application source when resolving an application failure.
    if _is_framework_class(classname):
        score -= 400

    return score


def _package_directory(workspace, package):
    if not package:
        return None

    package_parts = package.split(".")

    search_roots = [
        workspace / "src" / "main",
        workspace / "app" / "src" / "main",
    ]

    for root in search_roots:
        if not root.is_dir():
            continue

        for source_root in (
            root / "java",
            root / "kotlin",
        ):
            package_dir = source_root.joinpath(*package_parts)

            if package_dir.is_dir():
                return package_dir

    return None


def _source_roots(workspace):
    roots = []

    for root in (
        workspace / "src" / "main",
        workspace / "app" / "src" / "main",
    ):
        if root.is_dir():
            roots.append(root)

    return roots


def _find_in_directory(
    directory,
    filename=None,
    classname=None,
):
    if not directory or not directory.is_dir():
        return []

    candidates = []

    if filename:
        exact = directory / filename

        if exact.is_file():
            candidates.append(exact)

    if classname:
        simple_classname = _simple_classname(classname)

        for extension in SOURCE_EXTENSIONS:
            candidate = directory / (
                f"{simple_classname}{extension}"
            )

            if candidate.is_file():
                candidates.append(candidate)

    return candidates


def _read_text(path):
    try:
        return Path(path).read_text(
            encoding="utf-8",
            errors="ignore",
        )
    except Exception:
        return ""


def _jni_class_name(classname):
    """
    Convert a Java/Kotlin class name into the normal JNI symbol prefix.

    Example:

        com.example.nativecrash.MainActivity

    becomes:

        Java_com_example_nativecrash_MainActivity
    """

    if not classname:
        return ""

    value = classname.strip()

    # Remove nested-class separators.
    value = value.replace("$", "_")

    # JNI encodes underscores as _1.
    value = value.replace("_", "_1")

    value = value.replace(".", "_")

    return f"Java_{value}"


def _jni_method_candidates(
    classname,
    method,
):
    candidates = []

    if not classname or not method:
        return candidates

    prefix = _jni_class_name(classname)

    if not prefix:
        return candidates

    method = method.strip()

    if not method:
        return candidates

    # Normal JNI exported symbol.
    candidates.append(
        f"{prefix}_{method}"
    )

    # A small compatibility form for overloaded JNI methods.
    candidates.append(
        f"{prefix}_{method}__"
    )

    return list(dict.fromkeys(candidates))


def _search_text_for_symbols(
    workspace,
    symbols,
):
    if not symbols:
        return []

    matches = []

    for root in _source_roots(workspace):
        for path in root.rglob("*"):

            if not path.is_file():
                continue

            if path.suffix.lower() not in NATIVE_EXTENSIONS:
                continue

            try:
                text = _read_text(path)

                if not text:
                    continue

                for symbol in symbols:
                    if symbol in text:
                        matches.append(path)
                        break

            except Exception:
                continue

    return list(dict.fromkeys(matches))


def _find_external_methods(activity_source):
    """
    Find Kotlin/Java external/native method declarations.

    Examples supported:

        private external fun triggerNativeCrash()

        external fun nativeCrash()

        public external fun doSomething()

        private external fun nativeCall(value: Int): Int
    """

    if not activity_source:
        return []

    text = _read_text(
        activity_source.get("path", "")
    )

    if not text:
        return []

    import re

    pattern = re.compile(
        r"\bexternal\s+fun\s+"
        r"([A-Za-z_][A-Za-z0-9_]*)\s*\(",
        re.MULTILINE,
    )

    methods = pattern.findall(text)

    return list(dict.fromkeys(methods))


def find_native_source(
    workspace,
    report,
    source=None,
):
    """
    Resolve native C/C++ source for an Android native crash.

    Resolution strategy:

        Activity source
             |
             v
        external fun declaration
             |
             v
        JNI symbol
             |
             v
        C/C++ implementation

    No application package, class, method, or source path is hard-coded.
    """

    workspace = Path(workspace)

    if not workspace.is_dir():
        return None

    package = (
        report.get("package")
        or ""
    )

    classname = (
        report.get("class")
        or ""
    )

    method = (
        report.get("method")
        or ""
    )

    activity_source = source

    # ----------------------------------------------------------
    # Locate application source if it was not supplied.
    # ----------------------------------------------------------

    if not activity_source and classname:

        simple_classname = _simple_classname(
            classname
        )

        candidates = []

        for root in _source_roots(workspace):
            for extension in (
                ".kt",
                ".java",
            ):
                candidates.extend(
                    root.rglob(
                        f"{simple_classname}{extension}"
                    )
                )

        if candidates:
            candidates.sort(
                key=lambda path: (
                    0
                    if package
                    and f"/{package.replace('.', '/')}/"
                    in _normalize(path)
                    else 1,
                    str(path),
                )
            )

            activity_source = {
                "path": str(
                    candidates[0].resolve()
                ),
                "filename": candidates[0].name,
                "directory": str(
                    candidates[0].parent
                ),
                "package": package,
                "class": classname,
                "workspace": str(
                    workspace.resolve()
                ),
            }

    # ----------------------------------------------------------
    # Determine native method names.
    # ----------------------------------------------------------

    methods = []

    if method:
        methods.append(method)

    if activity_source:
        methods.extend(
            _find_external_methods(
                activity_source
            )
        )

    methods = list(
        dict.fromkeys(
            item
            for item in methods
            if item
        )
    )

    # ----------------------------------------------------------
    # Search by JNI symbol.
    # ----------------------------------------------------------

    symbols = []

    for native_method in methods:
        symbols.extend(
            _jni_method_candidates(
                classname,
                native_method,
            )
        )

    symbols = list(
        dict.fromkeys(symbols)
    )

    native_candidates = []

    if symbols:
        native_candidates = (
            _search_text_for_symbols(
                workspace,
                symbols,
            )
        )

    # ----------------------------------------------------------
    # If JNI symbol search did not find anything, search
    # for the native method name directly in C/C++ files.
    # ----------------------------------------------------------

    if not native_candidates and methods:

        for root in _source_roots(workspace):

            for path in root.rglob("*"):

                if not path.is_file():
                    continue

                if (
                    path.suffix.lower()
                    not in NATIVE_EXTENSIONS
                ):
                    continue

                text = _read_text(path)

                if not text:
                    continue

                if any(
                    native_method in text
                    for native_method in methods
                ):
                    native_candidates.append(path)

    native_candidates = list(
        dict.fromkeys(native_candidates)
    )

    if not native_candidates:
        return None

    # ----------------------------------------------------------
    # Prefer actual implementation files over headers.
    # ----------------------------------------------------------

    def native_score(path):
        score = 0

        if path.suffix.lower() in {
            ".c",
            ".cc",
            ".cpp",
            ".cxx",
        }:
            score += 100

        if "/cpp/" in _normalize(path):
            score += 50

        if "/src/main/" in _normalize(path):
            score += 25

        return score

    native_candidates.sort(
        key=lambda path: (
            native_score(path),
            str(path),
        ),
        reverse=True,
    )

    best = native_candidates[0]

    print(
        "Native source found:",
        best,
    )

    return {
        "path": str(best.resolve()),
        "filename": best.name,
        "directory": str(best.parent),
        "package": package,
        "class": classname,
        "method": method,
        "workspace": str(
            workspace.resolve()
        ),
        "native": True,
    }


def find_source(workspace, report):
    workspace = Path(workspace)

    if not workspace.is_dir():
        print(
            f"Source workspace not found: {workspace}"
        )
        return None

    filename = report.get("file")
    classname = report.get("class")
    package = report.get("package")

    candidates = []

    package_dir = _package_directory(
        workspace,
        package,
    )

    if package_dir:

        candidates.extend(
            _find_in_directory(
                package_dir,
                filename,
                classname,
            )
        )

        if not candidates:

            if filename:
                candidates.extend(
                    package_dir.rglob(filename)
                )

            if classname:
                simple_classname = (
                    _simple_classname(classname)
                )

                for extension in (
                    ".kt",
                    ".java",
                ):
                    candidates.extend(
                        package_dir.rglob(
                            f"{simple_classname}{extension}"
                        )
                    )

    # ----------------------------------------------------------
    # Generic source-root search.
    # ----------------------------------------------------------

    if not candidates:

        for source_root in _source_roots(
            workspace
        ):

            if filename:
                candidates.extend(
                    source_root.rglob(filename)
                )

            if classname:
                simple_classname = (
                    _simple_classname(classname)
                )

                for extension in (
                    ".kt",
                    ".java",
                ):
                    candidates.extend(
                        source_root.rglob(
                            f"{simple_classname}{extension}"
                        )
                    )

    candidates = list(
        dict.fromkeys(candidates)
    )

    if not candidates:
        print(
            "Source file not found."
        )
        return None

    # ----------------------------------------------------------
    # Avoid allowing framework stack frames to select
    # unrelated application source.
    # ----------------------------------------------------------

    scored = [
        (
            score_candidate(
                path,
                report,
            ),
            path,
        )
        for path in candidates
    ]

    scored.sort(
        key=lambda item: (
            item[0],
            str(item[1]),
        ),
        reverse=True,
    )

    best_score, best = scored[0]

    # A framework-only source report should not be treated
    # as an application source match.
    if (
        _is_framework_class(classname)
        and best_score < 300
    ):
        print(
            "Stack frame belongs to framework/system code."
        )
        print(
            "Application source will be resolved separately."
        )
        return None

    print(
        f"Source found: {best}"
    )

    return {
        "path": str(
            best.resolve()
        ),
        "filename": best.name,
        "directory": str(
            best.parent
        ),
        "package": package,
        "class": classname,
        "workspace": str(
            workspace.resolve()
        ),
    }
