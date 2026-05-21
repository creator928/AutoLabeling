# -*- coding: utf-8 -*-
"""이미지 캔버스의 그리기, 이동, 편집 동작을 처리합니다."""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import QPoint, QPointF, QRect, QRectF, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QBrush, QColor, QCursor, QImage, QMouseEvent, QPainter, QPen, QWheelEvent
from PyQt6.QtWidgets import QWidget

from ..models import LabelBox


class ImageCanvas(QWidget):
    """YOLO 박스 표시와 사용자 입력 모드를 담당하는 캔버스입니다."""

    box_created = pyqtSignal(float, float, float, float)
    mask_requested = pyqtSignal(QRect)
    label_edited = pyqtSignal(int, float, float, float, float)
    label_deleted = pyqtSignal(int)
    interaction_finished = pyqtSignal()

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
        self.edit_mode_kind: str | None = None
        self.edit_anchor_name: str | None = None
        self.edit_start_rect: QRectF | None = None
        self.hover_edit_index: int | None = None
        self.hover_edit_kind: str | None = None
        self.hover_handle_name: str | None = None
        self.erased_feedback_active = False
        self.erased_feedback_timer = QTimer(self)
        self.erased_feedback_timer.setSingleShot(True)
        self.erased_feedback_timer.timeout.connect(self._clear_erased_feedback)

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
        self.update()

    def set_mode(self, mode: str) -> None:
        """현재 모드를 손, 그리기, 마스킹, 편집 중 하나로 변경합니다."""
        self.current_mode = mode
        self.start_point = None
        self.preview_end = None
        self.first_click_point = None
        self.pan_anchor = None
        self._clear_edit_state()
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
        self.update()

    def reset_view(self) -> None:
        """이미지를 화면 맞춤 상태로 되돌립니다."""
        self.zoom_factor = 1.0
        self.pan_offset = QPointF(0.0, 0.0)
        self._update_cursor()
        self.update()

    def wheelEvent(self, event: QWheelEvent) -> None:  # noqa: N802
        """휠 입력으로 이미지를 확대/축소합니다."""
        if self.image.isNull():
            return
        delta = event.angleDelta().y()
        if delta == 0:
            return
        scale_step = 1.1 if delta > 0 else 0.9
        self.zoom_factor = max(0.2, min(8.0, self.zoom_factor * scale_step))
        self._update_cursor()
        self.update()

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
            pen_width = 3 if self.current_mode == "edit" and self.edit_label_index == index else 2
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

        point = self.clamp_to_image(event.position().toPoint())
        if point is None:
            return

        if self.current_mode == "edit" and event.button() == Qt.MouseButton.RightButton:
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
            if not self._begin_edit(point) and self.zoom_factor > 1.0:
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
                if self.erased_feedback_active:
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
        """편집 모드에서 우클릭한 박스를 삭제하고 잠시 Erased 표시를 유지합니다."""
        self._update_hover_edit_target(point)
        if self.hover_edit_index is None:
            return
        delete_index = self.hover_edit_index
        if delete_index < 0 or delete_index >= len(self.labels):
            return
        self.labels.pop(delete_index)
        self.label_deleted.emit(delete_index)
        self.erased_feedback_active = True
        self.erased_feedback_timer.start(2000)
        self._clear_edit_state()
        self.hover_point = point
        self.update()

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
            if rect.contains(QPointF(point)):
                self.hover_edit_index = index
                self.hover_edit_kind = "move"
                return

    def _update_cursor(self, dragging: bool = False) -> None:
        """현재 모드와 줌 상태에 맞는 마우스 커서를 적용합니다."""
        if self.current_mode == "hand" and self.zoom_factor > 1.0 and dragging:
            self.setCursor(QCursor(Qt.CursorShape.ClosedHandCursor))
        elif self.current_mode == "hand" and self.zoom_factor > 1.0:
            self.setCursor(QCursor(Qt.CursorShape.ArrowCursor))
        else:
            self.setCursor(QCursor(Qt.CursorShape.CrossCursor if self.current_mode in {"draw", "mask"} else Qt.CursorShape.ArrowCursor))
