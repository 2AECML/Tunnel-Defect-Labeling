import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
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
