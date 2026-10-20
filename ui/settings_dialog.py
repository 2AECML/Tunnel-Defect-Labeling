"""文件查找与掩膜保存偏好设置。"""

from PyQt5.QtCore import Qt, QRectF, QSize, pyqtSignal
from PyQt5.QtGui import QColor, QPainter, QPen
from PyQt5.QtWidgets import (
    QButtonGroup, QCheckBox, QDialog, QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout,
)

from ui.theme import THEMES

IMAGE_FILTER_OPTIONS = (
    ("all", "全部图片"),
    ("with_mask", "有掩膜文件"),
    ("without_mask", "无掩膜文件"),
)


class ToggleSwitch(QCheckBox):
    """保留复选框的键盘和辅助功能语义，绘制为紧凑开关。"""

    def __init__(self, name, theme, parent=None):
        super().__init__(parent)
        self._theme = theme
        self.setAccessibleName(name)
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedSize(46, 30)

    def sizeHint(self):
        return QSize(46, 30)

    def hitButton(self, position):
        return self.rect().contains(position)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        t = self._theme
        track = QColor(t['text_accent'] if self.isChecked() else t['border_hover'])
        painter.setPen(Qt.NoPen)
        painter.setBrush(track)
        painter.drawRoundedRect(QRectF(2, 4, 42, 22), 11, 11)
        painter.setBrush(QColor("#ffffff"))
        painter.drawEllipse(QRectF(25 if self.isChecked() else 5, 7, 16, 16))
        if self.hasFocus():
            painter.setBrush(Qt.NoBrush)
            painter.setPen(QPen(QColor(t['text_accent']), 1, Qt.DotLine))
            painter.drawRoundedRect(QRectF(0.5, 1, 45, 28), 13, 13)


class SettingsDialog(QDialog):
    save_requested = pyqtSignal()

    def __init__(self, recursive_search=False, preserve_mask_structure=False,
                 theme_name="light", parent=None, image_filter="all"):
        super().__init__(parent)
        self.setWindowTitle("设置")
        self.setWindowFlag(Qt.WindowContextHelpButtonHint, False)
        self.setObjectName("settingsDialog")
        self.setMinimumWidth(520)
        self.resize(560, 600)
        t = THEMES[theme_name]
        self.setStyleSheet(self._style(t))

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 22)
        layout.setSpacing(10)
        title = QLabel("设置")
        title.setObjectName("settingsTitle")
        layout.addWidget(title)
        subtitle = QLabel("管理文件查找与掩膜保存方式")
        subtitle.setObjectName("settingsSubtitle")
        layout.addWidget(subtitle)
        layout.addSpacing(12)

        self.chk_recursive = ToggleSwitch("递归查找子目录", t)
        self.chk_recursive.setChecked(recursive_search)
        layout.addWidget(self._section_label("文件查找"))
        search_card, search_layout = self._card()
        search_layout.addLayout(self._option_row(
            "递归查找子目录", "同时查找原图与掩膜文件夹中的所有子目录。",
            self.chk_recursive))
        line = QFrame()
        line.setObjectName("settingsDivider")
        line.setFixedHeight(1)
        search_layout.addWidget(line)
        filter_label = QLabel("图片显示范围")
        filter_label.setObjectName("settingsOption")
        search_layout.addWidget(filter_label)
        filter_hint = QLabel("按掩膜文件是否存在筛选图片。")
        filter_hint.setObjectName("settingsDescription")
        search_layout.addWidget(filter_hint)
        choices = QHBoxLayout()
        choices.setSpacing(8)
        self._filter_group = QButtonGroup(self)
        self.filter_buttons = {}
        for value, text in IMAGE_FILTER_OPTIONS:
            button = QPushButton(text)
            button.setObjectName("imageFilterChoice")
            button.setCheckable(True)
            button.setAutoDefault(False)
            button.setCursor(Qt.PointingHandCursor)
            self._filter_group.addButton(button)
            self.filter_buttons[value] = button
            choices.addWidget(button, 1)
        self.filter_buttons.get(image_filter, self.filter_buttons["all"]).setChecked(True)
        search_layout.addLayout(choices)
        layout.addWidget(search_card)
        layout.addSpacing(8)

        self.chk_preserve_structure = ToggleSwitch("保存掩膜时保留目录层级", t)
        self.chk_preserve_structure.setChecked(preserve_mask_structure)
        layout.addWidget(self._section_label("掩膜保存"))
        save_card, save_layout = self._card()
        save_layout.addLayout(self._option_row(
            "保留原图目录层级", "按原图的相对目录保存，便于区分同名图片。",
            self.chk_preserve_structure))
        line = QFrame()
        line.setObjectName("settingsDivider")
        line.setFixedHeight(1)
        save_layout.addWidget(line)
        example = QLabel("保存位置示例")
        example.setObjectName("settingsHint")
        save_layout.addWidget(example)
        source = QLabel("原图文件夹 / 区段 A / image.jpg")
        source.setObjectName("settingsSource")
        save_layout.addWidget(source)
        self.lbl_save_preview = QLabel()
        self.lbl_save_preview.setObjectName("settingsPreview")
        self.lbl_save_preview.setWordWrap(True)
        save_layout.addWidget(self.lbl_save_preview)
        self.chk_preserve_structure.toggled.connect(self._update_preview)
        self._update_preview()
        layout.addWidget(save_card)
        layout.addStretch(1)
        layout.addSpacing(8)

        footer = QHBoxLayout()
        remember = QLabel("保存后自动记住偏好")
        remember.setObjectName("settingsHint")
        footer.addWidget(remember)
        footer.addStretch()
        self.btn_cancel = QPushButton("取消")
        self.btn_cancel.clicked.connect(self.reject)
        footer.addWidget(self.btn_cancel)
        self.btn_save = QPushButton("保存设置")
        self.btn_save.setObjectName("settingsSave")
        self.btn_save.setDefault(True)
        self.btn_save.clicked.connect(self.save_requested)
        footer.addWidget(self.btn_save)
        layout.addLayout(footer)
        self.setTabOrder(self.chk_recursive, self.filter_buttons["all"])
        self.setTabOrder(self.filter_buttons["without_mask"], self.chk_preserve_structure)
        self.setTabOrder(self.chk_preserve_structure, self.btn_cancel)
        self.setTabOrder(self.btn_cancel, self.btn_save)

    @staticmethod
    def _section_label(text):
        label = QLabel(text)
        label.setObjectName("settingsSection")
        return label

    @staticmethod
    def _card():
        card = QFrame()
        card.setObjectName("settingsCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(12)
        return card, layout

    @staticmethod
    def _option_row(title, description, switch):
        row = QHBoxLayout()
        row.setSpacing(18)
        text = QVBoxLayout()
        text.setSpacing(6)
        label = QLabel(title)
        label.setObjectName("settingsOption")
        switch.setToolTip(title)
        label.setBuddy(switch)
        text.addWidget(label)
        hint = QLabel(description)
        hint.setObjectName("settingsDescription")
        hint.setWordWrap(True)
        text.addWidget(hint)
        row.addLayout(text, 1)
        row.addWidget(switch, 0, Qt.AlignVCenter)
        return row

    def _update_preview(self):
        directory = "区段 A / " if self.chk_preserve_structure.isChecked() else ""
        self.lbl_save_preview.setText(f"→  掩膜文件夹 / {directory}image.png")

    def values(self):
        image_filter = next(value for value, button in self.filter_buttons.items()
                            if button.isChecked())
        return (self.chk_recursive.isChecked(), self.chk_preserve_structure.isChecked(),
                image_filter)

    @staticmethod
    def _style(t):
        return f"""
QDialog#settingsDialog {{ background: {t['bg_root']}; }}
QDialog#settingsDialog QLabel {{
    color: {t['text_primary']}; font-family: 'Microsoft YaHei', 'Segoe UI';
    font-size: 12px; background: transparent; border: none;
}}
QDialog#settingsDialog QLabel#settingsTitle {{ font-size: 22px; font-weight: 600; }}
QDialog#settingsDialog QLabel#settingsSubtitle {{ color: {t['text_secondary']}; }}
QDialog#settingsDialog QLabel#settingsSection {{
    color: {t['text_secondary']}; font-size: 11px; font-weight: 600;
}}
QDialog#settingsDialog QFrame#settingsCard {{
    background: {t['bg_bar']}; border: 1px solid {t['border']}; border-radius: 10px;
}}
QDialog#settingsDialog QLabel#settingsOption {{ font-size: 13px; font-weight: 600; }}
QDialog#settingsDialog QLabel#settingsDescription,
QDialog#settingsDialog QLabel#settingsHint,
QDialog#settingsDialog QLabel#settingsSource {{ color: {t['text_secondary']}; font-size: 11px; }}
QDialog#settingsDialog QLabel#settingsPreview {{ color: {t['text_accent']}; font-size: 12px; }}
QDialog#settingsDialog QFrame#settingsDivider {{ background: {t['sep']}; border: none; }}
QDialog#settingsDialog QPushButton {{
    background: {t['bg_bar']}; color: {t['text_primary']}; border: 1px solid {t['border']};
    border-radius: 6px; padding: 8px 16px; font-size: 12px; font-weight: 500;
    font-family: 'Microsoft YaHei', 'Segoe UI';
}}
QDialog#settingsDialog QPushButton:hover {{ background: {t['bg_hover']}; }}
QDialog#settingsDialog QPushButton:focus {{ border-color: {t['text_accent']}; }}
QDialog#settingsDialog QPushButton#imageFilterChoice {{
    padding: 8px 4px; font-size: 11px;
}}
QDialog#settingsDialog QPushButton#imageFilterChoice:checked {{
    background: {t['btn_folder_bg']}; color: {t['text_accent']};
    border-color: {t['text_accent']}; font-weight: 600;
}}
QDialog#settingsDialog QPushButton#settingsSave {{
    background: #2563a6; color: white; border-color: #2563a6;
}}
QDialog#settingsDialog QPushButton#settingsSave:hover {{ background: #1d5087; }}
"""
