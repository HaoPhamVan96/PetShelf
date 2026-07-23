from __future__ import annotations

import os
import math
import random
import shutil
import subprocess
import sys
from pathlib import Path

from PIL.ImageQt import ImageQt
from PySide6.QtCore import QEvent, QPoint, QSettings, QSize, Qt, QThread, QTimer, Signal
from PySide6.QtGui import QAction, QColor, QCloseEvent, QCursor, QFont, QIcon, QMouseEvent, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QColorDialog,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSlider,
    QSizePolicy,
    QSystemTrayIcon,
    QVBoxLayout,
    QWidget,
)

from .models import ANIMATIONS, AnimationSpec, Pet, PetLoadError, add_silhouette_outline, scan_pet_root
from .editor import SpriteEditorDialog
from .petdex import PetDexDialog
from .updater import UpdateInfo, UpdateWorker, install_after_exit


def pixmap_from_pil(image) -> QPixmap:
    return QPixmap.fromImage(ImageQt(image))


def tray_icon_pixmap(size: int = 64) -> QIcon:
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    font = QFont()
    font.setPointSize(round(size * 0.62))
    painter.setFont(font)
    painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, "\U0001F43E")
    painter.end()
    return QIcon(pixmap)


def drag_animation_for_delta(delta_x: int) -> str | None:
    if delta_x < 0:
        return "running-left"
    if delta_x > 0:
        return "running-right"
    return None


def animation_cycle_should_end(spec: AnimationSpec, active_interaction: str | None) -> bool:
    return not spec.loop or active_interaction == "click"


def open_in_file_manager(path: Path) -> None:
    if sys.platform == "darwin":
        subprocess.Popen(["open", str(path)])
    elif os.name == "nt":
        os.startfile(str(path))  # type: ignore[attr-defined]
    else:
        subprocess.Popen(["xdg-open", str(path)])


class PetOverlay(QWidget):
    hidden_by_user = Signal(str)
    BASE_WIDTH = 192
    BASE_HEIGHT = 208
    CYCLE_EXCLUDED_STATES = {"idle", "running-left", "running-right"}
    CYCLE_MIN_DELAY_MS = 6000
    CYCLE_MAX_DELAY_MS = 15000

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Pet Shelf Pet")
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        # Qt maps Tool windows to NSPanel on macOS. Without this attribute,
        # macOS hides every pet when Pet Shelf is minimized or loses focus.
        self.setAttribute(Qt.WidgetAttribute.WA_MacAlwaysShowToolWindow)
        self.setObjectName("petOverlay")
        self.setStyleSheet(
            "QWidget#petOverlay { background: transparent; border: none; } "
            "QWidget#petOverlay QLabel { background: transparent; border: none; }"
        )
        self.display_scale = 1.0
        self.base_width = self.BASE_WIDTH
        self.base_height = self.BASE_HEIGHT
        self.setFixedSize(self.base_width, self.base_height)
        self.label = QLabel(self)
        self.label.setFixedSize(self.size())
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.pet: Pet | None = None
        self.state = "idle"
        self.frame_index = 0
        self.drag_offset: QPoint | None = None
        self.press_position: QPoint | None = None
        self.last_drag_position: QPoint | None = None
        self.drag_animation_active = False
        self.active_interaction: str | None = None
        self.interaction_indices: dict[str, int] = {}
        self.animation_speed = 1.0
        self.follow_pointer = True
        self.look_direction: int | None = None
        self.border_enabled = False
        self.border_color = "#202124"
        self.cycle_enabled = False
        self.loop_enabled = False
        self.show_action_name = True
        self.outline_cache: dict[tuple[str, int, int | None, str], object] = {}
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self._next_frame)
        self.look_timer = QTimer(self)
        self.look_timer.setInterval(50)
        self.look_timer.timeout.connect(self._update_pointer_look)
        self.cycle_timer = QTimer(self)
        self.cycle_timer.setSingleShot(True)
        self.cycle_timer.timeout.connect(self._cycle_tick)
        self.cycle_end_timer = QTimer(self)
        self.cycle_end_timer.setSingleShot(True)
        self.cycle_end_timer.timeout.connect(self._end_cycle_animation)

    def set_pet(self, pet: Pet) -> None:
        self.pet = pet
        self.base_width = pet.display_width
        self.base_height = pet.display_height
        self.setFixedSize(round(self.base_width * self.display_scale), round(self.base_height * self.display_scale))
        self.label.setFixedSize(self.size())
        self.state = "idle"
        self.frame_index = 0
        self.active_interaction = None
        self.look_direction = None
        self.interaction_indices.clear()
        self.outline_cache.clear()
        self._render_frame()

    def _decorate(self, image, cache_key: tuple[str, int, int | None, str]):
        if not self.border_enabled:
            return image
        if cache_key not in self.outline_cache:
            self.outline_cache[cache_key] = add_silhouette_outline(image, self.border_color, 1)
        return self.outline_cache[cache_key]

    def _render_frame(self) -> None:
        if not self.pet:
            return
        spec = self.pet.animation_spec(self.state)
        if spec is None:
            self.play_state("idle")
            return
        if self.look_direction is not None and self.pet.sprite_version == 2 and self.state == "idle":
            image = self.pet.look_frame(self.look_direction)
        else:
            image = self.pet.frame(self.state, self.frame_index)
        image = self._decorate(
            image,
            (self.state, self.frame_index, self.look_direction, self.border_color),
        )
        pixmap = self._scaled_pixmap(image)
        label = self._skill_label_text()
        if label:
            self._draw_skill_label(pixmap, label)
        self.label.setPixmap(pixmap)
        duration = max(16, round(spec.durations_ms[self.frame_index] / self.animation_speed))
        self.timer.start(duration)

    def _scaled_pixmap(self, image) -> QPixmap:
        return pixmap_from_pil(image).scaled(
            self.label.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )

    def _skill_label_text(self) -> str:
        if not self.show_action_name or not self.pet or self.state in ANIMATIONS:
            return ""
        return self.pet.animation_display_name(self.state)

    def _draw_skill_label(self, pixmap: QPixmap, text: str) -> None:
        painter = QPainter(pixmap)
        try:
            font = QFont("Segoe UI", max(9, round(self.label.height() * 0.055)))
            font.setBold(True)
            painter.setFont(font)
            metrics = painter.fontMetrics()
            margin = max(6, round(self.label.width() * 0.025))
            padding_x = 7
            padding_y = 4
            rect = metrics.boundingRect(text)
            box_w = min(self.label.width() - margin * 2, rect.width() + padding_x * 2)
            box_h = rect.height() + padding_y * 2
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(10, 18, 30, 190))
            painter.drawRoundedRect(margin, margin, box_w, box_h, 6, 6)
            painter.setPen(QPen(QColor(180, 235, 255), 1))
            painter.drawText(margin + padding_x, margin + padding_y + metrics.ascent(), text)
        finally:
            painter.end()

    def _next_frame(self) -> None:
        if not self.pet:
            return
        spec = self.pet.animation_spec(self.state)
        if spec is None:
            self.play_state("idle")
            return
        count = len(spec.durations_ms)
        if self.frame_index + 1 >= count and animation_cycle_should_end(spec, self.active_interaction):
            was_cycle = self.active_interaction == "cycle"
            self.cycle_end_timer.stop()
            self.active_interaction = None
            self.play_state("idle")
            if self.loop_enabled and was_cycle:
                self._cycle_tick()
            elif self.loop_enabled and self.isVisible():
                self._cycle_tick()
            return
        self.frame_index = (self.frame_index + 1) % count
        self._render_frame()

    def show_pet(self) -> None:
        if not self.pet:
            return
        screen = QApplication.primaryScreen().availableGeometry()
        if not screen.contains(self.geometry().center()):
            self.move(screen.right() - self.width() - 24, screen.bottom() - self.height() - 24)
        self.show()
        self.raise_()
        self._render_frame()
        self.look_timer.start()
        if self.loop_enabled:
            self._cycle_tick()
        elif self.cycle_enabled:
            self._schedule_cycle()

    def hide_pet(self) -> None:
        self.timer.stop()
        self.look_timer.stop()
        self.cycle_timer.stop()
        self.cycle_end_timer.stop()
        self.hide()
        if self.pet:
            self.hidden_by_user.emit(self.pet.pet_id)

    def keep_visible(self) -> None:
        """Detach this overlay's visible state from the manager window state."""
        if not self.pet:
            return
        state = self.windowState() & ~Qt.WindowState.WindowMinimized
        self.setWindowState(state)
        self.show()
        self.raise_()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            global_position = event.globalPosition().toPoint()
            self.drag_offset = global_position - self.frameGeometry().topLeft()
            self.press_position = global_position
            self.last_drag_position = global_position
            self.drag_animation_active = False
            event.accept()
        elif event.button() == Qt.MouseButton.RightButton:
            menu = QMenu(self)
            names = list(ANIMATIONS)
            if self.pet:
                names.extend(self.pet.custom_animations)
            for state in names:
                action = QAction(state.replace("-", " ").title(), menu)
                action.triggered.connect(lambda checked=False, name=state: self._play_manual_state(name))
                menu.addAction(action)
            menu.addSeparator()
            menu.addAction("Hide Pet", self.hide_pet)
            menu.exec(event.globalPosition().toPoint())

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self.drag_offset is not None and event.buttons() & Qt.MouseButton.LeftButton:
            global_position = event.globalPosition().toPoint()
            previous_position = self.last_drag_position or global_position
            delta_x = global_position.x() - previous_position.x()
            self.last_drag_position = global_position
            self.move(global_position - self.drag_offset)
            if self.pet and self.pet.drag_animation_enabled:
                drag_state = drag_animation_for_delta(delta_x)
                if drag_state and drag_state != self.state:
                    self.active_interaction = None
                    self.play_state(drag_state)
                if drag_state:
                    self.drag_animation_active = True
            event.accept()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        released_at = event.globalPosition().toPoint()
        was_click = (
            event.button() == Qt.MouseButton.LeftButton
            and self.press_position is not None
            and (released_at - self.press_position).manhattanLength() <= 6
        )
        self.drag_offset = None
        self.press_position = None
        self.last_drag_position = None
        if was_click:
            self.trigger_interaction("click")
        elif self.drag_animation_active:
            self.active_interaction = None
            self.play_state("idle")
            if self.loop_enabled:
                self._cycle_tick()
        self.drag_animation_active = False
        super().mouseReleaseEvent(event)

    def play_state(self, state: str) -> None:
        if not self.pet or self.pet.animation_spec(state) is None:
            return
        self.state = state
        self.frame_index = 0
        self.look_direction = None
        self._render_frame()

    def _play_manual_state(self, state: str) -> None:
        self.active_interaction = None
        self.play_state(state)

    def set_animation_speed(self, speed: float) -> None:
        self.animation_speed = min(5.0, max(0.1, float(speed)))
        if self.pet and self.isVisible():
            self._render_frame()

    def set_display_scale(self, scale: float) -> None:
        scale = min(3.0, max(0.5, float(scale)))
        if scale == self.display_scale:
            return
        center = self.frameGeometry().center()
        self.display_scale = scale
        self.setFixedSize(round(self.base_width * scale), round(self.base_height * scale))
        self.label.setFixedSize(self.size())
        if self.isVisible():
            self.move(center - QPoint(self.width() // 2, self.height() // 2))
        if self.pet:
            self._render_frame()

    def set_follow_pointer(self, enabled: bool) -> None:
        self.follow_pointer = enabled
        if not enabled and self.look_direction is not None:
            self.look_direction = None
            self._render_frame()

    def set_border(self, enabled: bool, color: str = "#202124") -> None:
        self.border_enabled = enabled
        self.border_color = QColor(color).name() if QColor(color).isValid() else "#202124"
        # The optional outline is rasterized from alpha. The Qt widgets themselves
        # must never contribute a rectangular border, including in the Off state.
        self.setStyleSheet(
            "QWidget#petOverlay { background: transparent; border: none; } "
            "QWidget#petOverlay QLabel { background: transparent; border: none; }"
        )
        self.outline_cache.clear()
        if self.pet:
            self._render_frame()

    def set_cycle_mode(self, enabled: bool) -> None:
        self.cycle_enabled = enabled
        if enabled:
            if self.isVisible():
                self._schedule_cycle()
        else:
            self.cycle_timer.stop()
            self.cycle_end_timer.stop()
            if self.active_interaction == "cycle" and not self.loop_enabled:
                self.active_interaction = None
                self.play_state("idle")

    def set_loop_mode(self, enabled: bool) -> None:
        self.loop_enabled = enabled
        if enabled:
            if self.isVisible() and self.state == "idle" and self.active_interaction is None:
                self._cycle_tick()
        else:
            self.cycle_end_timer.stop()
            if self.active_interaction == "cycle":
                self.active_interaction = None
                self.play_state("idle")
            elif self.cycle_enabled and self.isVisible():
                self._schedule_cycle()

    def set_show_action_name(self, enabled: bool) -> None:
        self.show_action_name = enabled
        if self.pet:
            self._render_frame()

    def _schedule_cycle(self) -> None:
        if not self.cycle_enabled or self.loop_enabled:
            return
        delay = random.randint(self.CYCLE_MIN_DELAY_MS, self.CYCLE_MAX_DELAY_MS)
        self.cycle_timer.start(max(500, round(delay / self.animation_speed)))

    def _cycle_tick(self) -> None:
        if (not self.cycle_enabled and not self.loop_enabled) or not self.pet:
            return
        if self.state != "idle" or self.active_interaction is not None or self.drag_offset is not None:
            self._schedule_cycle()
            return
        names = [name for name in ANIMATIONS if name not in self.CYCLE_EXCLUDED_STATES]
        names.extend(
            name for name in self.pet.custom_animations if name not in self.CYCLE_EXCLUDED_STATES
        )
        if not names:
            self._schedule_cycle()
            return
        choice = random.choice(names)
        self.active_interaction = "cycle"
        self.play_state(choice)
        spec = self.pet.animation_spec(choice)
        duration_ms = sum(spec.durations_ms) if spec else 1000
        self.cycle_end_timer.start(max(200, round(duration_ms / self.animation_speed)))

    def _end_cycle_animation(self) -> None:
        if self.active_interaction == "cycle":
            self.active_interaction = None
            self.play_state("idle")
        if self.loop_enabled:
            self._cycle_tick()
        else:
            self._schedule_cycle()

    def _update_pointer_look(self) -> None:
        if (
            not self.follow_pointer
            or not self.pet
            or self.pet.sprite_version != 2
            or self.active_interaction is not None
            or self.state != "idle"
            or self.drag_offset is not None
        ):
            return
        center = self.mapToGlobal(QPoint(self.width() // 2, self.height() // 2))
        cursor = QCursor.pos()
        dx = cursor.x() - center.x()
        dy = cursor.y() - center.y()
        distance = math.hypot(dx, dy)
        if distance < 18 or distance > 650:
            if self.look_direction is not None:
                self.look_direction = None
                self._render_frame()
            return
        # Contract: 000 is up, 090 right, 180 down, 270 left.
        degrees = math.degrees(math.atan2(dx, -dy)) % 360
        direction = round(degrees / 22.5) % 16
        if direction == self.look_direction:
            return
        self.look_direction = direction
        image = self.pet.look_frame(direction)
        image = self._decorate(image, ("__look__", direction, direction, self.border_color))
        self.label.setPixmap(self._scaled_pixmap(image))

    def trigger_interaction(self, event_name: str) -> bool:
        if not self.pet:
            return False
        interaction = self.pet.interactions.get(event_name)
        if not interaction:
            return False
        if self.active_interaction == "cycle":
            self.cycle_end_timer.stop()
        index = self.interaction_indices.get(event_name, 0)
        if interaction.mode == "cycle":
            animation = interaction.animations[index % len(interaction.animations)]
            self.interaction_indices[event_name] = index + 1
        else:
            animation = interaction.animations[0]
        self.active_interaction = event_name
        self.play_state(animation)
        return True

    def enterEvent(self, event) -> None:
        if self.pet and self.pet.hover_interaction_enabled:
            self.trigger_interaction("hover")
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        if self.active_interaction == "hover" and self.pet and self.pet.hover_interaction_enabled:
            spec = self.pet.animation_spec(self.state)
            if spec and spec.loop:
                self.active_interaction = None
                self.play_state("idle")
                if self.loop_enabled:
                    self._cycle_tick()
        super().leaveEvent(event)


class PetRow(QFrame):
    toggle_requested = Signal(str)
    edit_requested = Signal(str)

    def __init__(self, pet: Pet, visible: bool) -> None:
        super().__init__()
        self.pet = pet
        self.setObjectName("petRow")
        self.setMinimumHeight(128)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(20, 14, 20, 14)
        layout.setSpacing(18)
        thumbnail = QLabel()
        thumbnail.setFixedSize(88, 96)
        thumbnail.setAlignment(Qt.AlignmentFlag.AlignCenter)
        thumbnail.setPixmap(
            pixmap_from_pil(pet.thumbnail).scaled(
                88, 96, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
            )
        )
        layout.addWidget(thumbnail)

        copy = QVBoxLayout()
        copy.setSpacing(5)
        title = QLabel(pet.display_name)
        title.setObjectName("petTitle")
        description = QLabel(pet.description or "No description. A mysterious pet has appeared!")
        description.setObjectName("petDescription")
        description.setWordWrap(True)
        description.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        copy.addStretch()
        copy.addWidget(title)
        copy.addWidget(description)
        copy.addStretch()
        layout.addLayout(copy, 1)

        edit = QPushButton("Edit")
        edit.clicked.connect(lambda: self.edit_requested.emit(self.pet.pet_id))
        layout.addWidget(edit)
        toggle = QPushButton("Hide" if visible else "Show")
        if not visible:
            toggle.setObjectName("primaryButton")
        toggle.clicked.connect(lambda: self.toggle_requested.emit(self.pet.pet_id))
        layout.addWidget(toggle)


class SettingsDialog(QDialog):
    speed_changed = Signal(int)
    size_changed = Signal(int)
    border_changed = Signal(bool, str)
    follow_changed = Signal(bool)
    cycle_changed = Signal(bool)
    loop_changed = Signal(bool)
    show_action_name_changed = Signal(bool)

    def __init__(
        self,
        speed: float,
        pet_scale: float,
        border_enabled: bool,
        border_color: str,
        follow_pointer: bool,
        cycle_mode: bool,
        loop_mode: bool,
        show_action_name: bool,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Pet Settings")
        self.setModal(False)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setMinimumWidth(390)
        self.border_color = QColor(border_color) if QColor(border_color).isValid() else QColor("#202124")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 18)
        layout.setSpacing(18)

        heading = QLabel("Pet Settings")
        heading.setObjectName("settingsTitle")
        layout.addWidget(heading)

        speed_row = QHBoxLayout()
        speed_row.addWidget(QLabel("Animation speed"))
        self.speed_slider = QSlider(Qt.Orientation.Horizontal)
        self.speed_slider.setRange(10, 500)
        self.speed_slider.setSingleStep(10)
        self.speed_slider.setPageStep(25)
        self.speed_slider.setValue(round(speed * 100))
        self.speed_value = QLabel()
        self.speed_value.setFixedWidth(48)
        self._set_speed_label(self.speed_slider.value())
        self.speed_slider.valueChanged.connect(self._speed_updated)
        speed_row.addWidget(self.speed_slider, 1)
        speed_row.addWidget(self.speed_value)
        layout.addLayout(speed_row)

        size_row = QHBoxLayout()
        size_row.addWidget(QLabel("Pet size"))
        self.size_slider = QSlider(Qt.Orientation.Horizontal)
        self.size_slider.setRange(50, 300)
        self.size_slider.setSingleStep(10)
        self.size_slider.setPageStep(25)
        self.size_slider.setValue(round(pet_scale * 100))
        self.size_value = QLabel()
        self.size_value.setFixedWidth(48)
        self._set_size_label(self.size_slider.value())
        self.size_slider.valueChanged.connect(self._size_updated)
        size_row.addWidget(self.size_slider, 1)
        size_row.addWidget(self.size_value)
        layout.addLayout(size_row)

        self.follow_check = QCheckBox("Follow Cursor")
        self.follow_check.setChecked(follow_pointer)
        self.follow_check.toggled.connect(self.follow_changed.emit)
        layout.addWidget(self.follow_check)

        self.cycle_check = QCheckBox("Cycle animations automatically")
        self.cycle_check.setChecked(cycle_mode)
        self.cycle_check.toggled.connect(self.cycle_changed.emit)
        layout.addWidget(self.cycle_check)

        self.loop_check = QCheckBox("Loop")
        self.loop_check.setToolTip("Randomly play another action as soon as the current action ends")
        self.loop_check.setChecked(loop_mode)
        self.loop_check.toggled.connect(self.loop_changed.emit)
        layout.addWidget(self.loop_check)

        self.show_action_name_check = QCheckBox("Show action name")
        self.show_action_name_check.setChecked(show_action_name)
        self.show_action_name_check.toggled.connect(self.show_action_name_changed.emit)
        layout.addWidget(self.show_action_name_check)

        border_row = QHBoxLayout()
        self.border_check = QCheckBox("Pet outline (1px)")
        self.border_check.setChecked(border_enabled)
        self.border_check.toggled.connect(self._border_updated)
        self.color_button = QPushButton()
        self.color_button.clicked.connect(self.choose_color)
        self._update_color_button()
        border_row.addWidget(self.border_check)
        border_row.addStretch()
        border_row.addWidget(self.color_button)
        layout.addLayout(border_row)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.close)
        layout.addWidget(buttons)

    def _speed_updated(self, value: int) -> None:
        self._set_speed_label(value)
        self.speed_changed.emit(value)

    def _set_speed_label(self, value: int) -> None:
        self.speed_value.setText(f"{value / 100:.2g}×")

    def _size_updated(self, value: int) -> None:
        self._set_size_label(value)
        self.size_changed.emit(value)

    def _set_size_label(self, value: int) -> None:
        self.size_value.setText(f"{value}%")

    def choose_color(self) -> None:
        color = QColorDialog.getColor(self.border_color, self, "Choose pet outline color")
        if not color.isValid():
            return
        self.border_color = color
        was_enabled = self.border_check.isChecked()
        self.border_check.setChecked(True)
        self._update_color_button()
        if was_enabled:
            self._border_updated(True)

    def _update_color_button(self) -> None:
        self.color_button.setText(self.border_color.name())
        self.color_button.setStyleSheet(
            f"QPushButton {{ border: 1px solid #c8ccd1; border-radius: 8px; "
            f"background: {self.border_color.name()}; color: "
            f"{'#111111' if self.border_color.lightness() > 150 else '#ffffff'}; }}"
        )

    def _border_updated(self, enabled: bool) -> None:
        self.border_changed.emit(enabled, self.border_color.name())


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Pet Shelf")
        self.resize(1040, 720)
        self.setMinimumSize(QSize(760, 500))
        self.settings = QSettings("PetShelf", "PetShelf")
        self.root: Path | None = None
        self.pets: list[Pet] = []
        self.overlays: dict[str, PetOverlay] = {}
        saved_visible = self.settings.value("visiblePetIds", [])
        if isinstance(saved_visible, str):
            saved_visible = [saved_visible] if saved_visible else []
        self.saved_visible_ids = {str(value) for value in saved_visible}
        self.animation_speed = min(5.0, max(0.1, float(self.settings.value("animationSpeed", 1.0))))
        self.pet_scale = min(3.0, max(0.5, float(self.settings.value("petScale", 1.0))))
        self.border_enabled = self.settings.value("borderEnabled", False, type=bool)
        self.border_color = str(self.settings.value("borderColor", "#202124"))
        self.follow_pointer = self.settings.value("followPointer", True, type=bool)
        self.cycle_mode = self.settings.value("cycleMode", False, type=bool)
        self.loop_mode = self.settings.value("loopMode", False, type=bool)
        self.show_action_name = self.settings.value("showActionName", True, type=bool)
        self.settings_dialog: SettingsDialog | None = None
        self.update_thread: QThread | None = None
        self.update_worker: UpdateWorker | None = None
        self.pending_update: UpdateInfo | None = None

        central = QWidget()
        self.setCentralWidget(central)
        outer = QVBoxLayout(central)
        outer.setContentsMargins(34, 28, 34, 28)
        outer.setSpacing(18)

        header = QHBoxLayout()
        title = QLabel("Pets")
        title.setObjectName("pageTitle")
        header.addWidget(title)
        header.addStretch()
        self.folder_button = QPushButton("Open Pet Folder")
        self.folder_button.clicked.connect(self.choose_root)
        self.petdex_button = QPushButton("✦  PetDex")
        self.petdex_button.setObjectName("primaryButton")
        self.petdex_button.clicked.connect(self.open_petdex)
        self.refresh_button = QPushButton("↻  Refresh")
        self.refresh_button.clicked.connect(self.refresh)
        self.settings_button = QPushButton("⚙  Settings")
        self.settings_button.clicked.connect(self.open_settings)
        self.update_button = QPushButton("Check for Updates")
        self.update_button.clicked.connect(self.check_for_updates)
        header.addWidget(self.petdex_button)
        header.addWidget(self.folder_button)
        header.addWidget(self.refresh_button)
        header.addWidget(self.settings_button)
        header.addWidget(self.update_button)
        outer.addLayout(header)

        self.path_label = QLabel("Choose a parent folder containing pet subfolders.")
        self.path_label.setObjectName("pathLabel")
        self.path_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        outer.addWidget(self.path_label)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.list_widget = QWidget()
        self.list_layout = QVBoxLayout(self.list_widget)
        self.list_layout.setContentsMargins(0, 0, 0, 0)
        self.list_layout.setSpacing(0)
        self.scroll.setWidget(self.list_widget)
        outer.addWidget(self.scroll, 1)

        saved_root = self.settings.value("petRoot", "")
        if saved_root and Path(str(saved_root)).is_dir():
            self.root = Path(str(saved_root))
            self.refresh()
        else:
            self._render_empty("No pet folder selected yet. Open the gate, senpai ✨")

        self._tray_hint_shown = False
        self.tray_available = QSystemTrayIcon.isSystemTrayAvailable()
        self.tray_icon: QSystemTrayIcon | None = None
        if self.tray_available:
            self._setup_tray_icon()
        QTimer.singleShot(1800, lambda: self.check_for_updates(silent=True))

    def check_for_updates(self, silent: bool = False) -> None:
        if not silent and self.pending_update is not None:
            self._offer_update(self.pending_update)
            return
        if self.update_thread and self.update_thread.isRunning():
            return
        self.update_button.setEnabled(False)
        self.update_button.setText("Checking…")
        thread = QThread(self)
        worker = UpdateWorker()
        worker.moveToThread(thread)
        thread.started.connect(worker.check)
        worker.checked.connect(lambda info: self._update_checked(info, silent))
        worker.failed.connect(lambda message: self._update_failed(message, silent))
        worker.checked.connect(lambda _info: thread.quit())
        worker.failed.connect(lambda _message: thread.quit())
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(lambda: self._clear_update_worker(thread))
        self.update_thread = thread
        self.update_worker = worker
        thread.start()

    def _clear_update_worker(self, thread: QThread) -> None:
        if self.update_thread is thread:
            self.update_thread = None
            self.update_worker = None

    def _update_checked(self, info: UpdateInfo | None, silent: bool) -> None:
        self.update_button.setEnabled(True)
        if info is None:
            self.update_button.setText("Up to date")
            if not silent:
                QMessageBox.information(self, "Pet Shelf", "You are using the latest version.")
            QTimer.singleShot(2500, lambda: self.update_button.setText("Check for Updates"))
            return
        self.pending_update = info
        self.update_button.setText(f"Update {info.version}")
        self.update_button.setObjectName("primaryButton")
        self.update_button.style().unpolish(self.update_button)
        self.update_button.style().polish(self.update_button)
        self._offer_update(info)

    def _update_failed(self, message: str, silent: bool) -> None:
        self.update_button.setEnabled(True)
        self.update_button.setText("Check for Updates")
        if not silent:
            details = message or "No error details were returned. Check your internet connection and GitHub Release."
            QMessageBox.warning(self, "Update check failed", f"Could not check for updates.\n\n{details}")

    def _offer_update(self, info: UpdateInfo) -> None:
        notes = info.notes.strip() or "A newer version of Pet Shelf is available."
        answer = QMessageBox.question(
            self,
            f"Pet Shelf {info.version} is available",
            f"{notes}\n\nDownload and install it now?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if answer == QMessageBox.StandardButton.Yes:
            self._download_update(info)

    def _download_update(self, info: UpdateInfo) -> None:
        if self.update_thread and self.update_thread.isRunning():
            return
        progress = QMessageBox(self)
        progress.setWindowTitle("Updating Pet Shelf")
        progress.setText(f"Downloading {info.asset_name}…")
        progress.setStandardButtons(QMessageBox.StandardButton.NoButton)
        progress.show()
        thread = QThread(self)
        worker = UpdateWorker()
        worker.moveToThread(thread)
        thread.started.connect(lambda: worker.download(info))
        worker.progress.connect(lambda value: progress.setInformativeText(f"Downloaded {value}%"))
        worker.downloaded.connect(lambda path: self._install_download(path, progress, thread))
        worker.failed.connect(lambda message: self._download_failed(message, progress, thread))
        self.update_thread = thread
        self.update_worker = worker
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(lambda: self._clear_update_worker(thread))
        thread.start()

    def _install_download(self, path: str, progress: QMessageBox, thread: QThread) -> None:
        try:
            install_after_exit(path)
        except Exception as exc:
            progress.close()
            thread.quit()
            QMessageBox.warning(self, "Update failed", str(exc))
            return
        self.pending_update = None
        progress.setText("Update downloaded. Pet Shelf will restart now…")
        QTimer.singleShot(500, QApplication.instance().quit)
        thread.quit()

    def _download_failed(self, message: str, progress: QMessageBox, thread: QThread) -> None:
        progress.close()
        thread.quit()
        QMessageBox.warning(self, "Download failed", message)

    def _setup_tray_icon(self) -> None:
        icon = tray_icon_pixmap()
        self.setWindowIcon(icon)
        tray = QSystemTrayIcon(icon, self)
        tray.setToolTip("Pet Shelf")
        menu = QMenu()
        show_action = QAction("Show Pet Shelf", self)
        show_action.triggered.connect(self._restore_from_tray)
        quit_action = QAction("Quit Pet Shelf", self)
        quit_action.triggered.connect(self._quit_app)
        menu.addAction(show_action)
        menu.addSeparator()
        menu.addAction(quit_action)
        tray.setContextMenu(menu)
        tray.activated.connect(self._tray_activated)
        tray.show()
        self.tray_icon = tray

    def _tray_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason in (
            QSystemTrayIcon.ActivationReason.Trigger,
            QSystemTrayIcon.ActivationReason.DoubleClick,
        ):
            self._restore_from_tray()

    def _restore_from_tray(self) -> None:
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def _quit_app(self) -> None:
        if self.tray_icon:
            self.tray_icon.hide()
        for overlay in list(self.overlays.values()):
            overlay.blockSignals(True)
            overlay.close()
        QApplication.instance().quit()

    def choose_root(self) -> None:
        start = str(self.root) if self.root else str(Path.home())
        chosen = QFileDialog.getExistingDirectory(self, "Choose parent pet folder", start)
        if not chosen:
            return
        self.root = Path(chosen)
        self.settings.setValue("petRoot", chosen)
        self.refresh()

    def open_petdex(self) -> None:
        dialog = PetDexDialog(self._installed_petdex_slugs(), self)
        dialog.installed.connect(self._petdex_installed)
        dialog.exec()

    def _installed_petdex_slugs(self) -> set[str]:
        roots = {self.root} if self.root else {Path.home() / ".codex" / "pets"}
        installed: set[str] = set()
        for root in roots:
            if not root.is_dir():
                continue
            installed.update(
                folder.name
                for folder in root.iterdir()
                if folder.is_dir() and (folder / "pet.json").is_file()
            )
        return installed

    def _petdex_installed(self, slug: str) -> None:
        standard_root = Path.home() / ".codex" / "pets"
        source = standard_root / slug
        if not (source / "pet.json").is_file():
            QMessageBox.warning(self, "PetDex sync failed", f"Installed pet folder was not found: {source}")
            return
        if self.root is None:
            self.root = standard_root
            self.settings.setValue("petRoot", str(standard_root))
        elif self.root.resolve() != standard_root.resolve():
            destination = self.root / slug
            if not destination.exists():
                try:
                    shutil.copytree(source, destination)
                except OSError as exc:
                    QMessageBox.warning(
                        self,
                        "PetDex sync failed",
                        f"PetDex installed the pet, but Pet Shelf could not copy it into the selected folder.\n\n{exc}",
                    )
                    return
        self.refresh()

    def change_animation_speed(self, value: int) -> None:
        self.animation_speed = value / 100
        self.settings.setValue("animationSpeed", self.animation_speed)
        for overlay in self.overlays.values():
            overlay.set_animation_speed(self.animation_speed)

    def change_pet_size(self, value: int) -> None:
        self.pet_scale = value / 100
        self.settings.setValue("petScale", self.pet_scale)
        for overlay in self.overlays.values():
            overlay.set_display_scale(self.pet_scale)

    def open_settings(self) -> None:
        if self.settings_dialog is None:
            dialog = SettingsDialog(
                self.animation_speed,
                self.pet_scale,
                self.border_enabled,
                self.border_color,
                self.follow_pointer,
                self.cycle_mode,
                self.loop_mode,
                self.show_action_name,
                self,
            )
            dialog.speed_changed.connect(self.change_animation_speed)
            dialog.size_changed.connect(self.change_pet_size)
            dialog.border_changed.connect(self.apply_border)
            dialog.follow_changed.connect(self.toggle_follow_pointer)
            dialog.cycle_changed.connect(self.toggle_cycle_mode)
            dialog.loop_changed.connect(self.toggle_loop_mode)
            dialog.show_action_name_changed.connect(self.toggle_show_action_name)
            dialog.finished.connect(lambda: setattr(self, "settings_dialog", None))
            self.settings_dialog = dialog
        self.settings_dialog.show()
        self.settings_dialog.raise_()
        self.settings_dialog.activateWindow()

    def apply_border(self, enabled: bool, color: str) -> None:
        self.border_enabled = enabled
        self.border_color = color
        self.settings.setValue("borderEnabled", enabled)
        self.settings.setValue("borderColor", color)
        for overlay in self.overlays.values():
            overlay.set_border(enabled, color)

    def toggle_follow_pointer(self, enabled: bool) -> None:
        self.follow_pointer = enabled
        self.settings.setValue("followPointer", enabled)
        for overlay in self.overlays.values():
            overlay.set_follow_pointer(enabled)

    def toggle_cycle_mode(self, enabled: bool) -> None:
        self.cycle_mode = enabled
        self.settings.setValue("cycleMode", enabled)
        for overlay in self.overlays.values():
            overlay.set_cycle_mode(enabled)

    def toggle_loop_mode(self, enabled: bool) -> None:
        self.loop_mode = enabled
        self.settings.setValue("loopMode", enabled)
        for overlay in self.overlays.values():
            overlay.set_loop_mode(enabled)

    def toggle_show_action_name(self, enabled: bool) -> None:
        self.show_action_name = enabled
        self.settings.setValue("showActionName", enabled)
        for overlay in self.overlays.values():
            overlay.set_show_action_name(enabled)

    def refresh(self) -> None:
        if not self.root:
            self.choose_root()
            return
        try:
            pets, issues = scan_pet_root(self.root)
        except PetLoadError as exc:
            QMessageBox.critical(self, "Cannot read pet folder", str(exc))
            return
        self.pets = pets
        self.path_label.setText(str(self.root))
        pet_by_id = {pet.pet_id: pet for pet in pets}
        desired_ids = self.saved_visible_ids | set(self.overlays)
        for pet_id in list(self.overlays):
            if pet_id not in pet_by_id:
                overlay = self.overlays.pop(pet_id)
                overlay.close()
        for pet_id in desired_ids:
            pet = pet_by_id.get(pet_id)
            if pet:
                if pet_id in self.overlays:
                    self.overlays[pet_id].set_pet(pet)
                else:
                    self.show_pet(pet_id, render=False)
        self._render_list()
        if issues:
            details = "\n".join(f"• {issue.folder_name}: {issue.message}" for issue in issues)
            QMessageBox.warning(self, "Some pets could not be loaded", details)

    def _clear_list(self) -> None:
        while self.list_layout.count():
            item = self.list_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

    def _render_empty(self, text: str) -> None:
        self._clear_list()
        label = QLabel(text)
        label.setObjectName("emptyLabel")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.list_layout.addWidget(label, 1)

    def _render_list(self) -> None:
        self._clear_list()
        if not self.pets:
            self._render_empty("No valid pets found. Expected: pet-name/pet.json + spritesheet.webp")
            return
        for pet in self.pets:
            row = PetRow(pet, pet.pet_id in self.overlays)
            row.toggle_requested.connect(self.toggle_pet)
            row.edit_requested.connect(self.edit_pet)
            self.list_layout.addWidget(row)
        self.list_layout.addStretch()

    def show_pet(self, pet_id: str, render: bool = True) -> None:
        pet = next((item for item in self.pets if item.pet_id == pet_id), None)
        if not pet or pet_id in self.overlays:
            return
        overlay = PetOverlay()
        overlay.set_animation_speed(self.animation_speed)
        overlay.set_display_scale(self.pet_scale)
        overlay.set_border(self.border_enabled, self.border_color)
        overlay.set_follow_pointer(self.follow_pointer)
        overlay.set_cycle_mode(self.cycle_mode)
        overlay.set_loop_mode(self.loop_mode)
        overlay.set_show_action_name(self.show_action_name)
        overlay.set_pet(pet)
        overlay.hidden_by_user.connect(self._overlay_hidden)
        slot = len(self.overlays)
        screen = QApplication.primaryScreen().availableGeometry()
        column = slot % 5
        row = slot // 5
        overlay.move(
            screen.right() - overlay.width() - 24 - column * (overlay.width() + 8),
            screen.bottom() - overlay.height() - 24 - row * (overlay.height() + 8),
        )
        self.overlays[pet_id] = overlay
        overlay.show_pet()
        self._save_visible_ids()
        if render:
            self._render_list()

    def edit_pet(self, pet_id: str) -> None:
        pet = next((item for item in self.pets if item.pet_id == pet_id), None)
        if not pet:
            return
        editor = SpriteEditorDialog(pet, self)
        editor.saved.connect(lambda _saved_id: self.refresh())
        editor.exec()

    def toggle_pet(self, pet_id: str) -> None:
        if pet_id in self.overlays:
            self.overlays[pet_id].hide_pet()
        else:
            self.show_pet(pet_id)

    def _overlay_hidden(self, pet_id: str) -> None:
        overlay = self.overlays.pop(pet_id, None)
        if overlay:
            overlay.deleteLater()
        self.saved_visible_ids.discard(pet_id)
        self._save_visible_ids()
        self._render_list()

    def _save_visible_ids(self) -> None:
        visible_ids = sorted(self.overlays)
        self.saved_visible_ids = set(visible_ids)
        self.settings.setValue("visiblePetIds", visible_ids)

    def changeEvent(self, event) -> None:
        super().changeEvent(event)
        if event.type() == QEvent.Type.WindowStateChange and self.isMinimized():
            # Some window managers minimize/hide application Tool windows with
            # their main window. Restore only the pet overlays next event-loop
            # turn, while leaving the Pet Shelf manager minimized.
            QTimer.singleShot(0, self._keep_pets_visible)

    def _keep_pets_visible(self) -> None:
        for overlay in self.overlays.values():
            overlay.keep_visible()

    def closeEvent(self, event: QCloseEvent) -> None:
        if not self.tray_available:
            for overlay in list(self.overlays.values()):
                overlay.blockSignals(True)
                overlay.close()
            super().closeEvent(event)
            return
        event.ignore()
        self.hide()
        if not self._tray_hint_shown and self.tray_icon:
            self.tray_icon.showMessage(
                "Pet Shelf",
                "Pet Shelf vẫn chạy dưới khay hệ thống. Bấm vào icon để mở lại giao diện.",
                QSystemTrayIcon.MessageIcon.Information,
                3000,
            )
            self._tray_hint_shown = True


STYLE = """
QWidget { background: #ffffff; color: #202124; font-family: Arial, sans-serif; font-size: 15px; }
QLabel#pageTitle { font-size: 32px; font-weight: 600; }
QLabel#settingsTitle { font-size: 22px; font-weight: 600; }
QLabel#spritePreview { background: #f5f6f8; border: 1px solid #e1e3e6; border-radius: 8px; }
QLabel#pathLabel { color: #74777d; font-size: 13px; padding-left: 4px; }
QLabel#petTitle { font-size: 18px; font-weight: 600; }
QLabel#petDescription { color: #666a70; font-size: 14px; }
QLabel#emptyLabel { color: #7a7d82; font-size: 17px; border: 1px dashed #d8dade; border-radius: 16px; }
QPushButton { background: #f2f3f5; border: none; border-radius: 12px; padding: 9px 16px; }
QPushButton:hover { background: #e7e9ec; }
QPushButton:checked { background: #dcecff; color: #1269b0; }
QPushButton:disabled { color: #a8abb0; background: #f6f6f7; }
QPushButton#primaryButton { background: #3099f5; color: white; }
QPushButton#primaryButton:hover { background: #1789ed; }
QFrame#petRow { border-bottom: 1px solid #eceef0; }
QFrame#petdexRow { border-bottom: 1px solid #eceef0; }
QLabel#petdexPreview { background: #f5f6f8; border: 1px solid #e1e3e6; border-radius: 10px; }
QLabel#petdexMeta { color: #8a8d93; font-size: 12px; }
QLineEdit { background: #f5f6f8; border: 1px solid #dfe2e6; border-radius: 12px; padding: 10px 13px; }
QLineEdit:focus { border-color: #3099f5; background: #ffffff; }
QProgressBar { border: none; border-radius: 6px; background: #e8ebef; text-align: center; min-height: 12px; }
QProgressBar::chunk { border-radius: 6px; background: #3099f5; }
QScrollArea { border: 1px solid #e1e3e6; border-radius: 18px; }
QScrollBar:vertical { width: 10px; background: transparent; }
QScrollBar::handle:vertical { background: #cfd2d6; border-radius: 5px; min-height: 36px; }
QSlider::groove:horizontal { height: 6px; background: #dfe3e8; border-radius: 3px; }
QSlider::sub-page:horizontal { background: #3099f5; border-radius: 3px; }
QSlider::handle:horizontal { background: #3099f5; width: 18px; margin: -6px 0; border-radius: 9px; }
QSlider::handle:horizontal:hover { background: #1789ed; }
"""
