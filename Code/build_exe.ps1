# AutoLabeler 실행 파일을 최상위 디렉토리에 생성하는 빌드 스크립트입니다.
python -m PyInstaller `
  --noconfirm `
  --clean `
  --onefile `
  --windowed `
  --name AutoLabeler `
  --distpath .. `
  --workpath .\build `
  --specpath . `
  main.py
