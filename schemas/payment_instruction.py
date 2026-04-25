import json
from decimal import Decimal
from pydantic import BaseModel


class PaymentInstructionSchema(BaseModel):
    senderVpa: str
    receiverVpa: str
    amount: Decimal
    pinHash: str
    nonce: str
    signedAt: int

    @classmethod
    def from_json_bytes(cls, data: bytes) -> "PaymentInstructionSchema":
        d = json.loads(data.decode(), parse_float=Decimal)
        return cls(**d)
