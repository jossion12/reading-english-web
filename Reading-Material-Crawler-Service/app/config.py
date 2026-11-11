"""应用配置：环境变量 + .env。"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    """Reading-Material-Crawler-Service 运行配置。"""

    model_config = SettingsConfigDict(
        env_file=(BASE_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Supabase ---------------------------------------------------------
    supabase_url: str = "http://127.0.0.1:54321"
    supabase_service_role_key: str = ""

    # --- SearXNG ----------------------------------------------------------
    searxng_base_url: str = "http://127.0.0.1:8080"
    searxng_timeout: float = 20.0
    searxng_categories: str = "news"
    searxng_language: str = "zh-CN"
    searxng_min_interval: float = 2.0
    # SearXNG 阶段的总时间预算（秒）。上游引擎全挂时每条 Query 都要等满
    # searxng_timeout，3 条 Query 会把管理员干等好几分钟；预算用完就提前
    # 切到 RSS 兜底通道，不影响拿候选。
    searxng_total_budget: float = 45.0

    # --- RSS 直采（检索兜底通道，见 app/clients/rss.py）-------------------
    rss_timeout: float = 20.0
    rss_min_interval: float = 1.0
    rss_user_agent: str = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    )

    # --- Crawl4AI ---------------------------------------------------------
    crawler_mode: str = "auto"  # auto | library | http
    crawler_base_url: str = "http://127.0.0.1:11235"
    crawler_timeout: float = 120.0
    crawler_min_content_length: int = 200

    # --- LLM --------------------------------------------------------------
    llm_provider: str = "ollama"
    llm_base_url: str = "http://127.0.0.1:11434"
    llm_model: str = "qwen3.5:9b"
    llm_api_key: str = ""
    llm_timeout: float = 300.0
    llm_temperature: float = 0.3
    llm_think: bool = False

    # --- 服务自身 ----------------------------------------------------------
    service_host: str = "127.0.0.1"
    service_port: int = 8020
    log_dir: str = "logs"
    config_dir: str = "config"
    fingerprint_mode: str = "summary"  # summary | summary_level

    @property
    def base_dir(self) -> Path:
        return BASE_DIR

    @property
    def config_path(self) -> Path:
        return self.base_dir / self.config_dir

    @property
    def prompts_path(self) -> Path:
        return self.config_path / "prompts.yaml"

    @property
    def search_path(self) -> Path:
        return self.config_path / "search.yaml"

    @property
    def log_path(self) -> Path:
        return self.base_dir / self.log_dir


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
