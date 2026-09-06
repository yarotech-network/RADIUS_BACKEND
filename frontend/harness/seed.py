"""Seed users for every role plus a little data. Idempotent."""
import django
django.setup()
from django.contrib.auth import get_user_model
from django.utils import timezone
from datetime import timedelta
from apps.tenants.models import Tenant, TenantMembership, TenantSetting
from apps.vouchers.models import InternetPlan, PaymentTransaction, Radacct, Voucher
from apps.agents.models import AgentProfile, AgentWallet
from apps.accounts.staff_models import StaffAssignment
from apps.routers.models import NASDevice
from apps.routers.secret_store import secret_store
from apps.subscriptions.models import SubscriptionPlan

User = get_user_model()
PW = "Passw0rd!2026"

def user(username, email, **kw):
    u, created = User.objects.get_or_create(username=username, defaults={"email": email, **kw})
    if created:
        u.set_password(PW); u.save()
    return u

platform, _ = Tenant.objects.get_or_create(slug="yarotech", defaults={"name": "Yarotech Platform", "is_platform_admin": True, "email": "ops@yarotech.test"})
wuse, _ = Tenant.objects.get_or_create(slug="wuse-hotspot", defaults={"name": "Wuse Hotspot", "email": "hello@wuse.test", "phone": "+2348011111111", "address": "Wuse 2, Abuja"})
garki, _ = Tenant.objects.get_or_create(slug="garki-net", defaults={"name": "Garki Net", "email": "hi@garki.test", "phone": "+2348022222222"})
for t in (wuse, garki):
    TenantSetting.objects.get_or_create(tenant=t)
# Agent sales prefix their access codes with the tenant setting (see AgentService).
TenantSetting.objects.filter(tenant=wuse, voucher_prefix="").update(voucher_prefix="WH")

admin = user("admin", "admin@yarotech.test", first_name="Platform", last_name="Admin", is_staff=True, is_superuser=True)
TenantMembership.objects.get_or_create(user=admin, defaults={"tenant": platform, "role": "owner"})
owner = user("owner", "owner@wuse.test", first_name="Ada", last_name="Obi", phone="+2348030000001")
TenantMembership.objects.get_or_create(user=owner, defaults={"tenant": wuse, "role": "owner"})
manager = user("manager", "manager@wuse.test", first_name="Musa", last_name="Bello", phone="+2348030000002")
TenantMembership.objects.get_or_create(user=manager, defaults={"tenant": wuse, "role": "manager"})
staff = user("staff", "staff@wuse.test", first_name="Ngozi", last_name="Eze", phone="+2348030000003")
TenantMembership.objects.get_or_create(user=staff, defaults={"tenant": wuse, "role": "staff"})
garki_owner = user("garki", "owner@garki.test", first_name="Tunde", last_name="Ade")
TenantMembership.objects.get_or_create(user=garki_owner, defaults={"tenant": garki, "role": "owner"})

pstaff = user("pstaff", "pstaff@yarotech.test", first_name="Kemi", last_name="Support")
StaffAssignment.objects.get_or_create(user=pstaff, tenant=wuse, defaults={"services": ["routers.view", "routers.test", "live_sessions.view", "vouchers.print", "vouchers.generate"], "is_active": True})
StaffAssignment.objects.get_or_create(user=pstaff, tenant=garki, defaults={"services": ["payments.view", "payments.support"], "is_active": True})
pstaff_single = user("pstaff1", "pstaff1@yarotech.test", first_name="Single", last_name="Tenant")
StaffAssignment.objects.get_or_create(user=pstaff_single, tenant=wuse, defaults={"services": ["routers.view"], "is_active": True})

agent_user = user("agent", "agent@wuse.test", first_name="Chidi", last_name="Okafor", phone="+2348040000001")
agent, _ = AgentProfile.objects.get_or_create(user=agent_user, defaults={"tenant": wuse, "phone": "+2348040000001", "shop_name": "Chidi Phones", "status": "active", "commission_rate": "10.00"})
AgentWallet.objects.get_or_create(agent=agent, defaults={"balance": 250_000})
pending_agent_user = user("agent2", "agent2@wuse.test", first_name="Pending", last_name="Agent")
AgentProfile.objects.get_or_create(user=pending_agent_user, defaults={"tenant": wuse, "phone": "+2348040000002", "shop_name": "Waiting Shop", "status": "pending"})

nobody = user("nobody", "nobody@example.test", first_name="No", last_name="Role")

plans = []
for name, price, hours, rate, data in [("Daily 1GB", 50_000, 24, "5M/10M", 1024), ("Weekly Unlimited", 250_000, 168, "10M/20M", 0), ("Monthly 20GB", 800_000, 720, "20M/50M", 20480)]:
    p, _ = InternetPlan.objects.get_or_create(tenant=wuse, name=name, defaults={"price": price, "duration_hours": hours, "rate_limit": rate, "data_limit": data, "voucher_prefix": "WH"})
    plans.append(p)
InternetPlan.objects.get_or_create(tenant=garki, name="Garki Daily", defaults={"price": 40_000, "duration_hours": 24, "rate_limit": "3M/5M", "data_limit": 512})

if not Voucher.objects.filter(tenant=wuse).exists():
    for i in range(35):
        plan = plans[i % 3]
        status = ["unused", "active", "expired", "disabled"][i % 4]
        Voucher.objects.create(tenant=wuse, plan=plan, username=f"WH{10000 + i}", password=f"pw{1000 + i}", status=status,
                               generation_source="admin", expires_at=(timezone.now() + timedelta(hours=plan.duration_hours)) if status == "active" else None,
                               activated_at=timezone.now() - timedelta(hours=1) if status in ("active", "expired") else None)

# Storefront purchases in every state the payments / recovery / result-page tests look at.
if not PaymentTransaction.objects.filter(tenant=wuse).exists():
    daily = plans[0]
    legacy_voucher = Voucher.objects.create(tenant=wuse, plan=daily, username="2ju2AUqb", password="k9Fj2LqPz3Xy", status="unused", generation_source="customer")
    PaymentTransaction.objects.create(tenant=wuse, plan=daily, reference="PAY-FULFILLED-001", amount=daily.price, customer_email="fulfilled@example.com", status="success", verified_at=timezone.now() - timedelta(days=1), paid_at=timezone.now() - timedelta(days=1), voucher=legacy_voucher)
    PaymentTransaction.objects.create(tenant=wuse, plan=daily, reference="PAY-UNFULFILLED-002", amount=daily.price, customer_email="unfulfilled@example.com", status="pending", verified_at=timezone.now() - timedelta(hours=2))
    PaymentTransaction.objects.create(tenant=wuse, plan=daily, reference="PAY-PENDING-003", amount=daily.price, customer_email="pending@example.com", status="pending")
    PaymentTransaction.objects.create(tenant=wuse, plan=daily, reference="PAY-FAILED-004", amount=daily.price, customer_email="failed@example.com", status="failed")
    PaymentTransaction.objects.create(tenant=wuse, plan=plans[1], reference="PAY-ABANDONED-005", amount=plans[1].price, customer_email="abandoned@example.com", status="abandoned")
    # Single-code purchase (username == password) whose code the public result endpoint still reveals.
    code = Voucher.generate_access_code()
    code_voucher = Voucher.objects.create(tenant=wuse, plan=daily, username=code, password=code, status="unused", generation_source="customer")
    PaymentTransaction.objects.create(tenant=wuse, plan=daily, reference="PAY-FULFILLED-CODE-001", amount=daily.price, customer_email="code@example.com", status="success", verified_at=timezone.now() - timedelta(hours=1), paid_at=timezone.now() - timedelta(hours=1), voucher=code_voucher)

NASDevice.objects.get_or_create(tenant=wuse, name="mikrotik-wuse-01", defaults={"ip_address": "10.100.100.12", "nas_secret": secret_store.encrypt("testing-shared-secret"), "location": "Wuse 2, Abuja", "onboarding_state": "active", "deployment_status": "deployed", "routeros_username": "admin"})
NASDevice.objects.get_or_create(tenant=wuse, name="mikrotik-wuse-02", defaults={"ip_address": "10.100.100.13", "nas_secret": secret_store.encrypt("testing-shared-secret"), "location": "Jabi", "onboarding_state": "waiting_for_vpn"})
# Live sessions come from the unmanaged FreeRADIUS accounting table; two open sessions on router 01.
if not Radacct.objects.exists():
    for i, (username, minutes) in enumerate([("WH10002", 42), ("WH10006", 7)]):
        Radacct.objects.create(sessionid=f"8160000{i}", username=username, nasipaddress="10.100.100.12", nasportid=f"ether{i + 1}",
                               acctstarttime=timezone.now() - timedelta(minutes=minutes), acctinputoctets=12_500_000 * (i + 1), acctoutputoctets=180_000_000 * (i + 1), acctsessiontime=minutes * 60)
SubscriptionPlan.objects.get_or_create(name="Starter", defaults={"price": 1_500_000, "duration_days": 30, "features": ["1 router", "Unlimited vouchers"], "is_active": True})
SubscriptionPlan.objects.get_or_create(name="Business", defaults={"price": 4_500_000, "duration_days": 30, "features": ["5 routers", "Agents", "WhatsApp delivery"], "is_active": True})
print("seeded. password for all users:", PW)
print("users:", list(User.objects.values_list("username", flat=True)))
