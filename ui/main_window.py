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
    QListView
)
from PyQt5.QtCore import Qt, QRect, QPoint
from PyQt5.QtGui import QImage, QPixmap, QColor, QPalette, QFontMetrics, QFont, QScreen

from core import AnnotationState, DrawEngine, DrawTool, VALID_IMAGE_EXTS
from utils import (imread_unicode, imwrite_unicode, scan_images,
                   find_mask_path, mask_save_path,
                   blend_mask_on_image, adjust_brightness_contrast,
                   class_pixel_stats_str)
from ui.graphics_view import InteractiveGraphicsView
from ui.edit_panel import EditPanel
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
            Qt.FramelessWindowHint | Qt.WindowSystemMenuHint | Qt.WindowMinimizeButtonHint | Qt.WindowMaximizeButtonHint)

        # ── 核心数据 ──
        self.state  = AnnotationState()
        self.engine = DrawEngine(self.state)

        self._last_pen_tool = DrawTool.LINE
        self._last_pen_size = 3

        self.orig_folder:  str       = ""
        self.mask_folder:  str       = ""
        self.image_files:  list[str] = []
        self.current_index: int      = -1
        self._cursor_pos             = None
        self.edit_panel: EditPanel | None = None

        # ── 主题 ──
        self._theme_name = "dark"

        self._build_ui()
        self._apply_theme()
        self._adapt_to_screen()

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
        self.btn_prev.clicked.connect(self._prev_image)

        self.lbl_info = QLabel("—  /  —")
        self.lbl_info.setObjectName("infoLabel")
        self.lbl_info.setAlignment(Qt.AlignCenter)
        self.lbl_info.setMinimumWidth(200)

        self.btn_next = _btn("下一张  ▶", "navBtn", tooltip="下一张 (→)")
        self.btn_next.setFixedWidth(96)
        self.btn_next.clicked.connect(self._next_image)

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
            self.engine.cancel()
            self._refresh_display()

    def _show_edit_panel(self):
        if self.edit_panel is None:
            self.edit_panel = EditPanel(self.state, self._theme_name, self)
            ep = self.edit_panel
            ep.tool_changed.connect(lambda t: (
                self.engine.cancel(),  # <--- 新增：切换工具时强制中断绘制状态
                setattr(self.state, 'tool', t),
                self.viewer.update_cursor_state(t, self.state.brush_size),
                self._refresh_display()
            ))

            ep.brush_changed.connect(lambda v: (
                self.engine.cancel(),  # <--- 新增：调整画笔大小时也中断一下最安全
                setattr(self.state, 'brush_size', v),
                self.viewer.update_cursor_state(self.state.tool, v),
                self._refresh_display()
            ))
            ep.class_changed.connect(self._on_ep_class)
            ep.alpha_changed.connect(lambda _: self._refresh_display())
            ep.contour_changed.connect(lambda _: self._refresh_display())
            ep.show_all_changed.connect(lambda _: self._refresh_display())
            ep.brightness_changed.connect(lambda _: self._refresh_display())
            ep.contrast_changed.connect(lambda _: self._refresh_display())
            ep.undo_requested.connect(self._undo)
            ep.save_requested.connect(self._save_mask)
            ep.close_edit_requested.connect(
                lambda: (self.btn_edit.setChecked(False),
                         self._toggle_edit(False)))
            ep.classes_updated.connect(lambda _: self._refresh_display())
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
    def _on_press(self, x, y):
        self.engine.on_press(x, y)
        self._post_draw()

    def _on_move(self, x, y):
        self.engine.on_move(x, y)
        self._post_draw()

    def _on_release(self, x, y):
        self.engine.on_release(x, y)
        self._post_draw()

    def _on_dbl_click(self, x, y):
        self.engine.on_double_click(x, y)
        self._post_draw()

    def _on_hover(self, x, y):
        self._cursor_pos = (x, y)
        if self.state.tool == DrawTool.LINE and self.engine.is_active:
            self._refresh_display()

    def _on_ep_class(self, idx):
        self.state.current_class = idx
        self._refresh_display()

    def _post_draw(self):
        if self.edit_panel:
            self.edit_panel.set_undo_enabled(self.state.can_undo())
            self.edit_panel.show_line_hint(
                self.engine.is_active and self.state.tool == DrawTool.LINE)
            self.edit_panel.set_stats(
                class_pixel_stats_str(self.state.mask_img, self.state.classes))
        self._refresh_display()

    # ──────────────────────────────────────────────────────────────────────────
    # 显示刷新
    # ──────────────────────────────────────────────────────────────────────────
    def _refresh_display(self, reset_zoom=False, *args):
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

        if self.state.mask_img is not None and self.state.is_mask_visible:
            alpha    = ep.alpha_value() / 100.0 if ep and ep.isVisible() else 0.5
            contour  = ep.contour_checked()     if ep and ep.isVisible() else True
            show_all = ep.show_all_checked()    if ep and ep.isVisible() else True
            img = blend_mask_on_image(
                img, self.state.mask_img, self.state.classes,
                alpha=alpha, show_all=show_all,
                current_class_idx=self.state.current_class,
                show_contour=contour
            )

        if self.state.tool == DrawTool.LINE and self.engine.is_active:
            self.engine.draw_line_preview(img, self._cursor_pos)

        rgb  = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb.shape
        qimg = QImage(rgb.data, w, h, ch * w, QImage.Format_RGB888)
        px   = QPixmap.fromImage(qimg)

        if reset_zoom:
            self.viewer.set_image(px)
        else:
            self.viewer.update_image(px)

    # ──────────────────────────────────────────────────────────────────────────
    # 掩膜可见切换
    # ──────────────────────────────────────────────────────────────────────────
    def _toggle_mask_visible(self):
        self.state.is_mask_visible = self.btn_mask_vis.isChecked()
        self._refresh_display()

    # ──────────────────────────────────────────────────────────────────────────
    # 撤销 / 折线
    # ──────────────────────────────────────────────────────────────────────────
    def _undo(self):
        if self.state.pop_undo():
            if self.edit_panel:
                self.edit_panel.set_undo_enabled(self.state.can_undo())
            self._refresh_display()

    def _commit_line(self):
        self.engine.commit()
        self._post_draw()

    def _cancel_line(self):
        self.engine.cancel()
        self._post_draw()

    # ──────────────────────────────────────────────────────────────────────────
    # 文件夹 & 图片
    # ──────────────────────────────────────────────────────────────────────────
    def _load_orig_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "选择原图文件夹")
        if folder:
            self.orig_folder = folder
            short = os.path.basename(folder)
            self.lbl_orig.setText(f"📁 {short}")
            self.lbl_orig.setToolTip(folder)
            t = THEMES[self._theme_name]
            self.lbl_orig.setStyleSheet(f"color:{t['text_accent']}; font-size:11px;")
            self._scan_images()

    def _load_mask_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "选择掩膜文件夹")
        if folder:
            self.mask_folder = folder
            short = os.path.basename(folder)
            self.lbl_mask_path.setText(f"📁 {short}")
            self.lbl_mask_path.setToolTip(folder)
            t = THEMES[self._theme_name]
            self.lbl_mask_path.setStyleSheet(f"color:{t['text_accent']}; font-size:11px;")
            self._scan_images()

    def _scan_images(self):
        if not self.orig_folder:
            return
        self.image_files = scan_images(self.orig_folder, VALID_IMAGE_EXTS)
        total = len(self.image_files)
        self.spin_jump.setMaximum(max(1, total))
        if self.image_files:
            self.current_index = 0
            self._load_current_image()

    def _jump_to(self):
        idx = self.spin_jump.value() - 1
        if 0 <= idx < len(self.image_files):
            self.current_index = idx
            self._load_current_image()

    def _prev_image(self):
        if self.current_index > 0:
            self.current_index -= 1
            self._load_current_image()

    def _next_image(self):
        if self.current_index < len(self.image_files) - 1:
            self.current_index += 1
            self._load_current_image()

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
            mp = find_mask_path(self.mask_folder, filename, VALID_IMAGE_EXTS)
            if mp:
                loaded = imread_unicode(mp, cv2.IMREAD_GRAYSCALE)
                if loaded is not None:
                    h, w = orig_img.shape[:2]
                    if loaded.shape[:2] != (h, w):
                        loaded = cv2.resize(loaded, (w, h),
                                            interpolation=cv2.INTER_NEAREST)
                    mask_img = loaded

        self.state.load_image_and_mask(orig_img, mask_img)
        self.engine.cancel()
        self.btn_delete.setEnabled(True)

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

    # ──────────────────────────────────────────────────────────────────────────
    # 保存 & 删除
    # ──────────────────────────────────────────────────────────────────────────
    def _save_mask(self) -> bool:
        if self.state.mask_img is None or not self.mask_folder:
            QMessageBox.warning(self, "错误", "没有可保存的掩膜或未选择掩膜文件夹！")
            return False
        filename  = self.image_files[self.current_index]
        save_path = mask_save_path(self.mask_folder, filename)
        if imwrite_unicode(save_path, self.state.mask_img):
            stats = self.state.class_pixel_stats()
            s     = ", ".join(f"{n}:{c}px" for n, c in stats) or "全背景"
            t     = THEMES[self._theme_name]
            self.lbl_status.setText(
                f"✅ 已保存  {os.path.basename(save_path)}  [{s}]")
            self.lbl_status.setStyleSheet(
                f"color:{t['status_ok']}; font-size:11px;")
            self.setWindowTitle(
                f"Mask Annotator  ·  {filename}  ✓")
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
            base = os.path.splitext(filename)[0]
            for ext in VALID_IMAGE_EXTS:
                for suf in ('', '_mask'):
                    p = os.path.join(self.mask_folder, f"{base}{suf}{ext}")
                    try:
                        if os.path.exists(p): os.remove(p)
                    except Exception:
                        pass

        self.image_files.pop(self.current_index)
        if not self.image_files:
            self.state.orig_img = None
            self.state.mask_img = None
            self.lbl_info.setText("—  /  —")
            self.viewer._scene.clear()
            self.btn_delete.setEnabled(False)
            self.lbl_status.setText("文件夹已清空")
        else:
            if self.current_index >= len(self.image_files):
                self.current_index = len(self.image_files) - 1
            self._load_current_image()

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
                if not self._save_mask(): return
                self._next_image()
            elif key == Qt.Key_W:
                vis = not self.state.is_mask_visible
                self.state.is_mask_visible = vis
                self.btn_mask_vis.setChecked(vis)
                self._refresh_display()

            elif ep_on and key == Qt.Key_1:
                self.engine.cancel()
                self.edit_panel.set_tool_btn(DrawTool.LINE)
                self.state.tool = DrawTool.LINE
                self.state.brush_size = 3
                self.viewer.update_cursor_state(self.state.tool, self.state.brush_size)

            elif ep_on and key == Qt.Key_2:
                self.engine.cancel()
                self.edit_panel.set_tool_btn(DrawTool.POLY)
                self.state.tool = DrawTool.POLY
                self.state.brush_size = 1
                self.viewer.update_cursor_state(self.state.tool, self.state.brush_size)

            elif ep_on and key in (Qt.Key_E, Qt.Key_3):
                self.engine.cancel()

                if self.state.tool == DrawTool.ERASER:
                    self.state.tool = self._last_pen_tool
                    self.state.brush_size = self._last_pen_size
                    self.edit_panel.set_tool_btn(self.state.tool)
                else:
                    self._last_pen_tool = self.state.tool
                    self._last_pen_size = self.state.brush_size
                    self.state.tool = DrawTool.ERASER
                    self.state.brush_size = 20
                    self.edit_panel.set_tool_btn(DrawTool.ERASER)

                self.viewer.update_cursor_state(self.state.tool, self.state.brush_size)

            elif key in (Qt.Key_Return, Qt.Key_Enter):
                if self.state.tool == DrawTool.LINE:
                    self._commit_line()
            elif key == Qt.Key_Escape:
                self._cancel_line()
            elif mods == Qt.ControlModifier and key == Qt.Key_S:
                self._save_mask()
            elif mods == Qt.ControlModifier and key == Qt.Key_Z:
                self._undo()
            elif key == Qt.Key_Delete:
                self._delete_current()

    def closeEvent(self, event):
        if self.edit_panel:
            self.edit_panel.close()
        super().closeEvent(event)
