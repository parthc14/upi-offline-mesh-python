from pydantic import BaseModel, Field


class MeshPacketSchema(BaseModel):
    packetId: str = Field(min_length=1)
    ttl: int = Field(ge=0)
    createdAt: int
    ciphertext: str = Field(min_length=1)
