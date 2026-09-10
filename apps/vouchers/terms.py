def snapshot_plan(plan):
    """Capture server-owned terms and the existing speed-enforcement mode."""
    terms = {field: getattr(plan, field) for field in (
        'name', 'price', 'duration_hours', 'data_limit', 'rate_limit',
    )}
    profile = plan.bandwidth_profile
    return {
        **terms, 'version': 1, 'tenant_id': plan.tenant_id, 'plan_id': plan.pk,
        'radius_rate_limit': plan.rate_limit if profile and profile.rate_limit == plan.rate_limit else '',
    }
