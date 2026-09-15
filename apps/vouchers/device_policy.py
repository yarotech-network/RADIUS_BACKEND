from django.conf import settings
from rest_framework import serializers


def max_new_devices():
    return 10 if getattr(settings, 'MULTI_DEVICE_VOUCHERS_ENABLED', False) else 1


class NewDeviceCountField(serializers.IntegerField):
    def __init__(self, **kwargs):
        super().__init__(min_value=1, max_value=10, default=1, **kwargs)

    def to_internal_value(self, data):
        if isinstance(data, bool) or isinstance(data, float):
            self.fail('invalid')
        value = super().to_internal_value(data)
        if value > max_new_devices():
            raise serializers.ValidationError('Multiple devices are not enabled for new purchases or batches.')
        return value
