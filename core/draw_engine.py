# core/draw_engine.py
import numpy as np
import cv2
from enum import Enum, auto
from core.config import DrawTool
from core.similarity_fill import (
    fill_enclosed_holes, largest_connected_region, matching_sample_pixels, sample_lab_centers,
)


class DrawPhase(Enum):
    IDLE = auto()  # 空闲
    DRAWING = auto()  # 正在自由手绘中


class DrawEngine:
    def __init__(self, state, *, similarity_image=None):
        self._state = state
        self._similarity_image = similarity_image or (lambda: state.orig_img)
        self._phase = DrawPhase.IDLE
        self._poly_points: list[tuple[int, int]] = []
        self._last_pos: tuple[int, int] | None = None
        self._pending_redo = []
        self._area_tool: str | None = None

    @property
    def phase(self) -> DrawPhase:
        return self._phase

    @property
    def is_active(self) -> bool:
        return self._phase != DrawPhase.IDLE

    @property
    def is_sampling(self) -> bool:
        return self._area_tool == DrawTool.SAMPLE_FILL and self._state.fill_sample is None

    @property
    def uses_freehand_area(self) -> bool:
        return self._area_tool == DrawTool.POLY_ERASER or (
            self._area_tool == DrawTool.SAMPLE_FILL
            and (self.is_sampling or self._state.fill_freehand)
        )

    # ──────────────────────────────────────────────────────────────────────────
    # 核心绘制逻辑：按下 -> 拖动 -> 松开
    # ──────────────────────────────────────────────────────────────────────────
    def on_press(self, x: int, y: int):
        tool = self._state.tool
        mask = self._state.mask_img
        if mask is None or tool in (DrawTool.EDIT_POLY, DrawTool.AUTO_FILL):
            return

        if self._phase != DrawPhase.IDLE:
            return
        self._phase = DrawPhase.DRAWING
        self._last_pos = (x, y)
        if tool in (*DrawTool.AREA_ERASERS, DrawTool.SAMPLE_FILL):
            self._area_tool = tool
            # 拖动区域工具只显示预览，松开且实际修改时才生成历史。
            self._poly_points = [(x, y)]
            return
        self._pending_redo = self._state.redo_stack.copy()
        self._state.push_undo()
        self._state.mark_modified()

        if tool == DrawTool.POLY:
            self._poly_points = [(x, y)]
        else:
            color = self._state.current_draw_value if tool == DrawTool.LINE else 0
            brush = self._state.brush_size
            cv2.circle(mask, (x, y), max(1, brush // 2), color, -1)

    def on_move(self, x: int, y: int):
        if self._phase != DrawPhase.DRAWING or self._last_pos is None:
            return

        tool = self._state.tool
        mask = self._state.mask_img
        if mask is None:
            return

        if self._area_tool:
            if self.uses_freehand_area and (x, y) != self._last_pos:
                self._poly_points.append((x, y))
            self._last_pos = (x, y)
            return

        brush = self._state.brush_size

        if tool == DrawTool.LINE:
            # 自由线画笔
            color = self._state.current_draw_value
            cv2.line(mask, self._last_pos, (x, y), color, max(1, brush), cv2.LINE_8)
            self._last_pos = (x, y)

        elif tool == DrawTool.ERASER:
            # 自由橡皮擦
            cv2.line(mask, self._last_pos, (x, y), 0, max(1, brush), cv2.LINE_8)
            self._last_pos = (x, y)

        elif tool == DrawTool.POLY:
            # 面状笔：一边移动一边画边界线（实时预览边界），收集点阵
            color = self._state.current_draw_value
            cv2.line(mask, self._last_pos, (x, y), color, max(1, brush), cv2.LINE_8)
            self._poly_points.append((x, y))
            self._last_pos = (x, y)

    def on_release(self, x: int, y: int) -> int | None:
        """结束拖动。取样填充返回本次新增的像素数。"""
        if self._phase != DrawPhase.DRAWING:
            return
        if self._area_tool:
            filled_count = self._apply_area(x, y)
            self._finish()
            return filled_count
        if self._state.tool == DrawTool.POLY:
            if len(self._poly_points) > 2:
                pts = np.array(self._poly_points, np.int32)
                cv2.fillPoly(
                    self._state.mask_img,
                    [pts],
                    self._state.current_draw_value,
                )
            else:
                # 轻点时仍留下一个可见的小标记。
                cv2.circle(
                    self._state.mask_img,
                    (x, y),
                    max(1, self._state.brush_size // 2),
                    self._state.current_draw_value,
                    -1,
                )
        self._finish()

    def _apply_area(self, x: int, y: int) -> int | None:
        """仅分配选区包围盒大小的临时数组，避免拖动时扫描大幅掩膜。"""
        mask = self._state.mask_img
        if mask is None:
            return
        tool = self._area_tool
        freehand = self.uses_freehand_area
        if not freehand:
            start_x, start_y = self._poly_points[0]
            if tool == DrawTool.RECT_ERASER and (start_x == x or start_y == y):
                return
            points = [(start_x, start_y), (x, y)]
        else:
            self.on_move(x, y)  # 松开位置也属于边界，不依赖最后一次 move 事件。
            points = self._poly_points
            distinct = list(dict.fromkeys(points))
            if len(distinct) < 3:
                return
            x0, y0 = distinct[0]
            dx, dy = distinct[1][0] - x0, distinct[1][1] - y0
            if all((px - x0) * dy == (py - y0) * dx for px, py in distinct[2:]):
                return

        height, width = mask.shape[:2]
        left = max(0, min(px for px, _ in points))
        top = max(0, min(py for _, py in points))
        right = min(width, max(px for px, _ in points) + 1)
        bottom = min(height, max(py for _, py in points) + 1)
        if left >= right or top >= bottom:
            return
        roi = mask[top:bottom, left:right]
        region = None
        if freehand:
            region = np.zeros(roi.shape, dtype=np.uint8)
            local_points = np.asarray(points, dtype=np.int32) - (left, top)
            cv2.fillPoly(region, [local_points.astype(np.int32)], 1)
            region = region.astype(bool)

        if tool == DrawTool.SAMPLE_FILL:
            image = self._similarity_image()
            if image is None:
                return
            image_roi = image[top:bottom, left:right]
            if self.is_sampling:
                if region is not None and region.any():
                    self._state.fill_sample = sample_lab_centers(image_roi[region])
                return
            if roi.size > 1:
                return self._fill_sampled_area(image_roi, roi, region)
            return

        changed = np.any(roi if region is None else roi[region])
        if not changed:
            return
        self._state.push_undo()
        if region is None:
            roi[:] = 0
        else:
            roi[region] = 0
        self._state.mark_modified()

    def _fill_sampled_area(
        self, image: np.ndarray, mask: np.ndarray, region: np.ndarray | None,
    ) -> int:
        state = self._state
        sample = state.fill_sample
        value = state.current_draw_value
        if sample is None or not 1 <= value <= 255:
            return 0
        writable = mask == 0
        if region is not None:
            writable &= region
        matches = matching_sample_pixels(image, sample, state.sample_fill_tolerance)
        matches &= writable
        largest = largest_connected_region(matches)
        if largest is None:
            return 0
        filled = fill_enclosed_holes(largest) & writable
        count = int(np.count_nonzero(filled))
        state.push_undo()
        mask[filled] = value
        state.mark_modified()
        return count

    def on_double_click(self, x: int, y: int):
        # 按下拖动已经是完整笔划，双击不再承担结束操作。
        pass

    def _finish(self):
        self._poly_points = []
        self._last_pos = None
        self._phase = DrawPhase.IDLE
        self._pending_redo = []
        self._area_tool = None

    def cancel(self):
        """取消当前笔划（Esc）"""
        if self._phase == DrawPhase.DRAWING and not self._area_tool:
            self._state.pop_undo(record_redo=False)
            self._state.redo_stack = self._pending_redo
        self._finish()

    def draw_line_preview(self, display_img: np.ndarray, cursor_pos: tuple[int, int] | None = None):
        # 由于我们改为直接实时在 mask 上画线了，不再需要收集节点画幽灵预览线
        pass
