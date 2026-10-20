# utils/image_io.py
"""
图像读写工具（支持中文路径 & Unicode 路径）
统一封装 cv2.imdecode / imencode + np.fromfile / tofile
"""

import os
import numpy as np
import cv2


def imread_unicode(path: str, flags=cv2.IMREAD_COLOR) -> np.ndarray | None:
    """读取图像，支持 Unicode / 中文路径"""
    try:
        return cv2.imdecode(np.fromfile(path, dtype=np.uint8), flags)
    except Exception:
        return None


def imwrite_unicode(path: str, img: np.ndarray, ext: str = '.png') -> bool:
    """
    将图像写入文件，强制使用无损 PNG 编码。
    返回 True 表示成功。
    """
    try:
        # 确保目录存在
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        success, encoded = cv2.imencode(ext, img)
        if not success:
            return False
        encoded.tofile(path)
        return True
    except Exception:
        return False


def scan_images(folder: str, valid_exts: tuple, recursive: bool = False) -> list[str]:
    """
    扫描图像，返回排序后的相对路径；默认仅扫描当前目录。
    递归时保留相对目录，避免不同子目录中的同名文件混淆。
    """
    try:
        valid_exts = tuple(ext.lower() for ext in valid_exts)
        if recursive:
            files = [
                os.path.relpath(os.path.join(root, name), folder)
                for root, _, names in os.walk(folder)
                for name in names
                if name.lower().endswith(valid_exts)
                and os.path.isfile(os.path.join(root, name))
            ]
        else:
            files = [
                f for f in os.listdir(folder)
                if f.lower().endswith(valid_exts)
                and os.path.isfile(os.path.join(folder, f))
            ]
        return sorted(files)
    except Exception:
        return []


class MaskIndex:
    """一次扫描掩膜目录，供切图及状态刷新复用。"""

    def __init__(self, folder: str, valid_exts: tuple, recursive: bool = False):
        self.folder = folder
        self.paths = {}
        self.by_name = {}
        for relative_path in scan_images(folder, valid_exts, recursive):
            self.add(os.path.join(folder, relative_path))

    def add(self, path: str):
        relative_path = os.path.relpath(path, self.folder)
        key = relative_path.casefold()
        if key not in self.paths:
            self.paths[key] = relative_path
            self.by_name.setdefault(os.path.basename(key), []).append(relative_path)


def find_mask_paths(mask_folder: str, image_filename: str, valid_exts: tuple,
                    recursive: bool = False, preserve_structure: bool = False,
                    mask_index: MaskIndex | None = None) -> list[str]:
    """查找同一目录内的匹配掩膜变体；递归回退只接受唯一目录匹配。"""
    index = mask_index if mask_index is not None else MaskIndex(
        mask_folder, valid_exts, recursive)
    base = os.path.splitext(image_filename)[0]
    basename = os.path.basename(base)
    names = [f"{basename}{suffix}{ext}".casefold()
             for ext in valid_exts for suffix in ('', '_mask')]
    relative_dir = os.path.dirname(base) if recursive else ""
    directories = [relative_dir, ""] if preserve_structure else ["", relative_dir]
    for directory in dict.fromkeys(directories):
        matches = [index.paths[key] for name in names
                   if (key := os.path.join(directory, name).casefold()) in index.paths]
        if matches:
            return [os.path.join(mask_folder, path) for path in matches]

    if recursive:
        matches = [path for name in names for path in index.by_name.get(name, [])]
        # 同名掩膜分散在多个目录时不猜测，以免串用/误删其他图片的标注。
        if len({os.path.dirname(path).casefold() for path in matches}) == 1:
            return [os.path.join(mask_folder, path) for path in matches]
    return []


def find_mask_path(mask_folder: str, image_filename: str, valid_exts: tuple,
                   recursive: bool = False, preserve_structure: bool = False,
                   mask_index: MaskIndex | None = None) -> str | None:
    paths = find_mask_paths(mask_folder, image_filename, valid_exts,
                            recursive, preserve_structure, mask_index)
    return paths[0] if paths else None


def mask_save_path(mask_folder: str, image_filename: str,
                   preserve_structure: bool = False) -> str:
    """返回 PNG 保存路径；仅在用户开启选项后保留目录层级。"""
    if not preserve_structure:
        image_filename = os.path.basename(image_filename)
    base = os.path.splitext(image_filename)[0]
    return os.path.join(mask_folder, f"{base}.png")
