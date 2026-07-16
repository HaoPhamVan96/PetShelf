from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

from PIL import Image, ImageOps
from PIL.ImageQt import ImageQt
from PySide6.QtCore import QSize, Qt, QTimer, Signal
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .models import ANIMATIONS, ATLAS_COLUMNS, CELL_HEIGHT, CELL_WIDTH, Pet


ROW_NAMES = list(ANIMATIONS) + ["look-directions-a", "look-directions-b"]


def fit_frame(source: Image.Image, cell_width: int = CELL_WIDTH, cell_height: int = CELL_HEIGHT) -> Image.Image:
    source = source.convert("RGBA")
    fitted = ImageOps.contain(source, (cell_width, cell_height), Image.Resampling.LANCZOS)
    frame = Image.new("RGBA", (cell_width, cell_height), (0, 0, 0, 0))
    frame.alpha_composite(fitted, ((cell_width - fitted.width) // 2, (cell_height - fitted.height) // 2))
    return frame


def replace_atlas_cell(
    atlas: Image.Image,
    row: int,
    column: int,
    frame: Image.Image,
    cell_width: int = CELL_WIDTH,
    cell_height: int = CELL_HEIGHT,
) -> Image.Image:
    rows = atlas.height // cell_height
    if not 0 <= row < rows or not 0 <= column < ATLAS_COLUMNS:
        raise ValueError("cell is outside the spritesheet")
    result = atlas.convert("RGBA").copy()
    result.paste((0, 0, 0, 0), (column * cell_width, row * cell_height, (column + 1) * cell_width, (row + 1) * cell_height))
    result.alpha_composite(fit_frame(frame, cell_width, cell_height), (column * cell_width, row * cell_height))
    return result


def frame_from_image_or_atlas(
    source: Image.Image,
    row: int,
    column: int,
    cell_width: int = CELL_WIDTH,
    cell_height: int = CELL_HEIGHT,
) -> Image.Image:
    """Use a normal image as a frame, or crop the matching cell from an atlas."""
    rgba = source.convert("RGBA")
    looks_like_atlas = (
        rgba.width == ATLAS_COLUMNS * cell_width
        and rgba.height % cell_height == 0
        and row < rgba.height // cell_height
    )
    if looks_like_atlas:
        return rgba.crop(
            (
                column * cell_width,
                row * cell_height,
                (column + 1) * cell_width,
                (row + 1) * cell_height,
            )
        )
    return rgba


def parse_timing(text: str, frame_count: int) -> list[int]:
    try:
        values = [int(part.strip()) for part in text.split(",") if part.strip()]
    except ValueError as exc:
        raise ValueError("Timing must be comma-separated milliseconds") from exc
    if not values:
        values = [140]
    if any(value < 16 or value > 60_000 for value in values):
        raise ValueError("Each frame timing must be between 16 and 60000 ms")
    values = values[:frame_count]
    values.extend([values[-1]] * (frame_count - len(values)))
    return values


def update_action_manifest(
    manifest: dict,
    name: str,
    source_row: str,
    frame_count: int,
    timings: list[int],
    playback: str,
    trigger: str,
) -> None:
    name = name.strip()
    if not name or not name.replace("-", "").replace("_", "").isalnum():
        raise ValueError("Action name may contain letters, numbers, '-' and '_'")
    if source_row not in ANIMATIONS:
        raise ValueError("Custom actions must use a standard animation row")
    animations = manifest.setdefault("animations", {})
    if not isinstance(animations, dict):
        animations = manifest["animations"] = {}
    animations[name] = {
        "sourceRow": source_row,
        "frameCount": frame_count,
        "timingMs": timings,
        "durationMs": sum(timings),
        "playback": playback,
        "loop": playback == "loop",
    }
    actions = manifest.setdefault("actions", {})
    if not isinstance(actions, dict):
        actions = manifest["actions"] = {}
    actions[name] = name

    interactions = manifest.setdefault("interactions", {})
    if not isinstance(interactions, dict):
        interactions = manifest["interactions"] = {}
    for event in ("hover", "click"):
        raw = interactions.get(event)
        if not isinstance(raw, dict):
            continue
        if raw.get("animation") == name:
            interactions.pop(event, None)
            continue
        names = raw.get("animations")
        if isinstance(names, list) and name in names:
            names = [value for value in names if value != name]
            if names:
                raw["animations"] = names
            else:
                interactions.pop(event, None)
    if trigger in ("hover", "click"):
        interactions[trigger] = {
            "animation": name,
            "mode": "single",
            "playback": playback,
            "trigger": trigger,
            "event": "pointerenter" if trigger == "hover" else "click",
            "click": trigger == "click",
        }
    if not interactions:
        manifest.pop("interactions", None)


class SpriteEditorDialog(QDialog):
    saved = Signal(str)

    def __init__(self, pet: Pet, parent=None) -> None:
        super().__init__(parent)
        self.pet = pet
        self.atlas = pet.atlas.copy()
        self.cell_width = pet.cell_width
        self.cell_height = pet.cell_height
        self.manifest_path = pet.folder / "pet.json"
        self.manifest = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        self.rows = self.atlas.height // self.cell_height
        self.selected_row = 0
        self.selected_column = 0
        self.preview_index = 0
        self.setWindowTitle(f"Edit Pet — {pet.display_name}")
        self.resize(1220, 780)
        self.setMinimumSize(960, 640)

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 16, 18, 16)
        root.setSpacing(12)
        header = QHBoxLayout()
        title = QLabel(f"Sprite & Action Editor — {pet.display_name}")
        title.setObjectName("settingsTitle")
        header.addWidget(title)
        header.addStretch()
        header.addWidget(QLabel(f"{self.atlas.width}×{self.atlas.height} · {self.rows} rows"))
        root.addLayout(header)

        toolbar = QHBoxLayout()
        for label, handler in (
            ("Replace Frame…", self.replace_frame),
            ("Clear Frame", self.clear_frame),
            ("Export Selected…", self.export_frame),
            ("Import Spritesheet…", self.import_spritesheet),
        ):
            button = QPushButton(label)
            button.clicked.connect(handler)
            toolbar.addWidget(button)
        toolbar.addStretch()
        root.addLayout(toolbar)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        root.addWidget(splitter, 1)

        grid_host = QWidget()
        grid_layout = QVBoxLayout(grid_host)
        grid_layout.setContentsMargins(0, 0, 0, 0)
        self.grid = QTableWidget(self.rows, ATLAS_COLUMNS)
        self.grid.setIconSize(QSize(64, 70))
        self.grid.setShowGrid(True)
        self.grid.setSelectionMode(QTableWidget.SelectionMode.ExtendedSelection)
        self.grid.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectItems)
        self.grid.verticalHeader().setDefaultSectionSize(82)
        self.grid.horizontalHeader().setDefaultSectionSize(76)
        self.grid.setHorizontalHeaderLabels([str(index) for index in range(ATLAS_COLUMNS)])
        self.grid.setVerticalHeaderLabels(ROW_NAMES[: self.rows])
        self.grid.currentCellChanged.connect(self.cell_selected)
        self.grid.cellDoubleClicked.connect(self.empty_cell_double_clicked)
        grid_layout.addWidget(self.grid)
        splitter.addWidget(grid_host)

        panel = QWidget()
        panel.setMinimumWidth(360)
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(14, 0, 0, 0)
        panel_layout.setSpacing(12)
        self.preview = QLabel()
        self.preview.setFixedSize(self.cell_width, self.cell_height)
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview.setObjectName("spritePreview")
        panel_layout.addWidget(self.preview, alignment=Qt.AlignmentFlag.AlignHCenter)

        form = QFormLayout()
        self.action_name = QComboBox()
        self.action_name.setEditable(True)
        self.action_name.addItem("New action…")
        animations = self.manifest.get("animations", {})
        if isinstance(animations, dict):
            self.action_name.addItems(sorted(animations))
        self.action_name.currentTextChanged.connect(self.load_action)
        form.addRow("Action name", self.action_name)
        self.source_row = QComboBox()
        self.source_row.addItems(ANIMATIONS.keys())
        self.source_row.currentTextChanged.connect(self.source_row_changed)
        form.addRow("Source row", self.source_row)
        self.frame_count = QSpinBox()
        self.frame_count.setRange(1, ATLAS_COLUMNS)
        self.frame_count.setValue(6)
        form.addRow("Frame count", self.frame_count)
        self.timing = QLineEdit("140, 140, 140, 140, 140, 280")
        self.timing.setPlaceholderText("Milliseconds: 140, 140, 280")
        form.addRow("Frame timings", self.timing)
        self.playback = QComboBox()
        self.playback.addItems(("loop", "once"))
        form.addRow("Playback", self.playback)
        self.trigger = QComboBox()
        self.trigger.addItems(("none", "hover", "click"))
        form.addRow("Trigger", self.trigger)
        panel_layout.addLayout(form)

        action_buttons = QHBoxLayout()
        save_action = QPushButton("Apply Action")
        save_action.setObjectName("primaryButton")
        save_action.clicked.connect(self.apply_action)
        delete_action = QPushButton("Delete Action")
        delete_action.clicked.connect(self.delete_action)
        preview_action = QPushButton("Preview")
        preview_action.clicked.connect(self.start_preview)
        action_buttons.addWidget(save_action)
        action_buttons.addWidget(delete_action)
        action_buttons.addWidget(preview_action)
        panel_layout.addLayout(action_buttons)
        panel_layout.addStretch()
        splitter.addWidget(panel)
        splitter.setSizes((820, 380))

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.save_files)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

        self.preview_timer = QTimer(self)
        self.preview_timer.setSingleShot(True)
        self.preview_timer.timeout.connect(self.next_preview_frame)
        self.refresh_grid()
        self.grid.setCurrentCell(0, 0)

    def cell_image(self, row: int, column: int) -> Image.Image:
        return self.atlas.crop((column * self.cell_width, row * self.cell_height, (column + 1) * self.cell_width, (row + 1) * self.cell_height))

    def refresh_grid(self) -> None:
        for row in range(self.rows):
            for column in range(ATLAS_COLUMNS):
                image = self.cell_image(row, column)
                pixmap = QPixmap.fromImage(ImageQt(image)).scaled(64, 70, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
                item = self.grid.item(row, column) or QTableWidgetItem()
                item.setIcon(QIcon(pixmap))
                item.setToolTip(f"Row {row} ({ROW_NAMES[row]}), frame {column}")
                self.grid.setItem(row, column, item)

    def refresh_cell(self, row: int, column: int) -> None:
        image = self.cell_image(row, column)
        pixmap = QPixmap.fromImage(ImageQt(image)).scaled(64, 70, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        self.grid.item(row, column).setIcon(QIcon(pixmap))
        self.show_preview(image)

    def show_preview(self, image: Image.Image) -> None:
        self.preview.setPixmap(QPixmap.fromImage(ImageQt(image)))

    def cell_selected(self, row: int, column: int, *_args) -> None:
        if row < 0 or column < 0:
            return
        self.selected_row, self.selected_column = row, column
        self.show_preview(self.cell_image(row, column))

    def replace_frame(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Choose replacement frame", str(self.pet.folder), "Images (*.png *.webp *.jpg *.jpeg)")
        if not path:
            return
        try:
            with Image.open(path) as source:
                source.load()
                frame = frame_from_image_or_atlas(source, self.selected_row, self.selected_column, self.cell_width, self.cell_height)
                self.atlas = replace_atlas_cell(self.atlas, self.selected_row, self.selected_column, frame, self.cell_width, self.cell_height)
        except OSError as exc:
            QMessageBox.critical(self, "Cannot replace frame", str(exc))
            return
        self.refresh_cell(self.selected_row, self.selected_column)

    def empty_cell_double_clicked(self, row: int, column: int) -> None:
        self.selected_row, self.selected_column = row, column
        alpha = self.cell_image(row, column).getchannel("A")
        if alpha.getbbox() is None:
            self.replace_frame()

    def clear_frame(self) -> None:
        empty = Image.new("RGBA", (self.cell_width, self.cell_height), (0, 0, 0, 0))
        self.atlas = replace_atlas_cell(self.atlas, self.selected_row, self.selected_column, empty, self.cell_width, self.cell_height)
        self.refresh_cell(self.selected_row, self.selected_column)

    def export_frame(self) -> None:
        cells = sorted({(index.row(), index.column()) for index in self.grid.selectedIndexes()})
        if not cells:
            cells = [(self.selected_row, self.selected_column)]
        if len(cells) == 1:
            row, column = cells[0]
            default_name = f"{ROW_NAMES[row]}-frame-{column}.png"
            path, _ = QFileDialog.getSaveFileName(self, "Export frame", default_name, "PNG image (*.png)")
            if path:
                self.cell_image(row, column).save(path, "PNG")
            return
        folder = QFileDialog.getExistingDirectory(self, f"Export {len(cells)} selected frames", str(self.pet.folder))
        if not folder:
            return
        output = Path(folder)
        for row, column in cells:
            self.cell_image(row, column).save(output / f"{ROW_NAMES[row]}-frame-{column}.png", "PNG")
        QMessageBox.information(self, "Frames exported", f"Exported {len(cells)} frames to {output}.")

    def import_spritesheet(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Import spritesheet", str(self.pet.folder), "Spritesheets (*.webp *.png)")
        if not path:
            return
        try:
            with Image.open(path) as source:
                source.load()
                candidate = source.convert("RGBA")
        except OSError as exc:
            QMessageBox.critical(self, "Cannot import spritesheet", str(exc))
            return
        if candidate.size != self.atlas.size:
            QMessageBox.critical(self, "Wrong spritesheet size", f"Expected {self.atlas.width}×{self.atlas.height}, got {candidate.width}×{candidate.height}.")
            return
        self.atlas = candidate
        self.refresh_grid()
        self.cell_selected(self.selected_row, self.selected_column)

    def source_row_changed(self, name: str) -> None:
        spec = ANIMATIONS.get(name)
        if spec:
            self.grid.setCurrentCell(spec.row, 0)
            self.frame_count.setValue(len(spec.durations_ms))
            self.timing.setText(", ".join(str(value) for value in spec.durations_ms))

    def load_action(self, name: str) -> None:
        raw = self.manifest.get("animations", {}).get(name) if isinstance(self.manifest.get("animations"), dict) else None
        if not isinstance(raw, dict):
            return
        source = raw.get("sourceRow", "idle")
        if source not in ANIMATIONS:
            source = "idle"
        self.source_row.setCurrentText(source)
        self.frame_count.setValue(int(raw.get("frameCount", len(ANIMATIONS[source].durations_ms))))
        timings = raw.get("timingMs", ANIMATIONS[source].durations_ms)
        self.timing.setText(", ".join(str(value) for value in timings))
        self.playback.setCurrentText("loop" if raw.get("loop") or raw.get("playback") == "loop" else "once")
        self.trigger.setCurrentText(self._trigger_for(name))

    def _trigger_for(self, name: str) -> str:
        interactions = self.manifest.get("interactions", {})
        if isinstance(interactions, dict):
            for event in ("hover", "click"):
                raw = interactions.get(event)
                if isinstance(raw, dict) and (raw.get("animation") == name or name in raw.get("animations", [])):
                    return event
        return "none"

    def apply_action(self) -> None:
        if not self._store_current_action():
            return
        name = self.action_name.currentText().strip()
        QMessageBox.information(self, "Action applied", f"'{name}' is ready in the editor. Press Save to write pet.json.")

    def _store_current_action(self) -> bool:
        name = self.action_name.currentText().strip()
        if name == "New action…":
            QMessageBox.information(self, "Name the action", "Enter a custom action name first.")
            return False
        try:
            timings = parse_timing(self.timing.text(), self.frame_count.value())
            update_action_manifest(self.manifest, name, self.source_row.currentText(), self.frame_count.value(), timings, self.playback.currentText(), self.trigger.currentText())
        except ValueError as exc:
            QMessageBox.critical(self, "Invalid action", str(exc))
            return False
        if self.action_name.findText(name) < 0:
            self.action_name.addItem(name)
        return True

    def delete_action(self) -> None:
        name = self.action_name.currentText().strip()
        animations = self.manifest.get("animations", {})
        if not isinstance(animations, dict) or name not in animations:
            return
        animations.pop(name)
        if not animations:
            self.manifest.pop("animations", None)
        actions = self.manifest.get("actions", {})
        if isinstance(actions, dict):
            actions.pop(name, None)
            if not actions:
                self.manifest.pop("actions", None)
        interactions = self.manifest.get("interactions", {})
        if isinstance(interactions, dict):
            for event in ("hover", "click"):
                raw = interactions.get(event)
                if isinstance(raw, dict) and raw.get("animation") == name:
                    interactions.pop(event, None)
        index = self.action_name.findText(name)
        if index >= 0:
            self.action_name.removeItem(index)
        self.action_name.setCurrentIndex(0)

    def start_preview(self) -> None:
        self.preview_index = 0
        self.next_preview_frame()

    def next_preview_frame(self) -> None:
        source = self.source_row.currentText()
        spec = ANIMATIONS[source]
        count = self.frame_count.value()
        try:
            timings = parse_timing(self.timing.text(), count)
        except ValueError as exc:
            QMessageBox.critical(self, "Invalid timing", str(exc))
            return
        self.show_preview(self.cell_image(spec.row, self.preview_index))
        delay = timings[self.preview_index]
        self.preview_index += 1
        if self.preview_index >= count:
            if self.playback.currentText() != "loop":
                return
            self.preview_index = 0
        self.preview_timer.start(delay)

    def save_files(self) -> None:
        if self.action_name.currentText().strip() != "New action…" and not self._store_current_action():
            return
        sprite_path = self.pet.spritesheet_path
        try:
            for path in (sprite_path, self.manifest_path):
                backup = path.with_suffix(path.suffix + ".bak")
                if path.exists() and not backup.exists():
                    shutil.copy2(path, backup)
            sprite_temp = sprite_path.with_name(sprite_path.stem + ".editing" + sprite_path.suffix)
            if sprite_path.suffix.lower() == ".webp":
                self.atlas.save(sprite_temp, "WEBP", lossless=True, method=6)
            else:
                self.atlas.save(sprite_temp, "PNG")
            os.replace(sprite_temp, sprite_path)
            manifest_temp = self.manifest_path.with_name("pet.json.editing")
            manifest_temp.write_text(json.dumps(self.manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            os.replace(manifest_temp, self.manifest_path)
        except OSError as exc:
            QMessageBox.critical(self, "Save failed", str(exc))
            return
        self.saved.emit(self.pet.pet_id)
        self.accept()
