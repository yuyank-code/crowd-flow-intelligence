from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "Crowd Flow Intelligence"
    app_version: str = "0.1.0"
    database_url: str = "sqlite+aiosqlite:///./crowd_flow.db"
    cors_origins: list[str] = ["http://localhost:5173"]
    # Security. Empty OPERATOR_API_KEY disables auth (local development only).
    operator_api_key: str = ""
    trust_proxy: bool = False               # honour X-Forwarded-For (only behind your own reverse proxy)
    rate_limit_window_sec: float = 60.0
    rate_limit_operator: int = 60           # state-changing requests per window per client (0 = off)
    rate_limit_geo: int = 20                # geocoding / map-context requests per window per client
    rate_limit_parse: int = 30              # scenario text parsing per window per client
    ws_max_connections: int = 200
    ws_max_per_ip: int = 10

    simulation_hz: float = 2.0
    max_agents: int = 20000
    snapshot_interval_sec: float = 5.0      # persist a history row at most this often (wall clock)
    history_retention_rows: int = 5000      # older rows are pruned

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
