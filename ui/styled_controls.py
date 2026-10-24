"""沿用 Qt 的原生交互，统一选择框和数字框的箭头绘制。"""

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QPainter, QPainterPath, QPalette, QPen
from PyQt5.QtWidgets import (
    QAbstractSpinBox, QComboBox, QFrame, QLineEdit, QListView, QSpinBox, QStyle,
    QStyleOptionComboBox, QStyleOptionSpinBox,
)


class ThemedComboBox(QComboBox):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setCursor(Qt.PointingHandCursor)
        self.setMaxVisibleItems(8)
        view = QListView()
        view.setFrameShape(QFrame.NoFrame)
        view.setUniformItemSizes(True)
        view.setMouseTracking(True)
        view.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setView(view)
        view.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        popup = view.parentWidget()
        if isinstance(popup, QFrame):
            popup.setObjectName("comboPopup")
            popup.setFrameShape(QFrame.NoFrame)

    def paintEvent(self, event):
        super().paintEvent(event)
        option = QStyleOptionComboBox()
        self.initStyleOption(option)
        arrow = self.style().subControlRect(
            QStyle.CC_ComboBox, option, QStyle.SC_ComboBoxArrow, self)
        center = arrow.center()
        group = QPalette.Active if self.isEnabled() else QPalette.Disabled
        color = self.palette().color(group, QPalette.ButtonText)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(QPen(color, 1.6, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        direction = -1 if self.view().isVisible() else 1
        path = QPainterPath()
        path.moveTo(center.x() - 4, center.y() - 2 * direction)
        path.lineTo(center.x(), center.y() + 2 * direction)
        path.lineTo(center.x() + 4, center.y() - 2 * direction)
        painter.drawPath(path)

    def showPopup(self):
        # 样式重新应用后 Qt 可能重设此策略，展开前恢复可滚动列表。
        self.view().setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        super().showPopup()
        self.update()

    def hidePopup(self):
        super().hidePopup()
        self.update()


class _SelectAllLineEdit(QLineEdit):
    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        if event.button() == Qt.LeftButton and self.rect().contains(event.pos()):
            self.selectAll()


class ThemedSpinBox(QSpinBox):
    """明确绘制增减箭头，避免样式表下平台原生箭头消失或对比度不足。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setLineEdit(_SelectAllLineEdit(self))
        self.setObjectName("stepperSpinBox")
        self.setButtonSymbols(QAbstractSpinBox.UpDownArrows)
        self.setMinimumHeight(32)
        self.setMouseTracking(True)
        self.setCursor(Qt.IBeamCursor)
        self._editing_area_pressed = False

    def _is_editing_area(self, position):
        option = QStyleOptionSpinBox()
        self.initStyleOption(option)
        return self.rect().contains(position) and not any(
            self.style().subControlRect(QStyle.CC_SpinBox, option, control, self).contains(position)
            for control in (QStyle.SC_SpinBoxUp, QStyle.SC_SpinBoxDown)
        )

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and self._is_editing_area(event.pos()):
            self._editing_area_pressed = True
            self.lineEdit().setFocus(Qt.MouseFocusReason)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self._editing_area_pressed:
            self._editing_area_pressed = False
            if self._is_editing_area(event.pos()):
                self.selectAll()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def mouseMoveEvent(self, event):
        self.setCursor(Qt.IBeamCursor if self._is_editing_area(event.pos()) else Qt.ArrowCursor)
        super().mouseMoveEvent(event)

    def paintEvent(self, event):
        super().paintEvent(event)
        option = QStyleOptionSpinBox()
        self.initStyleOption(option)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        for control, step, direction in (
            (QStyle.SC_SpinBoxUp, QAbstractSpinBox.StepUpEnabled, -1),
            (QStyle.SC_SpinBoxDown, QAbstractSpinBox.StepDownEnabled, 1),
        ):
            rect = self.style().subControlRect(QStyle.CC_SpinBox, option, control, self)
            if rect.isEmpty():
                continue
            color = option.palette.color(QPalette.Text)
            if not self.isEnabled() or not (self.stepEnabled() & step):
                color.setAlpha(85)
            painter.setPen(QPen(color, 1.6, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
            center = rect.center()
            path = QPainterPath()
            path.moveTo(center.x() - 3, center.y() - 1.5 * direction)
            path.lineTo(center.x(), center.y() + 1.5 * direction)
            path.lineTo(center.x() + 3, center.y() - 1.5 * direction)
            painter.drawPath(path)
