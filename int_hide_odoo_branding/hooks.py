import logging
import re

_logger = logging.getLogger(__name__)

_LINK = r"Powered\s+by\s*<a\b[^>]*>.*?</a>\.?"
# The whole footer row, when the credit is all that's in it.
_ROW = re.compile(
    r"(?:<!--\s*POWERED BY\s*-->\s*)?"
    r"<tr[^>]*>\s*<td[^>]*>\s*"
    r"(?:<table[^>]*>\s*<tr[^>]*>\s*<td[^>]*>\s*)?"
    + _LINK +
    r"\s*(?:</td>\s*</tr>\s*</table>\s*)?"
    r"</td>\s*</tr>",
    re.IGNORECASE | re.DOTALL,
)
# Otherwise only the credit, so anything beside it (like Unfollow) stays.
_CREDIT = re.compile(r"(?:<!--\s*POWERED BY\s*-->\s*)?" + _LINK, re.IGNORECASE | re.DOTALL)
SIGNATURE_LAYOUT = "int_hide_odoo_branding.mail_notification_signature_only"


def strip_powered_by(html):
    return _CREDIT.sub("", _ROW.sub("", html))


def post_init_hook(env):
    """Saved email templates are noupdate records, so views can't reach them."""
    env["mail.template"].with_context(active_test=False).search([
        ("email_layout_xmlid", "=", False),
    ]).write({
        "email_layout_xmlid": SIGNATURE_LAYOUT,
    })

    templates = env["mail.template"].with_context(active_test=False).search([("body_html", "ilike", "powered by")])
    for lang, _name in env["res.lang"].get_installed():
        for template in templates.with_context(lang=lang):
            body = str(template.body_html or "")
            cleaned = strip_powered_by(body)
            if cleaned != body:
                template.body_html = cleaned
                _logger.info("Removed Powered by Odoo from mail template %s (%s)", template.id, lang)
