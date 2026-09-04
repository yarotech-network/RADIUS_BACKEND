import secrets
import string


def generate_reference(prefix="ref"):
    return f"{prefix}-{secrets.token_hex(12)}"


def generate_shortcode(length=8):
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))
