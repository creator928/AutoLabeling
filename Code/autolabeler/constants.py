# -*- coding: utf-8 -*-
"""앱 기본 상수와 기본 설정값을 정의합니다."""

from __future__ import annotations

from .models import ModelOption

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}

# 클래스 인덱스별 기본 표시 색상입니다.
CLASS_COLORS = [
    "#00FF00",
    "#FF0000",
    "#0000FF",
    "#00FFFF",
    "#FF00FF",
    "#FFFF00",
    "#FFFFFF",
    "#000000",
]

DEFAULT_SHORTCUTS = {
    "draw_box": "W",
    "mask_area": "X",
    "edit_box": "E",
    "cancel_mode": "Q",
    "prev_image": "A",
    "next_image": "D",
    "reset_view": "S",
    "delete_last_box": "R",
    "delete_current_pair": "Delete",
    "toggle_theme": "T",
    "open_settings": "Ctrl+,",
}

DEFAULT_CLASS_SHORTCUTS = {
    "0": "`",
    "1": "1",
    "2": "2",
    "3": "3",
    "4": "4",
    "5": "5",
    "6": "6",
    "7": "7",
    "8": "8",
    "9": "9",
}

DEFAULT_CONFIG = {
    "theme_mode": "light",
    "rectangle_input_mode": "drag",
    "selected_model": "yolo11n.pt",
    "shortcuts": DEFAULT_SHORTCUTS,
    "class_shortcuts": DEFAULT_CLASS_SHORTCUTS,
    "runtime_options": {
        "use_gpu": "true",
        "dataset_size": "100",
        "epochs": "50",
        "image_size": "640",
        "batch_size": "8",
        "project_name": "AutoLabelerTrain",
        "auto_label_conf": "0.01",
    },
}

# 2026-04-09 기준 공식 문서에서는 YOLO26이 최신 계열로 안내되지만,
# 현재 자동 다운로드 검증이 쉬운 공식 가중치 자산은 YOLO11 계열 URL을 우선 사용합니다.
MODEL_OPTIONS = [
    ModelOption(
        name="YOLO11 Nano",
        weight_name="yolo11n.pt",
        description="공식 배포 자산으로 바로 다운로드 가능한 경량 기본 모델입니다.",
        download_url="https://github.com/ultralytics/assets/releases/download/v8.3.0/yolo11n.pt",
    ),
    ModelOption(
        name="YOLO11 Small",
        weight_name="yolo11s.pt",
        description="조금 더 무겁지만 정확도가 높을 수 있는 대안 모델입니다.",
        download_url="https://github.com/ultralytics/assets/releases/download/v8.3.0/yolo11s.pt",
    ),
    ModelOption(
        name="YOLO11 Large",
        weight_name="yolo11l.pt",
        description="정확도 우선 작업에 사용할 수 있는 대형 모델입니다.",
        download_url="https://github.com/ultralytics/assets/releases/download/v8.3.0/yolo11l.pt",
    ),
]
