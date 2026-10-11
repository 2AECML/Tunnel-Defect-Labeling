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


def test_delete_removes_only_selected_connected_polygon():
    mask = _two_polygons()
    other_before = mask[20:51, 80:111].copy()
    editor = PolygonEditor()
    assert editor.select(mask, 35, 35)

    assert editor.delete(mask)

    assert not np.any(mask[20:61, 20:61])
    assert np.array_equal(mask[20:51, 80:111], other_before)
    assert not editor.has_selection


def test_delete_without_selection_does_nothing():
    mask = _two_polygons()
    before = mask.copy()

    assert not PolygonEditor().delete(mask)
    assert np.array_equal(mask, before)


def test_delete_selected_vertex_keeps_a_valid_polygon():
    mask = _two_polygons()
    editor = PolygonEditor()
    assert editor.select(mask, 35, 35)
    before = len(editor.vertices)
    index = editor.hit_vertex(20, 20, 4)
    assert index is not None
    editor.select_vertex(index)

    assert editor.delete_selected_vertex()
    assert len(editor.vertices) == before - 1
    assert editor.selected_vertex_index is None


def test_triangle_vertices_cannot_be_deleted():
    editor = PolygonEditor()
    editor.vertices = np.asarray(((10, 10), (30, 10), (20, 30)), dtype=np.int32)
    editor.select_vertex(0)

    assert not editor.delete_selected_vertex()
    assert len(editor.vertices) == 3


def test_selection_retains_more_than_160_exact_contour_points():
    import cv2

    mask = np.zeros((240, 1300), dtype=np.uint8)
    top = np.asarray([(20 + i * 3, 30 if i % 2 == 0 else 60) for i in range(401)], np.int32)
    polygon = np.vstack((top, ((1220, 180), (20, 180)))).astype(np.int32)
    cv2.fillPoly(mask, [polygon], 3)
    original = mask.copy()
    editor = PolygonEditor()
    assert editor.select(mask, 100, 100)
    contours, _ = cv2.findContours((mask == 3).astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    assert len(editor.outline_vertices) == len(max(contours, key=cv2.contourArea))
    assert len(editor.vertices) > 160
    assert not editor.apply(mask)
    assert np.array_equal(mask, original)


def test_subpixel_insert_only_splits_edge_and_does_not_change_mask():
    import cv2

    mask = np.zeros((100, 100), dtype=np.uint8)
    cv2.fillPoly(mask, [np.asarray(((10, 15), (50, 55), (50, 80), (10, 80)), np.int32)], 3)
    original = mask.copy()
    editor = PolygonEditor()
    assert editor.select(mask, 30, 65)
    vertices = editor.vertices.copy()
    area = cv2.contourArea(vertices.astype(np.float32))
    index = editor.insert_vertex(30.5, 35.5, 2)
    assert index is not None
    assert np.array_equal(editor.vertices[index], (30.5, 35.5))
    assert np.array_equal(np.delete(editor.vertices, index, axis=0), vertices)
    assert cv2.contourArea(editor.vertices.astype(np.float32)) == area
    assert not editor.apply(mask)
    assert np.array_equal(mask, original)


def test_insert_at_endpoint_selects_it_instead_of_creating_duplicate():
    editor = PolygonEditor()
    mask = _two_polygons()
    assert editor.select(mask, 35, 35)
    before = editor.vertices.copy()
    index = editor.insert_vertex(*before[0], 3)
    assert index == 0
    assert np.array_equal(editor.vertices, before)


def test_local_vertex_drag_does_not_change_distant_curved_boundary():
    import cv2

    mask = np.zeros((300, 300), dtype=np.uint8)
    cv2.circle(mask, (150, 150), 110, 3, -1)
    original = mask.copy()
    editor = PolygonEditor()
    assert editor.select(mask, 150, 150)
    index = editor.hit_vertex(150, 40, 1)
    assert index is not None
    editor.begin_drag(150, 40, index)
    editor.drag_to(150, 30, mask.shape)
    assert editor.apply(mask)
    assert not np.array_equal(mask, original)
    assert np.array_equal(mask[60:], original[60:])


def test_vertex_edit_preserves_holes_and_other_class_inside():
    mask = np.zeros((100, 120), dtype=np.uint8)
    mask[20:81, 20:81] = 3
    mask[35:66, 35:66] = 0
    mask[45:56, 45:56] = 2
    original = mask.copy()
    editor = PolygonEditor()
    assert editor.select(mask, 25, 25)
    assert not editor.contains(40, 40)
    assert not editor.contains(50, 50)
    index = editor.hit_vertex(20, 20, 1)
    editor.begin_drag(20, 20, index)
    editor.drag_to(10, 10, mask.shape)
    assert editor.apply(mask)
    assert np.array_equal(mask[35:66, 35:66], original[35:66, 35:66])
    # The two edges incident to the moved corner change; the opposite edge does not.
    assert np.array_equal(mask[30:, 70:], original[30:, 70:])
    assert not editor.apply(mask)


def test_whole_translation_moves_exact_pixels_and_holes():
    import cv2

    mask = np.zeros((200, 300), dtype=np.uint8)
    cv2.circle(mask, (90, 90), 40, 3, -1)
    cv2.circle(mask, (90, 90), 15, 0, -1)
    mask[85:96, 85:96] = 2
    source = mask == 3
    expected = mask.copy()
    expected[source] = 0
    shifted = np.zeros(mask.shape, dtype=bool)
    shifted[:, 60:] = source[:, :-60]
    expected[shifted] = 3
    editor = PolygonEditor()
    assert editor.select(mask, 60, 90)
    editor.begin_drag(60, 90, None)
    editor.drag_to(120, 90, mask.shape)
    assert editor.apply(mask)
    assert np.array_equal(mask, expected)
    assert mask[90, 150] == 0
    assert mask[90, 90] == 2


def test_translation_at_image_edge_does_not_squash_shape():
    mask = np.zeros((80, 100), dtype=np.uint8)
    mask[20:51, 10:41] = 3
    mask[30:36, 20:26] = 0
    source = mask[20:51, 10:41].copy()
    editor = PolygonEditor()
    assert editor.select(mask, 15, 25)
    editor.begin_drag(15, 25, None)
    editor.drag_to(500, 500, mask.shape)
    assert editor.apply(mask)
    assert np.array_equal(mask[49:80, 69:100], source)
    assert np.count_nonzero(mask == 3) == np.count_nonzero(source == 3)


def test_slanted_straight_edges_have_few_controls_but_keep_exact_pixels():
    import cv2

    mask = np.zeros((300, 550), dtype=np.uint8)
    cv2.fillPoly(mask, [np.asarray(((10, 20), (480, 120), (470, 220), (15, 130)), np.int32)], 3)
    original = mask.copy()
    editor = PolygonEditor()
    assert editor.select(mask, 200, 130)
    assert len(editor.vertices) == 4
    assert len(editor.outline_vertices) > 300
    exact = editor.outline_vertices.copy()
    assert not editor.apply(mask)
    assert np.array_equal(mask, original)
    assert np.array_equal(editor.outline_vertices, exact)


def test_adding_to_exact_staircase_edge_works_at_high_zoom_without_reshaping():
    import cv2

    mask = np.zeros((300, 550), dtype=np.uint8)
    cv2.fillPoly(mask, [np.asarray(((10, 20), (480, 120), (470, 220), (15, 130)), np.int32)], 3)
    editor = PolygonEditor()
    assert editor.select(mask, 200, 130)
    controls = editor.vertices.copy()
    exact = editor.outline_vertices.copy()
    original = mask.copy()
    # Choose a real pixel-boundary corner away from the reduced control cage.
    distances = [editor._closest_edge(*point)[0] for point in exact]
    point = exact[int(np.argmax(distances))]
    assert max(distances) > 0.2
    index = editor.insert_vertex(*point, tolerance=0.05)
    assert index is not None
    assert len(editor.vertices) == len(controls) + 1
    assert np.array_equal(np.delete(editor.vertices, index, axis=0), controls)
    assert np.array_equal(editor.outline_vertices, exact)
    assert not editor.apply(mask)
    assert np.array_equal(mask, original)
