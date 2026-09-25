# ui/toolbar_widget.py
"""
工具栏 Widget：
  · 编辑/查看模式切换
  · 工具选择（折线笔 / 面状笔 / 橡皮擦）
  · 笔刷大小滑块
  · 撤销按钮
  · 折线笔状态提示
"""
from PyQt5.QtWidgets import (QWidget, QHBoxLayout, QVBoxLayout,
                             QRadioButton, QButtonGroup, QSlider,
                             QPushButton, QLabel, QFrame)
from PyQt5.QtCore import Qt, pyqtSignal
from core.config import DrawTool, DEFAULT_BRUSH_LINE, DEFAULT_BRUSH_POLY, DEFAULT_BRUSH_ERASER


class ToolbarWidget(QWidget):
    """
    Signals
    -------
    mode_changed(edit: bool)      查看↔编辑
    tool_changed(tool: str)       DrawTool 常量
    brush_changed(size: int)
    undo_requested()
    commit_line_requested()       提交折线（Enter 按钮）
    cancel_line_requested()       取消折线（Esc 按钮）
    """
    mode_changed         = pyqtSignal(bool)
    tool_changed         = pyqtSignal(str)
    brush_changed        = pyqtSignal(int)
    undo_requested       = pyqtSignal()
    commit_line_requested = pyqtSignal()
    cancel_line_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self):
        outer = QVBoxLayout(self)
        outer.setSpacing(3)
        outer.setContentsMargins(0, 0, 0, 0)

        # ── 行1：模式 & 工具 & 笔刷 & 撤销 ──
        row = QHBoxLayout()

        # 模式
        self._mode_group = QButtonGroup(self)
        self.radio_view = QRadioButton("👀 查看/拖动")
        self.radio_edit = QRadioButton("✏️ 编辑 (右键拖画布)")
        self.radio_view.setChecked(True)
        self._mode_group.addButton(self.radio_view)
        self._mode_group.addButton(self.radio_edit)
        self.radio_view.toggled.connect(
            lambda checked: self.mode_changed.emit(not checked))

        # 工具
        self._tool_group = QButtonGroup(self)
        self.radio_line   = QRadioButton("〰 折线笔(裂缝) [1]")
        self.radio_poly   = QRadioButton("⬛ 面状笔 [2]")
        self.radio_eraser = QRadioButton("⬜ 橡皮擦 [3/E]")
        self.radio_line.setChecked(True)
        self._tool_group.addButton(self.radio_line)
        self._tool_group.addButton(self.radio_poly)
        self._tool_group.addButton(self.radio_eraser)
        self.radio_line.toggled.connect(self._on_tool_toggled)
        self.radio_poly.toggled.connect(self._on_tool_toggled)
        self.radio_eraser.toggled.connect(self._on_tool_toggled)

        # 笔刷
        self.slider_brush = QSlider(Qt.Horizontal)
        self.slider_brush.setRange(1, 80)
        self.slider_brush.setValue(DEFAULT_BRUSH_LINE)
        self.slider_brush.setFixedWidth(120)
        self.lbl_brush = QLabel(f"笔刷: {DEFAULT_BRUSH_LINE}")
        self.slider_brush.valueChanged.connect(self._on_brush_changed)

        # 撤销
        self.btn_undo = QPushButton("↩ 撤销 (Ctrl+Z)")
        self.btn_undo.clicked.connect(self.undo_requested)
        self.btn_undo.setEnabled(False)

        row.addWidget(self.radio_view)
        row.addWidget(self.radio_edit)
        row.addSpacing(15)
        row.addWidget(QLabel("工具:"))
        row.addWidget(self.radio_line)
        row.addWidget(self.radio_poly)
        row.addWidget(self.radio_eraser)
        row.addSpacing(10)
        row.addWidget(self.slider_brush)
        row.addWidget(self.lbl_brush)
        row.addSpacing(15)
        row.addWidget(self.btn_undo)
        row.addStretch()
        outer.addLayout(row)

        # ── 行2：折线笔提示 & 操作按钮（默认隐藏） ──
        self._line_hint_row = QHBoxLayout()
        self.lbl_line_hint = QLabel(
            "🖊 折线笔：单击添加节点  |  双击 / Enter 完成  |  Esc 取消")
        self.lbl_line_hint.setStyleSheet(
            "color: #b05000; background: #fff8e1; "
            "padding: 2px 8px; border-radius: 4px;")
        self.btn_commit_line = QPushButton("✔ 完成折线 (Enter)")
        self.btn_commit_line.setStyleSheet(
            "background:#4CAF50; color:white; font-weight:bold;")
        self.btn_commit_line.clicked.connect(self.commit_line_requested)
        self.btn_cancel_line = QPushButton("✖ 取消 (Esc)")
        self.btn_cancel_line.setStyleSheet(
            "background:#f44336; color:white;")
        self.btn_cancel_line.clicked.connect(self.cancel_line_requested)

        self._line_hint_row.addWidget(self.lbl_line_hint)
        self._line_hint_row.addStretch()
        self._line_hint_row.addWidget(self.btn_commit_line)
        self._line_hint_row.addWidget(self.btn_cancel_line)

        self._line_hint_widget = QWidget()
        self._line_hint_widget.setLayout(self._line_hint_row)
        self._line_hint_widget.setVisible(False)
        outer.addWidget(self._line_hint_widget)

    # ──────────────────────────────────────────────────────────────────────────
    # 内部回调
    # ──────────────────────────────────────────────────────────────────────────
    def _on_tool_toggled(self, _):
        tool = self.current_tool()
        # 自动调整笔刷默认值
        if tool == DrawTool.LINE:
            self.slider_brush.setValue(DEFAULT_BRUSH_LINE)
        elif tool == DrawTool.POLY:
            self.slider_brush.setValue(DEFAULT_BRUSH_POLY)
        else:
            self.slider_brush.setValue(DEFAULT_BRUSH_ERASER)
        self.tool_changed.emit(tool)

    def _on_brush_changed(self, v: int):
        self.lbl_brush.setText(f"笔刷: {v}")
        self.brush_changed.emit(v)

    # ──────────────────────────────────────────────────────────────────────────
    # 公开接口
    # ──────────────────────────────────────────────────────────────────────────
    def current_tool(self) -> str:
        if self.radio_line.isChecked():
            return DrawTool.LINE
        elif self.radio_poly.isChecked():
            return DrawTool.POLY
        return DrawTool.ERASER

    def set_tool(self, tool: str):
        """程序化切换工具（快捷键用）"""
        if tool == DrawTool.LINE:
            self.radio_line.setChecked(True)
        elif tool == DrawTool.POLY:
            self.radio_poly.setChecked(True)
        else:
            self.radio_eraser.setChecked(True)

    def set_undo_enabled(self, enabled: bool):
        self.btn_undo.setEnabled(enabled)

    def set_edit_enabled(self, enabled: bool):
        """编辑模式下启用/禁用工具区"""
        self.radio_line.setEnabled(enabled)
        self.radio_poly.setEnabled(enabled)
        self.radio_eraser.setEnabled(enabled)
        self.slider_brush.setEnabled(enabled)

    def show_line_hint(self, visible: bool):
        """折线绘制进行中时显示提示栏"""
        self._line_hint_widget.setVisible(visible)

    def set_edit_mode_radio(self, edit: bool):
        """从外部强制切换模式按钮状态"""
        if edit:
            self.radio_edit.setChecked(True)
        else:
            self.radio_view.setChecked(True)
