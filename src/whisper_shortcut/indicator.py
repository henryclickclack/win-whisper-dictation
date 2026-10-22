from __future__ import annotations

import math
import time
from collections import deque
from collections.abc import Callable

from PySide6.QtCore import QObject, QPointF, QRectF, Qt, QTimer, Signal, Slot
from PySide6.QtGui import (
    QColor,
    QFont,
    QFontMetrics,
    QGuiApplication,
    QPainter,
    QPaintEvent,
    QPen,
)
from PySide6.QtWidgets import QWidget

from .config import IndicatorConfig
from .states import AppState


class IndicatorBridge(QObject):
    state_changed = Signal(object, str)
    quit_requested = Signal()
    history_requested = Signal()

    def publish(self, state: AppState, message: str = "") -> None:
        self.state_changed.emit(state, message)

    def request_quit(self) -> None:
        self.quit_requested.emit()

    def request_history(self) -> None:
        self.history_requested.emit()


class FloatingIndicator(QWidget):
    ACCENTS = {
        AppState.RECORDING: "#f87171",
        AppState.TRANSCRIBING: "#fbbf24",
        AppState.INSERTED: "#4ade80",
        AppState.ERROR: "#f87171",
        AppState.NOTICE: "#60a5fa",
    }

    LABELS = {
        AppState.RECORDING: "Recording",
        AppState.TRANSCRIBING: "Transcribing",
        AppState.INSERTED: "Inserted",
        AppState.ERROR: "Error",
        AppState.NOTICE: "",
    }

    PADDING = 14
    GAP = 10
    GLYPH = 10
    BAR_WIDTH = 3
    BAR_GAP = 2
    BUSY_BARS = 7
    MAX_WIDTH = 460

    def __init__(
        self,
        config: IndicatorConfig,
        on_timeout: object | None = None,
        level_source: Callable[[], float] | None = None,
        mode_source: Callable[[], str] | None = None,
    ) -> None:
        super().__init__()
        self._config = config
        self._on_timeout = on_timeout
        self._level_source = level_source
        self._mode_source = mode_source
        self._state = AppState.IDLE
        self._text = ""
        self._mode = ""
        self._started = 0.0
        self._levels: deque[float] = deque(maxlen=128)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowDoesNotAcceptFocus
        )
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(config.width, config.height)

        self._font = QFont("Segoe UI")
        self._font.setPixelSize(13)
        self._font.setWeight(QFont.Weight.DemiBold)
        self._small_font = QFont("Segoe UI")
        self._small_font.setPixelSize(10)
        self._small_font.setWeight(QFont.Weight.Bold)
        self._small_font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 0.8)

        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self._timeout)

        self._frame_timer = QTimer(self)
        self._frame_timer.setInterval(33)
        self._frame_timer.timeout.connect(self._tick)

    def _position(self) -> None:
        screen = QGuiApplication.primaryScreen()
        if screen is None:
            return
        bounds = screen.availableGeometry()
        if self._config.anchor == "top-left":
            x = bounds.left()
        elif self._config.anchor == "top-right":
            x = bounds.right() - self.width() + 1
        else:
            x = bounds.left() + (bounds.width() - self.width()) // 2
        self.move(
            x + self._config.x_offset,
            bounds.top() + self._config.y_offset,
        )

    def _busy_bars_width(self) -> int:
        return self.BUSY_BARS * (self.BAR_WIDTH + self.BAR_GAP) - self.BAR_GAP

    def _width_for_state(self) -> int:
        if self._state == AppState.RECORDING:
            return self._config.width
        text_width = QFontMetrics(self._font).horizontalAdvance(self._text)
        if self._state == AppState.TRANSCRIBING:
            lead = self._busy_bars_width()
            tail = QFontMetrics(self._small_font).horizontalAdvance(self._mode)
            tail += self.GAP + 4 if self._mode else 0
        else:
            lead = self.GLYPH
            tail = 0
        needed = self.PADDING * 2 + lead + self.GAP + text_width + tail + 4
        return min(self.MAX_WIDTH, max(self._config.width, needed))

    @Slot(object, str)
    def set_state(self, state: AppState, message: str = "") -> None:
        self._hide_timer.stop()
        self._state = state
        if state == AppState.IDLE:
            self._frame_timer.stop()
            self.hide()
            return

        self._text = message or self.LABELS[state]
        self._mode = self._mode_source() if self._mode_source else ""
        if state == AppState.RECORDING:
            self._levels.clear()
            self._started = time.monotonic()

        if state in {AppState.RECORDING, AppState.TRANSCRIBING}:
            self._frame_timer.start()
        else:
            self._frame_timer.stop()

        self.setFixedSize(self._width_for_state(), self._config.height)
        self._position()
        self.show()
        self.raise_()
        self.update()

        if state in {AppState.INSERTED, AppState.NOTICE}:
            self._hide_timer.start(1_400)
        elif state == AppState.ERROR:
            self._hide_timer.start(4_000)

    def _tick(self) -> None:
        if self._state == AppState.RECORDING and self._level_source is not None:
            self._levels.append(max(0.0, min(1.0, self._level_source())))
        self.update()

    def _timeout(self) -> None:
        self.hide()
        if callable(self._on_timeout):
            self._on_timeout()

    def paintEvent(self, _event: QPaintEvent) -> None:
        if self._state == AppState.IDLE:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        body = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        radius = min(body.height() / 2, 16.0)
        painter.setPen(QPen(QColor(255, 255, 255, 40), 1))
        painter.setBrush(QColor(17, 17, 20, 240))
        painter.drawRoundedRect(body, radius, radius)

        accent = QColor(self.ACCENTS[self._state])
        content = body.adjusted(self.PADDING, 0, -self.PADDING, 0)
        if self._state == AppState.RECORDING:
            self._paint_recording(painter, content, accent)
        elif self._state == AppState.TRANSCRIBING:
            self._paint_transcribing(painter, content, accent)
        else:
            self._paint_message(painter, content, accent)
        painter.end()

    def _paint_bar(
        self, painter: QPainter, x: float, middle: float, height: float
    ) -> None:
        painter.drawRoundedRect(
            QRectF(x, middle - height / 2, self.BAR_WIDTH, height),
            self.BAR_WIDTH / 2,
            self.BAR_WIDTH / 2,
        )

    def _paint_recording(
        self, painter: QPainter, content: QRectF, accent: QColor
    ) -> None:
        middle = content.center().y()
        now = time.monotonic()

        pulse = 0.5 + 0.5 * math.sin(now * 4.0)
        dot = QColor(accent)
        dot.setAlphaF(0.55 + 0.45 * pulse)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(dot)
        painter.drawEllipse(QPointF(content.left() + 5, middle), 4.5, 4.5)

        elapsed = int(now - self._started)
        timer = f"{elapsed // 60}:{elapsed % 60:02d}"
        painter.setFont(self._font)
        timer_width = QFontMetrics(self._font).horizontalAdvance("0:00")
        timer_width = max(
            timer_width, QFontMetrics(self._font).horizontalAdvance(timer)
        )
        painter.setPen(QColor("#d4d4d8"))
        painter.drawText(
            QRectF(content.right() - timer_width, content.top(), timer_width,
                   content.height()),
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight,
            timer,
        )

        # Scrolling level meter: the newest sample is drawn at the right edge.
        left = content.left() + self.GLYPH + self.GAP
        right = content.right() - timer_width - self.GAP
        step = self.BAR_WIDTH + self.BAR_GAP
        count = max(0, int((right - left + self.BAR_GAP) // step))
        max_height = content.height() - 16
        levels = list(self._levels)[-count:] if count else []
        offset = count - len(levels)
        painter.setPen(Qt.PenStyle.NoPen)
        for index in range(count):
            x = right - (count - index) * step + self.BAR_GAP
            if index < offset:
                painter.setBrush(QColor(255, 255, 255, 40))
                self._paint_bar(painter, x, middle, 3)
                continue
            level = levels[index - offset]
            painter.setBrush(QColor(244, 244, 245, int(110 + 145 * level)))
            self._paint_bar(painter, x, middle, max(3.0, level * max_height))

    def _paint_transcribing(
        self, painter: QPainter, content: QRectF, accent: QColor
    ) -> None:
        middle = content.center().y()
        now = time.monotonic()
        step = self.BAR_WIDTH + self.BAR_GAP
        max_height = content.height() - 20
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(accent)
        for index in range(self.BUSY_BARS):
            wave = abs(math.sin(now * 4.5 - index * 0.55))
            self._paint_bar(
                painter,
                content.left() + index * step,
                middle,
                4 + wave * (max_height - 4),
            )

        text_left = content.left() + self._busy_bars_width() + self.GAP
        tag_width = 0
        if self._mode:
            painter.setFont(self._small_font)
            tag_width = QFontMetrics(self._small_font).horizontalAdvance(self._mode)
            painter.setPen(QColor("#8b8b94"))
            painter.drawText(
                QRectF(content.right() - tag_width - 4, content.top(),
                       tag_width + 4, content.height()),
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight,
                self._mode,
            )
            tag_width += self.GAP
        self._paint_text(
            painter, text_left, content.right() - tag_width, content
        )

    def _paint_message(
        self, painter: QPainter, content: QRectF, accent: QColor
    ) -> None:
        middle = content.center().y()
        center = QPointF(content.left() + 5, middle)
        if self._state == AppState.INSERTED:
            pen = QPen(accent, 2)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            painter.setPen(pen)
            painter.drawPolyline(
                [
                    QPointF(center.x() - 5, middle),
                    QPointF(center.x() - 1.5, middle + 3.5),
                    QPointF(center.x() + 5, middle - 4),
                ]
            )
        elif self._state == AppState.ERROR:
            pen = QPen(accent, 2)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(pen)
            painter.drawLine(
                QPointF(center.x(), middle - 5), QPointF(center.x(), middle + 1)
            )
            painter.drawPoint(QPointF(center.x(), middle + 5))
        else:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(accent)
            painter.drawEllipse(center, 4, 4)
        self._paint_text(
            painter,
            content.left() + self.GLYPH + self.GAP,
            content.right(),
            content,
        )

    def _paint_text(
        self, painter: QPainter, left: float, right: float, content: QRectF
    ) -> None:
        painter.setFont(self._font)
        painter.setPen(QColor("#f4f4f5"))
        text = QFontMetrics(self._font).elidedText(
            self._text, Qt.TextElideMode.ElideRight, int(right - left)
        )
        painter.drawText(
            QRectF(left, content.top(), right - left, content.height()),
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
            text,
        )
