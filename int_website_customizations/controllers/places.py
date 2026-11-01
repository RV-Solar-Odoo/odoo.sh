from odoo import http
from odoo.http import request

SUGGEST_LIMIT = 40
DETAILS_LIMIT = 20
VALIDATE_LIMIT = 15


def _within_limit(key, limit):
    count = int(request.session.get(key) or 0)
    if count >= limit:
        return False
    request.session[key] = count + 1
    return True


class PlacesController(http.Controller):

    def _places(self):
        return request.env["int.google.places"].sudo()

    @http.route("/website/places/config", type="jsonrpc", auth="public", website=True)
    def places_config(self):
        return {"enabled": bool(self._places().api_key())}

    @http.route("/website/places/suggest", type="jsonrpc", auth="public", website=True)
    def places_suggest(self, partial="", country_code="", session_token=""):
        if not _within_limit("int_places_suggest", SUGGEST_LIMIT):
            return {"enabled": True, "results": []}
        return {
            "enabled": True,
            "results": self._places().suggest(partial, country_code=country_code, session_token=session_token),
        }

    @http.route("/website/places/details", type="jsonrpc", auth="public", website=True)
    def places_details(self, place_id="", session_token=""):
        if not _within_limit("int_places_details", DETAILS_LIMIT):
            return {"enabled": True, "address": None}
        return {"enabled": True, "address": self._places().details(place_id, session_token=session_token)}

    @http.route("/website/places/validate", type="jsonrpc", auth="public", website=True)
    def places_validate(self, street="", street2="", city="", zip_code="", country_id=False, state_id=False, country_code="", state_name=""):
        # Past the cap, let the customer through. A Google outage or a long
        # edit session should not trap a real order.
        if not _within_limit("int_places_validate", VALIDATE_LIMIT):
            return {"enabled": True, "status": "unavailable"}
        return self._places().validate_address(
            street=street,
            street2=street2,
            city=city,
            zip_code=zip_code,
            country_id=country_id,
            state_id=state_id,
            country_code=country_code,
            state_name=state_name,
        )
