"""Backend에서 사용할 비밀값 없는 설정 계약."""

import os

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppSettings(BaseSettings):
    """환경변수로 변경 가능한 모델 설정."""

    model_config = SettingsConfigDict(populate_by_name=True)

    model_name: str = Field(default="gpt-4o", validation_alias="OPENAI_MODEL")

    @field_validator("model_name")
    @classmethod
    def reject_blank_model(cls, value: str) -> str:
        model_name = value.strip()
        if not model_name:
            raise ValueError("OPENAI_MODEL은 비어 있을 수 없습니다.")
        return model_name

    @property
    def openai_api_key_configured(self) -> bool:
        """키 값을 노출하지 않고 비어 있지 않은 설정인지 확인합니다."""
        return bool(os.getenv("OPENAI_API_KEY", "").strip())
