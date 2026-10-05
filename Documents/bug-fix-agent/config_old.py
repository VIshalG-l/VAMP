import os
from dotenv import load_dotenv

load_dotenv()

# ============================================================
# Gemini
# ============================================================

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")


# ============================================================
# Default Demo Workspace
# ============================================================

HOME = os.path.expanduser("~")

# ANR Project
ANR_WORKSPACE = os.path.join(
    HOME,
    "AndroidStudioProjects",
    "DEMO"
)

# Crash Project
CRASH_WORKSPACE = os.path.join(
    HOME,
    "AndroidStudioProjects",
    "DisplayCrashApp"
)


# ============================================================
# Default Demo Logs
# ============================================================

ANR_LOG_FILE = (
    "logs/bugreport/FS/data/anr/"
    "anr_2026-07-01-11-58-43-133"
)

CRASH_LOG_FILE = os.path.join(
    HOME,
    "Downloads",
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
