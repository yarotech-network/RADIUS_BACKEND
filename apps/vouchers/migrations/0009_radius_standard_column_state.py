from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('vouchers', '0008_paymenttransaction_customer_voucher_customer')]
    operations = [migrations.SeparateDatabaseAndState(database_operations=[], state_operations=[
        migrations.AlterField(model_name='radacct', name='sessionid', field=models.CharField(max_length=64, db_column='acctsessionid')),
        migrations.AlterField(model_name='radpostauth', name='pass_reply', field=models.CharField(max_length=64, db_column='reply')),
    ])]
