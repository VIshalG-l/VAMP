import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# ============================================================
# Gemini
# ============================================================

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")


# ============================================================
# Project Root
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parent


# ============================================================
# Default Demo Workspace
# ============================================================

HOME = Path.home()

# ANR Project
ANR_WORKSPACE = HOME / "AndroidStudioProjects" / "DEMO"

# Crash Project
CRASH_WORKSPACE = HOME / "AndroidStudioProjects" / "DisplayCrashApp"


# ============================================================
# Logs
# ============================================================

LOGS_ROOT = PROJECT_ROOT / "modules" / "logs"


def get_latest_log(issue_type, log_name="logcat.txt"):
    """
    Return the latest collected log file.

    Example:
        get_latest_log("anr", "anr_trace.txt")
        get_latest_log("anr", "logcat.txt")
        get_latest_log("display", "logcat.txt")
    """

    issue_dir = LOGS_ROOT / issue_type.lower()

    if not issue_dir.exists():
        return ""

    log_files = list(issue_dir.glob(f"*/{log_name}"))

    if not log_files:
        return ""

    latest = max(
        log_files,
        key=lambda file: file.parent.stat().st_mtime
    )

    return str(latest)


# ============================================================
# Default Demo Logs
# ============================================================

# Latest ANR trace
ANR_LOG_FILE = get_latest_log(
    "anr",
    "anr_trace.txt"
)

# Latest ANR logcat
ANR_LOGCAT_FILE = get_latest_log(
    "anr",
    "logcat.txt"
)

# Latest Display logcat
CRASH_LOG_FILE = get_latest_log(
    "display",
    "logcat.txt"
)


# ============================================================
# Runtime Variables (Remote Mode)
# ============================================================

DEVICE = {}

WORKSPACE = ""

LOG_FILE = ""

BUG_TYPE = ""


# ============================================================
# Build Variables
# ============================================================

APK_PATH = ""

LOG_DIR = ""

MOCK_BUILD = False
