import logging
import re
import uuid

import requests

from odoo import models

_logger = logging.getLogger(__name__)

PLACES_AUTOCOMPLETE = "https://places.googleapis.com/v1/places:autocomplete"
PLACES_DETAILS = "https://places.googleapis.com/v1/places/"
ADDRESS_VALIDATION = "https://addressvalidation.googleapis.com/v1:validateAddress"
TIMEOUT = 5
PLACE_ID = re.compile(r"^[A-Za-z0-9_-]{8,300}$")

# First matching type on a component wins. Earlier names are preferred when several could fill one field.
COMPONENT_PRIORITY = (
    "street_number",
    "route",
    "subpremise",
    "locality",
    "postal_town",
    "postal_code",
    "administrative_area_level_1",
    "country",
)
IMPORTANT = {
    "street_number",
    "route",
    "locality",
    "postal_town",
    "postal_code",
    "administrative_area_level_1",
    "country",
}
LABELS = {
    "street_number": "street number",
    "route": "street",
    "locality": "city",
    "postal_town": "city",
    "postal_code": "ZIP code",
    "administrative_area_level_1": "state",
    "country": "country",
}
ADDRESS_TYPES = {"street_address", "premise", "subpremise", "route", "street_number"}
PREMISE = {"PREMISE", "SUB_PREMISE"}
NEARBY = {"PREMISE_PROXIMITY"}
# A ZIP+4 that Google adds is not a reason to stop the customer.
HARMLESS = {"postal_code_suffix"}


class IntGooglePlaces(models.AbstractModel):
    _name = "int.google.places"
    _description = "Google Places address check"

    def api_key(self):
        return (self.env["ir.config_parameter"].sudo().get_param("int_website.google_places_api_key") or "").strip()

    def suggest(self, partial, country_code=None, session_token=None):
        partial = (partial or "").strip()
        if not self.api_key() or len(partial) < 3 or len(partial) > 200:
            return []
        body = {"input": partial, "languageCode": "en"}
        code = (country_code or "").strip().upper()
        if re.fullmatch(r"[A-Z]{2}", code):
            body["includedRegionCodes"] = [code]
        token = self._session_token(session_token)
        if token:
            body["sessionToken"] = token
        data = self._post(
            PLACES_AUTOCOMPLETE,
            body,
            field_mask="suggestions.placePrediction.placeId,suggestions.placePrediction.text.text,suggestions.placePrediction.types",
        )
        if not data:
            return []
        results = []
        for suggestion in data.get("suggestions") or []:
            prediction = suggestion.get("placePrediction") or {}
            place_id = prediction.get("placeId")
            label = ((prediction.get("text") or {}).get("text") or "").strip()
            kinds = set(prediction.get("types") or [])
            if kinds and kinds.isdisjoint(ADDRESS_TYPES):
                continue
            if place_id and label and PLACE_ID.match(place_id):
                results.append({"label": label, "place_id": place_id})
        return results

    def details(self, place_id, session_token=None):
        if not self.api_key() or not PLACE_ID.match(place_id or ""):
            return None
        params = {}
        token = self._session_token(session_token)
        if token:
            params["sessionToken"] = token
        data = self._get(
            PLACES_DETAILS + place_id,
            params,
            field_mask="addressComponents,formattedAddress",
        )
        if not data:
            return None
        return self._from_components(data.get("addressComponents") or [])

    def validate_address(self, street="", street2="", city="", zip_code="", country_id=False, state_id=False, country_code="", state_name=""):
        """Ask Address Validation whether this address is complete and real.

        ``accept`` means Google confirmed it. ``confirm`` means Google has a
        corrected version the customer should accept. ``fix`` means it should
        not be saved. ``unavailable`` means Google did not answer, and the
        form is allowed through so a Google outage does not stop checkout.
        """
        if not self.api_key():
            return {"enabled": False}
        street = (street or "").strip()
        street2 = (street2 or "").strip()
        city = (city or "").strip()
        zip_code = (zip_code or "").strip()
        if not street:
            return {"enabled": True, "status": "accept", "address": self._empty_address()}
        country, state = self._country_and_state(country_id, state_id, country_code, state_name)
        region = country.code if country else ""
        lines = [line for line in (street, street2) if line]
        address = {"addressLines": lines, "languageCode": "en"}
        if region:
            address["regionCode"] = region
        if city:
            address["locality"] = city
        if zip_code:
            address["postalCode"] = zip_code
        admin = state.code if state and state.code else (state_name or "").strip()
        if admin and admin.lower() not in ("state / province...", "state", "province"):
            address["administrativeArea"] = admin
        data = self._post(ADDRESS_VALIDATION, {"address": address})
        if not data or "result" not in data:
            return {"enabled": True, "status": "unavailable"}
        return self._verdict(data["result"], street2)

    def _verdict(self, result, typed_street2):
        verdict = result.get("verdict") or {}
        address = result.get("address") or {}
        components = address.get("addressComponents") or []
        granularity = verdict.get("validationGranularity") or "GRANULARITY_UNSPECIFIED"
        parsed = self._from_postal(address.get("postalAddress") or {})
        if typed_street2 and not parsed["street2"]:
            parsed["street2"] = typed_street2
        formatted = (address.get("formattedAddress") or "").strip()
        payload = {
            "enabled": True,
            "formatted": formatted,
            "address": parsed,
            "message": "",
            "status": "accept",
        }
        suspicious = self._levels(components, "UNCONFIRMED_AND_SUSPICIOUS")
        plausible = self._levels(components, "UNCONFIRMED_BUT_PLAUSIBLE")
        if not verdict.get("addressComplete") or granularity not in PREMISE | NEARBY or suspicious:
            payload["status"] = "fix"
            payload["message"] = self._fix_message(granularity, suspicious, formatted)
            return payload
        if (
            granularity in NEARBY
            or plausible
            or verdict.get("hasReplacedComponents")
            or self._material_inference(components, verdict)
        ):
            payload["status"] = "confirm"
            payload["message"] = f"Google suggests: {formatted}" if formatted else "Google suggests a corrected address."
            return payload
        return payload

    def _material_inference(self, components, verdict):
        if not verdict.get("hasInferredComponents"):
            return False
        inferred = [component.get("componentType") for component in components if component.get("inferred")]
        if not inferred:
            return True
        return any(kind not in HARMLESS for kind in inferred)

    def _levels(self, components, level):
        kinds = []
        for component in components:
            kind = component.get("componentType")
            if kind in IMPORTANT and component.get("confirmationLevel") == level and kind not in kinds:
                kinds.append(kind)
        return kinds

    def _fix_message(self, granularity, suspicious, formatted):
        if granularity not in PREMISE | NEARBY:
            message = "Enter a street number Google recognizes."
        elif suspicious:
            names = []
            for kind in suspicious:
                label = LABELS.get(kind)
                if label and label not in names:
                    names.append(label)
            message = "Google could not confirm the %s." % " and ".join(names)
        else:
            message = "Google could not confirm this address."
        if formatted:
            message = f"{message} Google has: {formatted}"
        return message

    def _from_postal(self, postal):
        lines = [line.strip() for line in (postal.get("addressLines") or []) if (line or "").strip()]
        return self._lookup(
            street=lines[0] if lines else "",
            street2=", ".join(lines[1:]),
            city=(postal.get("locality") or "").strip(),
            zip_code=(postal.get("postalCode") or "").strip(),
            state_text=(postal.get("administrativeArea") or "").strip(),
            country_code=(postal.get("regionCode") or "").strip(),
        )

    def _from_components(self, components):
        chosen = {}
        for component in components:
            for kind in COMPONENT_PRIORITY:
                if kind in chosen:
                    continue
                if kind in (component.get("types") or []):
                    chosen[kind] = component
                    break
        number = self._text(chosen.get("street_number"))
        route = self._text(chosen.get("route"))
        street = f"{number} {route}".strip()
        state_component = chosen.get("administrative_area_level_1")
        return self._lookup(
            street=street,
            street2=self._text(chosen.get("subpremise")),
            city=self._text(chosen.get("locality")) or self._text(chosen.get("postal_town")),
            zip_code=self._text(chosen.get("postal_code")),
            state_text=self._text(state_component, short=True),
            country_code=self._text(chosen.get("country"), short=True),
        )

    def _lookup(self, street, street2, city, zip_code, state_text, country_code):
        country, state = self._country_and_state(False, False, country_code, state_text)
        return {
            "street": street,
            "street2": street2,
            "city": city,
            "zip_code": zip_code,
            "country_id": country.id if country else False,
            "state_id": state.id if state else False,
        }

    def _country_and_state(self, country_id, state_id, country_code, state_name):
        Country = self.env["res.country"].sudo()
        State = self.env["res.country.state"].sudo()
        country = Country.browse(self._int(country_id)).exists()
        if not country and country_code:
            country = Country.search([("code", "=", country_code.strip().upper())], limit=1)
        state = State.browse(self._int(state_id)).exists()
        if state and country and state.country_id != country:
            state = State
        text = (state_name or "").strip()
        if not state and country and text:
            state = State.search([("country_id", "=", country.id), ("code", "=", text.upper())], limit=1)
            if not state:
                state = State.search([("country_id", "=", country.id), ("name", "=ilike", text)], limit=1)
        return country, state

    def _empty_address(self):
        return {"street": "", "street2": "", "city": "", "zip_code": "", "country_id": False, "state_id": False}

    def _text(self, component, short=False):
        if not component:
            return ""
        if short:
            return (component.get("shortText") or component.get("longText") or "").strip()
        return (component.get("longText") or component.get("shortText") or "").strip()

    def _session_token(self, token):
        try:
            return str(uuid.UUID(str(token)))
        except (ValueError, TypeError, AttributeError):
            return None

    def _int(self, value):
        try:
            return int(value)
        except (TypeError, ValueError):
            return 0

    def _headers(self, field_mask):
        headers = {"X-Goog-Api-Key": self.api_key(), "Content-Type": "application/json"}
        if field_mask:
            headers["X-Goog-FieldMask"] = field_mask
        return headers

    def _post(self, url, body, field_mask=None):
        try:
            response = requests.post(url, json=body, headers=self._headers(field_mask), timeout=TIMEOUT)
        except requests.RequestException as error:
            _logger.warning("Google Places request failed: %s", error)
            return None
        return self._json(response)

    def _get(self, url, params, field_mask):
        try:
            response = requests.get(url, params=params, headers=self._headers(field_mask), timeout=TIMEOUT)
        except requests.RequestException as error:
            _logger.warning("Google Places request failed: %s", error)
            return None
        return self._json(response)

    def _json(self, response):
        try:
            data = response.json()
        except ValueError:
            _logger.warning("Google Places returned a non-JSON response (%s).", response.status_code)
            return None
        if response.status_code >= 400 or (isinstance(data, dict) and data.get("error")):
            message = response.status_code
            if isinstance(data, dict):
                message = (data.get("error") or {}).get("message") or message
            _logger.warning("Google Places error: %s", message)
            return None
        return data
