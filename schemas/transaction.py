from datetime import datetime
from decimal import Decimal
from pydantic import BaseModel, ConfigDict, Field

from models.transaction import TransactionStatus


class TransactionSchema(BaseModel):
    id: int
    packetHash: str = Field(validation_alias="packet_hash", serialization_alias="packetHash")
    senderVpa: str = Field(validation_alias="sender_vpa", serialization_alias="senderVpa")
    receiverVpa: str = Field(validation_alias="receiver_vpa", serialization_alias="receiverVpa")
    amount: Decimal
    signedAt: datetime = Field(validation_alias="signed_at", serialization_alias="signedAt")
    settledAt: datetime = Field(validation_alias="settled_at", serialization_alias="settledAt")
    bridgeNodeId: str = Field(validation_alias="bridge_node_id", serialization_alias="bridgeNodeId")
    hopCount: int = Field(validation_alias="hop_count", serialization_alias="hopCount")
    status: TransactionStatus

    model_config = ConfigDict(from_attributes=True)
