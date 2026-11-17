"""掩膜叠加快捷键：按住临时反转或按次切换，限定在所属标注窗口内。"""

from PyQt5.QtCore import QEvent, QObject, Qt, QTimer
from PyQt5.QtGui import QKeySequence
from PyQt5.QtWidgets import (
    QApplication, QAbstractSpinBox, QComboBox, QKeySequenceEdit,
    QLineEdit, QPlainTextEdit, QTextEdit, QWidget,
)
from ui.shortcuts import DEFAULT_SHORTCUTS, sequence_error, shortcut_errors


OVERLAY_SHORTCUT_MODES = (("hold", "长按模式"), ("toggle", "点击模式"))
DEFAULT_OVERLAY_SHORTCUT = "C"
DEFAULT_OVERLAY_SHORTCUT_MODE = "hold"
_MODIFIER_MASK = int(Qt.KeyboardModifierMask)
_MODIFIER_KEYS = {
    Qt.Key_Control: Qt.ControlModifier, Qt.Key_Shift: Qt.ShiftModifier,
    Qt.Key_Alt: Qt.AltModifier, Qt.Key_Meta: Qt.MetaModifier,
}


def shortcut_error(sequence: QKeySequence, bindings=None) -> str:
    error = sequence_error(sequence)
    if error:
        return error
    candidate = dict(DEFAULT_SHORTCUTS if bindings is None else bindings)
    candidate["overlay"] = sequence.toString(QKeySequence.PortableText)
    return shortcut_errors(candidate).get("overlay", "")


class OverlayShortcutController(QObject):
    def __init__(self, window, mode, shortcut):
        super().__init__(window)
        self.window = window
        self._pressed = False
        self._restore_visible = None
        self.configure(mode, shortcut)
        QApplication.instance().installEventFilter(self)

    def configure(self, mode, shortcut):
        self.restore()
        self.mode = mode
        chord = int(QKeySequence(shortcut, QKeySequence.PortableText)[0])
        self.key = chord & ~_MODIFIER_MASK
        self.modifiers = chord & _MODIFIER_MASK

    def restore(self):
        self._pressed = False
        if self._restore_visible is not None:
            visible = self._restore_visible
            self._restore_visible = None
            self.window._set_mask_visible(visible)

    def _restore_if_outside(self):
        app = QApplication.instance()
        if app.activeModalWidget() is not None or app.activeWindow() is None or app.activeWindow() not in (
                self.window, self.window.edit_panel):
            self.restore()

    def _usable_context(self, watched):
        if not isinstance(watched, QWidget) or QApplication.activeModalWidget() is not None:
            return False
        if watched.window() not in (self.window, self.window.edit_panel):
            return False
        inputs = (QLineEdit, QAbstractSpinBox, QTextEdit, QPlainTextEdit,
                  QKeySequenceEdit, QComboBox)
        for widget in (watched, QApplication.focusWidget()):
            while widget is not None:
                if isinstance(widget, inputs):
                    return False
                widget = widget.parentWidget()
        return True

    def eventFilter(self, watched, event):
        kind = event.type()
        if kind == QEvent.ApplicationDeactivate:
            self.restore()
        elif kind == QEvent.WindowDeactivate and watched in (self.window, self.window.edit_panel):
            QTimer.singleShot(0, self._restore_if_outside)
        elif kind == QEvent.KeyRelease and self._pressed:
            released_modifier = int(_MODIFIER_KEYS.get(event.key(), 0)) & self.modifiers
            if event.key() == self.key or released_modifier:
                if not event.isAutoRepeat():
                    self.restore()
                event.accept()
                return True
        elif kind in (QEvent.ShortcutOverride, QEvent.KeyPress):
            modifiers = int(event.modifiers()) & ~int(Qt.KeypadModifier)
            if event.key() == self.key and modifiers == self.modifiers and self._usable_context(watched):
                event.accept()
                if kind == QEvent.KeyPress and not event.isAutoRepeat() and not self._pressed:
                    self._pressed = True
                    visible = self.window.state.is_mask_visible
                    if self.mode == "hold":
                        self._restore_visible = visible
                    self.window._set_mask_visible(not visible)
                return True
        return super().eventFilter(watched, event)
