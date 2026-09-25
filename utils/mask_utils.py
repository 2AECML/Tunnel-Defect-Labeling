# utils/mask_utils.py
"""
掩膜合成显示工具
"""

import numpy as np
import cv2


def blend_mask_on_image(
    orig_img: np.ndarray,
    mask_img: np.ndarray,
    classes: list,
    alpha: float = 0.5,
    show_all: bool = True,
    current_class_idx: int = 0,
    show_contour: bool = True,
) -> np.ndarray:
    """
    将掩膜以半透明方式叠加到原图上，返回合成图（BGR）。

    Parameters
    ----------
    orig_img          : BGR 原图
    mask_img          : 单通道掩膜
    classes           : 类别列表 [{"value": int, "name": str, "color": (B,G,R)}, ...]
    alpha             : 掩膜不透明度 [0, 1]
    show_all          : True=显示所有类别，False=仅显示 current_class_idx 对应的类别
    current_class_idx : 当前类别下标（show_all=False 时生效）
    show_contour      : 是否绘制轮廓线

    Returns
    -------
    display_img : 合成后的 BGR 图（原图副本）
    """
    display_img = orig_img.copy()

    if mask_img is None or not np.any(mask_img):
        return display_img

    if show_all:
        classes_to_show = classes
    else:
        if 0 <= current_class_idx < len(classes):
            classes_to_show = [classes[current_class_idx]]
        else:
            classes_to_show = classes

    color_mask = np.zeros_like(display_img)
    any_mask = np.zeros(display_img.shape[:2], dtype=bool)

    for cls in classes_to_show:
        region = (mask_img == cls["value"])
        if np.any(region):
            b, g, r = cls["color"]
            color_mask[region] = [b, g, r]
            any_mask |= region

    if np.any(any_mask):
        blended = cv2.addWeighted(display_img, 1 - alpha, color_mask, alpha, 0)
        display_img[any_mask] = blended[any_mask]

    if show_contour:
        for cls in classes_to_show:
            region = (mask_img == cls["value"]).astype(np.uint8) * 255
            if np.any(region):
                cnts, _ = cv2.findContours(region, cv2.RETR_EXTERNAL,
                                           cv2.CHAIN_APPROX_SIMPLE)
                b, g, r = cls["color"]
                bright = (min(255, b + 80), min(255, g + 80), min(255, r + 80))
                cv2.drawContours(display_img, cnts, -1, bright, 1)

    return display_img


def adjust_brightness_contrast(
    img: np.ndarray, brightness: int = 0, contrast: float = 1.0
) -> np.ndarray:
    """
    调整图像亮度和对比度。
    brightness : 偏移量 (-100 ~ 100)
    contrast   : 对比度倍数 (0.1 ~ 3.0)
    """
    if brightness == 0 and contrast == 1.0:
        return img
    return cv2.convertScaleAbs(img, alpha=contrast, beta=brightness)


def class_pixel_stats_str(mask_img: np.ndarray, classes: list) -> str:
    """返回各类别像素统计的可读字符串，用于状态栏显示"""
    if mask_img is None:
        return ""
    parts = []
    for cls in classes:
        cnt = int(np.sum(mask_img == cls["value"]))
        if cnt > 0:
            parts.append(f"[{cls['value']}]{cls['name']}: {cnt}px")
    bg = int(np.sum(mask_img == 0))
    if parts:
        return "  |  ".join(parts) + f"  背景: {bg}px"
    return "全背景"
