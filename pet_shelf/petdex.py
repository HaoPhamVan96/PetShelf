from __future__ import annotations

import os
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from PySide6.QtCore import QByteArray, QProcess, QProcessEnvironment, Qt, QTimer, QUrl, QUrlQuery, Signal
from PySide6.QtGui import QCloseEvent, QDesktopServices, QPixmap
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)


PETDEX_ORIGIN = "https://petdex.dev"
ANSI_ESCAPE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,62}$")


@dataclass(frozen=True)
class PetDexPet:
    slug: str
    display_name: str
    description: str
    creator: str
    install_count: int
    thumbnail_url: str
    page_url: str

    @classmethod
    def from_payload(cls, payload: dict) -> "PetDexPet":
        slug = str(payload.get("slug", "")).strip()
        if not SLUG_RE.fullmatch(slug):
            slug = ""
        creator_data = payload.get("submittedBy")
        creator = creator_data.get("name", "") if isinstance(creator_data, dict) else ""
        metrics = payload.get("metrics")
        install_count = metrics.get("installCount", 0) if isinstance(metrics, dict) else 0
        return cls(
            slug=slug,
            display_name=str(payload.get("displayName") or slug),
            description=str(payload.get("description") or "No description."),
            creator=str(creator or "PetDex creator"),
            install_count=int(install_count or 0),
            thumbnail_url=f"{PETDEX_ORIGIN}/api/pets/{slug}/thumb",
            page_url=f"{PETDEX_ORIGIN}/pets/{slug}",
        )


def resolve_petdex_cli(
    which: Callable[[str], str | None] | None = None,
    candidates: list[Path] | None = None,
) -> tuple[str, list[str]] | None:
    """Return the official PetDex CLI launcher and its fixed prefix args."""
    which = which or shutil.which
    petdex = which("petdex")
    if petdex:
        return petdex, []
    npx = which("npx") or which("npx.cmd")
    if npx:
        return npx, ["--yes", "petdex"]
    if candidates is None:
        candidates = [
            Path("/opt/homebrew/bin/npx"),
            Path("/usr/local/bin/npx"),
            Path.home() / ".local" / "bin" / "npx",
            Path.home() / ".volta" / "bin" / "npx",
            Path.home() / ".fnm" / "current" / "bin" / "npx",
            Path.home() / "AppData" / "Roaming" / "npm" / "npx.cmd",
        ]
        nvm_root = Path.home() / ".nvm" / "versions" / "node"
        if nvm_root.is_dir():
            candidates.extend(sorted(nvm_root.glob("*/bin/npx"), reverse=True))
        for variable in ("NVM_SYMLINK", "NVM_HOME"):
            if os.environ.get(variable):
                candidates.append(Path(os.environ[variable]) / "npx.cmd")
    for candidate in candidates:
        if candidate.is_file():
            return str(candidate), ["--yes", "petdex"]
    return None


class PetDexClient(QWidget):
    search_finished = Signal(list, object, int)
    search_failed = Signal(str)
    thumbnail_finished = Signal(str, QPixmap)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.network = QNetworkAccessManager(self)
        self._search_reply: QNetworkReply | None = None

    @staticmethod
    def search_url(query: str, cursor: int = 0, limit: int = 40) -> QUrl:
        url = QUrl(f"{PETDEX_ORIGIN}/api/pets/search")
        params = QUrlQuery()
        params.addQueryItem("q", query.strip())
        params.addQueryItem("sort", "alpha" if not query.strip() else "popular")
        params.addQueryItem("cursor", str(max(0, cursor)))
        params.addQueryItem("limit", str(max(1, min(50, limit))))
        params.addQueryItem("includeMeta", "1" if cursor == 0 else "0")
        url.setQuery(params)
        return url

    def search(self, query: str, cursor: int = 0) -> None:
        if self._search_reply and self._search_reply.isRunning():
            self._search_reply.abort()
        request = QNetworkRequest(self.search_url(query, cursor))
        request.setRawHeader(b"User-Agent", b"PetShelf/1.1 (+https://petdex.dev)")
        reply = self.network.get(request)
        self._search_reply = reply
        reply.finished.connect(lambda: self._finish_search(reply))

    def _finish_search(self, reply: QNetworkReply) -> None:
        if reply.error() == QNetworkReply.NetworkError.OperationCanceledError:
            reply.deleteLater()
            return
        if reply.error() != QNetworkReply.NetworkError.NoError:
            self.search_failed.emit(reply.errorString())
            reply.deleteLater()
            return
        try:
            import json

            payload = json.loads(bytes(reply.readAll()).decode("utf-8"))
            pets = [PetDexPet.from_payload(item) for item in payload.get("pets", [])]
            pets = [pet for pet in pets if pet.slug]
            next_cursor = payload.get("nextCursor")
            total = int(payload["total"]) if "total" in payload else -1
        except (ValueError, TypeError, UnicodeDecodeError) as exc:
            self.search_failed.emit(f"Invalid PetDex response: {exc}")
        else:
            self.search_finished.emit(pets, next_cursor, total)
        reply.deleteLater()

    def fetch_thumbnail(self, pet: PetDexPet) -> None:
        request = QNetworkRequest(QUrl(pet.thumbnail_url))
        request.setRawHeader(b"User-Agent", b"PetShelf/1.1 (+https://petdex.dev)")
        reply = self.network.get(request)
        reply.finished.connect(lambda: self._finish_thumbnail(pet.slug, reply))

    def _finish_thumbnail(self, slug: str, reply: QNetworkReply) -> None:
        if reply.error() == QNetworkReply.NetworkError.NoError:
            pixmap = QPixmap()
            if pixmap.loadFromData(QByteArray(reply.readAll())):
                self.thumbnail_finished.emit(slug, pixmap)
        reply.deleteLater()


class PetDexRow(QFrame):
    install_requested = Signal(object)

    def __init__(self, pet: PetDexPet, installed: bool) -> None:
        super().__init__()
        self.pet = pet
        self.setObjectName("petdexRow")
        self.setMinimumHeight(108)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(14)

        self.preview = QLabel("⋯")
        self.preview.setObjectName("petdexPreview")
        self.preview.setFixedSize(72, 78)
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.preview)

        copy = QVBoxLayout()
        copy.setSpacing(3)
        title = QLabel(pet.display_name)
        title.setObjectName("petTitle")
        description = QLabel(pet.description)
        description.setObjectName("petDescription")
        description.setWordWrap(True)
        description.setMaximumHeight(42)
        meta = QLabel(f"by {pet.creator}  ·  {pet.install_count:,} installs  ·  {pet.slug}")
        meta.setObjectName("petdexMeta")
        copy.addWidget(title)
        copy.addWidget(description)
        copy.addWidget(meta)
        layout.addLayout(copy, 1)

        page = QPushButton("View")
        page.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(pet.page_url)))
        layout.addWidget(page)
        self.install_button = QPushButton("Installed" if installed else "Install")
        self.install_button.setEnabled(not installed)
        if not installed:
            self.install_button.setObjectName("primaryButton")
        self.install_button.clicked.connect(lambda: self.install_requested.emit(self.pet))
        layout.addWidget(self.install_button)

    def set_thumbnail(self, pixmap: QPixmap) -> None:
        self.preview.setText("")
        self.preview.setPixmap(
            pixmap.scaled(
                self.preview.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )

    def set_installing(self, installing: bool) -> None:
        if installing:
            self.install_button.setText("Installing…")
            self.install_button.setEnabled(False)

    def set_installed(self) -> None:
        self.install_button.setText("Installed")
        self.install_button.setEnabled(False)

    def reset_install(self) -> None:
        self.install_button.setText("Install")
        self.install_button.setEnabled(True)


class PetDexDialog(QDialog):
    installed = Signal(str)

    def __init__(self, installed_slugs: set[str] | None = None, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("PetDex Gallery")
        self.resize(920, 680)
        self.setMinimumSize(700, 480)
        self.installed_slugs = set(installed_slugs or set())
        self.rows: dict[str, PetDexRow] = {}
        self.next_cursor: int | None = None
        self.total = 0
        self.current_query = ""
        self.install_process: QProcess | None = None
        self.installing_row: PetDexRow | None = None
        self.client = PetDexClient(self)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 20, 24, 16)
        outer.setSpacing(12)
        header = QHBoxLayout()
        heading = QLabel("PetDex")
        heading.setObjectName("pageTitle")
        header.addWidget(heading)
        header.addStretch()
        browse = QPushButton("Open petdex.dev")
        browse.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(PETDEX_ORIGIN)))
        header.addWidget(browse)
        outer.addLayout(header)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search 3,700+ pets by name, character or vibe…")
        self.search_input.setClearButtonEnabled(True)
        outer.addWidget(self.search_input)

        self.status = QLabel("Loading PetDex gallery…")
        self.status.setObjectName("pathLabel")
        outer.addWidget(self.status)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.results = QWidget()
        self.results_layout = QVBoxLayout(self.results)
        self.results_layout.setContentsMargins(0, 0, 0, 0)
        self.results_layout.setSpacing(0)
        self.scroll.setWidget(self.results)
        outer.addWidget(self.scroll, 1)

        footer = QHBoxLayout()
        self.progress = QProgressBar()
        self.progress.setVisible(False)
        self.progress.setTextVisible(True)
        self.progress.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        footer.addWidget(self.progress, 1)
        self.more_button = QPushButton("Load more")
        self.more_button.setVisible(False)
        self.more_button.clicked.connect(self.load_more)
        footer.addWidget(self.more_button)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        footer.addWidget(buttons)
        outer.addLayout(footer)

        self.search_timer = QTimer(self)
        self.search_timer.setSingleShot(True)
        self.search_timer.setInterval(350)
        self.search_timer.timeout.connect(self.start_search)
        self.search_input.textChanged.connect(lambda: self.search_timer.start())
        self.client.search_finished.connect(self._search_finished)
        self.client.search_failed.connect(self._search_failed)
        self.client.thumbnail_finished.connect(self._thumbnail_finished)
        QTimer.singleShot(0, self.start_search)

    def start_search(self) -> None:
        self.current_query = self.search_input.text().strip()
        self.next_cursor = None
        self._clear_results()
        self.status.setText("Searching PetDex…")
        self.more_button.setVisible(False)
        self.client.search(self.current_query)

    def load_more(self) -> None:
        if self.next_cursor is None:
            return
        self.more_button.setEnabled(False)
        self.status.setText("Loading more pets…")
        self.client.search(self.current_query, self.next_cursor)

    def _search_finished(self, pets: list[PetDexPet], next_cursor: int | None, total: int) -> None:
        self.next_cursor = int(next_cursor) if next_cursor is not None else None
        if total >= 0:
            self.total = total
        for pet in pets:
            if pet.slug in self.rows:
                continue
            row = PetDexRow(pet, pet.slug in self.installed_slugs)
            row.install_requested.connect(self.install_pet)
            self.rows[pet.slug] = row
            self.results_layout.addWidget(row)
            self.client.fetch_thumbnail(pet)
        if not self.rows:
            self.status.setText("No matching pets found. The gacha banner is empty, senpai.")
        else:
            self.status.setText(f"Showing {len(self.rows):,} of {self.total:,} PetDex pets")
        self.more_button.setVisible(self.next_cursor is not None)
        self.more_button.setEnabled(True)

    def _search_failed(self, message: str) -> None:
        self.status.setText(f"Could not load PetDex: {message}")
        self.more_button.setVisible(False)

    def _thumbnail_finished(self, slug: str, pixmap: QPixmap) -> None:
        row = self.rows.get(slug)
        if row:
            row.set_thumbnail(pixmap)

    def _clear_results(self) -> None:
        while self.results_layout.count():
            item = self.results_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.rows.clear()

    def install_pet(self, pet: PetDexPet) -> None:
        if self.install_process and self.install_process.state() != QProcess.ProcessState.NotRunning:
            return
        command = resolve_petdex_cli()
        if not command:
            QMessageBox.warning(
                self,
                "PetDex CLI not found",
                "Install Node.js 20+ or the official PetDex CLI first, then reopen Pet Shelf.\n\n"
                "Command: npm install -g petdex",
            )
            return
        program, prefix = command
        process = QProcess(self)
        process.setProgram(program)
        process.setArguments([*prefix, "install", pet.slug])
        process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        env = QProcessEnvironment.systemEnvironment()
        existing_path = env.value("PATH")
        extra = os.pathsep.join(
            [
                str(Path(program).parent),
                "/opt/homebrew/bin",
                "/usr/local/bin",
                str(Path.home() / ".local/bin"),
            ]
        )
        env.insert("PATH", f"{extra}{os.pathsep}{existing_path}")
        process.setProcessEnvironment(env)
        process.readyReadStandardOutput.connect(lambda: self._install_output(process))
        process.errorOccurred.connect(lambda error: self._install_error(process.errorString()))
        process.finished.connect(lambda code, status: self._install_finished(pet, int(code)))
        self.install_process = process
        self.installing_row = self.rows.get(pet.slug)
        self.search_timer.stop()
        self.search_input.setEnabled(False)
        self.more_button.setEnabled(False)
        if self.installing_row:
            self.installing_row.set_installing(True)
        self.progress.setRange(0, 0)
        self.progress.setFormat(f"Installing {pet.display_name}…")
        self.progress.setVisible(True)
        self.status.setText(f"PetDex CLI is summoning {pet.display_name}…")
        self._set_install_buttons_enabled(False)
        process.start()

    def _install_output(self, process: QProcess) -> None:
        output = bytes(process.readAllStandardOutput()).decode("utf-8", errors="replace")
        clean_lines = [ANSI_ESCAPE.sub("", line).strip() for line in output.splitlines() if line.strip()]
        if clean_lines:
            self.status.setText(clean_lines[-1])

    def _install_error(self, message: str) -> None:
        self.status.setText(f"PetDex CLI error: {message}")

    def _install_finished(self, pet: PetDexPet, exit_code: int) -> None:
        success = exit_code == 0 and (Path.home() / ".codex" / "pets" / pet.slug / "pet.json").is_file()
        self._finish_install_ui(success)
        if success:
            self.installed_slugs.add(pet.slug)
            if self.installing_row:
                self.installing_row.set_installed()
            self.status.setText(f"{pet.display_name} installed. Pet acquired! ✨")
            self.installed.emit(pet.slug)
        else:
            if self.installing_row:
                self.installing_row.reset_install()
            QMessageBox.critical(
                self,
                "PetDex install failed",
                f"The official PetDex CLI exited with code {exit_code}. Check the message above and try again.",
            )
        self.install_process = None
        self.installing_row = None

    def _finish_install_ui(self, success: bool) -> None:
        self.progress.setRange(0, 100)
        self.progress.setValue(100 if success else 0)
        self.progress.setVisible(False)
        self.search_input.setEnabled(True)
        self.more_button.setEnabled(self.next_cursor is not None)
        self._set_install_buttons_enabled(True)

    def _set_install_buttons_enabled(self, enabled: bool) -> None:
        for slug, row in self.rows.items():
            if slug not in self.installed_slugs and row is not self.installing_row:
                row.install_button.setEnabled(enabled)

    def closeEvent(self, event: QCloseEvent) -> None:
        if self.install_process and self.install_process.state() != QProcess.ProcessState.NotRunning:
            QMessageBox.information(self, "Install in progress", "Please wait until PetDex finishes installing the pet.")
            event.ignore()
            return
        super().closeEvent(event)
