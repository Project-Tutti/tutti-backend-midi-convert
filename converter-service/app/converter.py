# ══════════════════════════════════════════════════════════════
# Converter Service — MuseScore CLI Wrapper
# ══════════════════════════════════════════════════════════════
#
# MuseScore 4를 headless 모드로 실행하여 MIDI ↔ MusicXML ↔ PDF 변환을 수행합니다.
# MuseScore 4는 QT_QPA_PLATFORM=offscreen이 불안정하여 xvfb-run을 사용합니다.
# 동시 요청 처리를 위해 UUID 기반 파일명을 사용합니다.
#
# MP3 변환은 MuseScore 내장 오디오 내보내기를 사용하되, headless 무음 버그를
# 우회하기 위해 Docker 컨테이너 내부에 PulseAudio Dummy Sink를 구성하여 실행합니다.
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


# ── MP3 변환을 위한 PulseAudio 상태 관리 ─────────────────────

# MP3 출력의 최소 유효 크기 (바이트)
# MP3 프레임 헤더 + 최소 오디오 데이터를 포함해야 함
_MP3_MIN_VALID_SIZE = 1000


def _ensure_pulseaudio():
    """
    PulseAudio 데몬이 실행 중인지 확인하고, 죽어있으면 재시작합니다.

    MuseScore의 MP3 내보내기는 PulseAudio가 없으면 무음 파일을 생성합니다.
    컨테이너 수명 동안 PulseAudio가 크래시할 수 있으므로 매 변환 전 확인합니다.
    """
    check = subprocess.run(
        ["pulseaudio", "--check"],
        capture_output=True,
    )
    if check.returncode == 0:
        return  # 정상 실행 중

    logger.warning("PulseAudio가 실행 중이 아닙니다. 재시작 시도...")

    # 데몬 재시작
    start = subprocess.run(
        ["pulseaudio", "-D", "--exit-idle-time=-1"],
        capture_output=True,
        text=True,
    )
    if start.returncode != 0:
        logger.error("PulseAudio 재시작 실패: %s", start.stderr.strip())
        raise ConversionError(
            "MP3 변환 불가: PulseAudio 오디오 서비스를 시작할 수 없습니다",
            status_code=500,
        )

    # Null Sink 재설정
    subprocess.run(
        ["pacmd", "load-module", "module-null-sink",
         "sink_name=DummySink",
         'sink_properties=device.description="Virtual_Dummy_Sink"'],
        capture_output=True,
    )
    subprocess.run(
        ["pacmd", "set-default-sink", "DummySink"],
        capture_output=True,
    )
    logger.info("PulseAudio 재시작 및 DummySink 재설정 완료")


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
    is_mp3 = output_ext == "mp3"

    # MP3 변환 시 PulseAudio가 살아있는지 확인 (무음 출력 방지)
    if is_mp3:
        _ensure_pulseaudio()

    file_id = uuid.uuid4().hex
    input_path = Path(settings.temp_dir) / f"{file_id}.{input_ext}"
    output_path = Path(settings.temp_dir) / f"{file_id}.{output_ext}"

    # MP3 변환은 오디오 합성이 필요하므로 더 긴 타임아웃 사용
    timeout = settings.mp3_subprocess_timeout if is_mp3 else settings.subprocess_timeout

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
            timeout=timeout,
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

        # 5. MP3 무음/빈 파일 감지
        if is_mp3 and len(output_bytes) < _MP3_MIN_VALID_SIZE:
            logger.error(
                "MP3 출력이 비정상적으로 작습니다 (%d bytes) — 무음 파일 가능성",
                len(output_bytes),
            )
            raise ConversionError(
                "MP3 변환 실패: 출력 파일이 비정상적으로 작습니다 "
                "(PulseAudio 오디오 장치 문제일 수 있습니다)",
                status_code=500,
            )

        return output_bytes

    except subprocess.TimeoutExpired:
        logger.error("MuseScore 타임아웃 (%ds 초과)", timeout)
        raise TimeoutError(f"변환 시간 초과 ({timeout}초)")

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

    MuseScore 4는 MIDI→MusicXML 변환 시 제목 관련 태그를 생성하지 않습니다.
    이 함수는 누락된 태그를 삽입하고, 존재하는 태그는 교체합니다.

    OSMD 제목 파싱 우선순위:
    1. <work><work-title> → Title
    2. <movement-title> → Title (work-title 없을 때) 또는 Subtitle
    3. <credit-words> → 보충 (위 태그가 없을 때만)

    Args:
        xml_bytes: MusicXML 파일 바이트
        title: 주입할 악보 제목

    Returns:
        제목이 주입된 MusicXML 바이트
    """
    xml_str = xml_bytes.decode("utf-8")
    safe_title = xml_escape(title, {'"': "&quot;"})

    has_work_title = bool(re.search(r"<work-title>", xml_str))
    has_movement_title = bool(re.search(r"<movement-title>", xml_str))
    has_credit_words = bool(re.search(r"<credit-words", xml_str))

    logger.info(
        "XML 제목 태그 현황: work-title=%s, movement-title=%s, credit-words=%s",
        has_work_title, has_movement_title, has_credit_words,
    )

    # ── 1. 기존 태그가 있으면 교체 ──

    if has_movement_title:
        old_title_match = re.search(
            r"<movement-title>(.*?)</movement-title>", xml_str, re.DOTALL
        )
        old_title = old_title_match.group(1).strip() if old_title_match else None

        xml_str = re.sub(
            r"(<movement-title>)(.*?)(</movement-title>)",
            rf"\g<1>{safe_title}\g<3>",
            xml_str,
            flags=re.DOTALL,
        )

        # credit-words 중 기존 제목과 같은 텍스트만 교체
        if old_title and has_credit_words:
            escaped_old = re.escape(old_title)
            xml_str = re.sub(
                rf"(<credit-words[^>]*>)\s*{escaped_old}\s*(</credit-words>)",
                rf"\g<1>{safe_title}\g<2>",
                xml_str,
                flags=re.DOTALL,
            )

    if has_work_title:
        xml_str = re.sub(
            r"(<work-title>)(.*?)(</work-title>)",
            rf"\g<1>{safe_title}\g<3>",
            xml_str,
            flags=re.DOTALL,
        )

    # ── 2. 태그가 없으면 삽입 ──
    # MuseScore 4.6.5는 MIDI 변환 시 이 태그들을 생성하지 않음

    if not has_work_title or not has_movement_title:
        # <score-partwise ...> 바로 뒤에 삽입할 블록 생성
        insert_block = ""

        if not has_work_title:
            insert_block += f"\n  <work>\n    <work-title>{safe_title}</work-title>\n  </work>"

        if not has_movement_title:
            insert_block += f"\n  <movement-title>{safe_title}</movement-title>"

        if insert_block:
            # <score-partwise ...> 태그 바로 뒤에 삽입
            xml_str = re.sub(
                r"(<score-partwise[^>]*>)",
                rf"\g<1>{insert_block}",
                xml_str,
                count=1,
            )
            logger.info("누락된 제목 태그 삽입 완료: work-title=%s, movement-title=%s",
                         not has_work_title, not has_movement_title)

    # credit 태그가 없으면 삽입 (OSMD가 credit-words도 참조하므로)
    if not has_credit_words:
        # <part-list> 바로 앞에 credit 블록 삽입
        credit_block = (
            f'  <credit page="1">\n'
            f'    <credit-type>title</credit-type>\n'
            f'    <credit-words default-x="600" default-y="1611" '
            f'justify="center" valign="top" font-size="24">'
            f'{safe_title}</credit-words>\n'
            f'  </credit>\n'
        )
        xml_str = xml_str.replace(
            "<part-list>",
            credit_block + "  <part-list>",
            1,
        )
        logger.info("credit-words 태그 삽입 완료")

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

