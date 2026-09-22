"""Allowlisted commissioning context carried only by authenticated bootstrap.

Routing is not construction configuration. In particular browser principals,
parent session keys and server-history wake authority never cross this boundary.
"""
SESSION_FIELDS = ('platform', 'source', 'chat_id', 'chat_type', 'chat_name',
    'thread_id', 'user_id', 'user_id_alt', 'user_name', 'scope_id', 'message_id',
    'profile', 'parent_chat_id')
DELIVERY_FIELDS = ('platform', 'chat_id', 'thread_id')


def validate(context):
    if not isinstance(context, dict) or set(context) != {'session', 'delivery', 'async_delivery'}:
        raise ValueError('invalid isolated routing context')
    if type(context['async_delivery']) is not bool:
        raise ValueError('invalid isolated delivery capability')
    for section, fields in (('session', SESSION_FIELDS), ('delivery', DELIVERY_FIELDS)):
        values = context[section]
        if not isinstance(values, dict) or set(values) != set(fields):
            raise ValueError('invalid isolated routing fields')
        if any(not isinstance(v, str) or len(v.encode('utf-8')) > 4096 or '\x00' in v
               for v in values.values()):
            raise ValueError('invalid isolated routing value')
    return context


def capture():
    from gateway.session_context import get_session_env, async_delivery_supported
    return validate({
        'session': {key: get_session_env('HERMES_SESSION_' + key.upper()) for key in SESSION_FIELDS},
        'delivery': {key: get_session_env('HERMES_CRON_AUTO_DELIVER_' + key.upper()) for key in DELIVERY_FIELDS},
        'async_delivery': async_delivery_supported(),
    })


def install(context):
    from gateway.session_context import _VAR_MAP, _SESSION_ASYNC_DELIVERY
    context = validate(context)
    # Approval installation owns cron/unattended flags; do not reset them here.
    for section, prefix in (('session', 'HERMES_SESSION_'), ('delivery', 'HERMES_CRON_AUTO_DELIVER_')):
        for key, value in context[section].items():
            _VAR_MAP[prefix + key.upper()].set(value)
    _SESSION_ASYNC_DELIVERY.set(context['async_delivery'])
