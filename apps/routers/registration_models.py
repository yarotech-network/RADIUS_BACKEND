from django.db import models


class RouterRegistration(models.Model):
    router = models.OneToOneField('routers.NASDevice', on_delete=models.CASCADE, related_name='registration')
    nas_identifier = models.CharField(max_length=120)
    hotspot_interface = models.CharField(max_length=64)
    hotspot_profile = models.CharField(max_length=64)
    notes = models.TextField(blank=True)
    setup = models.JSONField(default=dict)
    private_key_encrypted = models.TextField()
    script_encrypted = models.TextField(blank=True)
    script_sha256 = models.CharField(max_length=64, blank=True)
    status = models.CharField(max_length=30, default='needs_attention')
    error_code = models.CharField(max_length=100, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'routers_registration'
