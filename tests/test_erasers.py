"""区域擦除的像素范围、预览、历史与擦除方式记忆。"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
import pytest
from PyQt5.QtCore import QPointF, QSettings, Qt
from PyQt5.QtGui import QMouseEvent
from PyQt5.QtWidgets import QApplication

from core.annotation_state import AnnotationState
from core.config import DrawTool
from core.draw_engine import DrawEngine
from ui import main_window


def state_and_engine(tool):
    state = AnnotationState()
    # 多种类别和旧版 255 值均应擦除，原图必须保留。
    image = np.full((64, 64, 3), 127, dtype=np.uint8)
    mask = np.tile(np.asarray([1, 2, 3, 255], np.uint8), (64, 16))
    state.load_image_and_mask(image, mask)
    state.tool = tool
    return state, DrawEngine(state)


@pytest.mark.parametrize("start,end", [((8, 12), (40, 48)), ((40, 48), (8, 12)),
                                     ((40, 12), (8, 48)), ((8, 48), (40, 12))])
def test_rectangle_erases_exact_range_in_every_drag_direction(start, end):
    state, engine = state_and_engine(DrawTool.RECT_ERASER)
    original = state.mask_img.copy()
    image = state.orig_img.copy()
    engine.on_press(*start)
    engine.on_move(55, 55)  # 移回较小范围时，不留下之前的矩形。
    engine.on_move(*end)
    assert np.array_equal(state.mask_img, original)
    assert not state.is_dirty and not state.can_undo()
    engine.on_release(*end)
    expected = original.copy()
    expected[12:49, 8:41] = 0
    assert np.array_equal(state.mask_img, expected)
    assert np.array_equal(state.orig_img, image)
    assert not engine.is_active
    assert len(state.undo_stack) == 1
    assert state.pop_undo()
    assert np.array_equal(state.mask_img, original) and not state.is_dirty
    assert state.pop_redo()
    assert np.array_equal(state.mask_img, expected) and state.is_dirty


@pytest.mark.parametrize("tool", DrawTool.AREA_ERASERS)
def test_area_erasure_clips_to_image_without_wrapping_negative_coordinates(tool):
    state, engine = state_and_engine(tool)
    original = state.mask_img.copy()
    engine.on_press(25, 25)
    if tool == DrawTool.POLY_ERASER:
        for point in ((-20, 25), (-20, -20), (25, -20)):
            engine.on_move(*point)
        engine.on_release(25, 25)
    else:
        engine.on_release(-20, -20)
    expected = original.copy()
    expected[:26, :26] = 0
    assert np.array_equal(state.mask_img, expected)


def test_area_eraser_closes_concave_outline_using_release_position():
    state, engine = state_and_engine(DrawTool.POLY_ERASER)
    state.brush_size = 80  # 区域擦除不受圆形笔刷大小影响。
    original = state.mask_img.copy()
    engine.on_press(10, 10)
    for point in ((45, 10), (45, 20), (20, 20), (20, 45)):
        engine.on_move(*point)
    assert np.array_equal(state.mask_img, original)
    engine.on_release(10, 45)  # 最后一段只由 release 提供。
    assert state.mask_img[35, 12] == 0
    assert state.mask_img[12, 35] == 0
    assert state.mask_img[10, 10] == 0
    assert state.mask_img[35, 35] == original[35, 35]  # 凹口不被包围盒擦除。
    assert state.mask_img[5, 5] == original[5, 5]
    assert len(state.undo_stack) == 1
    after = state.mask_img.copy()
    assert state.pop_undo() and np.array_equal(state.mask_img, original)
    assert state.pop_redo() and np.array_equal(state.mask_img, after)


@pytest.mark.parametrize("tool", DrawTool.AREA_ERASERS)
@pytest.mark.parametrize("action", ["cancel", "click", "collinear", "background"])
def test_no_op_or_cancelled_region_preserves_history_saved_state_and_redo(tool, action):
    state, engine = state_and_engine(DrawTool.ERASER)
    engine.on_press(50, 50)
    engine.on_release(50, 50)
    completed = state.mask_img.copy()
    assert state.pop_undo()
    before = state.mask_img.copy()
    state.mark_saved()
    state.tool = tool
    if action == "background":
        state.mask_img[:35, :35] = 0
        before = state.mask_img.copy()
    engine.on_press(5, 5)
    if action == "click":
        engine.on_release(5, 5)
    elif action == "collinear":
        engine.on_move(15, 5)
        engine.on_release(25, 5)
    else:
        for point in ((25, 5), (25, 25), (5, 25)):
            engine.on_move(*point)
        if action == "cancel":
            engine.cancel()
        else:
            engine.on_release(25, 25)
    assert not engine.is_active
    assert np.array_equal(state.mask_img, before)
    assert not state.is_dirty and not state.can_undo()
    assert state.pop_redo()
    assert np.array_equal(state.mask_img, completed)


@pytest.fixture
def windows(tmp_path, monkeypatch, qtbot):
    settings_path = str(tmp_path / "erasers.ini")
    monkeypatch.setattr(main_window, "QSettings", lambda *args: QSettings(
        settings_path, QSettings.IniFormat))

    def create():
        window = main_window.MainWindow()
        qtbot.addWidget(window, before_close_func=lambda widget: widget.state.mark_saved())
        window.state.load_image_and_mask(np.zeros((128, 128, 3), np.uint8),
                                         np.ones((128, 128), np.uint8))
        window.show()
        window.btn_edit.click()
        window._refresh_display(reset_zoom=True)
        QApplication.processEvents()
        return window

    return create, QSettings(settings_path, QSettings.IniFormat)


def choose_eraser(window, tool):
    panel = window.edit_panel
    panel.btn_eraser.click()
    panel.combo_eraser.setCurrentIndex(panel.combo_eraser.findData(tool))
    assert panel.btn_eraser.isChecked()
    assert window.state.tool == tool
    assert window.viewer._current_tool == tool


def send_mouse(view, kind, x, y):
    position = view.mapFromScene(QPointF(x, y))
    button = Qt.NoButton if kind == QMouseEvent.MouseMove else Qt.LeftButton
    buttons = Qt.NoButton if kind == QMouseEvent.MouseButtonRelease else Qt.LeftButton
    event = QMouseEvent(kind, QPointF(position), button, buttons, Qt.NoModifier)
    QApplication.sendEvent(view.viewport(), event)


@pytest.mark.parametrize("tool", DrawTool.AREA_ERASERS)
def test_viewport_drag_shows_preview_and_erases_only_on_release(windows, monkeypatch, tool):
    window = windows[0]()
    choose_eraser(window, tool)
    view = window.viewer
    original = window.state.mask_img.copy()
    calls = []
    refresh = window._refresh_mask_overlay
    monkeypatch.setattr(window, "_refresh_mask_overlay", lambda: (calls.append(1), refresh()))
    view.scale(1.5, 1.5)
    send_mouse(view, QMouseEvent.MouseButtonPress, 10, 10)
    send_mouse(view, QMouseEvent.MouseMove, 100, 10)
    send_mouse(view, QMouseEvent.MouseMove, 100, 100)
    assert np.array_equal(window.state.mask_img, original)
    assert not calls
    assert view.stroke_item.isVisible()
    assert not view.cursor_item.isVisible()  # 区域工具使用十字光标。
    path = view.stroke_item.path()
    if tool == DrawTool.POLY_ERASER:
        # 只有起点和实际走过的两段，没有回到起点的辅助线或填充。
        assert path.elementCount() == 3
        assert path.currentPosition().x() > 90
        assert path.currentPosition().y() > 90
        assert view.stroke_item.brush().style() == Qt.NoBrush
        assert view.stroke_item.pen().style() == Qt.SolidLine
    else:
        assert path.contains(QPointF(50, 50))
    release_x = 100 if tool == DrawTool.RECT_ERASER else 10
    send_mouse(view, QMouseEvent.MouseButtonRelease, release_x, 100)
    assert not window.engine.is_active
    assert not view.stroke_item.isVisible()
    assert len(calls) == 1
    assert window.state.mask_img[50, 50] == 0
    assert window.state.mask_img[5, 5] == 1
    assert len(window.state.undo_stack) == 1
    window._undo()
    assert np.array_equal(window.state.mask_img, original)
    window._redo()
    assert window.state.mask_img[50, 50] == 0


@pytest.mark.parametrize("tool", DrawTool.AREA_ERASERS)
@pytest.mark.parametrize("action", ["switch_tool", "close_edit"])
def test_leaving_eraser_cancels_preview_without_erasing(windows, tool, action):
    window = windows[0]()
    choose_eraser(window, tool)
    original = window.state.mask_img.copy()
    window._on_press(10, 10)
    window._on_move(100, 10)
    window._on_move(100, 100)
    if action == "switch_tool":
        window.edit_panel.btn_poly.click()
    else:
        window.btn_edit.click()
    assert not window.engine.is_active
    assert not window.viewer.stroke_item.isVisible()
    assert np.array_equal(window.state.mask_img, original)
    assert not window.state.is_dirty and not window.state.can_undo()


@pytest.mark.parametrize("tool", DrawTool.ERASERS)
def test_eraser_choice_survives_tool_panel_and_application_reopening(windows, tool):
    window = windows[0]()
    choose_eraser(window, tool)
    panel = window.edit_panel
    panel.btn_poly.click()
    panel.btn_eraser.click()
    assert window.state.tool == tool
    assert panel.combo_eraser.currentData() == tool
    assert panel.slider_brush.isHidden() == (tool in DrawTool.AREA_ERASERS)
    window.btn_edit.click()
    window.btn_edit.click()
    assert panel.btn_eraser.isChecked()
    assert panel.combo_eraser.currentData() == tool
    assert windows[1].value("eraser_tool", type=str) == tool
    window.close()
    reopened = windows[0]()
    reopened.edit_panel.btn_eraser.click()
    assert reopened.state.tool == tool
    assert reopened.edit_panel.combo_eraser.currentData() == tool


def test_invalid_saved_eraser_choice_falls_back_to_brush(windows):
    windows[1].setValue("eraser_tool", "unknown_tool")
    windows[1].sync()
    window = windows[0]()
    window.edit_panel.btn_eraser.click()
    assert window.state.tool == DrawTool.ERASER


def test_undo_while_selecting_empty_region_clears_preview(windows):
    window = windows[0]()
    window.state.mask_img[:] = 0
    choose_eraser(window, DrawTool.RECT_ERASER)
    window._on_press(10, 10)
    window._on_move(100, 100)
    window._undo()
    assert not window.engine.is_active
    assert not window.viewer.stroke_item.isVisible()
    assert not window.state.is_dirty and not window.state.can_undo()
