import re


def parse_log(log_file):
    """
    Parse Android ANR, Java/Kotlin Crash and Native Crash logs.

    Supported:
        - ANR (traces.txt / bugreport)
        - Java Crash
        - Kotlin Crash
        - Native Crash (SIGSEGV)

    Returns:
        dict
    """

    with open(log_file, "r", errors="ignore") as f:
        text = f.read()


    report = {
        "type": "UNKNOWN",
        "package": None,
        "process": None,
        "pid": None,
        "reason": None,
        "exception": None,
        "thread": None,
        "class": None,
        "method": None,
        "file": None,
        "line": None,
        "stacktrace": "",
        "timestamp": None,
    }


    # ==================================================
    # Detect Bug Type
    # ==================================================

    if (
        "Input dispatching timed out" in text
        or "ANR in" in text
        or "Application Not Responding" in text
    ):

        report["type"] = "ANR"


    elif (
        "FATAL EXCEPTION" in text
        or "Caused by:" in text
        or "java.lang." in text
        or "Exception" in text
        or "Error" in text
    ):

        report["type"] = "CRASH"


    elif (
        "SIGSEGV" in text
        or "signal 11" in text
        or "backtrace:" in text
        or "Abort message" in text
    ):

        report["type"] = "NATIVE_CRASH"

    # ==================================================
    # Select Correct Crash Block
    # ==================================================

    crash_text = text

    if report["type"] == "CRASH":

        crash_blocks = re.split(
            r"(?=FATAL EXCEPTION)",
            text
        )

        selected = None

        for block in crash_blocks:

            m = re.search(
                r"Process:\s*([A-Za-z0-9._]+)",
                block
            )

            if not m:
                continue

            pkg = m.group(1)

        # Ignore Android framework crashes
            if pkg.startswith("com.android"):
                continue

            if pkg.startswith("android"):
                continue

            if pkg == "system_server":
                continue

        # First non-framework crash
            selected = block
            break

        if selected:
            crash_text = selected

    # ==================================================
    # Select Correct Crash Block
    # ==================================================

    crash_text = text


    if report["type"] == "CRASH":

        crash_blocks = re.split(
            r"(?=FATAL EXCEPTION)",
            text
        )


        for block in crash_blocks:

            if "FATAL EXCEPTION" in block:

                crash_text = block

                # Prefer application crash
                # over framework crashes

                if "Process: com.example.displaycrashapp" in block:
                    break



    # ==================================================
    # ANR Reason
    # ==================================================

    if report["type"] == "ANR":

        m = re.search(
            r"Input dispatching timed out\s*\((.*?)\)",
            text,
            re.DOTALL,
        )

        if m:
            report["reason"] = m.group(1).strip()



    # ==================================================
    # Package
    # ==================================================

    patterns = [
        r'Process:\s*([A-Za-z0-9._]+)',
        r'Cmd line:\s*([A-Za-z0-9._]+)',
        r'Package:\s*([A-Za-z0-9._]+)',
    ]

    for pattern in patterns:

        m = re.search(pattern, crash_text)

        if not m:
            m = re.search(pattern, text)

        if m:
            report["package"] = m.group(1)
            break


    # ==================================================
    # Process
    # ==================================================

    m = re.search(
        r"Process:\s*([A-Za-z0-9._]+)",
        crash_text
    )


    if m:

        report["process"] = m.group(1)



    # ==================================================
    # PID
    # ==================================================

    m = re.search(
        r"PID:\s*(\d+)",
        crash_text
    )


    if not m:

        m = re.search(
            r"pid[:= ]+(\d+)",
            text
        )


    if m:

        report["pid"] = int(m.group(1))



    # ==================================================
    # Timestamp
    # ==================================================

    m = re.search(
        r"(\d\d-\d\d\s+\d\d:\d\d:\d+\.\d+)",
        text
    )


    if m:

        report["timestamp"] = m.group(1)



    # ==================================================
    # Thread
    # ==================================================

    m = re.search(
        r"FATAL EXCEPTION:\s*(.*)",
        crash_text
    )


    if m:

        report["thread"] = m.group(1).strip()



    elif '"main"' in text:

        report["thread"] = "main"



    # ==================================================
    # Exception
    # ==================================================

    m = re.search(
        r"([A-Za-z0-9_.]+Exception|[A-Za-z0-9_.]+Error)",
        crash_text
    )


    if m:

        report["exception"] = m.group(1)



    # ==================================================
    # First Application Stack Frame
    # ==================================================

    stack_match = re.findall(
        r'at\s+([A-Za-z0-9_.$]+)\.([A-Za-z0-9_$<>]+)\(([^:]+):(\d+)\)',
        crash_text
    )

    if stack_match:

        selected = None

    #    app_package = report["package"]
        app_package = report.get("package", "")
    # ------------------------------------------------
    # 1. Highest priority:
    # Frame belonging to application package
    # ------------------------------------------------

    for frame in stack_match:

        full_class = frame[0]

        if (
            "com.example.displaycrashapp" in full_class
            or (
                app_package
                and app_package in full_class
            )
        ):
            selected = frame
            break


    # ------------------------------------------------
    # 2. Ignore Android framework frames
    # ------------------------------------------------

    if selected is None:

        for frame in stack_match:

            full_class = frame[0]

            if not (
                full_class.startswith("android.")
                or full_class.startswith("java.")
                or full_class.startswith("kotlin.")
            ):
                selected = frame
                break


    # ------------------------------------------------
    # 3. Fallback: first frame
    # ------------------------------------------------

    if selected is None:
        selected = stack_match[0]


    class_path = selected[0]
    method = selected[1]
    file_name = selected[2]
    line = selected[3]


    report["method"] = method
    report["file"] = file_name
    report["line"] = int(line)


    # Convert:
    #
    # com.example.displaycrashapp.CrashRenderer
    #
    # into:
    #
    # CrashRenderer

    report["class"] = class_path.split(".")[-1]

    # ==================================================
    # Stack Trace
    # ==================================================

    if report["type"] == "ANR":


        m = re.search(
            r'"main".*?(?=\n\n"|----- end)',
            text,
            re.DOTALL
        )


        if m:

            report["stacktrace"] = m.group(0)



    else:


        stack = re.findall(
            r'at .+',
            crash_text
        )


        report["stacktrace"] = "\n".join(stack)



    # ==================================================
    # Console Summary
    # ==================================================

#    print("\n" + "=" * 55)
    print("LOG PARSER SUMMARY")
#    print("=" * 55)

#    print(f"Bug Type   : {report['type']}")
#    print(f"Package    : {report['package']}")
#    print(f"Process    : {report['process']}")
    print(f"PID        : {report['pid']}")
    print(f"Exception  : {report['exception']}")
    print(f"Reason     : {report['reason']}")
    print(f"Thread     : {report['thread']}")
    print(f"Class      : {report['class']}")
    print(f"Method     : {report['method']}")
    print(f"File       : {report['file']}")
    print(f"Line       : {report['line']}")

    print("=" * 55)



    return report
