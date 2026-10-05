from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "Crowd Flow Intelligence"
    app_version: str = "0.1.0"
    database_url: str = "sqlite+aiosqlite:///./crowd_flow.db"
    cors_origins: list[str] = ["http://localhost:5173"]
    simulation_hz: float = 2.0
    max_agents: int = 20000

    geo_user_agent: str = "CrowdFlowIntelligence/0.1 (operator@example.invalid)"
    geo_timeout_sec: float = 10.0
    geo_search_url: str = "https://nominatim.openstreetmap.org/search"
    geo_overpass_url: str = "https://overpass-api.de/api/interpreter"
    geo_max_radius_m: int = 5000
    geo_min_request_interval_sec: float = 1.0

    # Only operator-configured/authorized camera metadata is accepted here.
    # The application never discovers or scans arbitrary camera endpoints.
    cctv_sources_json: str = "[]"
    cctv_timeout_sec: float = 5.0

settings = Settings()