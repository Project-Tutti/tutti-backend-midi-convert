#!/bin/bash
set -e

# ══════════════════════════════════════════════════════════════
# Tutti Converter Service — Entrypoint
# ══════════════════════════════════════════════════════════════
#
# PulseAudio Dummy Sink를 구성하여 MuseScore 4의
# headless MP3 변환 시 무음 출력 버그를 우회합니다.
#

# ── PulseAudio 데몬 시작 ──
# --exit-idle-time=-1: 클라이언트가 없어도 종료하지 않음
# --log-target=stderr: 로그를 stderr로 출력 (Docker 로그 수집 호환)
echo "🔊 PulseAudio 데몬 시작 중..."
pulseaudio -D --exit-idle-time=-1 --log-target=stderr 2>/dev/null || {
    echo "⚠️  PulseAudio 데몬 시작 실패 — MP3 변환이 무음으로 출력될 수 있습니다"
}

# ── Null Sink (가상 스피커) 모듈 로드 ──
# MuseScore가 이 가상 장치에 오디오를 렌더링합니다
pacmd load-module module-null-sink \
    sink_name=DummySink \
    sink_properties=device.description="Virtual_Dummy_Sink" \
    2>/dev/null || true

pacmd set-default-sink DummySink 2>/dev/null || true

# ── PulseAudio 상태 확인 ──
if pulseaudio --check 2>/dev/null; then
    echo "✅ PulseAudio 정상 가동 (DummySink 활성)"
else
    echo "⚠️  PulseAudio가 실행되지 않았습니다"
fi

# ── FastAPI 서버 실행 ──
echo "🚀 Converter Service 시작..."
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
