# ══════════════════════════════════════════════════════════════
# Converter Service — MuseScore CLI Wrapper
# ══════════════════════════════════════════════════════════════
#
# MuseScore 4를 headless 모드로 실행하여 MIDI ↔ MusicXML ↔ PDF 변환을 수행합니다.
# MuseScore 4는 QT_QPA_PLATFORM=offscreen이 불안정하여 xvfb-run을 사용합니다.
# 동시 요청 처리를 위해 UUID 기반 파일명을 사용합니다.
#

import logging
import os
import re
import subprocess
import uuid
from pathlib import Path
from xml.sax.saxutils import escape as xml_escape

from .config import settings

logger = logging.getLogger(__name__)


class ConversionError(Exception):
    """변환 실패 시 발생하는 예외."""

    def __init__(self, message: str, status_code: int = 500):
        super().__init__(message)
        self.status_code = status_code


class TimeoutError(ConversionError):
    """변환 타임아웃 시 발생하는 예외."""

    def __init__(self, message: str = "변환 시간이 초과되었습니다"):
        super().__init__(message, status_code=504)


def convert_file(
    input_bytes: bytes,
    input_ext: str,
    output_ext: str,
) -> bytes:
    """
    MuseScore CLI를 사용하여 파일을 변환합니다.

    Args:
        input_bytes: 입력 파일 바이트
        input_ext: 입력 파일 확장자 (예: "mid", "musicxml")
        output_ext: 출력 파일 확장자 (예: "musicxml", "mid")

    Returns:
        변환된 파일의 바이트

    Raises:
        ConversionError: 변환 실패 시
        TimeoutError: 타임아웃 시
    """
    file_id = uuid.uuid4().hex
    input_path = Path(settings.temp_dir) / f"{file_id}.{input_ext}"
    output_path = Path(settings.temp_dir) / f"{file_id}.{output_ext}"

    try:
        # 1. 입력 파일 저장
        input_path.write_bytes(input_bytes)
        logger.info("입력 파일 저장: %s (%d bytes)", input_path, len(input_bytes))

        # 2. MuseScore CLI 실행 (xvfb-run으로 가상 디스플레이 제공)
        cmd = [
            "xvfb-run",
            "-a",
            settings.musescore_path,
            "-o",
            str(output_path),
            str(input_path),
        ]
        logger.info("MuseScore 실행: %s", " ".join(cmd))

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=settings.subprocess_timeout,
        )

        # 3. 결과 확인
        if result.returncode != 0:
            stderr = result.stderr.strip()
            logger.error(
                "MuseScore 변환 실패 (exit=%d): %s",
                result.returncode,
                stderr,
            )
            raise ConversionError(
                f"변환 실패: MuseScore exit code {result.returncode}",
                status_code=500,
            )

        if not output_path.exists():
            logger.error("출력 파일이 생성되지 않았습니다: %s", output_path)
            raise ConversionError("변환 실패: 출력 파일이 생성되지 않았습니다")

        # 4. 결과 파일 읽기
        output_bytes = output_path.read_bytes()
        logger.info(
            "변환 완료: %s → %s (%d bytes)",
            input_ext,
            output_ext,
            len(output_bytes),
        )
        return output_bytes

    except subprocess.TimeoutExpired:
        logger.error("MuseScore 타임아웃 (%ds 초과)", settings.subprocess_timeout)
        raise TimeoutError(f"변환 시간 초과 ({settings.subprocess_timeout}초)")

    finally:
        # 5. 임시 파일 정리
        for path in (input_path, output_path):
            try:
                if path.exists():
                    os.remove(path)
                    logger.debug("임시 파일 삭제: %s", path)
            except OSError as e:
                logger.warning("임시 파일 삭제 실패: %s (%s)", path, e)


def inject_title_into_musicxml(xml_bytes: bytes, title: str) -> bytes:
    """
    변환된 MusicXML에 악보 제목을 주입합니다.

    MuseScore는 MIDI 파일을 변환할 때 기본 제목을 "Untitled Score"로 설정합니다.
    이 함수는 MusicXML의 제목 관련 태그를 실제 프로젝트 이름으로 교체합니다.

    교체 대상:
    - <movement-title>: MusicXML 표준 악보 제목
    - <work-title>: 작품 제목
    - <credit-words>: 악보에 시각적으로 표시되는 제목 텍스트

    Args:
        xml_bytes: MusicXML 파일 바이트
        title: 주입할 악보 제목

    Returns:
        제목이 주입된 MusicXML 바이트
    """
    xml_str = xml_bytes.decode("utf-8")
    safe_title = xml_escape(title, {'"': "&quot;"})

    # 1. 기존 movement-title 값을 추출 (credit-words 교체에 사용)
    old_title_match = re.search(
        r"<movement-title>(.*?)</movement-title>", xml_str
    )
    old_title = old_title_match.group(1).strip() if old_title_match else None

    # 2. <movement-title> 교체 — MusicXML 표준 악보 제목
    xml_str = re.sub(
        r"(<movement-title>)(.*?)(</movement-title>)",
        rf"\g<1>{safe_title}\g<3>",
        xml_str,
    )

    # 3. <work-title> 교체 — 작품 제목
    xml_str = re.sub(
        r"(<work-title>)(.*?)(</work-title>)",
        rf"\g<1>{safe_title}\g<3>",
        xml_str,
    )

    # 4. <credit-words> 교체 — 악보 위에 시각적으로 표시되는 제목
    #    기존 movement-title과 동일한 텍스트를 가진 credit-words만 교체
    if old_title:
        escaped_old = re.escape(old_title)
        xml_str = re.sub(
            rf"(<credit-words[^>]*>)\s*{escaped_old}\s*(</credit-words>)",
            rf"\g<1>{safe_title}\g<2>",
            xml_str,
        )

    logger.info("MusicXML 제목 주입 완료: '%s'", title)
    return xml_str.encode("utf-8")


def get_musescore_version() -> str:
    """MuseScore 버전 문자열을 반환합니다."""
    try:
        result = subprocess.run(
            ["xvfb-run", "-a", settings.musescore_path, "--version"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        version = result.stdout.strip() or result.stderr.strip()
        return version if version else "unknown"
    except Exception as e:
        logger.warning("MuseScore 버전 확인 실패: %s", e)
        return "unavailable"

