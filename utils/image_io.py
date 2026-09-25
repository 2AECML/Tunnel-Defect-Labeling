# utils/image_io.py
"""
图像读写工具（支持中文路径 & Unicode 路径）
统一封装 cv2.imdecode / imencode + np.fromfile / tofile
"""

import os
import numpy as np
import cv2
from pathlib import Path


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


def scan_images(folder: str, valid_exts: tuple) -> list[str]:
    """
    扫描文件夹内所有符合后缀的图像文件名（仅文件名，不含路径）。
    返回排序后的列表。
    """
    try:
        files = [
            f for f in os.listdir(folder)
            if f.lower().endswith(valid_exts)
        ]
        return sorted(files)
    except Exception:
        return []


def find_mask_path(mask_folder: str, image_filename: str,
                   valid_exts: tuple) -> str | None:
    """
    在 mask_folder 中查找与 image_filename 匹配的掩膜文件。
    搜索顺序：
      1. {base}{ext}          e.g. image_001.png
      2. {base}_mask{ext}     e.g. image_001_mask.png
    """
    base = os.path.splitext(image_filename)[0]
    for ext in valid_exts:
        for suffix in ('', '_mask'):
            candidate = os.path.join(mask_folder, f"{base}{suffix}{ext}")
            if os.path.exists(candidate):
                return candidate
    return None


def mask_save_path(mask_folder: str, image_filename: str) -> str:
    """返回掩膜的标准保存路径（始终使用 .png）"""
    base = os.path.splitext(image_filename)[0]
    return os.path.join(mask_folder, f"{base}.png")
