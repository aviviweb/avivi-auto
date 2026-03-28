from __future__ import annotations

import ctypes
import hashlib
import os
import re
import shutil
import subprocess
import sys
import urllib.request
from dataclasses import dataclass
from pathlib import Path

# Pinned artifacts — update URLs and sha256 when bumping versions
NODE_MSI_URL = "https://nodejs.org/dist/v18.20.4/node-v18.20.4-x64.msi"
NODE_MSI_SHA256: str | None = None  # set for production verification
GIT_EXE_URL = "https://github.com/git-for-windows/git/releases/download/v2.43.0.windows.1/Git-2.43.0-64-bit.exe"
GIT_EXE_SHA256: str | None = None


@dataclass
class DepsStatus:
    node_ok: bool
    node_version: str | None
    git_ok: bool
    messages: list[str]


def _cache_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA") or "."
    d = Path(base) / "Avivi" / "cache"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _parse_node_major(version_line: str) -> int | None:
    m = re.search(r"v(\d+)", version_line)
    if not m:
        return None
    return int(m.group(1))


def check_node() -> tuple[bool, str | None]:
    exe = shutil.which("node")
    if not exe:
        return False, None
    try:
        out = subprocess.run(
            [exe, "-v"],
            capture_output=True,
            text=True,
            timeout=10,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )
        v = (out.stdout or "").strip()
        major = _parse_node_major(v)
        return (major is not None and major >= 18, v or None)
    except Exception:
        return False, None


def check_git() -> bool:
    return shutil.which("git") is not None


def refresh_path_from_registry() -> None:
    if sys.platform != "win32":
        return
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment") as k:
            machine_path, _ = winreg.QueryValueEx(k, "PATH")
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Environment") as k:
            try:
                user_path, _ = winreg.QueryValueEx(k, "PATH")
            except OSError:
                user_path = ""
        merged = f"{machine_path};{user_path}"
        os.environ["PATH"] = merged
    except Exception:
        pass


def broadcast_setting_change() -> None:
    if sys.platform != "win32":
        return
    try:
        HWND_BROADCAST = 0xFFFF
        WM_SETTINGCHANGE = 0x001A
        SMTO_ABORTIFHUNG = 0x0002
        ctypes.windll.user32.SendMessageTimeoutW(
            HWND_BROADCAST,
            WM_SETTINGCHANGE,
            0,
            "Environment",
            SMTO_ABORTIFHUNG,
            5000,
            None,
        )
    except Exception:
        pass


def download_file(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    urllib.request.urlretrieve(url, dest)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _verify_sha(path: Path, expected: str | None, verify: bool, label: str, msgs: list[str]) -> bool:
    if not verify:
        return True
    if not expected:
        msgs.append(f"{label}: SHA256 check skipped (no pinned hash in deps.py)")
        return True
    got = sha256_file(path)
    if got.lower() != expected.lower():
        msgs.append(f"{label}: SHA256 mismatch — refusing install (tamper or wrong file)")
        return False
    msgs.append(f"{label}: SHA256 verified")
    return True


def _install_failure_hint(msg: str) -> str:
    low = msg.lower()
    if "access is denied" in low or "error 5" in low or "1603" in msg or "administrator" in low:
        return (
            " Silent install may need Administrator rights (UAC). "
            "Run Avivi Client as Administrator once, or install Node/Git manually."
        )
    return ""


def install_node_msi(msi_path: Path) -> tuple[bool, str]:
    if sys.platform != "win32":
        return False, "Node silent install is implemented for Windows only"
    try:
        r = subprocess.run(
            ["msiexec.exe", "/i", str(msi_path), "/qn", "/norestart"],
            capture_output=True,
            text=True,
            timeout=600,
        )
        if r.returncode != 0:
            err = f"msiexec failed: {r.returncode} {r.stderr or r.stdout}"
            return False, err + _install_failure_hint(err)
        refresh_path_from_registry()
        broadcast_setting_change()
        return True, "Node installed"
    except Exception as e:
        return False, str(e)


def install_git_silent(exe_path: Path) -> tuple[bool, str]:
    if sys.platform != "win32":
        return False, "Git silent install is implemented for Windows only"
    try:
        r = subprocess.run(
            [str(exe_path), "/VERYSILENT", "/NORESTART", "/NOCANCEL", "/SP-"],
            capture_output=True,
            text=True,
            timeout=600,
        )
        if r.returncode != 0:
            err = f"Git installer failed: {r.returncode}"
            return False, err + _install_failure_hint(err)
        refresh_path_from_registry()
        broadcast_setting_change()
        return True, "Git installed"
    except Exception as e:
        return False, str(e)


def ensure_dependencies(auto_install: bool = False, verify_sha256: bool = False) -> DepsStatus:
    msgs: list[str] = []
    node_ok, node_v = check_node()
    git_ok = check_git()

    if not node_ok and auto_install and sys.platform == "win32":
        msi = _cache_dir() / "node-v18.msi"
        try:
            msgs.append("Downloading Node.js LTS installer…")
            download_file(NODE_MSI_URL, msi)
            if not _verify_sha(msi, NODE_MSI_SHA256, verify_sha256, "Node MSI", msgs):
                pass
            else:
                ok, m = install_node_msi(msi)
                msgs.append(m)
                node_ok, node_v = check_node()
        except Exception as e:
            msgs.append(f"Node install error: {e}{_install_failure_hint(str(e))}")

    if not git_ok and auto_install and sys.platform == "win32":
        git_exe = _cache_dir() / "Git-installer.exe"
        try:
            msgs.append("Downloading Git for Windows…")
            download_file(GIT_EXE_URL, git_exe)
            if not _verify_sha(git_exe, GIT_EXE_SHA256, verify_sha256, "Git installer", msgs):
                pass
            else:
                ok, m = install_git_silent(git_exe)
                msgs.append(m)
                git_ok = check_git()
        except Exception as e:
            msgs.append(f"Git install error: {e}{_install_failure_hint(str(e))}")

    return DepsStatus(node_ok=node_ok, node_version=node_v, git_ok=git_ok, messages=msgs)
