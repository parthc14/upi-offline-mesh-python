from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "sqlite:///./upimesh.db?check_same_thread=False"
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_timeout: int = 2
    idempotency_ttl_seconds: int = 86400
    packet_max_age_seconds: int = 86400
    port: int = 8080

    model_config = SettingsConfigDict(env_file=".env", env_prefix="UPI_MESH_")


settings = Settings()
