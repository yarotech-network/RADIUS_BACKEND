"""Review-only Hotspot intents. No credentials or executable deployment is issued here."""
import hashlib
import ipaddress
import json
import re
from datetime import timedelta

from django.utils import timezone
from rest_framework import serializers

from .models import RouterAuditEvent
from .discovery import latest_inventory, compatibility

VERSION = "hotspot-review-v1"
REQUIRED_CHECKS = ("wireguard_peer", "radius_auth", "radius_acct")
NAME = r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,62}$"


class StrictSerializer(serializers.Serializer):
    def to_internal_value(self, data):
        if isinstance(data, dict) and set(data) - set(self.fields):
            raise serializers.ValidationError({"non_field_errors": ["Unknown fields are not accepted."]})
        return super().to_internal_value(data)


class InterfaceSerializer(StrictSerializer):
    name = serializers.RegexField(NAME)
    kind = serializers.ChoiceField(choices=["ethernet", "wireless", "vlan", "bond", "other"])
    role = serializers.ChoiceField(choices=["wan", "management", "client", "unused"])
    bridge = serializers.RegexField(NAME, allow_blank=True, required=False, default="")


class HotspotIntentSerializer(StrictSerializer):
    expected_updated_at = serializers.DateTimeField()
    inventory_id = serializers.UUIDField(required=False, allow_null=True, default=None)
    model = serializers.RegexField(r"^[A-Za-z0-9][A-Za-z0-9 +_.-]{0,79}$")
    routeros_version = serializers.RegexField(r"^7\.\d+(?:\.\d+)?(?:[a-zA-Z0-9.-]*)?$")
    service = serializers.ChoiceField(choices=["hotspot"])
    mode = serializers.ChoiceField(choices=["fresh", "existing"])
    bridge = serializers.RegexField(NAME)
    hotspot_name = serializers.RegexField(NAME)
    profile_name = serializers.RegexField(NAME)
    gateway = serializers.CharField(max_length=32)
    radius_server = serializers.IPAddressField(protocol="IPv4")
    interfaces = InterfaceSerializer(many=True, min_length=2, max_length=64)
    inventory_confirmed = serializers.BooleanField()

    def validate(self, data):
        if not data["inventory_confirmed"]:
            raise serializers.ValidationError({"inventory_confirmed": "Confirm the inventory against this router before reviewing."})
        ports = data["interfaces"]
        names = [p["name"] for p in ports]
        if len(names) != len(set(names)):
            raise serializers.ValidationError({"interfaces": "Interface names must be unique."})
        if any(p["name"] == data["bridge"] and p["role"] == "client" for p in ports):
            raise serializers.ValidationError({"bridge": "A bridge cannot also be a client port."})
        if not any(p["role"] == "wan" for p in ports) or not any(p["role"] == "management" for p in ports):
            raise serializers.ValidationError({"interfaces": "Identify separate WAN and management interfaces."})
        clients = [p for p in ports if p["role"] == "client"]
        if not clients:
            raise serializers.ValidationError({"interfaces": "Select at least one client interface."})
        if any(p["role"] in ("wan", "management") and p["bridge"] == data["bridge"] for p in ports):
            raise serializers.ValidationError({"bridge": "The Hotspot bridge must not contain WAN or management interfaces."})
        if data["mode"] == "fresh" and any(p["bridge"] for p in clients):
            raise serializers.ValidationError({"interfaces": "Fresh setup requires unbridged client ports. Use an existing bridge review instead."})
        if data["mode"] == "existing" and any(p["bridge"] != data["bridge"] for p in clients):
            raise serializers.ValidationError({"interfaces": "Every selected client must already belong to the target bridge for migration review."})
        try:
            gateway = ipaddress.IPv4Interface(data["gateway"])
            if gateway.network.prefixlen < 16 or gateway.network.prefixlen > 29 or gateway.ip in (gateway.network.network_address, gateway.network.broadcast_address):
                raise ValueError()
            if not any(gateway.ip in ipaddress.IPv4Network(cidr) for cidr in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16")):
                raise ValueError()
        except ValueError:
            raise serializers.ValidationError({"gateway": "Use a private IPv4 host and prefix between /16 and /29, for example 10.40.0.1/24."})
        data["gateway"] = str(gateway)
        inventory_id = data.get("inventory_id")
        if inventory_id:
            router = self.context.get("router")
            observed = latest_inventory(router) if router else None
            if not observed or str(inventory_id) != observed["id"] or observed["state"] != "current":
                raise serializers.ValidationError({"inventory_id": "Discover again and use the latest current inventory."})
            if data["model"] != observed["model"] or data["routeros_version"] != observed["routeros_version"]:
                raise serializers.ValidationError({"model": "The model and OS must match the selected discovery snapshot."})
            if data["mode"] == "fresh" and any(p.get("name") == data["bridge"] for p in observed["bridges"]):
                raise serializers.ValidationError({"bridge": "Fresh setup cannot reuse an existing observed bridge."})
            known = {p["name"]: p for p in observed["interfaces"]}
            for port in ports:
                item = known.get(port["name"])
                if not item or port["kind"] != item["kind"] or port["bridge"] != item["bridge"]:
                    raise serializers.ValidationError({"interfaces": "Interface names, types and bridge membership must match discovery."})
                if item["protected_reasons"] and port["role"] == "client":
                    raise serializers.ValidationError({"interfaces": "An observed WAN or management interface cannot become a client port."})
                if port["role"] == "client" and (item["disabled"] or item["type"] in ("bridge", "wireguard") or not re.fullmatch(NAME, item["name"])):
                    raise serializers.ValidationError({"interfaces": "A disabled or unsupported interface cannot become a client port."})
            if any(p["protected_reasons"] and p["name"] not in names for p in observed["interfaces"]):
                raise serializers.ValidationError({"interfaces": "Keep all observed WAN and management interfaces in the review."})
            data["inventory_id"] = str(inventory_id)
        return data


def candidate(data):
    """All candidate commands are comments; the first statement aborts pasted/imported files."""
    commands = []
    bridge = data["bridge"]
    if data["mode"] == "fresh":
        commands.append(f'/interface bridge add name="{bridge}" comment="Yarotech Hotspot"')
        commands.extend(f'/interface bridge port add bridge="{bridge}" interface="{p["name"]}"' for p in data["interfaces"] if p["role"] == "client")
        commands.append(f'/ip address add address="{data["gateway"]}" interface="{bridge}"')
        commands.append(f'/ip hotspot profile add name="{data["profile_name"]}" use-radius=yes radius-accounting=yes')
        commands.append(f'/ip hotspot add name="{data["hotspot_name"]}" interface="{bridge}" profile="{data["profile_name"]}" disabled=yes')
    else:
        commands.append(f'/ip hotspot profile set [find where name="{data["profile_name"]}"] use-radius=yes radius-accounting=yes')
    return '\n'.join([
        ':error "REVIEW ONLY: this artifact is not an executable installation or migration"',
        f'# Generator: {VERSION}',
        '# Candidate changes only. DHCP, DNS, firewall/NAT, RADIUS secrets, device-mode,',
        '# inventory preconditions, idempotent execution and rollback require lab validation.',
        '# No credentials are included. Do not remove this guard to deploy.',
        *["# " + command for command in commands],
        f'# RADIUS destination to validate: {data["radius_server"]}',
    ])


def save_intent(router, values, actor_id):
    data = {k: v for k, v in values.items() if k != "expected_updated_at"}
    digest = hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()
    # Router is locked by the caller, so concurrent identical reviews reuse one record.
    latest = router.audit_events.filter(action="hotspot.intent_created").first()
    if latest and latest.details.get("digest") == digest and latest.details.get("router_version") == router.updated_at.isoformat() and valid_intent(router, latest):
        return latest
    return RouterAuditEvent.objects.create(router=router, action="hotspot.intent_created", details={
        "version": VERSION, "digest": digest, "intent": data,
        "router_version": router.updated_at.isoformat(), "actor_id": actor_id,
    })


def valid_intent(router, event):
    return event.created_at + timedelta(hours=1) > timezone.now() and not router.audit_events.filter(action="hotspot.intent_revoked", details__intent_id=str(event.pk)).exists()


def setup_result(router):
    event = router.audit_events.filter(action="hotspot.intent_created").first()
    intent = None
    if event:
        revoked = router.audit_events.filter(action="hotspot.intent_revoked", details__intent_id=str(event.pk)).exists()
        expired = event.created_at + timedelta(hours=1) <= timezone.now()
        observed = latest_inventory(router)
        inventory_id = event.details["intent"].get("inventory_id")
        stale = event.details["router_version"] != router.updated_at.isoformat() or bool(inventory_id and (not observed or observed["id"] != inventory_id or observed["state"] != "current"))
        state = "revoked" if revoked else "expired" if expired else "stale" if stale else "review"
        intent = {
            "id": str(event.pk), "version": event.details["version"], "state": state,
            "created_at": event.created_at, "expires_at": min(event.created_at + timedelta(hours=1), observed["observed_at"] + timedelta(minutes=10)) if inventory_id and observed and observed["id"] == inventory_id else event.created_at + timedelta(hours=1),
            "configuration": event.details["intent"],
            "script_preview": candidate(event.details["intent"]) if state == "review" else None,
        }
    checks = {c.check_type: c for c in router.onboarding_checks.filter(check_type__in=REQUIRED_CHECKS)}
    evidence = []
    for kind in REQUIRED_CHECKS:
        check = checks.get(kind)
        fresh = bool(check and event and check.checked_at >= event.created_at and timezone.now() - timedelta(minutes=10) <= check.checked_at <= timezone.now())
        evidence.append({"check_type": kind, "passed": bool(check and check.passed and fresh), "checked_at": check.checked_at if check else None, "fresh": fresh})
    observed = latest_inventory(router)
    return {"device_profile": {"model": router.model, "routeros_version": router.routeros_version},
            "discovery": observed, "compatibility": compatibility(router, observed),
            "version": VERSION, "execution_enabled": False, "supported_targets": [],
            "gate": "Production execution requires hardware validation. Fresh-install laboratory packages are available separately.",
            "inventory_source": "routeros_https" if intent and intent["configuration"].get("inventory_id") else "operator_confirmed", "intent": intent, "evidence": evidence,
            "ready": False}
