# core/draw_engine.py
import numpy as np
import cv2
from enum import Enum, auto
from core.config import DrawTool


class DrawPhase(Enum):
    IDLE = auto()  # 空闲
    DRAWING = auto()  # 正在自由手绘中


class DrawEngine:
    def __init__(self, state):
        self._state = state
        self._phase = DrawPhase.IDLE
        self._poly_points: list[tuple[int, int]] = []
        self._last_pos: tuple[int, int] | None = None

    @property
    def phase(self) -> DrawPhase:
        return self._phase

    @property
    def is_active(self) -> bool:
        return self._phase != DrawPhase.IDLE

    # ──────────────────────────────────────────────────────────────────────────
    # 核心绘制逻辑：点击 -> 移动(跟随) -> 点击
    # ──────────────────────────────────────────────────────────────────────────
    def on_press(self, x: int, y: int):
        tool = self._state.tool
        mask = self._state.mask_img
        if mask is None:
            return

        # 第一下点击：开始绘制
        if self._phase == DrawPhase.IDLE:
            self._phase = DrawPhase.DRAWING
            self._last_pos = (x, y)
            self._state.push_undo()

            if tool == DrawTool.POLY:
                self._poly_points = [(x, y)]
            elif tool in (DrawTool.LINE, DrawTool.ERASER):
                # 原地画一个起始点
                color = self._state.current_draw_value if tool == DrawTool.LINE else 0
                brush = self._state.brush_size
                cv2.circle(mask, (x, y), max(1, brush // 2), color, -1)

        # 第二下点击：结束绘制
        elif self._phase == DrawPhase.DRAWING:
            if tool == DrawTool.POLY and len(self._poly_points) > 2:
                # 面状笔：闭合并填充
                pts = np.array(self._poly_points, np.int32)
                color = self._state.current_draw_value
                cv2.fillPoly(mask, [pts], color)

            self._poly_points = []
            self._last_pos = None
            self._phase = DrawPhase.IDLE

    def on_move(self, x: int, y: int):
        if self._phase != DrawPhase.DRAWING or self._last_pos is None:
            return

        tool = self._state.tool
        mask = self._state.mask_img
        if mask is None:
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

    def on_release(self, x: int, y: int):
        # 取消拖拽松开结束的逻辑，交由第二次 Click (on_press) 处理
        pass

    def on_double_click(self, x: int, y: int):
        # 兼容双击：防止用户连续点击两下导致状态机错乱，强制结束
        if self._phase == DrawPhase.DRAWING:
            self.on_press(x, y)

    def cancel(self):
        """取消当前笔划（Esc）"""
        self._poly_points = []
        self._last_pos = None
        self._phase = DrawPhase.IDLE

    def draw_line_preview(self, display_img: np.ndarray, cursor_pos: tuple[int, int] | None = None):
        # 由于我们改为直接实时在 mask 上画线了，不再需要收集节点画幽灵预览线
        pass