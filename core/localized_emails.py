"""
Localized Email Templates for QUOT ERP

Provides multi-language email templates that automatically select
the appropriate language based on user preference, IP, or email domain.
"""
import logging
from typing import Dict, Optional, Any
from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.utils.translation import activate, get_language

from core.geolocation import detect_language_from_email, detect_language_from_ip

logger = logging.getLogger('dtsg')

# Email templates dictionary - each template has translations
EMAIL_TEMPLATES: Dict[str, Dict[str, Dict[str, str]]] = {
    'welcome': {
        'en': {
            'subject': 'Welcome to QUOT ERP - Your Organization is Ready',
            'greeting': 'Dear {first_name},',
            'body': '''Welcome to QUOT ERP!

Your organization "{org_name}" has been successfully created.

Getting Started:
1. Login at: {login_url}
2. Username: {username}
3. Temporary Password: {temp_password}

Important: Please change your password immediately after first login.

If you have any questions, our support team is here to help.

Best regards,
The QUOT ERP Team''',
            'footer': 'This is an automated message. Please do not reply directly to this email.',
        },
        'fr': {
            'subject': 'Bienvenue sur QUOT ERP - Votre organisation est prête',
            'greeting': 'Cher(e) {first_name},',
            'body': '''Bienvenue sur QUOT ERP !

Votre organisation "{org_name}" a été créée avec succès.

Pour commencer :
1. Connectez-vous sur : {login_url}
2. Nom d'utilisateur : {username}
3. Mot de passe temporaire : {temp_password}

Important : Veuillez changer votre mot de passe immédiatement après la première connexion.

Si vous avez des questions, notre équipe d'assistance est là pour vous aider.

Cordialement,
L'équipe QUOT ERP''',
            'footer': 'Ceci est un message automatique. Veuillez ne pas répondre directement à ce courriel.',
        },
        'es': {
            'subject': 'Bienvenido a QUOT ERP - Su organización está lista',
            'greeting': 'Estimado/a {first_name},',
            'body': '''¡Bienvenido a QUOT ERP!

Su organización "{org_name}" ha sido creada exitosamente.

Para comenzar:
1. Inicie sesión en: {login_url}
2. Nombre de usuario: {username}
3. Contraseña temporal: {temp_password}

Importante: Por favor cambie su contraseña inmediatamente después del primer inicio de sesión.

Si tiene alguna pregunta, nuestro equipo de soporte está aquí para ayudarle.

Saludos cordiales,
El equipo de QUOT ERP''',
            'footer': 'Este es un mensaje automático. Por favor no responda directamente a este correo electrónico.',
        },
        'de': {
            'subject': 'Willkommen bei QUOT ERP - Ihre Organisation ist bereit',
            'greeting': 'Sehr geehrte/r {first_name},',
            'body': '''Willkommen bei QUOT ERP!

Ihre Organisation "{org_name}" wurde erfolgreich erstellt.

Erste Schritte:
1. Melden Sie sich an unter: {login_url}
2. Benutzername: {username}
3. Temporäres Passwort: {temp_password}

Wichtig: Bitte ändern Sie Ihr Passwort sofort nach der ersten Anmeldung.

Wenn Sie Fragen haben, steht Ihnen unser Support-Team gerne zur Verfügung.

Mit freundlichen Grüßen,
Das QUOT ERP Team''',
            'footer': 'Dies ist eine automatische Nachricht. Bitte antworten Sie nicht direkt auf diese E-Mail.',
        },
        'pt': {
            'subject': 'Bem-vindo ao QUOT ERP - Sua organização está pronta',
            'greeting': 'Caro(a) {first_name},',
            'body': '''Bem-vindo ao QUOT ERP!

Sua organização "{org_name}" foi criada com sucesso.

Para começar:
1. Faça login em: {login_url}
2. Nome de usuário: {username}
3. Senha temporária: {temp_password}

Importante: Por favor, altere sua senha imediatamente após o primeiro login.

Se você tiver alguma dúvida, nossa equipe de suporte está aqui para ajudar.

Atenciosamente,
A equipe QUOT ERP''',
            'footer': 'Esta é uma mensagem automática. Por favor, não responda diretamente a este e-mail.',
        },
        'zh': {
            'subject': '欢迎使用 QUOT ERP - 您的组织已准备就绪',
            'greeting': '尊敬的 {first_name}，',
            'body': '''欢迎使用 QUOT ERP！

您的组织 "{org_name}" 已成功创建。

开始使用：
1. 请登录：{login_url}
2. 用户名：{username}
3. 临时密码：{temp_password}

重要提示：首次登录后请立即更改密码。

如果您有任何问题，我们的支持团队随时为您提供帮助。

此致敬礼，
QUOT ERP 团队''',
            'footer': '这是一封自动发送的邮件。请勿直接回复此邮件。',
        },
        'ar': {
            'subject': 'مرحباً بك في QUOT ERP - جهزت مؤسستك',
            'greeting': 'عزيزي/عزيزتي {first_name}،',
            'body': '''مرحباً بك في QUOT ERP!

تم إنشاء مؤسستك "{org_name}" بنجاح.

للبدء:
1. سجل الدخول على: {login_url}
2. اسم المستخدم: {username}
3. كلمة المرور المؤقتة: {temp_password}

مهم: يرجى تغيير كلمة المرور الخاصة بك فوراً بعد أول تسجيل دخول.

إذا كانت لديك أي أسئلة، فإن فريق الدعم لدينا هنا لمساعدتك.

مع أطيب التحيات،
فريق QUOT ERP''',
            'footer': 'هذه رسالة آلية. يرجى عدم الرد مباشرة على هذا البريد الإلكتروني.',
        },
    },
    'password_reset': {
        'en': {
            'subject': 'QUOT ERP - Password Reset Request',
            'greeting': 'Hello {first_name},',
            'body': '''We received a request to reset your password for QUOT ERP.

If you did not request this, please ignore this email.

To reset your password, click the link below:
{reset_url}

This link will expire in {expiry_hours} hours.

For security reasons, if you didn't request this, please contact support immediately.

Best regards,
The QUOT ERP Team''',
            'footer': 'This is an automated security message.',
        },
        'fr': {
            'subject': 'QUOT ERP - Demande de réinitialisation de mot de passe',
            'greeting': 'Bonjour {first_name},',
            'body': '''Nous avons reçu une demande de réinitialisation de votre mot de passe pour QUOT ERP.

Si vous n'avez pas effectué cette demande, veuillez ignorer ce courriel.

Pour réinitialiser votre mot de passe, cliquez sur le lien ci-dessous :
{reset_url}

Ce lien expirera dans {expiry_hours} heures.

Pour des raisons de sécurité, si vous n'avez pas demandé cela, veuillez contacter immédiatement le support.

Cordialement,
L'équipe QUOT ERP''',
            'footer': 'Ceci est un message de sécurité automatique.',
        },
        'es': {
            'subject': 'QUOT ERP - Solicitud de Restablecimiento de Contraseña',
            'greeting': 'Hola {first_name},',
            'body': '''Recibimos una solicitud para restablecer su contraseña de QUOT ERP.

Si no solicitó esto, por favor ignore este correo electrónico.

Para restablecer su contraseña, haga clic en el enlace a continuación:
{reset_url}

Este enlace expirará en {expiry_hours} horas.

Por razones de seguridad, si no solicitó esto, por favor contacte a soporte inmediatamente.

Saludos cordiales,
El equipo de QUOT ERP''',
            'footer': 'Este es un mensaje de seguridad automático.',
        },
        'de': {
            'subject': 'QUOT ERP - Anfrage zur Passwortzurücksetzung',
            'greeting': 'Hallo {first_name},',
            'body': '''Wir haben eine Anfrage zur Zurücksetzung Ihres Passworts für QUOT ERP erhalten.

Wenn Sie diese nicht angefordert haben, ignorieren Sie bitte diese E-Mail.

Um Ihr Passwort zurückzusetzen, klicken Sie auf den folgenden Link:
{reset_url}

Dieser Link läuft in {expiry_hours} Stunden ab.

Aus Sicherheitsgründen, wenn Sie dies nicht angefordert haben, wenden Sie sich bitte umgehend an den Support.

Mit freundlichen Grüßen,
Das QUOT ERP Team''',
            'footer': 'Dies ist eine automatische Sicherheitsnachricht.',
        },
        'zh': {
            'subject': 'QUOT ERP - 密码重置请求',
            'greeting': '您好 {first_name}，',
            'body': '''我们收到了重置您QUOT ERP密码的请求。

如果您未提出此请求，请忽略此邮件。

要重置密码，请点击下方链接：
{reset_url}

此链接将在 {expiry_hours} 小时后过期。

出于安全原因，如果您没有提出此请求，请立即联系支持团队。

此致敬礼，
QUOT ERP 团队''',
            'footer': '这是一封自动发送的安全邮件。',
        },
    },
    'payment_received': {
        'en': {
            'subject': 'QUOT ERP - Payment Confirmation',
            'greeting': 'Dear {first_name},',
            'body': '''Thank you for your payment!

Payment Details:
- Amount: {amount}
- Reference: {reference}
- Date: {date}

Your subscription is now active until {end_date}.

Thank you for choosing QUOT ERP!

Best regards,
The QUOT ERP Team''',
            'footer': 'For billing inquiries, please contact support.',
        },
        'fr': {
            'subject': 'QUOT ERP - Confirmation de Paiement',
            'greeting': 'Cher(e) {first_name},',
            'body': '''Merci pour votre paiement !

Détails du paiement :
- Montant : {amount}
- Référence : {reference}
- Date : {date}

Votre abonnement est maintenant actif jusqu'au {end_date}.

Merci d'avoir choisi QUOT ERP !

Cordialement,
L'équipe QUOT ERP''',
            'footer': 'Pour toute question concernant la facturation, veuillez contacter le support.',
        },
    },
    'subscription_expiring': {
        'en': {
            'subject': 'QUOT ERP - Subscription Expiring Soon',
            'greeting': 'Dear {first_name},',
            'body': '''Your QUOT ERP subscription is expiring soon!

Current Plan: {plan_name}
Expiration Date: {expiry_date}
Days Remaining: {days_remaining}

To continue using QUOT ERP without interruption, please renew your subscription.

Renew Now: {renew_url}

If you have any questions, our team is here to help.

Best regards,
The QUOT ERP Team''',
            'footer': 'This is a subscription reminder.',
        },
        'fr': {
            'subject': 'QUOT ERP - Abonnement expirant bientôt',
            'greeting': 'Cher(e) {first_name},',
            'body': '''Votre abonnement QUOT ERP expire bientôt !

Plan actuel : {plan_name}
Date d'expiration : {expiry_date}
Jours restants : {days_remaining}

Pour continuer à utiliser QUOT ERP sans interruption, veuillez renouveler votre abonnement.

Renouveler maintenant : {renew_url}

Si vous avez des questions, notre équipe est là pour vous aider.

Cordialement,
L'équipe QUOT ERP''',
            'footer': "Ceci est un rappel d'abonnement.",
        },
    },
    'support_ticket': {
        'en': {
            'subject': 'QUOT ERP Support - Ticket #{ticket_number}',
            'greeting': 'Hello {first_name},',
            'body': '''Thank you for contacting QUOT ERP Support!

Your ticket has been received and assigned to our team.

Ticket Details:
- Number: {ticket_number}
- Subject: {subject}
- Priority: {priority}
- Status: {status}

We will respond to your inquiry as soon as possible.

Track your ticket: {ticket_url}

Best regards,
QUOT ERP Support Team''',
            'footer': 'Please do not reply directly to this email. Use the ticket URL above.',
        },
        'fr': {
            'subject': 'Support QUOT ERP - Ticket #{ticket_number}',
            'greeting': 'Bonjour {first_name},',
            'body': '''Merci d'avoir contacté le support QUOT ERP !

Votre ticket a été reçu et assigné à notre équipe.

Détails du ticket :
- Numéro : {ticket_number}
- Sujet : {subject}
- Priorité : {priority}
- Statut : {status}

Nous répondrons à votre demande dès que possible.

Suivez votre ticket : {ticket_url}

Cordialement,
L'équipe de support QUOT ERP''',
            'footer': 'Veuillez ne pas répondre directement à ce courriel. Utilisez le lien du ticket ci-dessus.',
        },
    },
}


def get_email_template(template_name: str, language: str = 'en') -> Dict[str, str]:
    """Get email template in the specified language, fallback to English.

    Resolution order:
        1. Active DB row (EmailTemplate) for (template_name, language)
        2. Active DB row for (template_name, 'en')
        3. Hardcoded EMAIL_TEMPLATES dict in this module
    DB rows take precedence so SuperAdmin edits go live without a deploy.
    """
    # 1 & 2: DB lookup
    try:
        from superadmin.models import EmailTemplate  # lazy — avoid app-load cycle
        db_tpl = (
            EmailTemplate.objects
            .filter(key=template_name, language=language, is_active=True)
            .first()
        )
        if db_tpl is None and language != 'en':
            db_tpl = (
                EmailTemplate.objects
                .filter(key=template_name, language='en', is_active=True)
                .first()
            )
        if db_tpl is not None:
            return {
                'subject': db_tpl.subject,
                'greeting': '',  # DB templates fold greeting into body_html
                'body': db_tpl.body_html,
                'footer': '',
                '_is_html': True,
            }
    except Exception as e:  # pragma: no cover — DB might not be ready during migrations
        logger.debug('EmailTemplate DB lookup skipped: %s', e)

    # 3: Hardcoded fallback
    template = EMAIL_TEMPLATES.get(template_name, {})

    if language in template:
        return template[language]

    # Fallback to English
    if 'en' in template:
        return template['en']

    # Return empty template if not found
    return {
        'subject': 'QUOT ERP - Message',
        'greeting': 'Dear User,',
        'body': 'No content available.',
        'footer': '',
    }


def detect_email_language(user=None, email: str = '', request=None) -> str:
    """
    Detect the appropriate language for an email based on user preferences,
    email domain, or request IP.
    """
    # 1. Check user preference
    if user and hasattr(user, 'preferred_language') and user.preferred_language:
        return user.preferred_language

    # 2. Try email domain
    if email:
        lang = detect_language_from_email(email)
        if lang:
            return lang

    # 3. Try request IP
    if request:
        lang = detect_language_from_ip(request)
        if lang:
            return lang

    # 4. Default
    return getattr(settings, 'DEFAULT_LANGUAGE', 'en')


def send_localized_email(
    template_name: str,
    to_email: str,
    context: Dict[str, Any],
    user=None,
    cc: Optional[list] = None,
    bcc: Optional[list] = None,
    attachments: Optional[list] = None,
) -> bool:
    """
    Send a localized email based on the recipient's language preference.

    Args:
        template_name: Name of the email template
        to_email: Recipient email address
        context: Template variables
        user: Optional user object for language detection
        cc: Optional CC list
        bcc: Optional BCC list
        attachments: Optional list of attachments

    Returns:
        bool: True if email sent successfully
    """
    # Detect language
    language = detect_email_language(user, to_email)

    # Activate language for translations
    old_lang = get_language()
    activate(language)

    try:
        # Get template
        template = get_email_template(template_name, language)

        # DB-backed HTML template path — use beautified base layout.
        if template.get('_is_html'):
            from superadmin.email_rendering import base_layout, strip_html, substitute
            from superadmin.models import SuperAdminSettings
            sa = SuperAdminSettings.load()
            subject = substitute(template['subject'], context)
            body_html = substitute(template['body'], context)
            html_content = base_layout(
                title=subject,
                content_html=body_html,
                org_name=sa.organization_name or 'QUOT ERP',
                support_email=sa.support_email or sa.smtp_from_email or '',
                preheader=subject,
            )
            plain_content = strip_html(body_html)

            email = EmailMultiAlternatives(
                subject=subject,
                body=plain_content,
                from_email=settings.DEFAULT_FROM_EMAIL,
                to=[to_email],
                cc=cc or [],
                bcc=bcc or [],
            )
            email.attach_alternative(html_content, 'text/html')
            if attachments:
                for attachment in attachments:
                    email.attach(*attachment)
            email.send(fail_silently=False)
            logger.info(f'Localized (DB) email sent to {to_email} in {language}')
            return True

        # Legacy hardcoded-dict path (retained as fallback).
        subject = template['subject'].format(**context)
        greeting = template['greeting'].format(**context)
        body = template['body'].format(**context)
        footer = template['footer']

        # Combine content
        plain_content = f"{greeting}\n\n{body}\n\n{footer}"
        html_content = f"""
        <html>
        <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
            <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
                <div style="background: linear-gradient(135deg, #091735 0%, #1a2744 100%); padding: 20px; border-radius: 8px 8px 0 0;">
                    <h1 style="color: #fff; margin: 0; font-size: 24px;">QUOT ERP</h1>
                </div>
                <div style="background: #fff; padding: 30px; border: 1px solid #e0e0e0;">
                    <p style="font-size: 16px;">{greeting.replace(chr(10), '<br>')}</p>
                    <div style="margin: 20px 0; line-height: 1.8;">
                        {body.replace(chr(10), '<br>') if chr(10) not in body else "<br>".join(body.split(chr(10)))}</div>
                    <hr style="border: none; border-top: 1px solid #e0e0e0; margin: 20px 0;">
                    <p style="color: #666; font-size: 12px;">{footer}</p>
                </div>
                <div style="background: #f5f5f5; padding: 15px; text-align: center; border-radius: 0 0 8px 8px; border: 1px solid #e0e0e0; border-top: none;">
                    <p style="margin: 0; color: #666; font-size: 12px;">
                        © 2024 QUOT ERP. All rights reserved.<br>
                        <a href="#" style="color: #1890ff;">Privacy Policy</a> |
                        <a href="#" style="color: #1890ff;">Terms of Service</a>
                    </p>
                </div>
            </div>
        </body>
        </html>
        """

        # Create email
        email = EmailMultiAlternatives(
            subject=subject,
            body=plain_content,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[to_email],
            cc=cc or [],
            bcc=bcc or [],
        )
        email.attach_alternative(html_content, 'text/html')

        # Add attachments
        if attachments:
            for attachment in attachments:
                email.attach(*attachment)

        # Send
        email.send(fail_silently=False)
        logger.info(f'Localized email sent to {to_email} in {language}')
        return True

    except Exception as e:
        logger.error(f'Failed to send email to {to_email}: {e}')
        return False

    finally:
        # Restore language
        activate(old_lang)


def send_welcome_email(user, tenant, temp_password, login_url):
    """Send localized welcome email to new user."""
    context = {
        'first_name': user.first_name or user.username,
        'org_name': tenant.name,
        'username': user.username,
        'temp_password': temp_password,
        'login_url': login_url,
    }
    return send_localized_email(
        'welcome',
        user.email,
        context,
        user=user,
    )


def send_password_reset_email(user, reset_url, expiry_hours=24):
    """Send localized password reset email."""
    context = {
        'first_name': user.first_name or user.username,
        'reset_url': reset_url,
        'expiry_hours': expiry_hours,
    }
    return send_localized_email(
        'password_reset',
        user.email,
        context,
        user=user,
    )


def send_payment_confirmation_email(user, amount, reference, date, end_date):
    """Send localized payment confirmation email."""
    context = {
        'first_name': user.first_name or user.username,
        'amount': amount,
        'reference': reference,
        'date': date,
        'end_date': end_date,
    }
    return send_localized_email(
        'payment_received',
        user.email,
        context,
        user=user,
    )


def send_subscription_expiring_email(user, plan_name, expiry_date, days_remaining, renew_url):
    """Send localized subscription expiring email."""
    context = {
        'first_name': user.first_name or user.username,
        'plan_name': plan_name,
        'expiry_date': expiry_date,
        'days_remaining': days_remaining,
        'renew_url': renew_url,
    }
    return send_localized_email(
        'subscription_expiring',
        user.email,
        context,
        user=user,
    )


def send_support_ticket_email(user, ticket_number, subject, priority, status, ticket_url):
    """Send localized support ticket email."""
    context = {
        'first_name': user.first_name or user.username,
        'ticket_number': ticket_number,
        'subject': subject,
        'priority': priority,
        'status': status,
        'ticket_url': ticket_url,
    }
    return send_localized_email(
        'support_ticket',
        user.email,
        context,
        user=user,
    )
