# ui/edit_panel.py
"""
悬浮编辑面板 —— 开启编辑时显示，关闭时隐藏。
"""

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QSlider, QCheckBox,
    QComboBox, QButtonGroup, QFrame, QDialog, QSizeGrip,
    QListView
)
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QFont

from core.config import DrawTool, DEFAULT_BRUSH_LINE, DEFAULT_BRUSH_POLY, DEFAULT_BRUSH_ERASER
from ui.class_manager_dialog import ClassManagerDialog
from ui.theme import THEMES, build_panel_style


# ── 带标签滑块 ────────────────────────────────────────────────────────────────
class LabeledSlider(QWidget):
    valueChanged = pyqtSignal(int)

    def __init__(self, label, mn, mx, val, label_w=52, slider_w=130, parent=None):
        super().__init__(parent)
        h = QHBoxLayout(self)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(6)
        self.lbl_name = QLabel(label)
        self.lbl_name.setFixedWidth(label_w)
        self.lbl_name.setObjectName("sliderLabel")
        self.slider = QSlider(Qt.Horizontal)
        self.slider.setRange(mn, mx)
        self.slider.setValue(val)
        self.slider.setFixedWidth(slider_w)
        self.lbl_val = QLabel(str(val))
        self.lbl_val.setFixedWidth(34)
        self.lbl_val.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.lbl_val.setObjectName("sliderValLabel")
        self.slider.valueChanged.connect(lambda v: (
            self.lbl_val.setText(str(v)),
            self.valueChanged.emit(v)
        ))
        h.addWidget(self.lbl_name)
        h.addWidget(self.slider)
        h.addWidget(self.lbl_val)

    def value(self): return self.slider.value()

    def setValue(self, v): self.slider.setValue(v)


def _sep():
    f = QFrame()
    f.setObjectName("panelSep")
    f.setFrameShape(QFrame.HLine)
    return f


class EditPanel(QWidget):
    tool_changed = pyqtSignal(str)
    brush_changed = pyqtSignal(int)
    class_changed = pyqtSignal(int)
    alpha_changed = pyqtSignal(int)
    contour_changed = pyqtSignal(bool)
    show_all_changed = pyqtSignal(bool)
    brightness_changed = pyqtSignal(int)
    contrast_changed = pyqtSignal(int)
    undo_requested = pyqtSignal()
    save_requested = pyqtSignal()
    close_edit_requested = pyqtSignal()
    classes_updated = pyqtSignal(list)

    _drag_pos = None

    def __init__(self, state, theme_name="light", parent=None):
        super().__init__(parent,
                         Qt.Window | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.state = state
        self._theme_name = theme_name
        self.setFixedWidth(310)
        self._build_ui()
        self.apply_theme(theme_name)

    # ──────────────────────────────────────────────────────────────────────────
    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 8)
        root.setSpacing(0)

        # ── 标题栏 ──
        title_bar = QWidget()
        title_bar.setObjectName("titleBar")
        title_bar.setFixedHeight(38)
        tb = QHBoxLayout(title_bar)
        tb.setContentsMargins(14, 0, 10, 0)
        self.lbl_title = QLabel("✏   标注编辑")
        self.lbl_title.setObjectName("panelTitle")
        self.lbl_title.setStyleSheet("font-size:13px; font-weight:bold;")
        btn_close = QPushButton("✕")
        btn_close.setObjectName("panelClose")
        btn_close.setFixedSize(26, 26)
        btn_close.clicked.connect(self.close_edit_requested)
        tb.addWidget(self.lbl_title)
        tb.addStretch()
        tb.addWidget(btn_close)
        root.addWidget(title_bar)
        title_bar.mousePressEvent = self._tb_press
        title_bar.mouseMoveEvent = self._tb_move
        title_bar.mouseReleaseEvent = self._tb_release

        # ── 滚动内容区 ──
        content = QWidget()
        content.setObjectName("panelContent")
        v = QVBoxLayout(content)
        v.setContentsMargins(14, 10, 14, 6)
        v.setSpacing(10)

        # §1 绘制工具
        v.addWidget(self._section("DRAW TOOL"))
        tool_row = QHBoxLayout()
        tool_row.setSpacing(6)
        # 👇 文案从"折线笔" -> "线状笔"
        self.btn_line = self._tool_btn("🖌", "线状笔", "[ 1 ]")
        self.btn_poly = self._tool_btn("⬛", "面状笔", "[ 2 ]")
        self.btn_eraser = self._tool_btn("⬜", "橡皮擦", "[ E ]")
        self.btn_edit_poly = QPushButton("◇  编辑已有多边形    [ 4 ]")
        self.btn_edit_poly.setObjectName("toolBtn")
        self.btn_edit_poly.setCheckable(True)
        self.btn_edit_poly.setFixedHeight(38)
        grp = QButtonGroup(self)
        for b in (self.btn_line, self.btn_poly, self.btn_eraser, self.btn_edit_poly):
            grp.addButton(b)
        self.btn_line.setChecked(True)
        self.btn_line.clicked.connect(lambda: self._on_tool(DrawTool.LINE))
        self.btn_poly.clicked.connect(lambda: self._on_tool(DrawTool.POLY))
        self.btn_eraser.clicked.connect(lambda: self._on_tool(DrawTool.ERASER))
        self.btn_edit_poly.clicked.connect(
            lambda: self._on_tool(DrawTool.EDIT_POLY)
        )
        tool_row.addWidget(self.btn_line)
        tool_row.addWidget(self.btn_poly)
        tool_row.addWidget(self.btn_eraser)
        tool_row.addStretch()
        v.addLayout(tool_row)
        v.addWidget(self.btn_edit_poly)
        self.lbl_polygon_hint = QLabel(
            "单击已有面状区域选中；拖动控制点改形，"
            "拖动区域内部整体移动；双击边线增加控制点；"
            "加点不改变形状；按住左键拖动改形或移动；"
            "选中控制点或多边形后，右击或 Ctrl+D 删除。"
        )
        self.lbl_polygon_hint.setObjectName("statsLabel")
        self.lbl_polygon_hint.setWordWrap(True)
        self.lbl_polygon_hint.hide()
        v.addWidget(self.lbl_polygon_hint)

        # ！！ 这里删除了原本所有的 line_hint 提示框相关的代码 ！！

        # §2 笔刷
        v.addWidget(_sep())
        v.addWidget(self._section("BRUSH SIZE"))
        self.slider_brush = LabeledSlider("笔刷", 1, 80, DEFAULT_BRUSH_LINE)
        self.slider_brush.valueChanged.connect(self.brush_changed)
        v.addWidget(self.slider_brush)

        # §3 病害类别
        v.addWidget(_sep())
        v.addWidget(self._section("DEFECT CLASS"))
        class_row = QHBoxLayout()
        class_row.setSpacing(8)
        self.lbl_class_dot = QLabel()
        self.lbl_class_dot.setFixedSize(14, 14)
        self.lbl_class_dot.setStyleSheet(
            "border-radius:7px; border:1px solid #888; background:red;")
        self.combo_class = QComboBox()
        self.combo_class.setView(QListView())

        self.combo_class.currentIndexChanged.connect(self._on_class_changed)
        class_row.addWidget(self.lbl_class_dot)
        class_row.addWidget(self.combo_class, 1)
        v.addLayout(class_row)

        btn_manage = QPushButton("⚙   管理类别")
        btn_manage.setObjectName("manageBtn")
        btn_manage.clicked.connect(self._open_class_manager)
        v.addWidget(btn_manage)

        self.lbl_stats = QLabel("—")
        self.lbl_stats.setObjectName("statsLabel")
        self.lbl_stats.setWordWrap(True)
        self.lbl_stats.setStyleSheet("font-size:10px; padding:2px 0;")
        v.addWidget(self.lbl_stats)

        # §4 掩膜显示
        v.addWidget(_sep())
        v.addWidget(self._section("MASK DISPLAY"))
        self.slider_alpha = LabeledSlider("透明度", 0, 100, 50)
        self.slider_alpha.valueChanged.connect(self.alpha_changed)
        v.addWidget(self.slider_alpha)
        chk_row = QHBoxLayout()
        self.chk_contour = QCheckBox("显示轮廓")
        self.chk_show_all = QCheckBox("所有类别")
        self.chk_contour.setChecked(True)
        self.chk_show_all.setChecked(True)
        self.chk_contour.stateChanged.connect(
            lambda s: self.contour_changed.emit(bool(s)))
        self.chk_show_all.stateChanged.connect(
            lambda s: self.show_all_changed.emit(bool(s)))
        chk_row.addWidget(self.chk_contour)
        chk_row.addWidget(self.chk_show_all)
        chk_row.addStretch()
        v.addLayout(chk_row)

        # §5 原图调节
        v.addWidget(_sep())
        v.addWidget(self._section("IMAGE ADJUST"))
        self.slider_brightness = LabeledSlider("亮度", -100, 100, 0)
        self.slider_contrast = LabeledSlider("对比度", 10, 300, 100)
        self.slider_brightness.valueChanged.connect(self.brightness_changed)
        self.slider_contrast.valueChanged.connect(self.contrast_changed)
        v.addWidget(self.slider_brightness)
        v.addWidget(self.slider_contrast)
        btn_reset = QPushButton("↺  重置亮度 / 对比度")
        btn_reset.setObjectName("resetBtn")
        btn_reset.clicked.connect(self._reset_bc)
        v.addWidget(btn_reset)

        # §6 操作
        v.addWidget(_sep())
        act = QHBoxLayout()
        act.setSpacing(8)
        self.btn_undo = QPushButton("↩  撤销\nCtrl+Z")
        self.btn_save = QPushButton("💾  保存\nCtrl+S")
        self.btn_undo.setObjectName("undoBtn")
        self.btn_save.setObjectName("saveBtn")
        self.btn_undo.setFixedHeight(46)
        self.btn_save.setFixedHeight(46)
        self.btn_undo.setEnabled(False)
        self.btn_undo.clicked.connect(self.undo_requested)
        self.btn_save.clicked.connect(self.save_requested)
        act.addWidget(self.btn_undo)
        act.addWidget(self.btn_save)
        v.addLayout(act)
        v.addStretch()

        root.addWidget(content)

        grip_row = QHBoxLayout()
        grip_row.setContentsMargins(0, 0, 4, 0)
        grip_row.addStretch()
        grip_row.addWidget(QSizeGrip(self))
        root.addLayout(grip_row)

    # ── 工具函数 ──────────────────────────────────────────────────────────────
    def _section(self, text):
        lbl = QLabel(text)
        lbl.setObjectName("sectionLabel")
        lbl.setStyleSheet("font-size:10px; font-weight:bold; letter-spacing:1.5px;")
        return lbl

    def _tool_btn(self, icon, label, shortcut):
        b = QPushButton(f"{icon}\n{label}\n{shortcut}")
        b.setObjectName("toolBtn")
        b.setCheckable(True)
        b.setFixedSize(82, 64)
        return b

    # ── 拖动 ─────────────────────────────────────────────────────────────────
    def _tb_press(self, e):
        if e.button() == Qt.LeftButton:
            self._drag_pos = e.globalPos() - self.frameGeometry().topLeft()

    def _tb_move(self, e):
        if self._drag_pos and e.buttons() == Qt.LeftButton:
            self.move(e.globalPos() - self._drag_pos)

    def _tb_release(self, e):
        self._drag_pos = None

    # ── 回调 ─────────────────────────────────────────────────────────────────
    def _on_tool(self, tool):
        self.state.tool = tool
        if tool == DrawTool.LINE:
            self.slider_brush.setValue(DEFAULT_BRUSH_LINE)
        elif tool == DrawTool.POLY:
            self.slider_brush.setValue(DEFAULT_BRUSH_POLY)
        elif tool == DrawTool.ERASER:
            self.slider_brush.setValue(DEFAULT_BRUSH_ERASER)
        self._update_tool_controls(tool)
        self.tool_changed.emit(tool)

    def _update_tool_controls(self, tool):
        editing_polygon = tool == DrawTool.EDIT_POLY
        self.slider_brush.setEnabled(not editing_polygon)
        self.lbl_polygon_hint.setVisible(editing_polygon)

    def _on_class_changed(self, idx):
        if 0 <= idx < len(self.state.classes):
            b, g, r = self.state.classes[idx]["color"]
            self.lbl_class_dot.setStyleSheet(
                f"border-radius:7px; border:1px solid #888; background:rgb({r},{g},{b});")
        self.class_changed.emit(idx)

    def _reset_bc(self):
        self.slider_brightness.setValue(0)
        self.slider_contrast.setValue(100)

    def _open_class_manager(self):
        dlg = ClassManagerDialog(self.state.classes, self)
        if dlg.exec_() == QDialog.Accepted:
            self.state.classes = dlg.get_classes()
            self.state.current_class = min(
                self.state.current_class, len(self.state.classes) - 1)
            self.refresh_classes()
            self.classes_updated.emit(self.state.classes)

    # ── 主题 ─────────────────────────────────────────────────────────────────
    def apply_theme(self, theme_name: str):
        self._theme_name = theme_name
        t = THEMES[theme_name]

        # 提取颜色，方便 ComboBox 下拉列表使用
        bg_input = t.get('bg_input', '#2d2d30' if theme_name == 'dark' else '#ffffff')
        text_primary = t.get('text_primary', '#e0e0e0' if theme_name == 'dark' else '#000000')
        bg_hover = t.get('bg_hover', '#3e3e42' if theme_name == 'dark' else '#e5f3ff')
        border_col = t.get('border', '#404040' if theme_name == 'dark' else '#cccccc')

        self.setStyleSheet(build_panel_style(t) + f"""
            QLabel#panelTitle  {{ color: {t['text_primary']}; }}
            QPushButton#panelClose {{
                background: transparent; color: {t['text_muted']};
                border: none; font-size:14px; border-radius:4px;
            }}
            QPushButton#panelClose:hover {{ color: {t['text_red']}; background:{t['bg_hover']}; }}
            QLabel#sectionLabel {{ color: {t['section_label']}; }}
            QLabel#sliderLabel  {{ color: {t['text_secondary']}; font-size:11px; }}
            QLabel#sliderValLabel {{ color: {t['text_primary']}; font-size:11px; }}
            QLabel#statsLabel   {{ color: {t['text_muted']}; }}
            QFrame#panelSep     {{ color: {t['sep']}; max-height:1px; }}

            /* 👇 新增：修复 QComboBox 下拉菜单看不清的问题 */
            QComboBox QAbstractItemView {{
                background-color: {bg_input};
                color: {text_primary};
                selection-background-color: {bg_hover};
                selection-color: {text_primary};
                border: 1px solid {border_col};
                outline: none; /* 去除虚线框 */
            }}
            /* 下拉列表每一项的内边距，让它不那么拥挤 */
            QComboBox::item {{
                min-height: 24px;
                padding-left: 5px;
            }}

            QPushButton#manageBtn {{
                background:{t['bg_input']}; color:{t['text_secondary']};
                border:1px solid {t['border']}; border-radius:4px;
                font-size:11px; padding:5px;
            }}
            QPushButton#manageBtn:hover {{ background:{t['bg_hover']}; color:{t['text_primary']}; }}
            QPushButton#resetBtn {{
                background:transparent; color:{t['text_muted']};
                border:none; font-size:10px; text-align:left;
            }}
            QPushButton#resetBtn:hover {{ color:{t['text_secondary']}; }}
            QPushButton#undoBtn {{
                background:{t['bg_input']}; color:{t['text_primary']};
                border:1px solid {t['border']}; border-radius:6px; font-size:11px;
            }}
            QPushButton#undoBtn:hover {{ background:{t['bg_hover']}; }}
            QPushButton#undoBtn:disabled {{ color:{t['text_muted']}; }}
            QPushButton#saveBtn {{
                background:{'#1e3a1e' if theme_name == 'dark' else '#d0f0d0'};
                color:{t['text_green']}; border:1px solid {t['border_green']};
                border-radius:6px; font-size:11px; font-weight:bold;
            }}
            QPushButton#saveBtn:hover {{ background:{'#254a25' if theme_name == 'dark' else '#b8e8b8'}; }}
        """)

    # ── 公开接口 ─────────────────────────────────────────────────────────────
    def refresh_classes(self):
        self.combo_class.blockSignals(True)
        self.combo_class.clear()
        for cls in self.state.classes:
            self.combo_class.addItem(f"[{cls['value']}]   {cls['name']}")
        idx = min(self.state.current_class, len(self.state.classes) - 1)
        self.combo_class.setCurrentIndex(idx)
        self.combo_class.blockSignals(False)
        self._on_class_changed(idx)

    def set_stats(self, text):
        self.lbl_stats.setText(text or "—")

    def set_undo_enabled(self, v):
        self.btn_undo.setEnabled(v)

    # 注意这里，保留这个空函数防止 MainWindow 报错
    def show_line_hint(self, v):
        pass

    def set_tool_btn(self, tool):
        if tool == DrawTool.LINE:
            self.btn_line.setChecked(True)
        elif tool == DrawTool.POLY:
            self.btn_poly.setChecked(True)
        elif tool == DrawTool.ERASER:
            self.btn_eraser.setChecked(True)
        else:
            self.btn_edit_poly.setChecked(True)
        self._update_tool_controls(tool)

    def set_brush_value(self, value):
        self.slider_brush.setValue(value)

    def set_class_index(self, index):
        if 0 <= index < self.combo_class.count():
            self.combo_class.setCurrentIndex(index)

    def alpha_value(self):
        return self.slider_alpha.value()

    def contour_checked(self):
        return self.chk_contour.isChecked()

    def show_all_checked(self):
        return self.chk_show_all.isChecked()

    def brightness_value(self):
        return self.slider_brightness.value()

    def contrast_value(self):
        return self.slider_contrast.value()
