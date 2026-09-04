import hashlib
import hmac
import ipaddress
import secrets
import socket
import struct


class RadiusError(RuntimeError):
    pass


class RadiusUnavailable(RadiusError):
    pass


class RadiusProtocolError(RadiusError):
    pass


class RadiusAuthClient:
    ACCESS_REQUEST = 1
    ACCESS_ACCEPT = 2
    ACCESS_REJECT = 3

    def __init__(self, host, port=1812, timeout=3.0):
        if not host or not 1 <= int(port) <= 65535 or float(timeout) <= 0:
            raise ValueError("Invalid RADIUS client configuration.")
        self.host = host
        self.port = int(port)
        self.timeout = float(timeout)

    @staticmethod
    def _attribute(attribute_type, value):
        if len(value) > 253:
            raise ValueError("RADIUS attribute is too long.")
        return bytes([attribute_type, len(value) + 2]) + value

    @staticmethod
    def _encrypt_password(password, secret, request_authenticator):
        password_bytes = password.encode("utf-8")
        if not password_bytes or len(password_bytes) > 128:
            raise ValueError("RADIUS password must be between 1 and 128 bytes.")
        padded_length = ((len(password_bytes) + 15) // 16) * 16
        padded = password_bytes.ljust(padded_length, b"\x00")
        encrypted = bytearray()
        previous = request_authenticator
        for offset in range(0, padded_length, 16):
            digest = hashlib.md5(secret + previous).digest()
            block = bytes(a ^ b for a, b in zip(padded[offset:offset + 16], digest))
            encrypted.extend(block)
            previous = block
        return bytes(encrypted)

    def authenticate(self, username, password, shared_secret, nas_ip):
        username_bytes = username.encode("utf-8")
        secret_bytes = shared_secret.encode("utf-8")
        if not username_bytes or not secret_bytes:
            raise ValueError("RADIUS username and shared secret are required.")

        identifier = secrets.randbelow(256)
        request_authenticator = secrets.token_bytes(16)
        address = ipaddress.ip_address(nas_ip)
        nas_attribute = 4 if address.version == 4 else 95
        attributes = b"".join([
            self._attribute(1, username_bytes),
            self._attribute(
                2,
                self._encrypt_password(
                    password, secret_bytes, request_authenticator
                ),
            ),
            self._attribute(nas_attribute, address.packed),
        ])
        length = 20 + len(attributes)
        request_packet = struct.pack(
            "!BBH", self.ACCESS_REQUEST, identifier, length
        ) + request_authenticator + attributes

        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as client:
                client.settimeout(self.timeout)
                client.sendto(request_packet, (self.host, self.port))
                response, _source = client.recvfrom(4096)
        except (OSError, socket.timeout) as exc:
            raise RadiusUnavailable("RADIUS server is unavailable.") from exc

        if len(response) < 20:
            raise RadiusProtocolError("RADIUS response is truncated.")
        code, response_identifier, response_length = struct.unpack("!BBH", response[:4])
        if response_identifier != identifier or response_length != len(response):
            raise RadiusProtocolError("RADIUS response identity or length is invalid.")
        expected_authenticator = hashlib.md5(
            response[:4]
            + request_authenticator
            + response[20:]
            + secret_bytes
        ).digest()
        if not hmac.compare_digest(response[4:20], expected_authenticator):
            raise RadiusProtocolError("RADIUS response authenticator is invalid.")
        if code == self.ACCESS_ACCEPT:
            return True
        if code == self.ACCESS_REJECT:
            return False
        raise RadiusProtocolError("Unexpected RADIUS response code.")


class RadiusDisconnectClient:
    DISCONNECT_REQUEST = 40
    DISCONNECT_ACK = 41
    DISCONNECT_NAK = 42

    def __init__(self, host, port=3799, timeout=3.0):
        if not host or not 1 <= int(port) <= 65535 or float(timeout) <= 0:
            raise ValueError("Invalid RADIUS disconnect client configuration.")
        self.host = host
        self.port = int(port)
        self.timeout = float(timeout)

    def disconnect(
        self,
        session_id,
        shared_secret,
        nas_port_id="",
        calling_station_id="",
    ):
        secret_bytes = shared_secret.encode("utf-8")
        if not session_id or not secret_bytes:
            raise ValueError("Session ID and shared secret are required.")
        identifier = secrets.randbelow(256)
        attributes = RadiusAuthClient._attribute(44, str(session_id).encode("utf-8"))
        if nas_port_id:
            attributes += RadiusAuthClient._attribute(87, str(nas_port_id).encode("utf-8"))
        if calling_station_id:
            attributes += RadiusAuthClient._attribute(
                31, str(calling_station_id).encode("utf-8")
            )
        length = 20 + len(attributes)
        header = struct.pack("!BBH", self.DISCONNECT_REQUEST, identifier, length)
        request_authenticator = hashlib.md5(
            header + (b"\x00" * 16) + attributes + secret_bytes
        ).digest()
        request_packet = header + request_authenticator + attributes

        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as client:
                client.settimeout(self.timeout)
                client.sendto(request_packet, (self.host, self.port))
                response, _source = client.recvfrom(4096)
        except (OSError, socket.timeout) as exc:
            raise RadiusUnavailable("RADIUS disconnect endpoint is unavailable.") from exc

        if len(response) < 20:
            raise RadiusProtocolError("RADIUS disconnect response is truncated.")
        code, response_identifier, response_length = struct.unpack("!BBH", response[:4])
        if response_identifier != identifier or response_length != len(response):
            raise RadiusProtocolError("RADIUS disconnect response is invalid.")
        expected_authenticator = hashlib.md5(
            response[:4] + request_authenticator + response[20:] + secret_bytes
        ).digest()
        if not hmac.compare_digest(response[4:20], expected_authenticator):
            raise RadiusProtocolError("RADIUS disconnect authenticator is invalid.")
        if code == self.DISCONNECT_ACK:
            return True
        if code == self.DISCONNECT_NAK:
            return False
        raise RadiusProtocolError("Unexpected RADIUS disconnect response code.")
