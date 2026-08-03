# -*- coding: utf-8 -*-
"""YOLO 라벨 파일 로딩과 저장을 담당합니다."""

from __future__ import annotations

from pathlib import Path

from ..constants import CLASS_COLORS
from ..models import LabelBox


def _clamp_unit(value: float) -> float:
    """YOLO 정규화 좌표가 0~1 범위를 벗어나지 않도록 보정합니다."""
    return min(max(value, 0.0), 1.0)


def _clamp_box(label: LabelBox) -> LabelBox | None:
    """박스 좌표를 이미지 안쪽으로 보정하고 유효하지 않은 박스는 제외합니다."""
    left = _clamp_unit(label.x_center - label.width / 2.0)
    top = _clamp_unit(label.y_center - label.height / 2.0)
    right = _clamp_unit(label.x_center + label.width / 2.0)
    bottom = _clamp_unit(label.y_center + label.height / 2.0)
    width = max(0.0, right - left)
    height = max(0.0, bottom - top)
    if width <= 0.0 or height <= 0.0:
        return None
    label.x_center = _clamp_unit(left + width / 2.0)
    label.y_center = _clamp_unit(top + height / 2.0)
    label.width = width
    label.height = height
    return label


def label_path_for_image(image_path: Path) -> Path:
    """이미지와 같은 이름의 YOLO 라벨 경로를 계산합니다."""
    return image_path.with_suffix(".txt")


def load_labels(image_path: Path) -> list[LabelBox]:
    """이미지에 대응하는 YOLO 라벨 파일을 읽습니다."""
    labels: list[LabelBox] = []
    txt_path = label_path_for_image(image_path)
    if not txt_path.exists():
        return labels

    for line in txt_path.read_text(encoding="utf-8").splitlines():
        parts = line.strip().split()
        if len(parts) != 5:
            continue
        class_index = int(parts[0])
        color_hex = CLASS_COLORS[class_index % len(CLASS_COLORS)]
        label = LabelBox(
                class_index=class_index,
                x_center=float(parts[1]),
                y_center=float(parts[2]),
                width=float(parts[3]),
                height=float(parts[4]),
                color_hex=color_hex,
            )
        label = _clamp_box(label)
        if label is not None:
            labels.append(label)
    return labels


def save_labels(image_path: Path, labels: list[LabelBox]) -> None:
    """현재 이미지의 모든 라벨을 YOLO 포맷으로 저장합니다."""
    txt_path = label_path_for_image(image_path)
    # 라벨이 하나도 없어도 검토 완료/네거티브 샘플 상태를 보존하기 위해 빈 txt를 남깁니다.
    if not labels:
        txt_path.write_text("", encoding="utf-8")
        return

    lines = []
    for label in labels:
        label = _clamp_box(label)
        if label is None:
            continue
        lines.append(
            f"{label.class_index} "
            f"{label.x_center:.6f} {label.y_center:.6f} "
            f"{label.width:.6f} {label.height:.6f}"
        )
    if not lines:
        # 좌표 보정 후 유효 박스가 없어져도 라벨 파일은 빈 상태로 유지합니다.
        txt_path.write_text("", encoding="utf-8")
        return
    txt_path.write_text("\n".join(lines), encoding="utf-8")
