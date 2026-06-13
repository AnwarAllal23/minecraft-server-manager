from __future__ import annotations

from typing import List, Optional

from PySide6.QtCore import QPointF, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QWidget


class MetricChart(QWidget):
    def __init__(self, title: str, color: str, suffix: str = "") -> None:
        super().__init__()
        self.title = title
        self.color = QColor(color)
        self.suffix = suffix
        self.values: List[float] = []
        self.max_value: Optional[float] = None
        self.setMinimumHeight(150)

    def sizeHint(self) -> QSize:
        return QSize(360, 170)

    def push(self, value: float, max_value: Optional[float] = None) -> None:
        self.values.append(max(0.0, float(value)))
        self.values = self.values[-72:]
        self.max_value = max_value
        self.update()

    def paintEvent(self, event) -> None:  # type: ignore[override]
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        rect = QRectF(self.rect()).adjusted(1, 1, -1, -1)

        painter.setPen(QPen(QColor("#d7dbe2"), 1))
        painter.setBrush(QColor("#ffffff"))
        painter.drawRoundedRect(rect, 8, 8)

        inner = rect.adjusted(18, 34, -16, -24)
        painter.setPen(QColor("#2b2f36"))
        title_font = QFont()
        title_font.setPointSize(13)
        title_font.setWeight(QFont.DemiBold)
        painter.setFont(title_font)
        painter.drawText(rect.adjusted(16, 10, -16, -10), Qt.AlignTop | Qt.AlignLeft, self.title)

        latest = self.values[-1] if self.values else 0.0
        painter.setPen(QColor("#6b7280"))
        painter.drawText(rect.adjusted(16, 10, -16, -10), Qt.AlignTop | Qt.AlignRight, f"{latest:.1f}{self.suffix}")

        painter.setPen(QPen(QColor("#eef0f4"), 1))
        for index in range(4):
            y = inner.top() + inner.height() * index / 3
            painter.drawLine(QPointF(inner.left(), y), QPointF(inner.right(), y))

        if len(self.values) < 2:
            painter.setPen(QColor("#9ca3af"))
            painter.drawText(inner, Qt.AlignCenter, "En attente de données")
            return

        scale = self.max_value or max(max(self.values) * 1.2, 1.0)
        points = []
        for index, value in enumerate(self.values):
            x = inner.left() + inner.width() * index / max(len(self.values) - 1, 1)
            y = inner.bottom() - inner.height() * min(value / scale, 1.0)
            points.append(QPointF(x, y))

        path = QPainterPath(points[0])
        for point in points[1:]:
            path.lineTo(point)

        fill_path = QPainterPath(path)
        fill_path.lineTo(points[-1].x(), inner.bottom())
        fill_path.lineTo(points[0].x(), inner.bottom())
        fill_path.closeSubpath()

        gradient = QLinearGradient(0, inner.top(), 0, inner.bottom())
        fill_color = QColor(self.color)
        fill_color.setAlpha(55)
        transparent = QColor(self.color)
        transparent.setAlpha(4)
        gradient.setColorAt(0, fill_color)
        gradient.setColorAt(1, transparent)
        painter.fillPath(fill_path, gradient)

        pen = QPen(self.color, 2.4)
        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)
        painter.setPen(pen)
        painter.drawPath(path)
