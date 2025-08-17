# updater.py
"""
Windows-only update helper for RF2K-TRAINER.

- Queries GitHub "latest release" for the Setup.exe asset
- Compares versions (tag like v0.9.312 vs current '0.9.313')
- Interactive or auto flow
- Starts the Inno Setup installer with the *existing* install scope:
    * If running from Program Files  -> elevate and install machine-wide
    * Else (LocalAppData\\Programs)  -> per-user install (no UAC)
- After launching the installer, exits the process with code 111 so the
  batch launcher can close immediately.

This module does nothing on import. Call `check_for_updates(...)` from main,
or run `python -m updater --version 0.9.313 --interactive`.
"""

from __future__ import annotations

import ctypes
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple
from urllib.request import Request, urlopen, URLError

ENGINE_TAG = "r9"  # bump when logic changes (printed to console)

# ------------------------------ Model ---------------------------------


@dataclass
class ReleaseInfo:
    tag: str              # e.g. "v0.9.312"
    version: str          # e.g. "0.9.312"
    download_url: str     # browser_download_url for RF2K-TRAINER_*_Setup.exe
    name: str             # asset filename


# ------------------------------ Public API ----------------------------


def check_for_updates(current_version: str,
                      mode: str = "interactive") -> None:
    """
    Main entry point.

    :param current_version: like "0.9.313" (strip any leading 'v' yourself or not; we normalize)
    :param mode: "interactive" (ask), "auto" (no prompt), or "check" (print only)
    """
    if not is_windows():
        print("[update] updater is Windows-only; skipping.")
        return

    curr = normalize_version(current_version)
    if not curr:
        print(f"[update] invalid current version: {current_version!r}")
        return

    print(f"[update] engine {ENGINE_TAG}")
    rel = fetch_latest_release()
    if not rel:
        return  # already printed reason

    latest = rel.version
    cmp = compare_versions(curr, latest)

    # Status messages
    if cmp == 0:
        print(f"[update] up to date: v{curr} (latest release: v{latest})")
        return
    elif cmp < 0:
        print(f"A newer version v{latest} is available.")
    else:
        print(f"[update] you are ahead: v{curr} (latest release: v{latest})")
        if mode != "check":
            # Nothing to install if we're ahead
            return
        return

    if mode == "check":
        # Only report; no install
        return

    # Decide scope (machine vs per-user) based on where we are running from now
    install_dir, is_machine = detect_install_dir_and_scope()

    scope_msg = "machine-wide (UAC)" if is_machine else "per-user (no UAC)"
    print(f"Update will use the existing install scope: {scope_msg} and will close RF2K-TRAINER.")

    proceed = True
    if mode == "interactive":
        proceed = prompt_yes_no("Proceed? [Y/n]: ", default=True)

    if not proceed:
        print("[update] cancelled.")
        return

    # Download installer to temp
    temp_dir = Path(tempfile.gettempdir())
    ts = int(time.time())
    dest = temp_dir / f"RF2K-TRAINER_update_{ts}.exe"
    print("[update] downloading installer...")
    print(f"[update] saving installer to: {dest}")
    if not download(rel.download_url, dest):
        print("[update] download failed.")
        return

    # Build inno arguments
    log_path = temp_dir / "RF2K-TRAINER_update.log"
    args_list = [
        "/VERYSILENT",
        "/NORESTART",
        "/SP-",
        f"/LOG={str(log_path)}",
        f"/DIR={str(install_dir)}",
    ]
    if not is_machine:
        args_list.append("/CURRENTUSER")

    # Start installer (elevated if machine scope)
    started = start_installer(dest, args_list, elevate=is_machine)
    if not started:
        print("[update] failed to start installer.")
        return

    if is_machine:
        print(f"[update] installer started (elevated). Log: {log_path}")
    else:
        print(f"[update] installer started (per-user). Log: {log_path}")

    # Create a sentinel file so the batch launcher can close even if exit code gets lost.
    try:
        Path("rf2k-update.flag").write_text("111", encoding="utf-8")
    except Exception:
        pass

    print("[update] RF2K-TRAINER will exit now so the installer can update files.")
    os._exit(111)


# Back-compat aliases in case main calls a different name
run_update_flow = check_for_updates
check_and_maybe_update = check_for_updates
run = check_for_updates
update = check_for_updates


# ------------------------------ Helpers -------------------------------


def is_windows() -> bool:
    return os.name == "nt"


def normalize_version(v: str) -> str:
    """Return digits-only semantic version 'X.Y.Z', stripping any leading 'v'."""
    v = v.strip()
    if v.lower().startswith("v"):
        v = v[1:]
    # allow X.Y or X.Y.Z; pad to three parts
    parts = re.split(r"[^\d]+", v)
    parts = [p for p in parts if p.isdigit()]
    if not parts:
        return ""
    while len(parts) < 3:
        parts.append("0")
    return ".".join(parts[:3])


def compare_versions(a: str, b: str) -> int:
    """-1 if a<b, 0 if a==b, +1 if a>b (semantic compare)."""
    def parse(x: str) -> Tuple[int, int, int]:
        n = normalize_version(x)
        major, minor, patch = (int(p) for p in n.split("."))
        return major, minor, patch

    pa, pb = parse(a), parse(b)
    return (pa > pb) - (pa < pb)


def fetch_latest_release() -> Optional[ReleaseInfo]:
    """Call GitHub API for latest release and pick the Setup.exe asset."""
    req = Request(
        "https://api.github.com/repos/tnxqso/rf2k-trainer/releases/latest",
        headers={
            "User-Agent": "rf2k-trainer-updater",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )   
    try:
        with urlopen(req, timeout=15) as r:
            data = json.loads(r.read().decode("utf-8", "replace"))
    except URLError as e:
        print(f"[update] failed to query GitHub: {e}")
        return None
    except Exception as e:
        print(f"[update] error reading GitHub response: {e}")
        return None

    tag = str(data.get("tag_name", "")).strip()
    if not tag:
        print("[update] no tag_name in latest release.")
        return None

    assets = data.get("assets") or []
    setup = None
    for a in assets:
        name = a.get("name") or ""
        if re.match(r"^RF2K-TRAINER_.*_Setup\.exe$", name, re.I):
            setup = a
            break
    if not setup:
        print("[update] no Setup.exe asset found in latest release.")
        return None

    dl = setup.get("browser_download_url") or ""
    if not dl:
        print("[update] asset has no browser_download_url.")
        return None

    version = normalize_version(tag)
    return ReleaseInfo(tag=tag, version=version, download_url=dl, name=setup.get("name", ""))


def detect_install_dir_and_scope() -> Tuple[Path, bool]:
    r"""
    Return (install_dir, is_machine).
    - If current exe lives under Program Files -> machine-wide (True)
    - Else -> %LOCALAPPDATA%\Programs\RF2K-TRAINER (per-user, False)
    """
    exe_path = Path(sys.executable if getattr(sys, "frozen", False) else sys.argv[0]).resolve()
    lower = str(exe_path).lower()
    pf = os.environ.get("ProgramFiles", r"C:\Program Files").lower()
    pf86 = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)").lower()

    if lower.startswith(pf) or lower.startswith(pf86):
        inst_dir = Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "RF2K-TRAINER"
        return inst_dir, True

    # Default per-user
    local = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData/Local")))
    return local / "Programs" / "RF2K-TRAINER", False


def prompt_yes_no(msg: str, default: bool = True) -> bool:
    try:
        ans = input(msg).strip().lower()
    except (EOFError, KeyboardInterrupt):
        return False
    if not ans:
        return default
    return ans in ("y", "yes", "j", "ja", "true", "1")


def download(url: str, dest: Path) -> bool:
    try:
        req = Request(url, headers={"User-Agent": "rf2k-trainer-updater"})
        with urlopen(req, timeout=60) as r, open(dest, "wb") as f:
            # Stream to disk
            while True:
                chunk = r.read(64 * 1024)
                if not chunk:
                    break
                f.write(chunk)
        return True
    except Exception as e:
        print(f"[update] download error: {e}")
        return False


def start_installer(installer: Path, args: list[str], elevate: bool) -> bool:
    """
    Start the Inno Setup installer.
    - If elevate=True, request UAC via ShellExecute 'runas'
    - Else, start normally (per-user install)
    """
    try:
        if elevate:
            # Build a single command-line string for ShellExecute
            arg_str = " ".join(_quote_if_needed(a) for a in args)
            # ShellExecuteW returns >32 on success
            rc = ctypes.windll.shell32.ShellExecuteW(
                None, "runas", str(installer), arg_str, None, 1
            )
            return rc > 32
        else:
            # Start detached; no need to wait
            subprocess.Popen([str(installer), *args], close_fds=False)
            return True
    except Exception as e:
        print(f"[update] start error: {e}")
        return False


def _quote_if_needed(s: str) -> str:
    # Quote only when spaces exist; keep tokens like /LOG=C:\path intact
    if " " in s or "\t" in s:
        return f'"{s}"'
    return s


# ------------------------------ CLI (optional) ------------------------


def cli(argv: Optional[list[str]] = None) -> None:
    """
    Minimal CLI for dev/testing:
      python -m updater --version 0.9.313 --interactive
      python -m updater --version 0.9.313 --auto
      python -m updater --version 0.9.313 --check
    """
    import argparse

    p = argparse.ArgumentParser(prog="updater", add_help=True)
    p.add_argument("--version", required=False, default=os.environ.get("RF2K_TRAINER_VERSION", "0.0.0"))
    g = p.add_mutually_exclusive_group()
    g.add_argument("--interactive", action="store_true")
    g.add_argument("--auto", action="store_true")
    g.add_argument("--check", action="store_true")

    ns = p.parse_args(argv)
    mode = "interactive"
    if ns.auto:
        mode = "auto"
    elif ns.check:
        mode = "check"

    check_for_updates(ns.version, mode)


if __name__ == "__main__":
    cli()
