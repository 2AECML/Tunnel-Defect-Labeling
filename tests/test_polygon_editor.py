import numpy as np

from core.polygon_editor import PolygonEditor


def _two_polygons():
    mask = np.zeros((100, 120), dtype=np.uint8)
    mask[20:61, 20:61] = 3
    mask[20:51, 80:111] = 3
    return mask


def test_selects_only_clicked_connected_polygon():
    mask = _two_polygons()
    editor = PolygonEditor()

    assert editor.select(mask, 35, 35)
    assert editor.value == 3
    assert editor.has_selection
    assert editor.contains(35, 35)
    assert not editor.contains(90, 35)


def test_dragging_vertex_rebuilds_polygon_without_touching_other_component():
    mask = _two_polygons()
    other_before = mask[20:51, 80:111].copy()
    editor = PolygonEditor()
    assert editor.select(mask, 35, 35)

    index = editor.hit_vertex(20, 20, 4)
    assert index is not None
    editor.begin_drag(20, 20, index)
    editor.drag_to(10, 10, mask.shape)
    assert editor.drag_changed()
    editor.apply(mask)

    assert mask[10, 10] == 3
    assert np.array_equal(mask[20:51, 80:111], other_before)


def test_dragging_inside_moves_entire_polygon():
    mask = np.zeros((80, 100), dtype=np.uint8)
    mask[20:41, 20:41] = 2
    editor = PolygonEditor()
    assert editor.select(mask, 30, 30)

    editor.begin_drag(30, 30, None)
    editor.drag_to(50, 40, mask.shape)
    editor.apply(mask)

    assert mask[25, 25] == 0
    assert mask[40, 50] == 2


def test_background_click_clears_selection():
    mask = _two_polygons()
    editor = PolygonEditor()
    assert editor.select(mask, 35, 35)
    assert not editor.select(mask, 0, 0)
    assert not editor.has_selection


def test_double_click_style_insert_adds_control_point_on_edge():
    mask = _two_polygons()
    editor = PolygonEditor()
    assert editor.select(mask, 35, 35)
    before = len(editor.vertices)
    index = editor.insert_vertex(40, 20, 3)
    assert index is not None
    assert len(editor.vertices) == before + 1
    assert tuple(editor.vertices[index]) == (40, 20)
