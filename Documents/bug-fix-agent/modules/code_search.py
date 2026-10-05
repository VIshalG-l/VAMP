from pathlib import Path


def score_candidate(path, report):
    """
    Score a candidate source file.

    Higher score = more likely to be the correct source.
    """

    score = 0

    package = report.get("package") or ""
    classname = report.get("class") or ""
    filename = report.get("file") or ""

    p = str(path)

    # Exact filename
    if filename and path.name == filename:
        score += 100

    # Exact class name
    if classname and path.stem == classname:
        score += 80

    # Package path
    package_path = package.replace(".", "/")

    if package_path and package_path in p:
        score += 60

    # Prefer application source
    if "/src/main/" in p:
        score += 20

    # Prefer Java/Kotlin source
    if p.endswith(".java") or p.endswith(".kt"):
        score += 10

    return score


def find_source(workspace, report):
    """
    Locate the source file responsible for an ANR/Crash.

    Search order

    1. Stacktrace filename
    2. Class name
    3. Package hierarchy

    Returns
    -------
    dict or None
    """

    workspace = Path(workspace)

    filename = report.get("file")
    classname = report.get("class")
    package = report.get("package")

    candidates = []

    # -----------------------------------------
    # Search by filename
    # -----------------------------------------

    if filename:

        candidates.extend(workspace.rglob(filename))

    # -----------------------------------------
    # Search by classname
    # -----------------------------------------

    if classname:

        candidates.extend(workspace.rglob(f"{classname}.java"))
        candidates.extend(workspace.rglob(f"{classname}.kt"))

    # Remove duplicates

    candidates = list(dict.fromkeys(candidates))

    if not candidates:

        print("❌ No matching source file found.")

        return None

    # -----------------------------------------
    # Score candidates
    # -----------------------------------------

    scored = []

    for file in candidates:

        scored.append(
            (
                score_candidate(file, report),
                file
            )
        )

    scored.sort(reverse=True)

#    print("\n========== SOURCE SEARCH ==========")

    for score, file in scored:
        pass
        #print(f"{score:3}  {file}")

#    print("===================================\n")

    best = scored[0][1]

    return {
        "path": str(best.resolve()),
        "filename": best.name,
        "directory": str(best.parent),
        "package": package,
        "class": classname,
        "workspace": str(workspace.resolve())
    }
