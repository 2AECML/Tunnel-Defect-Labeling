"""基于原图颜色相似度的连通区域填充。"""

from __future__ import annotations

import cv2
import numpy as np


def _seed_component(binary: np.ndarray, x: int, y: int, connectivity: int) -> np.ndarray:
    """提取二值图中种子所在的前景连通区域。"""
    height, width = binary.shape
    if not binary[y, x]:
        return np.zeros_like(binary)
    flood_mask = np.zeros((height + 2, width + 2), dtype=np.uint8)
    flags = connectivity | cv2.FLOODFILL_MASK_ONLY | (255 << 8)
    cv2.floodFill(binary, flood_mask, (int(x), int(y)), 0, flags=flags)
    return flood_mask[1:-1, 1:-1].copy()


def _close_small_gaps(binary: np.ndarray) -> np.ndarray:
    """补齐细缝，图外补背景以保留贴着图像边缘的区域。"""
    padded = cv2.copyMakeBorder(binary, 2, 2, 2, 2, cv2.BORDER_CONSTANT, value=0)
    return cv2.morphologyEx(
        padded, cv2.MORPH_CLOSE, np.ones((3, 3), dtype=np.uint8),
        borderType=cv2.BORDER_CONSTANT, borderValue=0,
    )[2:-2, 2:-2].copy()


def similar_connected_region(
    image: np.ndarray,
    x: int,
    y: int,
    tolerance: int,
    *,
    connectivity: int = 4,
    annotation_mask: np.ndarray | None = None,
) -> np.ndarray:
    """返回颜色相近、尽量连通且内部无孔洞的实心区域。

    每个颜色通道始终与种子像素比较，避免沿渐变无限扩散。
    先对候选像素做 3×3 闭运算，连接 1–2 像素的细缝，再提取种子
    所在连通区域并填满外轮廓内部。较宽的外部凹口及远处区域保留。
    annotation_mask 中所有非零像素均为不可穿越、不可覆盖的边界，
    即使其类别与当前类别相同。默认四邻域避免从边界的对角缝隙穿过。
    """
    if image is None or image.ndim not in (2, 3):
        raise ValueError("image 必须是灰度或多通道图像")
    height, width = image.shape[:2]
    if not (0 <= x < width and 0 <= y < height):
        raise ValueError("种子坐标超出图像范围")
    if connectivity not in (4, 8):
        raise ValueError("connectivity 只能是 4 或 8")
    blocked = None
    if annotation_mask is not None:
        if annotation_mask.ndim != 2 or annotation_mask.shape != (height, width):
            raise ValueError("标注掩膜必须是与原图等尺寸的单通道图像")
        blocked = annotation_mask != 0
        if blocked[y, x]:
            return np.zeros((height, width), dtype=bool)

    tolerance = int(np.clip(tolerance, 0, 255))
    source = image
    if source.ndim == 3:
        if source.shape[2] < 3:
            source = source[:, :, 0]
        elif source.shape[2] > 3:
            source = source[:, :, :3]
    if source.dtype not in (np.uint8, np.float32):
        source = source.astype(np.float32)
    source = np.ascontiguousarray(source)

    seed = np.asarray(source[y, x], dtype=np.float64).reshape(-1)
    lower = tuple(float(value - tolerance) for value in seed)
    upper = tuple(float(value + tolerance) for value in seed)
    candidates = cv2.inRange(source, lower, upper)
    if blocked is not None:
        candidates[blocked] = 0

    closed = _close_small_gaps(candidates)
    # 闭运算不能把已有标注当成可补齐的细缝。
    if blocked is not None:
        closed[blocked] = 0

    region = _seed_component(closed, x, y, connectivity)
    contours, _ = cv2.findContours(region, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    cv2.drawContours(region, contours, -1, 255, cv2.FILLED)
    if blocked is not None:
        region[blocked] = 0
        # 填洞可能包含被已有多边形封闭的另一片背景；再次提取连通区域，
        # 防止绕过传播边界直接把这片背景填上。
        region = _seed_component(region, x, y, connectivity)
    return region.astype(bool)


def similarity_fill_target(
    image: np.ndarray,
    mask: np.ndarray,
    x: int,
    y: int,
    value: int,
    tolerance: int,
) -> tuple[np.ndarray, int]:
    """计算点击对应的填充区域及类别，不修改原图或掩膜。

    点击背景时执行受已有标注边界限制的相似像素填充；点击已有标注时，
    只补齐该同类别连通多边形的细缝及外轮廓内的空白，沿用其原类别。
    先选择连通区域再闭运算，避免把附近独立的同类别多边形一起补齐。
    """
    if mask.ndim != 2 or mask.shape != image.shape[:2]:
        raise ValueError("原图与单通道掩膜尺寸不一致")
    height, width = mask.shape
    if not (0 <= x < width and 0 <= y < height):
        raise ValueError("种子坐标超出图像范围")
    existing_value = int(mask[y, x])
    if existing_value:
        component = _seed_component((mask == existing_value).astype(np.uint8), x, y, 8)
        solid = _close_small_gaps(component)
        contours, _ = cv2.findContours(solid, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        cv2.drawContours(solid, contours, -1, 255, cv2.FILLED)
        return (solid != 0) & (mask == 0), existing_value
    region = similar_connected_region(image, x, y, tolerance, annotation_mask=mask)
    return region, value


def apply_similarity_fill(
    image: np.ndarray,
    mask: np.ndarray,
    x: int,
    y: int,
    value: int,
    tolerance: int,
) -> int:
    """填充背景或补齐被点击多边形的内部空白，返回变化像素数。"""
    region, value = similarity_fill_target(image, mask, x, y, value, tolerance)
    changed = region & (mask != value)
    changed_count = int(np.count_nonzero(changed))
    if changed_count:
        mask[region] = value
    return changed_count
