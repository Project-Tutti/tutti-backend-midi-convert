# ══════════════════════════════════════════════════════════════
# Converter Service — MuseScore CLI Wrapper
# ══════════════════════════════════════════════════════════════
#
# MuseScore 4를 headless 모드로 실행하여 MIDI ↔ MusicXML 변환을 수행합니다.
# 동시 요청 처리를 위해 UUID 기반 파일명을 사용합니다.
#

import logging
import os
import subprocess
import uuid
from pathlib import Path

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

        # 2. MuseScore CLI 실행
        cmd = [
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


def get_musescore_version() -> str:
    """MuseScore 버전 문자열을 반환합니다."""
    try:
        result = subprocess.run(
            [settings.musescore_path, "--version"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        version = result.stdout.strip() or result.stderr.strip()
        return version if version else "unknown"
    except Exception as e:
        logger.warning("MuseScore 버전 확인 실패: %s", e)
        return "unavailable"
