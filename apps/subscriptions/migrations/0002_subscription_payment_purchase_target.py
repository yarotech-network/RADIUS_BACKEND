import django.db.models.deletion
from django.db import migrations, models


def backfill_purchase_targets(apps, schema_editor):
    SubscriptionPayment = apps.get_model("subscriptions", "SubscriptionPayment")
    for payment in SubscriptionPayment.objects.select_related("subscription").iterator():
        payment.tenant_id = payment.subscription.tenant_id
        payment.plan_id = payment.subscription.plan_id
        payment.save(update_fields=["tenant", "plan"])


class Migration(migrations.Migration):
    dependencies = [
        ("subscriptions", "0001_initial"),
        ("tenants", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="subscriptionpayment",
            name="tenant",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="subscription_payments",
                to="tenants.tenant",
            ),
        ),
        migrations.AddField(
            model_name="subscriptionpayment",
            name="plan",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="payments",
                to="subscriptions.subscriptionplan",
            ),
        ),
        migrations.RunPython(backfill_purchase_targets, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="subscriptionpayment",
            name="tenant",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="subscription_payments",
                to="tenants.tenant",
            ),
        ),
        migrations.AlterField(
            model_name="subscriptionpayment",
            name="plan",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="payments",
                to="subscriptions.subscriptionplan",
            ),
        ),
        migrations.AlterField(
            model_name="subscriptionpayment",
            name="subscription",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="payments",
                to="subscriptions.tenantsubscription",
            ),
        ),
        migrations.AlterField(
            model_name="subscriptionpayment",
            name="status",
            field=models.CharField(
                choices=[
                    ("pending", "Pending"),
                    ("success", "Success"),
                    ("failed", "Failed"),
                ],
                default="pending",
                max_length=20,
            ),
        ),
    ]
