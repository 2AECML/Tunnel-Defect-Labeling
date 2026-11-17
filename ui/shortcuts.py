"""标注窗口全部应用快捷键的默认值、校验与显示。"""

from dataclasses import dataclass
import json

from PyQt5.QtCore import QEvent, QObject, Qt
from PyQt5.QtGui import QKeySequence
from PyQt5.QtWidgets import (
    QApplication, QAbstractSpinBox, QComboBox, QKeySequenceEdit,
    QLineEdit, QPlainTextEdit, QTextEdit, QWidget,
)


@dataclass(frozen=True)
class Shortcut:
    name: str
    label: str
    default: str
    action: str


SHORTCUTS = (
    Shortcut("previous", "上一张", "A", "previous"),
    Shortcut("next", "下一张", "D", "next"),
    Shortcut("undo", "撤销", "Ctrl+Z", "undo"),
    Shortcut("redo", "重做（恢复撤销）", "Ctrl+Y", "redo"),
    Shortcut("save", "保存掩膜", "Ctrl+S", "save"),
    Shortcut("overlay", "掩膜叠加", "C", "overlay"),
)
DEFAULT_SHORTCUTS = {item.name: item.default for item in SHORTCUTS}
MODIFIER_MASK = int(Qt.KeyboardModifierMask)
MODIFIER_KEYS = (Qt.Key_Control, Qt.Key_Shift, Qt.Key_Alt, Qt.Key_Meta)


def normalize_shortcut(text):
    return QKeySequence(text, QKeySequence.PortableText).toString(QKeySequence.PortableText)


def sequence_error(sequence):
    if sequence.isEmpty():
        return "请设置一个快捷键。"
    if sequence.count() != 1:
        return "请使用单个按键或一组组合键，例如 C、Ctrl+K。"
    chord = int(sequence[0])
    key = chord & ~MODIFIER_MASK
    if key in (0, Qt.Key_unknown, *MODIFIER_KEYS):
        return "快捷键需要包含一个普通按键。"
    if key in (Qt.Key_Tab, Qt.Key_Backtab):
        return "Tab 用于切换输入焦点，请选择其他按键。"
    return ""


def shortcut_errors(bindings):
    errors, used = {}, {}
    for item in SHORTCUTS:
        sequence = QKeySequence(bindings.get(item.name, ""), QKeySequence.PortableText)
        error = sequence_error(sequence)
        if error:
            errors[item.name] = f"{item.label}：{error}"
            continue
        chord = int(sequence[0])
        if chord in used:
            other = used[chord]
            error = f"“{item.label}”与“{other.label}”的快捷键重复，请修改其中一个。"
            errors[item.name] = errors[other.name] = error
        else:
            used[chord] = item
    return errors


def load_shortcuts(settings):
    bindings = dict(DEFAULT_SHORTCUTS)
    raw = settings.value("shortcuts", "", type=str)
    if raw:
        try:
            saved = json.loads(raw)
            if not isinstance(saved, dict) or any(not isinstance(v, str) for v in saved.values()):
                return bindings
            # 旧版的 32 项配置不再适用，不恢复已移除的快捷键。
            if set(saved) - set(bindings):
                return bindings
            bindings.update({k: v for k, v in saved.items() if k in bindings})
            if "overlay" not in saved:
                bindings["overlay"] = settings.value("mask_shortcut", "C", type=str)
        except (ValueError, TypeError):
            return dict(DEFAULT_SHORTCUTS)
    else:
        bindings["overlay"] = settings.value("mask_shortcut", "C", type=str)
    if shortcut_errors(bindings):
        return dict(DEFAULT_SHORTCUTS)
    return {key: normalize_shortcut(value) for key, value in bindings.items()}


def action_shortcut_text(bindings, action):
    return " / ".join(QKeySequence(bindings[item.name]).toString(QKeySequence.NativeText)
                      for item in SHORTCUTS if item.action == action)


def shortcut_action(bindings, event):
    chord = event.key() | (int(event.modifiers()) & ~int(Qt.KeypadModifier))
    return next((item.action for item in SHORTCUTS
                 if int(QKeySequence(bindings[item.name])[0]) == chord), None)


class ShortcutController(QObject):
    """响应五项常用快捷键；掩膜叠加由原有控制器处理长按状态。"""

    def __init__(self, window):
        super().__init__(window)
        self.window = window
        QApplication.instance().installEventFilter(self)

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
        if kind in (QEvent.ShortcutOverride, QEvent.KeyPress) and self._usable_context(watched):
            action = shortcut_action(self.window.shortcuts, event)
            if action and action != "overlay":
                event.accept()
                if kind == QEvent.KeyPress and not event.isAutoRepeat():
                    self.window._trigger_shortcut(action)
                return True
        return super().eventFilter(watched, event)
