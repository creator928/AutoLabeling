# AutoLabeler

YOLO 기반 이미지 라벨링, 백그라운드 학습, 학습 결과 기반 오토 라벨링을 하나의 PyQt6 GUI에서 수행하는 Windows용 도구입니다.

## 구성

- `Code/`: 실행 코드와 러너 스크립트
- `Document/`: 프로젝트 개요, 아키텍처, 실행/설치 가이드
- `Data/settings.json`: 앱 기본 설정
- `Work/ExampleDataset/`: 최소 예제 데이터셋
- `install_dependency.bat`: 원터치 의존성 설치 배치 파일

## 권장 환경

- Windows 10/11
- Python 3.10 이상
- GPU 학습 사용 시 CUDA 지원 PyTorch 환경

## 설치

기본 CPU 환경:

```bat
install_dependency.bat
```

GPU 학습 환경:

```bat
install_dependency.bat gpu
```

수동 설치가 필요하면 [Code/requirements.txt](Code/requirements.txt) 와 [Document/05_의존성설치가이드.md](Document/05_%EC%9D%98%EC%A1%B4%EC%84%B1%EC%84%A4%EC%B9%98%EA%B0%80%EC%9D%B4%EB%93%9C.md) 를 참고합니다.

## 실행

```powershell
cd Code
python main.py
```

## 포함 범위

이 저장소에는 소스 코드, 문서, 설치 스크립트, 최소 예제 데이터셋만 포함합니다.

다음 항목은 저장소에서 제외합니다.

- 학습 결과물과 캐시
- `Data/ultralytics/` 런타임 설정/캐시
- `Data/models/` 와 루트의 모델 가중치
- 전체 작업 데이터셋과 백업 데이터
- 빌드 결과 EXE와 `Code/build/`

## 작성자

- GitHub: `creator928`
- Contact: `creator928forgit@gmail.com`
