import subprocess
import shutil
import zipfile
from pathlib import Path
from datetime import datetime


def run(cmd):
    return subprocess.run(
        cmd,
        text=True,
        capture_output=True
    )


def collect_logs(issue_type):
    """
    Collect Android logs after bug reproduction.
    """

    issue_type = issue_type.lower()

    BASE_DIR = Path.cwd() / "logs"

    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")

    LOG_DIR = BASE_DIR / issue_type / timestamp

    LOG_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

#    print("\n" + "=" * 60)
#    print("            COLLECTING LOGS")
#    print("=" * 60)

    ##########################################################
    # BUGREPORT (OPTIONAL)
    ##########################################################

    if issue_type == "anr":

        print("\n[1] Generating Bugreport...")

        bugreport = LOG_DIR / "bugreport.zip"

        result = subprocess.run(
            [
                "adb",
                "bugreport",
                str(bugreport)
            ],
            text=True,
            capture_output=True
        )

        if bugreport.exists():

            print("✅ Bugreport Generated")

            ######################################################

            print("\n[2] Extracting Bugreport...")

            extract_dir = LOG_DIR / "bugreport"

            if extract_dir.exists():
                shutil.rmtree(extract_dir)

            with zipfile.ZipFile(
                bugreport,
                "r"
            ) as z:

                z.extractall(extract_dir)

            print("✅ Extraction Complete")

            ######################################################

            print("\n[3] Finding Latest ANR Trace...")

            anr_dir = extract_dir / "FS" / "data" / "anr"

            if anr_dir.exists():

                traces = sorted(
                    anr_dir.glob("*"),
                    key=lambda f: f.stat().st_mtime,
                    reverse=True
                )

                if traces:

                    latest = traces[0]

                    shutil.copy(
                        latest,
                        LOG_DIR / "anr_trace.txt"
                    )

                    print("Latest Trace :", latest.name)

                else:

                    print("⚠ No ANR trace inside bugreport.")

            else:

                print("⚠ ANR directory missing inside bugreport.")

        else:

            print("⚠ Bugreport generation failed.")
            print("Continuing with fallback collection...")

            with open(
                LOG_DIR / "bugreport_error.txt",
                "w"
            ) as f:

                f.write(result.stdout)
                f.write(result.stderr)

            ######################################################
            # FALLBACK : Pull ANR traces directly
            ######################################################

            print("\nCollecting ANR traces directly...")

            ls = run(
                [
                    "adb",
                    "shell",
                    "ls",
                    "/data/anr"
                ]
            )

            if ls.returncode == 0:

                files = [
                    x.strip()
                    for x in ls.stdout.splitlines()
                    if x.strip()
                ]

                if files:

                    latest = files[-1]

                    subprocess.run(
                        [
                            "adb",
                            "pull",
                            f"/data/anr/{latest}",
                            str(LOG_DIR / "anr_trace.txt")
                        ]
                    )

                    print("✅ ANR Trace Pulled")

                else:

                    print("⚠ No ANR files found.")

            else:

                print("⚠ Unable to access /data/anr")

    else:

        print("\nSkipping Bugreport")

    ##########################################################
    # LOGCAT
    ##########################################################

    print("[4] Collecting Logcat...")

    with open(
        LOG_DIR / "logcat.txt",
        "w"
    ) as f:

        subprocess.run(
            [
                "adb",
                "logcat",
                "-d"
            ],
            stdout=f
        )

    print("✅ logcat collected")

    ##########################################################
    # ACTIVITY
    ##########################################################

    print("[5] Collecting Activity Dump...")

    with open(
        LOG_DIR / "activity.txt",
        "w"
    ) as f:

        subprocess.run(
            [
                "adb",
                "shell",
                "dumpsys",
                "activity"
            ],
            stdout=f
        )

    print("✅ activity dump collected")

    ##########################################################
    # WINDOW
    ##########################################################

    print("\n[6] Collecting Window Dump...")

    with open(
        LOG_DIR / "window.txt",
        "w"
    ) as f:

        subprocess.run(
            [
                "adb",
                "shell",
                "dumpsys",
                "window"
            ],
            stdout=f
        )

    print("✅ window dump collected")

    ##########################################################
    # MEMINFO
    ##########################################################

    print("\n[7] Collecting MemInfo...")

    with open(
        LOG_DIR / "meminfo.txt",
        "w"
    ) as f:

        subprocess.run(
            [
                "adb",
                "shell",
                "dumpsys",
                "meminfo"
            ],
            stdout=f
        )

    print("✅ meminfo collected")

    ##########################################################

#    print("\n" + "=" * 60)
    print("LOG COLLECTION COMPLETE")
#    print("=" * 60)

    print("Issue :", issue_type.upper())
    print("Logs  :", LOG_DIR)

    return str(LOG_DIR)


#############################################################

if __name__ == "__main__":

    print("1. ANR")
    print("2. Display")

    choice = input("\nChoice : ")

    issue = "anr" if choice == "1" else "display"

    path = collect_logs(issue)

    print("\nReturned Directory:")
    print(path)
