from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [('routers', '0005_router_hardware_profile')]
    operations = [migrations.CreateModel(
        name='RouterRegistration',
        fields=[
            ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
            ('nas_identifier', models.CharField(max_length=120)),
            ('hotspot_interface', models.CharField(max_length=64)),
            ('hotspot_profile', models.CharField(max_length=64)),
            ('notes', models.TextField(blank=True)),
            ('setup', models.JSONField(default=dict)),
            ('private_key_encrypted', models.TextField()),
            ('script_encrypted', models.TextField(blank=True)),
            ('script_sha256', models.CharField(max_length=64, blank=True)),
            ('status', models.CharField(default='needs_attention', max_length=30)),
            ('error_code', models.CharField(blank=True, max_length=100)),
            ('created_at', models.DateTimeField(auto_now_add=True)),
            ('updated_at', models.DateTimeField(auto_now=True)),
            ('router', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='registration', to='routers.nasdevice')),
        ], options={'db_table': 'routers_registration'},
    )]
