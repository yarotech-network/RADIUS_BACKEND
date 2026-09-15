from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('vouchers', '0009_radius_standard_column_state')]
    operations = [migrations.SeparateDatabaseAndState(database_operations=[], state_operations=[
        migrations.AddField(model_name='radacct', name='acctupdatetime',
                            field=models.DateTimeField(null=True, blank=True)),
    ])]
