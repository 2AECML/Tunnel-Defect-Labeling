import cv2
import numpy as np


def analyze_mask_values(image_path):
    # 1. 以“不改变原图通道数”的方式读取图片
    # IMREAD_UNCHANGED 确保如果图片是单通道，就按单通道读取；如果有Alpha通道也会保留
    mask = cv2.imread(image_path, cv2.IMREAD_UNCHANGED)

    if mask is None:
        print(f"错误：无法读取图片，请检查路径是否正确：{image_path}")
        return

    # 2. 检查图片的维度
    if len(mask.shape) == 3:
        print(f"注意：这是一个 {mask.shape[2]} 通道的图片 (例如 RGB 或 RGBA)。")
        # 如果是RGB图，通常 mask 应该转为灰度图来统计单通道标签
        # mask = cv2.cvtColor(mask, cv2.COLOR_BGR2GRAY)
        # print("已将其转换为单通道灰度图进行统计。")
    else:
        print("这是一个单通道 (Grayscale) 图片。")

    # 3. 获取所有唯一的像素值，以及它们各自的数量
    unique_values, counts = np.unique(mask, return_counts=True)

    # 4. 打印结果
    print("-" * 30)
    print(f"统计结果：该 Mask 中共有 {len(unique_values)} 种像素值。")
    print("-" * 30)

    print("具体数值及对应的像素点数量：")
    for val, count in zip(unique_values, counts):
        print(f"像素值: {val:<5} | 数量: {count}")


# ========== 测试代码 ==========
if __name__ == "__main__":
    # 把这里的路径替换成你自己的 mask 图片路径
    mask_path = r"F:\YPing\LCS_Dataset\1_leakage\masks\H1_0_p0.png"
    analyze_mask_values(mask_path)