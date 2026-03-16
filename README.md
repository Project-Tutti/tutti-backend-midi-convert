# Tutti Converter Service

MIDI ↔ MusicXML ↔ PDF 변환 마이크로서비스 (FastAPI + MuseScore 4)

## 아키텍처

```
Client → main-server ──→ [converter-service] ← 이 서비스
                          (K8s ClusterIP, 포트 8000)
```

- **main-server**에서 `http://converter-service:8000`으로 호출
- 외부 접근 불필요 (ClusterIP)

## API 엔드포인트

| Method | Path                          | Request                           | Response                                         |
| ------ | ----------------------------- | --------------------------------- | ------------------------------------------------ |
| `POST` | `/api/v1/convert/midi-to-xml` | `application/octet-stream` (MIDI) | `application/octet-stream` (MusicXML)            |
| `POST` | `/api/v1/convert/xml-to-midi` | `application/xml` (MusicXML)      | `application/octet-stream` (MIDI)                |
| `POST` | `/api/v1/convert/midi-to-pdf` | `application/octet-stream` (MIDI) | `application/pdf` (PDF 악보)                     |
| `POST` | `/api/v1/convert/xml-to-pdf`  | `application/xml` (MusicXML)      | `application/pdf` (PDF 악보)                     |
| `GET`  | `/health`                     | —                                 | `{"status": "ok", "musescore_version": "4.x.x"}` |

### 에러 코드

| 코드 | 설명                                                    |
| ---- | ------------------------------------------------------- |
| 400  | 잘못된 입력 파일 (MIDI 매직바이트 없음 / XML 선언 없음) |
| 500  | MuseScore 변환 실패                                     |
| 504  | 변환 타임아웃 (50초 초과)                               |

## 프로젝트 구조

```
converter-service/
├── app/
│   ├── __init__.py
│   ├── main.py          # FastAPI 앱 + 라우터
│   ├── converter.py     # MuseScore CLI 래퍼 (모든 변환 로직)
│   └── config.py        # 설정 (환경변수)
├── Dockerfile
└── requirements.txt
k8s/base/
├── kustomization.yaml
├── namespace.yaml
└── converter-service/
    ├── deployment.yaml
    └── service.yaml
```

## 로컬 개발

```bash
# 가상환경 설정
cd converter-service
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 서버 실행 (MuseScore 4가 로컬에 설치되어 있어야 함)
uvicorn app.main:app --reload --port 8000

# 테스트
curl http://localhost:8000/health
curl -X POST http://localhost:8000/api/v1/convert/midi-to-xml \
  -H "Content-Type: application/octet-stream" \
  --data-binary @sample.mid -o output.musicxml
curl -X POST http://localhost:8000/api/v1/convert/midi-to-pdf \
  -H "Content-Type: application/octet-stream" \
  --data-binary @sample.mid -o output.pdf
```

## 배포

### CI/CD

`main` 브랜치에 push 시 GitHub Actions가 자동으로:

1. Docker 이미지 빌드 → Artifact Registry 푸시
2. Kustomize로 GKE에 배포

### 수동 배포

GitHub Actions > "CI/CD - Converter Service" > "Run workflow"

## 환경 변수

| 변수                           | 기본값       | 설명                    |
| ------------------------------ | ------------ | ----------------------- |
| `QT_QPA_PLATFORM`              | `offscreen`  | MuseScore headless 모드 |
| `CONVERTER_MUSESCORE_PATH`     | `musescore4` | MuseScore CLI 경로      |
| `CONVERTER_SUBPROCESS_TIMEOUT` | `50`         | 변환 타임아웃 (초)      |
| `CONVERTER_TEMP_DIR`           | `/tmp`       | 임시 파일 디렉토리      |

## 인프라 정보

| 항목          | 값                                                                |
| ------------- | ----------------------------------------------------------------- |
| GKE 클러스터  | `tutti-cluster` (us-central1-a)                                   |
| Namespace     | `tutti`                                                           |
| Service 이름  | `converter-service`                                               |
| 내부 URL      | `http://converter-service:8000`                                   |
| Docker 이미지 | `us-central1-docker.pkg.dev/{PROJECT_ID}/tutti/converter-service` |
