# core/annotation_state.py
"""
标注状态机
集中管理当前图像、掩膜、撤销栈以及当前绘制状态。
UI 层只通过此对象读写数据，不直接操作 numpy 数组。
"""
import copy
import numpy as np
from core.config import DEFAULT_CLASSES, MAX_UNDO, DrawTool


class AnnotationState:
    """
    存储所有与标注相关的可变状态。

    属性
    ----
    orig_img        : np.ndarray | None   当前原图 (BGR)
    mask_img        : np.ndarray | None   当前掩膜 (单通道 uint8)
    classes         : list[dict]          当前类别列表
    current_class   : int                 当前选中类别的下标（0-based）
    tool            : str                 当前绘制工具 (DrawTool 常量)
    brush_size      : int                 当前笔刷宽度
    is_mask_visible : bool
    undo_stack      : list[np.ndarray]
    """

    def __init__(self):
        # 图像数据
        self.orig_img: np.ndarray | None = None
        self.mask_img: np.ndarray | None = None

        # 类别
        self.classes: list = copy.deepcopy(DEFAULT_CLASSES)
        self.current_class: int = 0

        # 工具状态
        self.tool: str = DrawTool.LINE
        self.brush_size: int = 3
        self.is_mask_visible: bool = True
        self.show_all_classes: bool = True
        self.show_contour: bool = True

        # 撤销
        self.undo_stack: list = []
        self.edit_revision: int = 0
        self.saved_revision: int = 0

    @property
    def is_dirty(self) -> bool:
        """当前掩膜是否有未保存修改。"""
        return self.edit_revision != self.saved_revision

    def mark_modified(self):
        self.edit_revision += 1

    def mark_saved(self):
        self.saved_revision = self.edit_revision

    # ──────────────────────────────────────────────────────────────────────────
    # 类别属性快捷访问
    # ──────────────────────────────────────────────────────────────────────────
    @property
    def current_class_info(self) -> dict | None:
        if 0 <= self.current_class < len(self.classes):
            return self.classes[self.current_class]
        return None

    @property
    def current_draw_value(self) -> int:
        """当前类别对应的像素值"""
        info = self.current_class_info
        return info["value"] if info else 1

    @property
    def current_draw_color_bgr(self) -> tuple:
        """当前类别的 BGR 颜色"""
        info = self.current_class_info
        return info["color"] if info else (255, 255, 255)

    # ──────────────────────────────────────────────────────────────────────────
    # 掩膜操作
    # ──────────────────────────────────────────────────────────────────────────
    def reset_mask(self):
        """清空掩膜（全背景）"""
        if self.orig_img is not None:
            h, w = self.orig_img.shape[:2]
            self.mask_img = np.zeros((h, w), dtype=np.uint8)
        self.undo_stack.clear()

    def push_undo(self):
        """将当前掩膜推入撤销栈"""
        if self.mask_img is None:
            return
        self.undo_stack.append((self.mask_img.copy(), self.edit_revision))
        if len(self.undo_stack) > MAX_UNDO:
            self.undo_stack.pop(0)

    def pop_undo(self) -> bool:
        """弹出撤销栈，返回是否成功"""
        if not self.undo_stack:
            return False
        item = self.undo_stack.pop()
        if isinstance(item, tuple):
            self.mask_img, self.edit_revision = item
        else:  # 兼容旧的撤销栈内容
            self.mask_img = item
            self.edit_revision = max(0, self.edit_revision - 1)
        return True

    def can_undo(self) -> bool:
        return len(self.undo_stack) > 0

    # ──────────────────────────────────────────────────────────────────────────
    # 统计
    # ──────────────────────────────────────────────────────────────────────────
    def class_pixel_stats(self) -> list[tuple[str, int]]:
        """返回 [(类别名, 像素数), ...] 列表（只含非零像素）"""
        if self.mask_img is None:
            return []
        counts = np.bincount(self.mask_img.reshape(-1), minlength=256)
        result = []
        for cls in self.classes:
            value = int(cls["value"])
            cnt = int(counts[value]) if 0 <= value < len(counts) else 0
            if cnt > 0:
                result.append((cls["name"], cnt))
        return result

    def load_image_and_mask(self, orig_img: np.ndarray,
                            mask_img: np.ndarray | None):
        """加载新图像，重置绘制状态"""
        self.orig_img = orig_img
        self.mask_img = mask_img if mask_img is not None else np.zeros(
            orig_img.shape[:2], dtype=np.uint8)
        self.undo_stack.clear()
        self.edit_revision = 0
        self.saved_revision = 0
