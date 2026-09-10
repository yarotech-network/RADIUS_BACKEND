"""Bounded, read-only RouterOS discovery over a verified management VPN endpoint."""
import ipaddress
import json
import re
import time
from datetime import timedelta

import requests
from django.conf import settings
from django.utils import timezone

from .secret_store import secret_store

VERSION = "routeros-rest-inventory-v1"
# Query only non-secret properties. Never collect exports, users, RADIUS secrets or scripts.
TABLES = {
    "resource": ("system/resource", "board-name,version,architecture-name"),
    "interfaces": ("interface", "name,type,disabled"),
    "bridge_ports": ("interface/bridge/port", "bridge,interface,disabled"),
    "bridges": ("interface/bridge", "name,vlan-filtering"),
    "packages": ("system/package", "name,version,disabled"),
    "members": ("interface/list/member", "list,interface"),
    "addresses": ("ip/address", "address,interface,disabled"),
    "routes": ("ip/route", "dst-address,immediate-gw,gateway,active,disabled"),
    "dhcp_clients": ("ip/dhcp-client", "interface,disabled"),
    "vlans": ("interface/vlan", "name,interface"),
    "bonds": ("interface/bonding", "name,slaves"),
    "hotspots": ("ip/hotspot", "name,interface,profile,disabled"),
    "device_mode": ("system/device-mode", "hotspot"),
}
MESSAGES = {
    "not_configured": "Discovery requires an administrator-approved management VPN destination.",
    "vpn_required": "Provision the management VPN before running discovery.",
    "credentials_required": "Set the RouterOS username and password before running discovery.",
    "tls_failed": "Router certificate verification failed. Configure a trusted certificate or CA bundle.",
    "authentication_failed": "RouterOS rejected the discovery credentials or read permissions.",
    "unreachable": "The management HTTPS service could not be reached within the discovery deadline.",
    "redirect_refused": "The router returned a redirect; discovery only accepts its assigned endpoint.",
    "invalid_response": "The router returned an unexpected or oversized inventory response.",
    "service_unavailable": "The router HTTPS REST service is unavailable.",
}


class DiscoveryError(Exception):
    def __init__(self, code):
        self.code = code
        super().__init__(MESSAGES[code])


def destination(router):
    if router.deployment_status != "deployed" or not router.wireguard_ip or not router.is_active:
        raise DiscoveryError("vpn_required")
    try:
        address = ipaddress.IPv4Address(router.wireguard_ip)
        network = ipaddress.IPv4Network(settings.WG_MANAGED_SUBNET, strict=True)
        allowed = [ipaddress.IPv4Network(c, strict=False) for c in getattr(settings, "ROUTER_DISCOVERY_ALLOWED_CIDRS", [])]
        if address not in network or address in (network.network_address, network.broadcast_address) or address.is_loopback or address.is_link_local or not any(address in item for item in allowed):
            raise ValueError()
        port = int(getattr(settings, "ROUTER_DISCOVERY_HTTPS_PORT", 443))
        if not 1 <= port <= 65535:
            raise ValueError()
    except (ValueError, TypeError):
        raise DiscoveryError("not_configured") from None
    return f"https://{address}:{port}/rest"


def read_table(session, url, fields, deadline, optional=False, filters=None):
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise DiscoveryError("unreachable")
    try:
        with session.get(url, params={".proplist": fields, **(filters or {})},
                         timeout=(min(2, remaining), min(2, remaining)),
                         allow_redirects=False, stream=True) as response:
            if 300 <= response.status_code < 400:
                raise DiscoveryError("redirect_refused")
            if response.status_code in (401, 403):
                raise DiscoveryError("authentication_failed")
            if optional and response.status_code in (400, 404):
                return None
            if response.status_code != 200:
                raise DiscoveryError("service_unavailable")
            content = bytearray()
            for chunk in response.iter_content(chunk_size=8192):
                if time.monotonic() > deadline:
                    raise DiscoveryError("unreachable")
                content.extend(chunk)
                if len(content) > 262144:
                    raise DiscoveryError("invalid_response")
            rows = json.loads(content)
            if isinstance(rows, dict):
                rows = [rows]
            if not isinstance(rows, list) or len(rows) > 512 or any(not isinstance(row, dict) for row in rows):
                raise DiscoveryError("invalid_response")
            selected = fields.split(',')
            cleaned = []
            for row in rows:
                item = {}
                for key in selected:
                    if key not in row:
                        continue
                    value = row[key]
                    if not isinstance(value, (str, int, bool)) or len(str(value)) > 512 or any(ord(c) < 32 for c in str(value)):
                        raise DiscoveryError("invalid_response")
                    item[key] = str(value).lower() if isinstance(value, bool) else str(value)
                cleaned.append(item)
            return cleaned
    except requests.exceptions.SSLError:
        raise DiscoveryError("tls_failed") from None
    except (requests.RequestException, OSError):
        raise DiscoveryError("unreachable") from None
    except (ValueError, TypeError):
        raise DiscoveryError("invalid_response") from None


def collect(router):
    base = destination(router)
    if not router.routeros_username or not router.routeros_password_encrypted:
        raise DiscoveryError("credentials_required")
    try:
        password = secret_store.decrypt(router.routeros_password_encrypted)
    except Exception:
        raise DiscoveryError("credentials_required") from None
    deadline = time.monotonic() + 20
    tables = {}
    with requests.Session() as session:
        session.trust_env = False
        session.verify = getattr(settings, "ROUTER_DISCOVERY_CA_BUNDLE", "") or True
        session.auth = (router.routeros_username, password)
        for name, (path, fields) in TABLES.items():
            tables[name] = read_table(session, f"{base}/{path}", fields, deadline,
                                      optional=name not in ("resource", "interfaces"),
                                      filters={"dst-address": "0.0.0.0/0"} if name == "routes" else None)
    return normalize(tables, router.wireguard_ip)


def normalize(tables, management_ip):
    resource = tables.get("resource") or []
    raw_interfaces = tables.get("interfaces") or []
    if len(resource) != 1 or not raw_interfaces or len(raw_interfaces) > 256:
        raise DiscoveryError("invalid_response")
    model = resource[0].get("board-name", "")
    raw_version = resource[0].get("version", "")
    version = raw_version.split(' ')[0]
    if not model or not re.fullmatch(r"[0-9]+\.[0-9]+(?:\.[0-9]+)?(?:[a-zA-Z0-9.-]*)?", version):
        raise DiscoveryError("invalid_response")
    interfaces = {}
    for row in raw_interfaces:
        name = row.get("name", "")
        if not name or name in interfaces:
            raise DiscoveryError("invalid_response")
        typ = row.get("type", "")
        kind = {"ether":"ethernet", "wlan":"wireless", "wifi":"wireless", "vlan":"vlan", "bonding":"bond"}.get(typ, "other")
        interfaces[name] = {"name": name, "kind": kind, "type": typ, "disabled": row.get("disabled") == "true", "bridge": "", "protected_reasons": []}
    graph = {name: set() for name in interfaces}
    def connect(left, right):
        if left in graph and right in graph:
            graph[left].add(right)
            graph[right].add(left)
    def protect(name, reason):
        if name in interfaces and reason not in interfaces[name]["protected_reasons"]:
            interfaces[name]["protected_reasons"].append(reason)
    for row in tables.get("bridge_ports") or []:
        name, bridge = row.get("interface"), row.get("bridge", "")
        if name in interfaces:
            interfaces[name]["bridge"] = bridge
            connect(name, bridge)
    for row in tables.get("vlans") or []:
        connect(row.get("name"), row.get("interface"))
    for row in tables.get("bonds") or []:
        for slave in row.get("slaves", "").split(','):
            connect(row.get("name"), slave.strip())
    for row in tables.get("members") or []:
        if row.get("list", "").upper() == "WAN":
            protect(row.get("interface"), "wan")
    for row in tables.get("dhcp_clients") or []:
        if row.get("disabled") != "true":
            protect(row.get("interface"), "wan")
    for row in tables.get("routes") or []:
        if row.get("dst-address") == "0.0.0.0/0" and row.get("disabled") != "true":
            gateway = row.get("immediate-gw", row.get("gateway", ""))
            protect(gateway.rsplit('%', 1)[-1], "wan")
    for row in tables.get("addresses") or []:
        if row.get("address", "").split('/')[0] == management_ip:
            protect(row.get("interface"), "management")
    # Conservatively protect the entire connected bridge/VLAN/bond topology of an uplink.
    for origin, item in interfaces.items():
        for reason in list(item["protected_reasons"]):
            pending, seen = [origin], set()
            while pending:
                current = pending.pop()
                if current in seen:
                    continue
                seen.add(current)
                protect(current, reason)
                pending.extend(graph[current] - seen)
    mode = tables.get("device_mode")
    hotspot_allowed = None if not mode or mode[0].get("hotspot") not in ("true", "false", "yes", "no") else mode[0]["hotspot"] in ("true", "yes")
    return {"version": VERSION, "model": model, "routeros_version": version,
            "reported_version": raw_version, "architecture": resource[0].get("architecture-name", ""),
            "addresses": tables.get("addresses") or [],
            "interfaces": list(interfaces.values()), "bridges": tables.get("bridges") or [],
            "packages": tables.get("packages") or [], "hotspots": tables.get("hotspots") or [],
            "hotspot_allowed": hotspot_allowed,
            "unavailable_sections": [key for key in TABLES if tables.get(key) is None]}


def latest_inventory(router):
    event = router.audit_events.filter(action="hotspot.inventory_discovered").first()
    if not event:
        return None
    state = "changed" if event.details["router_version"] != router.updated_at.isoformat() else "stale" if event.created_at < timezone.now() - timedelta(minutes=10) else "current"
    return {"id": str(event.pk), "observed_at": event.created_at,
            "state": state, "source": "routeros_https", **event.details["inventory"]}


def compatibility(router, inventory):
    reasons = []
    if not inventory:
        status = "incomplete" if not router.model or not router.routeros_version else "discovery_required" if router.routeros_version.startswith("7.") else "unsupported"
        reasons.append("Run discovery to confirm the router's model, OS and installed configuration.")
    else:
        version = inventory["routeros_version"]
        if not re.fullmatch(r"7\.[0-9]+(?:\.[0-9]+)?", version):
            reasons.append("The current discovery/review path requires a stable RouterOS 7 release.")
        if inventory["state"] != "current":
            reasons.append("The inventory is stale or the router record changed; discover again.")
        if router.model and router.model.casefold() != inventory["model"].casefold():
            reasons.append("The reported model differs from the registered model. Review the target identity.")
        if router.routeros_version and router.routeros_version != version:
            reasons.append("The reported RouterOS version differs from the registered version.")
        if inventory["unavailable_sections"]:
            reasons.append("Some inventory sections could not be read; topology and feature checks are incomplete.")
        if inventory["hotspot_allowed"] is not True:
            reasons.append("Hotspot device-mode permission is disabled or could not be confirmed.")
        if len(inventory["interfaces"]) > 64:
            reasons.append("This review supports up to 64 interfaces.")
        if any(not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,62}", row["name"]) for row in inventory["interfaces"]):
            reasons.append("Some interface names are outside the current review generator's supported format.")
        if not any("wan" in row["protected_reasons"] for row in inventory["interfaces"]):
            reasons.append("WAN protection could not be established from the inventory.")
        if not any("management" in row["protected_reasons"] for row in inventory["interfaces"]):
            reasons.append("The management interface could not be identified.")
        status = "blocked" if reasons else "unverified"
    if not reasons:
        reasons.append("Inventory checks passed; this model/OS combination still needs a validated executable generator.")
    return {"status": status, "reason": reasons[0], "reasons": reasons,
            "generator": None, "execution_enabled": False}
