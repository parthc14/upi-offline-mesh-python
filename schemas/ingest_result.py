from typing import Optional
from pydantic import BaseModel


class IngestResultSchema(BaseModel):
    outcome: str
    packetHash: str
    reason: Optional[str] = None
    transactionId: Optional[int] = None
