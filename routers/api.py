import concurrent.futures
import threading
from decimal import Decimal
from typing import Optional, List

from fastapi import APIRouter, Depends, Header
from sqlalchemy.orm import Session
from pydantic import BaseModel

from database import get_db, SessionLocal
from models.account import Account
from models.transaction import Transaction
from schemas.account import AccountSchema
from schemas.transaction import TransactionSchema
from schemas.mesh_packet import MeshPacketSchema
from schemas.ingest_result import IngestResultSchema
from crypto.server_key_holder import server_key_holder
from services.bridge_ingestion_service import bridge_ingestion_service
from services.mesh_simulator_service import mesh_simulator_service
from services.idempotency_service import idempotency_service
from services.demo_service import create_packet

router = APIRouter(prefix="/api")


# --- /api/server-key ---


@router.get("/server-key")
def get_server_public_key():
    return {
        "publicKey": server_key_holder.get_public_key_base64(),
        "algorithm": "RSA-2048 / OAEP-SHA256",
        "hybridScheme": "RSA-OAEP encrypts an AES-256-GCM session key",
    }


# --- /api/demo/send ---


class DemoSendRequest(BaseModel):
    senderVpa: str
    receiverVpa: str
    amount: Decimal
    pin: str
    ttl: Optional[int] = 5
    startDevice: Optional[str] = "phone-alice"


@router.post("/demo/send")
def demo_send(req: DemoSendRequest):
    packet = create_packet(req.senderVpa, req.receiverVpa, req.amount, req.pin, req.ttl)
    mesh_simulator_service.inject(req.startDevice, packet)
    return {
        "packetId": packet.packetId,
        "ciphertextPreview": packet.ciphertext[:64] + "...",
        "ttl": packet.ttl,
        "injectedAt": req.startDevice,
    }


# --- /api/mesh/state ---


@router.get("/mesh/state")
def mesh_state():
    devices = mesh_simulator_service.get_devices()
    device_data = [
        {
            "deviceId": d.device_id,
            "hasInternet": d.has_internet,
            "packetCount": d.packet_count(),
            "packetIds": [p.packetId[:8] for p in d.get_held_packets()],
        }
        for d in devices
    ]
    return {
        "devices": device_data,
        "idempotencyCacheSize": idempotency_service.size(),
    }


# --- /api/mesh/gossip ---


@router.post("/mesh/gossip")
def mesh_gossip():
    result = mesh_simulator_service.gossip_once()
    return {"transfers": result.transfers, "deviceCounts": result.device_counts}


# --- /api/mesh/flush ---


@router.post("/mesh/flush")
def mesh_flush(db: Session = Depends(get_db)):
    uploads = mesh_simulator_service.collect_bridge_uploads()
    results = []
    results_lock = threading.Lock()

    def process_upload(upload):
        thread_db = SessionLocal()
        try:
            r = bridge_ingestion_service.ingest(
                upload.packet, upload.bridge_node_id, 5 - upload.packet.ttl, thread_db
            )
            with results_lock:
                results.append(
                    {
                        "bridgeNode": upload.bridge_node_id,
                        "packetId": upload.packet.packetId[:8],
                        "outcome": r.outcome,
                        "reason": r.reason or "",
                        "transactionId": r.transaction_id if r.transaction_id is not None else -1,
                    }
                )
        finally:
            thread_db.close()

    with concurrent.futures.ThreadPoolExecutor() as executor:
        futures = [executor.submit(process_upload, up) for up in uploads]
        concurrent.futures.wait(futures)

    return {"uploadsAttempted": len(uploads), "results": results}


# --- /api/mesh/reset ---


@router.post("/mesh/reset")
def mesh_reset():
    mesh_simulator_service.reset_mesh()
    idempotency_service.clear()
    return {"status": "mesh and idempotency cache cleared"}


# --- /api/bridge/ingest ---


@router.post("/bridge/ingest", response_model=IngestResultSchema)
def ingest(
    packet: MeshPacketSchema,
    bridge_node_id: str = Header(default="unknown", alias="X-Bridge-Node-Id"),
    hop_count: int = Header(default=0, alias="X-Hop-Count"),
    db: Session = Depends(get_db),
):
    result = bridge_ingestion_service.ingest(packet, bridge_node_id, hop_count, db)
    return IngestResultSchema(
        outcome=result.outcome,
        packetHash=result.packet_hash,
        reason=result.reason,
        transactionId=result.transaction_id,
    )


# --- /api/accounts ---


@router.get("/accounts", response_model=List[AccountSchema])
def list_accounts(db: Session = Depends(get_db)):
    return db.query(Account).all()


# --- /api/transactions ---


@router.get("/transactions", response_model=List[TransactionSchema])
def list_transactions(db: Session = Depends(get_db)):
    return db.query(Transaction).order_by(Transaction.id.desc()).limit(20).all()
