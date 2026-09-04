import hmac
import hashlib
import time
import json
import requests
import uuid
import base64
import binascii
import ipaddress
import re
import subprocess


class WireGuardConfigurationError(ValueError):
    pass


class WireGuardCommandError(RuntimeError):
    pass


def validate_wireguard_public_key(value):
    try:
        decoded = base64.b64decode(value, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise WireGuardConfigurationError("Invalid WireGuard public key.") from exc
    if len(decoded) != 32:
        raise WireGuardConfigurationError("Invalid WireGuard public key.")
    return value


def validate_managed_ip(value, managed_subnet):
    try:
        address = ipaddress.ip_address(value)
        network = ipaddress.ip_network(managed_subnet, strict=True)
    except ValueError as exc:
        raise WireGuardConfigurationError("Invalid WireGuard network address.") from exc
    if address.version != network.version or address not in network:
        raise WireGuardConfigurationError("WireGuard IP is outside the managed subnet.")
    if address in (network.network_address, network.broadcast_address):
        raise WireGuardConfigurationError("WireGuard IP is not assignable to a peer.")
    return str(address)


class ProvisioningAgentClient:
    """HMAC-authenticated client for provisioning agent."""

    def __init__(self, api_key, base_url):
        self.api_key = api_key
        self.base_url = base_url

    def _sign(self, payload, timestamp):
        message = f"{timestamp}.{payload}"
        return hmac.new(
            self.api_key.encode(),
            message.encode(),
            hashlib.sha256,
        ).hexdigest()

    def _request(self, method, endpoint, data=None):
        timestamp = str(int(time.time()))
        payload = json.dumps(data) if data else ""
        signature = self._sign(payload, timestamp)

        response = requests.request(
            method,
            f"{self.base_url}{endpoint}",
            json=data,
            headers={
                "X-Provisioning-Timestamp": timestamp,
                "X-Provisioning-Signature": signature,
                "X-Provisioning-Key-Id": self.api_key[:8],
                "Content-Type": "application/json",
            },
            timeout=30,
        )
        response.raise_for_status()
        return response.json()

    def provision_wireguard_peer(self, router_id, wireguard_ip, public_key):
        return self._request("POST", "/internal/router-provisioning/", {
            "request_id": str(uuid.uuid4()),
            "action": "provision_wireguard_peer",
            "router_id": str(router_id),
            "wireguard_ip": wireguard_ip,
            "public_key": public_key,
        })

    def test_radius_authentication(self, router_id, username, password):
        return self._request("POST", "/internal/router-provisioning/", {
            "request_id": str(uuid.uuid4()),
            "action": "test_radius_authentication",
            "router_id": str(router_id),
            "username": username,
            "password": password,
        })

    def suspend_wireguard_peer(self, router_id):
        return self._request("POST", "/internal/router-provisioning/", {
            "request_id": str(uuid.uuid4()),
            "action": "suspend_wireguard_peer",
            "router_id": str(router_id),
        })


class WireGuardManager:
    """Manage WireGuard peers on VPS."""

    _HOST_PATTERN = re.compile(r"^[A-Za-z0-9_.:@\-\[\]]+$")
    _INTERFACE_PATTERN = re.compile(r"^[A-Za-z0-9_=+.-]{1,15}$")

    def __init__(
        self,
        vps_host,
        ssh_key,
        known_hosts="",
        interface="wg0",
        managed_subnet="10.100.100.0/24",
        use_sudo=True,
        save_config=True,
        timeout=30,
    ):
        self.vps_host = vps_host
        self.ssh_key = ssh_key
        self.known_hosts = known_hosts
        self.interface = interface
        self.managed_subnet = managed_subnet
        self.use_sudo = use_sudo
        self.save_config = save_config
        self.timeout = timeout

    def _validate_configuration(self):
        if (
            not self.vps_host
            or self.vps_host.startswith("-")
            or not self._HOST_PATTERN.fullmatch(self.vps_host)
        ):
            raise WireGuardConfigurationError("WG_VPS_HOST is invalid or missing.")
        if not self.ssh_key:
            raise WireGuardConfigurationError("WG_VPS_SSH_KEY is missing.")
        if not self._INTERFACE_PATTERN.fullmatch(self.interface):
            raise WireGuardConfigurationError("WG_INTERFACE is invalid.")

    def _ssh(self, command):
        self._validate_configuration()
        ssh_command = [
            "ssh",
            "-i",
            self.ssh_key,
            "-o",
            "BatchMode=yes",
            "-o",
            "StrictHostKeyChecking=yes",
            "-o",
            "ConnectTimeout=10",
        ]
        if self.known_hosts:
            ssh_command.extend(["-o", f"UserKnownHostsFile={self.known_hosts}"])
        ssh_command.extend(["--", self.vps_host, *command])
        try:
            result = subprocess.run(
                ssh_command,
                capture_output=True,
                text=True,
                timeout=self.timeout,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise WireGuardCommandError("Unable to execute the WireGuard SSH command.") from exc
        if result.returncode != 0:
            raise WireGuardCommandError("WireGuard SSH command failed.")
        return result.stdout

    def _wg_command(self, *arguments):
        prefix = ["sudo", "--"] if self.use_sudo else []
        return self._ssh([*prefix, "wg", *arguments])

    def _save(self):
        if not self.save_config:
            return
        prefix = ["sudo", "--"] if self.use_sudo else []
        self._ssh([*prefix, "wg-quick", "save", self.interface])

    def create_peer(self, public_key, allowed_ip):
        """Add a WireGuard peer to the VPS."""
        public_key = validate_wireguard_public_key(public_key)
        allowed_ip = validate_managed_ip(allowed_ip, self.managed_subnet)
        suffix = "/32" if ipaddress.ip_address(allowed_ip).version == 4 else "/128"
        self._wg_command(
            "set", self.interface, "peer", public_key, "allowed-ips", f"{allowed_ip}{suffix}"
        )
        self._save()
        return True

    def remove_peer(self, public_key):
        """Remove a WireGuard peer from the VPS."""
        public_key = validate_wireguard_public_key(public_key)
        self._wg_command("set", self.interface, "peer", public_key, "remove")
        self._save()
        return True

    def list_peers(self):
        """List all WireGuard peers."""
        output = self._wg_command("show", self.interface, "dump")
        peers = []
        lines = output.splitlines()
        for line in lines[1:]:
            fields = line.split("\t")
            if len(fields) < 8:
                raise WireGuardCommandError("Unexpected WireGuard dump output.")
            try:
                latest_handshake = int(fields[4])
                transfer_rx = int(fields[5])
                transfer_tx = int(fields[6])
            except ValueError as exc:
                raise WireGuardCommandError("Unexpected WireGuard dump output.") from exc
            peers.append({
                "public_key": fields[0],
                "endpoint": fields[2],
                "allowed_ips": fields[3].split(","),
                "latest_handshake": latest_handshake,
                "transfer_rx": transfer_rx,
                "transfer_tx": transfer_tx,
                "persistent_keepalive": fields[7],
            })
        return peers

    def get_peer_status(self, public_key):
        """Check if a peer is currently connected."""
        peers = self.list_peers()
        for peer in peers:
            if peer["public_key"] == public_key:
                return peer.get("latest_handshake", 0) > time.time() - 180
        return False
