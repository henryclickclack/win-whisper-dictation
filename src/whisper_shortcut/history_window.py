from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

from PySide6.QtCore import QEvent, Qt, Slot
from PySide6.QtGui import QCursor, QGuiApplication, QKeyEvent
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .history import TranscriptHistory

STYLE = """
QFrame#panel {
    background-color: #111114;
    border: 1px solid rgba(255, 255, 255, 0.14);
    border-radius: 12px;
}
QLabel {
    font-family: "Segoe UI";
    background: transparent;
}
QLabel#title {
    color: #f4f4f5;
    font-size: 14px;
    font-weight: 600;
}
QLabel#hint, QLabel#empty {
    color: #8b8b94;
    font-size: 12px;
}
QListWidget {
    background: transparent;
    border: none;
    outline: none;
    color: #e4e4e7;
    font-family: "Segoe UI";
    font-size: 13px;
}
QListWidget::item {
    background-color: rgba(255, 255, 255, 0.05);
    border-radius: 8px;
    padding: 8px 10px;
    margin-bottom: 6px;
}
QListWidget::item:hover, QListWidget::item:selected {
    background-color: rgba(255, 255, 255, 0.12);
    color: #ffffff;
}
QScrollBar:vertical {
    background: transparent;
    width: 8px;
}
QScrollBar::handle:vertical {
    background: rgba(255, 255, 255, 0.2);
    border-radius: 4px;
    min-height: 24px;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0;
}
"""

PREVIEW_LENGTH = 220


def _format_time(timestamp: float) -> str:
    moment = datetime.fromtimestamp(timestamp)
    if moment.date() == datetime.now().date():
        return moment.strftime("%H:%M")
    return moment.strftime("%d %b, %H:%M")


class HistoryWindow(QWidget):
    """A small popup listing recent transcripts; click one to copy it."""

    def __init__(
        self,
        history: TranscriptHistory,
        on_copy: Callable[[str], None],
    ) -> None:
        super().__init__()
        self._history = history
        self._on_copy = on_copy
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(460, 440)
        self.setStyleSheet(STYLE)

        panel = QFrame()
        panel.setObjectName("panel")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(panel)

        title = QLabel("Recent transcripts")
        title.setObjectName("title")
        hint = QLabel("Click to copy  ·  Esc to close")
        hint.setObjectName("hint")
        header = QHBoxLayout()
        header.addWidget(title)
        header.addStretch()
        header.addWidget(hint)

        self._list = QListWidget()
        self._list.setWordWrap(True)
        self._list.setVerticalScrollMode(QListWidget.ScrollMode.ScrollPerPixel)
        self._list.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self._list.setCursor(Qt.CursorShape.PointingHandCursor)
        self._list.itemClicked.connect(self._copy)
        self._list.itemActivated.connect(self._copy)

        self._empty = QLabel("No transcripts yet.")
        self._empty.setObjectName("empty")
        self._empty.setAlignment(Qt.AlignmentFlag.AlignCenter)

        layout = QVBoxLayout(panel)
        layout.setContentsMargins(14, 12, 14, 10)
        layout.setSpacing(10)
        layout.addLayout(header)
        layout.addWidget(self._list, 1)
        layout.addWidget(self._empty, 1)

    def _refresh(self) -> None:
        self._list.clear()
        entries = self._history.entries()
        for entry in entries:
            preview = " ".join(entry.text.split())
            if len(preview) > PREVIEW_LENGTH:
                preview = preview[:PREVIEW_LENGTH].rstrip() + "…"
            words = len(entry.text.split())
            item = QListWidgetItem(
                f"{_format_time(entry.timestamp)}  ·  {words} words\n{preview}"
            )
            item.setData(Qt.ItemDataRole.UserRole, entry.text)
            item.setToolTip(entry.text)
            self._list.addItem(item)
        self._list.setVisible(bool(entries))
        self._empty.setVisible(not entries)
        if entries:
            self._list.setCurrentRow(0)

    def _position(self) -> None:
        screen = QGuiApplication.screenAt(QCursor.pos())
        if screen is None:
            screen = QGuiApplication.primaryScreen()
        if screen is None:
            return
        bounds = screen.availableGeometry()
        self.move(
            bounds.left() + (bounds.width() - self.width()) // 2,
            bounds.top() + (bounds.height() - self.height()) // 2,
        )

    @Slot()
    def toggle(self) -> None:
        if self.isVisible():
            self.hide()
            return
        self._refresh()
        self._position()
        self.show()
        self.raise_()
        self.activateWindow()
        self._list.setFocus()

    def _copy(self, item: QListWidgetItem) -> None:
        if not self.isVisible():
            return
        self.hide()
        self._on_copy(str(item.data(Qt.ItemDataRole.UserRole)))

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self.hide()
            return
        super().keyPressEvent(event)

    def event(self, event: QEvent) -> bool:
        if event.type() == QEvent.Type.WindowDeactivate:
            self.hide()
        return super().event(event)
