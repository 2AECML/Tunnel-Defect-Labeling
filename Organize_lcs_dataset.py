#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
organize_lcs_dataset.py
=======================
地铁隧道多病害分割数据集：审计 + 统一组织脚本

两步工作流（强烈建议先审计后落盘）：
  1) AUDIT_ONLY = True  -> 只扫描、统计、报告，不写任何文件。先核对真相。
  2) AUDIT_ONLY = False -> 重映射标签并写出统一数据集 + train/val/test 划分。

关键处理：
  - 标签重映射 {0:背景, 2:渗水, 3:裂缝, 4:剥落} -> {0:背景, 1:渗水, 2:裂缝, 3:剥落}
    （你磁盘上的掩码是 {0,2,3,4}，模型/损失需要的是连续的 {0,1,2,3}）
  - 任何不在 LABEL_REMAP 里的像素值都会被逐文件记录并告警（默认映射为背景，但你应人工核查）。
  - 来源感知 + 类别组合分层划分，保证多病害与真地铁样本在 train/val/test 都有代表。

依赖：numpy, Pillow      安装：pip install numpy pillow
"""

import os
import sys
import json
import random
import shutil
from pathlib import Path
from collections import defaultdict, Counter
from itertools import combinations

import numpy as np
from PIL import Image

# ============================================================================
# 配置区 —— 按你的实际情况改这里
# ============================================================================

# 数据集根目录（你截图里的 LCS_Dataset）
SRC_ROOT = Path(r"F:\YPing\LCS_Dataset")

# 输出目录（统一后的数据集会写到这里；不要和 SRC_ROOT 相同）
OUT_ROOT = Path(r"F:\YPing\LCS_Dataset_unified")

# True = 只审计不落盘；先用 True 跑一遍核对，再改成 False 正式生成
AUDIT_ONLY = True

# 每个来源文件夹的配置：
#   folder    : SRC_ROOT 下的子文件夹名
#   source    : 写进 metadata 的来源标签（论文里做分来源消融会用到）
#   domain    : "metro"=真地铁隧道 / "concrete"=相似混凝土环境（非地铁）/ "mixed"
#   注：domain 只是给你统计和划分参考，先按你的真实情况填，拿不准填 "mixed"
SOURCES = [
    {"folder": "1_leakage",      "source": "leakage_src",  "domain": "metro"},
    {"folder": "2_crack",        "source": "crack_src",    "domain": "metro"},
    {"folder": "3_spalling",     "source": "spalling_src", "domain": "concrete"},
    {"folder": "tongji_dataset", "source": "tongji",       "domain": "metro"},  # FY387两套数据合并+手工重标，真地铁，含真地铁剥落
    # 如果 FY387 是单独文件夹，在这里再加一行，例如：
    # {"folder": "FY387", "source": "fy387", "domain": "mixed"},
]

# 每个来源里图像/掩码子文件夹的候选名（脚本会自动探测命中的那个）
IMAGE_SUBDIR_CANDIDATES = ["images", "image", "imgs", "img", "JPEGImages"]
MASK_SUBDIR_CANDIDATES  = ["masks", "mask", "labels", "label", "annotations", "ann", "gt", "SegmentationClass"]

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff"}
MASK_EXTS  = {".png", ".bmp", ".tif", ".tiff"}  # 掩码不要用 jpg（有损会改变像素值）

# 标签重映射：磁盘值 -> 训练值
# 实际约定：0=背景, 1=渗水, 2=裂缝, 3=剥落（掩码本就在此空间，无需重映射，恒等即可）
LABEL_REMAP = {0: 0, 1: 1, 2: 2, 3: 3}
CLASS_NAMES = {0: "background", 1: "leakage", 2: "crack", 3: "spalling"}
DEFECT_IDS  = [1, 2, 3]  # 非背景类（重映射后的值）

# 划分比例与随机种子
SPLIT = {"train": 0.70, "val": 0.15, "test": 0.15}
SEED = 42

# ============================================================================
# 工具函数
# ============================================================================

def find_subdir(base: Path, candidates):
    for name in candidates:
        p = base / name
        if p.is_dir():
            return p
    # 兜底：base 下唯一的子目录
    subdirs = [d for d in base.iterdir() if d.is_dir()]
    return None


def pair_images_masks(src_cfg):
    """在一个来源文件夹里把 image 和 mask 按文件名主干配对。"""
    base = SRC_ROOT / src_cfg["folder"]
    if not base.is_dir():
        print(f"  [警告] 来源文件夹不存在，跳过: {base}")
        return []

    img_dir = find_subdir(base, IMAGE_SUBDIR_CANDIDATES)
    msk_dir = find_subdir(base, MASK_SUBDIR_CANDIDATES)
    if img_dir is None or msk_dir is None:
        print(f"  [警告] 在 {base} 下没找到 images/masks 子目录 "
              f"(images={img_dir}, masks={msk_dir})，跳过")
        return []

    imgs = {p.stem: p for p in img_dir.iterdir()
            if p.suffix.lower() in IMAGE_EXTS}
    msks = {p.stem: p for p in msk_dir.iterdir()
            if p.suffix.lower() in MASK_EXTS}

    common = sorted(set(imgs) & set(msks))
    only_img = sorted(set(imgs) - set(msks))
    only_msk = sorted(set(msks) - set(imgs))
    if only_img:
        print(f"  [提示] {src_cfg['folder']}: {len(only_img)} 张图无对应掩码（示例: {only_img[:3]}）")
    if only_msk:
        print(f"  [提示] {src_cfg['folder']}: {len(only_msk)} 个掩码无对应图（示例: {only_msk[:3]}）")

    return [(stem, imgs[stem], msks[stem]) for stem in common]


def analyze_mask(mask_path: Path):
    """返回 (unique_value_counts: Counter, present_defect_classes: set(remapped), unknown_values: set)"""
    arr = np.array(Image.open(mask_path))
    if arr.ndim == 3:
        # RGB/RGBA 掩码：若三通道相同则压成单通道，否则告警
        if arr.shape[2] >= 3 and np.all(arr[..., 0] == arr[..., 1]) and np.all(arr[..., 1] == arr[..., 2]):
            arr = arr[..., 0]
        else:
            return Counter({"__RGB_NONFLAT__": 1}), set(), {"__RGB__"}
    vals, cnts = np.unique(arr, return_counts=True)
    raw_counter = Counter({int(v): int(c) for v, c in zip(vals, cnts)})
    unknown = {int(v) for v in vals if int(v) not in LABEL_REMAP}
    present = {LABEL_REMAP[int(v)] for v in vals
               if int(v) in LABEL_REMAP and LABEL_REMAP[int(v)] in DEFECT_IDS}
    return raw_counter, present, unknown


def remap_mask(mask_path: Path) -> np.ndarray:
    arr = np.array(Image.open(mask_path))
    if arr.ndim == 3:
        arr = arr[..., 0]
    out = np.zeros_like(arr, dtype=np.uint8)
    for src_v, dst_v in LABEL_REMAP.items():
        out[arr == src_v] = dst_v
    # 未知值已在审计阶段告警，这里默认落背景(0)
    return out


def combo_key(present_defects: set):
    if not present_defects:
        return "background"
    return "+".join(CLASS_NAMES[c] for c in sorted(present_defects))


# ============================================================================
# 主流程
# ============================================================================

def main():
    random.seed(SEED)
    print("=" * 70)
    print(f"扫描根目录: {SRC_ROOT}")
    print(f"模式: {'仅审计（不写文件）' if AUDIT_ONLY else '审计 + 落盘生成统一数据集'}")
    print("=" * 70)

    records = []          # 每条: dict(stem, img, msk, source, domain, present, combo, unknown)
    global_raw = Counter()
    by_source_raw = defaultdict(Counter)              # source -> {value: px_count}
    by_source_imgval = defaultdict(lambda: Counter()) # source -> {value: 含该值的图片数}
    unknown_log = []      # (file, unknown_values)

    for cfg in SOURCES:
        pairs = pair_images_masks(cfg)
        print(f"\n来源 [{cfg['source']}] ({cfg['folder']}, domain={cfg['domain']}): "
              f"{len(pairs)} 对 image/mask")
        for stem, img_p, msk_p in pairs:
            raw, present, unknown = analyze_mask(msk_p)
            int_raw = {k: v for k, v in raw.items() if isinstance(k, int)}
            global_raw.update(int_raw)
            by_source_raw[cfg["source"]].update(int_raw)
            for v in int_raw:
                by_source_imgval[cfg["source"]][v] += 1
            if unknown:
                unknown_log.append((str(msk_p), sorted(unknown)))
            records.append({
                "stem": stem, "img": str(img_p), "msk": str(msk_p),
                "source": cfg["source"], "domain": cfg["domain"],
                "present": sorted(present), "combo": combo_key(present),
                "unknown": sorted(unknown),
            })

    if not records:
        print("\n[错误] 没有扫描到任何样本，请检查 SRC_ROOT 和 SOURCES 配置。")
        sys.exit(1)

    # ---------------- 审计报告 ----------------
    print("\n" + "=" * 70)
    print("审计报告")
    print("=" * 70)
    print(f"总样本: {len(records)}")

    print("\n[1] 掩码原始像素值分布（重映射前）:")
    for v in sorted(global_raw):
        tag = ""
        if v in LABEL_REMAP:
            tag = f"-> {LABEL_REMAP[v]} ({CLASS_NAMES.get(LABEL_REMAP[v],'?')})"
        else:
            tag = "  <<< 未知值！未在 LABEL_REMAP 中，将被当作背景，请核查"
        print(f"    值 {v:>3}: {global_raw[v]:>14,} px   {tag}")

    print("\n[1b] 分来源像素值分布（诊断每个文件夹到底用了哪些类）:")
    all_vals = sorted(global_raw)
    for src in by_source_raw:
        print(f"    [{src}]")
        for v in all_vals:
            px = by_source_raw[src].get(v, 0)
            imgs = by_source_imgval[src].get(v, 0)
            if px or imgs:
                cls = CLASS_NAMES.get(LABEL_REMAP.get(v), f"未知({v})")
                print(f"        值{v}({cls}): {px:>13,} px,  出现于 {imgs} 张图")

    print("\n[1c] 各类像素占比与失衡比（裂缝稀疏是关键诊断）:")
    defect_px = {cid: global_raw.get(cid, 0) for cid in DEFECT_IDS}  # 恒等映射下值==类id
    max_px = max(defect_px.values()) if any(defect_px.values()) else 1
    for cid in DEFECT_IDS:
        px = defect_px[cid]
        ratio = (max_px / px) if px else float("inf")
        print(f"    {CLASS_NAMES[cid]:<10}: {px:>13,} px   相对最大类失衡 ~{ratio:.0f}x")

    print("\n[2] 各来源 / domain 样本数:")
    by_src = Counter(r["source"] for r in records)
    by_dom = Counter(r["domain"] for r in records)
    for s, n in by_src.items():
        print(f"    {s:<14}: {n}")
    print("    --- domain ---")
    for d, n in by_dom.items():
        print(f"    {d:<14}: {n}")

    print("\n[3] 病害共现 / 背景统计:")
    combo_counter = Counter(r["combo"] for r in records)
    for c, n in sorted(combo_counter.items(), key=lambda x: -x[1]):
        print(f"    {c:<28}: {n}")
    multi = sum(1 for r in records if len(r["present"]) >= 2)
    bg = sum(1 for r in records if len(r["present"]) == 0)
    print(f"    >> 多病害(>=2类)样本: {multi}   纯背景样本: {bg}")

    print("\n[4] 各类出现的图片数（含共现重复计数）:")
    for cid in DEFECT_IDS:
        n = sum(1 for r in records if cid in r["present"])
        print(f"    {CLASS_NAMES[cid]:<12}: {n}")

    print("\n[5] 真地铁(metro domain)样本含各病害的数量（评估可信度关键）:")
    for cid in DEFECT_IDS:
        n = sum(1 for r in records if r["domain"] == "metro" and cid in r["present"])
        print(f"    metro & {CLASS_NAMES[cid]:<10}: {n}")

    if unknown_log:
        print(f"\n[!] 发现 {len(unknown_log)} 个掩码含未知像素值（前 10 个）:")
        for f, vs in unknown_log[:10]:
            print(f"    {vs}  {f}")
    else:
        print("\n[OK] 未发现未知像素值，标签已是 {0,1,2,3}，恒等映射可安全进行。")

    if AUDIT_ONLY:
        print("\n" + "=" * 70)
        print("仅审计模式结束。核对无误后，把 AUDIT_ONLY 改为 False 再跑一次即可落盘。")
        print("=" * 70)
        return

    # ---------------- 来源感知 + 类别组合分层划分 ----------------
    print("\n生成划分中（分层键 = source × combo）...")
    strata = defaultdict(list)
    for r in records:
        strata[(r["source"], r["combo"])].append(r)

    split_assign = {"train": [], "val": [], "test": []}
    for key, items in strata.items():
        items = items[:]
        random.shuffle(items)
        n = len(items)
        n_tr = int(round(n * SPLIT["train"]))
        n_va = int(round(n * SPLIT["val"]))
        # 小分层兜底：至少保证 train 拿到样本
        n_tr = min(n_tr, n)
        tr = items[:n_tr]
        va = items[n_tr:n_tr + n_va]
        te = items[n_tr + n_va:]
        split_assign["train"] += tr
        split_assign["val"]   += va
        split_assign["test"]  += te

    # ---------------- 落盘（嵌套结构，匹配 Tunnle2Dataset）----------------
    # split 内部名 -> dataloader 期望的文件夹名（build_tunnle2_loaders 用 'valid'）
    SPLIT_DIR = {"train": "train", "val": "valid", "test": "test"}
    for split_name, dir_name in SPLIT_DIR.items():
        (OUT_ROOT / dir_name / "images").mkdir(parents=True, exist_ok=True)
        (OUT_ROOT / dir_name / "masks").mkdir(parents=True, exist_ok=True)

    metadata = []
    split_lists = {"train": [], "val": [], "test": []}

    for split_name, items in split_assign.items():
        dir_name = SPLIT_DIR[split_name]
        for r in items:
            # 来源前缀防止跨来源重名冲突
            out_stem = f"{r['source']}__{r['stem']}"
            img_ext = Path(r["img"]).suffix.lower()
            out_img = OUT_ROOT / dir_name / "images" / f"{out_stem}{img_ext}"
            out_msk = OUT_ROOT / dir_name / "masks" / f"{out_stem}.png"

            shutil.copy2(r["img"], out_img)
            remapped = remap_mask(Path(r["msk"]))
            Image.fromarray(remapped, mode="L").save(out_msk)

            split_lists[split_name].append(out_stem)
            metadata.append({
                "stem": out_stem, "split": split_name,
                "source": r["source"], "domain": r["domain"],
                "classes_present": r["present"], "combo": r["combo"],
                "image": f"{dir_name}/images/{out_img.name}",
                "mask":  f"{dir_name}/masks/{out_msk.name}",
            })

    # split txt + metadata
    for split_name, stems in split_lists.items():
        (OUT_ROOT / f"{split_name}.txt").write_text(
            "\n".join(sorted(stems)), encoding="utf-8")

    import csv
    with open(OUT_ROOT / "metadata.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=[
            "stem", "split", "source", "domain", "combo",
            "classes_present", "image", "mask"])
        w.writeheader()
        for m in metadata:
            row = dict(m)
            row["classes_present"] = ";".join(map(str, m["classes_present"]))
            w.writerow(row)

    (OUT_ROOT / "dataset_info.json").write_text(json.dumps({
        "class_names": CLASS_NAMES, "label_remap": LABEL_REMAP,
        "split_counts": {k: len(v) for k, v in split_lists.items()},
        "seed": SEED, "split_ratio": SPLIT,
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n落盘完成：")
    for k, v in split_lists.items():
        print(f"    {SPLIT_DIR[k]}: {len(v)}")
    print(f"    输出目录: {OUT_ROOT}")
    print("    结构: train/{images,masks}  valid/{images,masks}  test/{images,masks}  metadata.csv  dataset_info.json")
    print(f"    -> 训练时把 build_tunnle2_loaders 的 tunnle2_root 指向: {OUT_ROOT}")
    print("    -> 并把 img_size 从 256 改为 640")


if __name__ == "__main__":
    main()