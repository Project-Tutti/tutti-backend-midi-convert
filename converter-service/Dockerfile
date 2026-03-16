# ══════════════════════════════════════════════════════════════
# Tutti Converter Service — Dockerfile
# ══════════════════════════════════════════════════════════════
#
# MuseScore 4 headless 모드 + FastAPI
# QT_QPA_PLATFORM=offscreen으로 X11 없이 실행
#

FROM python:3.11-slim-bookworm

# ── 시스템 의존성 설치 ──
# MuseScore 4 실행에 필요한 Qt/오디오 라이브러리 + PPA 추가 도구
RUN apt-get update && apt-get install -y --no-install-recommends \
    software-properties-common \
    gpg \
    gpg-agent \
    wget \
    && wget -qO- https://musescore.org/sites/musescore.org/files/2024-12/musescore.gpg | gpg --dearmor -o /usr/share/keyrings/musescore-archive-keyring.gpg \
    && echo "deb [signed-by=/usr/share/keyrings/musescore-archive-keyring.gpg] https://musescore.org/debian stable main" \
    > /etc/apt/sources.list.d/musescore.list \
    && apt-get update && apt-get install -y --no-install-recommends \
    musescore4 \
    # Qt offscreen 플랫폼 플러그인
    libqt5gui5 \
    libqt5widgets5 \
    libqt5network5 \
    libqt5xml5 \
    libqt5svg5 \
    # 오디오 (MuseScore가 필요로 함)
    libasound2 \
    libpulse0 \
    # X11 가상 프레임버퍼 (fallback)
    xvfb \
    # PDF 변환을 위한 폰트 패키지
    fonts-noto \
    fontconfig \
    && fc-cache -fv \
    && apt-get purge -y software-properties-common gpg gpg-agent wget \
    && apt-get autoremove -y \
    && rm -rf /var/lib/apt/lists/*

# ── 환경 변수 ──
# X11 없이 MuseScore 실행하기 위한 offscreen 플랫폼
ENV QT_QPA_PLATFORM=offscreen
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# ── Python 의존성 설치 (캐싱 레이어) ──
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ── 애플리케이션 코드 복사 ──
COPY app/ app/

# ── 보안: non-root 사용자 ──
RUN groupadd -r converter && useradd -r -g converter converter \
    && chown -R converter:converter /app
USER converter

EXPOSE 8000

# ── 헬스체크 ──
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

# ── 실행 ──
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
