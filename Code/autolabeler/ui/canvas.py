# -*- coding: utf-8 -*-
"""이미지 캔버스의 그리기, 이동, 편집 동작을 처리합니다."""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import QPoint, QPointF, QRect, QRectF, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QBrush, QColor, QCursor, QImage, QKeyEvent, QMouseEvent, QPainter, QPen, QWheelEvent
from PyQt6.QtWidgets import QWidget

from ..constants import CLASS_COLORS
from ..models import LabelBox


class ImageCanvas(QWidget):
    """YOLO 박스 표시와 사용자 입력 모드를 담당하는 캔버스입니다."""

    box_created = pyqtSignal(float, float, float, float)
    mask_requested = pyqtSignal(QRect)
    label_edited = pyqtSignal(int, float, float, float, float)
    label_class_change_requested = pyqtSignal(int)
    label_deleted = pyqtSignal(int)
    label_selection_changed = pyqtSignal(int)
    interaction_finished = pyqtSignal()
    zoom_changed = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        # 클릭하지 않아도 포인터 이동만으로 십자선/호버 상태가 갱신되도록 마우스 트래킹을 켭니다.
        self.setMouseTracking(True)
        self.current_mode = "hand"
        self.input_mode = "drag"
        self.image_path: Path | None = None
        self.image = QImage()
        self.labels: list[LabelBox] = []
        self.hover_point: QPoint | None = None
        self.start_point: QPoint | None = None
        self.preview_end: QPoint | None = None
        self.first_click_point: QPoint | None = None
        self.zoom_factor = 1.0
        self.class_color_hex = "#7f7f7f"
        self.class_name = ""
        self.pan_offset = QPointF(0.0, 0.0)
        self.pan_anchor: QPoint | None = None
        self.pan_start_offset = QPointF(0.0, 0.0)
        self.edit_label_index: int | None = None
        self.selected_label_index: int | None = None
        self.edit_mode_kind: str | None = None
        self.edit_anchor_name: str | None = None
        self.edit_start_rect: QRectF | None = None
        self.hover_edit_index: int | None = None
        self.hover_edit_kind: str | None = None
        self.hover_handle_name: str | None = None
        self.held_class_index: int | None = None
        self.erased_feedback_active = False
        self.erased_feedback_timer = QTimer(self)
        self.erased_feedback_timer.setSingleShot(True)
        self.erased_feedback_timer.timeout.connect(self._clear_erased_feedback)
        self.pending_delete_point: QPoint | None = None

    def set_input_mode(self, mode: str) -> None:
        """사각형 입력 방식을 갱신합니다."""
        self.input_mode = mode
        self.first_click_point = None

    def load_image(self, image_path: Path, labels: list[LabelBox]) -> None:
        """새 이미지를 불러오고 화면 상태를 초기화합니다."""
        self.image_path = image_path
        self.image = QImage(str(image_path))
        self.labels = labels
        self.hover_point = None
        self.start_point = None
        self.preview_end = None
        self.first_click_point = None
        self.zoom_factor = 1.0
        self.pan_offset = QPointF(0.0, 0.0)
        self.pan_anchor = None
        self._clear_edit_state()
        self.set_selected_label_index(None)
        self.update()
        self.zoom_changed.emit()

    def clear_image(self) -> None:
        """현재 표시 중인 이미지와 라벨을 비웁니다."""
        self.image_path = None
        self.image = QImage()
        self.labels = []
        self.hover_point = None
        self.start_point = None
        self.preview_end = None
        self.first_click_point = None
        self.zoom_factor = 1.0
        self.pan_offset = QPointF(0.0, 0.0)
        self.pan_anchor = None
        self._clear_edit_state()
        self.set_selected_label_index(None)
        self.update()
        self.zoom_changed.emit()

    def set_mode(self, mode: str) -> None:
        """현재 모드를 손, 그리기, 마스킹, 편집 중 하나로 변경합니다."""
        self.current_mode = mode
        self.start_point = None
        self.preview_end = None
        self.first_click_point = None
        self.pan_anchor = None
        self._clear_edit_state()
        if mode != "edit":
            self.set_selected_label_index(None)
        self._update_cursor()
        self.update()

    def set_active_class_info(self, color_hex: str, class_name: str) -> None:
        """현재 선택 클래스의 색상과 이름을 표시용으로 저장합니다."""
        self.class_color_hex = color_hex
        self.class_name = class_name
        self.update()

    def set_labels(self, labels: list[LabelBox]) -> None:
        """현재 라벨 목록을 갱신합니다."""
        self.labels = labels
        if self.selected_label_index is not None and self.selected_label_index >= len(labels):
            self.set_selected_label_index(None)
        self.update()

    def set_held_class_index(self, class_index: int | None) -> None:
        """클래스 단축키를 누른 상태를 편집 클릭 처리에 사용합니다."""
        self.held_class_index = class_index

    def set_selected_label_index(self, label_index: int | None, emit_signal: bool = True) -> None:
        """지속 선택 상태의 라벨 인덱스를 갱신합니다."""
        if label_index is not None and (label_index < 0 or label_index >= len(self.labels)):
            label_index = None
        if self.selected_label_index == label_index:
            return
        self.selected_label_index = label_index
        if emit_signal:
            self.label_selection_changed.emit(-1 if label_index is None else label_index)
        self.update()

    def reset_view(self) -> None:
        """이미지를 화면 맞춤 상태로 되돌립니다."""
        self.zoom_factor = 1.0
        self.pan_offset = QPointF(0.0, 0.0)
        self._update_cursor()
        self.update()
        self.zoom_changed.emit()

    def is_fit_view(self) -> bool:
        """현재 화면이 배율/위치 초기화 상태인지 확인합니다."""
        return (
            abs(self.zoom_factor - 1.0) < 0.0001
            and abs(self.pan_offset.x()) < 0.0001
            and abs(self.pan_offset.y()) < 0.0001
        )

    def zoom_to_cursor(self, zoom_factor: float) -> None:
        """현재 마우스 커서가 가리키는 이미지 지점을 기준으로 지정 배율까지 확대합니다."""
        if self.image.isNull():
            return
        cursor_point = self.mapFromGlobal(QCursor.pos())
        self.zoom_to_widget_point(cursor_point, zoom_factor)

    def zoom_to_widget_point(self, point: QPoint, zoom_factor: float) -> None:
        """위젯 좌표의 특정 지점을 기준으로 확대 배율과 위치를 계산합니다."""
        target_before = self.target_rect()
        if target_before.isNull():
            return

        pointer = self.clamp_to_image(point)
        if pointer is None:
            return

        new_zoom = max(0.2, min(8.0, zoom_factor))
        anchor_x_ratio = (pointer.x() - target_before.left()) / max(1, target_before.width())
        anchor_y_ratio = (pointer.y() - target_before.top()) / max(1, target_before.height())
        fit_size = self.image.size().scaled(self.size(), Qt.AspectRatioMode.KeepAspectRatio)
        scaled_width = max(1, int(fit_size.width() * new_zoom))
        scaled_height = max(1, int(fit_size.height() * new_zoom))
        target_left = pointer.x() - anchor_x_ratio * scaled_width
        target_top = pointer.y() - anchor_y_ratio * scaled_height

        self.zoom_factor = new_zoom
        self.pan_offset = QPointF(
            target_left - (self.width() - scaled_width) / 2.0,
            target_top - (self.height() - scaled_height) / 2.0,
        )
        self._update_cursor()
        self.update()
        self.zoom_changed.emit()

    def wheelEvent(self, event: QWheelEvent) -> None:  # noqa: N802
        """휠 입력 시 마우스 포인터가 가리키는 이미지 지점을 기준으로 확대/축소합니다."""
        if self.image.isNull():
            return
        delta = event.angleDelta().y()
        if delta == 0:
            return

        target_before = self.target_rect()
        if target_before.isNull():
            return

        pointer = self.clamp_to_image(event.position().toPoint())
        if pointer is None:
            return

        old_zoom = self.zoom_factor
        scale_step = 1.1 if delta > 0 else 0.9
        new_zoom = max(0.2, min(8.0, old_zoom * scale_step))
        if new_zoom == old_zoom:
            return

        # 포인터 아래 이미지 내 상대 위치를 새 확대율에서도 같은 화면 좌표에 유지합니다.
        self.zoom_to_widget_point(pointer, new_zoom)

    def original_display_scale(self) -> float:
        """현재 화면 표시 크기가 원본 이미지 크기의 몇 배인지 반환합니다."""
        if self.image.isNull() or self.image.width() <= 0:
            return 0.0
        target = self.target_rect()
        if target.isNull():
            return 0.0
        return target.width() / self.image.width()

    def resizeEvent(self, event) -> None:  # noqa: N802
        """캔버스 크기가 바뀌면 원본 대비 표시 비율을 다시 알립니다."""
        super().resizeEvent(event)
        self.zoom_changed.emit()

    def paintEvent(self, event) -> None:  # noqa: N802
        """이미지, 기존 박스, 미리보기, 모드별 가이드를 그립니다."""
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#101010"))

        if self.image.isNull():
            painter.end()
            return

        target_rect = self.target_rect()
        painter.drawImage(target_rect, self.image)

        for index, label in enumerate(self.labels):
            rect = self._normalized_to_widget_rect(label.x_center, label.y_center, label.width, label.height)
            is_selected = self.current_mode == "edit" and (
                self.edit_label_index == index or self.selected_label_index == index
            )
            pen_width = 4 if is_selected else 2
            painter.setPen(QPen(QColor(label.color_hex), pen_width))
            # 사각형 본체는 항상 테두리만 그려야 하므로 브러시를 비워 채워짐을 방지합니다.
            painter.setBrush(QBrush(Qt.BrushStyle.NoBrush))
            painter.drawRect(rect)
            if self.current_mode == "edit":
                self._draw_resize_handles(painter, rect, QColor(label.color_hex))

        preview_rect = self._current_preview_rect()
        if preview_rect is not None:
            color = QColor("#ffffff") if self.current_mode == "mask" else QColor(self.class_color_hex)
            painter.setPen(QPen(color, 2, Qt.PenStyle.DashLine))
            painter.drawRect(preview_rect)

        self._draw_mode_guides(painter, target_rect)
        painter.end()

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        """모드별 입력 시작을 처리합니다."""
        if self.image.isNull():
            return
        self.setFocus(Qt.FocusReason.MouseFocusReason)

        point = self.clamp_to_image(event.position().toPoint())
        if point is None:
            return

        if self.current_mode == "edit" and event.button() == Qt.MouseButton.RightButton:
            self._update_hover_edit_target(point)
            if self.hover_edit_index is None:
                self.set_selected_label_index(None)
            else:
                self.set_selected_label_index(self.hover_edit_index)
                self._delete_label_at_point(point)
            return

        if event.button() != Qt.MouseButton.LeftButton:
            return

        if self.current_mode == "hand":
            if self.zoom_factor > 1.0:
                self.pan_anchor = point
                self.pan_start_offset = QPointF(self.pan_offset)
                self._update_cursor(True)
            return

        if self.current_mode == "edit":
            if self.held_class_index is not None:
                self._update_hover_edit_target(point)
                if self.hover_edit_index is not None:
                    self.set_selected_label_index(self.hover_edit_index)
                    self.label_class_change_requested.emit(self.hover_edit_index)
                    self.update()
                    return
            if not self._begin_edit(point):
                self.set_selected_label_index(None)
                if self.zoom_factor > 1.0:
                    # 편집 대상이 없는 빈 영역에서는 확대된 화면을 손 도구처럼 이동할 수 있게 합니다.
                    self.pan_anchor = point
                    self.pan_start_offset = QPointF(self.pan_offset)
                    self._update_cursor(True)
            return

        if self.current_mode not in {"draw", "mask"}:
            return

        if self.input_mode == "two_click":
            if self.first_click_point is None:
                self.first_click_point = point
                self.preview_end = point
            else:
                self._emit_rectangle(self.first_click_point, point)
                self.first_click_point = None
                self.preview_end = None
            self.update()
            return

        self.start_point = point
        self.preview_end = point
        self.update()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        """모드별 이동 중 갱신 처리를 수행합니다."""
        point = self.clamp_to_image(event.position().toPoint())
        self.hover_point = point

        if self.current_mode == "hand":
            if self.pan_anchor is not None and point is not None:
                delta = point - self.pan_anchor
                self.pan_offset = QPointF(self.pan_start_offset.x() + delta.x(), self.pan_start_offset.y() + delta.y())
            self.update()
            return

        if point is None:
            self.update()
            return

        if self.current_mode == "edit":
            if self.pan_anchor is not None and point is not None:
                delta = point - self.pan_anchor
                self.pan_offset = QPointF(self.pan_start_offset.x() + delta.x(), self.pan_start_offset.y() + delta.y())
                self.update()
                return
            self._update_hover_edit_target(point)
            self._update_edit(point)
            return

        if self.input_mode == "two_click" and self.first_click_point is not None:
            if event.buttons() & Qt.MouseButton.LeftButton:
                return
            self.preview_end = point
            self.update()
            return

        if self.start_point is not None:
            self.preview_end = point
        self.update()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        """모드별 마우스 버튼 해제 처리를 수행합니다."""
        if self.current_mode == "hand":
            self.pan_anchor = None
            self._update_cursor()
            return

        if self.current_mode == "edit":
            if self.pan_anchor is not None:
                self.pan_anchor = None
                self._update_cursor()
                return
            self._finish_edit()
            return

        if self.input_mode != "drag":
            return
        if self.start_point is None or self.preview_end is None:
            return
        self._emit_rectangle(self.start_point, self.preview_end)
        self.start_point = None
        self.preview_end = None
        self.update()

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        """선택된 라벨을 방향키로 1px, Shift+방향키로 10px 이동합니다."""
        if self.current_mode != "edit" or self.selected_label_index is None:
            super().keyPressEvent(event)
            return

        move_map = {
            Qt.Key.Key_Left: (-1, 0),
            Qt.Key.Key_Right: (1, 0),
            Qt.Key.Key_Up: (0, -1),
            Qt.Key.Key_Down: (0, 1),
        }
        direction = move_map.get(event.key())
        if direction is None:
            super().keyPressEvent(event)
            return

        step = 10 if event.modifiers() & Qt.KeyboardModifier.ShiftModifier else 1
        self._move_selected_label_by_pixels(direction[0] * step, direction[1] * step)
        event.accept()

    def target_rect(self) -> QRect:
        """현재 배율과 이동량을 반영한 실제 이미지 표시 영역을 반환합니다."""
        if self.image.isNull():
            return QRect()

        fit_size = self.image.size().scaled(self.size(), Qt.AspectRatioMode.KeepAspectRatio)
        scaled_width = max(1, int(fit_size.width() * self.zoom_factor))
        scaled_height = max(1, int(fit_size.height() * self.zoom_factor))
        x = int((self.width() - scaled_width) // 2 + self.pan_offset.x())
        y = int((self.height() - scaled_height) // 2 + self.pan_offset.y())
        return QRect(x, y, scaled_width, scaled_height)

    def clamp_to_image(self, point: QPoint) -> QPoint | None:
        """포인터가 이미지 밖으로 나가도 가장자리 좌표로 보정해 반환합니다."""
        target = self.target_rect()
        if target.isNull():
            return None
        x = min(max(point.x(), target.left()), target.right())
        y = min(max(point.y(), target.top()), target.bottom())
        return QPoint(x, y)

    def widget_rect_to_normalized(self, rect: QRect) -> tuple[float, float, float, float]:
        """화면 사각형을 YOLO 정규화 좌표로 변환합니다."""
        target = self.target_rect()
        x1 = (rect.left() - target.left()) / target.width()
        y1 = (rect.top() - target.top()) / target.height()
        x2 = (rect.right() - target.left()) / target.width()
        y2 = (rect.bottom() - target.top()) / target.height()
        width = max(0.0, min(1.0, x2 - x1))
        height = max(0.0, min(1.0, y2 - y1))
        x_center = max(0.0, min(1.0, x1 + width / 2.0))
        y_center = max(0.0, min(1.0, y1 + height / 2.0))
        return x_center, y_center, width, height

    def _constrain_edit_rect_to_target(self, rect: QRectF, keep_size: bool) -> QRectF:
        """편집 중인 박스가 이미지 표시 영역 밖으로 나가지 않도록 보정합니다."""
        target = QRectF(self.target_rect())
        if target.isNull():
            return rect

        if keep_size:
            constrained = QRectF(rect)
            if constrained.width() > target.width():
                constrained.setWidth(target.width())
            if constrained.height() > target.height():
                constrained.setHeight(target.height())
            if constrained.left() < target.left():
                constrained.moveLeft(target.left())
            if constrained.right() > target.right():
                constrained.moveRight(target.right())
            if constrained.top() < target.top():
                constrained.moveTop(target.top())
            if constrained.bottom() > target.bottom():
                constrained.moveBottom(target.bottom())
            return constrained

        left = min(max(rect.left(), target.left()), target.right())
        right = min(max(rect.right(), target.left()), target.right())
        top = min(max(rect.top(), target.top()), target.bottom())
        bottom = min(max(rect.bottom(), target.top()), target.bottom())
        return QRectF(QPointF(left, top), QPointF(right, bottom)).normalized()

    def _current_preview_rect(self) -> QRect | None:
        """현재 작업 중인 사각형 미리보기 영역을 계산합니다."""
        if self.input_mode == "two_click":
            if self.first_click_point is None or self.preview_end is None:
                return None
            return QRect(self.first_click_point, self.preview_end).normalized()
        if self.start_point is None or self.preview_end is None:
            return None
        return QRect(self.start_point, self.preview_end).normalized()

    def _normalized_to_widget_rect(self, x_center: float, y_center: float, width: float, height: float) -> QRectF:
        """YOLO 정규화 좌표를 현재 화면 좌표로 환산합니다."""
        target = self.target_rect()
        left = target.left() + (x_center - width / 2.0) * target.width()
        top = target.top() + (y_center - height / 2.0) * target.height()
        return QRectF(left, top, width * target.width(), height * target.height())

    def _emit_rectangle(self, start: QPoint, end: QPoint) -> None:
        """확정된 사각형을 외부 신호로 전달합니다."""
        rect = QRect(start, end).normalized()
        if rect.width() < 4 or rect.height() < 4:
            return
        if self.current_mode == "draw":
            self.box_created.emit(*self.widget_rect_to_normalized(rect))
            self.interaction_finished.emit()
        elif self.current_mode == "mask":
            self.mask_requested.emit(rect)
            self.interaction_finished.emit()

    def _draw_mode_guides(self, painter: QPainter, target_rect: QRect) -> None:
        """손 모드와 그리기 모드의 십자선/포인트 안내를 그립니다."""
        if self.hover_point is not None:
            color = QColor("#9a9a9a")
            draw_circle = False
            text = ""
            text_color = QColor("#ff9f1c")
            outlined_text = False

            if self.current_mode == "draw":
                color = QColor(self.class_color_hex)
                draw_circle = True
                text = self.class_name
                text_color = QColor(self.class_color_hex)
            elif self.current_mode == "mask":
                color = QColor("#ffffff")
                draw_circle = True
                text = "Masking"
                text_color = QColor("#ffffff")
                outlined_text = True
            elif self.current_mode == "edit":
                if self.held_class_index is not None:
                    # 클래스 키를 누른 상태에서는 기존 편집 대신 클래스 변경 상태를 커서에 표시합니다.
                    color = QColor(CLASS_COLORS[self.held_class_index % len(CLASS_COLORS)])
                    draw_circle = True
                    text = "Class Change"
                    text_color = QColor("#ff9f1c")
                elif self.erased_feedback_active:
                    color = QColor("#ff9f1c")
                    draw_circle = True
                    text = "Erased"
                elif self.hover_edit_kind == "resize":
                    color = QColor("#ff9f1c")
                    draw_circle = True
                    text = "Point"
                elif self.hover_edit_kind == "move":
                    color = QColor("#9a9a9a")
                    draw_circle = False
                    text = "Position"
                else:
                    color = QColor("#ff9f1c")
                    draw_circle = True
                    text = "Edit"

            self._draw_crosshair(painter, target_rect, self.hover_point, color, draw_circle)
            if text:
                self._draw_hover_text(
                    painter,
                    self.hover_point + QPoint(6, -6),
                    text,
                    text_color,
                    outlined_text,
                )

        if self.current_mode in {"draw", "mask"}:
            anchor_point = self.start_point if self.start_point is not None else self.first_click_point
            if anchor_point is not None:
                anchor_color = QColor("#ffffff") if self.current_mode == "mask" else QColor(self.class_color_hex)
                self._draw_crosshair(painter, target_rect, anchor_point, anchor_color, True)

    def _draw_crosshair(
        self,
        painter: QPainter,
        target_rect: QRect,
        point: QPoint,
        color: QColor,
        draw_circle: bool,
    ) -> None:
        """한 점을 기준으로 1px 십자선과 선택적 원 표시를 그립니다."""
        painter.setPen(QPen(color, 1))
        painter.drawLine(point.x(), target_rect.top(), point.x(), target_rect.bottom())
        painter.drawLine(target_rect.left(), point.y(), target_rect.right(), point.y())
        if draw_circle:
            painter.setBrush(color)
            painter.drawEllipse(point, 2, 2)

    def _draw_hover_text(
        self,
        painter: QPainter,
        point: QPoint,
        text: str,
        color: QColor,
        outlined: bool,
    ) -> None:
        """포인터 안내 문구를 그리고, 필요하면 검은 외곽선을 함께 표시합니다."""
        if outlined:
            painter.setPen(QPen(QColor("#000000"), 1))
            for offset in (QPoint(-1, 0), QPoint(1, 0), QPoint(0, -1), QPoint(0, 1)):
                painter.drawText(point + offset, text)
        painter.setPen(QPen(color, 1))
        painter.drawText(point, text)

    def _draw_resize_handles(self, painter: QPainter, rect: QRectF, color: QColor) -> None:
        """편집 모드에서 네 꼭지점 리사이즈 핸들을 그립니다."""
        painter.setBrush(color)
        for handle_rect in self._handle_rects(rect).values():
            painter.drawRect(handle_rect)

    def _handle_rects(self, rect: QRectF) -> dict[str, QRectF]:
        """사각형 네 꼭지점의 핸들 영역을 계산합니다."""
        # 확대 배율이 높을수록 포인트를 키워 클릭 판정과 표시 크기를 함께 넓힙니다.
        if self.zoom_factor >= 3.0:
            size = 12.0
        elif self.zoom_factor >= 1.5:
            size = 9.0
        else:
            size = 6.0
        half = size / 2.0
        return {
            "tl": QRectF(rect.left() - half, rect.top() - half, size, size),
            "tr": QRectF(rect.right() - half, rect.top() - half, size, size),
            "bl": QRectF(rect.left() - half, rect.bottom() - half, size, size),
            "br": QRectF(rect.right() - half, rect.bottom() - half, size, size),
        }

    def _begin_edit(self, point: QPoint) -> bool:
        """편집 모드에서 이동 또는 리사이즈할 대상을 선택합니다."""
        self._update_hover_edit_target(point)
        if self.hover_edit_index is None:
            return False
        self.set_selected_label_index(self.hover_edit_index)
        rect = self._normalized_to_widget_rect(
            self.labels[self.hover_edit_index].x_center,
            self.labels[self.hover_edit_index].y_center,
            self.labels[self.hover_edit_index].width,
            self.labels[self.hover_edit_index].height,
        )
        self.edit_label_index = self.hover_edit_index
        self.edit_mode_kind = self.hover_edit_kind
        self.edit_anchor_name = self.hover_handle_name
        self.edit_start_rect = QRectF(rect)
        if self.edit_mode_kind == "move":
            self.start_point = QPoint(point)
        self.update()
        return True

    def _update_edit(self, point: QPoint) -> None:
        """편집 중인 박스를 현재 포인터 위치에 맞춰 갱신합니다."""
        if self.edit_label_index is None or self.edit_start_rect is None:
            self.update()
            return

        rect = QRectF(self.edit_start_rect)
        if self.edit_mode_kind == "move" and self.start_point is not None:
            delta = point - self.start_point
            rect.translate(delta.x(), delta.y())
            self.start_point = QPoint(point)
            rect = self._constrain_edit_rect_to_target(rect, keep_size=True)
        elif self.edit_mode_kind == "resize" and self.edit_anchor_name is not None:
            if self.edit_anchor_name == "tl":
                rect.setTopLeft(QPointF(point))
            elif self.edit_anchor_name == "tr":
                rect.setTopRight(QPointF(point))
            elif self.edit_anchor_name == "bl":
                rect.setBottomLeft(QPointF(point))
            elif self.edit_anchor_name == "br":
                rect.setBottomRight(QPointF(point))
            rect = rect.normalized()
            rect = self._constrain_edit_rect_to_target(rect, keep_size=False)

        x_center, y_center, width, height = self.widget_rect_to_normalized(rect.toRect())
        label = self.labels[self.edit_label_index]
        label.x_center = x_center
        label.y_center = y_center
        label.width = width
        label.height = height
        # 다음 이동 계산이 현재 결과를 기준으로 이어지도록 시작 사각형을 갱신합니다.
        self.edit_start_rect = QRectF(rect)
        self.update()

    def _finish_edit(self) -> None:
        """편집이 끝나면 변경 내용을 외부로 알립니다."""
        if self.edit_label_index is None:
            return
        label = self.labels[self.edit_label_index]
        self.label_edited.emit(
            self.edit_label_index,
            label.x_center,
            label.y_center,
            label.width,
            label.height,
        )
        self._clear_edit_state()
        self.update()

    def _clear_edit_state(self) -> None:
        """편집 중 임시 상태를 초기화합니다."""
        self.edit_label_index = None
        self.edit_mode_kind = None
        self.edit_anchor_name = None
        self.edit_start_rect = None
        self.hover_edit_index = None
        self.hover_edit_kind = None
        self.hover_handle_name = None
        self.start_point = None

    def _delete_label_at_point(self, point: QPoint) -> None:
        """편집 모드에서 우클릭한 박스의 삭제를 메인 창에 요청합니다."""
        self._update_hover_edit_target(point)
        if self.hover_edit_index is None:
            return
        delete_index = self.hover_edit_index
        if delete_index < 0 or delete_index >= len(self.labels):
            return
        self.pending_delete_point = point
        self.label_deleted.emit(delete_index)

    def confirm_label_deleted(self, delete_index: int) -> None:
        """메인 창에서 확인된 라벨 삭제를 캔버스 상태에 반영합니다."""
        if delete_index < 0 or delete_index >= len(self.labels):
            return
        self.labels.pop(delete_index)
        self.erased_feedback_active = True
        self.erased_feedback_timer.start(2000)
        self._clear_edit_state()
        self.set_selected_label_index(None)
        self.hover_point = self.pending_delete_point
        self.pending_delete_point = None
        self.update()

    def cancel_label_delete(self) -> None:
        """라벨 삭제 확인이 취소되면 임시 삭제 지점을 초기화합니다."""
        self.pending_delete_point = None

    def _clear_erased_feedback(self) -> None:
        """Erased 안내 문구를 지우고 일반 편집 안내로 되돌립니다."""
        self.erased_feedback_active = False
        self.update()

    def _update_hover_edit_target(self, point: QPoint) -> None:
        """현재 포인터 위치에서 편집 가능한 대상을 탐색합니다."""
        self.hover_edit_index = None
        self.hover_edit_kind = None
        self.hover_handle_name = None
        for index in range(len(self.labels) - 1, -1, -1):
            rect = self._normalized_to_widget_rect(
                self.labels[index].x_center,
                self.labels[index].y_center,
                self.labels[index].width,
                self.labels[index].height,
            )
            for handle_name, handle_rect in self._handle_rects(rect).items():
                if handle_rect.contains(QPointF(point)):
                    self.hover_edit_index = index
                    self.hover_edit_kind = "resize"
                    self.hover_handle_name = handle_name
                    return
            hit_rect = QRectF(rect).adjusted(-3.0, -3.0, 3.0, 3.0)
            if hit_rect.contains(QPointF(point)):
                self.hover_edit_index = index
                self.hover_edit_kind = "move"
                return

    def _move_selected_label_by_pixels(self, dx: int, dy: int) -> None:
        """선택된 라벨을 화면 픽셀 단위로 이동하고 변경 내용을 알립니다."""
        if self.selected_label_index is None or self.selected_label_index >= len(self.labels):
            return

        target = self.target_rect()
        if target.isNull() or target.width() <= 0 or target.height() <= 0:
            return

        label = self.labels[self.selected_label_index]
        x_delta = dx / target.width()
        y_delta = dy / target.height()
        half_width = min(0.5, label.width / 2.0)
        half_height = min(0.5, label.height / 2.0)
        new_x = min(max(label.x_center + x_delta, half_width), 1.0 - half_width)
        new_y = min(max(label.y_center + y_delta, half_height), 1.0 - half_height)
        if new_x == label.x_center and new_y == label.y_center:
            return

        label.x_center = new_x
        label.y_center = new_y
        self.label_edited.emit(
            self.selected_label_index,
            label.x_center,
            label.y_center,
            label.width,
            label.height,
        )
        self.update()

    def _update_cursor(self, dragging: bool = False) -> None:
        """현재 모드와 줌 상태에 맞는 마우스 커서를 적용합니다."""
        if self.current_mode == "hand" and self.zoom_factor > 1.0 and dragging:
            self.setCursor(QCursor(Qt.CursorShape.ClosedHandCursor))
        elif self.current_mode == "hand" and self.zoom_factor > 1.0:
            self.setCursor(QCursor(Qt.CursorShape.ArrowCursor))
        else:
            self.setCursor(QCursor(Qt.CursorShape.CrossCursor if self.current_mode in {"draw", "mask"} else Qt.CursorShape.ArrowCursor))
