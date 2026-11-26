from django.utils import timezone


def apply_pending_limit(control):
    if control.pending_limit_effective_at and control.pending_limit_effective_at <= timezone.now():
        control.daily_funding_limit_cents = control.pending_daily_funding_limit_cents
        control.pending_daily_funding_limit_cents = None
        control.pending_limit_effective_at = None
        control.save(update_fields=["daily_funding_limit_cents", "pending_daily_funding_limit_cents", "pending_limit_effective_at", "updated_at"])
