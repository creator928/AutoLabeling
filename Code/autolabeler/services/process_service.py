# -*- coding: utf-8 -*-
"""외부 Python 프로세스를 안정적으로 실행하기 위한 공통 유틸리티입니다."""

from __future__ import annotations

import contextlib
import ctypes
import os
import shutil
import sys
from collections.abc import Iterator
from pathlib import Path


def _normalized_path_text(path: Path) -> str:
    """경로 비교가 흔들리지 않도록 대소문자와 구분자를 정규화합니다."""
    try:
        return str(path.resolve()).casefold()
    except Exception:
        return str(path).casefold()


def _should_remove_from_path(path_text: str) -> bool:
    """외부 Python이 현재 exe나 빌드 Python의 DLL을 물지 않도록 위험 경로를 걸러냅니다."""
    if not path_text:
        return True

    normalized = _normalized_path_text(Path(path_text))
    blocked_sources = [
        getattr(sys, "_MEIPASS", ""),
        str(Path(sys.executable).resolve().parent),
        sys.prefix,
        sys.base_prefix,
    ]
    blocked_paths = {_normalized_path_text(Path(source)) for source in blocked_sources if source}

    if normalized in blocked_paths:
        return True
    return "pyinstaller" in normalized or normalized.endswith(r"\python310") or normalized.endswith(r"\python310\scripts")


def build_clean_python_env(base_env: dict[str, str] | None = None) -> dict[str, str]:
    """외부 Python이 현재 exe의 Python 경로를 잘못 물려받지 않도록 환경 변수를 정리합니다."""
    process_env = dict(base_env or os.environ)
    process_env.pop("PYTHONHOME", None)
    process_env.pop("PYTHONPATH", None)
    process_env["PYTHONIOENCODING"] = "utf-8"
    process_env["PYTHONUTF8"] = "1"
    existing_path_items = [
        item for item in process_env.get("PATH", "").split(os.pathsep) if not _should_remove_from_path(item)
    ]

    conda_env_dir = process_env.get("AUTOLABELER_CONDA_ENV_DIR", "").strip()
    if conda_env_dir:
        env_path = Path(conda_env_dir)
        # conda activate 없이도 외부 Python이 자신의 DLL과 패키지를 먼저 찾도록 합니다.
        conda_paths = [
            env_path,
            env_path / "Library" / "bin",
            env_path / "Scripts",
        ]
        process_env["PATH"] = os.pathsep.join(
            [str(path) for path in conda_paths if path.exists()] + existing_path_items
        )
    else:
        process_env["PATH"] = os.pathsep.join(existing_path_items)
    return process_env


def external_python_cwd(command: list[str]) -> str | None:
    """외부 Python 실행 시 작업 폴더를 Python 실행 파일 위치로 고정합니다."""
    if not command:
        return None
    executable = shutil.which(command[0]) or command[0]
    executable_path = Path(executable)
    if executable_path.exists():
        return str(executable_path.resolve().parent)
    return None


@contextlib.contextmanager
def clean_windows_dll_search_path() -> Iterator[None]:
    """PyInstaller의 DLL 검색 경로가 외부 Python에 상속되지 않도록 잠시 초기화합니다."""
    if os.name != "nt":
        yield
        return

    kernel32 = ctypes.windll.kernel32
    restore_path = str(getattr(sys, "_MEIPASS", "")) if getattr(sys, "frozen", False) else ""
    kernel32.SetDllDirectoryW(None)
    try:
        yield
    finally:
        if restore_path:
            kernel32.SetDllDirectoryW(restore_path)


def hidden_subprocess_kwargs() -> dict[str, object]:
    """Windows GUI 앱에서 자식 프로세스 콘솔 창이 뜨지 않도록 옵션을 반환합니다."""
    if os.name != "nt":
        return {}
    import subprocess

    startup_info = subprocess_startup_info()
    return {
        "startupinfo": startup_info,
        "creationflags": subprocess.CREATE_NO_WINDOW,
    }


def subprocess_startup_info():
    """subprocess.STARTUPINFO 객체를 지연 생성합니다."""
    import subprocess

    startup_info = subprocess.STARTUPINFO()
    startup_info.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startup_info.wShowWindow = 0
    return startup_info
