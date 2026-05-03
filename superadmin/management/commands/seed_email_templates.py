"""Seed canonical email templates into the EmailTemplate table.

Idempotent — re-running updates the body_html/subject of system templates
unless --no-update is passed, in which case existing rows are left alone.

Usage:
    python manage.py seed_email_templates
    python manage.py seed_email_templates --no-update
"""
from __future__ import annotations

from django.core.management.base import BaseCommand

from superadmin.models import EmailTemplate


# Each seed: (key, language, category, display_name, description, subject, body_html, variables)
# body_html is the *inner content* — the base layout chrome is added at send time.
SEEDS = [
    (
        'welcome', 'en', 'auth',
        'Welcome / Signup Confirmation',
        'Sent when a new tenant organisation is provisioned. Includes login URL and temporary credentials.',
        'Welcome to {org_name} — Your Account is Ready',
        """<p style="font-size:16px;margin:0 0 16px 0;">Dear <strong>{first_name}</strong>,</p>
<p>Your organisation <strong>"{org_name}"</strong> has been successfully created on our platform. We're thrilled to have you on board.</p>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin:20px 0;background:#f8fafc;border:1px solid #e2e8f0;border-radius:10px;">
  <tr><td style="padding:16px 20px;">
    <div style="font-size:12px;font-weight:700;color:#64748b;text-transform:uppercase;letter-spacing:1px;margin-bottom:10px;">Your Login Details</div>
    <div style="font-size:14px;line-height:1.9;">
      <strong>Login URL:</strong> <a href="{login_url}" style="color:#242a88;">{login_url}</a><br>
      <strong>Username:</strong> {username}<br>
      <strong>Temporary password:</strong> <code style="background:#fff;padding:2px 6px;border-radius:4px;border:1px solid #e2e8f0;">{temp_password}</code>
    </div>
  </td></tr>
</table>
<div style="text-align:center;margin:28px 0;">
  <a href="{login_url}" style="display:inline-block;background:linear-gradient(135deg,#242a88,#2e35a0);color:#ffffff;text-decoration:none;font-weight:600;padding:12px 28px;border-radius:10px;">Log in now</a>
</div>
<p style="font-size:13px;color:#64748b;">For security, please change your password immediately after your first login.</p>""",
        ['first_name', 'org_name', 'username', 'temp_password', 'login_url'],
    ),
    (
        'password_reset', 'en', 'auth',
        'Password Reset Request',
        'Sent when a user requests a password reset. Contains a time-limited link.',
        'Reset your password',
        """<p style="font-size:16px;margin:0 0 16px 0;">Hello <strong>{first_name}</strong>,</p>
<p>We received a request to reset the password for your account. If this was you, click the button below to choose a new password. If not, you can safely ignore this email — your current password remains unchanged.</p>
<div style="text-align:center;margin:28px 0;">
  <a href="{reset_url}" style="display:inline-block;background:linear-gradient(135deg,#242a88,#2e35a0);color:#ffffff;text-decoration:none;font-weight:600;padding:12px 28px;border-radius:10px;">Reset password</a>
</div>
<p style="font-size:13px;color:#64748b;">This link expires in <strong>{expiry_hours} hours</strong>. If the button doesn't work, paste this URL into your browser:<br><span style="word-break:break-all;color:#242a88;">{reset_url}</span></p>
<p style="font-size:13px;color:#64748b;">If you didn't request this, please contact support immediately.</p>""",
        ['first_name', 'reset_url', 'expiry_hours'],
    ),
    (
        'password_reset_success', 'en', 'auth',
        'Password Reset Confirmation',
        'Confirms a successful password change.',
        'Your password has been changed',
        """<p style="font-size:16px;margin:0 0 16px 0;">Hello <strong>{first_name}</strong>,</p>
<p>This is a confirmation that the password for your account was successfully changed on <strong>{changed_at}</strong>.</p>
<p style="font-size:13px;color:#64748b;">If you did not make this change, contact support immediately — your account may be compromised.</p>""",
        ['first_name', 'changed_at'],
    ),
    (
        'email_verification', 'en', 'auth',
        'Email Verification',
        'Sent to verify a user-owned email address.',
        'Verify your email address',
        """<p style="font-size:16px;margin:0 0 16px 0;">Hello <strong>{first_name}</strong>,</p>
<p>Please confirm that <strong>{email}</strong> is your email address by clicking the button below.</p>
<div style="text-align:center;margin:28px 0;">
  <a href="{verify_url}" style="display:inline-block;background:linear-gradient(135deg,#242a88,#2e35a0);color:#ffffff;text-decoration:none;font-weight:600;padding:12px 28px;border-radius:10px;">Verify email</a>
</div>
<p style="font-size:13px;color:#64748b;">This link expires in {expiry_hours} hours.</p>""",
        ['first_name', 'email', 'verify_url', 'expiry_hours'],
    ),
    (
        'user_invitation', 'en', 'auth',
        'User Invitation',
        'Sent when an admin invites a new user to a tenant.',
        "You've been invited to {org_name}",
        """<p style="font-size:16px;margin:0 0 16px 0;">Hello,</p>
<p><strong>{inviter_name}</strong> has invited you to join <strong>{org_name}</strong>. Accept the invitation to create your account.</p>
<div style="text-align:center;margin:28px 0;">
  <a href="{invite_url}" style="display:inline-block;background:linear-gradient(135deg,#242a88,#2e35a0);color:#ffffff;text-decoration:none;font-weight:600;padding:12px 28px;border-radius:10px;">Accept invitation</a>
</div>
<p style="font-size:13px;color:#64748b;">This invitation expires in {expiry_hours} hours.</p>""",
        ['inviter_name', 'org_name', 'invite_url', 'expiry_hours'],
    ),
    (
        'payment_received', 'en', 'billing',
        'Payment Confirmation',
        'Sent after a successful subscription payment.',
        'Payment received — thank you',
        """<p style="font-size:16px;margin:0 0 16px 0;">Dear <strong>{first_name}</strong>,</p>
<p>Thank you! We've received your payment and your subscription is now active.</p>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin:20px 0;background:#f8fafc;border:1px solid #e2e8f0;border-radius:10px;">
  <tr><td style="padding:16px 20px;">
    <div style="font-size:14px;line-height:1.9;">
      <strong>Amount:</strong> {amount}<br>
      <strong>Reference:</strong> {reference}<br>
      <strong>Payment date:</strong> {date}<br>
      <strong>Active until:</strong> {end_date}
    </div>
  </td></tr>
</table>""",
        ['first_name', 'amount', 'reference', 'date', 'end_date'],
    ),
    (
        'subscription_expiring', 'en', 'billing',
        'Subscription Expiring Soon',
        'Reminder sent N days before subscription expiry.',
        'Your subscription expires in {days_remaining} days',
        """<p style="font-size:16px;margin:0 0 16px 0;">Dear <strong>{first_name}</strong>,</p>
<p>Your <strong>{plan_name}</strong> subscription expires on <strong>{expiry_date}</strong> — that's <strong>{days_remaining} days</strong> away.</p>
<p>Renew now to avoid any interruption in service.</p>
<div style="text-align:center;margin:28px 0;">
  <a href="{renew_url}" style="display:inline-block;background:linear-gradient(135deg,#242a88,#2e35a0);color:#ffffff;text-decoration:none;font-weight:600;padding:12px 28px;border-radius:10px;">Renew subscription</a>
</div>""",
        ['first_name', 'plan_name', 'expiry_date', 'days_remaining', 'renew_url'],
    ),
    (
        'support_ticket', 'en', 'support',
        'Support Ticket Acknowledgement',
        'Sent when a support ticket is created.',
        'Support ticket #{ticket_number} received',
        """<p style="font-size:16px;margin:0 0 16px 0;">Hello <strong>{first_name}</strong>,</p>
<p>Thanks for reaching out — we've received your ticket and the team is on it.</p>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin:20px 0;background:#f8fafc;border:1px solid #e2e8f0;border-radius:10px;">
  <tr><td style="padding:16px 20px;">
    <div style="font-size:14px;line-height:1.9;">
      <strong>Ticket:</strong> #{ticket_number}<br>
      <strong>Subject:</strong> {subject}<br>
      <strong>Priority:</strong> {priority}<br>
      <strong>Status:</strong> {status}
    </div>
  </td></tr>
</table>
<div style="text-align:center;margin:28px 0;">
  <a href="{ticket_url}" style="display:inline-block;background:linear-gradient(135deg,#242a88,#2e35a0);color:#ffffff;text-decoration:none;font-weight:600;padding:12px 28px;border-radius:10px;">View ticket</a>
</div>""",
        ['first_name', 'ticket_number', 'subject', 'priority', 'status', 'ticket_url'],
    ),
    # ─── HR Portal Templates ─────────────────────────────────────────────────
    (
        'payslip_ready', 'en', 'hr',
        'Payslip Ready',
        'Sent when a new payslip is available in the employee self-service portal.',
        'Your {period_label} payslip is ready',
        """<p style="font-size:16px;margin:0 0 16px 0;">Hello <strong>{employee_name}</strong>,</p>
<p>Your payslip for <strong>{period_label}</strong> has been processed and is now available in your portal.</p>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin:20px 0;background:#f8fafc;border:1px solid #e2e8f0;border-radius:10px;">
  <tr><td style="padding:16px 20px;">
    <div style="font-size:12px;font-weight:700;color:#64748b;text-transform:uppercase;letter-spacing:1px;margin-bottom:10px;">Payment Summary</div>
    <div style="font-size:14px;line-height:1.9;">
      <strong>Period:</strong> {period_label}<br>
      <strong>Payment date:</strong> {payment_date}<br>
      <strong>Net pay:</strong> {net_salary}
    </div>
  </td></tr>
</table>
<div style="text-align:center;margin:28px 0;">
  <a href="{portal_url}" style="display:inline-block;background:linear-gradient(135deg,#242a88,#2e35a0);color:#ffffff;text-decoration:none;font-weight:600;padding:12px 28px;border-radius:10px;">View payslip</a>
</div>
<p style="font-size:13px;color:#64748b;">For questions about this payslip, contact your HR representative.</p>""",
        ['employee_name', 'period_label', 'payment_date', 'net_salary', 'portal_url'],
    ),
    (
        'leave_submitted', 'en', 'hr',
        'Leave Request Submitted',
        'Confirms that a leave request has been submitted and is pending approval.',
        'Leave request received — {leave_type}',
        """<p style="font-size:16px;margin:0 0 16px 0;">Hello <strong>{employee_name}</strong>,</p>
<p>Your leave request has been submitted and is awaiting approval from your supervisor.</p>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin:20px 0;background:#f8fafc;border:1px solid #e2e8f0;border-radius:10px;">
  <tr><td style="padding:16px 20px;">
    <div style="font-size:14px;line-height:1.9;">
      <strong>Leave type:</strong> {leave_type}<br>
      <strong>From:</strong> {start_date}<br>
      <strong>To:</strong> {end_date}<br>
      <strong>Days:</strong> {total_days}<br>
      <strong>Reason:</strong> {reason}
    </div>
  </td></tr>
</table>
<p style="font-size:13px;color:#64748b;">You'll receive another email once your request is reviewed.</p>""",
        ['employee_name', 'leave_type', 'start_date', 'end_date', 'total_days', 'reason'],
    ),
    (
        'leave_approved', 'en', 'hr',
        'Leave Request Approved',
        'Sent when a supervisor approves an employee leave request.',
        'Your leave request has been approved',
        """<p style="font-size:16px;margin:0 0 16px 0;">Hello <strong>{employee_name}</strong>,</p>
<p>Good news — your leave request has been <strong style="color:#16a34a;">approved</strong>.</p>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin:20px 0;background:#f0fdf4;border:1px solid #bbf7d0;border-radius:10px;">
  <tr><td style="padding:16px 20px;">
    <div style="font-size:14px;line-height:1.9;">
      <strong>Leave type:</strong> {leave_type}<br>
      <strong>From:</strong> {start_date}<br>
      <strong>To:</strong> {end_date}<br>
      <strong>Days:</strong> {total_days}<br>
      <strong>Approved by:</strong> {approver_name}
    </div>
    {comments_block}
  </td></tr>
</table>
<p style="font-size:13px;color:#64748b;">Have a great time off — we'll see you when you return!</p>""",
        ['employee_name', 'leave_type', 'start_date', 'end_date', 'total_days', 'approver_name', 'comments_block'],
    ),
    (
        'leave_rejected', 'en', 'hr',
        'Leave Request Rejected',
        'Sent when a leave request is rejected.',
        'Your leave request was not approved',
        """<p style="font-size:16px;margin:0 0 16px 0;">Hello <strong>{employee_name}</strong>,</p>
<p>Unfortunately, your leave request was not approved at this time.</p>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin:20px 0;background:#fef2f2;border:1px solid #fecaca;border-radius:10px;">
  <tr><td style="padding:16px 20px;">
    <div style="font-size:14px;line-height:1.9;">
      <strong>Leave type:</strong> {leave_type}<br>
      <strong>From:</strong> {start_date}<br>
      <strong>To:</strong> {end_date}<br>
      <strong>Reviewed by:</strong> {approver_name}
    </div>
    {comments_block}
  </td></tr>
</table>
<p style="font-size:13px;color:#64748b;">Please speak with your supervisor if you'd like to discuss this decision or submit a revised request.</p>""",
        ['employee_name', 'leave_type', 'start_date', 'end_date', 'approver_name', 'comments_block'],
    ),
    (
        'verification_due', 'en', 'hr',
        'Employee Verification Due',
        'Sent when a new verification cycle opens or a deadline nears.',
        'Action required: verify your employment details',
        """<p style="font-size:16px;margin:0 0 16px 0;">Hello <strong>{employee_name}</strong>,</p>
<p>A verification exercise is under way. To stay in active status on the payroll, please sign in to the portal and confirm your details before the deadline.</p>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin:20px 0;background:#fffbeb;border:1px solid #fde68a;border-radius:10px;">
  <tr><td style="padding:16px 20px;">
    <div style="font-size:14px;line-height:1.9;">
      <strong>Cycle:</strong> {cycle_name}<br>
      <strong>Period:</strong> {period_label}<br>
      <strong>Deadline:</strong> {deadline}
    </div>
  </td></tr>
</table>
<p style="margin:20px 0;">
  <a href="{portal_url}" style="background:linear-gradient(135deg,#242a88,#2e35a0);color:#ffffff;padding:12px 22px;border-radius:8px;text-decoration:none;font-weight:600;display:inline-block;">Open employee portal</a>
</p>
<p style="font-size:13px;color:#64748b;">Employees who don't attest by the deadline may be flagged for HR follow-up.</p>""",
        ['employee_name', 'cycle_name', 'period_label', 'deadline', 'portal_url'],
    ),
]


class Command(BaseCommand):
    help = 'Seed canonical email templates (idempotent).'

    def add_arguments(self, parser):
        parser.add_argument(
            '--no-update', action='store_true',
            help='Leave existing rows untouched — only create missing ones.',
        )

    def handle(self, *args, **options):
        no_update = options['no_update']
        created = updated = skipped = 0

        for key, lang, category, display_name, description, subject, body_html, variables in SEEDS:
            defaults = {
                'category': category,
                'display_name': display_name,
                'description': description,
                'subject': subject,
                'body_html': body_html,
                'variables': variables,
                'is_active': True,
                'is_system': True,
            }
            obj, was_created = EmailTemplate.objects.get_or_create(
                key=key, language=lang, defaults=defaults,
            )
            if was_created:
                created += 1
                self.stdout.write(self.style.SUCCESS(f'  + {key} [{lang}]'))
            elif no_update:
                skipped += 1
            else:
                changed = False
                for field, value in defaults.items():
                    if getattr(obj, field) != value:
                        setattr(obj, field, value)
                        changed = True
                if changed:
                    obj.save()
                    updated += 1
                    self.stdout.write(f'  ~ {key} [{lang}] (updated)')
                else:
                    skipped += 1

        self.stdout.write(self.style.SUCCESS(
            f'Done. {created} created, {updated} updated, {skipped} unchanged.'
        ))
