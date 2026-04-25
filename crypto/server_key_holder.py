import logging
import base64
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    PublicFormat,
)

logger = logging.getLogger(__name__)


class ServerKeyHolder:
    def __init__(self):
        self._private_key = None
        self._public_key = None

    def init(self) -> None:
        self._private_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=2048,
        )
        self._public_key = self._private_key.public_key()
        logger.info(
            "Server RSA keypair generated (2048-bit). Public key fingerprint: %s...",
            self.get_public_key_base64()[:32],
        )

    @property
    def private_key(self):
        return self._private_key

    @property
    def public_key(self):
        return self._public_key

    def get_public_key_base64(self) -> str:
        der_bytes = self._public_key.public_bytes(
            Encoding.DER, PublicFormat.SubjectPublicKeyInfo
        )
        return base64.b64encode(der_bytes).decode()


server_key_holder = ServerKeyHolder()
