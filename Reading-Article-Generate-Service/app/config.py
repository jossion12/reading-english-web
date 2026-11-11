"""应用配置：全部来自环境变量 + .env，便于内网部署时切换 LLM / Supabase 实例。"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent


def _env_file_name() -> str:
    """选配置文件：APP_ENV=production 读 .env.production，否则读 .env。

    这样开发（.env 指向本机 Ollama + 本地 Docker Supabase）与生产
    （.env.production 指向 DeepSeek + 在线 Supabase）可以并存，切换只改一个环境变量。
    """
    app_env = os.environ.get("APP_ENV", "").strip().lower()
    return ".env.production" if app_env in {"production", "prod"} else ".env"


class Settings(BaseSettings):
    """Reading-Article-Generate-Service 运行配置。"""

    model_config = SettingsConfigDict(
        env_file=(BASE_DIR / _env_file_name()),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Supabase ---------------------------------------------------------
    supabase_url: str = "http://127.0.0.1:54321"
    supabase_service_role_key: str = ""

    # --- LLM --------------------------------------------------------------
    llm_provider: str = "ollama"
    llm_base_url: str = "http://127.0.0.1:11434"
    llm_model: str = "qwen3.5:9b"
    llm_api_key: str = ""
    llm_timeout: float = 300.0
    llm_temperature: float = 0.7
    llm_think: bool = False
    #: 单次响应最多输出多少 token —— 云端模型默认上限偏小，JSON 模式被截断会返回空内容
    llm_max_tokens: int = 4096

    # --- 服务自身 ----------------------------------------------------------
    service_host: str = "127.0.0.1"
    service_port: int = 8010
    log_dir: str = "logs"
    config_dir: str = "config"

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
    def taxonomy_path(self) -> Path:
        return self.config_path / "taxonomy.yaml"

    @property
    def log_path(self) -> Path:
        return self.base_dir / self.log_dir


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
