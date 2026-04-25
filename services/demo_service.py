import hashlib
import uuid
import logging
import time
from decimal import Decimal
from sqlalchemy.orm import Session

from models.account import Account
from schemas.mesh_packet import MeshPacketSchema
from schemas.payment_instruction import PaymentInstructionSchema
from crypto.server_key_holder import server_key_holder
from crypto.hybrid_crypto_service import hybrid_crypto_service

logger = logging.getLogger(__name__)


def seed_accounts(db: Session) -> None:
    if db.query(Account).count() == 0:
        for vpa, name, balance in [
            ("alice@demo", "Alice", Decimal("5000.00")),
            ("bob@demo", "Bob", Decimal("1000.00")),
            ("carol@demo", "Carol", Decimal("2500.00")),
            ("dave@demo", "Dave", Decimal("500.00")),
        ]:
            db.add(Account(vpa=vpa, holder_name=name, balance=balance))
        db.commit()
        logger.info("Seeded 4 demo accounts")


def sha256_hex(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()


def create_packet(
    sender_vpa: str, receiver_vpa: str, amount: Decimal, pin: str, ttl: int = 5
) -> MeshPacketSchema:
    instruction = PaymentInstructionSchema(
        senderVpa=sender_vpa,
        receiverVpa=receiver_vpa,
        amount=amount,
        pinHash=sha256_hex(pin),
        nonce=str(uuid.uuid4()),
        signedAt=int(time.time() * 1000),
    )
    ciphertext = hybrid_crypto_service.encrypt(instruction, server_key_holder.public_key)
    return MeshPacketSchema(
        packetId=str(uuid.uuid4()),
        ttl=ttl,
        createdAt=int(time.time() * 1000),
        ciphertext=ciphertext,
    )
