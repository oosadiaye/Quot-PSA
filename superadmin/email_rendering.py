"""Email rendering helpers: beautified base layout + placeholder substitution.

The "base layout" is an email-safe HTML wrapper (table-based, inline CSS, MSO
fallbacks) that mirrors the PageHeader gradient used elsewhere in the app.
Seed templates inject their content via the ``{content}`` placeholder after
the wrapper has been resolved — so SuperAdmin editors can focus on the body
and never have to touch the fragile outer chrome.
"""
from __future__ import annotations

import re
from html import escape
from typing import Any, Dict


# Brand gradient mirrors frontend/src/components/layout (#242a88 → #2e35a0).
BRAND_PRIMARY = '#242a88'
BRAND_PRIMARY_ALT = '#2e35a0'
BRAND_ACCENT = '#f59e0b'


def base_layout(
    *,
    title: str,
    content_html: str,
    org_name: str = 'QUOT ERP',
    support_email: str = 'support@quot-erp.com',
    preheader: str = '',
) -> str:
    """Wrap ``content_html`` in the beautified email chrome.

    All CSS is inline. Uses a 600-px centered table (the only reliable
    layout primitive across Outlook, Gmail, and Apple Mail).
    """
    preheader_html = (
        f'<div style="display:none;max-height:0;overflow:hidden;opacity:0;'
        f'font-size:1px;line-height:1px;color:#ffffff;">{escape(preheader)}</div>'
        if preheader else ''
    )

    return f"""<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{escape(title)}</title>
    <!--[if mso]><style>table{{border-collapse:collapse;mso-table-lspace:0;mso-table-rspace:0;}}</style><![endif]-->
  </head>
  <body style="margin:0;padding:0;background:#f1f5f9;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;color:#0b1320;">
    {preheader_html}
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f1f5f9;padding:32px 0;">
      <tr>
        <td align="center">
          <table role="presentation" width="600" cellpadding="0" cellspacing="0" style="max-width:600px;width:100%;background:#ffffff;border-radius:14px;overflow:hidden;box-shadow:0 4px 18px rgba(15,23,42,0.08);">
            <!-- Header -->
            <tr>
              <td style="background:linear-gradient(135deg,{BRAND_PRIMARY} 0%,{BRAND_PRIMARY_ALT} 100%);padding:28px 32px;">
                <table role="presentation" width="100%" cellpadding="0" cellspacing="0">
                  <tr>
                    <td>
                      <div style="color:rgba(255,255,255,0.72);font-size:11px;font-weight:700;letter-spacing:2px;text-transform:uppercase;margin-bottom:6px;">{escape(org_name)}</div>
                      <div style="color:#ffffff;font-size:22px;font-weight:700;line-height:1.25;">{escape(title)}</div>
                    </td>
                  </tr>
                </table>
              </td>
            </tr>
            <!-- Content -->
            <tr>
              <td style="padding:32px;font-size:15px;line-height:1.65;color:#0b1320;">
                {content_html}
              </td>
            </tr>
            <!-- Footer -->
            <tr>
              <td style="padding:20px 32px 28px 32px;border-top:1px solid #eef2f7;background:#fafbfd;">
                <div style="font-size:12px;color:#64748b;line-height:1.55;">
                  Need help? Contact us at
                  <a href="mailto:{escape(support_email)}" style="color:{BRAND_PRIMARY};text-decoration:none;">{escape(support_email)}</a>.<br>
                  This is an automated message from {escape(org_name)}.
                </div>
              </td>
            </tr>
          </table>
          <div style="font-size:11px;color:#94a3b8;margin-top:16px;">
            &copy; {escape(org_name)}. All rights reserved.
          </div>
        </td>
      </tr>
    </table>
  </body>
</html>
"""


_TAG_RE = re.compile(r'<[^>]+>')


def strip_html(html: str) -> str:
    """Crude HTML → plain-text fallback (only used when body_text is blank)."""
    text = _TAG_RE.sub('', html)
    # Collapse runs of whitespace but keep paragraph breaks.
    text = re.sub(r'\n\s*\n', '\n\n', text)
    text = re.sub(r'[ \t]+', ' ', text)
    return text.strip()


class _SafeDict(dict):
    """dict subclass that leaves unknown {placeholders} in place instead of KeyError.

    Protects SuperAdmin editors from subtle breakages when a template references
    a variable the caller didn't supply — the placeholder renders literally and
    the email still goes out.
    """

    def __missing__(self, key):  # type: ignore[override]
        return '{' + key + '}'


def substitute(template_str: str, context: Dict[str, Any]) -> str:
    """Format ``template_str`` using str.format_map with safe missing-key behavior."""
    # Stringify all values so Decimal / datetime / None don't crash format().
    safe_ctx = _SafeDict({k: ('' if v is None else v) for k, v in context.items()})
    try:
        return template_str.format_map(safe_ctx)
    except (IndexError, ValueError):
        # Fall back to literal on malformed format strings.
        return template_str
