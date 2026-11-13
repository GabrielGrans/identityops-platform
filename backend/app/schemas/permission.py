from pydantic import BaseModel, ConfigDict, Field


class PermissionCreate(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    code: str = Field(min_length=2, max_length=100)
    resource: str = Field(min_length=2, max_length=100)
    action: str = Field(min_length=2, max_length=50)
    description: str | None = None


class PermissionUpdate(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    code: str = Field(min_length=2, max_length=100)
    resource: str = Field(min_length=2, max_length=100)
    action: str = Field(min_length=2, max_length=50)
    description: str | None = None
    is_active: bool = True


class PermissionResponse(BaseModel):
    id: int
    name: str
    code: str
    resource: str
    action: str
    description: str | None
    is_active: bool

    model_config = ConfigDict(from_attributes=True)
