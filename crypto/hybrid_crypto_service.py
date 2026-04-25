import base64
import hashlib
import json
import os
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPublicKey, RSAPrivateKey
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

RSA_ENCRYPTED_KEY_BYTES = 256
GCM_IV_BYTES = 12
GCM_TAG_BYTES = 16
MIN_CIPHERTEXT_LEN = RSA_ENCRYPTED_KEY_BYTES + GCM_IV_BYTES + GCM_TAG_BYTES


class HybridCryptoService:

    def encrypt(self, instruction, public_key: RSAPublicKey) -> str:
        plaintext = json.dumps({
            "senderVpa": instruction.senderVpa,
            "receiverVpa": instruction.receiverVpa,
            "amount": str(instruction.amount),
            "pinHash": instruction.pinHash,
            "nonce": instruction.nonce,
            "signedAt": instruction.signedAt,
        }).encode()

        aes_key = os.urandom(32)
        iv = os.urandom(GCM_IV_BYTES)

        aesgcm = AESGCM(aes_key)
        aes_ciphertext = aesgcm.encrypt(iv, plaintext, None)

        encrypted_aes_key = public_key.encrypt(
            aes_key,
            padding.OAEP(
                mgf=padding.MGF1(algorithm=hashes.SHA256()),
                algorithm=hashes.SHA256(),
                label=None,
            ),
        )
        assert len(encrypted_aes_key) == RSA_ENCRYPTED_KEY_BYTES

        packed = encrypted_aes_key + iv + aes_ciphertext
        return base64.b64encode(packed).decode()

    def decrypt(self, base64_ciphertext: str):
        from schemas.payment_instruction import PaymentInstructionSchema

        raw = base64.b64decode(base64_ciphertext)

        if len(raw) < MIN_CIPHERTEXT_LEN:
            raise ValueError("Ciphertext too short")

        encrypted_aes_key = raw[:RSA_ENCRYPTED_KEY_BYTES]
        iv = raw[RSA_ENCRYPTED_KEY_BYTES : RSA_ENCRYPTED_KEY_BYTES + GCM_IV_BYTES]
        aes_ciphertext = raw[RSA_ENCRYPTED_KEY_BYTES + GCM_IV_BYTES :]

        from crypto.server_key_holder import server_key_holder

        aes_key = server_key_holder.private_key.decrypt(
            encrypted_aes_key,
            padding.OAEP(
                mgf=padding.MGF1(algorithm=hashes.SHA256()),
                algorithm=hashes.SHA256(),
                label=None,
            ),
        )

        aesgcm = AESGCM(aes_key)
        plaintext = aesgcm.decrypt(iv, aes_ciphertext, None)

        return PaymentInstructionSchema.from_json_bytes(plaintext)

    def hash_ciphertext(self, base64_ciphertext: str) -> str:
        return hashlib.sha256(base64_ciphertext.encode()).hexdigest()


hybrid_crypto_service = HybridCryptoService()
