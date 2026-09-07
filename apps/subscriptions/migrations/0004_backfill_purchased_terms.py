from django.db import migrations


def backfill(apps, schema_editor):
    Plan = apps.get_model("subscriptions", "SubscriptionPlan")
    Payment = apps.get_model("subscriptions", "SubscriptionPayment")
    Subscription = apps.get_model("subscriptions", "TenantSubscription")
    Period = apps.get_model("subscriptions", "SubscriptionPeriod")
    alias = schema_editor.connection.alias
    for plan in Plan.objects.using(alias).iterator(chunk_size=200):
        terms = {field: getattr(plan, field) for field in ("name", "price", "duration_days", "max_routers", "daily_voucher_print_limit", "whatsapp_enabled", "version")}
        for payment in Payment.objects.using(alias).filter(plan=plan, plan_terms__isnull=True).iterator(chunk_size=200):
            Payment.objects.using(alias).filter(pk=payment.pk).update(plan_terms={**terms, "price": payment.amount})
        for subscription in Subscription.objects.using(alias).filter(plan=plan).iterator(chunk_size=200):
            if subscription.expires_at > subscription.started_at:
                Period.objects.using(alias).create(tenant_id=subscription.tenant_id, plan_id=plan.pk, starts_at=subscription.started_at, ends_at=subscription.expires_at, terms=terms)


class Migration(migrations.Migration):
    dependencies = [("subscriptions", "0003_subscriptionpayment_plan_terms_and_more")]
    operations = [migrations.RunPython(backfill, migrations.RunPython.noop)]
