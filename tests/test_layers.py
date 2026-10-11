import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
import pytest
from PyQt5.QtWidgets import QApplication

from core.config import DEFAULT_CLASSES
from ui.main_window import MainWindow
from utils.mask_utils import mask_to_overlay_rgba


def test_mask_overlay_is_independent_rgba_layer():
    mask = np.zeros((8, 8), dtype=np.uint8)
    mask[2:6, 3:7] = 2
    original = mask.copy()

    overlay = mask_to_overlay_rgba(
        mask, DEFAULT_CLASSES, alpha=0.5, show_contour=False
    )

    assert overlay.shape == (8, 8, 4)
    assert np.array_equal(mask, original)
    assert overlay[0, 0, 3] == 0
    assert overlay[3, 4, 3] == 128
    assert tuple(overlay[3, 4, :3]) == (255, 0, 0)


def test_show_current_class_filters_other_classes():
    mask = np.array([[1, 2, 3]], dtype=np.uint8)
    overlay = mask_to_overlay_rgba(
        mask,
        DEFAULT_CLASSES,
        alpha=1.0,
        show_all=False,
        current_class_idx=1,
        show_contour=False,
    )
    assert overlay[0, 0, 3] == 0
    assert overlay[0, 1, 3] == 255
    assert overlay[0, 2, 3] == 0


def test_mouse_move_updates_preview_without_rebuilding_full_layers():
    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    image = np.zeros((32, 32, 3), dtype=np.uint8)
    window.state.load_image_and_mask(image, None)
    window.image_files = ["test.png"]
    window.current_index = 0
    calls = {"base": 0, "overlay": 0, "stats": 0}
    window._refresh_base_image = lambda *args, **kwargs: calls.__setitem__(
        "base", calls["base"] + 1
    )
    window._refresh_mask_overlay = lambda *args, **kwargs: calls.__setitem__(
        "overlay", calls["overlay"] + 1
    )
    window._refresh_stats = lambda *args, **kwargs: calls.__setitem__(
        "stats", calls["stats"] + 1
    )

    window._on_press(2, 2)
    for x in range(3, 20):
        window._on_move(x, x)
    assert calls == {"base": 0, "overlay": 0, "stats": 0}

    window._on_release(20, 20)
    assert calls == {"base": 0, "overlay": 1, "stats": 1}
    window.state.mark_saved()
    window.deleteLater()
    app.processEvents()


def _polygon_window():
    from core.config import DrawTool
    from PyQt5.QtGui import QPixmap

    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    window.resize(1200, 800)
    image = np.zeros((300, 500, 3), dtype=np.uint8)
    mask = np.zeros(image.shape[:2], dtype=np.uint8)
    mask[50:251, 40:461] = 3
    window.state.load_image_and_mask(image, mask)
    window.state.tool = DrawTool.EDIT_POLY
    window.viewer.set_edit_mode()
    window.viewer.update_cursor_state(DrawTool.EDIT_POLY, 3)
    window.viewer.set_image(QPixmap(500, 300))
    window.show()
    app.processEvents()
    window.viewer.fit_image()
    assert window.polygon_editor.select(mask, 100, 100)
    return app, window


def _polygon_mouse(view, kind, position, *, buttons=None):
    from PyQt5.QtCore import Qt, QPointF
    from PyQt5.QtGui import QMouseEvent

    button = Qt.NoButton if kind == QMouseEvent.MouseMove else Qt.LeftButton
    if buttons is None:
        buttons = Qt.NoButton if kind == QMouseEvent.MouseButtonRelease else Qt.LeftButton
    event = QMouseEvent(kind, QPointF(position), QPointF(view.viewport().mapToGlobal(position)), button, buttons, Qt.NoModifier)
    handlers = {
        QMouseEvent.MouseButtonPress: view.mousePressEvent,
        QMouseEvent.MouseMove: view.mouseMoveEvent,
        QMouseEvent.MouseButtonRelease: view.mouseReleaseEvent,
        QMouseEvent.MouseButtonDblClick: view.mouseDoubleClickEvent,
    }
    handlers[kind](event)


@pytest.mark.parametrize("scene_y", [49, 51])
def test_double_click_with_jitter_adds_point_without_moving_polygon(scene_y):
    from PyQt5.QtCore import QPointF, QPoint, Qt
    from PyQt5.QtGui import QMouseEvent

    app, window = _polygon_window()
    view = window.viewer
    position = view.mapFromScene(QPointF(200, scene_y))
    vertices = window.polygon_editor.vertices.copy()
    original = window.state.mask_img.copy()
    _polygon_mouse(view, QMouseEvent.MouseButtonPress, position)
    _polygon_mouse(view, QMouseEvent.MouseMove, position + QPoint(1, 0))
    _polygon_mouse(view, QMouseEvent.MouseButtonRelease, position + QPoint(1, 0))
    # Platforms may dispatch an additional press before the double-click event.
    _polygon_mouse(view, QMouseEvent.MouseButtonPress, position)
    _polygon_mouse(view, QMouseEvent.MouseButtonDblClick, position)
    _polygon_mouse(view, QMouseEvent.MouseMove, position + QPoint(30, 0))
    _polygon_mouse(view, QMouseEvent.MouseButtonRelease, position + QPoint(30, 0))
    inserted = window.polygon_editor.selected_vertex_index
    assert inserted is not None
    assert len(window.polygon_editor.vertices) == len(vertices) + 1
    assert np.array_equal(np.delete(window.polygon_editor.vertices, inserted, axis=0), vertices)
    assert np.array_equal(window.state.mask_img, original)
    assert not window.state.is_dirty
    assert not window.state.can_undo()
    assert not window.polygon_editor.is_dragging
    after = window.polygon_editor.vertices.copy()
    _polygon_mouse(view, QMouseEvent.MouseMove, position + QPoint(80, 0), buttons=Qt.NoButton)
    assert np.array_equal(window.polygon_editor.vertices, after)
    window.deleteLater()
    app.processEvents()


def test_real_drag_still_moves_polygon_and_can_be_undone():
    from PyQt5.QtCore import QPointF, QPoint
    from PyQt5.QtGui import QMouseEvent

    app, window = _polygon_window()
    view = window.viewer
    position = view.mapFromScene(QPointF(200, 150))
    target = position + QPoint(QApplication.startDragDistance() + 30, 0)
    original = window.state.mask_img.copy()
    _polygon_mouse(view, QMouseEvent.MouseButtonPress, position)
    _polygon_mouse(view, QMouseEvent.MouseMove, target)
    _polygon_mouse(view, QMouseEvent.MouseButtonRelease, target)
    assert not np.array_equal(window.state.mask_img, original)
    assert window.state.is_dirty
    assert window.state.can_undo()
    window._undo()
    assert np.array_equal(window.state.mask_img, original)
    assert not window.state.is_dirty
    window.deleteLater()
    app.processEvents()


def test_view_displays_exact_outline_separately_from_reduced_controls():
    import cv2
    from core.config import DrawTool

    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    image = np.zeros((300, 550, 3), dtype=np.uint8)
    mask = np.zeros(image.shape[:2], dtype=np.uint8)
    cv2.fillPoly(mask, [np.asarray(((10, 20), (480, 120), (470, 220), (15, 130)), np.int32)], 3)
    window.state.load_image_and_mask(image, mask)
    window.state.tool = DrawTool.EDIT_POLY
    window._on_press(200, 130)
    editor = window.polygon_editor
    assert len(window.viewer._polygon_handles) == 4
    path = window.viewer.polygon_edit_item.path()
    assert path.elementCount() > 300
    point = max(editor.outline_vertices, key=lambda p: editor._closest_edge(*p)[0])
    window._on_dbl_click(*point)
    assert len(window.viewer._polygon_handles) == 5
    assert window.viewer.polygon_edit_item.path() == path
    assert not window.state.is_dirty
    window.deleteLater()
    app.processEvents()
