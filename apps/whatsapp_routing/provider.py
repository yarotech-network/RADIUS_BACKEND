"""Fixed-host Meta adapter. Call only outside database transactions."""
import re
import requests
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.views.decorators.debug import sensitive_variables
from apps.routers.secret_store import secret_store


class ProviderFailure(Exception):
    def __init__(self, code, *, retryable=False, ambiguous=False):
        self.code, self.retryable, self.ambiguous = code, retryable, ambiguous
        super().__init__(code)


def api_url(phone_id, suffix=''):
    version = getattr(settings, 'WHATSAPP_GRAPH_VERSION', '')
    if not re.fullmatch(r'v[0-9]{1,3}\.0', version) or not re.fullmatch(r'[0-9]{1,100}', phone_id):
        raise ImproperlyConfigured('Configure a supported WHATSAPP_GRAPH_VERSION and phone ID.')
    return f'https://graph.facebook.com/{version}/{phone_id}{suffix}'


@sensitive_variables()
def verify_endpoint(endpoint):
    token = secret_store.decrypt(endpoint.access_token_encrypted)
    if not token:
        raise ProviderFailure('token_missing')
    try:
        response = requests.get(api_url(endpoint.phone_number_id),
            params={'fields': 'id,display_phone_number,verified_name,code_verification_status'},
            headers={'Authorization': f'Bearer {token}'}, timeout=(5, 15), allow_redirects=False)
        if response.status_code != 200:
            raise ProviderFailure('meta_rejected_verification')
        data = response.json()
        if not isinstance(data, dict) or str(data.get('id')) != endpoint.phone_number_id:
            raise ProviderFailure('phone_id_mismatch')
        display = data.get('display_phone_number')
        if not isinstance(display, str) or re.sub(r'\D', '', display) != endpoint.display_number.lstrip('+'):
            raise ProviderFailure('public_number_mismatch')
        if data.get('code_verification_status') != 'VERIFIED':
            raise ProviderFailure('phone_not_verified')
    except requests.RequestException as exc:
        raise ProviderFailure('meta_unavailable') from exc
    except (ValueError, TypeError) as exc:
        raise ProviderFailure('invalid_meta_response') from exc


@sensitive_variables()
def send_payload(endpoint, payload):
    if getattr(settings, 'STAGING_MODE', False):
        allowed = {re.sub(r'\D', '', value) for value in getattr(settings, 'STAGING_WHATSAPP_RECIPIENTS', [])}
        allowed.discard('')
        if re.sub(r'\D', '', str(payload.get('to', ''))) not in allowed:
            raise ProviderFailure('staging_recipient_not_allowed')
    try:
        response = requests.post(api_url(endpoint.phone_number_id, '/messages'), json=payload,
            headers={'Authorization': f'Bearer {secret_store.decrypt(endpoint.access_token_encrypted)}'},
            timeout=(5, 20), allow_redirects=False)
    except requests.ConnectTimeout as exc:
        raise ProviderFailure('meta_connect_timeout', retryable=True) from exc
    except requests.RequestException as exc:
        raise ProviderFailure('meta_outcome_unknown', ambiguous=True) from exc
    if response.status_code == 429:
        raise ProviderFailure('meta_rate_limited', retryable=True)
    if response.status_code >= 500 or response.status_code == 408:
        raise ProviderFailure('meta_outcome_unknown', ambiguous=True)
    if response.status_code not in (200, 201):
        raise ProviderFailure('meta_message_rejected')
    try:
        message_id = response.json()['messages'][0]['id']
        if not isinstance(message_id, str) or not 1 <= len(message_id) <= 512:
            raise ValueError()
        return message_id
    except (ValueError, TypeError, KeyError, IndexError) as exc:
        raise ProviderFailure('meta_outcome_unknown', ambiguous=True) from exc
