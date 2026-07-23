"""Small, dependency-free updater for packaged PetShelf builds."""

from __future__ import annotations

import json
import os
import platform
import subprocess
import sys
import tempfile
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QObject, Signal

from . import __version__

CURRENT_VERSION = __version__
GITHUB_REPOSITORY = "HaoPhamVan96/PetShelf"
RELEASES_API = f"https://api.github.com/repos/{GITHUB_REPOSITORY}/releases/latest"


def version_tuple(value: str) -> tuple[int, ...]:
    parts = value.strip().lstrip("vV").split(".")
    numbers: list[int] = []
    for part in parts:
        digits = "".join(char for char in part if char.isdigit())
        numbers.append(int(digits or 0))
    return tuple(numbers or [0])


@dataclass(frozen=True)
class UpdateInfo:
    version: str
    notes: str
    download_url: str
    asset_name: str


def _asset_name() -> str:
    if os.name == "nt":
        return "PetShelf-Windows-x64.zip"
    if sys.platform == "darwin":
        architecture = platform.machine().lower()
        return "PetShelf-macOS-arm64.zip" if architecture in {"arm64", "aarch64"} else "PetShelf-macOS-x64.zip"
    raise RuntimeError("Automatic updates are only supported on Windows and macOS")


def check_latest_release() -> UpdateInfo | None:
    """Return an update for this platform, or None when already current."""
    request = urllib.request.Request(
        os.environ.get("PETSHELF_RELEASES_API", RELEASES_API),
        headers={"Accept": "application/vnd.github+json", "User-Agent": "PetShelf-Updater"},
    )
    with urllib.request.urlopen(request, timeout=8) as response:
        release = json.load(response)
    version = str(release.get("tag_name", "")).lstrip("vV")
    if not version or version_tuple(version) <= version_tuple(CURRENT_VERSION):
        return None
    wanted = _asset_name()
    asset = next((item for item in release.get("assets", []) if item.get("name") == wanted), None)
    if not asset or not asset.get("browser_download_url"):
        raise RuntimeError(f"Release {version} does not contain {wanted}")
    return UpdateInfo(version, str(release.get("body") or ""), str(asset["browser_download_url"]), wanted)


class UpdateWorker(QObject):
    checked = Signal(object)
    failed = Signal(str)
    downloaded = Signal(str)
    progress = Signal(int)

    def check(self) -> None:
        try:
            self.checked.emit(check_latest_release())
        except Exception as exc:  # network errors must never crash the app
            self.failed.emit(str(exc))

    def download(self, info: UpdateInfo) -> None:
        try:
            destination = Path(tempfile.gettempdir()) / f"PetShelf-{info.version}.zip"
            request = urllib.request.Request(info.download_url, headers={"User-Agent": "PetShelf-Updater"})
            with urllib.request.urlopen(request, timeout=30) as response, destination.open("wb") as output:
                total = int(response.headers.get("Content-Length", "0"))
                received = 0
                while chunk := response.read(1024 * 256):
                    output.write(chunk)
                    received += len(chunk)
                    if total:
                        self.progress.emit(min(100, round(received * 100 / total)))
            self.downloaded.emit(str(destination))
        except Exception as exc:
            self.failed.emit(str(exc))


def _application_path() -> Path:
    executable = Path(sys.executable).resolve()
    if sys.platform == "darwin":
        for parent in executable.parents:
            if parent.suffix == ".app":
                return parent
    return executable.parent


def install_after_exit(zip_path: str) -> None:
    """Start a detached helper that replaces the app after this process exits."""
    if not getattr(sys, "frozen", False):
        raise RuntimeError("Updates can only install packaged applications")
    archive = Path(zip_path).resolve()
    target = _application_path()
    staging = Path(tempfile.mkdtemp(prefix="petshelf-update-"))
    if os.name == "nt":
        script = staging / "update.cmd"
        script.write_text(
            "@echo off\r\n"
            "timeout /t 2 /nobreak >nul\r\n"
            f"powershell -NoProfile -ExecutionPolicy Bypass -Command \"Expand-Archive -LiteralPath '{archive}' -DestinationPath '{staging / 'unpacked'}' -Force\"\r\n"
            f"rmdir /s /q \"{target}\"\r\n"
            f"move \"{staging / 'unpacked' / 'PetShelf'}\" \"{target}\"\r\n"
            f"start \"\" \"{target / 'PetShelf.exe'}\"\r\n"
            f"rmdir /s /q \"{staging}\"\r\n",
            encoding="utf-8",
        )
        subprocess.Popen(["cmd.exe", "/c", str(script)], creationflags=subprocess.CREATE_NO_WINDOW)
        return

    script = staging / "update.sh"
    extracted = staging / "unpacked"
    script.write_text(
        "#!/bin/sh\n"
        "sleep 2\n"
        f"ditto -x -k '{archive}' '{extracted}'\n"
        f"rm -rf '{target}'\n"
        f"mv '{extracted / 'PetShelf.app'}' '{target}'\n"
        f"open '{target}'\n"
        f"rm -rf '{staging}'\n",
        encoding="utf-8",
    )
    script.chmod(0o700)
    subprocess.Popen(["/bin/sh", str(script)], start_new_session=True)
