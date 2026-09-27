import numpy as np

from core.annotation_state import AnnotationState
from core.config import DrawTool
from core.draw_engine import DrawEngine


def _state() -> AnnotationState:
    state = AnnotationState()
    image = np.zeros((64, 64, 3), dtype=np.uint8)
    state.load_image_and_mask(image, None)
    return state


def test_line_stroke_finishes_on_mouse_release_and_can_be_undone():
    state = _state()
    state.tool = DrawTool.LINE
    state.brush_size = 3
    engine = DrawEngine(state)

    engine.on_press(5, 5)
    engine.on_move(30, 30)
    engine.on_release(30, 30)

    assert not engine.is_active
    assert state.is_dirty
    assert np.count_nonzero(state.mask_img == state.current_draw_value) > 0
    assert state.pop_undo()
    assert not state.is_dirty
    assert not np.any(state.mask_img)


def test_escape_restores_mask_before_current_stroke():
    state = _state()
    engine = DrawEngine(state)

    engine.on_press(4, 4)
    engine.on_move(40, 40)
    assert np.any(state.mask_img)
    engine.cancel()

    assert not engine.is_active
    assert not state.is_dirty
    assert not np.any(state.mask_img)


def test_area_tool_closes_and_fills_dragged_outline_on_release():
    state = _state()
    state.tool = DrawTool.POLY
    engine = DrawEngine(state)

    engine.on_press(10, 10)
    for point in ((40, 10), (40, 40), (10, 40), (10, 10)):
        engine.on_move(*point)
    engine.on_release(10, 10)

    assert not engine.is_active
    assert state.mask_img[25, 25] == state.current_draw_value


def test_saved_revision_becomes_dirty_only_after_a_new_stroke():
    state = _state()
    engine = DrawEngine(state)
    engine.on_press(5, 5)
    engine.on_release(5, 5)
    state.mark_saved()

    assert not state.is_dirty
    engine.on_press(20, 20)
    engine.on_release(20, 20)
    assert state.is_dirty
    assert state.pop_undo()
    assert not state.is_dirty


def test_existing_polygon_vertex_edit_can_be_undone():
    from core.polygon_editor import PolygonEditor

    state = _state()
    state.mask_img[10:41, 10:41] = 3
    original = state.mask_img.copy()
    editor = PolygonEditor()
    assert editor.select(state.mask_img, 20, 20)
    index = editor.hit_vertex(10, 10, 4)
    assert index is not None

    editor.begin_drag(10, 10, index)
    editor.drag_to(5, 5, state.mask_img.shape)
    state.push_undo()
    state.mark_modified()
    editor.apply(state.mask_img)

    assert state.is_dirty
    assert not np.array_equal(state.mask_img, original)
    assert state.pop_undo()
    assert np.array_equal(state.mask_img, original)
    assert not state.is_dirty
