import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
import pytest
from PyQt5.QtCore import QSettings

from core.similarity_fill import sample_lab_centers
from ui import main_window


@pytest.fixture
def windows(tmp_path, monkeypatch, qtbot):
    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.IniFormat)
    monkeypatch.setattr(main_window, "QSettings", lambda *args: settings)

    def create():
        window = main_window.MainWindow()
        qtbot.addWidget(window, before_close_func=lambda widget: widget.state.mark_saved())
        return window

    return create, settings


def test_enhanced_similarity_fill_preference_saves_and_restores(windows, monkeypatch):
    create, settings = windows
    window = create()
    assert not window.use_enhanced_fill_image
    window.state.fill_sample = np.zeros((1, 3), dtype=np.float32)
    dialog_values = []

    def save(dialog):
        control = dialog.chk_use_enhanced_fill_image
        dialog_values.append(control.isChecked())
        control.setChecked(True)
        dialog.btn_save.click()

    monkeypatch.setattr(main_window.SettingsDialog, "exec_", save)
    window._open_settings()
    assert dialog_values == [False]
    assert window.use_enhanced_fill_image and window.state.fill_sample is None
    assert settings.value("use_enhanced_fill_image", False, type=bool)

    def cancel(dialog):
        control = dialog.chk_use_enhanced_fill_image
        dialog_values.append(control.isChecked())
        control.setChecked(False)
        dialog.reject()

    restored = create()
    monkeypatch.setattr(main_window.SettingsDialog, "exec_", cancel)
    restored._open_settings()
    assert dialog_values == [False, True]
    assert restored.use_enhanced_fill_image
    assert settings.value("use_enhanced_fill_image", False, type=bool)


@pytest.mark.parametrize("enhanced", [False, True])
def test_click_fill_and_sampled_fill_use_the_selected_image(windows, enhanced):
    create, settings = windows
    if enhanced:
        settings.setValue("use_enhanced_fill_image", True)
    window = create()
    image = np.full((24, 36, 3), 180, dtype=np.uint8)
    image[:, :12] = 20
    image[:, 12:24] = 30
    original = image.copy()
    window.state.load_image_and_mask(image, None)
    window.show()
    window.btn_edit.click()
    window._refresh_display(reset_zoom=True)
    panel = window.edit_panel
    panel.slider_brightness.setValue(-40)

    expected_region = np.zeros(image.shape[:2], dtype=bool)
    expected_region[:, :(24 if enhanced else 12)] = True
    panel.btn_auto_fill.click()
    panel.slider_similarity.setValue(0)
    window._on_press(3, 3)
    np.testing.assert_array_equal(window.state.mask_img != 0, expected_region)
    window._undo()
    assert not np.any(window.state.mask_img)

    panel.btn_sample_fill.click()
    panel.slider_similarity.setValue(0)
    window._on_press(1, 1)
    window._on_move(8, 1)
    window._on_move(8, 10)
    window._on_release(1, 10)
    sample_rgb = np.full((1, 3), 0 if enhanced else 20, dtype=np.uint8)
    np.testing.assert_array_equal(window.state.fill_sample, sample_lab_centers(sample_rgb))

    window._on_press(0, 0)
    window._on_release(35, 23)
    np.testing.assert_array_equal(window.state.mask_img != 0, expected_region)
    panel.slider_contrast.setValue(90)
    assert (window.state.fill_sample is None) == enhanced
    np.testing.assert_array_equal(window.state.mask_img != 0, expected_region)
    np.testing.assert_array_equal(window.state.orig_img, original)
