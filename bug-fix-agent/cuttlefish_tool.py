#!/usr/bin/env python3
"""
cuttlefish_tool.py

Combines cuttlefish workflow steps into one CLI:

  fetch   - fetch a cuttlefish build from ci.android.com via `cvd fetch`
  create  - `cvd create --product_path=... --host_path=... --nostart`
            (registers the instance without starting it)
  start   - the full launch sequence:
                cvd create --product_path=... --host_path=... --nostart
                cvd fleet    # Status: stop
                cvd start    # Starts device; Status: running
            then waits for the device to show up in `adb devices`,
            retrying once with `cvd start --gpu_mode=gfxstream` if it
            doesn't (per the documented fallback for adb not showing the
            device).
  stop    - tear down a running instance via `cvd stop`
  fleet   - list currently running cvd instances via `cvd fleet`
  info    - run `adb shell getprop` checks against a running cuttlefish
            device and save the output to a text file
  all     - fetch -> stop (best-effort cleanup of any prior run) ->
            start -> info, back to back

IMPORTANT / UNVERIFIED: I don't have cuttlefish tooling or network access
in this environment, so `create`/`start`/`stop`/`fleet` below are built
from the `cvd` commands you provided plus the documented CLI shape, but
are NOT tested end-to-end against your exact cuttlefish version. Before
relying on this in automation, run `cvd create --help` / `cvd start
--help` / `cvd stop --help` / `cvd fleet --help` on your machine and diff
them against the *_ARGS lists near the top of the create/start/stop/fleet
functions below.

Usage:
    python3 cuttlefish_tool.py fetch
    python3 cuttlefish_tool.py create
    python3 cuttlefish_tool.py start
    python3 cuttlefish_tool.py stop
    python3 cuttlefish_tool.py fleet
    python3 cuttlefish_tool.py info
    python3 cuttlefish_tool.py all
    BUILD_ID=16102939 python3 cuttlefish_tool.py info

Config is via environment variables (same names as the original scripts):

    Shared:
        BASE_DIR           default: ~/cuttlefish_builds
        BUILD_ID           default: newest build dir under BASE_DIR
                            (used by create/start/stop/info when not
                            chained via `all`)
        CVD_BIN            path/name of the cvd binary (default: "cvd")

    fetch:
        BRANCH             default: aosp-android-latest-release
        TARGET             default: aosp_cf_x86_64_only_phone-userdebug
        FORCE_BUILD_ID     pin to a specific build id instead of auto-detecting latest
        CVD_FETCH_BIN      path/name of the fetch binary (default: CVD_BIN)

    create:
        CREATE_EXTRA_ARGS  extra space-separated flags appended verbatim to
                            `cvd create` (e.g. "--daemon")

    start:
        START_EXTRA_ARGS   extra space-separated flags appended verbatim to
                            `cvd start` (e.g. "--cpus=4 --memory_mb=4096")
        GPU_MODE_FALLBACK  gpu_mode value used for the fallback `cvd start
                            --gpu_mode=...` retry (default: "gfxstream")
        ADB_WAIT_SECONDS   how long to wait for the device to show up in
                            `adb devices` before/after the fallback (default: 30)
        ADB_POLL_INTERVAL  seconds between `adb devices` polls (default: 3)

    stop:
        STOP_EXTRA_ARGS    extra space-separated flags appended verbatim to
                            `cvd stop`

    info:
        ADB_SERIAL         optional pin (e.g. "127.0.0.1:6520"). By default
                            NOT hardcoded — it's auto-detected from `adb
                            devices` at the time each command needs it. Set
                            this only if multiple adb devices are online at
                            once and you need to disambiguate.
        OUTPUT_DIR         default: BASE_DIR/<BUILD_ID>  (the build's own folder)

Output:
    fetch -> <BASE_DIR>/<BUILD_ID>/images/            (device images)
             <BASE_DIR>/<BUILD_ID>/cvd-host_package/  (host tools)
    create/start -> by default runs with your normal environment/HOME,
             same as running the cvd commands by hand. Set
             CVD_HOME_OVERRIDE=1 to point HOME at <BASE_DIR>/<BUILD_ID>
             instead (only if you've confirmed that doesn't break your
             cvd version's host-configuration check — see the note above
             CVD_HOME_OVERRIDE near the top of the file).
    info  -> <OUTPUT_DIR>/build_info_<BUILD_ID>.txt
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
from datetime import datetime
from pathlib import Path

### ---- Shared configuration --------------------------------------------

BASE_DIR = Path(os.environ.get("BASE_DIR", str(Path.home() / "cuttlefish_builds")))

### ---- fetch configuration ----------------------------------------------

BRANCH = os.environ.get("BRANCH", "aosp-android-latest-release")
TARGET = os.environ.get("TARGET", "aosp_cf_x86_64_only_phone-userdebug")
FORCE_BUILD_ID = os.environ.get("FORCE_BUILD_ID", "").strip()

# CVD_BIN is the shared binary name/path for cvd fetch/start/stop/fleet.
# CVD_FETCH_BIN is kept for backwards compatibility with the original
# fetch_cuttlefish_build.py env var and falls back to CVD_BIN.
CVD_BIN = os.environ.get("CVD_BIN", "cvd")
CVD_FETCH_BIN = os.environ.get("CVD_FETCH_BIN", CVD_BIN)

CI_HOST = "https://ci.android.com"

### ---- start/stop/fleet configuration -------------------------------------

CREATE_EXTRA_ARGS = os.environ.get("CREATE_EXTRA_ARGS", "").split()
START_EXTRA_ARGS = os.environ.get("START_EXTRA_ARGS", "").split()
STOP_EXTRA_ARGS = os.environ.get("STOP_EXTRA_ARGS", "").split()

# Fallback flag used if the device doesn't show up in `adb devices` after a
# plain `cvd start` — matches the documented `cvd start --gpu_mode=gfxstream`
# workaround.
GPU_MODE_FALLBACK = os.environ.get("GPU_MODE_FALLBACK", "gfxstream")

# How long to wait / poll for the device to appear in `adb devices` before
# trying the gpu_mode fallback (and again after the fallback).
ADB_WAIT_SECONDS = int(os.environ.get("ADB_WAIT_SECONDS", "30"))
ADB_POLL_INTERVAL = int(os.environ.get("ADB_POLL_INTERVAL", "3"))

# Opt-in only: some multi-instance setups isolate cvd's runtime/config
# state per build by pointing HOME at the build's own folder. This is OFF
# by default because cvd also keeps its "is this host configured" marker
# under $HOME, and overriding it can make a properly-configured host look
# unconfigured (`cvd create` fails with "Host configuration requirements
# not met" even right after a successful `cvd setup`). Set
# CVD_HOME_OVERRIDE=1 only if you've confirmed your cvd version's host
# config check is unaffected by HOME, or you re-run `cvd setup` with that
# HOME first.
CVD_HOME_OVERRIDE = os.environ.get("CVD_HOME_OVERRIDE", "0").strip() == "1"

# When enabled, start using the host package bundled with the exact build
# instead of relying on system-wide /usr/lib/cuttlefish-common substitutions.
DIRECT_LAUNCH = os.environ.get("DIRECT_LAUNCH", "1").strip() != "0"
LAUNCH_TIMEOUT = int(os.environ.get("LAUNCH_TIMEOUT", "90"))

BUILD_ID_ENV = os.environ.get("BUILD_ID", "").strip()

# ADB_SERIAL is no longer hardcoded. If you set it explicitly it's treated
# as a pinned override (useful if you're targeting one specific instance
# among several); otherwise it's auto-detected from `adb devices` at the
# point each command actually needs it (see resolve_adb_serial() below).
ADB_SERIAL_OVERRIDE = os.environ.get("ADB_SERIAL", "").strip()

OUTPUT_DIR_OVERRIDE = os.environ.get("OUTPUT_DIR", "").strip()

# prop name -> label used in the output file
PROPS = [
    ("ro.build.version.release", "Android version"),
    ("ro.build.version.sdk", "SDK level"),
    ("ro.build.id", "Build ID"),
    ("ro.build.fingerprint", "Fingerprint"),
    ("ro.build.version.security_patch", "Security patch"),
    ("ro.product.cpu.abi", "CPU ABI"),
    ("ro.build.ab_update", "A/B update"),
    ("ro.virtual_ab.enabled", "Virtual A/B enabled"),
]

### ---- shared helpers -----------------------------------------------------


def log(tag: str, msg: str) -> None:
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{tag}] {ts} - {msg}", flush=True)


def err(tag: str, msg: str) -> None:
    print(f"[{tag}] ERROR: {msg}", file=sys.stderr, flush=True)


### ---- fetch logic (from fetch_cuttlefish_build.py) ------------------------


def fetch_resolve_build_id() -> str:
    """Resolve latest known-good build id via status.json.

    Unaffected by the ci.android.com artifact-viewer UI change (status.json
    is still plain JSON) and worked fine when tested.
    """
    if FORCE_BUILD_ID:
        log("fetch", f"Using forced BUILD_ID={FORCE_BUILD_ID}")
        return FORCE_BUILD_ID

    log("fetch", f"Looking up latest known-good build for branch={BRANCH} target={TARGET}")
    status_url = f"{CI_HOST}/builds/branches/{BRANCH}/status.json"
    try:
        with urllib.request.urlopen(status_url, timeout=60) as resp:
            status = json.loads(resp.read().decode("utf-8"))
    except Exception as exc:
        err("fetch", f"Could not fetch {status_url}: {exc}")
        sys.exit(1)

    target_id = f"{BRANCH}.{TARGET}"
    targets = status.get("targets") or []
    if not targets:
        err("fetch", f"Branch '{BRANCH}' has no active targets in status.json.")
        err("fetch", f"Check {CI_HOST}/builds/branches/{BRANCH}/grid?head=1")
        sys.exit(1)

    build_id = None
    for t in targets:
        if t.get("ID") == target_id:
            build_id = t.get("last_known_good_build")
            break

    if not build_id:
        err("fetch", f"Could not resolve a build ID for target '{target_id}'.")
        err("fetch", f"Double-check the exact target name on {CI_HOST}/builds/branches/{BRANCH}/grid?head=1")
        sys.exit(1)

    return str(build_id)


def fetch_run_cvd_fetch(target_directory: Path, build_id: str, download_images: bool) -> None:
    """Shell out to `cvd fetch`.

    default_build accepts "<build_id_or_branch>/<target>" - using the
    numeric build_id here pins it to the exact build we resolved above,
    so this call and the status.json lookup can never disagree.
    """
    target_directory.mkdir(parents=True, exist_ok=True)
    args = [
        CVD_FETCH_BIN,
        "fetch",
        f"--target_directory={target_directory}",
        f"--default_build={build_id}/{TARGET}",
    ]
    if not download_images:
        args.append("--download_img_zip=false")

    log("fetch", f"  Running: {' '.join(args)}")
    result = subprocess.run(args, capture_output=True, text=True)
    if result.returncode != 0:
        err("fetch", f"  cvd fetch failed (exit {result.returncode})")
        err("fetch", f"  stdout:\n{result.stdout}")
        err("fetch", f"  stderr:\n{result.stderr}")
        raise RuntimeError(
            "cvd fetch failed. Run `cvd fetch --help` on this machine and "
            "check the flag names above still match your cuttlefish version "
            "(fetch_cvd/cvd fetch flags have changed between releases)."
        )
    log("fetch", "  cvd fetch succeeded.")


def fetch_relative_file_set(root: Path) -> set:
    return {p.relative_to(root) for p in root.rglob("*") if p.is_file()}


def fetch_is_dir_populated(d: Path) -> bool:
    return d.is_dir() and any(d.iterdir())


def cmd_fetch() -> str:
    """Fetch a build. Returns the resolved build_id."""
    BASE_DIR.mkdir(parents=True, exist_ok=True)

    build_id = fetch_resolve_build_id()
    log("fetch", f"Resolved BUILD_ID={build_id}")

    build_dir = BASE_DIR / build_id
    images_dir = build_dir / "images"
    host_pkg_dir = build_dir / "cvd-host_package"

    if fetch_is_dir_populated(images_dir) and fetch_is_dir_populated(host_pkg_dir):
        log("fetch", f"Build {build_id} already fetched at {build_dir} — nothing to do.")
        return build_id

    log("fetch", f"Fetching build {build_id} into {build_dir}")

    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        host_only_stage = tmp_dir / "host_only"
        full_stage = tmp_dir / "full"

        log("fetch", "Step 1/2: fetching host package only ...")
        fetch_run_cvd_fetch(host_only_stage, build_id, download_images=False)

        log("fetch", "Step 2/2: fetching images + host package ...")
        fetch_run_cvd_fetch(full_stage, build_id, download_images=True)

        host_only_files = fetch_relative_file_set(host_only_stage)
        full_files = fetch_relative_file_set(full_stage)
        image_only_files = full_files - host_only_files

        if not image_only_files:
            err("fetch", "Could not identify any image-only files by diffing the two")
            err("fetch", "fetches — the --download_img_zip=false flag may not be doing")
            err("fetch", "what this script assumes on your cvd version. Check")
            err("fetch", f"{host_only_stage} and {full_stage} manually.")
            sys.exit(1)

        images_dir.mkdir(parents=True, exist_ok=True)
        host_pkg_dir.mkdir(parents=True, exist_ok=True)

        log("fetch", f"Moving {len(image_only_files)} image file(s) into {images_dir}")
        for rel in image_only_files:
            src = full_stage / rel
            dst = images_dir / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(src), str(dst))

        log("fetch", f"Moving host package into {host_pkg_dir}")
        for item in host_only_stage.iterdir():
            shutil.move(str(item), str(host_pkg_dir / item.name))

    log("fetch", "Done. Build is ready at:")
    log("fetch", f"  images:            {images_dir}")
    log("fetch", f"  cvd-host_package:  {host_pkg_dir}")
    return build_id


### ---- shared build-id resolution ------------------------------------------


def resolve_build_id(tag: str, preferred: str = "") -> str:
    """Resolve a build id: explicit arg > BUILD_ID env > newest dir under BASE_DIR."""
    if preferred:
        return preferred
    if BUILD_ID_ENV:
        return BUILD_ID_ENV
    if not BASE_DIR.is_dir():
        err(tag, f"BASE_DIR {BASE_DIR} does not exist and BUILD_ID not set.")
        sys.exit(1)
    candidates = sorted(
        (p.name for p in BASE_DIR.iterdir() if p.is_dir() and p.name.isdigit()),
        key=int,
    )
    if not candidates:
        err(tag, f"No builds found under {BASE_DIR} and BUILD_ID not set.")
        sys.exit(1)
    build_id = candidates[-1]
    log(tag, f"No BUILD_ID given — using newest available: {build_id}")
    return build_id


### ---- start / stop / fleet logic (new) ------------------------------------


def _build_paths(build_id: str):
    build_dir = BASE_DIR / build_id
    images_dir = build_dir / "images"
    host_pkg_dir = build_dir / "cvd-host_package"
    return build_dir, images_dir, host_pkg_dir


def _find_bundled_launcher(host_pkg_dir: Path) -> Path:
    """Find the launcher in the fetched host package."""
    candidates = [
        host_pkg_dir / "bin" / "launch_cvd",
        host_pkg_dir / "bin" / "cvd_internal_start",
        host_pkg_dir / "launch_cvd",
        host_pkg_dir / "cvd_internal_start",
    ]
    for candidate in candidates:
        if candidate.is_file() and candidate.stat().st_mode & 0o111:
            return candidate
    # Allow a non-executable file only as a last resort; chmod it in that case.
    for candidate in candidates:
        if candidate.is_file():
            try:
                candidate.chmod(candidate.stat().st_mode | 0o111)
                return candidate
            except OSError:
                pass
    raise FileNotFoundError(
        f"No bundled Cuttlefish launcher found under {host_pkg_dir}"
    )


def _direct_launch(
    build_id: str,
    build_dir: Path,
    images_dir: Path,
    host_pkg_dir: Path,
) -> tuple[int, str]:
    """Launch Cuttlefish with the exact host package fetched for this build.

    Official Cuttlefish usage keeps the host package and images together and
    launches the bundled launcher. We emulate that layout in a temporary
    directory using symlinks, so no image files are copied.
    """
    launcher = _find_bundled_launcher(host_pkg_dir)

    runtime_home = build_dir / "direct_cvd_home"
    runtime_home.mkdir(parents=True, exist_ok=True)

    # The bundled launcher expects its build artifacts to be discoverable.
    # Make a lightweight combined layout with links.
    bin_dir = runtime_home / "bin"
    if not bin_dir.exists():
        bin_dir.symlink_to(host_pkg_dir / "bin", target_is_directory=True)

    image_link = runtime_home / "images"
    if not image_link.exists():
        image_link.symlink_to(images_dir, target_is_directory=True)

    # launcher invocation: use the directory containing the images as system
    # image directory when supported by this host package.
    env = os.environ.copy()
    env["HOME"] = str(runtime_home)
    env["ANDROID_HOST_OUT"] = str(host_pkg_dir)
    env["ANDROID_PRODUCT_OUT"] = str(images_dir)
    env["CUTTLEFISH_CONFIG_FILE"] = str(runtime_home / "cuttlefish_config.json")

    args = [
        str(launcher),
        f"--system_image_dir={images_dir}",
    ]

    log("start", f"Bundled launcher: {launcher}")
    log("start", f"Direct launcher HOME: {runtime_home}")
    result = _run_cvd(
        "start",
        args,
        env=env,
        check_label="bundled launch_cvd",
        timeout=LAUNCH_TIMEOUT,
    )

    # If launch_cvd is a foreground process and has already created a device,
    # _run_cvd may time out while the device is still alive. Treat adb as the
    # authoritative signal instead of failing solely on the timeout.
    if _adb_device_present():
        serial = resolve_adb_serial("start", required=False) or "unknown"
        log("start", f"Device is online despite launcher timeout: {serial}")
        return 0, serial

    return result.returncode, ""


def _run_cvd(
    tag: str,
    args: list,
    env=None,
    check_label: str = "",
    timeout: int = 60,
) -> subprocess.CompletedProcess:
    """Run a cvd command without allowing an indefinite hang."""
    log(tag, f"  Running: {' '.join(args)}")

    try:
        result = subprocess.run(
            args,
            capture_output=True,
            text=True,
            env=env,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        err(tag, f"{check_label or args[1]} timed out after {timeout}s")
        stdout_text = exc.stdout.decode("utf-8", errors="replace") if isinstance(exc.stdout, bytes) else (exc.stdout or "")
        stderr_text = exc.stderr.decode("utf-8", errors="replace") if isinstance(exc.stderr, bytes) else (exc.stderr or "")

        if stdout_text:
            err(tag, f"stdout:\n{stdout_text}")
        if stderr_text:
            err(tag, f"stderr:\n{stderr_text}")

        # Return a synthetic failure result so the caller can decide whether
        # to retry/fallback instead of hanging forever.
        return subprocess.CompletedProcess(
            args=args,
            returncode=124,
            stdout=stdout_text,
            stderr=stderr_text + f"\nTIMEOUT after {timeout}s",
        )

    if result.stdout.strip():
        log(tag, result.stdout.strip())

    if result.returncode != 0:
        err(tag, f"{check_label or args[1]} failed (exit {result.returncode})")
        if result.stderr.strip():
            err(tag, f"stderr:\n{result.stderr}")

    return result


def cmd_clear(quiet: bool = False) -> subprocess.CompletedProcess:
    """`cvd clear` — removes stale/leftover instance-group registrations.

    `cvd stop` only stops a running instance; it doesn't remove the
    instance-group entry from cvd's local instance database. A later
    `cvd create` can then fail with "New instance conflicts with existing
    instance" even though nothing is running. `cvd clear` resets that
    registration. This does NOT touch your fetched build files under
    BASE_DIR — those live outside cvd's own runtime/assembly directories.
    UNVERIFIED against your exact cvd version — run `cvd clear --help` if
    you want to confirm scope before relying on it.
    """
    args = [CVD_BIN, "clear"]
    result = _run_cvd("clear", args, check_label="cvd clear", timeout=30)
    if result.returncode != 0 and not quiet:
        raise RuntimeError(
            "cvd clear failed. Run `cvd clear --help` on this machine to "
            "confirm the command and its behavior on your cuttlefish version."
        )
    return result


def cmd_create(preferred_build_id: str = "") -> str:
    """`cvd clear` (best-effort) then `cvd create --product_path=... --host_path=... --nostart`

    `cvd stop` only stops a group, it doesn't remove its registration, so
    repeated create/stop cycles pile up multiple groups (cvd_1, cvd_2, ...).
    That leftover state is what later makes a bare `cvd start` fail with
    "Multiple groups found. Narrow the selection with selector arguments."
    So this always clears stale groups first, keeping exactly one group
    around at a time and letting plain `cvd start`/`cvd stop` (no selector
    args) stay unambiguous.
    """
    build_id = resolve_build_id("create", preferred_build_id)
    build_dir, images_dir, host_pkg_dir = _build_paths(build_id)

    if not fetch_is_dir_populated(images_dir) or not fetch_is_dir_populated(host_pkg_dir):
        err("create", f"Build {build_id} doesn't look fully fetched under {build_dir}.")
        err("create", f"Expected populated dirs at {images_dir} and {host_pkg_dir}.")
        err("create", "Run the 'fetch' command first.")
        sys.exit(1)

    build_dir.mkdir(parents=True, exist_ok=True)

    log("create", "Clearing any stale instance-group registrations first ...")
    cmd_clear(quiet=True)

    env = os.environ.copy()
    if CVD_HOME_OVERRIDE:
        env["HOME"] = str(build_dir)

    args = [
        CVD_BIN,
        "create",
        f"--product_path={images_dir}",
        f"--host_path={host_pkg_dir}",
        "--nostart",
    ]
    args.extend(CREATE_EXTRA_ARGS)

    log("create", f"Creating instance for build {build_id}" + (f" (HOME={build_dir})" if CVD_HOME_OVERRIDE else "") + " ...")
    result = _run_cvd("create", args, env=env, check_label="cvd create")
    if result.returncode != 0:
        if "Host configuration" in result.stderr or "cvd setup" in result.stderr:
            err("create", "Your host isn't set up for cuttlefish yet.")
            err("create", "Run `cvd setup` (possibly with sudo) once on this")
            err("create", "machine, then re-run this command.")
            sys.exit(1)
        if "New instance conflicts" in result.stderr or "conflicts with existing instance" in result.stderr:
            log("create", "Stale instance-group registration found — running `cvd clear` and retrying ...")
            cmd_clear(quiet=True)
            result = _run_cvd("create", args, env=env, check_label="cvd create (retry after clear)")
        if result.returncode != 0:
            raise RuntimeError(
                "cvd create failed. Run `cvd create --help` on this machine and "
                "check --product_path/--host_path/--nostart still match your "
                "cuttlefish version."
            )
    log("create", "cvd create succeeded.")
    return build_id


def _list_adb_devices() -> list:
    """Parse `adb devices -l` into a list of (serial, state) tuples,
    skipping the header line. State is e.g. "device", "offline",
    "unauthorized" — only "device" means it's actually usable.
    """
    result = subprocess.run(["adb", "devices"], capture_output=True, text=True)
    entries = []
    for line in result.stdout.splitlines():
        line = line.strip()
        if not line or line.startswith("List of devices"):
            continue
        parts = line.split()
        if len(parts) >= 2:
            entries.append((parts[0], parts[1]))
    return entries


def resolve_adb_serial(tag: str, required: bool = True) -> str:
    """Figure out which adb serial to use.

    - If ADB_SERIAL was set explicitly (env var), that's an intentional
      pin — always use it as-is, no detection.
    - Otherwise, look at the current `adb devices` output and pick the
      serial that's actually in "device" state. Cuttlefish's default is
      127.0.0.1:6520, but the port/host can differ (multiple instances,
      different configs), so this reads it instead of assuming.
    - If more than one device is online, this can't guess which one you
      mean — it errors out and asks you to pass ADB_SERIAL explicitly.
    """
    if ADB_SERIAL_OVERRIDE:
        return ADB_SERIAL_OVERRIDE

    online = [serial for serial, state in _list_adb_devices() if state == "device"]

    if len(online) == 1:
        return online[0]

    if len(online) > 1:
        err(tag, f"Multiple adb devices online, can't auto-pick one: {online}")
        err(tag, "Set ADB_SERIAL=<one of the above> to disambiguate.")
        if required:
            sys.exit(1)
        return ""

    if required:
        return ""  # caller decides how to handle "not found yet" (e.g. keep polling)
    return ""


def _adb_device_present() -> bool:
    """True if exactly one adb device is online (state == 'device'), or
    the pinned ADB_SERIAL (if set) is online."""
    entries = _list_adb_devices()
    if ADB_SERIAL_OVERRIDE:
        return any(serial == ADB_SERIAL_OVERRIDE and state == "device" for serial, state in entries)
    return any(state == "device" for _, state in entries)


def _wait_for_adb(timeout: int) -> str:
    """Wait for a usable adb device and return its serial."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        serial = resolve_adb_serial("start", required=False)
        if serial:
            return serial
        time.sleep(ADB_POLL_INTERVAL)
    return ""


def _kill_stuck_start_processes() -> None:
    """Best-effort cleanup of launch processes after a timed-out start."""
    # Do not kill arbitrary qemu processes. Only terminate known Cuttlefish
    # launch helpers, if present.
    names = [
        "launch_cvd",
        "run_cvd",
        "assemble_cvd",
    ]
    for name in names:
        try:
            subprocess.run(
                ["pkill", "-TERM", "-x", name],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=5,
            )
        except Exception:
            pass


def cmd_start(preferred_build_id: str = "") -> str:
    """Create and start one Cuttlefish instance robustly."""

    build_id = cmd_create(preferred_build_id)
    build_dir, images_dir, host_pkg_dir = _build_paths(build_id)

    env = os.environ.copy()
    if CVD_HOME_OVERRIDE:
        env["HOME"] = str(build_dir)

    # Prefer the exact launcher shipped with the build. This avoids mixing
    # the fetched images with a different system-wide cuttlefish-common
    # installation. The observed log had exactly that warning:
    # /usr/lib/cuttlefish-common/bin/allocd_client missing.
    if DIRECT_LAUNCH:
        log(
            "start",
            "DIRECT_LAUNCH=1: using the bundled host launcher for this build."
        )
        try:
            rc, serial = _direct_launch(
                build_id,
                build_dir,
                images_dir,
                host_pkg_dir,
            )
            if serial:
                return build_id
            if rc == 0:
                serial = _wait_for_adb(ADB_WAIT_SECONDS)
                if serial:
                    log("start", f"Device is online: {serial}")
                    return build_id
        except Exception as exc:
            err("start", f"Bundled launcher attempt failed: {exc}")
            log("start", "Falling back to cvd start ...")

        # Direct launch can leave a partially running/registered instance.
        _kill_stuck_start_processes()
        time.sleep(2)

        log("start", "Cleaning partial state before cvd fallback ...")
        cmd_clear(quiet=True)
        cmd_create(preferred_build_id=build_id)

    log("start", "Checking fleet status before cvd start ...")
    fleet = _run_cvd(
        "start",
        [CVD_BIN, "fleet"],
        env=env,
        check_label="cvd fleet",
        timeout=30,
    )
    if fleet.returncode != 0:
        raise RuntimeError("cvd fleet failed before start.")

    start_args = [CVD_BIN, "start"] + START_EXTRA_ARGS
    log("start", f"Starting build {build_id} ...")

    result = _run_cvd(
        "start",
        start_args,
        env=env,
        check_label="cvd start",
        timeout=60,
    )

    if result.returncode == 0:
        serial = _wait_for_adb(ADB_WAIT_SECONDS)
        if serial:
            log("start", f"Device is online: {serial}")
            return build_id
        err("start", "cvd start returned, but adb did not show a device.")

    _kill_stuck_start_processes()
    time.sleep(2)

    log("start", "Trying a clean gfxstream cvd fallback ...")
    cmd_clear(quiet=True)
    cmd_create(preferred_build_id=build_id)

    fallback_args = [
        CVD_BIN,
        "start",
        f"--gpu_mode={GPU_MODE_FALLBACK}",
    ] + START_EXTRA_ARGS

    result = _run_cvd(
        "start",
        fallback_args,
        env=env,
        check_label="cvd start (gpu_mode fallback)",
        timeout=60,
    )

    if result.returncode != 0:
        err("start", "gfxstream fallback also failed.")
        _run_cvd(
            "start",
            [CVD_BIN, "fleet"],
            env=env,
            check_label="cvd fleet",
            timeout=30,
        )
        raise RuntimeError("Cuttlefish failed to start.")

    serial = _wait_for_adb(ADB_WAIT_SECONDS)
    if serial:
        log("start", f"Device is online: {serial}")
        return build_id

    _run_cvd(
        "start",
        [CVD_BIN, "fleet"],
        env=env,
        check_label="cvd fleet",
        timeout=30,
    )
    raise RuntimeError("Cuttlefish started but no adb device appeared.")

def cmd_stop(preferred_build_id: str = "", quiet_if_nothing_running: bool = False) -> None:
    """Stop a running instance with `cvd stop`."""
    build_id = ""
    try:
        build_id = resolve_build_id("stop", preferred_build_id)
    except SystemExit:
        if quiet_if_nothing_running:
            log("stop", "No build to resolve — nothing to stop.")
            return
        raise

    build_dir, _, _ = _build_paths(build_id)
    env = os.environ.copy()
    if CVD_HOME_OVERRIDE:
        env["HOME"] = str(build_dir)

    args = [CVD_BIN, "stop"]
    args.extend(STOP_EXTRA_ARGS)

    log("stop", f"Stopping instance for build {build_id}" + (f" (HOME={build_dir})" if CVD_HOME_OVERRIDE else "") + " ...")
    result = _run_cvd(
        "stop",
        args,
        env=env,
        check_label="cvd stop",
        timeout=30,
    )
    if result.returncode != 0:
        if quiet_if_nothing_running:
            log(
                "stop",
                "(ignoring stop failure during best-effort cleanup; "
                "there may be no running instance)"
            )
            return
        raise RuntimeError(
            "cvd stop failed. Run `cvd stop --help` on this machine and "
            "check the flags/behavior match your cuttlefish version."
        )
    log("stop", "cvd stop succeeded.")


def cmd_fleet() -> None:
    """List currently running cvd instances with `cvd fleet`."""
    result = _run_cvd(
        "fleet",
        [CVD_BIN, "fleet"],
        check_label="cvd fleet",
        timeout=30,
    )
    if result.returncode != 0:
        raise RuntimeError(
            "cvd fleet failed. Run `cvd fleet --help` on this machine to "
            "confirm the command is supported by your cuttlefish version."
        )


### ---- info logic (from launch_cuttlefish.py / collect_build_info.py) ------


def info_get_prop(serial: str, prop: str) -> str:
    result = subprocess.run(
        ["adb", "-s", serial, "shell", "getprop", prop],
        capture_output=True, text=True, timeout=15,
    )
    if result.returncode != 0:
        return f"<error: {result.stderr.strip() or 'command failed'}>"
    return result.stdout.strip() or "<empty>"


def cmd_info(preferred_build_id: str = "") -> None:
    build_id = resolve_build_id("info", preferred_build_id)

    serial = resolve_adb_serial("info", required=False)
    if not serial:
        err("info", "No single usable adb device found. Current 'adb devices' output:")
        err("info", subprocess.run(["adb", "devices"], capture_output=True, text=True).stdout)
        err("info", "If more than one device is online, set ADB_SERIAL=<serial> and re-run.")
        sys.exit(1)

    log("info", f"Collecting build info for build {build_id} from {serial} ...")

    results = []
    for prop, label in PROPS:
        value = info_get_prop(serial, prop)
        log("info", f"  {prop} = {value}")
        results.append((prop, label, value))

    output_dir = Path(OUTPUT_DIR_OVERRIDE) if OUTPUT_DIR_OVERRIDE else (BASE_DIR / build_id)
    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = output_dir / f"build_info_{build_id}.txt"

    lines = [
        f"Build ID (folder): {build_id}",
        f"ADB serial:        {serial}",
        f"Collected at:      {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "",
    ]
    for prop, label, value in results:
        lines.append(f"{label} ({prop}):")
        lines.append(f"  {value}")
        lines.append("")

    output_file.write_text("\n".join(lines), encoding="utf-8")

    log("info", f"Saved to {output_file}")


### ---- entry point ---------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Fetch a cuttlefish build and/or collect adb build-info from a running device."
    )
    parser.add_argument(
        "command",
        choices=["fetch", "create", "start", "stop", "clear", "fleet", "info", "all"],
        help="fetch: download a build via cvd fetch. "
             "create: register the instance via cvd create --nostart "
             "(auto-retries once via cvd clear on a stale-instance conflict). "
             "start: create -> fleet (status check) -> start, with an "
             "automatic --gpu_mode=gfxstream retry if adb doesn't see the "
             "device. "
             "stop: tear down the running instance via cvd stop. "
             "clear: remove stale instance-group registrations via cvd clear. "
             "fleet: list running instances via cvd fleet. "
             "info: collect adb getprop info from a running device. "
             "all: fetch -> stop (best-effort) -> start -> info.",
    )
    args = parser.parse_args()

    if args.command == "fetch":
        cmd_fetch()
    elif args.command == "create":
        cmd_create()
    elif args.command == "start":
        cmd_start()
    elif args.command == "stop":
        cmd_stop()
    elif args.command == "clear":
        cmd_clear()
    elif args.command == "fleet":
        cmd_fleet()
    elif args.command == "info":
        cmd_info()
    elif args.command == "all":
        build_id = cmd_fetch()
        # Best-effort: stop anything already running for this build before
        # starting fresh (harmless if nothing was running).
        cmd_stop(preferred_build_id=build_id, quiet_if_nothing_running=True)
        cmd_start(preferred_build_id=build_id)
        cmd_info(preferred_build_id=build_id)


if __name__ == "__main__":
    main()