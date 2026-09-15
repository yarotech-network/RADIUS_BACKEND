import hashlib
import hmac
import logging
import re
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured, RequestDataTooBig
from django.db import DatabaseError
from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.debug import sensitive_variables
from django.views.decorators.http import require_http_methods
from .inbox import MAX_BODY, InvalidEnvelope, accept_events, parse_events

logger = logging.getLogger(__name__)


def webhook_configured():
    return bool(getattr(settings, 'WHATSAPP_APP_SECRET', '') and getattr(settings, 'WHATSAPP_WEBHOOK_VERIFY_TOKEN', ''))


def unavailable():
    response = JsonResponse({'error': 'WhatsApp webhook is temporarily unavailable.'}, status=503)
    response['Retry-After'] = '60'
    return response


@csrf_exempt  # Provider authentication is the raw-body signature, never a browser session.
@require_http_methods(['GET', 'POST'])
@sensitive_variables()
def whatsapp_webhook(request):
    if not getattr(settings, 'WHATSAPP_WEBHOOK_ENABLED', False) or not webhook_configured():
        return unavailable()
    if request.method == 'GET':
        supplied = request.GET.get('hub.verify_token', '')
        expected = settings.WHATSAPP_WEBHOOK_VERIFY_TOKEN
        challenge = request.GET.get('hub.challenge', '')
        if (request.GET.get('hub.mode') != 'subscribe' or not re.fullmatch(r'[0-9]{1,256}', challenge)
            or not hmac.compare_digest(supplied.encode('utf-8'), expected.encode('utf-8'))):
            return JsonResponse({'error': 'Invalid verification request.'}, status=403)
        response = HttpResponse(challenge, content_type='text/plain')
        response['Cache-Control'] = 'no-store'
        return response
    try:
        length = int(request.META.get('CONTENT_LENGTH') or 0)
        if length < 0 or length > MAX_BODY:
            return JsonResponse({'error': 'Webhook body too large.'}, status=413)
        raw = request.read(MAX_BODY + 1)
        if len(raw) > MAX_BODY:
            return JsonResponse({'error': 'Webhook body too large.'}, status=413)
    except RequestDataTooBig:
        return JsonResponse({'error': 'Webhook body too large.'}, status=413)
    except ValueError:
        return JsonResponse({'error': 'Invalid content length.'}, status=400)
    signature = request.headers.get('X-Hub-Signature-256', '')
    expected = 'sha256=' + hmac.new(settings.WHATSAPP_APP_SECRET.encode('utf-8'), raw, hashlib.sha256).hexdigest()
    if not re.fullmatch(r'sha256=[0-9a-f]{64}', signature) or not hmac.compare_digest(signature, expected):
        return JsonResponse({'error': 'Invalid signature.'}, status=403)
    try:
        events = parse_events(raw)
    except InvalidEnvelope:
        return JsonResponse({'error': 'Invalid WhatsApp envelope.'}, status=400)
    try:
        result = accept_events(events)
    except (DatabaseError, ImproperlyConfigured):
        logger.warning('whatsapp_inbox_unavailable')
        return unavailable()
    logger.info('whatsapp_inbox_receipt received=%s duplicates=%s conflicts=%s ignored=%s',
        result['received'], result['duplicates'], result['conflicts'], result['ignored'])
    return JsonResponse(result)
