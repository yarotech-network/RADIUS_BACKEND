"""Purchase contacts are independent records, never email-based identities."""
import uuid
from django.db import transaction
from .models import Customer


@transaction.atomic
def create_purchase_payment(**values):
    from apps.vouchers.models import PaymentTransaction
    if 'customer' in values or 'customer_id' in values:
        raise ValueError('Purchase contacts are assigned by the server.')
    tenant_id = values.get('tenant_id') or values['tenant'].pk
    customer = Customer.objects.create(tenant_id=tenant_id, reference='P-'+uuid.uuid4().hex.upper(),
        name=values.get('customer_name') or '', email=values.get('customer_email') or '',
        phone=values.get('customer_phone') or '')
    return PaymentTransaction.objects.create(customer=customer, **values)
