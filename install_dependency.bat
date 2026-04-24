@echo off
setlocal EnableExtensions EnableDelayedExpansion
chcp 65001 > nul

REM AutoLabeler 의존성을 한 번에 설치하는 배치 파일입니다.
REM 기본 동작은 CPU 환경 기준 설치이며, 첫 번째 인자로 gpu를 주면 CUDA용 PyTorch를 설치합니다.

set "SCRIPT_DIR=%~dp0"
set "CODE_DIR=%SCRIPT_DIR%Code"
set "REQUIREMENTS_FILE=%CODE_DIR%\requirements.txt"
set "MODE=%~1"

if /I "%MODE%"=="" set "MODE=cpu"
if /I not "%MODE%"=="cpu" if /I not "%MODE%"=="gpu" (
    echo [오류] 설치 모드는 cpu 또는 gpu만 사용할 수 있습니다.
    echo [예시] install_dependency.bat
    echo [예시] install_dependency.bat gpu
    exit /b 1
)

if not exist "%REQUIREMENTS_FILE%" (
    echo [오류] requirements.txt를 찾지 못했습니다.
    echo [경로] %REQUIREMENTS_FILE%
    exit /b 1
)

call :resolve_python
if errorlevel 1 exit /b 1

echo ==================================================
echo AutoLabeler 의존성 설치를 시작합니다.
echo Python 명령: %PYTHON_CMD%
echo 설치 모드: %MODE%
echo ==================================================

call :run_python_cmd -m pip install --upgrade pip setuptools wheel
if errorlevel 1 goto :install_failed

call :run_python_cmd -m pip install -r "%REQUIREMENTS_FILE%"
if errorlevel 1 goto :install_failed

if /I "%MODE%"=="gpu" (
    REM CUDA 12.8 인덱스를 사용해 GPU 학습용 PyTorch를 설치합니다.
    call :run_python_cmd -m pip install --upgrade --index-url https://download.pytorch.org/whl/cu128 torch torchvision torchaudio
    if errorlevel 1 goto :install_failed
) else (
    REM CPU 전용 기본 설치 경로입니다.
    call :run_python_cmd -m pip install --upgrade torch torchvision torchaudio
    if errorlevel 1 goto :install_failed
)

echo.
echo ==================================================
echo 설치가 완료되었습니다.
echo 실행 방법: cd /d "%CODE_DIR%" ^&^& %PYTHON_CMD% main.py
echo ==================================================
exit /b 0

:resolve_python
REM 가능한 한 문서와 코드에서 기대하는 Python 3.10을 우선 선택합니다.
py -3.10 --version > nul 2>&1
if not errorlevel 1 (
    set "PYTHON_CMD=py -3.10"
    exit /b 0
)

py --version > nul 2>&1
if not errorlevel 1 (
    set "PYTHON_CMD=py"
    exit /b 0
)

python --version > nul 2>&1
if not errorlevel 1 (
    set "PYTHON_CMD=python"
    exit /b 0
)

echo [오류] Python 실행 파일을 찾지 못했습니다.
echo Python 3.10 이상을 먼저 설치해 주세요.
exit /b 1

:run_python_cmd
REM 미리 선택한 Python 명령으로 pip 또는 실행 명령을 호출합니다.
if /I "%PYTHON_CMD%"=="py -3.10" (
    py -3.10 %*
) else (
    if /I "%PYTHON_CMD%"=="py" (
        py %*
    ) else (
        python %*
    )
)
exit /b %errorlevel%

:install_failed
echo.
echo [오류] 의존성 설치 중 문제가 발생했습니다.
echo 설치 로그를 확인하고, GPU 모드였다면 CUDA 지원 PyTorch 인덱스 접근 가능 여부도 확인해 주세요.
exit /b 1
