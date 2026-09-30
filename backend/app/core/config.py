from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    app_name: str = "Crowd Flow Intelligence"
    app_version: str = "0.1.0"
    database_url: str = "sqlite+aiosqlite:///./crowd_flow.db"
    cors_origins: list[str] = ["http://localhost:5173"]
    simulation_hz: float = 2.0
    max_agents: int = 20000

settings = Settings()
