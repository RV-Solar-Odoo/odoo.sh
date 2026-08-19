import json
import logging
import urllib.error
import urllib.request

from odoo import models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

SHIPPO_API = "https://api.goshippo.com"


class ShippoApi(models.AbstractModel):
    _name = "int.shippo.api"
    _description = "Shippo REST helper"

    def _token(self):
        token = self.env["ir.config_parameter"].sudo().get_param("int_shippo.api_token")
        if not token:
            raise UserError(self.env._(
                "Set the Shippo API token under Inventory → Settings → Shippo."
            ))
        return token.strip()

    def request(self, method, path, payload=None):
        data = json.dumps(payload).encode() if payload is not None else None
        req = urllib.request.Request(
            f"{SHIPPO_API}{path}",
            data=data,
            method=method,
            headers={
                "Authorization": f"ShippoToken {self._token()}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                body = resp.read().decode()
                return json.loads(body) if body else {}
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode()
            _logger.warning("Shippo %s %s failed: %s", method, path, detail)
            raise UserError(self.env._("Shippo error %(status)s: %(detail)s", status=exc.code, detail=detail)) from exc
        except urllib.error.URLError as exc:
            raise UserError(self.env._("Could not reach Shippo: %s", exc.reason)) from exc
