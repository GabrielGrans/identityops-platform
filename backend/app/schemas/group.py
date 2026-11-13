from pydantic import BaseModel, ConfigDict, Field


class GroupCreate(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    code: str = Field(min_length=2, max_length=50)
    description: str | None = None


class GroupUpdate(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    code: str = Field(min_length=2, max_length=50)
    description: str | None = None
    is_active: bool = True


class GroupResponse(BaseModel):
    id: int
    name: str
    code: str
    description: str | None
    is_active: bool

    model_config = ConfigDict(from_attributes=True)
