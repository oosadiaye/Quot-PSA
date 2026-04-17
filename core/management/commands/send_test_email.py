"""
Send a test email using the configured Django email backend.

Usage
-----
    python manage.py send_test_email --to alice@example.com
    python manage.py send_test_email --to alice@example.com --subject "SMTP drill"

Use this to verify SMTP credentials after deploying:

    EMAIL_HOST=smtp.sendgrid.net EMAIL_HOST_USER=apikey \\
    EMAIL_HOST_PASSWORD=SG.xxxxx EMAIL_USE_TLS=true \\
    python manage.py send_test_email --to you@example.com

Exits 0 on send, 1 on error.
"""
from __future__ import annotations

import sys
from django.core.mail import send_mail
from django.conf import settings
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = 'Send a test email via the configured EMAIL_BACKEND.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--to', required=True,
            help='Recipient email address.',
        )
        parser.add_argument(
            '--subject', default='Quot PSE test email',
            help='Subject line (default: Quot PSE test email).',
        )
        parser.add_argument(
            '--body', default=(
                'This is a test message from the Quot PSE platform.\n\n'
                'If you received this, your SMTP configuration is working.'
            ),
            help='Message body.',
        )

    def handle(self, *args, **options):
        to_addr = options['to']
        subject = options['subject']
        body = options['body']

        self.stdout.write(self.style.NOTICE(
            f'Sending test email via {settings.EMAIL_BACKEND}'
        ))
        if settings.EMAIL_HOST:
            self.stdout.write(
                f'  Host: {settings.EMAIL_HOST}:{settings.EMAIL_PORT} '
                f'(TLS={settings.EMAIL_USE_TLS}, '
                f'SSL={settings.EMAIL_USE_SSL})'
            )
        self.stdout.write(f'  From: {settings.DEFAULT_FROM_EMAIL}')
        self.stdout.write(f'  To:   {to_addr}')
        self.stdout.write(f'  Subj: {subject}')

        try:
            sent = send_mail(
                subject=subject,
                message=body,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[to_addr],
                fail_silently=False,
            )
        except Exception as exc:
            self.stderr.write(self.style.ERROR(
                f'Email send failed: {type(exc).__name__}: {exc}'
            ))
            sys.exit(1)

        if sent:
            self.stdout.write(self.style.SUCCESS(
                f'Email accepted by backend ({sent} recipient(s)).'
            ))
        else:
            self.stderr.write(self.style.WARNING(
                'Backend returned 0 — message may have been silently dropped. '
                'Verify inbox reception.'
            ))
            sys.exit(1)
