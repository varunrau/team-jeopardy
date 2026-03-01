from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    notion_api_key: str = ""
    notion_database_id: str = ""
    host: str = "0.0.0.0"
    port: int = 8000
    max_teams: int = 4

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )


settings = Settings()
