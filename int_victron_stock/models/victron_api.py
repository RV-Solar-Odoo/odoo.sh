import base64
import json
import logging
import urllib.error
import urllib.request

from odoo import models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

VICTRON_API = "https://eorder.victronenergy.com/api/v1"
# Stop following "next" links after this many pages so a malformed feed cannot spin forever.
MAX_PAGES = 200


class VictronApi(models.AbstractModel):
    _name = "int.victron.api"
    _description = "Victron E-Order REST helper"

    def _auth_header(self):
        icp = self.env["ir.config_parameter"].sudo()
        username = (icp.get_param("int_victron.username") or "").strip()
        password = (icp.get_param("int_victron.password") or "").strip()
        if not username or not password:
            raise UserError(self.env._(
                "Set the Victron E-Order username and password under Inventory → Settings → Victron E-Order."
            ))
        raw = base64.b64encode(f"{username}:{password}".encode()).decode()
        return f"Basic {raw}"

    def fetch_all(self, path):
        """Return every row from a paginated E-Order list endpoint."""
        auth = self._auth_header()
        url = f"{VICTRON_API}{path}"
        rows = []
        seen = set()
        while url and url not in seen and len(seen) < MAX_PAGES:
            seen.add(url)
            payload = self._get(url, auth)
            if isinstance(payload, list):
                rows.extend(payload)
                break
            if not isinstance(payload, dict):
                break
            rows.extend(
                payload.get("results")
                or payload.get("data")
                or payload.get("products")
                or []
            )
            url = payload.get("next") or payload.get("next_page_url") or None
        return rows

    def _get(self, url, auth):
        req = urllib.request.Request(
            url,
            method="GET",
            headers={"Authorization": auth, "Accept": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                body = resp.read().decode()
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode()[:500]
            _logger.warning("Victron GET %s failed: %s", url, detail)
            raise UserError(self.env._(
                "Victron E-Order error %(status)s: %(detail)s", status=exc.code, detail=detail
            )) from exc
        except urllib.error.URLError as exc:
            raise UserError(self.env._("Could not reach Victron E-Order: %s", exc.reason)) from exc
        try:
            return json.loads(body) if body else {}
        except ValueError as exc:
            raise UserError(self.env._("Victron E-Order returned a response that is not JSON.")) from exc
