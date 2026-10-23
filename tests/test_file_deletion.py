import os
import subprocess
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
import pytest
from PyQt5.QtCore import QSettings, Qt, QTimer
from PyQt5.QtWidgets import QApplication, QMessageBox

from core.config import DEFAULT_CLASSES, DrawTool
from ui import delete_confirmation, main_window
from ui.class_manager_dialog import ClassManagerDialog
from utils.image_io import imwrite_unicode


OPERATIONS = ("mask_only", "image_and_mask")


@pytest.fixture(autouse=True)
def reset_confirmation_preferences(qapp):
    for operation in OPERATIONS:
        qapp.setProperty(delete_confirmation._SKIP_PROPERTY_PREFIX + operation, False)
    yield
    for operation in OPERATIONS:
        qapp.setProperty(delete_confirmation._SKIP_PROPERTY_PREFIX + operation, False)


@pytest.fixture
def window_factory(tmp_path, monkeypatch, qtbot):
    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.IniFormat)
    monkeypatch.setattr(main_window, "QSettings", lambda *args: settings)

    def create(names=("a", "b"), mask_names=("a",)):
        originals, masks = tmp_path / "原图", tmp_path / "掩膜"
        masks.mkdir(exist_ok=True)
        for name in names:
            assert imwrite_unicode(str(originals / f"{name}.jpg"),
                                   np.full((40, 60, 3), 100, np.uint8))
        for name in mask_names:
            mask = np.zeros((40, 60), np.uint8)
            mask[5:26, 5:36] = 3
            assert imwrite_unicode(str(masks / f"{name}.png"), mask)
        window = main_window.MainWindow()
        qtbot.addWidget(window, before_close_func=lambda widget: widget.state.mark_saved())
        window._set_folder("orig_folder", str(originals))
        window._set_folder("mask_folder", str(masks))
        window._scan_images()
        return window, originals, masks

    return create


@pytest.fixture
def allow_delete(monkeypatch):
    monkeypatch.setattr(main_window, "confirm_delete", lambda *args: True)


@pytest.fixture
def message_boxes(qapp):
    # Qt 5.15 的 Windows 无窗口插件显示标准 QMessageBox 时会崩溃。
    # 文件逻辑测试仍可无窗口运行；确认框交互在 windows 平台插件下验证。
    if sys.platform == "win32" and qapp.platformName() in ("offscreen", "minimal"):
        pytest.skip("确认框交互需要 QT_QPA_PLATFORM=windows（Windows 无窗口插件不支持消息框）")


def _answer_dialog(qtbot, decision="delete", skip=False):
    observed = {}

    def answer():
        box = QApplication.activeModalWidget()
        try:
            assert isinstance(box, QMessageBox)
            observed["title"] = box.windowTitle()
            observed["text"] = box.text()
            observed["checkbox"] = box.checkBox().text()
            observed["default_role"] = box.buttonRole(box.defaultButton())
            observed["escape_role"] = box.buttonRole(box.escapeButton())
            box.checkBox().setChecked(skip)
            if decision == "close":
                box.close()
            elif decision == "escape":
                qtbot.keyClick(box, Qt.Key_Escape)
            else:
                role = (QMessageBox.DestructiveRole if decision == "delete"
                        else QMessageBox.RejectRole)
                button = next(button for button in box.buttons()
                              if box.buttonRole(button) == role)
                qtbot.mouseClick(button, Qt.LeftButton)
        except BaseException:
            if box is not None:
                box.close()
            raise

    QTimer.singleShot(0, answer)
    return observed


@pytest.mark.parametrize("operation", OPERATIONS)
def test_confirmation_without_checkbox_prompts_each_time(qtbot, operation, qapp, message_boxes):
    for _ in range(2):
        observed = _answer_dialog(qtbot)
        assert delete_confirmation.confirm_delete(None, operation, "确认删除", "目标文件")
        assert observed["checkbox"] == "此次运行中不再提示"
        assert observed["default_role"] == QMessageBox.RejectRole
        assert observed["escape_role"] == QMessageBox.RejectRole
        assert not qapp.property(delete_confirmation._SKIP_PROPERTY_PREFIX + operation)


@pytest.mark.parametrize("operation", OPERATIONS)
@pytest.mark.parametrize("decision", ["cancel", "close", "escape"])
def test_cancel_with_checkbox_does_not_disable_confirmation(qtbot, qapp, operation, decision, message_boxes):
    _answer_dialog(qtbot, decision, skip=True)
    assert not delete_confirmation.confirm_delete(None, operation, "确认删除", "目标文件")
    assert not qapp.property(delete_confirmation._SKIP_PROPERTY_PREFIX + operation)


@pytest.mark.parametrize("first,second", [OPERATIONS, OPERATIONS[::-1]])
def test_suppression_is_independent_for_each_operation(qtbot, monkeypatch, first, second, message_boxes):
    _answer_dialog(qtbot, skip=True)
    assert delete_confirmation.confirm_delete(None, first, "第一类删除", "目标文件")
    observed = _answer_dialog(qtbot, "cancel")
    assert not delete_confirmation.confirm_delete(None, second, "第二类删除", "目标文件")
    assert observed["title"] == "第二类删除"
    monkeypatch.setattr(QMessageBox, "exec_", lambda self: pytest.fail("不应再次提示第一类删除"))
    assert delete_confirmation.confirm_delete(None, first, "第一类删除", "另一文件")


def test_suppression_resets_in_new_application_process(qtbot, message_boxes):
    for operation in OPERATIONS:
        _answer_dialog(qtbot, skip=True)
        assert delete_confirmation.confirm_delete(None, operation, "确认删除", "目标文件")
    script = """
from PyQt5.QtWidgets import QApplication
from ui.delete_confirmation import _SKIP_PROPERTY_PREFIX
app = QApplication([])
for operation in ('mask_only', 'image_and_mask'):
    assert not app.property(_SKIP_PROPERTY_PREFIX + operation)
"""
    result = subprocess.run([sys.executable, "-c", script], capture_output=True,
                            text=True, timeout=20)
    assert result.returncode == 0, result.stderr


def test_mask_only_deletion_keeps_original_and_clears_editing(window_factory, allow_delete):
    window, originals, masks = window_factory()
    source_bytes = (originals / "a.jpg").read_bytes()
    assert imwrite_unicode(str(masks / "a_mask.PNG"), window.state.mask_img)
    window._rebuild_mask_index()
    assert window.polygon_editor.select(window.state.mask_img, 10, 10)
    window.engine.on_press(1, 1)
    before_zoom = window.viewer.transform()
    window.btn_delete_mask.click()
    assert (originals / "a.jpg").read_bytes() == source_bytes
    assert not (masks / "a.png").exists()
    assert not (masks / "a_mask.PNG").exists()
    assert window.image_files == ["a.jpg", "b.jpg"]
    assert window.current_index == 0
    assert not np.any(window.state.mask_img)
    assert not window.state.is_dirty
    assert not window.state.can_undo()
    assert not window.engine.is_active
    assert not window.polygon_editor.has_selection
    assert not window.btn_delete_mask.isEnabled()
    assert window.btn_delete.isEnabled()
    assert window.viewer.transform() == before_zoom
    assert "没有掩膜" in window.lbl_status.text()
    assert window._find_mask_paths("a.jpg") == []


@pytest.mark.parametrize("method,operation", [
    ("_delete_current_mask", "mask_only"), ("_delete_current", "image_and_mask"),
])
def test_cancel_file_deletion_preserves_unsaved_work(window_factory, qtbot, method, operation, qapp, message_boxes):
    window, originals, masks = window_factory()
    window.state.push_undo()
    window.state.mask_img[0, 0] = 4
    window.state.mark_modified()
    before = window.state.mask_img.copy()
    observed = _answer_dialog(qtbot, "cancel", skip=True)
    getattr(window, method)()
    assert "未保存" in observed["text"]
    assert str(masks / "a.png") in observed["text"]
    assert (originals / "a.jpg").is_file()
    assert (masks / "a.png").is_file()
    assert np.array_equal(window.state.mask_img, before)
    assert window.state.is_dirty
    assert len(window.state.undo_stack) == 1
    assert not qapp.property(delete_confirmation._SKIP_PROPERTY_PREFIX + operation)


def test_both_file_actions_keep_independent_preferences(window_factory, qtbot, qapp, message_boxes):
    window, originals, masks = window_factory(mask_names=("a", "b"))
    _answer_dialog(qtbot, skip=True)
    window.btn_delete_mask.click()
    assert (originals / "a.jpg").exists()
    assert not (masks / "a.png").exists()
    observed = _answer_dialog(qtbot, "cancel")
    window.btn_delete.click()
    assert observed["title"] == "确认删除图像与掩膜"
    assert (originals / "a.jpg").exists()
    assert qapp.property(delete_confirmation._SKIP_PROPERTY_PREFIX + "mask_only")
    assert not qapp.property(delete_confirmation._SKIP_PROPERTY_PREFIX + "image_and_mask")
    window._next_image()
    window.btn_delete_mask.click()  # 同类删除免提示，无需安排确认框应答。
    assert not (masks / "b.png").exists()
    assert (originals / "b.jpg").exists()


def test_mask_deletion_updates_filtered_list_and_empty_state(window_factory, allow_delete):
    window, originals, masks = window_factory(names=("a", "b", "c"), mask_names=("a", "c"))
    window._apply_folder_settings(False, False, "with_mask")
    window._delete_current_mask()
    assert window.image_files == ["c.jpg"]
    assert window.spin_jump.maximum() == 1
    assert window.btn_delete_mask.isEnabled()
    window._delete_current_mask()
    assert window.image_files == []
    assert window.current_index == -1
    assert window.state.mask_img is None
    assert not window.btn_delete_mask.isEnabled()
    assert not window.btn_delete.isEnabled()
    window._apply_folder_settings(False, False, "without_mask")
    assert window.image_files == ["a.jpg", "b.jpg", "c.jpg"]
    assert all((originals / f"{name}.jpg").is_file() for name in ("a", "b", "c"))


def test_save_enables_mask_deletion_and_missing_file_is_harmless(window_factory, allow_delete, monkeypatch):
    window, _, masks = window_factory(mask_names=())
    assert not window.btn_delete_mask.isEnabled()
    window.state.mask_img[1, 1] = 3
    window.state.mark_modified()
    window._delete_current_mask()
    assert window.state.is_dirty  # 没有磁盘文件时不清除尚未保存的标注。
    assert window._save_mask()
    assert window.btn_delete_mask.isEnabled()
    (masks / "a.png").unlink()
    monkeypatch.setattr(main_window, "confirm_delete", lambda *args: pytest.fail("没有文件无需确认"))
    window._delete_current_mask()
    assert not window.btn_delete_mask.isEnabled()


def test_recursive_deletion_preserves_other_directory_masks(window_factory, allow_delete):
    window, originals, masks = window_factory(names=("隧道一/tile", "隧道二/tile"),
                                             mask_names=("隧道一/tile", "隧道二/tile"))
    window._apply_folder_settings(True, True)
    window._delete_current_mask()
    assert (originals / "隧道一" / "tile.jpg").is_file()
    assert not (masks / "隧道一" / "tile.png").exists()
    assert (masks / "隧道二" / "tile.png").is_file()


def test_partial_mask_deletion_failure_keeps_editing_and_reports_path(window_factory, allow_delete, monkeypatch):
    window, originals, masks = window_factory()
    blocked = masks / "a_mask.PNG"
    assert imwrite_unicode(str(blocked), window.state.mask_img)
    window._rebuild_mask_index()
    window.state.push_undo()
    window.state.mask_img[0, 0] = 4
    window.state.mark_modified()
    before = window.state.mask_img.copy()
    remove = os.remove
    errors = []

    def remove_with_failure(path):
        if os.path.normcase(str(path)) == os.path.normcase(str(blocked)):
            raise PermissionError("文件正在使用")
        remove(path)

    monkeypatch.setattr(main_window.os, "remove", remove_with_failure)
    monkeypatch.setattr(QMessageBox, "critical", lambda *args: errors.append(args[-1]))
    window._delete_current_mask()
    assert not (masks / "a.png").exists()
    assert blocked.exists()
    assert (originals / "a.jpg").exists()
    assert np.array_equal(window.state.mask_img, before)
    assert window.state.is_dirty and window.state.can_undo()
    assert window.btn_delete_mask.isEnabled()
    assert str(blocked) in errors[0]


def test_mask_only_deletion_rejects_original_as_mask(window_factory, monkeypatch):
    window, originals, _ = window_factory()
    window._set_folder("mask_folder", str(originals))
    window._scan_images()
    warnings = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *args: warnings.append(args[-1]))
    monkeypatch.setattr(main_window, "confirm_delete", lambda *args: pytest.fail("不应确认删除原图"))
    window._delete_current_mask()
    assert (originals / "a.jpg").is_file()
    assert "同一个文件" in warnings[0]


@pytest.mark.parametrize("failure_target", ["original", "mask"])
def test_combined_delete_reports_file_failures(window_factory, allow_delete, monkeypatch, failure_target):
    window, originals, masks = window_factory()
    blocked = originals / "a.jpg" if failure_target == "original" else masks / "a.png"
    remove = os.remove
    errors = []

    def remove_with_failure(path):
        if str(path) == str(blocked):
            raise PermissionError("文件正在使用")
        remove(path)

    monkeypatch.setattr(main_window.os, "remove", remove_with_failure)
    monkeypatch.setattr(QMessageBox, "critical", lambda *args: errors.append(args[-1]))
    window._delete_current()
    assert (masks / "a.png").exists()
    assert (originals / "a.jpg").exists() == (failure_target == "original")
    assert window.image_files == (["a.jpg", "b.jpg"] if failure_target == "original" else ["b.jpg"])
    assert errors


@pytest.mark.parametrize("selection", ["polygon", "vertex", "class"])
def test_other_deletions_do_not_prompt(window_factory, monkeypatch, qtbot, selection):
    window, _, _ = window_factory()
    monkeypatch.setattr(QMessageBox, "exec_", lambda self: pytest.fail("其他删除不应二次确认"))
    if selection == "class":
        dialog = ClassManagerDialog(DEFAULT_CLASSES)
        qtbot.addWidget(dialog)
        before = len(dialog.classes)
        dialog.table.setCurrentCell(0, 0)
        dialog._del_row()
        assert len(dialog.classes) == before - 1
    else:
        window.state.tool = DrawTool.EDIT_POLY
        assert window.polygon_editor.select(window.state.mask_img, 10, 10)
        if selection == "vertex":
            window.polygon_editor.selected_vertex_index = 0
            before = len(window.polygon_editor.vertices)
            window._delete_selection()
            assert len(window.polygon_editor.vertices) == before - 1
        else:
            window._delete_selection()
            assert not np.any(window.state.mask_img)
        assert window.state.is_dirty and window.state.can_undo()
