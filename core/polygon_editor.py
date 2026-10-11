"""已有面状标注的轮廓重建与顶点编辑。

掩膜只保存像素，不保存原始绘制顶点。本类从用户点击的连通区域
重建精确轮廓；顶点编辑只提交边界差异，整体移动保留原始像素及孔洞。
"""

from __future__ import annotations

import cv2
import numpy as np


class PolygonEditor:
    INITIAL_CONTROL_TOLERANCE_PX = 0.75

    def __init__(self) -> None:
        self.vertices: np.ndarray | None = None
        self.value: int = 0
        self._component_origin = (0, 0)
        self._component_mask: np.ndarray | None = None
        self._drag_vertices: np.ndarray | None = None
        self._drag_anchor: tuple[float, float] | None = None
        self._drag_vertex_index: int | None = None
        self.selected_vertex_index: int | None = None
        self._committed_vertices: np.ndarray | None = None
        self._exact_outline: np.ndarray | None = None

    @property
    def has_selection(self) -> bool:
        return self.vertices is not None and len(self.vertices) >= 3

    @property
    def is_dragging(self) -> bool:
        return self._drag_vertices is not None

    @property
    def outline_vertices(self) -> np.ndarray | None:
        """静止时显示真实像素轮廓；实际拖动期间显示候选编辑轮廓。"""
        if self._exact_outline is not None and np.array_equal(self.vertices, self._committed_vertices):
            return self._exact_outline
        return self.vertices

    def clear(self) -> None:
        self._drag_vertices = None
        self._drag_anchor = None
        self._drag_vertex_index = None
        self.selected_vertex_index = None
        self.vertices = None
        self.value = 0
        self._component_origin = (0, 0)
        self._component_mask = None
        self._committed_vertices = None
        self._exact_outline = None

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
        exact = contour.reshape(-1, 2)
        if len(exact) < 3:
            return False

        # Rasterized oblique straight lines contain staircase turns. Compress
        # these only in the initial control cage, with a fixed subpixel error.
        # Keep the exact outline/mask separately; never target a point count.
        polygon = cv2.approxPolyDP(contour, self.INITIAL_CONTROL_TOLERANCE_PX, True).reshape(-1, 2)
        if len(polygon) < 3:
            polygon = exact

        polygon = polygon.astype(np.float64)
        polygon[:, 0] += origin[0]
        polygon[:, 1] += origin[1]
        self._exact_outline = exact.astype(np.float64) + origin
        self.vertices = polygon
        self.value = value
        self._store_component(component.astype(bool), origin)
        self._committed_vertices = self.vertices.copy()
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

    def select_vertex(self, index: int | None) -> None:
        if index is None or self.vertices is None or not (0 <= index < len(self.vertices)):
            self.selected_vertex_index = None
            return
        self.selected_vertex_index = index

    def contains(self, x: float, y: float) -> bool:
        if not self.has_selection:
            return False
        if not self.is_dragging and self._component_mask is not None:
            x0, y0 = self._component_origin
            ix, iy = int(np.floor(x)) - x0, int(np.floor(y)) - y0
            height, width = self._component_mask.shape
            return 0 <= ix < width and 0 <= iy < height and bool(self._component_mask[iy, ix])
        return cv2.pointPolygonTest(
            self.vertices.reshape(-1, 1, 2).astype(np.float32),
            (float(x), float(y)),
            False,
        ) >= 0

    def insert_vertex(self, x: float, y: float, tolerance: float) -> int | None:
        """在最近边上插入控制点；点击距轮廓过远时不处理。"""
        self.cancel_drag()
        if not self.has_selection:
            return None
        vertices = self.vertices.astype(np.float64)
        best = self._project_to_edges(self.outline_vertices, x, y)
        if best is None or best[0] > tolerance:
            return None
        inserted = best[2]
        control_edge = self._closest_edge(*inserted)
        for index in (control_edge[1], (control_edge[1] + 1) % len(vertices)):
            if np.linalg.norm(inserted - vertices[index]) < 1e-9:
                self.selected_vertex_index = index
                return index
        was_committed = np.array_equal(self.vertices, self._committed_vertices)
        insert_at = control_edge[1] + 1
        self.vertices = np.insert(vertices, insert_at, inserted, axis=0)
        if was_committed:
            # Splitting an edge does not change its geometry or the mask. Keep
            # this exact subdivision as the baseline for the next real edit.
            self._committed_vertices = self.vertices.copy()
        self.selected_vertex_index = insert_at
        return insert_at

    def hit_edge(self, x: float, y: float, tolerance: float) -> bool:
        best = self._project_to_edges(self.outline_vertices, x, y)
        return best is not None and best[0] <= tolerance

    def _closest_edge(self, x: float, y: float):
        if not self.has_selection:
            return None
        return self._project_to_edges(self.vertices, x, y)

    @staticmethod
    def _project_to_edges(vertices, x: float, y: float):
        if vertices is None or len(vertices) < 2:
            return None
        vertices = vertices.astype(np.float64)
        edges = np.roll(vertices, -1, axis=0) - vertices
        lengths2 = np.sum(edges * edges, axis=1)
        offsets = np.asarray((x, y)) - vertices
        ratios = np.divide(np.sum(offsets * edges, axis=1), lengths2,
                           out=np.zeros(len(vertices)), where=lengths2 > 0)
        projected = vertices + np.clip(ratios, 0, 1)[:, None] * edges
        distances = np.linalg.norm(projected - (x, y), axis=1)
        index = int(np.argmin(distances))
        return float(distances[index]), index, projected[index]

    def begin_drag(self, x: float, y: float, vertex_index: int | None) -> None:
        if not self.has_selection:
            return
        self.select_vertex(vertex_index)
        self._drag_vertices = self.vertices.copy()
        self._drag_anchor = (x, y)
        self._drag_vertex_index = vertex_index

    def drag_to(self, x: float, y: float, shape: tuple[int, int]) -> None:
        if self._drag_vertices is None or self._drag_anchor is None:
            return
        height, width = shape
        if self._drag_vertex_index is not None:
            self.vertices[self._drag_vertex_index] = (
                max(0, min(width - 1, x)),
                max(0, min(height - 1, y)),
            )
            return
        dx, dy = round(x - self._drag_anchor[0]), round(y - self._drag_anchor[1])
        # Constrain the translation, not individual vertices: reaching an image
        # edge must not squash the polygon or destroy its interior holes.
        min_x, min_y = np.ceil(-self._drag_vertices.min(axis=0)).astype(int)
        max_x, max_y = np.floor((width - 1, height - 1) - self._drag_vertices.max(axis=0)).astype(int)
        if self._component_mask is not None:
            x0, y0 = self._component_origin
            h, w = self._component_mask.shape
            min_x, min_y = max(min_x, -x0), max(min_y, -y0)
            max_x, max_y = min(max_x, width - x0 - w), min(max_y, height - y0 - h)
        dx, dy = int(np.clip(dx, min_x, max_x)), int(np.clip(dy, min_y, max_y))
        self.vertices = self._drag_vertices + (dx, dy)

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

    def apply(self, mask: np.ndarray) -> bool:
        if not self.has_selection or self._component_mask is None or self._committed_vertices is None:
            return False
        if np.array_equal(self.vertices, self._committed_vertices):
            self._finish_apply()
            return False
        x0, y0 = self._component_origin
        height, width = self._component_mask.shape
        if self.is_dragging and self._drag_vertex_index is None:
            delta = self.vertices - self._committed_vertices
            if np.allclose(delta, delta[0], rtol=0, atol=1e-9):
                dx, dy = np.rint(delta[0]).astype(int)
                old = mask[y0:y0 + height, x0:x0 + width]
                old[self._component_mask & (old == self.value)] = 0
                new = mask[y0 + dy:y0 + dy + height, x0 + dx:x0 + dx + width]
                new[self._component_mask] = self.value
                self._component_origin = (x0 + int(dx), y0 + int(dy))
                if self._exact_outline is not None:
                    self._exact_outline = self._exact_outline + (dx, dy)
                self._finish_apply()
                return True

        all_vertices = np.vstack((self._committed_vertices, self.vertices))
        height_img, width_img = mask.shape[:2]
        left = max(0, min(x0, int(np.floor(all_vertices[:, 0].min())) - 1))
        top = max(0, min(y0, int(np.floor(all_vertices[:, 1].min())) - 1))
        right = min(width_img, max(x0 + width, int(np.ceil(all_vertices[:, 0].max())) + 2))
        bottom = min(height_img, max(y0 + height, int(np.ceil(all_vertices[:, 1].max())) + 2))
        shape = (bottom - top, right - left)
        origin = (left, top)
        old_outline = self._rasterize(self._committed_vertices, origin, shape)
        new_outline = self._rasterize(self.vertices, origin, shape)
        component = np.zeros(shape, dtype=bool)
        component[y0 - top:y0 - top + height, x0 - left:x0 - left + width] = self._component_mask
        removed = component & old_outline & ~new_outline
        added = new_outline & ~old_outline
        region = mask[top:bottom, left:right]
        changed = bool(np.any(removed & (region == self.value)) or np.any(added & (region != self.value)))
        region[removed & (region == self.value)] = 0
        region[added] = self.value
        component = (component & ~removed) | added
        self._store_component(component, origin)
        self._refresh_exact_outline()
        self._finish_apply()
        return changed

    def _finish_apply(self) -> None:
        self._committed_vertices = self.vertices.copy() if self.vertices is not None else None
        self._drag_vertices = None
        self._drag_anchor = None
        self._drag_vertex_index = None

    def _refresh_exact_outline(self):
        if self._component_mask is None:
            self._exact_outline = None
            return
        contours, _ = cv2.findContours(
            self._component_mask.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE,
        )
        if contours:
            contour = max(contours, key=cv2.contourArea)
            self._exact_outline = contour.reshape(-1, 2).astype(np.float64) + self._component_origin

    def delete(self, mask: np.ndarray) -> bool:
        """删除当前选中的连通区域。"""
        if not self.has_selection or self._component_mask is None:
            return False
        x0, y0 = self._component_origin
        height, width = self._component_mask.shape
        selected = mask[y0:y0 + height, x0:x0 + width]
        selected[self._component_mask] = 0
        self.clear()
        return True

    def delete_selected_vertex(self) -> bool:
        """删除当前选中的控制点，并保证多边形至少有 3 个点。"""
        index = self.selected_vertex_index
        if self.vertices is None or index is None or len(self.vertices) <= 3:
            return False
        self.vertices = np.delete(self.vertices, index, axis=0)
        self.selected_vertex_index = None
        return True

    @staticmethod
    def _rasterize(vertices, origin, shape):
        raster = np.zeros(shape, dtype=np.uint8)
        local = np.rint((vertices - origin) * 256).astype(np.int32)
        cv2.fillPoly(raster, [local.reshape(-1, 1, 2)], 1, shift=8)
        return raster.astype(bool)

    def _store_component(self, component, origin):
        rows = np.flatnonzero(np.any(component, axis=1))
        columns = np.flatnonzero(np.any(component, axis=0))
        if not len(rows) or not len(columns):
            self.clear()
            return
        x0, x1 = int(columns[0]), int(columns[-1]) + 1
        y0, y1 = int(rows[0]), int(rows[-1]) + 1
        self._component_origin = (origin[0] + x0, origin[1] + y0)
        self._component_mask = component[y0:y1, x0:x1].copy()
