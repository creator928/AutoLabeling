$ErrorActionPreference = 'Stop'

# AutoLabeler 실행 파일을 Code\dist에 만든 뒤 프로젝트 루트로 복사하는 빌드 스크립트입니다.
$distDir = Join-Path $PSScriptRoot 'dist'
$workDir = Join-Path $PSScriptRoot 'build'
$targetExe = Join-Path (Split-Path $PSScriptRoot -Parent) 'AutoLabeler.exe'
$builtExe = Join-Path $distDir 'AutoLabeler.exe'

if (Test-Path -LiteralPath $distDir) {
    Remove-Item -LiteralPath $distDir -Recurse -Force
}

# spec 파일에는 main.py 상대경로를 유지해 다른 PC/폴더에서도 빌드되도록 합니다.
python -m PyInstaller `
  --noconfirm `
  --clean `
  --distpath $distDir `
  --workpath $workDir `
  AutoLabeler.spec

# 기존 EXE를 먼저 삭제하지 않고 직접 덮어써 교체 실패 시 기존 실행 파일을 보존합니다.
$copySucceeded = $false
for ($attempt = 1; $attempt -le 10; $attempt++) {
    try {
        [System.IO.File]::Copy($builtExe, $targetExe, $true)
        $copySucceeded = $true
        break
    }
    catch {
        if ($attempt -eq 10) {
            throw
        }
        Start-Sleep -Milliseconds (200 * $attempt)
    }
}

# 최종 실행 파일만 남기기 위해 중간 dist 산출물은 빌드 후 정리합니다.
if ($copySucceeded -and (Test-Path -LiteralPath $distDir)) {
    Remove-Item -LiteralPath $distDir -Recurse -Force
}
