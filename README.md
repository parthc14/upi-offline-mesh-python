# UPI Offline Mesh — Python Implementation

A production-ready backend for offline UPI payments routed through a Bluetooth mesh network using Python and FastAPI.

## Prerequisites

- **Python 3.9+** installed
- **Redis running** on `localhost:6379`
  - macOS: `brew install redis && brew services start redis`
  - Linux: `sudo apt-get install redis-server && sudo systemctl start redis-server`
  - Docker: `docker run -d -p 6379:6379 redis:latest`
  - Windows: Use WSL2 or Docker Desktop

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Verify Redis is running
redis-cli ping  # → PONG

# Start the server
uvicorn main:app --port 8080 --reload

# Open the dashboard
open http://localhost:8080
```

## Demo Flow

The dashboard has four steps:

### Step 1 — Compose a payment

Choose sender, receiver, amount, PIN. Click **"📤 Inject into Mesh"**.

### Step 2 — Run gossip rounds

Click **"🔄 Run Gossip Round"** twice. Each round, every device broadcasts packets to neighbors, TTL decrements per hop.

### Step 3 — Bridge node walks outside

Click **"📡 Bridges Upload to Backend"**.

The server pipeline runs:
1. Hash the ciphertext (SHA-256)
2. Try to claim the hash in the Redis idempotency cache (atomic SETNX)
3. Decrypt with the server's RSA private key (AES-GCM-authenticated)
4. Verify freshness (signed within 24 hours)
5. Debit sender, credit receiver, write ledger

### Step 4 — Demonstrate idempotency

To really see idempotency in action:

1. Click "Inject" once.
2. Click "Gossip" twice (all devices now have the packet).
3. Click "Flush Bridges" — **only one settles, the rest are DUPLICATE_DROPPED**.

If you run flush again, all are duplicates (cache remembers the hash for 24h).

## Run the Tests

```bash
pytest tests/ -v
```

Expected output: 3 tests pass.

The headline test: **`test_single_packet_…_settles_exactly_once`**
- Three threads simulate three bridge nodes delivering the same packet **simultaneously**.
- Uses `threading.Barrier(3)` to fire all threads at the same instant.
- Asserts exactly **one SETTLED**, **two DUPLICATE_DROPPED**.
- Verifies the sender's balance changed exactly once (not three times).

## Architecture

### Web Framework
- **FastAPI** — modern async web framework with OpenAPI support

### Database
- **SQLAlchemy** with **SQLite** (in-memory for testing, file-based for dev)
- Optimistic locking via `version_id_col` (compare-and-swap on version field)
- Handles concurrent updates safely

### Idempotency
- **Redis** with atomic `SET nx EX` (atomic SET-if-not-exists with TTL)
- Hash of ciphertext is the key; prevents duplicates across threads/processes

### Cryptography
- **`cryptography`** library for RSA-OAEP + AES-256-GCM
- Hybrid encryption: one-time AES key wrapped in RSA
- Wire format: `[256B RSA-key][12B IV][ciphertext+16B tag]`

### Concurrency
- `threading.Lock()` per virtual device (ensures thread-safe access)
- `ThreadPoolExecutor` for parallel bridge uploads
- Each thread gets its own SQLAlchemy session (not thread-safe)

### Dashboard
- Pure HTML+JavaScript, served via FileResponse
- Fetches from REST endpoints every 3 seconds
- Real-time visualization of account balances and transactions

## File Structure

```
upi_mesh_python/
├── main.py                  # FastAPI entry point + lifespan startup
├── config.py                # Settings (Redis, DB URLs)
├── database.py              # SQLAlchemy engine + get_db()
├── models/                  # ORM entities (Account, Transaction)
├── schemas/                 # Pydantic validation schemas
├── crypto/                  # RSA keypair + hybrid encryption
├── services/                # Business logic (demo, mesh, settlement, etc.)
├── routers/                 # REST endpoints (/api/*, /)
├── templates/dashboard.html # Web UI
├── tests/                   # pytest tests
└── requirements.txt         # Python dependencies
```

## Design Highlights

### Atomic Idempotency
Redis `SETNX` with TTL ensures a payment is settled **exactly once**, even if delivered by multiple bridge nodes simultaneously. Duplicate uploads return immediately with `DUPLICATE_DROPPED` status.

### Optimistic Locking
Account balances use SQLAlchemy's `version_id_col` to detect concurrent updates. If two threads attempt to modify the same account simultaneously, one succeeds and the other raises `StaleDataError`, preventing lost updates.

### Authenticated Encryption
AES-256-GCM provides both confidentiality and authenticity. Tampering with even one ciphertext bit fails authentication, so packets cannot be modified in transit without detection.

### Thread-Safe Mesh Simulation
Virtual devices use `threading.Lock()` to synchronize packet storage, and parallel bridge uploads use `ThreadPoolExecutor` with per-thread database sessions.

## Troubleshooting

**`redis.exceptions.ConnectionError`** — Redis not running.
```bash
redis-cli ping  # should return PONG
brew services start redis  # or your platform's equivalent
```

**Port 8080 already in use** — Change in main.py or:
```bash
uvicorn main:app --port 8081
```

**`ModuleNotFoundError`** — Missing dependencies.
```bash
pip install -r requirements.txt
```

**Tests fail with Redis connection error** — Same as above, start Redis first.

## Development

For local development with auto-reload:

```bash
uvicorn main:app --reload --port 8080
```

The server restarts whenever you save a Python file.

## License

MIT License — see LICENSE file for details.
