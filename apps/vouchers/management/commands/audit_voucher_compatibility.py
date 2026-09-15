"""Read-only target preflight: IDs and issue codes, never voucher credentials."""
import json
from collections import Counter
from django.core.management.base import BaseCommand
from apps.vouchers.models import Voucher


class Command(BaseCommand):
    help = 'Report voucher lifecycle records needing review without changing records.'

    def handle(self, *args, **options):
        counts = Counter()
        samples = []
        total = 0
        for v in Voucher.objects.order_by('pk').iterator(chunk_size=500):
            total += 1
            issues = []
            consumed = v.is_used or v.first_used_at or v.activated_at or v.used_at or v.last_used_at or v.status in ('active', 'used')
            if consumed and v.expires_at is None:
                issues.append('consumed_without_deadline')
            if v.status not in dict(Voucher.STATUS_CHOICES):
                issues.append('unknown_state')
            if v.bound_device_mac and (not v.device_lock_enabled or not v.device_bound_at or not v.device_bound_nas_id):
                issues.append('incomplete_device_binding')
            if not 1 <= v.device_limit <= 10:
                issues.append('invalid_device_limit')
            if v.legacy_provenance and (not isinstance(v.legacy_provenance, dict) or v.legacy_provenance.get('requires_review')):
                issues.append('import_review_required')
            counts.update(issues)
            if issues and len(samples) < 100:
                samples.append({'voucher_id':v.pk, 'tenant_id':v.tenant_id, 'issues':issues})
        self.stdout.write(json.dumps({'total':total, 'issue_counts':dict(counts), 'samples':samples, 'sample_limit':100}, sort_keys=True))
