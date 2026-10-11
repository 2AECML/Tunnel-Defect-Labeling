# ui/graphics_view.py
from PyQt5.QtWidgets import (
    QGraphicsView, QGraphicsScene, QGraphicsPixmapItem,
    QGraphicsEllipseItem, QGraphicsPathItem, QGraphicsItem, QApplication,
)
from PyQt5.QtCore import Qt, pyqtSignal, QPoint
from PyQt5.QtGui import QPainter, QPixmap, QPen, QPainterPath, QColor
from core.config import DrawTool

class InteractiveGraphicsView(QGraphicsView):
    press_signal     = pyqtSignal(float, float)
    move_signal      = pyqtSignal(float, float)
    release_signal   = pyqtSignal(float, float)
    dbl_click_signal = pyqtSignal(float, float)
    hover_signal     = pyqtSignal(int, int)
    context_menu_signal = pyqtSignal(int, int, object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setRenderHint(QPainter.Antialiasing)
        self.setRenderHint(QPainter.SmoothPixmapTransform)

        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)
        self.image_item = QGraphicsPixmapItem()
        self._scene.addItem(self.image_item)

        # 掩膜与原图是两个独立图层，绘制时不再重建原图。
        self.overlay_item = QGraphicsPixmapItem()
        self.overlay_item.setZValue(10)
        self._scene.addItem(self.overlay_item)

        # 当前笔划使用轻量矢量路径预览，松开后再更新掩膜图层。
        self.stroke_item = QGraphicsPathItem()
        self.stroke_item.setZValue(20)
        self.stroke_item.hide()
        self._scene.addItem(self.stroke_item)
        self._stroke_path = QPainterPath()

        # 已有多边形编辑轮廓与顶点控制柄。
        self.polygon_edit_item = QGraphicsPathItem()
        polygon_pen = QPen(QColor(0, 220, 255), 2)
        polygon_pen.setCosmetic(True)
        self.polygon_edit_item.setPen(polygon_pen)
        self.polygon_edit_item.setZValue(30)
        self.polygon_edit_item.hide()
        self._scene.addItem(self.polygon_edit_item)
        self._polygon_handles: list[QGraphicsEllipseItem] = []

        # --- 新增：动态光标（橡皮擦圆圈） ---
        self.cursor_item = QGraphicsEllipseItem()
        pen = QPen(Qt.white, 1)
        pen.setCosmetic(True) # 保持线宽为1像素，不随视图缩放而变粗
        self.cursor_item.setPen(pen)
        self.cursor_item.setZValue(9999) # 确保光标在最上层
        self.cursor_item.hide()
        self._scene.addItem(self.cursor_item)

        self._is_edit_mode = False
        self._pan_start: QPoint | None = None
        self._pan_press_pos: QPoint | None = None
        self._pan_moved = False
        self._current_tool = DrawTool.LINE
        self._polygon_press_pos: QPoint | None = None
        self._polygon_drag_started = False
        self._polygon_double_click = False

        # 开启鼠标追踪（无需按下左键也能触发 mouseMoveEvent）
        self.setMouseTracking(True)
        self.viewport().setMouseTracking(True)
        self.set_view_mode()

    # ──────────────────────────────────────────────────────────────────────────
    # 模式与光标切换
    # ──────────────────────────────────────────────────────────────────────────
    def set_view_mode(self):
        self._reset_polygon_gesture()
        self._is_edit_mode = False
        self.setDragMode(QGraphicsView.ScrollHandDrag)
        self.viewport().setCursor(Qt.ArrowCursor)
        self.cursor_item.hide()

    def set_edit_mode(self):
        self._is_edit_mode = True
        self.setDragMode(QGraphicsView.NoDrag)
        self._update_cursor_display()

    def update_cursor_state(self, tool: str, brush_size: int):
        """外部（如MainWindow）在切换工具或画笔大小时调用此方法"""
        if tool != self._current_tool:
            self._reset_polygon_gesture()
        self._current_tool = tool
        # 更新橡皮擦圆圈大小 (由于是场景坐标，圆圈会自动完美匹配图像像素并支持缩放)
        r = brush_size / 2.0
        self.cursor_item.setRect(-r, -r, brush_size, brush_size)
        self._update_cursor_display()

    def _update_cursor_display(self):
        if not self._is_edit_mode:
            return
        if self._current_tool == DrawTool.ERASER:
            self.viewport().setCursor(Qt.BlankCursor) # 隐藏系统光标
            self.cursor_item.show()                   # 显示圆形光标
        elif self._current_tool == DrawTool.EDIT_POLY:
            self.viewport().setCursor(Qt.PointingHandCursor)
            self.cursor_item.hide()
        else:
            self.viewport().setCursor(Qt.CrossCursor) # 画笔/面状笔使用十字光标
            self.cursor_item.hide()

    # ──────────────────────────────────────────────────────────────────────────
    # 图像设置 (保持不变)
    # ──────────────────────────────────────────────────────────────────────────
    def set_image(self, pixmap: QPixmap):
        self.image_item.setPixmap(pixmap)
        self.setSceneRect(self.image_item.boundingRect())
        self.fit_image()

    def fit_image(self):
        """恢复到整图适应窗口的视图。"""
        if not self.image_item.pixmap().isNull():
            self.resetTransform()
            self.fitInView(self.sceneRect(), Qt.KeepAspectRatio)

    def update_image(self, pixmap: QPixmap):
        self.image_item.setPixmap(pixmap)

    def set_overlay(self, pixmap: QPixmap):
        self.overlay_item.setPixmap(pixmap)

    def set_overlay_visible(self, visible: bool):
        self.overlay_item.setVisible(visible)

    def begin_stroke(self, x: int, y: int, tool: str, color: QColor, width: int):
        self._stroke_path = QPainterPath()
        self._stroke_path.moveTo(x, y)
        pen_color = QColor(255, 255, 255, 220) if tool == DrawTool.ERASER else color
        pen = QPen(pen_color, max(1, width), Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
        if tool == DrawTool.ERASER:
            pen.setStyle(Qt.DashLine)
        self.stroke_item.setPen(pen)
        self.stroke_item.setPath(self._stroke_path)
        self.stroke_item.show()

    def extend_stroke(self, x: int, y: int):
        if not self.stroke_item.isVisible():
            return
        self._stroke_path.lineTo(x, y)
        self.stroke_item.setPath(self._stroke_path)

    def clear_stroke(self):
        self.stroke_item.hide()
        self._stroke_path = QPainterPath()
        self.stroke_item.setPath(self._stroke_path)

    def set_polygon_edit(self, vertices, active_index: int | None = None, *, outline_vertices=None):
        """轮廓线与控制柄分开显示，减少初始控制点不改变真实轮廓。"""
        if vertices is None or len(vertices) < 3:
            self.clear_polygon_edit()
            return
        path = QPainterPath()
        outline = vertices if outline_vertices is None else outline_vertices
        path.moveTo(float(outline[0][0]), float(outline[0][1]))
        for x, y in outline[1:]:
            path.lineTo(float(x), float(y))
        path.closeSubpath()
        self.polygon_edit_item.setPath(path)
        self.polygon_edit_item.show()
        # Exact outlines can have thousands of points. Reuse existing handles
        # when inserting/deleting one point rather than recreate them all.
        while len(self._polygon_handles) > len(vertices):
            self._scene.removeItem(self._polygon_handles.pop())
        while len(self._polygon_handles) < len(vertices):
            handle = QGraphicsEllipseItem(-4, -4, 8, 8)
            handle.setFlag(QGraphicsItem.ItemIgnoresTransformations, True)
            handle.setPen(QPen(QColor(20, 20, 20), 1))
            handle.setZValue(31)
            self._scene.addItem(handle)
            self._polygon_handles.append(handle)
        for index, ((x, y), handle) in enumerate(
            zip(vertices, self._polygon_handles)
        ):
            handle.setPos(float(x), float(y))
            handle.setBrush(
                QColor(255, 205, 40) if index == active_index
                else QColor(0, 220, 255)
            )
            handle.show()

    def clear_polygon_edit(self):
        self.polygon_edit_item.hide()
        self.polygon_edit_item.setPath(QPainterPath())
        for handle in self._polygon_handles:
            self._scene.removeItem(handle)
        self._polygon_handles.clear()

    def clear_image(self):
        """清空当前图像，但保留可重用的场景和光标对象。"""
        self.image_item.setPixmap(QPixmap())
        self.overlay_item.setPixmap(QPixmap())
        self.clear_stroke()
        self.clear_polygon_edit()
        self.cursor_item.hide()
        self.setSceneRect(0, 0, 0, 0)
        self.resetTransform()

    # ──────────────────────────────────────────────────────────────────────────
    # 事件
    # ──────────────────────────────────────────────────────────────────────────
    def _reset_polygon_gesture(self):
        self._polygon_press_pos = None
        self._polygon_drag_started = False
        self._polygon_double_click = False

    def wheelEvent(self, event):
        factor = 1.15 if event.angleDelta().y() > 0 else 1.0 / 1.15
        current = self.transform().m11()
        target = current * factor
        if 0.02 <= target <= 80.0:
            self.scale(factor, factor)

    def mousePressEvent(self, event):
        if event.button() == Qt.RightButton:
            self._pan_start = event.pos()
            self._pan_press_pos = event.pos()
            self._pan_moved = False
            self.viewport().setCursor(Qt.ClosedHandCursor)
            self.cursor_item.hide()
            event.accept()
            return

        if self._is_edit_mode and event.button() == Qt.LeftButton:
            if self._current_tool == DrawTool.EDIT_POLY:
                self._reset_polygon_gesture()
                self._polygon_press_pos = event.pos()
            pos = self.mapToScene(event.pos())
            self.press_signal.emit(pos.x(), pos.y())
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._pan_start is not None:
            if not self._pan_moved and self._pan_press_pos is not None:
                distance = (event.pos() - self._pan_press_pos).manhattanLength()
                if distance < QApplication.startDragDistance():
                    return
                self._pan_moved = True
            delta = event.pos() - self._pan_start
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - delta.x())
            self.verticalScrollBar().setValue(self.verticalScrollBar().value() - delta.y())
            self._pan_start = event.pos()
            return

        pos = self.mapToScene(event.pos())
        ix, iy = int(pos.x()), int(pos.y())

        # 实时更新自定义橡皮擦光标位置
        if self.cursor_item.isVisible():
            self.cursor_item.setPos(pos)

        if self._is_edit_mode:
            if self._current_tool == DrawTool.EDIT_POLY:
                if self._polygon_press_pos is not None and event.buttons() & Qt.LeftButton:
                    distance = (event.pos() - self._polygon_press_pos).manhattanLength()
                    if distance >= QApplication.startDragDistance():
                        self._polygon_drag_started = True
                    if self._polygon_drag_started:
                        self.move_signal.emit(pos.x(), pos.y())
            else:
                self.move_signal.emit(pos.x(), pos.y())
            self.hover_signal.emit(ix, iy)
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.RightButton:
            was_click = not self._pan_moved
            self._pan_start = None
            self._pan_press_pos = None
            self._pan_moved = False
            self._update_cursor_display()
            if was_click and self._is_edit_mode:
                pos = self.mapToScene(event.pos())
                self.context_menu_signal.emit(
                    int(pos.x()), int(pos.y()),
                    self.viewport().mapToGlobal(event.pos()),
                )
            event.accept()
            return
        if self._is_edit_mode and event.button() == Qt.LeftButton:
            if self._current_tool == DrawTool.EDIT_POLY:
                if self._polygon_double_click or self._polygon_press_pos is None:
                    self._reset_polygon_gesture()
                    event.accept()
                    return
            pos = self.mapToScene(event.pos())
            self.release_signal.emit(pos.x(), pos.y())
            self._reset_polygon_gesture()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event):
        if self._is_edit_mode and event.button() == Qt.LeftButton:
            if self._current_tool == DrawTool.EDIT_POLY:
                self._reset_polygon_gesture()
                self._polygon_double_click = True
            pos = self.mapToScene(event.pos())
            self.dbl_click_signal.emit(pos.x(), pos.y())
            event.accept()
        else:
            super().mouseDoubleClickEvent(event)
