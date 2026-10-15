# core/__init__.py
from core.config import DEFAULT_CLASSES, DrawTool, MAX_UNDO, VALID_IMAGE_EXTS
from core.annotation_state import AnnotationState
from core.draw_engine import DrawEngine, DrawPhase
from core.polygon_editor import PolygonEditor
from core.similarity_fill import (
    apply_similarity_fill, similar_connected_region, similarity_fill_target,
)
