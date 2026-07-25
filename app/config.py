from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    secret_key: str = "change-me"
    database_url: str = "mysql+pymysql://lab_diary:lab_diary@127.0.0.1:3307/lab_diary"
    app_base_url: str = "http://localhost:8000"
    upload_dir: str = "uploads"
    max_attachments_per_draw: int = 10
    # Soft cap per import job (batch upload)
    max_import_files: int = 40
    # Parallel Smart/classic extracts in the in-process worker
    import_worker_concurrency: int = 2
    # Max wall time per file before soft-fail and continue the batch (seconds)
    import_file_timeout_sec: int = 720
    # auto | rapid | tesseract
    ocr_engine: str = "auto"
    # Smart extract (NVIDIA NIM only)
    nvidia_api_key: str = ""
    smart_provider: str = "nvidia"
    smart_model: str = "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning"

    brevo_api_key: str = ""
    brevo_sender_email: str = "noreply@lab.behejsrdcem.cz"
    brevo_sender_name: str = "Lab deník"

    google_client_id: str = ""
    google_client_secret: str = ""
    apple_client_id: str = ""
    apple_team_id: str = ""
    apple_key_id: str = ""
    apple_private_key: str = ""

    dev_log_email: bool = True
    session_cookie_name: str = "lab_diary_session"
    session_max_age: int = 60 * 60 * 24 * 30


@lru_cache
def get_settings() -> Settings:
    return Settings()
