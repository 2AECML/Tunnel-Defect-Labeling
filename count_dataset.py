import os
import cv2
import numpy as np

# ================= 配置区域 =================
# 1. 替换为你的 Mask 掩膜文件夹路径
MASK_FOLDER = r"F:\YPing\LCS_Dataset\masks"

# 2. 定义你的类别字典 {像素值: "病害名称"}
# 请根据你 core/config.py 里的 DEFAULT_CLASSES 实际设定的 value 进行修改
CLASS_MAPPING = {
    1: "渗水",
    2: "裂缝",
    3: "剥落"
}


# ============================================

def imread_unicode(path):
    """支持中文路径的读取方法"""
    try:
        return cv2.imdecode(np.fromfile(path, dtype=np.uint8), cv2.IMREAD_GRAYSCALE)
    except Exception as e:
        print(f"读取图片失败: {path}\n错误: {e}")
        return None


def main():
    if not os.path.exists(MASK_FOLDER):
        print(f"错误: 文件夹不存在 -> {MASK_FOLDER}")
        return

    # 初始化统计字典
    # counts 用于记录包含某类病害的图片数量
    counts = {val: 0 for val in CLASS_MAPPING.keys()}

    # 额外统计项
    total_images = 0  # 总有效 Mask 数量
    empty_images = 0  # 全是背景（没有病害）的图片数量
    multi_defect_images = 0  # 同时包含多种病害的图片数量

    print(f"正在扫描文件夹: {MASK_FOLDER} ...\n")

    valid_exts = {'.png', '.jpg', '.jpeg', '.bmp', '.tif'}

    for filename in os.listdir(MASK_FOLDER):
        ext = os.path.splitext(filename)[1].lower()
        if ext not in valid_exts:
            continue

        filepath = os.path.join(MASK_FOLDER, filename)
        mask = imread_unicode(filepath)

        if mask is None:
            continue

        total_images += 1

        # 核心：获取这张 mask 里面所有的唯一像素值
        unique_vals = np.unique(mask)

        # 检查这张图包含了多少种我们关心的病害
        defects_in_this_image = 0

        for val in CLASS_MAPPING.keys():
            if val in unique_vals:
                counts[val] += 1
                defects_in_this_image += 1

        # 统计纯背景和混合病害图
        if defects_in_this_image == 0:
            empty_images += 1
        elif defects_in_this_image > 1:
            multi_defect_images += 1

    # ================= 打印统计结果 =================
    print("=" * 40)
    print(" 📊 数据集病害统计报告")
    print("=" * 40)
    print(f"总计扫描 Mask 图片 : {total_images} 张")
    print(f"无病害图片 (纯背景): {empty_images} 张")
    print(f"包含多种病害的图片 : {multi_defect_images} 张\n")

    print("--- 各类病害图片数量分布 ---")
    for val, name in CLASS_MAPPING.items():
        cnt = counts[val]
        # 计算比例
        ratio = (cnt / total_images * 100) if total_images > 0 else 0
        print(f"[{val}] {name:<6} : {cnt} 张  (占比 {ratio:.1f}%)")
    print("=" * 40)


if __name__ == "__main__":
    main()