# ui/main_window.py
"""
主窗口 —— 简洁查看 + 悬浮编辑面板，支持夜间/白天主题切换，自适应 DPI。
"""

import os
import cv2
import numpy as np

from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QFileDialog, QSpinBox,
    QMessageBox, QFrame, QApplication, QSizePolicy, QToolButton,
    QListView, QMenu
)
from PyQt5.QtCore import Qt, QRect, QPoint, QEvent, QSettings
from PyQt5.QtGui import QImage, QPixmap, QColor, QPalette, QFontMetrics, QFont, QScreen

from core import (
    AnnotationState, DrawEngine, DrawTool, PolygonEditor, VALID_IMAGE_EXTS,
    similarity_fill_target,
)
from utils import (imread_unicode, imwrite_unicode, scan_images,
                   find_mask_paths, mask_save_path, MaskIndex,
                   mask_to_overlay_rgba, adjust_brightness_contrast,
                   class_pixel_stats_str)
from ui.graphics_view import InteractiveGraphicsView
from ui.edit_panel import EditPanel
from ui.settings_dialog import SettingsDialog, IMAGE_FILTER_OPTIONS
from ui.theme import THEMES, build_main_style


def _btn(text, obj_name, checkable=False, tooltip=""):
    b = QPushButton(text)
    b.setObjectName(obj_name)
    b.setCheckable(checkable)
    if tooltip:
        b.setToolTip(tooltip)
    return b


def _hline():
    f = QFrame()
    f.setObjectName("hline")
    f.setFrameShape(QFrame.HLine)
    return f

class ResizeHandle(QWidget):
    """无边框窗口的透明边缘拖动区域。"""

    def __init__(self, window, edges, cursor):
        super().__init__(window)
        self.window = window
        self.edges = edges
        self.setCursor(cursor)
        self._start_pos = None
        self._start_geometry = None

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and not self.window.isMaximized():
            self._start_pos = event.globalPos()
            self._start_geometry = self.window.geometry()
            event.accept()

    def mouseMoveEvent(self, event):
        if self._start_pos is None:
            return
        delta = event.globalPos() - self._start_pos
        rect = QRect(self._start_geometry)
        minimum = self.window.minimumSizeHint().expandedTo(self.window.minimumSize())
        min_width = max(1, minimum.width())
        min_height = max(1, minimum.height())
        if self.edges & Qt.LeftEdge:
            rect.setLeft(min(rect.right() - min_width + 1,
                             max(rect.right() - self.window.maximumWidth() + 1,
                                 rect.left() + delta.x())))
        if self.edges & Qt.RightEdge:
            rect.setWidth(max(min_width, min(self.window.maximumWidth(),
                                            rect.width() + delta.x())))
        if self.edges & Qt.TopEdge:
            rect.setTop(min(rect.bottom() - min_height + 1,
                            max(rect.bottom() - self.window.maximumHeight() + 1,
                                rect.top() + delta.y())))
        if self.edges & Qt.BottomEdge:
            rect.setHeight(max(min_height, min(self.window.maximumHeight(),
                                              rect.height() + delta.y())))
        self.window.setGeometry(rect)
        event.accept()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._start_pos = None
            self._start_geometry = None
            event.accept()


class DraggableTopBar(QWidget):
    """自定义的可拖拽顶部栏"""
    def __init__(self, parent_window):
        super().__init__(parent_window)
        self.parent_window = parent_window
        self._is_tracking = False
        self._start_pos = QPoint()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._is_tracking = True
            self._start_pos = event.globalPos() - self.parent_window.pos()
            event.accept()

    def mouseMoveEvent(self, event):
        if self._is_tracking and event.buttons() == Qt.LeftButton:
            # 如果处于最大化状态且拖动了，先还原窗口再拖动
            if self.parent_window.isMaximized():
                self.parent_window.showNormal()
                # 重新计算起始点，防止鼠标瞬间飞到边角
                self._start_pos = event.globalPos() - self.parent_window.pos()
            self.parent_window.move(event.globalPos() - self._start_pos)
            event.accept()

    def mouseReleaseEvent(self, event):
        self._is_tracking = False
        event.accept()

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.parent_window._toggle_maximize()
            event.accept()


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Mask Annotator")

        self.setWindowFlags(
            Qt.FramelessWindowHint | Qt.WindowSystemMenuHint
            | Qt.WindowMinimizeButtonHint | Qt.WindowMaximizeButtonHint)

        # ── 核心数据 ──
        self.state  = AnnotationState()
        self.engine = DrawEngine(self.state)
        self.polygon_editor = PolygonEditor()
        self._settings = QSettings("MaskAnnotator", "MaskAnnotator")
        self.recursive_search = self._settings.value("recursive_search", False, type=bool)
        self.preserve_mask_structure = self._settings.value(
            "preserve_mask_structure", False, type=bool)
        self.image_filter = self._settings.value("image_filter", "all", type=str)
        if self.image_filter not in dict(IMAGE_FILTER_OPTIONS):
            self.image_filter = "all"
        self._mask_index = None

        self._last_pen_tool = DrawTool.LINE
        self._last_pen_size = 3

        self.orig_folder:  str       = ""
        self.mask_folder:  str       = ""
        self.image_files:  list[str] = []
        self._all_image_files: list[str] = []
        self.current_index: int      = -1
        self._cursor_pos             = None
        self.edit_panel: EditPanel | None = None

        # ── 主题 ──
        self._theme_name = "light"

        self._build_ui()
        self._resize_handles = [
            ResizeHandle(self, edges, cursor)
            for edges, cursor in (
                (Qt.LeftEdge, Qt.SizeHorCursor),
                (Qt.RightEdge, Qt.SizeHorCursor),
                (Qt.TopEdge, Qt.SizeVerCursor),
                (Qt.BottomEdge, Qt.SizeVerCursor),
                (Qt.TopEdge | Qt.LeftEdge, Qt.SizeFDiagCursor),
                (Qt.TopEdge | Qt.RightEdge, Qt.SizeBDiagCursor),
                (Qt.BottomEdge | Qt.LeftEdge, Qt.SizeBDiagCursor),
                (Qt.BottomEdge | Qt.RightEdge, Qt.SizeFDiagCursor),
            )
        ]
        self._apply_theme()
        self._adapt_to_screen()
        self._update_resize_handles()
        self._restore_folders()

    def _update_resize_handles(self):
        if not hasattr(self, "_resize_handles"):
            return
        margin = 6
        width, height = self.width(), self.height()
        rects = (
            QRect(0, margin, margin, max(0, height - 2 * margin)),
            QRect(width - margin, margin, margin, max(0, height - 2 * margin)),
            QRect(margin, 0, max(0, width - 2 * margin), margin),
            QRect(margin, height - margin, max(0, width - 2 * margin), margin),
            QRect(0, 0, margin, margin),
            QRect(width - margin, 0, margin, margin),
            QRect(0, height - margin, margin, margin),
            QRect(width - margin, height - margin, margin, margin),
        )
        for handle, rect in zip(self._resize_handles, rects):
            handle.setGeometry(rect)
            handle.setVisible(not (self.isMaximized() or self.isFullScreen()))
            handle.raise_()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_resize_handles()

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() == QEvent.WindowStateChange:
            self._update_resize_handles()

    # ──────────────────────────────────────────────────────────────────────────
    # 自适应屏幕
    # ──────────────────────────────────────────────────────────────────────────
    def _adapt_to_screen(self):
        screen: QScreen = QApplication.primaryScreen()
        geo = screen.availableGeometry()
        # 占可用区域 90%
        w = int(geo.width()  * 0.90)
        h = int(geo.height() * 0.90)
        self.resize(w, h)
        # 居中
        self.move(
            geo.left() + (geo.width()  - w) // 2,
            geo.top()  + (geo.height() - h) // 2,
        )
        # 根据 DPI 调整字体
        dpi = screen.logicalDotsPerInch()
        if dpi > 144:          # 200% 缩放
            base_font_size = 13
        elif dpi > 120:        # 150% 缩放
            base_font_size = 12
        else:                  # 100%
            base_font_size = 11
        font = QFont()
        font.setPixelSize(base_font_size)
        QApplication.setFont(font)

    # ──────────────────────────────────────────────────────────────────────────
    # UI 构建
    # ──────────────────────────────────────────────────────────────────────────
    def _build_ui(self):
        root = QWidget()
        root.setObjectName("root")
        self.setCentralWidget(root)
        ml = QVBoxLayout(root)
        ml.setContentsMargins(0, 0, 0, 0)
        ml.setSpacing(0)

        # ══ 顶部工具栏 ════════════════════════════════════════════════════════
        top_bar = DraggableTopBar(self)  # 👇 使用刚刚创建的可拖拽组件
        top_bar.setObjectName("topBar")
        top_bar.setFixedHeight(50)
        tb = QHBoxLayout(top_bar)
        tb.setContentsMargins(16, 6, 8, 6)  # 右侧边距改小一点，给关闭按钮留空间
        tb.setSpacing(10)

        # App 名称
        lbl_app = QLabel("MASK  ANNOTATOR")
        lbl_app.setObjectName("appTitle")
        lbl_app.setStyleSheet(
            "font-size:14px; font-weight:bold; letter-spacing:2px; "
            "font-family:'Segoe UI', 'Microsoft YaHei', sans-serif;")
        tb.addWidget(lbl_app)

        # 竖分隔
        def _vdiv():
            d = QLabel("|")
            d.setObjectName("divider")
            return d

        tb.addWidget(_vdiv())

        # 文件夹按钮
        self.btn_orig = _btn("📂  原图文件夹", "folderBtn",
                             tooltip="选择原始图像所在文件夹")
        self.btn_mask_folder = _btn("📂  掩膜文件夹", "folderBtn",
                                    tooltip="选择掩膜文件保存文件夹")
        self.btn_orig.clicked.connect(self._load_orig_folder)
        self.btn_mask_folder.clicked.connect(self._load_mask_folder)
        tb.addWidget(self.btn_orig)
        tb.addWidget(self.btn_mask_folder)

        self.lbl_orig = QLabel("未选择")
        self.lbl_orig.setObjectName("pathLabel")
        self.lbl_orig.setMaximumWidth(220)
        self.lbl_orig.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        self.lbl_mask_path = QLabel("未选择")
        self.lbl_mask_path.setObjectName("pathLabel")
        self.lbl_mask_path.setMaximumWidth(220)
        tb.addWidget(self.lbl_orig)
        tb.addWidget(self.lbl_mask_path)

        tb.addStretch()

        self.btn_settings = _btn("⚙  设置", "settingsBtn", tooltip="文件查找与掩膜保存设置")
        self.btn_settings.clicked.connect(self._open_settings)
        tb.addWidget(self.btn_settings)

        # 主题切换
        self.btn_theme = _btn("☀  日间模式", "themeBtn", tooltip="切换亮色/暗色主题")
        self.btn_theme.clicked.connect(self._toggle_theme)
        tb.addWidget(self.btn_theme)

        tb.addWidget(_vdiv())

        # 掩膜显示
        self.btn_mask_vis = _btn("◑  掩膜叠加", "maskBtn",
                                  checkable=True, tooltip="切换掩膜显示 (W)")
        self.btn_mask_vis.setChecked(True)
        self.btn_mask_vis.clicked.connect(self._toggle_mask_visible)
        tb.addWidget(self.btn_mask_vis)

        # 编辑开关
        self.btn_edit = _btn("✏  开启编辑", "editBtn",
                              checkable=True, tooltip="打开/关闭标注编辑面板")
        self.btn_edit.clicked.connect(self._toggle_edit)
        tb.addWidget(self.btn_edit)

        tb.addSpacing(10)
        tb.addWidget(_vdiv())

        self.btn_min = QToolButton()
        self.btn_min.setText("—")
        self.btn_min.setObjectName("winCtrlBtn")
        self.btn_min.clicked.connect(self.showMinimized)

        self.btn_max = QToolButton()
        self.btn_max.setText("🗖")
        self.btn_max.setObjectName("winCtrlBtn")
        self.btn_max.clicked.connect(self._toggle_maximize)

        self.btn_close = QToolButton()
        self.btn_close.setText("✕")
        self.btn_close.setObjectName("winCloseBtn")
        self.btn_close.clicked.connect(self.close)

        tb.addWidget(self.btn_min)
        tb.addWidget(self.btn_max)
        tb.addWidget(self.btn_close)

        ml.addWidget(top_bar)

        # ══ 图像视图 ══════════════════════════════════════════════════════════
        self.viewer = InteractiveGraphicsView()
        self.viewer.press_signal.connect(self._on_press)
        self.viewer.move_signal.connect(self._on_move)
        self.viewer.release_signal.connect(self._on_release)
        self.viewer.dbl_click_signal.connect(self._on_dbl_click)
        self.viewer.hover_signal.connect(self._on_hover)
        self.viewer.context_menu_signal.connect(self._on_context_menu)
        ml.addWidget(self.viewer, 1)

        # ══ 底部导航栏 ════════════════════════════════════════════════════════
        btm = QWidget()
        btm.setObjectName("bottomBar")
        btm.setFixedHeight(54)
        bl = QHBoxLayout(btm)
        bl.setContentsMargins(16, 6, 16, 6)
        bl.setSpacing(8)

        self.btn_prev = _btn("◀  上一张", "navBtn", tooltip="上一张 (← / A)")
        self.btn_prev.setFixedWidth(96)
        self.btn_prev.setEnabled(False)
        self.btn_prev.clicked.connect(self._prev_image)

        self.lbl_info = QLabel("—  /  —")
        self.lbl_info.setObjectName("infoLabel")
        self.lbl_info.setAlignment(Qt.AlignCenter)
        self.lbl_info.setMinimumWidth(200)

        self.btn_next = _btn("下一张  ▶", "navBtn", tooltip="下一张 (→)")
        self.btn_next.setFixedWidth(96)
        self.btn_next.setEnabled(False)
        self.btn_next.clicked.connect(self._next_image)

        self.btn_save_next = _btn("💾  保存并下一张", "saveNextBtn",
                                  tooltip="保存当前掩膜并进入下一张 (D)")
        self.btn_save_next.setFixedWidth(144)
        self.btn_save_next.setEnabled(False)
        self.btn_save_next.clicked.connect(self._save_and_next)

        lbl_jump = QLabel("跳至")
        lbl_jump.setObjectName("jumpLabel")
        self.spin_jump = QSpinBox()
        self.spin_jump.setMinimum(1)
        self.spin_jump.setMaximum(1)
        self.spin_jump.setFixedWidth(68)
        btn_go = _btn("GO", "navBtn")
        btn_go.setFixedWidth(42)
        btn_go.clicked.connect(self._jump_to)

        bl.addWidget(self.btn_prev)
        bl.addWidget(self.lbl_info)
        bl.addWidget(self.btn_next)
        bl.addWidget(self.btn_save_next)
        bl.addSpacing(20)
        bl.addWidget(lbl_jump)
        bl.addWidget(self.spin_jump)
        bl.addWidget(btn_go)
        bl.addStretch()

        self.lbl_status = QLabel("")
        self.lbl_status.setObjectName("statusLabel")
        bl.addWidget(self.lbl_status)

        bl.addSpacing(20)

        self.btn_delete = _btn("🗑  删除", "deleteBtn",
                               tooltip="删除当前图及掩膜 (Del)")
        self.btn_delete.setFixedWidth(84)
        self.btn_delete.setEnabled(False)
        self.btn_delete.clicked.connect(self._delete_current)
        bl.addWidget(self.btn_delete)

        ml.addWidget(btm)

    def _toggle_maximize(self):
        if self.isMaximized():
            self.showNormal()
            self.btn_max.setText("🗖")
        else:
            self.showMaximized()
            self.btn_max.setText("🗗")

    # ──────────────────────────────────────────────────────────────────────────
    # 主题
    # ──────────────────────────────────────────────────────────────────────────
    def _apply_theme(self):
        t = THEMES[self._theme_name]
        self.setStyleSheet(build_main_style(t) + f"""
                    /* 全局按钮字体优化，解决发虚问题 */
                    QPushButton {{
                        font-family: "Microsoft YaHei", "Segoe UI", system-ui, sans-serif;
                        font-size: 13px;
                        font-weight: 600; /* 加粗使得在暗色背景下更加清晰 */
                        padding: 6px 14px;
                    }}
                    QLabel {{
                        font-family: "Microsoft YaHei", "Segoe UI", system-ui, sans-serif;
                    }}

                    QWidget#topBar {{
                        background: {t['bg_bar']};
                        border-bottom: 1px solid {t['bg_bar_border']};
                    }}
                    QWidget#bottomBar {{
                        background: {t['bg_bar']};
                        border-top: 1px solid {t['bg_bar_border']};
                    }}
                    QLabel#appTitle  {{ color: {t['text_accent']}; }}
                    QLabel#divider   {{ color: {t['border']}; font-size:16px; }}
                    QLabel#jumpLabel {{ color: {t['text_muted']}; font-size:12px; }}

                    /* 窗口控制按钮样式 */
                    QToolButton#winCtrlBtn, QToolButton#winCloseBtn {{
                        background: transparent;
                        border: none;
                        color: {t['text_primary']};
                        font-size: 14px;
                        width: 36px;
                        height: 30px;
                        border-radius: 4px;
                    }}
                    QToolButton#winCtrlBtn:hover {{
                        background: rgba(255, 255, 255, 0.1);
                    }}
                    QToolButton#winCloseBtn:hover {{
                        background: #E81123; /* 微软官方关闭红 */
                        color: white;
                    }}
                """)
        self.btn_theme.setText(t['theme_btn_text'])

        # 更新编辑面板主题
        if self.edit_panel:
            self.edit_panel.apply_theme(self._theme_name)

        # 更新调色板
        is_dark = (self._theme_name == "dark")
        pal = QPalette()
        pal.setColor(QPalette.Window,
                     QColor(t['bg_root']))
        pal.setColor(QPalette.WindowText,
                     QColor(t['text_primary']))
        self.setPalette(pal)

    def _toggle_theme(self):
        self._theme_name = "light" if self._theme_name == "dark" else "dark"
        self._apply_theme()

    # ──────────────────────────────────────────────────────────────────────────
    # 编辑面板
    # ──────────────────────────────────────────────────────────────────────────
    def _toggle_edit(self, checked: bool):
        if checked:
            self.btn_edit.setText("✏  关闭编辑")
            self._show_edit_panel()
            self.viewer.set_edit_mode()
            self.viewer.update_cursor_state(self.state.tool, self.state.brush_size)
        else:
            self.btn_edit.setText("✏  开启编辑")
            if self.edit_panel:
                self.edit_panel.hide()
            self.viewer.set_view_mode()
            was_active = self.engine.is_active
            self.engine.cancel()
            self.viewer.clear_stroke()
            self._clear_polygon_selection()
            if was_active and self.edit_panel:
                self.edit_panel.set_undo_enabled(self.state.can_undo())
            self._update_dirty_indicator()

    def _show_edit_panel(self):
        if self.edit_panel is None:
            self.edit_panel = EditPanel(self.state, self._theme_name, self)
            ep = self.edit_panel
            ep.tool_changed.connect(self._on_tool_changed)
            ep.brush_changed.connect(self._on_brush_changed)
            ep.similarity_changed.connect(self._on_similarity_changed)
            ep.class_changed.connect(self._on_ep_class)
            ep.alpha_changed.connect(lambda _: self._refresh_mask_overlay())
            ep.contour_changed.connect(lambda _: self._refresh_mask_overlay())
            ep.show_all_changed.connect(lambda _: self._refresh_mask_overlay())
            ep.brightness_changed.connect(lambda _: self._refresh_base_image())
            ep.contrast_changed.connect(lambda _: self._refresh_base_image())
            ep.undo_requested.connect(self._undo)
            ep.save_requested.connect(self._save_mask)
            ep.close_edit_requested.connect(
                lambda: (self.btn_edit.setChecked(False),
                         self._toggle_edit(False)))
            ep.classes_updated.connect(lambda _: self._refresh_mask_overlay())
            ep.refresh_classes()

        # 面板放在主窗口右侧内部，固定偏移
        geo = self.geometry()
        panel_w = self.edit_panel.width()
        px = geo.right() - panel_w - 24
        py = geo.top() + 70
        self.edit_panel.move(px, py)
        self.edit_panel.show()
        self.edit_panel.raise_()

    # ──────────────────────────────────────────────────────────────────────────
    # 视图事件
    # ──────────────────────────────────────────────────────────────────────────
    def _show_polygon_selection(self):
        self.viewer.set_polygon_edit(
            self.polygon_editor.vertices,
            active_index=self.polygon_editor.selected_vertex_index,
            outline_vertices=self.polygon_editor.outline_vertices,
        )

    def _on_press(self, x, y):
        mask = self.state.mask_img
        if mask is None or not (0 <= x < mask.shape[1] and 0 <= y < mask.shape[0]):
            return
        if self.state.tool == DrawTool.AUTO_FILL:
            self._auto_fill_at(int(x), int(y))
            return
        if self.state.tool == DrawTool.EDIT_POLY:
            scale = max(0.001, self.viewer.transform().m11())
            tolerance = min(50.0, 9.0 / scale)
            vertex = self.polygon_editor.hit_vertex(x, y, tolerance)
            if vertex is not None:
                self.polygon_editor.begin_drag(x, y, vertex)
                self._show_polygon_selection()
                return
            if self.polygon_editor.contains(x, y) or (
                mask[int(y), int(x)] == 0 and self.polygon_editor.hit_edge(x, y, tolerance)
            ):
                self.polygon_editor.begin_drag(x, y, None)
                self._show_polygon_selection()
                return
            if self.polygon_editor.select(mask, int(x), int(y)):
                self._show_polygon_selection()
                for index, cls in enumerate(self.state.classes):
                    if int(cls["value"]) == self.polygon_editor.value:
                        if self.edit_panel:
                            self.edit_panel.set_class_index(index)
                        break
            else:
                self.viewer.clear_polygon_edit()
            return
        x, y = int(x), int(y)
        self.engine.on_press(x, y)
        info = self.state.current_class_info
        b, g, r = info["color"] if info else (255, 255, 255)
        alpha = self.edit_panel.alpha_value() if self.edit_panel else 50
        self.viewer.begin_stroke(
            x, y, self.state.tool, QColor(r, g, b, max(80, int(alpha * 2.55))),
            self.state.brush_size,
        )
        if self.edit_panel:
            self.edit_panel.set_undo_enabled(self.state.can_undo())
        self._update_dirty_indicator()

    def _on_move(self, x, y):
        if self.state.tool == DrawTool.EDIT_POLY and self.polygon_editor.is_dragging:
            mask = self.state.mask_img
            if mask is not None:
                self.polygon_editor.drag_to(x, y, mask.shape[:2])
                self._show_polygon_selection()
            return
        if not self.engine.is_active:
            return
        x, y = int(x), int(y)
        self.engine.on_move(x, y)
        self.viewer.extend_stroke(x, y)

    def _on_release(self, x, y):
        if self.state.tool == DrawTool.EDIT_POLY and self.polygon_editor.is_dragging:
            if self.polygon_editor.drag_changed():
                self.state.push_undo()
                self.state.mark_modified()
                self.polygon_editor.apply(self.state.mask_img)
                self._show_polygon_selection()
                self._finish_stroke_update()
            else:
                self.polygon_editor.cancel_drag()
                self._show_polygon_selection()
            return
        if not self.engine.is_active:
            return
        self.engine.on_release(int(x), int(y))
        self.viewer.clear_stroke()
        self._finish_stroke_update()

    def _on_dbl_click(self, x, y):
        if self.state.tool != DrawTool.EDIT_POLY:
            return
        self.polygon_editor.cancel_drag()
        scale = max(0.001, self.viewer.transform().m11())
        tolerance = min(50.0, 9.0 / scale)
        self.polygon_editor.insert_vertex(x, y, tolerance)
        self._show_polygon_selection()

    def _on_hover(self, x, y):
        self._cursor_pos = (x, y)

    def _auto_fill_at(self, x: int, y: int):
        image = self.state.orig_img
        mask = self.state.mask_img
        if image is None or mask is None:
            return
        region, value = similarity_fill_target(
            image, mask, x, y, self.state.current_draw_value, self.state.fill_tolerance
        )
        if not np.any(region & (mask != value)):
            return
        self.state.push_undo()
        mask[region] = value
        self.state.mark_modified()
        self._finish_stroke_update()

    def _on_context_menu(self, x, y, global_pos):
        if (
            self.state.tool != DrawTool.EDIT_POLY
            or not self.polygon_editor.has_selection
        ):
            return
        scale = max(0.001, self.viewer.transform().m11())
        tolerance = min(50.0, 9.0 / scale)
        hit_vertex = self.polygon_editor.hit_vertex(x, y, tolerance)
        selected_vertex = self.polygon_editor.selected_vertex_index
        menu = QMenu(self)
        if hit_vertex is not None and hit_vertex == selected_vertex:
            delete_action = menu.addAction("删除控制点\tCtrl+D")
            delete_action.setEnabled(len(self.polygon_editor.vertices) > 3)
            if menu.exec_(global_pos) == delete_action:
                self._delete_selected_vertex()
        elif self.polygon_editor.contains(x, y):
            delete_action = menu.addAction("删除多边形\tCtrl+D")
            if menu.exec_(global_pos) == delete_action:
                self._delete_selected_polygon()

    def _delete_selection(self):
        if self.polygon_editor.selected_vertex_index is not None:
            self._delete_selected_vertex()
        else:
            self._delete_selected_polygon()

    def _on_ep_class(self, idx):
        if self.engine.is_active:
            self.engine.cancel()
            self.viewer.clear_stroke()
        changed = idx != self.state.current_class
        self.state.current_class = idx
        if changed or (self.edit_panel and not self.edit_panel.show_all_checked()):
            self._refresh_mask_overlay()
        self._update_dirty_indicator()

    def _on_tool_changed(self, tool):
        was_active = self.engine.is_active
        self.engine.cancel()
        self.viewer.clear_stroke()
        self._clear_polygon_selection()
        self.state.tool = tool
        self.viewer.update_cursor_state(tool, self.state.brush_size)
        if was_active and self.edit_panel:
            self.edit_panel.set_undo_enabled(self.state.can_undo())
        self._update_dirty_indicator()

    def _on_brush_changed(self, value):
        was_active = self.engine.is_active
        self.engine.cancel()
        self.viewer.clear_stroke()
        self.state.brush_size = value
        self.viewer.update_cursor_state(self.state.tool, value)
        if was_active and self.edit_panel:
            self.edit_panel.set_undo_enabled(self.state.can_undo())
        self._update_dirty_indicator()

    def _on_similarity_changed(self, value):
        self.state.fill_tolerance = value

    def _refresh_stats(self):
        if self.edit_panel:
            self.edit_panel.set_undo_enabled(self.state.can_undo())
            self.edit_panel.set_stats(
                class_pixel_stats_str(self.state.mask_img, self.state.classes))

    def _finish_stroke_update(self):
        self._refresh_mask_overlay()
        self._refresh_stats()
        self._update_dirty_indicator()

    # 保留方法名以兼容旧调用；它只用于一笔结束后的更新。
    def _post_draw(self):
        self._finish_stroke_update()

    def _update_dirty_indicator(self):
        if not self.image_files or self.current_index < 0:
            return
        filename = self.image_files[self.current_index]
        if self.state.is_dirty:
            t = THEMES[self._theme_name]
            self.lbl_status.setText("● 当前标注尚未保存")
            self.lbl_status.setStyleSheet(
                f"color:{t['text_accent']}; font-size:11px; font-weight:600;")
            self.setWindowTitle(f"Mask Annotator  ·  {filename}  *")
        else:
            has_mask = bool(
                self.mask_folder
                and self._find_mask_paths(filename)
            )
            t = THEMES[self._theme_name]
            self.lbl_status.setText(
                "✓ 当前掩膜已保存" if has_mask else "○ 当前图像还没有掩膜"
            )
            self.lbl_status.setStyleSheet(
                f"color:{t['status_ok'] if has_mask else t['text_muted']}; font-size:11px;"
            )
            self.setWindowTitle(f"Mask Annotator  ·  {filename}")

    def _confirm_save_if_dirty(self) -> bool:
        """在切换图像、文件夹或退出前保护未保存标注。"""
        if not self.state.is_dirty:
            return True
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Warning)
        box.setWindowTitle("尚未保存")
        box.setText("当前图像的标注尚未保存。")
        box.setInformativeText("保存后继续，还是放弃本次修改？")
        save_btn = box.addButton("保存", QMessageBox.AcceptRole)
        discard_btn = box.addButton("放弃修改", QMessageBox.DestructiveRole)
        box.addButton("取消", QMessageBox.RejectRole)
        box.setDefaultButton(save_btn)
        box.exec_()
        clicked = box.clickedButton()
        if clicked == save_btn:
            return self._save_mask()
        return clicked == discard_btn

    # ──────────────────────────────────────────────────────────────────────────
    # 显示刷新
    # ──────────────────────────────────────────────────────────────────────────
    def _refresh_base_image(self, reset_zoom=False, *args):
        if self.state.orig_img is None:
            return
        ep = self.edit_panel
        brightness = ep.brightness_value() if ep and ep.isVisible() else 0
        contrast   = ep.contrast_value()   if ep and ep.isVisible() else 100

        img = adjust_brightness_contrast(
            self.state.orig_img,
            brightness=brightness,
            contrast=contrast / 100.0
        )

        rgb  = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb.shape
        qimg = QImage(rgb.data, w, h, ch * w, QImage.Format_RGB888)
        px   = QPixmap.fromImage(qimg)

        if reset_zoom:
            self.viewer.set_image(px)
        else:
            self.viewer.update_image(px)
        self._update_dirty_indicator()

    def _refresh_mask_overlay(self):
        if self.state.mask_img is None:
            self.viewer.set_overlay(QPixmap())
            return
        ep = self.edit_panel
        alpha = ep.alpha_value() / 100.0 if ep else 0.5
        contour = ep.contour_checked() if ep else True
        show_all = ep.show_all_checked() if ep else True
        rgba = mask_to_overlay_rgba(
            self.state.mask_img,
            self.state.classes,
            alpha=alpha,
            show_all=show_all,
            current_class_idx=self.state.current_class,
            show_contour=contour,
        )
        if rgba is None:
            self.viewer.set_overlay(QPixmap())
        else:
            h, w, _ = rgba.shape
            qimg = QImage(rgba.data, w, h, 4 * w, QImage.Format_RGBA8888)
            self.viewer.set_overlay(QPixmap.fromImage(qimg))
        self.viewer.set_overlay_visible(self.state.is_mask_visible)

    def _refresh_display(self, reset_zoom=False, *args):
        """完整刷新只在加载图像等低频场景使用。"""
        self._refresh_base_image(reset_zoom=reset_zoom)
        self._refresh_mask_overlay()

    # ──────────────────────────────────────────────────────────────────────────
    # 掩膜可见切换
    # ──────────────────────────────────────────────────────────────────────────
    def _toggle_mask_visible(self):
        self.state.is_mask_visible = self.btn_mask_vis.isChecked()
        self.viewer.set_overlay_visible(self.state.is_mask_visible)

    # ──────────────────────────────────────────────────────────────────────────
    # 撤销 / 折线
    # ──────────────────────────────────────────────────────────────────────────
    def _undo(self):
        if self.state.pop_undo():
            self._clear_polygon_selection()
            if self.edit_panel:
                self.edit_panel.set_undo_enabled(self.state.can_undo())
            self.viewer.clear_stroke()
            self._refresh_mask_overlay()
            self._refresh_stats()
            self._update_dirty_indicator()

    def _commit_line(self):
        if self.engine.is_active and self._cursor_pos is not None:
            self.engine.on_release(*self._cursor_pos)
        self.viewer.clear_stroke()
        self._post_draw()

    def _cancel_line(self):
        if self.polygon_editor.is_dragging:
            self.polygon_editor.cancel_drag()
            self._show_polygon_selection()
            return
        self.engine.cancel()
        self.viewer.clear_stroke()
        if self.edit_panel:
            self.edit_panel.set_undo_enabled(self.state.can_undo())
        self._update_dirty_indicator()

    def _clear_polygon_selection(self):
        self.polygon_editor.clear()
        self.viewer.clear_polygon_edit()

    def _delete_selected_polygon(self):
        mask = self.state.mask_img
        if (
            self.state.tool != DrawTool.EDIT_POLY
            or mask is None
            or not self.polygon_editor.has_selection
        ):
            return
        self.state.push_undo()
        if not self.polygon_editor.delete(mask):
            return
        self.state.mark_modified()
        self.viewer.clear_polygon_edit()
        self._finish_stroke_update()

    def _delete_selected_vertex(self):
        mask = self.state.mask_img
        if (
            self.state.tool != DrawTool.EDIT_POLY
            or mask is None
            or self.polygon_editor.selected_vertex_index is None
            or len(self.polygon_editor.vertices) <= 3
        ):
            return
        self.state.push_undo()
        self.polygon_editor.delete_selected_vertex()
        self.state.mark_modified()
        self.polygon_editor.apply(mask)
        self._show_polygon_selection()
        self._finish_stroke_update()

    # ──────────────────────────────────────────────────────────────────────────
    # 文件夹 & 图片
    # ──────────────────────────────────────────────────────────────────────────
    def _open_settings(self):
        dialog = SettingsDialog(self.recursive_search, self.preserve_mask_structure,
                                self._theme_name, self, image_filter=self.image_filter)

        def save():
            if self._apply_folder_settings(*dialog.values()):
                dialog.accept()

        dialog.save_requested.connect(save)
        dialog.exec_()
        dialog.deleteLater()

    def _apply_folder_settings(self, recursive_search, preserve_mask_structure,
                               image_filter=None):
        image_filter = self.image_filter if image_filter is None else image_filter
        if image_filter not in dict(IMAGE_FILTER_OPTIONS):
            image_filter = "all"
        if (recursive_search, preserve_mask_structure, image_filter) == (
                self.recursive_search, self.preserve_mask_structure, self.image_filter):
            return True
        if not self._confirm_save_if_dirty():
            return False
        self.recursive_search = recursive_search
        self.preserve_mask_structure = preserve_mask_structure
        self.image_filter = image_filter
        self._settings.setValue("recursive_search", recursive_search)
        self._settings.setValue("preserve_mask_structure", preserve_mask_structure)
        self._settings.setValue("image_filter", image_filter)
        self._settings.sync()
        self._scan_images()
        return True

    def _rebuild_mask_index(self):
        self._mask_index = (MaskIndex(self.mask_folder, VALID_IMAGE_EXTS,
                                      self.recursive_search)
                            if self.mask_folder else None)

    def _find_mask_paths(self, filename):
        if not self.mask_folder:
            return []
        return find_mask_paths(self.mask_folder, filename, VALID_IMAGE_EXTS,
                               self.recursive_search, self.preserve_mask_structure,
                               self._mask_index)

    def _set_folder(self, name: str, folder: str):
        folder = os.path.abspath(folder)
        setattr(self, name, folder)
        label = self.lbl_orig if name == "orig_folder" else self.lbl_mask_path
        label.setText(f"📁 {os.path.basename(folder) or folder}")
        label.setToolTip(folder)
        t = THEMES[self._theme_name]
        label.setStyleSheet(f"color:{t['text_accent']}; font-size:11px;")
        self._settings.setValue(name, folder)
        self._settings.sync()

    def _restore_folders(self):
        for name in ("orig_folder", "mask_folder"):
            folder = self._settings.value(name, "", type=str)
            if folder and os.path.isdir(folder):
                self._set_folder(name, folder)
        self._scan_images()

    def _load_orig_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "选择原图文件夹")
        if folder and self._confirm_save_if_dirty():
            self._set_folder("orig_folder", folder)
            self._scan_images()

    def _load_mask_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "选择掩膜文件夹")
        if folder and self._confirm_save_if_dirty():
            self._set_folder("mask_folder", folder)
            self._scan_images()

    def _scan_images(self):
        self._rebuild_mask_index()
        if not self.orig_folder:
            return
        self._all_image_files = scan_images(
            self.orig_folder, VALID_IMAGE_EXTS, self.recursive_search)
        self._update_image_list()

    def _update_image_list(self, preferred_filename=None, fallback_index=0):
        if self.image_filter == "all":
            self.image_files = self._all_image_files.copy()
        else:
            want_mask = self.image_filter == "with_mask"
            self.image_files = [filename for filename in self._all_image_files
                                if bool(self._find_mask_paths(filename)) == want_mask]
        total = len(self.image_files)
        self.spin_jump.setMaximum(max(1, total))
        if self.image_files:
            self.current_index = max(0, min(fallback_index, total - 1))
            last_image_path = self._settings.value("last_image_path", "", type=str)
            if preferred_filename is not None:
                last_filename = os.path.normcase(preferred_filename)
            elif last_image_path and os.path.isfile(last_image_path):
                try:
                    last_filename = os.path.normcase(os.path.relpath(
                        last_image_path, self.orig_folder))
                except ValueError:  # 上次图像位于另一盘符。
                    last_filename = None
            else:
                last_filename = None
            for index, filename in enumerate(self.image_files):
                if os.path.normcase(filename) == last_filename:
                    self.current_index = index
                    break
            self._load_current_image()
        else:
            self.current_index = -1
            self.engine.cancel()
            self._clear_polygon_selection()
            self.state.orig_img = None
            self.state.mask_img = None
            self.state.undo_stack.clear()
            self.state.mark_saved()
            self.viewer.clear_image()
            self.lbl_info.setText("—  /  —")
            if not self._all_image_files:
                message = "所选原图文件夹中没有可支持的图像"
            elif self.image_filter == "with_mask" and not self.mask_folder:
                message = "请选择掩膜文件夹，以筛选有掩膜的图片"
            else:
                message = "没有符合当前显示范围的图片，可在设置中切换为全部图片"
            self.lbl_status.setText(message)
            self.lbl_status.setStyleSheet(
                f"color:{THEMES[self._theme_name]['text_muted']}; font-size:11px;")
            self.setWindowTitle("Mask Annotator")
            self.btn_prev.setEnabled(False)
            self.btn_next.setEnabled(False)
            self.btn_save_next.setEnabled(False)
            self.btn_delete.setEnabled(False)
            if self.edit_panel:
                self.edit_panel.set_undo_enabled(False)
                self.edit_panel.set_stats("")

    def _navigate_to(self, filename):
        # 保存可能使当前图片离开“无掩膜”列表，按文件名定位以免跳过下一张。
        if filename in self.image_files:
            index = self.image_files.index(filename)
            if index != self.current_index:
                self.current_index = index
                self._load_current_image()

    def _jump_to(self):
        idx = self.spin_jump.value() - 1
        if 0 <= idx < len(self.image_files) and idx != self.current_index:
            filename = self.image_files[idx]
            if self._confirm_save_if_dirty():
                self._navigate_to(filename)

    def _prev_image(self):
        if self.current_index > 0:
            filename = self.image_files[self.current_index - 1]
            if self._confirm_save_if_dirty():
                self._navigate_to(filename)

    def _next_image(self):
        if 0 <= self.current_index < len(self.image_files) - 1:
            filename = self.image_files[self.current_index + 1]
            if self._confirm_save_if_dirty():
                self._navigate_to(filename)

    def _save_and_next(self):
        next_filename = (self.image_files[self.current_index + 1]
                         if 0 <= self.current_index < len(self.image_files) - 1 else None)
        if self._save_mask() and next_filename is not None:
            self._navigate_to(next_filename)

    def _load_current_image(self):
        filename = self.image_files[self.current_index]
        total    = len(self.image_files)
        self.lbl_info.setText(
            f"{self.current_index + 1}  /  {total}    ·    {filename}")
        self.spin_jump.setValue(self.current_index + 1)

        orig_img = imread_unicode(os.path.join(self.orig_folder, filename))
        if orig_img is None:
            QMessageBox.warning(self, "加载失败",
                f"无法读取原图:\n{os.path.join(self.orig_folder, filename)}")
            return

        mask_img = None
        if self.mask_folder:
            paths = self._find_mask_paths(filename)
            mp = paths[0] if paths else None
            if mp:
                loaded = imread_unicode(mp, cv2.IMREAD_GRAYSCALE)
                if loaded is not None:
                    h, w = orig_img.shape[:2]
                    if loaded.shape[:2] != (h, w):
                        loaded = cv2.resize(loaded, (w, h),
                                            interpolation=cv2.INTER_NEAREST)
                    mask_img = loaded

        self.state.load_image_and_mask(orig_img, mask_img)
        self._clear_polygon_selection()
        self.engine.cancel()
        self.btn_delete.setEnabled(True)
        self.btn_prev.setEnabled(self.current_index > 0)
        self.btn_next.setEnabled(self.current_index < total - 1)
        self.btn_save_next.setEnabled(True)

        if self.edit_panel:
            self.edit_panel.set_undo_enabled(False)
            self.edit_panel.show_line_hint(False)
            self.edit_panel.set_stats(
                class_pixel_stats_str(self.state.mask_img, self.state.classes))

        t = THEMES[self._theme_name]
        has_mask = mask_img is not None
        status = (f"{'✓ 已有掩膜' if has_mask else '○ 无掩膜'}"
                  f"  ·  掩膜目录: {os.path.basename(self.mask_folder)}"
                  if self.mask_folder else "未选择掩膜文件夹")
        self.lbl_status.setText(status)
        self.lbl_status.setStyleSheet(
            f"color:{ t['status_ok'] if has_mask else t['text_muted'] }; font-size:11px;")
        self.setWindowTitle(f"Mask Annotator  ·  {filename}")
        self._refresh_display(reset_zoom=True)
        self._settings.setValue(
            "last_image_path", os.path.abspath(os.path.join(self.orig_folder, filename)))
        self._settings.sync()

    # ──────────────────────────────────────────────────────────────────────────
    # 保存 & 删除
    # ──────────────────────────────────────────────────────────────────────────
    def _save_mask(self) -> bool:
        if self.state.mask_img is None:
            QMessageBox.warning(self, "无法保存", "当前没有可保存的掩膜。")
            return False
        if not self.mask_folder:
            folder = QFileDialog.getExistingDirectory(self, "选择掩膜保存文件夹")
            if not folder:
                return False
            self._set_folder("mask_folder", folder)
            self._rebuild_mask_index()
        filename  = self.image_files[self.current_index]
        save_path = mask_save_path(
            self.mask_folder, filename, self.preserve_mask_structure)
        if imwrite_unicode(save_path, self.state.mask_img):
            if self._mask_index is not None:
                self._mask_index.add(save_path)
            self.state.mark_saved()
            stats = self.state.class_pixel_stats()
            s     = ", ".join(f"{n}:{c}px" for n, c in stats) or "全背景"
            t     = THEMES[self._theme_name]
            self.lbl_status.setText(
                f"✅ 已保存  {os.path.basename(save_path)}  [{s}]")
            self.lbl_status.setStyleSheet(
                f"color:{t['status_ok']}; font-size:11px;")
            self.setWindowTitle(
                f"Mask Annotator  ·  {filename}  ✓")
            if self.image_filter != "all":
                self._update_image_list(filename, self.current_index)
            return True
        QMessageBox.critical(self, "保存失败", f"无法写入:\n{save_path}")
        return False

    def _delete_current(self):
        if not self.image_files or self.current_index < 0:
            return
        filename  = self.image_files[self.current_index]
        orig_path = os.path.join(self.orig_folder, filename)
        reply = QMessageBox.question(
            self, "确认删除",
            f"永久删除以下文件及其掩膜？\n\n  {filename}\n\n此操作不可恢复。",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return
        try:
            if os.path.exists(orig_path):
                os.remove(orig_path)
        except Exception as e:
            QMessageBox.critical(self, "删除失败", str(e)); return

        if self.mask_folder:
            for path in self._find_mask_paths(filename):
                try:
                    if os.path.exists(path):
                        os.remove(path)
                except Exception:
                    pass
            self._rebuild_mask_index()

        self._all_image_files = [path for path in self._all_image_files if path != filename]
        self._update_image_list(filename, self.current_index)

    # ──────────────────────────────────────────────────────────────────────────
    # 快捷键
    # ──────────────────────────────────────────────────────────────────────────
    def keyPressEvent(self, event):
            key = event.key()
            mods = event.modifiers()
            ep_on = self.edit_panel and self.edit_panel.isVisible()

            if key in (Qt.Key_Left, Qt.Key_A):
                self._prev_image()
            elif key == Qt.Key_Right:
                self._next_image()
            elif key == Qt.Key_D and not (mods & Qt.ControlModifier):
                self._save_and_next()
            elif key == Qt.Key_W:
                vis = not self.state.is_mask_visible
                self.state.is_mask_visible = vis
                self.btn_mask_vis.setChecked(vis)
                self.viewer.set_overlay_visible(vis)

            elif ep_on and not (mods & Qt.AltModifier) and key == Qt.Key_1:
                self.engine.cancel()
                self.viewer.clear_stroke()
                self._clear_polygon_selection()
                self.edit_panel.set_tool_btn(DrawTool.LINE)
                self.state.tool = DrawTool.LINE
                self.state.brush_size = 3
                self.edit_panel.set_brush_value(3)
                self.viewer.update_cursor_state(self.state.tool, self.state.brush_size)

            elif ep_on and not (mods & Qt.AltModifier) and key == Qt.Key_2:
                self.engine.cancel()
                self.viewer.clear_stroke()
                self._clear_polygon_selection()
                self.edit_panel.set_tool_btn(DrawTool.POLY)
                self.state.tool = DrawTool.POLY
                self.state.brush_size = 1
                self.edit_panel.set_brush_value(1)
                self.viewer.update_cursor_state(self.state.tool, self.state.brush_size)

            elif ep_on and not (mods & Qt.AltModifier) and key in (Qt.Key_E, Qt.Key_3):
                self.engine.cancel()
                self.viewer.clear_stroke()
                self._clear_polygon_selection()

                if self.state.tool == DrawTool.ERASER:
                    self.state.tool = self._last_pen_tool
                    self.state.brush_size = self._last_pen_size
                    self.edit_panel.set_tool_btn(self.state.tool)
                    self.edit_panel.set_brush_value(self.state.brush_size)
                else:
                    self._last_pen_tool = self.state.tool
                    self._last_pen_size = self.state.brush_size
                    self.state.tool = DrawTool.ERASER
                    self.state.brush_size = 20
                    self.edit_panel.set_tool_btn(DrawTool.ERASER)
                    self.edit_panel.set_brush_value(20)

                self.viewer.update_cursor_state(self.state.tool, self.state.brush_size)

            elif ep_on and not (mods & Qt.AltModifier) and key == Qt.Key_4:
                self.engine.cancel()
                self.viewer.clear_stroke()
                self._clear_polygon_selection()
                self.edit_panel.set_tool_btn(DrawTool.EDIT_POLY)
                self.state.tool = DrawTool.EDIT_POLY
                self.viewer.update_cursor_state(self.state.tool, self.state.brush_size)

            elif ep_on and not (mods & Qt.AltModifier) and key == Qt.Key_5:
                self.engine.cancel()
                self.viewer.clear_stroke()
                self._clear_polygon_selection()
                self.edit_panel.set_tool_btn(DrawTool.AUTO_FILL)
                self.state.tool = DrawTool.AUTO_FILL
                self.viewer.update_cursor_state(self.state.tool, self.state.brush_size)

            elif key in (Qt.Key_Return, Qt.Key_Enter):
                if self.state.tool == DrawTool.LINE:
                    self._commit_line()
            elif key == Qt.Key_Escape:
                self._cancel_line()
            elif key in (Qt.Key_F, Qt.Key_0):
                self.viewer.fit_image()
            elif ep_on and key in (Qt.Key_BracketLeft, Qt.Key_BracketRight):
                delta = -1 if key == Qt.Key_BracketLeft else 1
                if self.state.tool == DrawTool.AUTO_FILL:
                    self.edit_panel.set_similarity_value(
                        max(0, min(100, self.state.fill_tolerance + delta)))
                else:
                    self.edit_panel.set_brush_value(
                        max(1, min(80, self.state.brush_size + delta)))
            elif ep_on and (mods & Qt.AltModifier) and Qt.Key_1 <= key <= Qt.Key_9:
                idx = key - Qt.Key_1
                if idx < len(self.state.classes):
                    self.edit_panel.set_class_index(idx)
            elif mods == Qt.ControlModifier and key == Qt.Key_S:
                self._save_mask()
            elif mods == Qt.ControlModifier and key == Qt.Key_Z:
                self._undo()
            elif mods == Qt.ControlModifier and key == Qt.Key_D:
                self._delete_selection()
            elif key == Qt.Key_Delete:
                self._delete_current()

    def closeEvent(self, event):
        if not self._confirm_save_if_dirty():
            event.ignore()
            return
        if self.edit_panel:
            self.edit_panel.close()
        super().closeEvent(event)
