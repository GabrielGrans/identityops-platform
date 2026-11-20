from uuid import UUID

from pydantic import Field, SecretStr, field_validator
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
    ENTRA_SYNC_INTERVAL_MINUTES: int = Field(default=10, ge=5, le=15)
    ENTRA_WRITE_ENABLED: bool = False
    ENTRA_WRITE_GROUP_IDS: str = ""
    ENTRA_PROTECTED_GROUP_IDS: str = ""
    AZURE_TENANT_ID: str = Field(default="", repr=False)
    AZURE_CLIENT_ID: str = Field(default="", repr=False)
    AZURE_CLIENT_SECRET: SecretStr = Field(default=SecretStr(""), repr=False, exclude=True)
    ENTRA_GRAPH_BASE_URL: str = "https://graph.microsoft.com/v1.0"
    ENTRA_HTTP_TIMEOUT_SECONDS: float = Field(default=10, gt=0, le=30)

    SERVICENOW_ENABLED: bool = False
    SERVICENOW_SIMULATION: bool = True
    SERVICENOW_INSTANCE: str = ""
    SERVICENOW_API_NAMESPACE: str = Field(default="identityops", pattern=r"^[a-zA-Z0-9_]{1,80}$")
    SERVICENOW_READ_USER: str = ""
    SERVICENOW_READ_PASSWORD: SecretStr = Field(default=SecretStr(""), repr=False, exclude=True)
    SERVICENOW_INTAKE_TOKEN: SecretStr = Field(default=SecretStr(""), repr=False, exclude=True)
    SERVICENOW_REQUESTER_ID: int | None = Field(default=None, gt=0)

    @field_validator("SERVICENOW_REQUESTER_ID", mode="before")
    @classmethod
    def empty_servicenow_requester(cls, value):
        return None if value == "" else value

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
