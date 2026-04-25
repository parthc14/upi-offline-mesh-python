from decimal import Decimal
from pydantic import BaseModel, ConfigDict, Field


class AccountSchema(BaseModel):
    vpa: str
    holderName: str = Field(validation_alias="holder_name", serialization_alias="holderName")
    balance: Decimal

    model_config = ConfigDict(from_attributes=True)
