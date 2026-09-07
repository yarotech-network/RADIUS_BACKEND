from django.db import transaction
from django.utils import timezone
from .models import Voucher, InternetPlan, PaymentTransaction, Radcheck
import secrets
import string
import hashlib
import requests


class VoucherService:
    """Core voucher operations."""

    @staticmethod
    def write_radius_credentials(voucher):
        Radcheck.objects.create(username=voucher.username, attribute="Cleartext-Password", op=":=", value=voucher.password)
        Radcheck.objects.create(username=voucher.username, attribute="Max-Days", op=":=", value=str(voucher.plan.duration_hours * 3600))
        if voucher.plan.data_limit > 0:
            Radcheck.objects.create(username=voucher.username, attribute="Max-Total-Octets", op=":=", value=str(voucher.plan.data_limit * 1024 * 1024))

    @staticmethod
    @transaction.atomic
    def generate_vouchers(tenant, plan_id, quantity, prefix="", agent=None, source="admin"):
        """Generate vouchers and create RADIUS radcheck rows."""
        if type(quantity) is not int or not 1 <= quantity <= 100:
            raise ValueError("Quantity must be an integer between 1 and 100.")
        if not tenant.is_active or (agent is not None and agent.tenant_id != tenant.pk):
            raise ValueError("Invalid tenant or agent scope.")
        plan = InternetPlan.objects.get(id=plan_id, tenant=tenant, is_active=True)
        vouchers = []

        for _ in range(quantity):
            username, password = Voucher.generate_credentials(prefix)

            # Ensure unique username
            while Voucher.objects.filter(username=username).exists():
                username, password = Voucher.generate_credentials(prefix)

            voucher = Voucher.objects.create(
                username=username,
                password=password,
                plan=plan,
                tenant=tenant,
                agent=agent,
                generation_source=source,
                device_limit=1,
            )

            VoucherService.write_radius_credentials(voucher)

            vouchers.append(voucher)

        return vouchers

    @staticmethod
    def activate_voucher(voucher):
        """Called by FreeRADIUS post-auth to activate voucher."""
        if voucher.status == "unused":
            voucher.activate()
            return True
        return False

    @staticmethod
    @transaction.atomic
    def expire_vouchers():
        """Expire vouchers past their expiration time."""
        now = timezone.now()
        expired = Voucher.objects.filter(
            status="active",
            expires_at__lte=now,
        )
        usernames = list(expired.values_list("username", flat=True))
        count = len(usernames)
        expired.update(status="expired")

        # Disable radcheck rows for expired vouchers
        if usernames:
            Radcheck.objects.filter(username__in=usernames).delete()

        return count

    @staticmethod
    @transaction.atomic
    def disable_voucher(voucher):
        """Manually disable a voucher."""
        voucher.status = "disabled"
        voucher.save(update_fields=["status"])
        Radcheck.objects.filter(username=voucher.username).delete()
        return True


class PaystackService:
    """Paystack payment integration."""

    BASE_URL = "https://api.paystack.co"

    def __init__(self, secret_key):
        self.secret_key = secret_key
        self.headers = {
            "Authorization": f"Bearer {secret_key}",
            "Content-Type": "application/json",
        }

    def initialize_transaction(self, email, amount, reference=None, metadata=None, callback_url=None):
        """Initialize a Paystack transaction."""
        data = {
            "email": email,
            "amount": amount,  # in kobo
            "metadata": metadata or {},
        }
        if reference:
            data["reference"] = reference
        if callback_url:
            data["callback_url"] = callback_url

        response = requests.post(
            f"{self.BASE_URL}/transaction/initialize",
            json=data,
            headers=self.headers,
            timeout=30,
        )
        response.raise_for_status()
        return response.json()

    def verify_transaction(self, reference):
        """Verify a Paystack transaction."""
        response = requests.get(
            f"{self.BASE_URL}/transaction/verify/{reference}",
            headers=self.headers,
            timeout=30,
        )
        response.raise_for_status()
        return response.json()

    def create_customer(self, email, first_name="", last_name="", phone=""):
        """Create a Paystack customer."""
        data = {
            "email": email,
            "first_name": first_name,
            "last_name": last_name,
            "phone": phone,
        }
        response = requests.post(
            f"{self.BASE_URL}/customer",
            json=data,
            headers=self.headers,
            timeout=30,
        )
        response.raise_for_status()
        return response.json()


class RadiusService:
    """FreeRADIUS session management."""

    @staticmethod
    def get_active_sessions(tenant=None):
        """Get active RADIUS sessions."""
        from .models import Radacct
        query = Radacct.objects.filter(acctstoptime__isnull=True)
        if tenant:
            from apps.routers.selectors import tenant_radius_addresses
            query = query.filter(nasipaddress__in=tenant_radius_addresses(tenant))
        return query

    @staticmethod
    def disconnect_session(session_id, nas_ip, nas_port, callingsession_id, shared_secret):
        """Send CoA disconnect to RADIUS server."""
        from django.conf import settings
        from apps.routers.radius_client import RadiusDisconnectClient

        return RadiusDisconnectClient(
            host=nas_ip,
            port=settings.RADIUS_COA_PORT,
            timeout=settings.RADIUS_COA_TIMEOUT,
        ).disconnect(
            session_id=session_id,
            shared_secret=shared_secret,
            nas_port_id=nas_port or "",
            calling_station_id=callingsession_id or "",
        )
