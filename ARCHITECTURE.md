# UPI Offline Mesh — Architecture

## High-Level System Design

This is an offline UPI payment system that routes encrypted payments through a Bluetooth mesh network. Here's how it works:

```
┌─────────────────────────────────────────────────────────────────────┐
│                    SENDER PHONE (offline)                           │
│  PaymentInstruction { sender, receiver, amount, pinHash, nonce }   │
│              │                                                      │
│              ▼ encrypt with server's RSA public key                 │
│   MeshPacket { packetId, ttl, createdAt, ciphertext }              │
└──────────────────────────────┬──────────────────────────────────────┘
                               │ Bluetooth gossip (simulated)
                               ▼
    ┌─────────┐  hop   ┌─────────┐  hop   ┌─────────┐
    │phone-   │ ─────▶ │phone-   │ ─────▶ │phone-   │ ◀── walks out
    │stranger1│        │stranger2│        │bridge   │     gets 4G
    └─────────┘        └─────────┘        └────┬────┘
                                               │
                                               ▼ HTTPS POST
┌─────────────────────────────────────────────────────────────────────┐
│              BACKEND SERVER (FastAPI + SQLAlchemy)                  │
│                                                                     │
│  [1] Hash ciphertext (SHA-256)                                      │
│       │                                                             │
│       ▼                                                             │
│  [2] Idempotency: claim hash in Redis (atomic SETNX)                │
│       │ If duplicate → return DUPLICATE_DROPPED                     │
│       ▼                                                             │
│  [3] Decrypt with server's RSA private key (AES-GCM authenticated)  │
│       │ If tampered → return INVALID                               │
│       ▼                                                             │
│  [4] Freshness: reject if >24h old                                  │
│       │                                                             │
│       ▼                                                             │
│  [5] Settlement: atomic debit + credit in one db.commit()          │
│       │ With optimistic locking on Account.version                  │
│       ▼                                                             │
│  [6] Return SETTLED with transaction ID                            │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Core Components

### 1. **Cryptography Layer** (`crypto/`)

**RSA-2048 Keypair:**
```python
from crypto.server_key_holder import server_key_holder

# Generated at startup, persisted in memory
server_key_holder.init()
public_key_b64 = server_key_holder.get_public_key_base64()
```

**Hybrid Encryption (RSA-OAEP + AES-256-GCM):**
```python
from crypto.hybrid_crypto_service import hybrid_crypto_service

# Encryption (happens on sender's phone, simulated by DemoService)
ciphertext_b64 = hybrid_crypto_service.encrypt(instruction, public_key)

# Wire format (byte-exact):
# [Byte 0-255]   RSA-OAEP encrypted AES-256 key
# [Byte 256-267] 12-byte GCM IV
# [Byte 268+]    AES-GCM ciphertext + 16-byte auth tag

# Decryption (happens on backend during settlement)
instruction = hybrid_crypto_service.decrypt(ciphertext_b64)
# Throws InvalidTag if ciphertext was tampered with
```

**Why Hybrid Encryption:**
- RSA can only encrypt ~245 bytes (payload is larger)
- Solution: RSA encrypts the AES key, AES encrypts the payload
- GCM provides authenticated encryption (tampering = authentication failure)

---

### 2. **Idempotency Cache** (`services/idempotency_service.py`)

```python
from services.idempotency_service import idempotency_service

# Try to claim a packet hash (atomic at Redis level)
result = idempotency_service.claim(packet_hash)

# Returns True only for the FIRST caller
# Returns False for all subsequent callers (duplicates)
# Redis command: SET key value NX EX 86400 (atomic)
```

**How it prevents duplicates:**
```
Scenario: Same packet uploaded by 3 bridge nodes simultaneously
    ↓
All compute: hash = SHA256(ciphertext) = "abc123..."
    ↓
All call: idempotency.claim("abc123...")
    ↓
Redis SETNX (atomic operation):
  Thread 1: SET "abc123..." value NX EX 86400 → TRUE (success)
  Thread 2: SET "abc123..." value NX EX 86400 → FALSE (already exists)
  Thread 3: SET "abc123..." value NX EX 86400 → FALSE (already exists)
    ↓
Result: Only Thread 1 continues to settlement
         Threads 2 & 3 return DUPLICATE_DROPPED immediately
         Payment settles exactly ONCE
```

---

### 3. **Virtual Mesh Devices** (`services/virtual_device.py`, `services/mesh_simulator_service.py`)

```python
from services.virtual_device import VirtualDevice
from services.mesh_simulator_service import mesh_simulator_service

# 5 simulated phones
mesh_simulator_service.get_devices()
# [
#   VirtualDevice(device_id="phone-alice", has_internet=False),
#   VirtualDevice(device_id="phone-stranger1", has_internet=False),
#   VirtualDevice(device_id="phone-stranger2", has_internet=False),
#   VirtualDevice(device_id="phone-stranger3", has_internet=False),
#   VirtualDevice(device_id="phone-bridge", has_internet=True),  ← Has 4G
# ]
```

**Gossip Protocol (Packet Routing):**
```python
# Each round, packets hop to neighboring devices (TTL decrements)
result = mesh_simulator_service.gossip_once()
# {
#   transfers: 4,  # 4 packets moved to new devices
#   device_counts: {
#     "phone-alice": 1,      # Holds 1 packet (source)
#     "phone-stranger1": 1,  # Received 1 packet
#     "phone-stranger2": 1,  # Received 1 packet
#     "phone-stranger3": 1,  # Received 1 packet
#     "phone-bridge": 1,     # Received 1 packet (will upload)
#   }
# }
```

**Important:** Takes snapshot BEFORE iterating. This ensures a packet travels max 1 hop per round (not cascading through all devices in one round).

---

### 4. **Settlement & Transactions** (`services/settlement_service.py`)

```python
from services.settlement_service import settlement_service
from sqlalchemy.orm.exc import StaleDataError

try:
    transaction = settlement_service.settle(
        instruction,  # Decrypted payment details
        packet_hash,  # For deduplication in DB
        bridge_node_id,
        hop_count,
        db  # SQLAlchemy session
    )
except StaleDataError:
    # Optimistic lock conflict: another thread updated same account
    # This should NOT happen in single-server demo
    # In production, would implement retry logic
    raise
```

**Settlement Logic (Atomic):**
```python
def settle(instruction, packet_hash, bridge_node_id, hop_count, db):
    # 1. Load accounts
    sender = db.get(Account, instruction.senderVpa)
    receiver = db.get(Account, instruction.receiverVpa)
    
    # 2. Check balance
    if sender.balance < instruction.amount:
        # Mark as REJECTED, don't transfer money
        return _record_rejected(...)
    
    # 3. Transactional update (all-or-nothing)
    sender.balance -= instruction.amount
    receiver.balance += instruction.amount
    
    transaction = Transaction(
        packet_hash=packet_hash,
        sender_vpa=instruction.senderVpa,
        receiver_vpa=instruction.receiverVpa,
        amount=instruction.amount,
        signed_at=instruction.signedAt,
        settled_at=datetime.now(timezone.utc),
        bridge_node_id=bridge_node_id,
        hop_count=hop_count,
        status=TransactionStatus.SETTLED,
    )
    
    db.add(transaction)
    db.commit()  # ← Atomic: all or nothing
    # If version conflict: StaleDataError
    # If constraint violation: IntegrityError
    # If any error: auto-rollback in finally block
    
    return transaction
```

**Optimistic Locking:**
```
Thread A: Reads Account(vpa="alice", version=5, balance=5000)
Thread B: Reads Account(vpa="alice", version=5, balance=5000)
    ↓
Thread A: UPDATE accounts SET balance=4500, version=6 
          WHERE vpa='alice' AND version=5
          ✓ Success (1 row updated, version incremented)
    ↓
Thread B: UPDATE accounts SET balance=4500, version=6 
          WHERE vpa='alice' AND version=5
          ✗ Fails (0 rows matched, version is now 6)
          → StaleDataError raised
```

---

### 5. **Bridge Ingestion Pipeline** (`services/bridge_ingestion_service.py`)

The main endpoint that processes incoming packets:

```python
@router.post("/api/bridge/ingest")
def ingest(packet: MeshPacketSchema, bridge_node_id: str, hop_count: int, db: Session):
    return bridge_ingestion_service.ingest(packet, bridge_node_id, hop_count, db)

# Pipeline (in order):
# [1] Hash ciphertext
# [2] Claim in Redis (idempotency gate)
# [3] Decrypt (AES-GCM auth check)
# [4] Freshness (reject if >24h old)
# [5] Settlement (atomic debit + credit)
```

**Response:**
```json
{
  "outcome": "SETTLED" | "DUPLICATE_DROPPED" | "INVALID",
  "packetHash": "abc123...",
  "reason": null | "decryption_failed" | "stale_packet" | ...,
  "transactionId": 1 | null
}
```

---

### 6. **REST API** (`routers/api.py`)

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/server-key` | GET | Retrieve server's RSA public key |
| `/api/accounts` | GET | List all accounts & balances |
| `/api/transactions` | GET | Last 20 transactions |
| `/api/mesh/state` | GET | State of all virtual devices |
| `/api/demo/send` | POST | Inject encrypted payment into mesh |
| `/api/mesh/gossip` | POST | Run one gossip round (packet routing) |
| `/api/mesh/flush` | POST | Bridge nodes upload to backend (parallel) |
| `/api/mesh/reset` | POST | Clear mesh & idempotency cache |
| `/api/bridge/ingest` | POST | Settlement pipeline (real endpoint) |
| `/` | GET | Dashboard HTML |

---

### 7. **Database Schema**

**Accounts Table:**
```python
class Account(Base):
    vpa: str (PK)           # e.g., "alice@demo"
    holder_name: str        # e.g., "Alice"
    balance: Decimal(19,2)  # e.g., "5000.00"
    version: int            # Optimistic lock counter
```

**Transactions Table:**
```python
class Transaction(Base):
    id: int (PK, auto-increment)
    packet_hash: str (unique)           # SHA-256 of ciphertext
    sender_vpa: str
    receiver_vpa: str
    amount: Decimal(19,2)
    signed_at: datetime                 # When sender signed it
    settled_at: datetime                # When backend processed it
    bridge_node_id: str                 # Which node uploaded it
    hop_count: int                      # How many hops it took
    status: "SETTLED" | "REJECTED"      # Outcome
```

---

## Data Flow: End-to-End Example

### **Step 1: User Creates Payment**
```
UI: POST /api/demo/send
  {
    "senderVpa": "alice@demo",
    "receiverVpa": "bob@demo",
    "amount": 500,
    "pin": "1234",
    "ttl": 5
  }
    ↓
DemoService.create_packet()
  - Build PaymentInstruction(alice, bob, 500, sha256("1234"), uuid.uuid4(), now())
  - Encrypt with server RSA public key using AES-GCM
  - Create MeshPacket(uuid(), 5, now(), ciphertext)
    ↓
MeshSimulatorService.inject("phone-alice", packet)
    ↓
UI: GET /api/mesh/state
  - "phone-alice" now holds 1 packet
```

### **Step 2: Gossip Propagation**
```
UI: POST /api/mesh/gossip (call 2x)
    ↓
Round 1:
  - Take snapshot of all device packets
  - For each device pair:
    - If src has packet AND dst doesn't, copy with ttl-1
  - Result: 4 transfers
  - All 5 devices now hold the packet (ttl decreased each time)
    ↓
Round 2:
  - All devices already have it
  - No transfers
    ↓
UI: GET /api/mesh/state
  - All 5 devices hold 1 packet each
```

### **Step 3: Bridge Upload & Settlement**
```
UI: POST /api/mesh/flush
    ↓
MeshSimulatorService.collect_bridge_uploads()
  - Only "phone-bridge" has hasInternet=true
  - Returns 1 upload: BridgeUpload("phone-bridge", packet)
    ↓
[Parallel execution via ThreadPoolExecutor]
  - Thread 1 processes upload:
    ↓
    BridgeIngestionService.ingest(packet, "phone-bridge", 1)
      [1] hash = sha256("base64ciphertext") = "abc123..."
      [2] idempotency.claim("abc123...") → TRUE (first caller)
      [3] instruction = decrypt(ciphertext) → PaymentInstruction
      [4] age = now - instruction.signedAt = 0.5s < 86400s ✓
      [5] settlement.settle(instruction, ...)
          - Load alice(balance=5000, version=5)
          - Load bob(balance=1000, version=2)
          - alice.balance = 5000 - 500 = 4500
          - bob.balance = 1000 + 500 = 1500
          - CREATE Transaction(packet_hash="abc123...", status="SETTLED")
          - db.commit()
            - UPDATE accounts SET balance=4500, version=6 WHERE vpa='alice' AND version=5
            - UPDATE accounts SET balance=1500, version=3 WHERE vpa='bob' AND version=2
            - INSERT INTO transactions ...
            - All 3 succeed atomically or all rollback
          ↓
      Return IngestResult(outcome="SETTLED", transactionId=1)
    ↓
UI: GET /api/accounts
  - alice.balance = 4500 ✓ (debited ₹500)
  - bob.balance = 1500 ✓ (credited ₹500)
    ↓
UI: GET /api/transactions
  - TX #1: alice → bob ₹500 [SETTLED] ✓
```

---

## Key Design Principles

### **1. Encrypted-by-Default**
- Sender encrypts with server's public key
- Only server can decrypt (has private key)
- Intermediates never see plaintext

### **2. Authenticated Encryption (GCM)**
- AES-GCM provides confidentiality AND authenticity
- If intermediary modifies even 1 bit → authentication tag fails
- Tampering is cryptographically impossible

### **3. Idempotency via Atomic Cache**
- Redis SETNX is atomic at server level
- No race conditions
- Hash (not ID) is deduplication key (can't be forged)

### **4. Atomic Settlement**
- Debit + credit + ledger insert in ONE `db.commit()`
- All or nothing: either all succeed or all rollback
- No partial updates visible to other threads

### **5. Optimistic Locking**
- Version field on Account acts as compare-and-swap
- No row locks (no deadlocks)
- Concurrent updates detected and rejected

### **6. Stateless Message Routing**
- Packets are self-contained (fully encrypted)
- Intermediates route without understanding content
- Only hash/freshness/tampering checked on backend

---

## Technology Stack

| Layer | Technology | Version |
|-------|-----------|---------|
| **Web** | FastAPI | 0.136+ |
| **Server** | Uvicorn | 0.46+ |
| **ORM** | SQLAlchemy | 2.0+ |
| **Database** | SQLite | (file-based) |
| **Cache** | Redis | 7.0+ |
| **Crypto** | cryptography | 43.0+ |
| **Validation** | Pydantic | 2.13+ |
| **Testing** | pytest | 9.0+ |

---

## Running the System

See [README.md](README.md) for complete setup and usage instructions.

## Testing

All 3 core tests pass:
- **Concurrency test**: 3 threads, 1 packet → exactly 1 SETTLED, 2 DUPLICATE_DROPPED
- **Tamper test**: Modified ciphertext → INVALID
- **Crypto test**: Encryption/decryption round-trip

Run with: `pytest tests/ -v`
