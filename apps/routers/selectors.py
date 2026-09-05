from django.db.models import Q
from .models import NASDevice


def tenant_radius_addresses(tenant):
    """Never assign accounting rows to a tenant when the NAS address is ambiguous."""
    addresses = {
        str(address)
        for pair in NASDevice.objects.filter(tenant=tenant).values_list("ip_address", "wireguard_ip")
        for address in pair if address is not None
    }
    matching_addresses = NASDevice.objects.filter(
        Q(ip_address__in=addresses) | Q(wireguard_ip__in=addresses)
    ).values_list("ip_address", "wireguard_ip")
    counts = {address: 0 for address in addresses}
    for pair in matching_addresses:
        for address in {str(value) for value in pair if value is not None}:
            if address in counts:
                counts[address] += 1
    return {address for address, count in counts.items() if count == 1}
