from uuid import UUID

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL


class Settings(BaseSettings):
    POSTGRES_DB: str = "identityops"
    POSTGRES_USER: str = "identityops"
    POSTGRES_PASSWORD: str
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432

    SECRET_KEY: str
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

    ENTRA_ENABLED: bool = False
    AZURE_TENANT_ID: str = Field(default="", repr=False)
    AZURE_CLIENT_ID: str = Field(default="", repr=False)
    AZURE_CLIENT_SECRET: SecretStr = Field(default=SecretStr(""), repr=False, exclude=True)
    ENTRA_GRAPH_BASE_URL: str = "https://graph.microsoft.com/v1.0"
    ENTRA_HTTP_TIMEOUT_SECONDS: float = Field(default=10, gt=0, le=30)

    @property
    def entra_tenant(self) -> str | None:
        if not self.ENTRA_ENABLED:
            return None
        try:
            return str(UUID(self.AZURE_TENANT_ID))
        except ValueError:
            return None

    @property
    def database_url(self) -> URL:
        return URL.create(
            "postgresql+psycopg",
            username=self.POSTGRES_USER,
            password=self.POSTGRES_PASSWORD,
            host=self.POSTGRES_HOST,
            port=self.POSTGRES_PORT,
            database=self.POSTGRES_DB,
        )

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
    )


settings = Settings()
