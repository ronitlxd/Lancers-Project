"""
lancer_project/audit.py

Audit logging for actions that touch personal or clinical data.

UWindsor IT review finding 7: the application lacked auditability controls.
IT Services' response (section 1.7) set the design: write significant audit
events to standard error, timestamped, using the Python logging configuration.
Kubernetes captures stderr and the platform pipeline forwards it to the
University SIEM, so the application needs no SIEM client of its own.

Each event is emitted as a single JSON object on one line, which is what makes
it parseable at the other end.  Never put credentials, free-text clinical notes
or photograph contents in an audit entry: the log travels further than the
database does.
"""

import json
import logging
from datetime import datetime, timezone

logger = logging.getLogger('lancerspulse.audit')


def _client_ip(request):
    """Best-effort client address.

    Behind the campus Gateway the real client address arrives in
    X-Forwarded-For; REMOTE_ADDR would be the proxy.
    """
    if request is None:
        return None
    forwarded = request.META.get('HTTP_X_FORWARDED_FOR', '')
    if forwarded:
        return forwarded.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR')


def audit(action, actor=None, request=None, outcome='SUCCESS', **context):
    """Record one audit event.

    :param action:  stable upper-case verb, e.g. 'INJURY_PHOTO_VIEW'
    :param actor:   the acting user, or None for an unauthenticated attempt
    :param request: used for the source address
    :param outcome: 'SUCCESS' or 'FAILURE'
    :param context: extra fields, e.g. target_type='InjuryRecord', target_id=12
    """
    entry = {
        'ts': datetime.now(timezone.utc).isoformat(),
        'action': action,
        'outcome': outcome,
        'actor_id': getattr(actor, 'id', None),
        'actor': getattr(actor, 'username', None),
        'actor_role': getattr(actor, 'role', None),
        'ip': _client_ip(request),
    }
    entry.update({k: v for k, v in context.items() if v is not None})
    logger.info(json.dumps(entry, default=str, sort_keys=True))
