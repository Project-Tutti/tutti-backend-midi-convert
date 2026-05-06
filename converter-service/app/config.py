# ══════════════════════════════════════════════════════════════
# Converter Service — Configuration
# ══════════════════════════════════════════════════════════════

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """환경 변수 기반 설정."""

    # MuseScore CLI 경로
    musescore_path: str = "musescore4"

    # subprocess 타임아웃 (초) — main-server 60초보다 작게
    subprocess_timeout: int = 50

    # MP3 변환용 타임아웃 (초) — 오디오 합성은 PDF/XML보다 오래 걸림
    mp3_subprocess_timeout: int = 90

    # 임시 파일 디렉토리
    temp_dir: str = "/tmp"

    model_config = {"env_prefix": "CONVERTER_"}


settings = Settings()
