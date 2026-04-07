import logging

from django.core.mail.backends.smtp import EmailBackend

from .models import SuperAdminSettings

logger = logging.getLogger('dtsg')


def get_smtp_backend(sa_settings=None):
    """Return a configured SMTP EmailBackend without mutating global settings."""
    if not sa_settings:
        try:
            sa_settings = SuperAdminSettings.load()
        except Exception:
            logger.warning('Could not load SuperAdminSettings for SMTP')
            return None

    if not sa_settings.smtp_enabled or not sa_settings.smtp_host:
        return None

    return EmailBackend(
        host=sa_settings.smtp_host,
        port=sa_settings.smtp_port,
        username=sa_settings.smtp_username,
        password=sa_settings.smtp_password,
        use_tls=sa_settings.smtp_use_tls,
        use_ssl=sa_settings.smtp_use_ssl,
    )


# Keep old name as an alias for any callers that haven't been updated yet.
apply_smtp_settings = get_smtp_backend


def _get_from_email(sa_settings=None):
    """Build the From header from SuperAdminSettings."""
    if not sa_settings:
        sa_settings = SuperAdminSettings.load()
    if sa_settings and sa_settings.smtp_from_email:
        return f"{sa_settings.smtp_from_name} <{sa_settings.smtp_from_email}>"
    return 'noreply@dtsg.test'


def send_test_email(to_email):
    """Send a test email to verify SMTP configuration.

    Raises on failure so the caller can handle it.
    """
    from django.core.mail import EmailMessage

    backend = get_smtp_backend()
    if not backend:
        raise ValueError('SMTP is not configured or disabled in platform settings.')

    from_email = _get_from_email()

    email = EmailMessage(
        subject='DTSG ERP - SMTP Test',
        body='This is a test email from DTSG ERP platform. '
             'Your SMTP configuration is working correctly.',
        from_email=from_email,
        to=[to_email],
        connection=backend,
    )
    email.send(fail_silently=False)
    logger.info('SMTP test email sent to %s', to_email)


def send_tenant_smtp_test(smtp_config, to_email):
    """Send a test email using a tenant's SMTP configuration."""
    from django.core.mail import EmailMessage

    backend = EmailBackend(
        host=smtp_config.smtp_host,
        port=smtp_config.smtp_port,
        username=smtp_config.smtp_username,
        password=smtp_config.smtp_password,
        use_tls=smtp_config.smtp_use_tls,
        use_ssl=smtp_config.smtp_use_ssl,
        timeout=10,
    )

    from_email = (
        f"{smtp_config.smtp_from_name} <{smtp_config.smtp_from_email}>"
        if smtp_config.smtp_from_name
        else smtp_config.smtp_from_email
    )

    email = EmailMessage(
        subject='DTSG ERP - Tenant SMTP Test',
        body='This is a test email from your tenant SMTP configuration. It is working correctly.',
        from_email=from_email,
        to=[to_email],
        connection=backend,
    )
    if smtp_config.reply_to_email:
        email.reply_to = [smtp_config.reply_to_email]

    email.send(fail_silently=False)
    logger.info('Tenant SMTP test sent via %s to %s', smtp_config.smtp_host, to_email)
