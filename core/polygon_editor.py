"""已有面状标注的轮廓重建与顶点编辑。

掩膜只保存像素，不保存原始绘制顶点。本类从用户点击的连通区域
重建简化轮廓，并在提交时仅替换该连通区域。
"""

from __future__ import annotations

import cv2
import numpy as np


class PolygonEditor:
    def __init__(self) -> None:
        self.vertices: np.ndarray | None = None
        self.value: int = 0
        self._component_origin = (0, 0)
        self._component_mask: np.ndarray | None = None
        self._drag_vertices: np.ndarray | None = None
        self._drag_anchor: tuple[int, int] | None = None
        self._drag_vertex_index: int | None = None

    @property
    def has_selection(self) -> bool:
        return self.vertices is not None and len(self.vertices) >= 3

    @property
    def is_dragging(self) -> bool:
        return self._drag_vertices is not None

    def clear(self) -> None:
        self._drag_vertices = None
        self._drag_anchor = None
        self._drag_vertex_index = None
        self.vertices = None
        self.value = 0
        self._component_origin = (0, 0)
        self._component_mask = None

    def select(self, mask: np.ndarray, x: int, y: int) -> bool:
        self.clear()
        height, width = mask.shape[:2]
        if not (0 <= x < width and 0 <= y < height):
            return False
        value = int(mask[y, x])
        if value == 0:
            return False

        origin, component = self._extract_component(mask, x, y, value)
        contours, _ = cv2.findContours(
            component, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )
        if not contours:
            return False
        contour = max(contours, key=cv2.contourArea)
        perimeter = cv2.arcLength(contour, True)
        epsilon = max(0.75, perimeter * 0.0015)
        polygon = cv2.approxPolyDP(contour, epsilon, True).reshape(-1, 2)
        while len(polygon) > 160:
            epsilon *= 1.5
            polygon = cv2.approxPolyDP(contour, epsilon, True).reshape(-1, 2)
        if len(polygon) < 3:
            return False

        polygon = polygon.astype(np.int32)
        polygon[:, 0] += origin[0]
        polygon[:, 1] += origin[1]
        self.vertices = polygon
        self.value = value
        self._component_origin = origin
        self._component_mask = component.astype(bool)
        return True

    @staticmethod
    def _extract_component(
        mask: np.ndarray, x: int, y: int, value: int
    ) -> tuple[tuple[int, int], np.ndarray]:
        """逐步扩大点击点周围的窗口，避免为大幅影像立即构造整图副本。"""
        height, width = mask.shape[:2]
        radius = 256
        while True:
            x0, x1 = max(0, x - radius), min(width, x + radius + 1)
            y0, y1 = max(0, y - radius), min(height, y + radius + 1)
            binary = (mask[y0:y1, x0:x1] == value).astype(np.uint8)
            work = binary.copy()
            flood_mask = np.zeros((work.shape[0] + 2, work.shape[1] + 2), np.uint8)
            cv2.floodFill(work, flood_mask, (x - x0, y - y0), 2)
            component = (work == 2).astype(np.uint8)
            touches_open_edge = (
                (x0 > 0 and np.any(component[:, 0]))
                or (x1 < width and np.any(component[:, -1]))
                or (y0 > 0 and np.any(component[0, :]))
                or (y1 < height and np.any(component[-1, :]))
            )
            if not touches_open_edge:
                return (x0, y0), component
            radius *= 2

    def hit_vertex(self, x: int, y: int, tolerance: float) -> int | None:
        if not self.has_selection:
            return None
        delta = self.vertices.astype(np.float64) - (x, y)
        distances = np.hypot(delta[:, 0], delta[:, 1])
        index = int(np.argmin(distances))
        return index if distances[index] <= tolerance else None

    def contains(self, x: int, y: int) -> bool:
        if not self.has_selection:
            return False
        return cv2.pointPolygonTest(
            self.vertices.reshape(-1, 1, 2).astype(np.float32),
            (float(x), float(y)),
            False,
        ) >= 0

    def insert_vertex(self, x: int, y: int, tolerance: float) -> int | None:
        """在最近边上插入控制点；点击距轮廓过远时不处理。"""
        if not self.has_selection:
            return None
        point = np.asarray((x, y), dtype=np.float64)
        vertices = self.vertices.astype(np.float64)
        best: tuple[float, int, np.ndarray] | None = None
        for index in range(len(vertices)):
            start = vertices[index]
            end = vertices[(index + 1) % len(vertices)]
            edge = end - start
            length2 = float(np.dot(edge, edge))
            ratio = 0.0 if length2 == 0 else float(
                np.clip(np.dot(point - start, edge) / length2, 0.0, 1.0)
            )
            projected = start + ratio * edge
            distance = float(np.linalg.norm(point - projected))
            if best is None or distance < best[0]:
                best = (distance, index, projected)
        if best is None or best[0] > tolerance:
            return None
        inserted = np.rint(best[2]).astype(np.int32)
        insert_at = best[1] + 1
        self.vertices = np.insert(self.vertices, insert_at, inserted, axis=0)
        return insert_at

    def begin_drag(self, x: int, y: int, vertex_index: int | None) -> None:
        if not self.has_selection:
            return
        self._drag_vertices = self.vertices.copy()
        self._drag_anchor = (x, y)
        self._drag_vertex_index = vertex_index

    def drag_to(self, x: int, y: int, shape: tuple[int, int]) -> None:
        if self._drag_vertices is None or self._drag_anchor is None:
            return
        height, width = shape
        if self._drag_vertex_index is not None:
            self.vertices[self._drag_vertex_index] = (
                max(0, min(width - 1, x)),
                max(0, min(height - 1, y)),
            )
            return
        dx, dy = x - self._drag_anchor[0], y - self._drag_anchor[1]
        moved = self._drag_vertices + (dx, dy)
        moved[:, 0] = np.clip(moved[:, 0], 0, width - 1)
        moved[:, 1] = np.clip(moved[:, 1], 0, height - 1)
        self.vertices = moved.astype(np.int32)

    def drag_changed(self) -> bool:
        return (
            self._drag_vertices is not None
            and self.vertices is not None
            and not np.array_equal(self._drag_vertices, self.vertices)
        )

    def cancel_drag(self) -> None:
        if self._drag_vertices is not None:
            self.vertices = self._drag_vertices
        self._drag_vertices = None
        self._drag_anchor = None
        self._drag_vertex_index = None

    def apply(self, mask: np.ndarray) -> None:
        if not self.has_selection or self._component_mask is None:
            return
        x0, y0 = self._component_origin
        height, width = self._component_mask.shape
        old = mask[y0:y0 + height, x0:x0 + width]
        old[self._component_mask] = 0
        cv2.fillPoly(mask, [self.vertices.reshape(-1, 1, 2)], self.value)
        self._update_component_from_polygon(mask.shape[:2])
        self._drag_vertices = None
        self._drag_anchor = None
        self._drag_vertex_index = None

    def _update_component_from_polygon(self, shape: tuple[int, int]) -> None:
        height, width = shape
        x, y, w, h = cv2.boundingRect(self.vertices.reshape(-1, 1, 2))
        x0, y0 = max(0, x), max(0, y)
        x1, y1 = min(width, x + w), min(height, y + h)
        component = np.zeros((y1 - y0, x1 - x0), np.uint8)
        local = self.vertices - (x0, y0)
        cv2.fillPoly(component, [local.reshape(-1, 1, 2)], 1)
        self._component_origin = (x0, y0)
        self._component_mask = component.astype(bool)
