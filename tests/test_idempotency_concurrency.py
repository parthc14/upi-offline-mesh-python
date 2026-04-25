import threading
import pytest
import time
from decimal import Decimal
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database import Base
from crypto.server_key_holder import server_key_holder
from crypto.hybrid_crypto_service import hybrid_crypto_service
from services.demo_service import seed_accounts, create_packet
from services.bridge_ingestion_service import bridge_ingestion_service
from services.idempotency_service import idempotency_service
from schemas.payment_instruction import PaymentInstructionSchema
from models.account import Account


@pytest.fixture(scope="session", autouse=True)
def init_crypto():
    server_key_holder.init()


@pytest.fixture()
def db():
    import tempfile
    import os

    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)

    engine = create_engine(f"sqlite:///{db_path}")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    seed_accounts(session)

    from database import SessionLocal, engine as app_engine
    import database
    database.engine = engine
    database.SessionLocal = Session

    yield session
    session.close()
    Base.metadata.drop_all(engine)
    engine.dispose()
    os.unlink(db_path)


@pytest.fixture(autouse=True)
def clear_idempotency():
    idempotency_service.clear()
    yield
    idempotency_service.clear()


def test_single_packet_delivered_by_three_bridges_settles_exactly_once(db):
    alice_before = db.get(Account, "alice@demo").balance
    bob_before = db.get(Account, "bob@demo").balance

    packet = create_packet("alice@demo", "bob@demo", Decimal("100.00"), "1234", 5)

    settled_count = 0
    duplicate_count = 0
    lock = threading.Lock()
    barrier = threading.Barrier(3)

    def run(node_id: str):
        nonlocal settled_count, duplicate_count
        from database import SessionLocal

        thread_db = SessionLocal()
        try:
            barrier.wait()
            result = bridge_ingestion_service.ingest(packet, node_id, 3, thread_db)
            with lock:
                if result.outcome == "SETTLED":
                    settled_count += 1
                elif result.outcome == "DUPLICATE_DROPPED":
                    duplicate_count += 1
        finally:
            thread_db.close()

    threads = [threading.Thread(target=run, args=(f"bridge-{i}",)) for i in range(3)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=5)

    assert settled_count == 1, f"Expected 1 SETTLED, got {settled_count}"
    assert duplicate_count == 2, f"Expected 2 DUPLICATE_DROPPED, got {duplicate_count}"

    db.expire_all()
    alice_after = db.get(Account, "alice@demo").balance
    bob_after = db.get(Account, "bob@demo").balance
    assert alice_after == alice_before - Decimal("100.00")
    assert bob_after == bob_before + Decimal("100.00")


def test_tampered_ciphertext_is_rejected(db):
    from schemas.mesh_packet import MeshPacketSchema

    packet = create_packet("alice@demo", "bob@demo", Decimal("50.00"), "1234", 5)
    chars = list(packet.ciphertext)
    mid = len(chars) // 2
    chars[mid] = "B" if chars[mid] == "A" else "A"
    tampered = MeshPacketSchema(
        packetId=packet.packetId,
        ttl=packet.ttl,
        createdAt=packet.createdAt,
        ciphertext="".join(chars),
    )
    result = bridge_ingestion_service.ingest(tampered, "bridge-x", 1, db)
    assert result.outcome == "INVALID"


def test_encrypt_decrypt_round_trip():
    instruction = PaymentInstructionSchema(
        senderVpa="alice@demo",
        receiverVpa="bob@demo",
        amount=Decimal("123.45"),
        pinHash="abcdef",
        nonce="nonce-1",
        signedAt=int(time.time() * 1000),
    )
    ct = hybrid_crypto_service.encrypt(instruction, server_key_holder.public_key)
    decrypted = hybrid_crypto_service.decrypt(ct)

    assert decrypted.senderVpa == instruction.senderVpa
    assert decrypted.receiverVpa == instruction.receiverVpa
    assert decrypted.amount == instruction.amount
    assert decrypted.nonce == instruction.nonce
