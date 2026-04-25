import logging
from datetime import datetime, timezone
from decimal import Decimal
from sqlalchemy.orm import Session
from sqlalchemy.orm.exc import StaleDataError

from models.account import Account
from models.transaction import Transaction, TransactionStatus
from schemas.payment_instruction import PaymentInstructionSchema

logger = logging.getLogger(__name__)


class SettlementService:

    def settle(
        self,
        instruction: PaymentInstructionSchema,
        packet_hash: str,
        bridge_node_id: str,
        hop_count: int,
        db: Session,
    ) -> Transaction:
        sender = db.get(Account, instruction.senderVpa)
        if sender is None:
            raise ValueError(f"Unknown sender VPA: {instruction.senderVpa}")

        receiver = db.get(Account, instruction.receiverVpa)
        if receiver is None:
            raise ValueError(f"Unknown receiver VPA: {instruction.receiverVpa}")

        amount = instruction.amount
        if amount <= Decimal("0"):
            raise ValueError("Amount must be positive")

        if sender.balance < amount:
            logger.warning(
                "Insufficient balance: %s has %s, tried to send %s",
                sender.vpa,
                sender.balance,
                amount,
            )
            return self._record_rejected(
                instruction, packet_hash, bridge_node_id, hop_count, db
            )

        sender.balance -= amount
        receiver.balance += amount

        tx = Transaction(
            packet_hash=packet_hash,
            sender_vpa=instruction.senderVpa,
            receiver_vpa=instruction.receiverVpa,
            amount=amount,
            signed_at=datetime.fromtimestamp(
                instruction.signedAt / 1000, tz=timezone.utc
            ),
            settled_at=datetime.now(tz=timezone.utc),
            bridge_node_id=bridge_node_id,
            hop_count=hop_count,
            status=TransactionStatus.SETTLED,
        )
        db.add(tx)
        db.commit()

        logger.info(
            "SETTLED %s from %s to %s (packetHash=%s..., bridge=%s, hops=%d)",
            amount,
            sender.vpa,
            receiver.vpa,
            packet_hash[:12],
            bridge_node_id,
            hop_count,
        )
        return tx

    def _record_rejected(
        self,
        instruction: PaymentInstructionSchema,
        packet_hash: str,
        bridge_node_id: str,
        hop_count: int,
        db: Session,
    ) -> Transaction:
        tx = Transaction(
            packet_hash=packet_hash,
            sender_vpa=instruction.senderVpa,
            receiver_vpa=instruction.receiverVpa,
            amount=instruction.amount,
            signed_at=datetime.fromtimestamp(
                instruction.signedAt / 1000, tz=timezone.utc
            ),
            settled_at=datetime.now(tz=timezone.utc),
            bridge_node_id=bridge_node_id,
            hop_count=hop_count,
            status=TransactionStatus.REJECTED,
        )
        db.add(tx)
        db.commit()
        return tx


settlement_service = SettlementService()
