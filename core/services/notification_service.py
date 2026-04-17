import logging

from django.core.mail import send_mail
from django.conf import settings

logger = logging.getLogger('dtsg')


class NotificationService:
    @staticmethod
    def send_verification_email(user, token):
        """Send an email verification link to the user."""
        frontend_url = settings.FRONTEND_URL
        verify_link = f"{frontend_url}/verify-email?token={token}"
        try:
            send_mail(
                subject='QUOT ERP — Verify Your Email',
                message=(
                    f"Hi {user.first_name or user.username},\n\n"
                    f"Please verify your email address by clicking this link:\n\n"
                    f"{verify_link}\n\n"
                    f"This link expires in 72 hours.\n\n"
                    f"If you did not create this account, please ignore this email."
                ),
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[user.email],
                fail_silently=True,
            )
        except Exception:
            logger.warning('Failed to send verification email to user_id=%s', user.pk)

    @staticmethod
    def send_password_reset_email(user, reset_link):
        """Send a password reset email to the user."""
        try:
            send_mail(
                subject='QUOT ERP — Password Reset',
                message=(
                    f'Click the link to reset your password:\n\n'
                    f'{reset_link}\n\n'
                    f'This link expires in 3 days. '
                    f'If you did not request this, ignore this email.'
                ),
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[user.email],
                fail_silently=True,
            )
            logger.info('Password reset email sent to user_id=%s', user.pk)
        except Exception:
            logger.warning('Failed to send password reset email to user_id=%s', user.pk)
