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
LATEST_MANIFEST = f"https://github.com/{GITHUB_REPOSITORY}/releases/latest/download/latest.json"


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
    author: str
    description: str
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
        os.environ.get("PETSHELF_UPDATE_URL", LATEST_MANIFEST),
        headers={"Accept": "application/json", "User-Agent": "PetShelf-Updater"},
    )
    with urllib.request.urlopen(request, timeout=8) as response:
        manifest = json.load(response)
    version = str(manifest.get("version", "")).lstrip("vV")
    if not version or version_tuple(version) <= version_tuple(CURRENT_VERSION):
        return None
    wanted = _asset_name()
    download_url = manifest.get("assets", {}).get(
        "windows" if os.name == "nt" else f"macos-{'arm64' if platform.machine().lower() in {'arm64', 'aarch64'} else 'x64'}"
    )
    if not download_url:
        raise RuntimeError(f"Release {version} does not contain {wanted}")
    return UpdateInfo(
        version=version,
        notes=str(manifest.get("notes") or ""),
        author=str(manifest.get("author") or "Unknown"),
        description=str(manifest.get("description") or manifest.get("notes") or "No release description."),
        download_url=str(download_url),
        asset_name=wanted,
    )


class UpdateWorker(QObject):
    checked = Signal(object)
    failed = Signal(str)
    downloaded = Signal(str)
    progress = Signal(int)

    def check(self) -> None:
        try:
            self.checked.emit(check_latest_release())
        except Exception as exc:  # network errors must never crash the app
            self.failed.emit(f"{type(exc).__name__}: {exc}".strip())

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
            self.failed.emit(f"{type(exc).__name__}: {exc}".strip())


def download_update(info: UpdateInfo, progress_callback=None) -> str:
    """Download an update archive and return its path without touching the UI."""
    destination = Path(tempfile.gettempdir()) / f"PetShelf-{info.version}.zip"
    request = urllib.request.Request(info.download_url, headers={"User-Agent": "PetShelf-Updater"})
    with urllib.request.urlopen(request, timeout=30) as response, destination.open("wb") as output:
        total = int(response.headers.get("Content-Length", "0"))
        received = 0
        while chunk := response.read(1024 * 256):
            output.write(chunk)
            received += len(chunk)
            if total and progress_callback:
                progress_callback(min(100, round(received * 100 / total)))
    return str(destination)


def _application_path() -> Path:
    executable = Path(sys.executable).resolve()
    if sys.platform == "darwin":
        for parent in executable.parents:
            if parent.suffix == ".app":
                return parent
    return executable.parent


def validate_update_archive(zip_path: str) -> None:
    """Reject incomplete or unexpected update archives before closing the app."""
    archive = Path(zip_path)
    if not archive.is_file() or archive.stat().st_size < 1024:
        raise RuntimeError("The downloaded update is missing or incomplete.")
    with zipfile.ZipFile(archive) as package:
        names = set(package.namelist())
        if os.name == "nt":
            required = "PetShelf/PetShelf.exe"
        else:
            required = "PetShelf.app/Contents/MacOS/PetShelf"
        if required not in names:
            raise RuntimeError(f"The update archive is invalid: missing {required}.")


def install_after_exit(zip_path: str) -> None:
    """Start a detached helper that replaces the app after this process exits."""
    if not getattr(sys, "frozen", False):
        raise RuntimeError("Updates can only install packaged applications")
    archive = Path(zip_path).resolve()
    validate_update_archive(str(archive))
    target = _application_path()
    staging = Path(tempfile.mkdtemp(prefix="petshelf-update-"))
    if os.name == "nt":
        script = staging / "update.ps1"
        log = staging / "update.log"
        backup = target.with_name(f"{target.name}.backup")
        incoming = target.with_name(f"{target.name}.incoming")

        def ps_quote(path: Path) -> str:
            return str(path).replace("'", "''")

        script.write_text(
            "$ErrorActionPreference = 'Stop'\r\n"
            f"Start-Transcript -Path '{ps_quote(log)}' -Force\r\n"
            "try {\r\n"
            f"  Wait-Process -Id {os.getpid()} -ErrorAction SilentlyContinue\r\n"
            f"  Expand-Archive -LiteralPath '{ps_quote(archive)}' -DestinationPath '{ps_quote(staging / 'unpacked')}' -Force\r\n"
            f"  $source = '{ps_quote(staging / 'unpacked' / 'PetShelf')}'\r\n"
            f"  $incoming = '{ps_quote(incoming)}'\r\n"
            f"  $target = '{ps_quote(target)}'\r\n"
            f"  $backup = '{ps_quote(backup)}'\r\n"
            "  if (-not (Test-Path -LiteralPath (Join-Path $source 'PetShelf.exe'))) { throw 'The extracted update has no PetShelf.exe.' }\r\n"
            "  Remove-Item -LiteralPath $incoming -Recurse -Force -ErrorAction SilentlyContinue\r\n"
            "  Move-Item -LiteralPath $source -Destination $incoming -Force\r\n"
            "  Remove-Item -LiteralPath $backup -Recurse -Force -ErrorAction SilentlyContinue\r\n"
            "  if (Test-Path -LiteralPath $target) { Move-Item -LiteralPath $target -Destination $backup -Force }\r\n"
            "  try { Move-Item -LiteralPath $incoming -Destination $target -Force }\r\n"
            "  catch { if (-not (Test-Path -LiteralPath $target) -and (Test-Path -LiteralPath $backup)) { Move-Item -LiteralPath $backup -Destination $target -Force }; throw }\r\n"
            "  Start-Process -FilePath (Join-Path $target 'PetShelf.exe')\r\n"
            "  Remove-Item -LiteralPath $backup -Recurse -Force -ErrorAction SilentlyContinue\r\n"
            "}\r\n"
            "catch { Write-Error $_ }\r\n"
            "finally { Stop-Transcript }\r\n",
            encoding="utf-8",
        )
        subprocess.Popen(
            ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script)],
            cwd=str(staging),
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        return

    script = staging / "update.sh"
    extracted = staging / "unpacked"
    log = staging / "update.log"
    script.write_text(
        "#!/bin/sh\n"
        f"exec >> '{log}' 2>&1\n"
        "echo 'Pet Shelf updater started'\n"
        "sleep 2\n"
        f"ditto -x -k '{archive}' '{extracted}'\n"
        f"test -x '{extracted / 'PetShelf.app' / 'Contents' / 'MacOS' / 'PetShelf'}'\n"
        f"rm -rf '{target}'\n"
        f"mv '{extracted / 'PetShelf.app'}' '{target}'\n"
        f"open '{target}'\n"
        f"rm -rf '{staging}'\n",
        encoding="utf-8",
    )
    script.chmod(0o700)
    subprocess.Popen(["/bin/sh", str(script)], cwd=str(staging), start_new_session=True)
