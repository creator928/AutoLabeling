# -*- coding: utf-8 -*-
"""YOLO 라벨 파일 로딩과 저장을 담당합니다."""

from __future__ import annotations

from pathlib import Path

from ..constants import CLASS_COLORS
from ..models import LabelBox


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
        labels.append(
            LabelBox(
                class_index=class_index,
                x_center=float(parts[1]),
                y_center=float(parts[2]),
                width=float(parts[3]),
                height=float(parts[4]),
                color_hex=color_hex,
            )
        )
    return labels


def save_labels(image_path: Path, labels: list[LabelBox]) -> None:
    """현재 이미지의 모든 라벨을 YOLO 포맷으로 저장합니다."""
    txt_path = label_path_for_image(image_path)
    # 라벨이 하나도 없으면 파일 자체를 제거해 미작업 상태와 일치시킵니다.
    if not labels:
        if txt_path.exists():
            txt_path.unlink()
        return

    lines = []
    for label in labels:
        lines.append(
            f"{label.class_index} "
            f"{label.x_center:.6f} {label.y_center:.6f} "
            f"{label.width:.6f} {label.height:.6f}"
        )
    txt_path.write_text("\n".join(lines), encoding="utf-8")
