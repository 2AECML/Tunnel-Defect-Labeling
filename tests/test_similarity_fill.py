import os

import cv2
import numpy as np

from core.similarity_fill import apply_similarity_fill, similar_connected_region


def _image():
    image = np.full((32, 48, 3), 200, dtype=np.uint8)
    image[4:28, 4:28] = 50
    return image


def _assert_solid_connected(region):
    count, _ = cv2.connectedComponents(region.astype(np.uint8), connectivity=8)
    assert count == 2
    _, hierarchy = cv2.findContours(
        region.astype(np.uint8), cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE
    )
    assert np.all(hierarchy[0, :, 3] == -1)


def test_fills_isolated_empty_pixels_and_large_internal_holes():
    image = _image()
    image[7, 7] = 200
    image[10:22, 10:22] = 200
    region = similar_connected_region(image, 5, 5, 20)
    expected = np.zeros(image.shape[:2], dtype=bool)
    expected[4:28, 4:28] = True
    assert np.array_equal(region, expected)
    _assert_solid_connected(region)


def test_bridges_one_and_two_pixel_gaps_before_selecting_component():
    for gap in (1, 2):
        image = _image()
        image[4:28, 14:14 + gap] = 200
        region = similar_connected_region(image, 5, 5, 20)
        assert np.all(region[4:28, 4:28])
        _assert_solid_connected(region)


def test_leaves_wide_external_notches_and_distant_regions_unfilled():
    image = _image()
    image[4:18, 12:18] = 200
    image[4:28, 36:44] = 50
    region = similar_connected_region(image, 5, 5, 20)
    assert not np.any(region[4:18, 12:18])
    assert not np.any(region[:, 36:44])
    _assert_solid_connected(region)


def test_does_not_cross_wide_colour_barrier():
    image = _image()
    image[4:28, 14:18] = 200
    region = similar_connected_region(image, 5, 5, 20)
    assert np.all(region[4:28, 4:14])
    assert not np.any(region[:, 14:])


def test_preserves_regions_touching_image_edges():
    image = np.full((20, 30), 200, dtype=np.uint8)
    image[:15, :18] = 50
    image[4:10, 5:12] = 200
    expected = np.zeros(image.shape, dtype=bool)
    expected[:15, :18] = True
    assert np.array_equal(similar_connected_region(image, 0, 0, 20), expected)
    image[:] = 50
    assert np.all(similar_connected_region(image, 0, 0, 20))


def test_keeps_single_pixel_and_narrow_line_regions():
    image = np.full((12, 12), 200, dtype=np.uint8)
    image[5, 5] = 50
    assert similar_connected_region(image, 5, 5, 0).sum() == 1
    image[5, 3:10] = 50
    assert similar_connected_region(image, 5, 5, 0).sum() == 7


def test_colour_tolerance_stays_relative_to_seed():
    image = np.full((12, 24, 3), 200, dtype=np.uint8)
    for left, value in ((2, 50), (6, 60), (10, 70), (14, 80)):
        image[2:10, left:left + 4] = value
    region = similar_connected_region(image, 3, 3, 20)
    assert np.all(region[2:10, 2:14])
    assert not np.any(region[:, 14:])
    exact = similar_connected_region(image, 3, 3, 0)
    assert np.all(exact[2:10, 2:6])
    assert not np.any(exact[:, 6:])


def test_checks_every_colour_channel():
    image = np.full((12, 18, 3), 200, dtype=np.uint8)
    image[2:10, 2:7] = (50, 60, 70)
    image[2:10, 7:12] = (50, 60, 100)
    region = similar_connected_region(image, 3, 3, 20)
    assert np.all(region[2:10, 2:7])
    assert not np.any(region[:, 7:])


def test_fill_count_includes_holes_and_source_is_unchanged():
    image = _image()
    image[10:22, 10:22] = 200
    original = image.copy()
    mask = np.zeros(image.shape[:2], dtype=np.uint8)
    mask[6, 6] = 3
    mask[15, 15] = 2
    mask[30, 40] = 2
    assert apply_similarity_fill(image, mask, 5, 5, 3, 20) == 24 * 24 - 2
    expected = np.full((24, 24), 3, dtype=np.uint8)
    expected[11, 11] = 2
    assert np.array_equal(mask[4:28, 4:28], expected)
    assert mask[30, 40] == 2
    assert apply_similarity_fill(image, mask, 5, 5, 3, 20) == 0
    assert np.array_equal(image, original)


def test_existing_annotation_blocks_fill_even_with_matching_colour_and_class():
    for value in (2, 3):
        for width in (1, 2):
            image = np.full((20, 30, 3), 50, dtype=np.uint8)
            mask = np.zeros(image.shape[:2], dtype=np.uint8)
            mask[:, 14:14 + width] = value
            original = mask.copy()
            assert apply_similarity_fill(image, mask, 3, 10, 3, 255) == 20 * 14
            assert np.all(mask[:, :14] == 3)
            assert np.array_equal(mask[:, 14:], original[:, 14:])


def test_closed_polygon_stops_inside_fill_from_reaching_outside():
    image = np.full((30, 30, 3), 50, dtype=np.uint8)
    mask = np.zeros(image.shape[:2], dtype=np.uint8)
    cv2.rectangle(mask, (6, 6), (23, 23), 2, 1)
    original = mask.copy()
    assert apply_similarity_fill(image, mask, 10, 10, 3, 20) == 16 * 16
    expected = original.copy()
    expected[7:23, 7:23] = 3
    assert np.array_equal(mask, expected)


def test_hole_filling_does_not_jump_into_an_existing_polygon_enclosure():
    image = np.full((30, 30, 3), 50, dtype=np.uint8)
    mask = np.zeros(image.shape[:2], dtype=np.uint8)
    cv2.rectangle(mask, (6, 6), (23, 23), 2, 1)
    original = mask.copy()
    apply_similarity_fill(image, mask, 0, 0, 3, 20)
    assert np.array_equal(mask[6:24, 6:24], original[6:24, 6:24])
    assert mask[0, 0] == 3


def test_diagonal_polygon_boundary_does_not_leak_at_corners():
    image = np.full((31, 31, 3), 50, dtype=np.uint8)
    mask = np.zeros(image.shape[:2], dtype=np.uint8)
    vertices = np.asarray(((15, 3), (27, 15), (15, 27), (3, 15)), np.int32)
    cv2.polylines(mask, [vertices], True, 2, 1)
    original = mask.copy()
    apply_similarity_fill(image, mask, 15, 15, 3, 20)
    assert mask[15, 15] == 3
    assert not np.any(mask[0, :])
    assert not np.any(mask[-1, :])
    assert not np.any(mask[:, 0])
    assert not np.any(mask[:, -1])
    assert np.array_equal(mask[original != 0], original[original != 0])


def test_unlabelled_holes_and_small_gaps_still_fill_on_seed_side_of_boundary():
    image = np.full((32, 48, 3), 50, dtype=np.uint8)
    image[8:20, 6:15] = 200
    image[:, 18:20] = 200
    mask = np.zeros(image.shape[:2], dtype=np.uint8)
    mask[:, 28] = 2
    apply_similarity_fill(image, mask, 3, 3, 3, 20)
    assert np.all(mask[:, :28] == 3)
    assert np.all(mask[:, 28] == 2)
    assert not np.any(mask[:, 29:])


def test_clicking_existing_annotation_is_noop_for_any_class():
    image = _image()
    mask = np.zeros(image.shape[:2], dtype=np.uint8)
    mask[4:28, 4:28] = 2
    original = mask.copy()
    for value in (2, 3):
        assert apply_similarity_fill(image, mask, 5, 5, value, 20) == 0
        assert np.array_equal(mask, original)


def test_clicking_polygon_fills_all_holes_with_its_original_class():
    image = np.full((40, 60, 3), 200, dtype=np.uint8)
    mask = np.zeros(image.shape[:2], dtype=np.uint8)
    mask[4:36, 4:36] = 2
    mask[8, 8] = 0
    mask[12:28, 12:28] = 0
    original_image = image.copy()
    assert apply_similarity_fill(image, mask, 5, 5, 3, 0) == 1 + 16 * 16
    assert np.all(mask[4:36, 4:36] == 2)
    assert not np.any(mask[:, 36:])
    assert np.array_equal(image, original_image)
    assert apply_similarity_fill(image, mask, 5, 5, 3, 100) == 0


def test_polygon_repair_preserves_other_classes_and_unselected_polygons():
    image = np.zeros((40, 64, 3), dtype=np.uint8)
    mask = np.zeros(image.shape[:2], dtype=np.uint8)
    mask[4:36, 4:32] = 2
    mask[10:25, 10:25] = 0
    mask[14:18, 14:18] = 3
    # 附近同类别的独立多边形也有孔洞，不能跟随一起补齐。
    mask[4:36, 34:60] = 2
    mask[10:25, 40:50] = 0
    original = mask.copy()
    assert apply_similarity_fill(image, mask, 5, 5, 1, 255) == 15 * 15 - 4 * 4
    assert np.all(mask[14:18, 14:18] == 3)
    assert np.array_equal(mask[:, 32:], original[:, 32:])
    assert not np.any(mask[:4, :])
    assert not np.any(mask[36:, :])


def test_polygon_repair_closes_thin_cracks_but_keeps_wide_openings():
    for gap in (1, 2):
        image = _image()
        mask = np.zeros(image.shape[:2], dtype=np.uint8)
        mask[4:28, 4:28] = 2
        mask[4:20, 14:14 + gap] = 0
        assert apply_similarity_fill(image, mask, 5, 5, 3, 0) == 16 * gap
        assert np.all(mask[4:28, 4:28] == 2)
        assert not np.any(mask[:4, :])
    mask[4:20, 12:18] = 0
    original = mask.copy()
    assert apply_similarity_fill(image, mask, 5, 5, 3, 0) == 0
    assert np.array_equal(mask, original)


def test_polygon_repair_fills_diagonal_outline_without_expanding_outside():
    image = np.zeros((31, 31, 3), dtype=np.uint8)
    mask = np.zeros(image.shape[:2], dtype=np.uint8)
    vertices = np.asarray(((15, 3), (27, 15), (15, 27), (3, 15)), np.int32)
    cv2.polylines(mask, [vertices], True, 2, 1)
    expected = np.zeros_like(mask)
    cv2.fillPoly(expected, [vertices], 2)
    assert apply_similarity_fill(image, mask, 15, 3, 3, 0) > 0
    assert np.array_equal(mask, expected)


def test_polygon_repair_at_image_border_and_with_degenerate_components():
    image = np.zeros((20, 30, 3), dtype=np.uint8)
    mask = np.zeros(image.shape[:2], dtype=np.uint8)
    mask[:15, :18] = 2
    mask[4:10, 5:12] = 0
    assert apply_similarity_fill(image, mask, 0, 0, 3, 0) == 6 * 7
    assert np.all(mask[:15, :18] == 2)
    assert not np.any(mask[:, 18:])
    mask[:] = 0
    mask[5, 5] = 2
    assert apply_similarity_fill(image, mask, 5, 5, 3, 0) == 0
    mask[5, 3:10] = 2
    assert apply_similarity_fill(image, mask, 5, 5, 3, 0) == 0


def test_ui_fill_can_be_undone_and_repeated_click_is_noop():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PyQt5.QtWidgets import QApplication
    from core.config import DrawTool
    from ui.main_window import MainWindow

    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    try:
        image = _image()
        image[10:22, 10:22] = 200
        window.state.load_image_and_mask(image, None)
        window.state.tool = DrawTool.AUTO_FILL
        window._on_press(5, 5)
        value = window.state.current_draw_value
        assert np.all(window.state.mask_img[4:28, 4:28] == value)
        assert window.state.is_dirty
        assert len(window.state.undo_stack) == 1
        window._on_press(5, 5)
        assert len(window.state.undo_stack) == 1
        assert window.state.pop_undo()
        assert not np.any(window.state.mask_img)
        assert not window.state.is_dirty
    finally:
        window.state.mark_saved()
        window.deleteLater()
        app.processEvents()


def test_ui_respects_existing_polygon_boundary_and_undo_restores_it():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PyQt5.QtWidgets import QApplication
    from core.config import DrawTool
    from ui.main_window import MainWindow

    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    try:
        image = np.full((20, 30, 3), 50, dtype=np.uint8)
        mask = np.zeros(image.shape[:2], dtype=np.uint8)
        mask[:, 14] = 2
        original = mask.copy()
        window.state.load_image_and_mask(image, mask)
        window.state.tool = DrawTool.AUTO_FILL
        window._on_press(14, 10)
        assert not window.state.is_dirty
        assert not window.state.undo_stack
        window._on_press(3, 10)
        assert np.all(window.state.mask_img[:, :14] == window.state.current_draw_value)
        assert np.array_equal(window.state.mask_img[:, 14:], original[:, 14:])
        assert len(window.state.undo_stack) == 1
        assert window.state.pop_undo()
        assert np.array_equal(window.state.mask_img, original)
        assert not window.state.is_dirty
    finally:
        window.state.mark_saved()
        window.deleteLater()
        app.processEvents()


def test_ui_clicking_existing_polygon_repairs_holes_and_can_be_undone():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PyQt5.QtWidgets import QApplication
    from core.config import DrawTool
    from ui.main_window import MainWindow

    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    try:
        image = _image()
        mask = np.zeros(image.shape[:2], dtype=np.uint8)
        mask[4:28, 4:28] = 2
        mask[10:22, 10:22] = 0
        mask[15, 15] = 3
        original = mask.copy()
        window.state.load_image_and_mask(image, mask)
        window.state.tool = DrawTool.AUTO_FILL
        assert window.state.current_draw_value != 2
        window._on_press(5, 5)
        expected = original.copy()
        expected[4:28, 4:28][expected[4:28, 4:28] == 0] = 2
        assert np.array_equal(window.state.mask_img, expected)
        assert window.state.is_dirty
        assert len(window.state.undo_stack) == 1
        window._on_press(5, 5)
        assert len(window.state.undo_stack) == 1
        assert window.state.pop_undo()
        assert np.array_equal(window.state.mask_img, original)
        assert not window.state.is_dirty
    finally:
        window.state.mark_saved()
        window.deleteLater()
        app.processEvents()
