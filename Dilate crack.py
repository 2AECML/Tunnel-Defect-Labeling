#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
dilate_crack.py
===============
把外部公开数据集的 1px 裂缝中心线膨胀到 ~3px，使整个裂缝类的标注宽度口径
与你自己标注的 3/5px 一致、并贴近真实裂缝宽度，从而让裂缝 IoU 与文献口径可比。

规则（严格，避免污染与灌水）：
  1. 只膨胀“非保护来源”的裂缝。你自己标的 tongji（3/5px，已是真实宽度）受保护、不动。
  2. 只对裂缝类别(值=2)膨胀，且只把膨胀新增的像素写到“原本是背景(0)”的位置——
     绝不覆盖渗水(1)/剥落(3)或你已有的裂缝标注。
  3. 默认 3×3 八连通膨胀 1 次：1px → 3px。DILATE_ITERS 可调。
  4. train/valid/test 三个 split 全部处理（评估端必须同口径）。

输出：在 OUT_ROOT 生成一份新数据集（images 原样拷贝，masks 为膨胀后版本），
      并在 OUT_ROOT/_preview 下生成若干“膨胀前/后”叠加预览供你肉眼核对宽度是否贴合真实裂缝。

依赖：numpy, Pillow
"""

import os
import shutil
from pathlib import Path
import numpy as np
from PIL import Image

# ============ 配置 ============
SRC_ROOT = Path(r"F:\YPing\LCS_Dataset_unified")          # 当前统一数据集
OUT_ROOT = Path(r"F:\YPing\LCS_Dataset_unified_dilated")  # 膨胀后输出（新目录，不覆盖原始）

PROTECTED_SOURCES = {"tongji", "spalling_src"}   # 受保护、不膨胀的来源（你自己标的/已有宽度的真实标注）
CRACK_ID   = 2
BG_ID      = 0
DILATE_ITERS = 1                 # 1 次 3×3 → 1px 变 3px；想更宽改 2
SPLITS = ["train", "valid", "test"]
N_PREVIEW = 10                   # 抽查预览数量
# ==============================


def source_of(stem: str) -> str:
    # organize 脚本命名为 {source}__{原stem}
    return stem.split("__", 1)[0]


def dilate3x3(binary: np.ndarray, iters: int) -> np.ndarray:
    """纯 numpy 的 8 连通 3×3 膨胀，避免 scipy 依赖。"""
    out = binary.copy()
    for _ in range(iters):
        acc = out.copy()
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                if dy == 0 and dx == 0:
                    continue
                shifted = np.zeros_like(out)
                ys = slice(max(0, dy), out.shape[0] + min(0, dy))
                xs = slice(max(0, dx), out.shape[1] + min(0, dx))
                ys2 = slice(max(0, -dy), out.shape[0] + min(0, -dy))
                xs2 = slice(max(0, -dx), out.shape[1] + min(0, -dx))
                shifted[ys, xs] = out[ys2, xs2]
                acc |= shifted
        out = acc
    return out


def process_mask(mask_path: Path, stem: str):
    """返回 (新mask数组, 是否被膨胀, 新增像素数)。"""
    arr = np.array(Image.open(mask_path).convert("L"))
    src = source_of(stem)
    if src in PROTECTED_SOURCES:
        return arr, False, 0

    crack = (arr == CRACK_ID)
    if not crack.any():
        return arr, False, 0

    dilated = dilate3x3(crack, DILATE_ITERS)
    # 只把“原本是背景”的新增位置变成裂缝，保护其它类别与已有标注
    add = dilated & (arr == BG_ID)
    n_add = int(add.sum())
    new_arr = arr.copy()
    new_arr[add] = CRACK_ID
    return new_arr, True, n_add


def make_preview(img_path: Path, old_arr, new_arr, out_path: Path):
    """灰度图上叠加：原裂缝=绿，膨胀新增=红，供核对宽度是否贴合真实裂缝。"""
    img = Image.open(img_path).convert("RGB")
    rgb = np.array(img).copy()
    if rgb.shape[:2] != old_arr.shape:
        img = img.resize((old_arr.shape[1], old_arr.shape[0]))
        rgb = np.array(img).copy()
    old_crack = (old_arr == CRACK_ID)
    added = (new_arr == CRACK_ID) & (~old_crack)
    rgb[old_crack] = [0, 255, 0]   # 原始中心线：绿
    rgb[added]     = [255, 0, 0]   # 膨胀新增：红
    Image.fromarray(rgb).save(out_path)


def main():
    (OUT_ROOT / "_preview").mkdir(parents=True, exist_ok=True)
    total, dilated_cnt, protected_cnt, add_px_total = 0, 0, 0, 0
    preview_done = 0

    for split in SPLITS:
        in_img = SRC_ROOT / split / "images"
        in_msk = SRC_ROOT / split / "masks"
        out_img = OUT_ROOT / split / "images"
        out_msk = OUT_ROOT / split / "masks"
        out_img.mkdir(parents=True, exist_ok=True)
        out_msk.mkdir(parents=True, exist_ok=True)
        if not in_msk.is_dir():
            print(f"[跳过] 不存在: {in_msk}")
            continue

        for msk_file in sorted(in_msk.iterdir()):
            if msk_file.suffix.lower() != ".png":
                continue
            stem = msk_file.stem
            total += 1

            # 找对应图像（拷贝原样）
            img_file = None
            for ext in (".jpg", ".jpeg", ".png", ".bmp"):
                cand = in_img / f"{stem}{ext}"
                if cand.exists():
                    img_file = cand
                    break
            if img_file is not None:
                shutil.copy2(img_file, out_img / img_file.name)

            old_arr = np.array(Image.open(msk_file).convert("L"))
            new_arr, was_dilated, n_add = process_mask(msk_file, stem)
            Image.fromarray(new_arr.astype(np.uint8), mode="L").save(out_msk / msk_file.name)

            if was_dilated and n_add > 0:
                dilated_cnt += 1
                add_px_total += n_add
                # 抽样预览（优先外部裂缝图）
                if preview_done < N_PREVIEW and img_file is not None and split == "train":
                    make_preview(img_file, old_arr, new_arr,
                                 OUT_ROOT / "_preview" / f"{stem}.png")
                    preview_done += 1
            elif source_of(stem) in PROTECTED_SOURCES and (old_arr == CRACK_ID).any():
                protected_cnt += 1

    print("=" * 60)
    print(f"总 mask: {total}")
    print(f"被膨胀的外部裂缝 mask: {dilated_cnt}（新增裂缝像素 {add_px_total:,}）")
    print(f"受保护未动的 tongji 裂缝 mask: {protected_cnt}")
    print(f"膨胀强度: 3×3 × {DILATE_ITERS} 次（约 1px→{1+2*DILATE_ITERS}px）")
    print(f"输出数据集: {OUT_ROOT}")
    print(f"预览图: {OUT_ROOT / '_preview'} （绿=原中心线，红=膨胀新增；")
    print(f"        核对红绿合起来是否刚好盖住图像里那条暗色裂缝、没有明显溢出）")
    print("=" * 60)


if __name__ == "__main__":
    main()