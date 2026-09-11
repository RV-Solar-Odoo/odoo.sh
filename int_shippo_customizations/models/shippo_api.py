import json
import logging
import time
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

    def request(self, method, path, payload=None, timeout=60, retries=0):
        data = json.dumps(payload).encode() if payload is not None else None
        token = self._token()
        for attempt in range(retries + 1):
            req = urllib.request.Request(
                f"{SHIPPO_API}{path}",
                data=data,
                method=method,
                headers={
                    "Authorization": f"ShippoToken {token}",
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
            )
            try:
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    body = resp.read().decode()
            except urllib.error.HTTPError as exc:
                detail = exc.read().decode()
                # Rate limits and server errors are worth another go; a 4xx is our
                # own bad request and will fail identically every time.
                retryable = exc.code == 429 or exc.code >= 500
                if not retryable or attempt == retries:
                    _logger.warning("Shippo %s %s failed: %s", method, path, detail)
                    raise UserError(self.env._(
                        "Shippo error %(status)s: %(detail)s", status=exc.code, detail=detail
                    )) from exc
                _logger.warning(
                    "Shippo %s %s returned %s, retrying: %s", method, path, exc.code, detail
                )
            except OSError as exc:
                if attempt == retries:
                    raise UserError(self.env._("Could not reach Shippo: %s", exc)) from exc
                _logger.warning("Shippo %s %s unreachable, retrying: %s", method, path, exc)
            else:
                try:
                    return json.loads(body) if body else {}
                except ValueError as exc:
                    # A proxy or outage page can answer 200 with HTML; treat it like
                    # any other failed call instead of crashing the caller.
                    raise UserError(self.env._("Shippo returned a response that is not JSON.")) from exc
            # An instant retry against a rate limit or a wobbling server just fails
            # again; give it a moment.
            time.sleep(1)
        raise UserError(self.env._("Could not reach Shippo after %s attempts.", retries + 1))
