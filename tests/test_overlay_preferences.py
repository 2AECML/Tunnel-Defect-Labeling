import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
import pytest
from PyQt5.QtCore import QEvent, QSettings, Qt, QTimer
from PyQt5.QtGui import QKeyEvent, QKeySequence
from PyQt5.QtWidgets import QApplication, QDialog, QLineEdit

from core.config import DEFAULT_FILL_TOLERANCE, DrawTool
from ui import main_window
from ui.settings_dialog import SettingsDialog


@pytest.fixture
def windows(tmp_path, monkeypatch, qtbot):
    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.IniFormat)
    monkeypatch.setattr(main_window, "QSettings", lambda *args: settings)

    def create():
        window = main_window.MainWindow()
        qtbot.addWidget(window, before_close_func=lambda widget: widget.state.mark_saved())
        window.show()
        window.activateWindow()
        window.viewer.setFocus()
        QApplication.processEvents()
        return window

    return create, settings


def _assert_visible(window, visible):
    assert window.state.is_mask_visible == visible
    assert window.btn_mask_vis.isChecked() == visible
    assert window.viewer.overlay_item.isVisible() == visible


@pytest.mark.parametrize("initial", [True, False])
def test_default_c_hold_inverts_and_restores_exact_state(windows, qtbot, initial):
    window = windows[0]()
    assert window.mask_shortcut == "C"
    assert window.mask_shortcut_mode == "hold"
    window._set_mask_visible(initial)
    qtbot.keyPress(window.viewer, Qt.Key_C)
    _assert_visible(window, not initial)
    repeated = QKeyEvent(QEvent.KeyPress, Qt.Key_C, Qt.NoModifier, "c", True)
    QApplication.sendEvent(window.viewer, repeated)
    _assert_visible(window, not initial)
    QApplication.sendEvent(window.viewer, QKeyEvent(QEvent.KeyRelease, Qt.Key_C, Qt.NoModifier, "c", True))
    _assert_visible(window, not initial)
    qtbot.keyRelease(window.viewer, Qt.Key_C)
    _assert_visible(window, initial)


def test_toggle_mode_changes_once_per_press_and_ignores_repeat(windows, qtbot):
    window = windows[0]()
    assert window._apply_overlay_settings("toggle", "C")
    qtbot.keyPress(window.viewer, Qt.Key_C)
    _assert_visible(window, False)
    for _ in range(3):
        QApplication.sendEvent(window.viewer, QKeyEvent(QEvent.KeyPress, Qt.Key_C, Qt.NoModifier, "c", True))
    _assert_visible(window, False)
    qtbot.keyRelease(window.viewer, Qt.Key_C)
    _assert_visible(window, False)
    qtbot.keyClick(window.viewer, Qt.Key_C)
    _assert_visible(window, True)


def test_custom_combination_requires_modifiers_and_restores_if_modifier_released_first(windows, qtbot):
    window = windows[0]()
    assert window._apply_overlay_settings("hold", "Ctrl+K")
    qtbot.keyClick(window.viewer, Qt.Key_C)
    qtbot.keyClick(window.viewer, Qt.Key_K)
    _assert_visible(window, True)
    qtbot.keyPress(window.viewer, Qt.Key_K, Qt.ControlModifier)
    _assert_visible(window, False)
    qtbot.keyRelease(window.viewer, Qt.Key_Control)
    _assert_visible(window, True)
    qtbot.keyRelease(window.viewer, Qt.Key_K)


def test_hold_restores_after_application_loses_focus(windows, qtbot, qapp):
    window = windows[0]()
    qtbot.keyPress(window.viewer, Qt.Key_C)
    _assert_visible(window, False)
    QApplication.sendEvent(qapp, QEvent(QEvent.ApplicationDeactivate))
    _assert_visible(window, True)
    qtbot.keyRelease(window.viewer, Qt.Key_C)
    _assert_visible(window, True)


def test_changing_binding_during_hold_restores_then_uses_new_key(windows, qtbot):
    window = windows[0]()
    qtbot.keyPress(window.viewer, Qt.Key_C)
    assert window._apply_overlay_settings("toggle", "V")
    _assert_visible(window, True)
    qtbot.keyRelease(window.viewer, Qt.Key_C)
    qtbot.keyClick(window.viewer, Qt.Key_C)
    _assert_visible(window, True)
    qtbot.keyClick(window.viewer, Qt.Key_V)
    _assert_visible(window, False)


def test_mouse_button_works_in_both_modes(windows, qtbot):
    window = windows[0]()
    for mode in ("hold", "toggle"):
        window._apply_overlay_settings(mode, "C")
        window._set_mask_visible(True)
        window.btn_mask_vis.click()
        _assert_visible(window, False)
        window.btn_mask_vis.click()
        _assert_visible(window, True)
    window._apply_overlay_settings("hold", "C")
    qtbot.keyPress(window.viewer, Qt.Key_C)
    window.btn_mask_vis.click()
    qtbot.keyRelease(window.viewer, Qt.Key_C)
    _assert_visible(window, True)


def test_shortcut_works_with_edit_panel_focus_but_not_text_inputs(windows, qtbot):
    window = windows[0]()
    window.btn_edit.click()
    panel = window.edit_panel
    panel.activateWindow()
    panel.btn_auto_fill.setFocus()
    QApplication.processEvents()
    qtbot.keyPress(panel.btn_auto_fill, Qt.Key_C)
    _assert_visible(window, False)
    qtbot.keyRelease(panel.btn_auto_fill, Qt.Key_C)
    _assert_visible(window, True)
    text = QLineEdit(panel)
    text.show()
    text.setFocus()
    qtbot.keyClick(text, Qt.Key_C)
    assert text.text() == "c"
    _assert_visible(window, True)


def test_input_recording_modal_and_other_windows_do_not_toggle_overlay(windows, qtbot):
    window = windows[0]()
    dialog = SettingsDialog(parent=window)
    qtbot.addWidget(dialog)
    dialog.show()
    dialog.activateWindow()
    dialog.key_mask_shortcut.setFocus()
    qtbot.keyClick(dialog.key_mask_shortcut, Qt.Key_C)
    _assert_visible(window, True)
    dialog.close()
    other = QDialog()
    qtbot.addWidget(other)
    other.show()
    qtbot.keyClick(other, Qt.Key_C)
    _assert_visible(window, True)


@pytest.mark.parametrize("action", ["save", "cancel", "close"])
def test_settings_persist_only_on_save_without_reloading_images(windows, qtbot, monkeypatch, action):
    create, settings = windows
    window = create()
    monkeypatch.setattr(window, "_scan_images", lambda: pytest.fail("快捷键设置不应重新加载图片"))
    monkeypatch.setattr(window, "_confirm_save_if_dirty", lambda: pytest.fail("快捷键设置不应打断未保存编辑"))

    def interact():
        dialog = QApplication.activeModalWidget()
        try:
            assert dialog.overlay_values() == ("hold", "C")
            dialog.combo_mask_shortcut_mode.setCurrentIndex(1)
            dialog.key_mask_shortcut.setKeySequence(QKeySequence("Ctrl+K"))
            if action == "save":
                dialog.btn_save.click()
            elif action == "cancel":
                dialog.btn_cancel.click()
            else:
                dialog.close()
        except BaseException:
            dialog.reject()
            raise

    QTimer.singleShot(0, interact)
    window._open_settings()
    expected = ("toggle", "Ctrl+K") if action == "save" else ("hold", "C")
    assert (window.mask_shortcut_mode, window.mask_shortcut) == expected
    assert settings.value("mask_shortcut_mode", "hold") == expected[0]
    assert settings.value("mask_shortcut", "C") == expected[1]
    restored = create()
    assert (restored.mask_shortcut_mode, restored.mask_shortcut) == expected
    assert expected[1] in restored.btn_mask_vis.toolTip()
    monkeypatch.setattr(window, "_confirm_save_if_dirty", lambda: True)


@pytest.mark.parametrize("shortcut", ["", "Ctrl+S", "D", "Ctrl+K, Ctrl+C"])
def test_empty_conflicting_or_multi_step_binding_cannot_be_saved(qtbot, shortcut):
    dialog = SettingsDialog()
    qtbot.addWidget(dialog)
    dialog.key_mask_shortcut.setKeySequence(QKeySequence(shortcut))
    assert not dialog.validate_overlay_shortcut()
    assert not dialog.btn_save.isEnabled()
    assert dialog.lbl_shortcut_error.text()
    dialog.btn_reset_shortcut.click()
    assert dialog.overlay_values() == ("hold", "C")
    assert dialog.btn_save.isEnabled()


def test_shortcut_can_be_recorded_by_keyboard_before_save(qtbot):
    dialog = SettingsDialog()
    qtbot.addWidget(dialog)
    dialog.show()
    dialog.key_mask_shortcut.setFocus()
    qtbot.keyClick(dialog.key_mask_shortcut, Qt.Key_K, Qt.ControlModifier)
    assert dialog.validate_overlay_shortcut()
    assert dialog.overlay_values() == ("hold", "Ctrl+K")


def test_invalid_remembered_overlay_preferences_fall_back_to_defaults(windows):
    create, settings = windows
    settings.setValue("mask_shortcut_mode", "unknown")
    settings.setValue("mask_shortcut", "Ctrl+S")
    window = create()
    assert (window.mask_shortcut_mode, window.mask_shortcut) == ("hold", "C")


@pytest.mark.parametrize("value,expected", [(73, 73), (-5, 0), (120, 100), ("bad", DEFAULT_FILL_TOLERANCE)])
def test_tolerance_restores_with_validation(windows, value, expected):
    create, settings = windows
    settings.setValue("fill_tolerance", value)
    window = create()
    assert window.state.fill_tolerance == expected
    window.btn_edit.click()
    assert window.edit_panel.slider_similarity.value() == expected
    assert window.edit_panel.slider_similarity.spin_value.value() == expected


def test_tolerance_manual_input_slider_and_reopened_window_stay_in_sync(windows, qtbot):
    create, settings = windows
    window = create()
    window.btn_edit.click()
    panel = window.edit_panel
    panel.btn_auto_fill.click()
    spin = panel.slider_similarity.spin_value
    spin.setFocus()
    spin.selectAll()
    qtbot.keyClicks(spin, "67")
    qtbot.keyClick(spin, Qt.Key_Return)
    assert window.state.fill_tolerance == 67
    assert panel.slider_similarity.value() == 67
    assert settings.value("fill_tolerance", type=int) == 67
    panel.slider_similarity.slider.setValue(42)
    assert spin.value() == 42
    assert window.state.fill_tolerance == 42
    panel.btn_line.click()
    panel.btn_auto_fill.click()
    assert spin.value() == 42
    spin.clearFocus()
    window.activateWindow()
    window.viewer.setFocus()
    QApplication.processEvents()
    qtbot.keyClick(window, Qt.Key_BracketRight)
    assert spin.value() == 43
    assert settings.value("fill_tolerance", type=int) == 43
    restored = create()
    restored.btn_edit.click()
    assert restored.state.fill_tolerance == 43
    assert restored.edit_panel.slider_similarity.spin_value.value() == 43


def test_fill_uses_manually_entered_tolerance(windows):
    window = windows[0]()
    image = np.zeros((16, 30, 3), np.uint8)
    image[:, 15:] = 40
    window.state.load_image_and_mask(image, None)
    window.btn_edit.click()
    window.edit_panel.btn_auto_fill.click()
    spin = window.edit_panel.slider_similarity.spin_value
    spin.setValue(0)
    window._on_press(1, 1)
    assert not np.any(window.state.mask_img[:, 15:])
    window._undo()
    spin.setValue(50)
    window._on_press(1, 1)
    assert np.all(window.state.mask_img != 0)


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_tolerance_step_buttons_change_and_remember_value(windows, qtbot, theme):
    from PyQt5.QtWidgets import QStyle, QStyleOptionSpinBox

    create, settings = windows
    window = create()
    window._theme_name = theme
    window._apply_theme()
    window.btn_edit.click()
    window.edit_panel.btn_auto_fill.click()
    spin = window.edit_panel.slider_similarity.spin_value
    spin.setValue(50)
    QApplication.processEvents()
    option = QStyleOptionSpinBox()
    spin.initStyleOption(option)
    up = spin.style().subControlRect(QStyle.CC_SpinBox, option, QStyle.SC_SpinBoxUp, spin)
    down = spin.style().subControlRect(QStyle.CC_SpinBox, option, QStyle.SC_SpinBoxDown, spin)
    assert up.width() >= 20 and up.height() >= 14
    assert down.width() >= 20 and down.height() >= 14
    qtbot.mouseClick(spin, Qt.LeftButton, pos=up.center())
    assert spin.value() == window.state.fill_tolerance == 51
    assert window.edit_panel.slider_similarity.value() == 51
    assert settings.value("fill_tolerance", type=int) == 51
    qtbot.mouseClick(spin, Qt.LeftButton, pos=down.center())
    assert spin.value() == window.state.fill_tolerance == 50
    assert settings.value("fill_tolerance", type=int) == 50
    for limit, button in ((100, up), (0, down)):
        spin.setValue(limit)
        qtbot.mouseClick(spin, Qt.LeftButton, pos=button.center())
        assert spin.value() == limit


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_tolerance_click_selects_all_and_each_digit_applies_immediately(windows, qtbot, theme):
    create, settings = windows
    window = create()
    window._theme_name = theme
    window._apply_theme()
    window.btn_edit.click()
    window.edit_panel.btn_auto_fill.click()
    field = window.edit_panel.slider_similarity
    spin = field.spin_value
    editor = spin.lineEdit()
    spin.setValue(73)
    QApplication.processEvents()

    def click_and_type(digits, values):
        old_text = editor.text()
        qtbot.mouseClick(editor, Qt.LeftButton, pos=editor.rect().center())
        assert editor.selectedText() == old_text
        for digit, value in zip(digits, values):
            qtbot.keyClicks(editor, digit)
            assert spin.value() == field.value() == window.state.fill_tolerance == value
            assert settings.value("fill_tolerance", type=int) == value

    click_and_type("67", (6, 67))
    click_and_type("0", (0,))  # 已有焦点时再次点击仍全选，零值也立即生效。
    click_and_type("100", (1, 10, 100))


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_tolerance_padding_and_edges_focus_and_select_all_except_step_buttons(windows, qtbot, theme):
    from PyQt5.QtCore import QPoint
    from PyQt5.QtWidgets import QStyle, QStyleOptionSpinBox

    window = windows[0]()
    window._theme_name = theme
    window._apply_theme()
    window.btn_edit.click()
    window.edit_panel.btn_auto_fill.click()
    field = window.edit_panel.slider_similarity
    spin = field.spin_value
    QApplication.processEvents()
    option = QStyleOptionSpinBox()
    spin.initStyleOption(option)
    buttons = [spin.style().subControlRect(QStyle.CC_SpinBox, option, control, spin)
               for control in (QStyle.SC_SpinBoxUp, QStyle.SC_SpinBoxDown)]
    for x in (0, 2, spin.width() // 2, buttons[0].left() - 2, spin.width() - 1):
        for y in (0, 2, spin.height() // 2, spin.height() - 3, spin.height() - 1):
            point = QPoint(x, y)
            if any(button.contains(point) for button in buttons):
                continue
            spin.setValue(73)
            spin.lineEdit().deselect()
            spin.lineEdit().clearFocus()
            qtbot.mouseClick(spin, Qt.LeftButton, pos=point)
            # Qt 在部分平台由 SpinBox 代理内部编辑器焦点，两者均应可直接输入。
            assert spin.window().focusWidget() in (spin, spin.lineEdit())
            assert spin.lineEdit().selectedText() == "73"
            qtbot.keyClicks(spin, "6")
            assert spin.value() == field.value() == window.state.fill_tolerance == 6
    spin.setValue(50)
    qtbot.mouseClick(spin, Qt.LeftButton, pos=buttons[0].center())
    assert spin.value() == 51
    qtbot.mouseClick(spin, Qt.LeftButton, pos=buttons[1].center())
    assert spin.value() == 50
