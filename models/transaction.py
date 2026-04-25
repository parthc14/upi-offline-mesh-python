import enum
from datetime import datetime
from decimal import Decimal
from sqlalchemy import String, Numeric, DateTime, Index, Enum as SQLEnum, Integer
from sqlalchemy.orm import Mapped, mapped_column

from database import Base


class TransactionStatus(str, enum.Enum):
    SETTLED = "SETTLED"
    REJECTED = "REJECTED"


class Transaction(Base):
    __tablename__ = "transactions"
    __table_args__ = (
        Index("idx_packet_hash", "packet_hash", unique=True),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    packet_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    sender_vpa: Mapped[str] = mapped_column(String, nullable=False)
    receiver_vpa: Mapped[str] = mapped_column(String, nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(precision=19, scale=2), nullable=False)
    signed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    settled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    bridge_node_id: Mapped[str] = mapped_column(String, nullable=False)
    hop_count: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[TransactionStatus] = mapped_column(SQLEnum(TransactionStatus), nullable=False)

    def __repr__(self):
        return f"<Transaction id={self.id} hash={self.packet_hash[:12]}... status={self.status}>"
