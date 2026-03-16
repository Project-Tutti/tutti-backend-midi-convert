# ══════════════════════════════════════════════════════════════
# Tutti Converter Service — Dockerfile
# ══════════════════════════════════════════════════════════════
#
# MuseScore 4 headless 모드 + FastAPI
# AppImage를 추출하여 설치, xvfb-run으로 headless 실행
#

FROM python:3.11-slim-bookworm

# ── 시스템 의존성 설치 ──
# MuseScore 4 AppImage 실행에 필요한 라이브러리
RUN apt-get update && apt-get install -y --no-install-recommends \
    wget \
    # xvfb — headless 디스플레이 (MuseScore 4는 offscreen 미지원)
    xvfb \
    # Qt / GUI 라이브러리
    libxcb-xinerama0 \
    libxcb-cursor0 \
    libxcb-icccm4 \
    libxcb-image0 \
    libxcb-keysyms1 \
    libxcb-randr0 \
    libxcb-render-util0 \
    libxcb-shape0 \
    libxkbcommon-x11-0 \
    libegl1 \
    libopengl0 \
    libgl1 \
    libdbus-1-3 \
    libnss3 \
    libxcomposite1 \
    libxdamage1 \
    libxrandr2 \
    libxtst6 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libgbm1 \
    libpango-1.0-0 \
    libcairo2 \
    libasound2 \
    # PDF 변환을 위한 폰트 패키지
    fonts-noto \
    fontconfig \
    && fc-cache -fv \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# ── MuseScore 4 AppImage 설치 ──
# AppImage를 다운로드 → 추출 → 심볼릭 링크 생성
ARG MUSESCORE_VERSION=4.4.4
ARG MUSESCORE_URL=https://github.com/musescore/MuseScore/releases/download/v${MUSESCORE_VERSION}/MuseScore-Studio-${MUSESCORE_VERSION}-x86_64.AppImage

RUN wget -q "${MUSESCORE_URL}" -O /tmp/musescore.AppImage \
    && chmod +x /tmp/musescore.AppImage \
    && cd /opt \
    && /tmp/musescore.AppImage --appimage-extract \
    && rm /tmp/musescore.AppImage \
    && ln -s /opt/squashfs-root/AppRun /usr/local/bin/musescore4

# ── 환경 변수 ──
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# ── Python 의존성 설치 (캐싱 레이어) ──
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ── 애플리케이션 코드 복사 ──
COPY app/ app/

# ── 보안: non-root 사용자 ──
RUN groupadd -r converter && useradd -r -g converter converter \
    && chown -R converter:converter /app \
    && chown -R converter:converter /opt/squashfs-root
USER converter

EXPOSE 8000

# ── 헬스체크 ──
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

# ── 실행 ──
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
