"""撤销/重做的历史分支与可配置快捷键的用户操作回归。"""

import json
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
import pytest
from PyQt5.QtCore import QSettings, Qt, QTimer
from PyQt5.QtGui import QKeySequence
from PyQt5.QtWidgets import QApplication, QDialog, QLineEdit

from core.annotation_state import AnnotationState
from core.config import DrawTool, MAX_UNDO
from core.draw_engine import DrawEngine
from ui import main_window
from ui.settings_dialog import SettingsDialog
from ui.shortcuts import DEFAULT_SHORTCUTS, SHORTCUTS, normalize_shortcut


def state_and_engine():
    state = AnnotationState()
    state.load_image_and_mask(np.zeros((64, 64, 3), np.uint8), None)
    return state, DrawEngine(state)


def stroke(engine, x):
    engine.on_press(x, x)
    engine.on_move(x + 5, x + 5)
    engine.on_release(x + 5, x + 5)


def test_multiple_undo_redo_round_trips_preserve_pixels_and_saved_state():
    state, engine = state_and_engine()
    snapshots = [state.mask_img.copy()]
    for x in (5, 20, 40):
        stroke(engine, x)
        snapshots.append(state.mask_img.copy())
    state.mark_saved()
    for expected in reversed(snapshots[:-1]):
        assert state.pop_undo()
        assert np.array_equal(state.mask_img, expected)
        assert state.is_dirty
    assert not state.pop_undo()
    for expected in snapshots[1:]:
        assert state.pop_redo()
        assert np.array_equal(state.mask_img, expected)
    assert not state.is_dirty
    assert not state.pop_redo()
    assert state.pop_undo()
    assert state.pop_redo()
    assert not state.is_dirty


def test_new_branch_discards_redo_and_does_not_reuse_saved_revision():
    state, engine = state_and_engine()
    stroke(engine, 5)
    state.mark_saved()
    saved_revision = state.saved_revision
    assert state.pop_undo()
    stroke(engine, 30)
    assert not state.can_redo()
    assert state.edit_revision != saved_revision
    assert state.is_dirty


def test_cancelled_stroke_preserves_existing_redo_and_is_not_redone():
    state, engine = state_and_engine()
    stroke(engine, 5)
    completed = state.mask_img.copy()
    state.pop_undo()
    engine.on_press(30, 30)
    engine.on_move(45, 45)
    engine.cancel()
    assert not state.is_dirty
    assert not state.can_undo()
    assert state.can_redo()
    assert state.pop_redo()
    assert np.array_equal(state.mask_img, completed)


@pytest.mark.parametrize("reset", ["reset_mask", "load_image_and_mask"])
def test_image_changes_clear_both_histories(reset):
    state, engine = state_and_engine()
    stroke(engine, 5)
    stroke(engine, 20)
    state.pop_undo()
    if reset == "reset_mask":
        state.reset_mask()
    else:
        state.load_image_and_mask(np.zeros((16, 16, 3), np.uint8), None)
    assert not state.can_undo()
    assert not state.can_redo()


def test_redo_respects_history_limit():
    state, engine = state_and_engine()
    for _ in range(MAX_UNDO + 5):
        stroke(engine, 5)
    for _ in range(MAX_UNDO):
        assert state.pop_undo()
    assert not state.can_undo()
    for _ in range(MAX_UNDO):
        assert state.pop_redo()
    assert len(state.undo_stack) == MAX_UNDO
    assert not state.can_redo()


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


@pytest.mark.parametrize("tool", [DrawTool.LINE, DrawTool.POLY, DrawTool.ERASER,
                                 DrawTool.RECT_ERASER, DrawTool.POLY_ERASER,
                                 DrawTool.AUTO_FILL, DrawTool.EDIT_POLY])
def test_default_redo_key_and_button_restore_real_edits(windows, qtbot, tool):
    window = windows[0]()
    window.state.load_image_and_mask(np.zeros((64, 64, 3), np.uint8), None)
    window.btn_edit.click()
    panel = window.edit_panel
    window.state.tool = tool
    window.viewer.setFocus()
    if tool in DrawTool.ERASERS:
        window.state.mask_img[:] = 1
    if tool == DrawTool.EDIT_POLY:
        window.state.mask_img[10:35, 10:35] = 1
        assert window.polygon_editor.select(window.state.mask_img, 20, 20)
    original = window.state.mask_img.copy()
    if tool == DrawTool.EDIT_POLY:
        window._delete_selected_polygon()
    else:
        window._on_press(15, 15)
        window._on_move(30, 15)
        window._on_move(30, 30)
        window._on_release(30, 30)
    completed = window.state.mask_img.copy()
    assert not np.array_equal(original, completed)
    qtbot.keyClick(window.viewer, Qt.Key_Z, Qt.ControlModifier)
    assert np.array_equal(window.state.mask_img, original)
    assert panel.btn_redo.isEnabled()
    assert not window.state.is_dirty
    qtbot.keyClick(window.viewer, Qt.Key_Y, Qt.ControlModifier)
    assert np.array_equal(window.state.mask_img, completed)
    assert window.state.is_dirty
    assert not panel.btn_redo.isEnabled()
    panel.btn_undo.click()
    panel.btn_redo.click()
    assert np.array_equal(window.state.mask_img, completed)
    assert not window.polygon_editor.has_selection


@pytest.mark.parametrize("item", SHORTCUTS, ids=lambda item: item.name)
def test_every_shortcut_can_be_changed_and_individually_reset(qtbot, item):
    dialog = SettingsDialog()
    qtbot.addWidget(dialog)
    editor = dialog.shortcut_editors[item.name]
    editor.setKeySequence(QKeySequence("Ctrl+Shift+K"))
    assert dialog.validate_shortcuts()
    assert dialog.shortcut_values()[item.name] == "Ctrl+Shift+K"
    for name, value in dialog.shortcut_values().items():
        if name != item.name:
            assert value == normalize_shortcut(DEFAULT_SHORTCUTS[name])
    dialog.shortcut_reset_buttons[item.name].click()
    assert dialog.shortcut_values()[item.name] == normalize_shortcut(item.default)
    assert dialog.validate_shortcuts()


def test_default_tool_keys_select_tools_only_in_edit_mode(windows, qtbot):
    create, settings = windows
    settings.setValue("eraser_tool", DrawTool.RECT_ERASER)
    window = create()
    window.state.load_image_and_mask(np.zeros((32, 32, 3), np.uint8), None)
    qtbot.keyClick(window.viewer, Qt.Key_2)
    assert window.state.tool == DrawTool.LINE
    assert not window.btn_edit.isChecked()

    window.btn_edit.click()
    panel = window.edit_panel
    window.activateWindow()
    window.viewer.setFocus()
    QApplication.processEvents()
    for key, tool, button in (
        (Qt.Key_2, DrawTool.POLY, panel.btn_poly),
        (Qt.Key_E, DrawTool.RECT_ERASER, panel.btn_eraser),
        (Qt.Key_3, DrawTool.AUTO_FILL, panel.btn_auto_fill),
        (Qt.Key_4, DrawTool.SAMPLE_FILL, panel.btn_sample_fill),
    ):
        qtbot.keyClick(window.viewer, key)
        assert window.state.tool == tool
        assert button.isChecked()

    panel.activateWindow()
    panel.btn_sample_fill.setFocus()
    QApplication.processEvents()
    qtbot.keyClick(panel.btn_sample_fill, Qt.Key_1)
    assert window.state.tool == DrawTool.LINE
    assert panel.btn_line.isChecked()
    assert not window.state.mask_img.any()
    assert not window.state.can_undo()

    window.btn_edit.click()
    qtbot.keyClick(window.viewer, Qt.Key_4)
    assert window.state.tool == DrawTool.LINE


@pytest.mark.parametrize("item", [item for item in SHORTCUTS if item.name != "overlay"],
                         ids=lambda item: item.name)
def test_rebound_shortcuts_use_exact_modifiers_and_old_key_stops(windows, qtbot, monkeypatch, item):
    window = windows[0]()
    bindings = dict(window.shortcuts)
    bindings[item.name] = "Ctrl+Shift+K"
    assert window._apply_shortcut_settings(bindings)
    calls = []
    monkeypatch.setattr(window, "_trigger_shortcut", calls.append)
    qtbot.keyClick(window.viewer, Qt.Key_K, Qt.ControlModifier)
    assert not calls
    old = int(QKeySequence(item.default)[0])
    qtbot.keyClick(window.viewer, old & ~int(Qt.KeyboardModifierMask),
                   Qt.KeyboardModifiers(old & int(Qt.KeyboardModifierMask)))
    assert not calls
    qtbot.keyClick(window.viewer, Qt.Key_K, Qt.ControlModifier | Qt.ShiftModifier)
    assert calls == [item.action]


def test_conflicts_are_dynamic_and_can_be_resolved_by_swapping(qtbot):
    dialog = SettingsDialog()
    qtbot.addWidget(dialog)
    dialog.shortcut_editors["undo"].setKeySequence(QKeySequence("Ctrl+Y"))
    assert not dialog.btn_save.isEnabled()
    assert "重复" in dialog.lbl_shortcut_error.text()
    dialog.shortcut_editors["redo"].setKeySequence(QKeySequence("Ctrl+Z"))
    assert dialog.btn_save.isEnabled()



@pytest.mark.parametrize("action", ["save", "cancel", "close"])
def test_all_shortcuts_persist_together_only_on_settings_save(windows, qtbot, action):
    create, settings = windows
    window = create()
    bindings = {item.name: f"Ctrl+Alt+Shift+F{i + 1}" for i, item in enumerate(SHORTCUTS)}

    def interact():
        dialog = QApplication.activeModalWidget()
        for name, value in bindings.items():
            dialog.shortcut_editors[name].setKeySequence(QKeySequence(value))
        assert dialog.btn_save.isEnabled()
        if action == "save":
            dialog.btn_save.click()
        elif action == "cancel":
            dialog.btn_cancel.click()
        else:
            dialog.close()

    QTimer.singleShot(0, interact)
    window._open_settings()
    expected = bindings if action == "save" else DEFAULT_SHORTCUTS
    expected = {key: normalize_shortcut(value) for key, value in expected.items()}
    assert window.shortcuts == expected
    restored = create()
    assert restored.shortcuts == expected
    if action == "save":
        assert json.loads(settings.value("shortcuts")) == expected
        assert expected["previous"] in restored.btn_prev.toolTip()
        restored.btn_edit.click()
        assert expected["redo"] in restored.edit_panel.btn_redo.toolTip()
        assert expected[DrawTool.SAMPLE_FILL] in restored.edit_panel.btn_sample_fill.toolTip()


def test_shortcuts_work_from_panel_and_do_not_intercept_inputs_or_dialogs(windows, qtbot, monkeypatch):
    window = windows[0]()
    window.state.load_image_and_mask(np.zeros((32, 32, 3), np.uint8), None)
    window.btn_edit.click()
    panel = window.edit_panel
    panel.activateWindow()
    panel.btn_poly.setFocus()
    QApplication.processEvents()
    calls = []
    monkeypatch.setattr(window, "_undo", lambda: calls.append("undo"))
    qtbot.keyClick(panel.btn_poly, Qt.Key_Z, Qt.ControlModifier)
    assert calls == ["undo"]
    calls = []
    monkeypatch.setattr(window, "_trigger_shortcut", calls.append)
    text = QLineEdit(panel)
    text.show()
    text.setFocus()
    qtbot.keyClicks(text, "12345ade")
    qtbot.keyClick(text, Qt.Key_Y, Qt.ControlModifier)
    assert text.text() == "12345ade"
    assert not calls
    dialog = SettingsDialog(parent=window)
    qtbot.addWidget(dialog)
    dialog.show()
    dialog.shortcut_editors["redo"].setFocus()
    qtbot.keyClick(dialog.shortcut_editors["redo"], Qt.Key_Y, Qt.ControlModifier)
    assert not calls
    dialog.close()
    other = QDialog()
    qtbot.addWidget(other)
    other.show()
    qtbot.keyClick(other, Qt.Key_Delete)
    assert not calls


@pytest.mark.parametrize("saved", ["bad json", "[]", '{"redo": "Ctrl+Z"}', '{"undo": 12}'])
def test_invalid_saved_shortcuts_fall_back_safely(windows, saved):
    create, settings = windows
    settings.setValue("shortcuts", saved)
    assert create().shortcuts == DEFAULT_SHORTCUTS


def test_old_profiles_do_not_restore_removed_shortcuts(windows, qtbot, monkeypatch):
    create, settings = windows
    settings.setValue("shortcuts", json.dumps({
        "previous": "Left", "next": "Right", "save_next": "D", "overlay": "C",
        "undo": "Ctrl+Z", "redo": "Ctrl+Y", "save": "Ctrl+S",
    }))
    settings.setValue("mask_shortcut", "Ctrl+K")
    settings.setValue("mask_shortcut_mode", "hold")
    window = create()
    assert window.shortcuts == DEFAULT_SHORTCUTS
    dialog = SettingsDialog(shortcuts=window.shortcuts)
    qtbot.addWidget(dialog)
    assert set(dialog.shortcut_editors) == set(window.shortcuts)
    assert len(dialog.shortcut_editors) == 11
    window.btn_edit.click()
    window.activateWindow()
    window.viewer.setFocus()
    QApplication.processEvents()
    calls = []
    monkeypatch.setattr(window, "_trigger_shortcut", calls.append)
    removed = ("Left", "Right", "F", "0", "5",
               "[", "]", "Return", "Enter", "Esc", "Ctrl+D", "Del",
               *(f"Alt+{i}" for i in range(1, 10)))
    for text in removed:
        chord = int(QKeySequence(text)[0])
        qtbot.keyClick(window.viewer, chord & ~int(Qt.KeyboardModifierMask),
                       Qt.KeyboardModifiers(chord & int(Qt.KeyboardModifierMask)))
    assert not calls
    assert window.state.is_mask_visible
    assert window.state.tool == DrawTool.LINE
    assert window._apply_shortcut_settings(window.shortcuts)
    assert set(json.loads(settings.value("shortcuts"))) == set(DEFAULT_SHORTCUTS)
    assert settings.value("mask_shortcut") == "C"
    assert settings.value("mask_shortcut_mode") == "hold"


def test_default_five_keys_dispatch_to_the_requested_actions(windows, qtbot, monkeypatch):
    window = windows[0]()
    calls = []
    monkeypatch.setattr(window, "_prev_image", lambda: calls.append("previous"))
    monkeypatch.setattr(window, "_next_image", lambda: calls.append("next"))
    monkeypatch.setattr(window, "_undo", lambda: calls.append("undo"))
    monkeypatch.setattr(window, "_redo", lambda: calls.append("redo"))
    monkeypatch.setattr(window, "_save_mask", lambda: calls.append("save"))
    monkeypatch.setattr(window, "_save_and_next", lambda: pytest.fail("D 只应切换到下一张"))
    for key, modifiers in ((Qt.Key_A, Qt.NoModifier), (Qt.Key_D, Qt.NoModifier),
                           (Qt.Key_Z, Qt.ControlModifier), (Qt.Key_Y, Qt.ControlModifier),
                           (Qt.Key_S, Qt.ControlModifier)):
        qtbot.keyClick(window.viewer, key, modifiers)
    assert calls == ["previous", "next", "undo", "redo", "save"]


@pytest.mark.parametrize("binding", ["", "Ctrl+Y", "Ctrl+K, Ctrl+C"])
def test_invalid_binding_blocks_save_and_reset_recovers(qtbot, binding):
    dialog = SettingsDialog()
    qtbot.addWidget(dialog)
    dialog.shortcut_editors["undo"].setKeySequence(QKeySequence(binding))
    assert not dialog.btn_save.isEnabled()
    dialog.shortcut_reset_buttons["undo"].click()
    assert dialog.btn_save.isEnabled()


def test_restoring_overlay_keeps_saved_five_shortcuts(windows):
    create, settings = windows
    saved = {"previous": "Q", "next": "W", "undo": "Ctrl+U",
             "redo": "Ctrl+R", "save": "Ctrl+Shift+S"}
    settings.setValue("shortcuts", json.dumps(saved))
    window = create()
    assert window.shortcuts == {**DEFAULT_SHORTCUTS, **saved}
    assert window.mask_shortcut_mode == "hold"


def test_new_tool_defaults_do_not_replace_saved_shortcuts(windows):
    create, settings = windows
    saved = {"previous": "3", "next": "Ctrl+3", "overlay": "E", "undo": "Ctrl+U"}
    settings.setValue("shortcuts", json.dumps(saved))
    assert create().shortcuts == {
        **DEFAULT_SHORTCUTS, **saved, DrawTool.AUTO_FILL: "Alt+3", DrawTool.ERASER: "Ctrl+E",
    }
