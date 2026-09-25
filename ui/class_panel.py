# ui/class_panel.py
"""
类别选择面板：下拉框 + 颜色预览 + 管理按钮 + 像素统计
"""
from PyQt5.QtWidgets import (QWidget, QHBoxLayout, QLabel,
                             QComboBox, QPushButton, QDialog)
from PyQt5.QtCore import pyqtSignal


class ClassPanel(QWidget):
    """
    Signals
    -------
    class_changed(idx: int)    当前类别下标变化
    manage_requested()         用户点击"管理类别"
    """
    class_changed    = pyqtSignal(int)
    manage_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        layout.addWidget(QLabel("🏷 当前绘制类别 (数字键切换):"))

        self.combo = QComboBox()
        self.combo.setMinimumWidth(200)
        self.combo.currentIndexChanged.connect(self._on_combo_changed)
        layout.addWidget(self.combo)

        self.lbl_color = QLabel("  ")
        self.lbl_color.setFixedSize(28, 22)
        self.lbl_color.setStyleSheet("background-color: red; border:1px solid gray;")
        layout.addWidget(self.lbl_color)

        layout.addSpacing(10)

        btn_manage = QPushButton("⚙ 管理类别")
        btn_manage.clicked.connect(self.manage_requested)
        layout.addWidget(btn_manage)

        layout.addSpacing(20)

        self.lbl_stats = QLabel("")
        self.lbl_stats.setStyleSheet("color:#555; font-size:11px;")
        layout.addWidget(self.lbl_stats)

        layout.addStretch()

        # 内部缓存
        self._classes: list = []

    # ──────────────────────────────────────────────────────────────────────────
    def refresh(self, classes: list, current_idx: int = 0):
        """刷新类别列表（从 MainWindow 调用）"""
        self._classes = classes
        self.combo.blockSignals(True)
        self.combo.clear()
        for cls in classes:
            self.combo.addItem(f"[{cls['value']}] {cls['name']}")
        idx = min(current_idx, len(classes) - 1) if classes else 0
        self.combo.setCurrentIndex(idx)
        self.combo.blockSignals(False)
        self._update_color(idx)

    def set_stats(self, text: str):
        self.lbl_stats.setText(text)

    def current_index(self) -> int:
        return self.combo.currentIndex()

    def set_index(self, idx: int):
        self.combo.setCurrentIndex(idx)

    # ──────────────────────────────────────────────────────────────────────────
    def _on_combo_changed(self, idx: int):
        self._update_color(idx)
        self.class_changed.emit(idx)

    def _update_color(self, idx: int):
        if 0 <= idx < len(self._classes):
            b, g, r = self._classes[idx]["color"]
            self.lbl_color.setStyleSheet(
                f"background-color: rgb({r},{g},{b}); border:1px solid gray;")
