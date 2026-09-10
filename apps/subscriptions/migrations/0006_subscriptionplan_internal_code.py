from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('subscriptions', '0005_subscriptionperiod_superseded')]

    operations = [
        migrations.AddField(
            model_name='subscriptionplan', name='internal_code',
            field=models.CharField(max_length=64, null=True, blank=True, unique=True, editable=False),
        ),
    ]
