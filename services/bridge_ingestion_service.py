import logging
import time
from dataclasses import dataclass
from typing import Optional
from sqlalchemy.orm import Session
from sqlalchemy.orm.exc import StaleDataError
from cryptography.exceptions import InvalidTag

from schemas.mesh_packet import MeshPacketSchema
from services.idempotency_service import idempotency_service
from services.settlement_service import settlement_service
from crypto.hybrid_crypto_service import hybrid_crypto_service
from config import settings

logger = logging.getLogger(__name__)


@dataclass
class IngestResult:
    outcome: str
    packet_hash: str
    reason: Optional[str]
    transaction_id: Optional[int]

    @classmethod
    def settled(cls, packet_hash: str, tx) -> "IngestResult":
        return cls("SETTLED", packet_hash, None, tx.id)

    @classmethod
    def duplicate(cls, packet_hash: str) -> "IngestResult":
        return cls("DUPLICATE_DROPPED", packet_hash, None, None)

    @classmethod
    def invalid(cls, packet_hash: str, reason: str) -> "IngestResult":
        return cls("INVALID", packet_hash, reason, None)


class BridgeIngestionService:

    def ingest(
        self,
        packet: MeshPacketSchema,
        bridge_node_id: str,
        hop_count: int,
        db: Session,
    ) -> IngestResult:
        try:
            packet_hash = hybrid_crypto_service.hash_ciphertext(packet.ciphertext)

            if not idempotency_service.claim(packet_hash):
                logger.info(
                    "DUPLICATE packet %s... from bridge %s — dropped",
                    packet_hash[:12],
                    bridge_node_id,
                )
                return IngestResult.duplicate(packet_hash)

            try:
                instruction = hybrid_crypto_service.decrypt(packet.ciphertext)
            except (InvalidTag, ValueError) as e:
                logger.warning(
                    "Decryption failed for packet %s...: %s", packet_hash[:12], e
                )
                return IngestResult.invalid(packet_hash, "decryption_failed")

            now_ms = int(time.time() * 1000)
            age_seconds = (now_ms - instruction.signedAt) / 1000
            if age_seconds > settings.packet_max_age_seconds:
                logger.warning(
                    "Packet %s... too old (%ds), rejected", packet_hash[:12], age_seconds
                )
                return IngestResult.invalid(packet_hash, "stale_packet")
            if age_seconds < -300:
                return IngestResult.invalid(packet_hash, "future_dated")

            try:
                tx = settlement_service.settle(
                    instruction, packet_hash, bridge_node_id, hop_count, db
                )
            except StaleDataError:
                logger.warning(
                    "Optimistic lock conflict for packet %s...", packet_hash[:12]
                )
                return IngestResult.invalid(packet_hash, "concurrent_update_conflict")

            return IngestResult.settled(packet_hash, tx)

        except Exception as e:
            logger.error("Ingestion error: %s", e, exc_info=True)
            return IngestResult.invalid("?", f"internal_error: {e}")


bridge_ingestion_service = BridgeIngestionService()
