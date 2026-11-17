# ui/edit_panel.py
"""
悬浮编辑面板 —— 开启编辑时显示，关闭时隐藏。
"""

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QSlider, QCheckBox,
    QButtonGroup, QFrame, QDialog, QSizeGrip
)
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QFont

from core.config import (
    DrawTool,
    DEFAULT_BRUSH_LINE,
    DEFAULT_BRUSH_POLY,
    DEFAULT_BRUSH_ERASER,
)
from ui.class_manager_dialog import ClassManagerDialog
from ui.theme import THEMES, build_panel_style
from ui.styled_controls import ThemedComboBox, ThemedSpinBox
from ui.shortcuts import action_shortcut_text


# ── 带标签滑块 ────────────────────────────────────────────────────────────────
class LabeledSlider(QWidget):
    valueChanged = pyqtSignal(int)

    def __init__(self, label, mn, mx, val, label_w=52, slider_w=130, parent=None,
                 editable=False):
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
        if editable:
            self.spin_value = ThemedSpinBox()
            self.spin_value.setRange(mn, mx)
            self.spin_value.setValue(val)
            self.spin_value.setFixedWidth(72)
            self.spin_value.setKeyboardTracking(True)
            self.spin_value.setAccessibleName(label)
            self.spin_value.valueChanged.connect(self.slider.setValue)
            self.slider.valueChanged.connect(self.spin_value.setValue)
            value_widget = self.spin_value
        else:
            self.lbl_val = QLabel(str(val))
            self.lbl_val.setFixedWidth(34)
            self.lbl_val.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.lbl_val.setObjectName("sliderValLabel")
            self.slider.valueChanged.connect(lambda value: self.lbl_val.setText(str(value)))
            value_widget = self.lbl_val
        self.slider.valueChanged.connect(self.valueChanged)
        h.addWidget(self.lbl_name)
        h.addWidget(self.slider)
        h.addWidget(value_widget)

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
    similarity_changed = pyqtSignal(int)
    fill_range_changed = pyqtSignal(bool)
    resample_requested = pyqtSignal()
    class_changed = pyqtSignal(int)
    alpha_changed = pyqtSignal(int)
    contour_changed = pyqtSignal(bool)
    show_all_changed = pyqtSignal(bool)
    brightness_changed = pyqtSignal(int)
    contrast_changed = pyqtSignal(int)
    undo_requested = pyqtSignal()
    redo_requested = pyqtSignal()
    save_requested = pyqtSignal()
    close_edit_requested = pyqtSignal()
    classes_updated = pyqtSignal(list)

    _drag_pos = None

    def __init__(self, state, theme_name="light", parent=None):
        # 从属工具窗口只保持在所属主窗口上方，不对其他应用全局置顶。
        super().__init__(parent, Qt.Tool | Qt.FramelessWindowHint)
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
        self.btn_line = self._tool_btn("🖌", "线状笔")
        self.btn_poly = self._tool_btn("⬛", "面状笔")
        self.btn_eraser = self._tool_btn("⬜", "橡皮擦")
        self.btn_eraser.setToolTip("使用上次选择的擦除方式，可选笔刷、矩形或面状。")
        self.btn_edit_poly = QPushButton("◇  编辑已有多边形")
        self.btn_edit_poly.setObjectName("toolBtn")
        self.btn_edit_poly.setCheckable(True)
        self.btn_edit_poly.setFixedHeight(38)
        self.btn_auto_fill = QPushButton("▣  相似像素自动填充")
        self.btn_auto_fill.setObjectName("toolBtn")
        self.btn_auto_fill.setCheckable(True)
        self.btn_auto_fill.setFixedHeight(38)
        self.btn_sample_fill = QPushButton("取样框选填充")
        self.btn_sample_fill.setObjectName("toolBtn")
        self.btn_sample_fill.setCheckable(True)
        self.btn_sample_fill.setFixedHeight(38)
        grp = QButtonGroup(self)
        for b in (
            self.btn_line, self.btn_poly, self.btn_eraser,
            self.btn_edit_poly, self.btn_auto_fill, self.btn_sample_fill,
        ):
            grp.addButton(b)
        self.btn_line.setChecked(True)
        self.btn_line.clicked.connect(lambda: self._on_tool(DrawTool.LINE))
        self.btn_poly.clicked.connect(lambda: self._on_tool(DrawTool.POLY))
        self.btn_eraser.clicked.connect(lambda: self._on_tool(self.state.eraser_tool))
        self.btn_edit_poly.clicked.connect(
            lambda: self._on_tool(DrawTool.EDIT_POLY)
        )
        self.btn_auto_fill.clicked.connect(
            lambda: self._on_tool(DrawTool.AUTO_FILL)
        )
        self.btn_sample_fill.clicked.connect(lambda: self._on_tool(DrawTool.SAMPLE_FILL))
        tool_row.addWidget(self.btn_line)
        tool_row.addWidget(self.btn_poly)
        tool_row.addWidget(self.btn_eraser)
        tool_row.addStretch()
        v.addLayout(tool_row)
        self.eraser_controls = QWidget()
        eraser_row = QHBoxLayout(self.eraser_controls)
        eraser_row.setContentsMargins(0, 0, 0, 0)
        eraser_row.setSpacing(6)
        eraser_row.addWidget(QLabel("擦除方式"))
        self.combo_eraser = ThemedComboBox()
        self.combo_eraser.setAccessibleName("擦除方式")
        for label, tool in (("笔刷橡皮擦", DrawTool.ERASER),
                            ("矩形橡皮擦", DrawTool.RECT_ERASER),
                            ("面状橡皮擦", DrawTool.POLY_ERASER)):
            self.combo_eraser.addItem(label, tool)
        self.combo_eraser.setCurrentIndex(self.combo_eraser.findData(self.state.eraser_tool))
        self.combo_eraser.currentIndexChanged.connect(self._on_eraser_changed)
        eraser_row.addWidget(self.combo_eraser, 1)
        self.eraser_controls.hide()
        v.addWidget(self.eraser_controls)
        self.lbl_eraser_hint = QLabel()
        self.lbl_eraser_hint.setObjectName("statsLabel")
        self.lbl_eraser_hint.setWordWrap(True)
        self.lbl_eraser_hint.hide()
        v.addWidget(self.lbl_eraser_hint)
        v.addWidget(self.btn_edit_poly)
        fill_row = QHBoxLayout()
        fill_row.addWidget(self.btn_auto_fill, 1)
        fill_row.addWidget(self.btn_sample_fill, 1)
        v.addLayout(fill_row)
        self.lbl_polygon_hint = QLabel(
            "单击已有面状区域选中；拖动控制点改形，"
            "拖动区域内部整体移动；双击边线增加控制点；"
            "加点不改变形状；按住左键拖动改形或移动；"
            "选中控制点或多边形后，右击删除。"
        )
        self.lbl_polygon_hint.setObjectName("statsLabel")
        self.lbl_polygon_hint.setWordWrap(True)
        self.lbl_polygon_hint.hide()
        v.addWidget(self.lbl_polygon_hint)
        self.lbl_auto_fill_hint = QLabel(
            "单击原图中的一点，自动填充与该点颜色相近且相连的区域。"
            "自动连接 1–2 像素细缝并填满内部空洞。"
            "遇到已有标注停止扩张，不穿过或覆盖已有多边形。"
            "单击已有多边形则按其原类别补齐内部空点、孔洞及细缝。"
            "阈值越大，纳入的颜色范围越广；每次填充均可 Ctrl+Z 撤销。"
        )
        self.lbl_auto_fill_hint.setObjectName("statsLabel")
        self.lbl_auto_fill_hint.setWordWrap(True)
        self.lbl_auto_fill_hint.hide()
        v.addWidget(self.lbl_auto_fill_hint)
        self.sample_fill_controls = QWidget()
        sample_layout = QVBoxLayout(self.sample_fill_controls)
        sample_layout.setContentsMargins(0, 0, 0, 0)
        self.lbl_sample_fill_hint = QLabel()
        self.lbl_sample_fill_hint.setObjectName("statsLabel")
        self.lbl_sample_fill_hint.setWordWrap(True)
        sample_layout.addWidget(self.lbl_sample_fill_hint)
        sample_row = QHBoxLayout()
        self.combo_fill_range = ThemedComboBox()
        self.combo_fill_range.setAccessibleName("填充范围")
        self.combo_fill_range.addItem("矩形范围", False)
        self.combo_fill_range.addItem("面状范围", True)
        self.combo_fill_range.setCurrentIndex(int(self.state.fill_freehand))
        self.combo_fill_range.currentIndexChanged.connect(
            lambda: self.fill_range_changed.emit(bool(self.combo_fill_range.currentData()))
        )
        sample_row.addWidget(self.combo_fill_range, 1)
        self.btn_resample = QPushButton("重新取样")
        self.btn_resample.setObjectName("manageBtn")
        self.btn_resample.clicked.connect(self.resample_requested)
        sample_row.addWidget(self.btn_resample)
        sample_layout.addLayout(sample_row)
        self.sample_fill_controls.hide()
        v.addWidget(self.sample_fill_controls)

        # ！！ 这里删除了原本所有的 line_hint 提示框相关的代码 ！！

        # §2 笔刷
        self.size_separator = _sep()
        v.addWidget(self.size_separator)
        self.lbl_size_section = self._section("BRUSH SIZE")
        v.addWidget(self.lbl_size_section)
        self.slider_brush = LabeledSlider("笔刷", 1, 80, DEFAULT_BRUSH_LINE)
        self.slider_brush.valueChanged.connect(self.brush_changed)
        v.addWidget(self.slider_brush)
        self.slider_similarity = LabeledSlider(
            "色差阈值", 0, 100, self.state.fill_tolerance, label_w=60, slider_w=122,
            editable=True,
        )
        self.slider_similarity.valueChanged.connect(self.similarity_changed)
        self.slider_similarity.hide()
        v.addWidget(self.slider_similarity)

        # §3 病害类别
        v.addWidget(_sep())
        v.addWidget(self._section("DEFECT CLASS"))
        class_row = QHBoxLayout()
        class_row.setSpacing(8)
        self.lbl_class_dot = QLabel()
        self.lbl_class_dot.setFixedSize(14, 14)
        self.lbl_class_dot.setStyleSheet(
            "border-radius:7px; border:1px solid #888; background:red;")
        self.combo_class = ThemedComboBox()

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
        self.btn_redo = QPushButton("↪  重做\nCtrl+Y")
        self.btn_save = QPushButton("💾  保存\nCtrl+S")
        self.btn_undo.setObjectName("undoBtn")
        self.btn_redo.setObjectName("undoBtn")
        self.btn_save.setObjectName("saveBtn")
        self.btn_undo.setFixedHeight(46)
        self.btn_redo.setFixedHeight(46)
        self.btn_save.setFixedHeight(46)
        self.btn_undo.setEnabled(False)
        self.btn_redo.setEnabled(False)
        self.btn_undo.clicked.connect(self.undo_requested)
        self.btn_redo.clicked.connect(self.redo_requested)
        self.btn_save.clicked.connect(self.save_requested)
        act.addWidget(self.btn_undo)
        act.addWidget(self.btn_redo)
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

    def _tool_btn(self, icon, label):
        b = QPushButton(f"{icon}\n{label}")
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
        if tool in DrawTool.ERASERS:
            self.state.eraser_tool = tool
        if tool == DrawTool.LINE:
            self.slider_brush.setValue(DEFAULT_BRUSH_LINE)
        elif tool == DrawTool.POLY:
            self.slider_brush.setValue(DEFAULT_BRUSH_POLY)
        elif tool == DrawTool.ERASER:
            self.slider_brush.setValue(DEFAULT_BRUSH_ERASER)
        self._update_tool_controls(tool)
        self.tool_changed.emit(tool)

    def _on_eraser_changed(self, index):
        tool = self.combo_eraser.itemData(index)
        if tool in DrawTool.ERASERS:
            self._on_tool(tool)

    def _update_tool_controls(self, tool):
        editing_polygon = tool == DrawTool.EDIT_POLY
        sampled_filling = tool == DrawTool.SAMPLE_FILL
        auto_filling = tool == DrawTool.AUTO_FILL or sampled_filling
        area_erasing = tool in DrawTool.AREA_ERASERS
        self.eraser_controls.setVisible(tool in DrawTool.ERASERS)
        selected_eraser = tool if tool in DrawTool.ERASERS else self.state.eraser_tool
        self.combo_eraser.blockSignals(True)
        self.combo_eraser.setCurrentIndex(self.combo_eraser.findData(selected_eraser))
        self.combo_eraser.blockSignals(False)
        self.lbl_size_section.setText("PIXEL SIMILARITY" if auto_filling else "BRUSH SIZE")
        self.size_separator.setVisible(not area_erasing)
        self.lbl_size_section.setVisible(not area_erasing)
        self.slider_brush.setVisible(not auto_filling and not area_erasing)
        self.slider_brush.setEnabled(not editing_polygon)
        self.slider_similarity.setVisible(auto_filling)
        if auto_filling:
            tolerance = (
                self.state.sample_fill_tolerance if sampled_filling else self.state.fill_tolerance
            )
            was_blocked = self.slider_similarity.blockSignals(True)
            self.slider_similarity.setValue(tolerance)
            self.slider_similarity.blockSignals(was_blocked)
            self.slider_similarity.setToolTip(
                "像素与最近 Lab 颜色中心的距离上限" if sampled_filling else ""
            )
        self.lbl_polygon_hint.setVisible(editing_polygon)
        self.lbl_auto_fill_hint.setVisible(tool == DrawTool.AUTO_FILL)
        self.sample_fill_controls.setVisible(sampled_filling)
        if sampled_filling:
            self.set_sample_fill_status()
        self.lbl_eraser_hint.setVisible(area_erasing)
        if area_erasing:
            self.lbl_eraser_hint.setText(
                "按住左键从一个角拖到对角，松开后擦除矩形框内的标注。"
                if tool == DrawTool.RECT_ERASER else
                "像面状笔一样按住左键沿边界拖动，松开后自动闭合并擦除内部标注。"
            )

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
            QSpinBox {{
                background: {bg_input}; color: {text_primary};
                border: 1px solid {border_col}; border-radius: 4px;
                padding: 2px 4px; font-size: 11px;
            }}
            QLabel#statsLabel   {{ color: {t['text_muted']}; }}
            QFrame#panelSep     {{ color: {t['sep']}; max-height:1px; }}

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

    def set_redo_enabled(self, v):
        self.btn_redo.setEnabled(v)

    def update_shortcuts(self, bindings):
        def key(action):
            return action_shortcut_text(bindings, action)

        def compact(button, text, width):
            return button.fontMetrics().elidedText(text, Qt.ElideRight, width)

        for button, label, action in (
            (self.btn_undo, "↩  撤销", "undo"),
            (self.btn_redo, "↪  重做", "redo"),
            (self.btn_save, "💾  保存", "save"),
        ):
            hint = compact(button, key(action), 74)
            button.setText(f"{label}\n{hint}")
            button.setToolTip(f"{label} ({key(action)})")
        self.lbl_auto_fill_hint.setText(
            "单击原图中的一点，自动填充与该点颜色相近且相连的区域。"
            "自动连接 1–2 像素细缝并填满内部空洞。"
            "遇到已有标注停止扩张，不穿过或覆盖已有多边形。"
            "单击已有多边形则按其原类别补齐内部空点、孔洞及细缝。"
            f"阈值越大，纳入的颜色范围越广；每次填充均可 {key('undo')} 撤销。")

    # 注意这里，保留这个空函数防止 MainWindow 报错
    def show_line_hint(self, v):
        pass

    def set_tool_btn(self, tool):
        if tool == DrawTool.LINE:
            self.btn_line.setChecked(True)
        elif tool == DrawTool.POLY:
            self.btn_poly.setChecked(True)
        elif tool in DrawTool.ERASERS:
            self.btn_eraser.setChecked(True)
        elif tool == DrawTool.EDIT_POLY:
            self.btn_edit_poly.setChecked(True)
        elif tool == DrawTool.AUTO_FILL:
            self.btn_auto_fill.setChecked(True)
        elif tool == DrawTool.SAMPLE_FILL:
            self.btn_sample_fill.setChecked(True)
        self._update_tool_controls(tool)

    def set_sample_fill_status(self, filled_count: int | None = None):
        sampled = self.state.fill_sample is not None
        self.btn_resample.setEnabled(sampled)
        if not sampled:
            hint = "按住左键沿样本边界拖动，松开后自动闭合取样。"
        elif filled_count is None:
            if self.state.fill_freehand:
                hint = "已取样。沿填充范围的边界拖动，松开后自动闭合并填充。"
            else:
                hint = "已取样。拖出矩形范围，松开后填充最大的相似连通区域。"
        elif filled_count:
            hint = f"已填充 {filled_count} 个像素，可继续选择范围。"
        else:
            hint = "选区内没有可填充的连通区域。可调整阈值后重选范围。"
        self.lbl_sample_fill_hint.setText(hint)

    def set_brush_value(self, value):
        self.slider_brush.setValue(value)

    def set_similarity_value(self, value):
        self.slider_similarity.setValue(value)

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
