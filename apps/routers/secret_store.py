from cryptography.fernet import Fernet
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured


class SecretStore:
    """Fernet encryption for router credentials."""

    def __init__(self):
        self._cipher = None

    @property
    def cipher(self):
        if self._cipher is None:
            if not settings.FERNET_KEY:
                raise ImproperlyConfigured(
                    "FERNET_KEY must be configured before router secrets can be encrypted."
                )
            try:
                self._cipher = Fernet(settings.FERNET_KEY.encode())
            except (TypeError, ValueError) as exc:
                raise ImproperlyConfigured("FERNET_KEY is not a valid Fernet key.") from exc
        return self._cipher

    def encrypt(self, plaintext):
        if not plaintext:
            return ""
        if plaintext.startswith("enc:v1:"):
            return plaintext
        return "enc:v1:" + self.cipher.encrypt(plaintext.encode()).decode()

    def decrypt(self, ciphertext):
        if not ciphertext:
            return ""
        if not ciphertext.startswith("enc:v1:"):
            return ciphertext
        return self.cipher.decrypt(ciphertext[7:].encode()).decode()


secret_store = SecretStore()
