import os

import cv2
import numpy as np
import pytest

from core.similarity_fill import (
    apply_similarity_fill, matching_sample_pixels, sample_lab_centers, similar_connected_region,
)


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


def test_sample_fill_uses_largest_new_component_in_rectangular_and_freehand_ranges(
    qtbot, monkeypatch, tmp_path,
):
    from PyQt5.QtCore import QPointF, QSettings, Qt
    from PyQt5.QtGui import QMouseEvent
    from PyQt5.QtWidgets import QApplication

    from ui import main_window

    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.IniFormat)
    monkeypatch.setattr(main_window, "QSettings", lambda *args: settings)
    window = main_window.MainWindow()
    qtbot.addWidget(window, before_close_func=lambda widget: widget.state.mark_saved())
    image = np.full((40, 40, 3), 220, dtype=np.uint8)
    dark = (40, 40, 40)
    warm = (20, 100, 180)
    image[2:4, 2:6:2] = image[4:6, 2] = dark
    image[2:4, 3:6:2] = image[4:6, 3] = warm
    image[10:13, 12:16] = dark
    image[10, 12] = warm  # 最大区域内包含两种代表色。
    image[11, 13] = (30, 70, 110)  # 介于两色之间，但超出两个中心的阈值。
    image[9, 13] = dark  # 与最大区域相邻，但在框外。
    image[13, 16] = warm  # 仅在对角处接触另一候选像素。
    image[28:30, 26:29] = warm
    image[33:37, 33:37] = warm  # 位于面状选区的凹口内。
    image[21:25, 20:25] = dark
    image[18, 21] = warm
    original_mask = np.zeros(image.shape[:2], dtype=np.uint8)
    original_mask[10:13, 14] = 2  # 已有同类标注隔开左右两片候选像素。
    original_mask[11, 15] = 3
    original_mask[18, 21] = 3
    original_mask[21:25, 20:25] = 2
    original_mask[23, 22] = 0  # 大片已有标注仅剩一个符合阈值的空白像素。
    window.state.load_image_and_mask(image, original_mask.copy())
    window.show()
    window.btn_edit.click()
    window._refresh_display(reset_zoom=True)
    panel = window.edit_panel
    panel.btn_sample_fill.click()
    panel.set_class_index(1)
    panel.slider_similarity.spin_value.setValue(1)
    QApplication.processEvents()
    view = window.viewer
    view.resetTransform()
    view.scale(4, 4)

    def mouse(kind, x, y):
        position = view.mapFromScene(QPointF(x + 0.5, y + 0.5))
        button = Qt.NoButton if kind == QMouseEvent.MouseMove else Qt.LeftButton
        buttons = Qt.NoButton if kind == QMouseEvent.MouseButtonRelease else Qt.LeftButton
        event = QMouseEvent(kind, QPointF(position), button, buttons, Qt.NoModifier)
        QApplication.sendEvent(view.viewport(), event)

    mouse(QMouseEvent.MouseButtonPress, 2, 2)
    for x, y in [(5, 2), (5, 3), (3, 3), (3, 5)]:
        mouse(QMouseEvent.MouseMove, x, y)
    assert view.stroke_item.path().elementCount() == 5
    assert view.stroke_item.brush().style() == Qt.NoBrush
    mouse(QMouseEvent.MouseButtonRelease, 2, 5)
    expected_centers = cv2.cvtColor(np.array([[dark, warm]], np.float32) / 255, cv2.COLOR_BGR2Lab)[0]
    centers = window.state.fill_sample
    np.testing.assert_allclose(centers[np.argsort(centers[:, 0])], expected_centers, atol=0.001)
    assert panel.btn_resample.isEnabled()
    assert not window.state.is_dirty and not window.state.can_undo()

    mouse(QMouseEvent.MouseButtonPress, 27, 29)
    mouse(QMouseEvent.MouseMove, 12, 10)
    assert view.stroke_item.isVisible()
    assert view.stroke_item.path().contains(QPointF(18, 18))
    np.testing.assert_array_equal(window.state.mask_img, original_mask)
    mouse(QMouseEvent.MouseButtonRelease, 12, 10)
    assert not view.stroke_item.isVisible()
    expected = original_mask.copy()
    expected[10:13, 12:14] = 2
    expected[11, 13] = 0
    np.testing.assert_array_equal(window.state.mask_img, expected)
    assert len(window.state.undo_stack) == 1

    panel.btn_undo.click()
    np.testing.assert_array_equal(window.state.mask_img, original_mask)
    mouse(QMouseEvent.MouseButtonPress, 16, 13)
    mouse(QMouseEvent.MouseButtonRelease, 22, 20)
    np.testing.assert_array_equal(window.state.mask_img, original_mask)
    assert not window.state.is_dirty and window.state.can_redo()
    panel.btn_redo.click()
    np.testing.assert_array_equal(window.state.mask_img, expected)

    mouse(QMouseEvent.MouseButtonPress, 27, 29)
    mouse(QMouseEvent.MouseButtonRelease, 12, 10)
    expected[28:30, 26:28] = 2
    np.testing.assert_array_equal(window.state.mask_img, expected)
    assert len(window.state.undo_stack) == 2

    mouse(QMouseEvent.MouseButtonPress, 25, 27)
    mouse(QMouseEvent.MouseMove, 37, 37)
    panel.combo_fill_range.setCurrentIndex(1)
    assert not window.engine.is_active and not view.stroke_item.isVisible()
    mouse(QMouseEvent.MouseButtonRelease, 37, 37)
    np.testing.assert_array_equal(window.state.mask_img, expected)
    np.testing.assert_array_equal(window.state.fill_sample, centers)

    mouse(QMouseEvent.MouseButtonPress, 25, 27)
    for x, y in [(37, 27), (37, 30), (30, 30), (30, 37)]:
        mouse(QMouseEvent.MouseMove, x, y)
    assert view.stroke_item.path().elementCount() == 5
    assert view.stroke_item.brush().style() == Qt.NoBrush
    np.testing.assert_array_equal(window.state.mask_img, expected)
    mouse(QMouseEvent.MouseButtonRelease, 25, 37)
    expected[28:30, 28] = 2
    np.testing.assert_array_equal(window.state.mask_img, expected)
    panel.btn_resample.click()
    assert window.state.fill_sample is None and not panel.btn_resample.isEnabled()
    np.testing.assert_array_equal(window.state.mask_img, expected)


def test_sample_fill_clips_ranges_and_resets_sample_when_loading_an_image():
    from core.annotation_state import AnnotationState
    from core.config import DrawTool
    from core.draw_engine import DrawEngine

    state = AnnotationState()
    image = np.full((4, 6, 3), 20, dtype=np.uint8)
    state.load_image_and_mask(image, None)
    state.tool = DrawTool.SAMPLE_FILL
    state.sample_fill_tolerance = 0
    engine = DrawEngine(state)
    engine.on_press(5, 3)
    engine.on_release(5, 3)
    assert state.fill_sample is None
    engine.on_press(5, 3)
    engine.on_move(6, 2)
    engine.on_release(7, 1)
    assert state.fill_sample is None
    engine.on_press(5, 3)
    engine.on_move(9, 2)
    engine.on_release(5, 1)
    assert state.fill_sample is not None
    engine.on_press(1, 1)
    assert engine.on_release(-2, -2) == 4
    assert np.all(state.mask_img[:2, :2] == state.current_draw_value)
    assert np.count_nonzero(state.mask_img) == 4
    state.load_image_and_mask(image.copy(), None)
    assert state.fill_sample is None


@pytest.mark.parametrize("freehand", [False, True], ids=["rectangle", "freehand"])
def test_sample_fill_fills_only_enclosed_background_in_the_largest_region(freehand):
    from core.annotation_state import AnnotationState
    from core.config import DrawTool
    from core.draw_engine import DrawEngine

    image = np.full((20, 24, 3), 200, dtype=np.uint8)
    image[3:14, 3:16] = 50
    image[6:10, 6:10] = 200  # 完全封闭、色差超出阈值。
    image[3:8, 12] = 200  # 与外部相通的凹口。
    image[3, 3] = image[4, 4] = 200  # 对角方向相通。
    image[15:18, 17:20] = 50  # 面积较小的独立区域。
    mask = np.zeros(image.shape[:2], dtype=np.uint8)
    mask[7, 7] = mask[3, 12] = 3
    state = AnnotationState()
    state.load_image_and_mask(image, mask.copy())
    state.tool = DrawTool.SAMPLE_FILL
    state.fill_freehand = freehand
    state.fill_sample = sample_lab_centers(image[3, 4:5])
    state.sample_fill_tolerance = 0

    engine = DrawEngine(state)
    engine.on_press(1, 1)
    if freehand:
        for x, y in [(22, 1), (22, 12), (20, 12), (20, 19)]:
            engine.on_move(x, y)
        count = engine.on_release(1, 19)
    else:
        count = engine.on_release(22, 19)

    expected = mask.copy()
    expected[3:14, 3:16] = state.current_draw_value
    expected[3:8, 12] = 0
    expected[3, 3] = expected[4, 4] = 0
    expected[mask != 0] = mask[mask != 0]
    assert count == np.count_nonzero(expected != mask)
    np.testing.assert_array_equal(state.mask_img, expected)
    assert state.pop_undo() and not state.can_undo()
    np.testing.assert_array_equal(state.mask_img, mask)
    assert state.pop_redo()
    np.testing.assert_array_equal(state.mask_img, expected)


def test_sample_lab_centers_discards_a_rare_color_cluster():
    pixels = np.array([(50, 50, 50)] * 19 + [(20, 100, 180)], dtype=np.uint8)
    centers = sample_lab_centers(pixels)
    assert centers.shape == (1, 3)
    matches = matching_sample_pixels(pixels[None, :, :], centers, tolerance=1)
    assert matches[0, :-1].all()
    assert not matches[0, -1]
