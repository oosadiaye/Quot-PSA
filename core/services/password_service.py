import logging

from django_tenants.utils import schema_context
from rest_framework.authtoken.models import Token

security_logger = logging.getLogger('security')
logger = logging.getLogger('dtsg')


class PasswordService:
    @staticmethod
    def validate_new_password(user, new_password):
        """Validate password strength and check password history.

        Returns a list of error messages, or an empty list if valid.
        """
        from django.contrib.auth.password_validation import validate_password
        from django.core.exceptions import ValidationError as DjangoValidationError
        from core.models import PasswordHistory

        errors = []

        try:
            validate_password(new_password, user)
        except DjangoValidationError as e:
            errors.extend(e.messages)
            return errors  # No point checking history if strength fails

        with schema_context('public'):
            if PasswordHistory.is_password_reused(user, new_password):
                errors.append(
                    f'Cannot reuse any of your last {PasswordHistory.HISTORY_DEPTH} passwords.'
                )

        return errors

    @staticmethod
    def reset_password(user, new_password):
        """Record the current password, set the new one, and revoke all sessions."""
        from core.models import PasswordHistory, UserSession

        with schema_context('public'):
            PasswordHistory.record_password(user)
            user.set_password(new_password)
            user.save()
            Token.objects.filter(user=user).delete()
            UserSession.objects.filter(user=user).update(is_active=False)

        logger.info('Password reset completed for user_id=%s', user.pk)
