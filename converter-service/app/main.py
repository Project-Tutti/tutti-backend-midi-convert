# ══════════════════════════════════════════════════════════════
# Converter Service — FastAPI Application
# ══════════════════════════════════════════════════════════════
#
# MIDI ↔ MusicXML ↔ PDF 변환 API
# main-server에서 ClusterIP를 통해 호출됩니다.
#

import logging

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse

from .converter import (
    ConversionError,
    TimeoutError,
    convert_file,
    get_musescore_version,
    inject_title_into_musicxml,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Tutti Converter Service",
    description="MIDI ↔ MusicXML ↔ PDF 변환 마이크로서비스",
    version="1.0.0",
)


# ── Health Check ──────────────────────────────────────────────


@app.get("/health")
async def health():
    """헬스 체크 엔드포인트. K8s 프로브 및 모니터링에 사용."""
    return {
        "status": "ok",
        "musescore_version": get_musescore_version(),
    }


# ── MIDI → MusicXML ──────────────────────────────────────────


@app.post(
    "/api/v1/convert/midi-to-xml",
    response_class=Response,
    responses={
        200: {"content": {"application/octet-stream": {}}},
        400: {"description": "잘못된 MIDI 파일"},
        500: {"description": "변환 실패"},
        504: {"description": "변환 타임아웃"},
    },
)
async def midi_to_xml(request: Request):
    """
    MIDI 파일을 MusicXML로 변환합니다.

    - **Request**: `Content-Type: application/octet-stream`, Body = MIDI bytes
    - **Response**: `Content-Type: application/octet-stream`, Body = MusicXML bytes
    """
    body = await request.body()

    if not body:
        return JSONResponse(
            status_code=400,
            content={"detail": "요청 본문이 비어있습니다"},
        )

    # MIDI 파일 기본 검증 (MThd 매직 바이트)
    if not body[:4] == b"MThd":
        return JSONResponse(
            status_code=400,
            content={"detail": "유효하지 않은 MIDI 파일입니다"},
        )

    try:
        result = convert_file(body, "mid", "musicxml")

        # X-Score-Title 헤더가 있으면 악보 제목을 주입
        title = request.headers.get("X-Score-Title")
        if title:
            result = inject_title_into_musicxml(result, title)

        return Response(
            content=result,
            media_type="application/octet-stream",
            headers={"Content-Disposition": "attachment; filename=output.musicxml"},
        )
    except TimeoutError as e:
        logger.error("MIDI→XML 타임아웃: %s", e)
        return JSONResponse(status_code=504, content={"detail": str(e)})
    except ConversionError as e:
        logger.error("MIDI→XML 변환 실패: %s", e)
        return JSONResponse(status_code=e.status_code, content={"detail": str(e)})
    except Exception as e:
        logger.exception("MIDI→XML 예기치 않은 오류: %s", e)
        return JSONResponse(
            status_code=500,
            content={"detail": "내부 서버 오류"},
        )


# ── MusicXML → MIDI ──────────────────────────────────────────


@app.post(
    "/api/v1/convert/xml-to-midi",
    response_class=Response,
    responses={
        200: {"content": {"application/octet-stream": {}}},
        400: {"description": "잘못된 MusicXML 파일"},
        500: {"description": "변환 실패"},
    },
)
async def xml_to_midi(request: Request):
    """
    MusicXML 파일을 MIDI로 변환합니다.

    - **Request**: `Content-Type: application/xml`, Body = MusicXML bytes
    - **Response**: `Content-Type: application/octet-stream`, Body = MIDI bytes
    """
    body = await request.body()

    if not body:
        return JSONResponse(
            status_code=400,
            content={"detail": "요청 본문이 비어있습니다"},
        )

    # MusicXML 기본 검증 (XML 선언 또는 루트 태그)
    text_start = body[:100].decode("utf-8", errors="ignore").strip().lower()
    if not (text_start.startswith("<?xml") or text_start.startswith("<score")):
        return JSONResponse(
            status_code=400,
            content={"detail": "유효하지 않은 MusicXML 파일입니다"},
        )

    try:
        result = convert_file(body, "musicxml", "mid")
        return Response(
            content=result,
            media_type="application/octet-stream",
            headers={"Content-Disposition": "attachment; filename=output.mid"},
        )
    except TimeoutError as e:
        logger.error("XML→MIDI 타임아웃: %s", e)
        return JSONResponse(status_code=504, content={"detail": str(e)})
    except ConversionError as e:
        logger.error("XML→MIDI 변환 실패: %s", e)
        return JSONResponse(status_code=e.status_code, content={"detail": str(e)})
    except Exception as e:
        logger.exception("XML→MIDI 예기치 않은 오류: %s", e)
        return JSONResponse(
            status_code=500,
            content={"detail": "내부 서버 오류"},
        )


# ── MIDI → PDF ────────────────────────────────────────────────


@app.post(
    "/api/v1/convert/midi-to-pdf",
    response_class=Response,
    responses={
        200: {"content": {"application/pdf": {}}},
        400: {"description": "잘못된 MIDI 파일"},
        500: {"description": "변환 실패"},
        504: {"description": "변환 타임아웃"},
    },
)
async def midi_to_pdf(request: Request):
    """
    MIDI 파일을 PDF 악보로 변환합니다.

    - **Request**: `Content-Type: application/octet-stream`, Body = MIDI bytes
    - **Response**: `Content-Type: application/pdf`, Body = PDF bytes
    """
    body = await request.body()

    if not body:
        return JSONResponse(
            status_code=400,
            content={"detail": "요청 본문이 비어있습니다"},
        )

    if not body[:4] == b"MThd":
        return JSONResponse(
            status_code=400,
            content={"detail": "유효하지 않은 MIDI 파일입니다"},
        )

    try:
        result = convert_file(body, "mid", "pdf")
        return Response(
            content=result,
            media_type="application/pdf",
            headers={"Content-Disposition": "attachment; filename=output.pdf"},
        )
    except TimeoutError as e:
        logger.error("MIDI→PDF 타임아웃: %s", e)
        return JSONResponse(status_code=504, content={"detail": str(e)})
    except ConversionError as e:
        logger.error("MIDI→PDF 변환 실패: %s", e)
        return JSONResponse(status_code=e.status_code, content={"detail": str(e)})
    except Exception as e:
        logger.exception("MIDI→PDF 예기치 않은 오류: %s", e)
        return JSONResponse(
            status_code=500,
            content={"detail": "내부 서버 오류"},
        )


# ── MusicXML → PDF ────────────────────────────────────────────


@app.post(
    "/api/v1/convert/xml-to-pdf",
    response_class=Response,
    responses={
        200: {"content": {"application/pdf": {}}},
        400: {"description": "잘못된 MusicXML 파일"},
        500: {"description": "변환 실패"},
        504: {"description": "변환 타임아웃"},
    },
)
async def xml_to_pdf(request: Request):
    """
    MusicXML 파일을 PDF 악보로 변환합니다.

    - **Request**: `Content-Type: application/xml`, Body = MusicXML bytes
    - **Response**: `Content-Type: application/pdf`, Body = PDF bytes
    """
    body = await request.body()

    if not body:
        return JSONResponse(
            status_code=400,
            content={"detail": "요청 본문이 비어있습니다"},
        )

    text_start = body[:100].decode("utf-8", errors="ignore").strip().lower()
    if not (text_start.startswith("<?xml") or text_start.startswith("<score")):
        return JSONResponse(
            status_code=400,
            content={"detail": "유효하지 않은 MusicXML 파일입니다"},
        )

    try:
        result = convert_file(body, "musicxml", "pdf")
        return Response(
            content=result,
            media_type="application/pdf",
            headers={"Content-Disposition": "attachment; filename=output.pdf"},
        )
    except TimeoutError as e:
        logger.error("XML→PDF 타임아웃: %s", e)
        return JSONResponse(status_code=504, content={"detail": str(e)})
    except ConversionError as e:
        logger.error("XML→PDF 변환 실패: %s", e)
        return JSONResponse(status_code=e.status_code, content={"detail": str(e)})
    except Exception as e:
        logger.exception("XML→PDF 예기치 않은 오류: %s", e)
        return JSONResponse(
            status_code=500,
            content={"detail": "내부 서버 오류"},
        )
