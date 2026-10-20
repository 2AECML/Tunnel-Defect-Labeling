import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
import pytest
from PyQt5.QtCore import QSettings, Qt, QTimer
from PyQt5.QtWidgets import QApplication

from core.config import VALID_IMAGE_EXTS
from ui import main_window
from ui.settings_dialog import SettingsDialog
from utils.image_io import (
    MaskIndex, find_mask_path, find_mask_paths, imread_unicode,
    imwrite_unicode, mask_save_path, scan_images,
)


def _write(path, value=0, color=False):
    shape = (8, 8, 3) if color else (8, 8)
    assert imwrite_unicode(str(path), np.full(shape, value, dtype=np.uint8),
                           path.suffix.lower())
    return str(path)


def test_recursive_scan_keeps_relative_paths_and_accepts_uppercase_jpg(tmp_path):
    _write(tmp_path / "root.jpg", color=True)
    _write(tmp_path / "隧道一" / "深层" / "tile.JPG", color=True)
    _write(tmp_path / "隧道二" / "tile.jpg", color=True)
    (tmp_path / "fake.jpg").mkdir()
    (tmp_path / "notes.txt").write_text("ignore")
    assert scan_images(str(tmp_path), VALID_IMAGE_EXTS) == ["root.jpg"]
    assert scan_images(str(tmp_path), VALID_IMAGE_EXTS, True) == sorted([
        "root.jpg", os.path.join("隧道一", "深层", "tile.JPG"),
        os.path.join("隧道二", "tile.jpg"),
    ])


def test_recursive_mask_lookup_handles_layouts_and_ambiguous_names(tmp_path):
    flat = _write(tmp_path / "tile.png", 1)
    nested = _write(tmp_path / "a" / "tile_mask.JPG", 2)
    filename = os.path.join("a", "tile.jpg")
    assert find_mask_path(str(tmp_path), filename, VALID_IMAGE_EXTS, True) == flat
    assert find_mask_path(str(tmp_path), filename, VALID_IMAGE_EXTS, True, True) == nested
    unique = _write(tmp_path / "different" / "unique_mask.JPG", 3)
    assert find_mask_path(str(tmp_path), "unique.jpg", VALID_IMAGE_EXTS) is None
    assert find_mask_path(str(tmp_path), "unique.jpg", VALID_IMAGE_EXTS, True) == unique
    _write(tmp_path / "another" / "unique.png", 4)
    assert find_mask_path(str(tmp_path), "unique.jpg", VALID_IMAGE_EXTS, True) is None
    # 删除只选择匹配目录内的掩膜，不涉及其他目录的同名文件。
    assert find_mask_paths(str(tmp_path), filename, VALID_IMAGE_EXTS, True, True) == [nested]


def test_mask_index_does_not_rescan_during_lookup(tmp_path, monkeypatch):
    path = _write(tmp_path / "a" / "image.PNG", 2)
    index = MaskIndex(str(tmp_path), VALID_IMAGE_EXTS, True)
    monkeypatch.setattr("utils.image_io.scan_images", lambda *a, **k: pytest.fail("rescanned"))
    assert find_mask_path(str(tmp_path), os.path.join("a", "image.jpg"),
                          VALID_IMAGE_EXTS, True, True, index) == path


def test_mask_save_structure_requires_explicit_option(tmp_path):
    filename = os.path.join("a", "b", "image.jpg")
    assert mask_save_path(str(tmp_path), filename) == str(tmp_path / "image.png")
    assert mask_save_path(str(tmp_path), filename, True) == str(tmp_path / "a" / "b" / "image.png")


@pytest.fixture
def windows(tmp_path, monkeypatch, qtbot):
    # 每个测试使用独立设置文件，不读写用户实际的目录记忆。
    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.IniFormat)
    monkeypatch.setattr(main_window, "QSettings", lambda *args: settings)
    created = []

    def create():
        window = main_window.MainWindow()
        qtbot.addWidget(window, before_close_func=lambda widget: widget.state.mark_saved())
        created.append(window)
        return window

    yield create, settings
    for window in created:
        window.state.mark_saved()


def test_options_default_off_and_persist_independently(windows):
    create, settings = windows
    first = create()
    assert not first.recursive_search
    assert not first.preserve_mask_structure
    first._apply_folder_settings(True, False)
    second = create()
    assert second.recursive_search
    assert not second.preserve_mask_structure
    second._apply_folder_settings(True, True)
    third = create()
    assert third.recursive_search
    assert third.preserve_mask_structure
    third._apply_folder_settings(False, True)
    fourth = create()
    assert not fourth.recursive_search
    assert fourth.preserve_mask_structure


def test_recursive_load_save_and_restore_last_nested_image(windows, tmp_path):
    create, settings = windows
    orig, masks = tmp_path / "originals", tmp_path / "masks"
    _write(orig / "root.jpg", color=True)
    _write(orig / "a" / "tile.JPG", color=True)
    _write(orig / "b" / "tile.JPG", color=True)
    _write(masks / "a" / "tile.PNG", 2)
    _write(masks / "b" / "tile_mask.PNG", 3)
    window = create()
    window._set_folder("orig_folder", str(orig))
    window._set_folder("mask_folder", str(masks))
    window._scan_images()
    assert window.image_files == ["root.jpg"]
    window._apply_folder_settings(True, False)
    assert len(window.image_files) == 3
    assert not window.preserve_mask_structure
    filename = os.path.join("a", "tile.JPG")
    window.current_index = window.image_files.index(filename)
    window._load_current_image()
    assert np.all(window.state.mask_img == 2)
    window.state.mask_img[:] = 4
    window.state.mark_modified()
    assert window._save_mask()
    assert np.all(imread_unicode(str(masks / "tile.png"), 0) == 4)
    assert np.all(imread_unicode(str(masks / "a" / "tile.PNG"), 0) == 2)
    window._load_current_image()
    assert np.all(window.state.mask_img == 4)
    window._apply_folder_settings(True, True)
    assert np.all(window.state.mask_img == 2)
    window.state.mask_img[:] = 5
    window.state.mark_modified()
    assert window._save_mask()
    assert np.all(imread_unicode(str(masks / "a" / "tile.png"), 0) == 5)
    restored = create()
    assert restored.image_files[restored.current_index] == filename
    assert np.all(restored.state.mask_img == 5)
    assert np.all(imread_unicode(str(masks / "b" / "tile_mask.PNG"), 0) == 3)


@pytest.mark.parametrize("options", [(True, False), (False, True)])
def test_cancel_option_change_preserves_unsaved_annotation(windows, monkeypatch, options):
    create, settings = windows
    window = create()
    window.state.load_image_and_mask(np.zeros((8, 8, 3), np.uint8), None)
    window.state.mask_img[0, 0] = 3
    window.state.mark_modified()
    monkeypatch.setattr(window, "_confirm_save_if_dirty", lambda: False)
    assert not window._apply_folder_settings(*options)
    assert not window.recursive_search
    assert not window.preserve_mask_structure
    assert window.state.is_dirty
    assert window.state.mask_img[0, 0] == 3


@pytest.mark.parametrize("action", ["save", "cancel", "close"])
def test_settings_entry_applies_only_on_save(windows, qtbot, monkeypatch, action):
    create, settings = windows
    window = create()
    scans = []
    monkeypatch.setattr(window, "_scan_images", lambda: scans.append(True))

    def interact():
        dialog = QApplication.activeModalWidget()
        assert isinstance(dialog, SettingsDialog)
        assert dialog.values() == (False, False, "all")
        qtbot.mouseClick(dialog.chk_recursive, Qt.LeftButton)
        qtbot.mouseClick(dialog.chk_preserve_structure, Qt.LeftButton)
        qtbot.mouseClick(dialog.filter_buttons["with_mask"], Qt.LeftButton)
        assert "区段 A" in dialog.lbl_save_preview.text()
        assert not window.recursive_search
        if action == "save":
            qtbot.mouseClick(dialog.btn_save, Qt.LeftButton)
        elif action == "cancel":
            qtbot.mouseClick(dialog.btn_cancel, Qt.LeftButton)
        else:
            dialog.close()

    QTimer.singleShot(0, interact)
    window.btn_settings.click()
    expected = action == "save"
    assert window.recursive_search == expected
    assert window.preserve_mask_structure == expected
    assert settings.value("recursive_search", False, type=bool) == expected
    assert window.image_filter == ("with_mask" if expected else "all")
    assert len(scans) == int(expected)


def test_settings_remain_open_when_unsaved_prompt_is_cancelled(windows, monkeypatch):
    create, settings = windows
    window = create()
    monkeypatch.setattr(window, "_confirm_save_if_dirty", lambda: False)

    def interact():
        dialog = QApplication.activeModalWidget()
        dialog.chk_recursive.setChecked(True)
        dialog.btn_save.click()
        assert dialog.isVisible()
        assert not window.recursive_search
        dialog.reject()

    QTimer.singleShot(0, interact)
    window._open_settings()


def test_opening_and_saving_unchanged_settings_does_not_reload(windows, monkeypatch):
    create, settings = windows
    window = create()
    monkeypatch.setattr(window, "_scan_images", lambda: pytest.fail("unexpected reload"))
    monkeypatch.setattr(window, "_confirm_save_if_dirty", lambda: pytest.fail("unexpected prompt"))
    QTimer.singleShot(0, lambda: QApplication.activeModalWidget().btn_save.click())
    window._open_settings()
    monkeypatch.undo()


def test_previous_image_on_other_drive_does_not_break_restore(windows, tmp_path):
    create, settings = windows
    _write(tmp_path / "current" / "root.jpg", color=True)
    settings.setValue("orig_folder", str(tmp_path / "current"))
    settings.setValue("last_image_path", "Z:\\previous\\image.jpg")
    real_isfile = os.path.isfile
    from unittest.mock import patch
    with patch("ui.main_window.os.path.isfile", side_effect=lambda path: (
            True if path == "Z:\\previous\\image.jpg" else real_isfile(path))):
        window = create()
    assert window.image_files[window.current_index] == "root.jpg"


def _filter_window(windows, tmp_path, names=("a", "b", "c"), mask_names=()):
    create, _ = windows
    originals, masks = tmp_path / "originals", tmp_path / "masks"
    masks.mkdir(exist_ok=True)
    for name in names:
        _write(originals / f"{name}.jpg", color=True)
    for name in mask_names:
        _write(masks / f"{name}.png")
    window = create()
    window._set_folder("orig_folder", str(originals))
    window._set_folder("mask_folder", str(masks))
    window._scan_images()
    return window, masks


def test_filter_uses_file_existence_and_remembers_selection(windows, tmp_path):
    window, _ = _filter_window(windows, tmp_path, mask_names=("a", "c"))
    assert window.image_filter == "all"
    window._apply_folder_settings(False, False, "with_mask")
    assert window.image_files == ["a.jpg", "c.jpg"]
    assert window.spin_jump.maximum() == 2
    assert not np.any(window.state.mask_img)  # 全背景掩膜仍算存在。
    window._next_image()
    assert window.image_files[window.current_index] == "c.jpg"
    restored = windows[0]()
    assert restored.image_filter == "with_mask"
    assert restored.image_files[restored.current_index] == "c.jpg"
    window._apply_folder_settings(False, False, "without_mask")
    assert window.image_files == ["b.jpg"]
    window._apply_folder_settings(False, False, "all")
    assert window.image_files == ["a.jpg", "b.jpg", "c.jpg"]


def test_recursive_filter_follows_mask_matching_rules(windows, tmp_path):
    names = ("a/tile", "b/tile", "c/unique", "d/missing", "e/ambiguous")
    window, masks = _filter_window(windows, tmp_path, names=names)
    _write(masks / "a" / "tile_mask.JPG")
    _write(masks / "different" / "unique.PNG")
    _write(masks / "x" / "ambiguous.png")
    _write(masks / "y" / "ambiguous.png")
    window._apply_folder_settings(True, True, "with_mask")
    assert window.image_files == [os.path.join(folder, name + ".jpg")
                                 for folder, name in (("a", "tile"), ("b", "tile"),
                                                      ("c", "unique"))]
    window._apply_folder_settings(True, True, "without_mask")
    assert window.image_files == [os.path.join("d", "missing.jpg"),
                                  os.path.join("e", "ambiguous.jpg")]


@pytest.mark.parametrize("mode, count", [("with_mask", 0), ("without_mask", 3)])
def test_filter_without_mask_folder(windows, tmp_path, mode, count):
    window, _ = _filter_window(windows, tmp_path)
    window.mask_folder = ""
    window._apply_folder_settings(False, False, mode)
    assert len(window.image_files) == count
    if not count:
        assert "请选择掩膜文件夹" in window.lbl_status.text()
        assert window.current_index == -1
        assert window.state.orig_img is None
        assert not window.btn_save_next.isEnabled()


def test_save_and_next_removes_completed_image_without_skipping(windows, tmp_path):
    window, masks = _filter_window(windows, tmp_path, names=("a", "b", "c", "d"),
                                   mask_names=("b",))
    window._apply_folder_settings(False, False, "without_mask")
    assert window.image_files == ["a.jpg", "c.jpg", "d.jpg"]
    window._save_and_next()
    assert (masks / "a.png").is_file()
    assert window.image_files == ["c.jpg", "d.jpg"]
    assert window.image_files[window.current_index] == "c.jpg"
    window._save_and_next()
    assert window.image_files == ["d.jpg"]
    window._save_and_next()
    assert window.image_files == []
    assert window.current_index == -1
    assert window.state.mask_img is None
    assert not window.state.is_dirty
    assert not window.state.can_undo()
    assert not window.btn_next.isEnabled()
    assert not window.btn_delete.isEnabled()
    assert "没有符合" in window.lbl_status.text()
    window._apply_folder_settings(False, False, "with_mask")
    assert window.image_files == ["a.jpg", "b.jpg", "c.jpg", "d.jpg"]


@pytest.mark.parametrize("navigation", ["next", "prev", "jump"])
def test_navigation_after_saving_dirty_filtered_image(windows, tmp_path, monkeypatch, navigation):
    window, masks = _filter_window(windows, tmp_path, names=("a", "b", "c", "d"))
    window._apply_folder_settings(False, False, "without_mask")
    window.current_index = 1
    window._load_current_image()
    window.state.mark_modified()
    monkeypatch.setattr(window, "_confirm_save_if_dirty", window._save_mask)
    if navigation == "next":
        window._next_image()
        expected = "c.jpg"
    elif navigation == "prev":
        window._prev_image()
        expected = "a.jpg"
    else:
        window.spin_jump.setValue(4)
        window._jump_to()
        expected = "d.jpg"
    assert (masks / "b.png").is_file()
    assert window.image_files[window.current_index] == expected
    # 关闭测试窗口时不再次触发保存。
    monkeypatch.setattr(window, "_confirm_save_if_dirty", lambda: True)


def test_failed_save_keeps_filtered_image(windows, tmp_path, monkeypatch):
    window, _ = _filter_window(windows, tmp_path)
    window._apply_folder_settings(False, False, "without_mask")
    window.state.mark_modified()
    monkeypatch.setattr(main_window, "imwrite_unicode", lambda *args: False)
    monkeypatch.setattr(main_window.QMessageBox, "critical", lambda *args: None)
    assert not window._save_mask()
    assert window.image_files == ["a.jpg", "b.jpg", "c.jpg"]
    assert window.current_index == 0
    assert window.state.is_dirty


def test_filter_change_cancel_keeps_images_and_preference(windows, tmp_path, monkeypatch):
    window, _ = _filter_window(windows, tmp_path)
    window.state.mark_modified()
    monkeypatch.setattr(window, "_confirm_save_if_dirty", lambda: False)
    assert not window._apply_folder_settings(False, False, "with_mask")
    assert window.image_filter == "all"
    assert window.image_files == ["a.jpg", "b.jpg", "c.jpg"]


def test_delete_updates_filtered_count_and_preserves_hidden_images(windows, tmp_path, monkeypatch):
    window, masks = _filter_window(windows, tmp_path, mask_names=("a", "c"))
    window._apply_folder_settings(False, False, "with_mask")
    monkeypatch.setattr(main_window.QMessageBox, "question",
                        lambda *args: main_window.QMessageBox.Yes)
    window._delete_current()
    assert window.image_files == ["c.jpg"]
    assert window.spin_jump.maximum() == 1
    assert not (masks / "a.png").exists()
    assert os.path.isfile(os.path.join(window.orig_folder, "b.jpg"))
    window._apply_folder_settings(False, False, "all")
    assert window.image_files == ["b.jpg", "c.jpg"]


def test_invalid_remembered_filter_falls_back_to_all(windows):
    create, settings = windows
    settings.setValue("image_filter", "unknown")
    assert create().image_filter == "all"
