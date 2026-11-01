from unittest.mock import Mock, patch

from odoo.tests import TransactionCase, tagged

from odoo.addons.int_website_customizations.models.google_places import IntGooglePlaces


def _response(payload, status=200):
    response = Mock()
    response.status_code = status
    response.json.return_value = payload
    return response


def _validation(granularity="PREMISE", complete=True, replaced=False, inferred=False, components=None, lines=None):
    return {
        "result": {
            "verdict": {
                "validationGranularity": granularity,
                "addressComplete": complete,
                "hasReplacedComponents": replaced,
                "hasInferredComponents": inferred,
            },
            "address": {
                "formattedAddress": "1600 Amphitheatre Pkwy, Mountain View, CA 94043-1351, USA",
                "postalAddress": {
                    "regionCode": "US",
                    "postalCode": "94043-1351",
                    "administrativeArea": "CA",
                    "locality": "Mountain View",
                    "addressLines": lines or ["1600 Amphitheatre Pkwy"],
                },
                "addressComponents": components if components is not None else [
                    {"componentType": "street_number", "confirmationLevel": "CONFIRMED"},
                    {"componentType": "route", "confirmationLevel": "CONFIRMED"},
                    {"componentType": "locality", "confirmationLevel": "CONFIRMED"},
                    {"componentType": "administrative_area_level_1", "confirmationLevel": "CONFIRMED"},
                    {"componentType": "postal_code", "confirmationLevel": "CONFIRMED"},
                    {"componentType": "country", "confirmationLevel": "CONFIRMED"},
                ],
            },
        }
    }


@tagged("post_install", "-at_install")
class TestGooglePlaces(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.places = cls.env["int.google.places"]
        cls.us = cls.env.ref("base.us")
        cls.california = cls.env["res.country.state"].search([
            ("country_id", "=", cls.us.id),
            ("code", "=", "CA"),
        ], limit=1)
        if not cls.california:
            raise AssertionError("United States states are not loaded")
        cls.env["ir.config_parameter"].sudo().set_param("int_website.google_places_api_key", "")

    def test_missing_key_does_not_call_google(self):
        with patch.object(IntGooglePlaces, "_post") as post:
            self.assertEqual(self.places.suggest("1600 Amphitheatre"), [])
            self.assertFalse(self.places.validate_address(street="1600 Amphitheatre")["enabled"])
            post.assert_not_called()

    def test_suggest_reads_place_predictions(self):
        self.env["ir.config_parameter"].sudo().set_param("int_website.google_places_api_key", "test-key")
        payload = {"suggestions": [
            {"placePrediction": {
                "placeId": "ChIJabcdefghijk",
                "text": {"text": "1600 Amphitheatre Pkwy, Mountain View, CA, USA"},
                "types": ["street_address", "geocode"],
            }},
            {"placePrediction": {
                "placeId": "ChIJmuseummuseum",
                "text": {"text": "Amoeba Music, San Francisco, CA, USA"},
                "types": ["establishment", "point_of_interest"],
            }},
            {"queryPrediction": {"text": {"text": "ignored"}}},
            {"placePrediction": {"placeId": "bad id", "text": {"text": "dropped"}}},
        ]}
        with patch.object(IntGooglePlaces, "_post", return_value=payload) as post:
            results = self.places.suggest("1600 Amp", country_code="us", session_token="not-a-uuid")
        self.assertEqual(results, [{
            "label": "1600 Amphitheatre Pkwy, Mountain View, CA, USA",
            "place_id": "ChIJabcdefghijk",
        }])
        body = post.call_args.args[1]
        self.assertEqual(body["includedRegionCodes"], ["US"])
        self.assertNotIn("sessionToken", body)

    def test_details_fill_country_and_state(self):
        self.env["ir.config_parameter"].sudo().set_param("int_website.google_places_api_key", "test-key")
        payload = {"addressComponents": [
            {"types": ["street_number"], "longText": "1600", "shortText": "1600"},
            {"types": ["route"], "longText": "Amphitheatre Parkway", "shortText": "Amphitheatre Pkwy"},
            {"types": ["locality", "political"], "longText": "Mountain View", "shortText": "Mountain View"},
            {"types": ["administrative_area_level_1", "political"], "longText": "California", "shortText": "CA"},
            {"types": ["postal_code"], "longText": "94043", "shortText": "94043"},
            {"types": ["country", "political"], "longText": "United States", "shortText": "US"},
            {"types": ["subpremise"], "longText": "Suite 4", "shortText": "Suite 4"},
        ]}
        with patch.object(IntGooglePlaces, "_get", return_value=payload):
            address = self.places.details("ChIJabcdefghijk", session_token="6f9619ff-8b86-d011-b42d-00cf4fc964ff")
        self.assertEqual(address["street"], "1600 Amphitheatre Parkway")
        self.assertEqual(address["street2"], "Suite 4")
        self.assertEqual(address["city"], "Mountain View")
        self.assertEqual(address["zip_code"], "94043")
        self.assertEqual(address["country_id"], self.us.id)
        self.assertEqual(address["state_id"], self.california.id)

    def test_details_rejects_a_bad_place_id(self):
        self.env["ir.config_parameter"].sudo().set_param("int_website.google_places_api_key", "test-key")
        with patch.object(IntGooglePlaces, "_get") as get:
            self.assertIsNone(self.places.details("../secret"))
            get.assert_not_called()

    def test_complete_address_is_accepted_and_keeps_the_apartment(self):
        self.env["ir.config_parameter"].sudo().set_param("int_website.google_places_api_key", "test-key")
        with patch.object(IntGooglePlaces, "_post", return_value=_validation()):
            result = self.places.validate_address(
                street="1600 Amphitheatre Parkway",
                street2="Suite 4",
                city="Mountain View",
                zip_code="94043",
                country_id=self.us.id,
                state_id=self.california.id,
            )
        self.assertEqual(result["status"], "accept")
        self.assertEqual(result["address"]["street2"], "Suite 4")
        self.assertEqual(result["address"]["zip_code"], "94043-1351")
        self.assertEqual(result["address"]["state_id"], self.california.id)

    def test_missing_street_number_must_be_fixed(self):
        self.env["ir.config_parameter"].sudo().set_param("int_website.google_places_api_key", "test-key")
        with patch.object(IntGooglePlaces, "_post", return_value=_validation(granularity="ROUTE", complete=False)):
            result = self.places.validate_address(street="Amphitheatre Parkway", city="Mountain View", country_code="US")
        self.assertEqual(result["status"], "fix")
        self.assertIn("street number", result["message"])

    def test_replaced_address_asks_for_confirmation(self):
        self.env["ir.config_parameter"].sudo().set_param("int_website.google_places_api_key", "test-key")
        with patch.object(IntGooglePlaces, "_post", return_value=_validation(replaced=True)):
            result = self.places.validate_address(street="1600 Amphitheatre", city="Mountain View", country_code="US")
        self.assertEqual(result["status"], "confirm")
        self.assertIn("1600 Amphitheatre Pkwy", result["message"])

    def test_zip_suffix_alone_does_not_ask_for_confirmation(self):
        self.env["ir.config_parameter"].sudo().set_param("int_website.google_places_api_key", "test-key")
        components = [
            {"componentType": "street_number", "confirmationLevel": "CONFIRMED"},
            {"componentType": "postal_code_suffix", "confirmationLevel": "CONFIRMED", "inferred": True},
        ]
        with patch.object(IntGooglePlaces, "_post", return_value=_validation(inferred=True, components=components)):
            result = self.places.validate_address(street="1600 Amphitheatre Pkwy", country_code="US")
        self.assertEqual(result["status"], "accept")

    def test_suspicious_street_number_must_be_fixed(self):
        self.env["ir.config_parameter"].sudo().set_param("int_website.google_places_api_key", "test-key")
        components = [
            {"componentType": "street_number", "confirmationLevel": "UNCONFIRMED_AND_SUSPICIOUS"},
            {"componentType": "route", "confirmationLevel": "CONFIRMED"},
        ]
        with patch.object(IntGooglePlaces, "_post", return_value=_validation(components=components)):
            result = self.places.validate_address(street="99999 Nowhere", country_code="US")
        self.assertEqual(result["status"], "fix")
        self.assertIn("street number", result["message"])

    def test_google_error_lets_the_form_through(self):
        self.env["ir.config_parameter"].sudo().set_param("int_website.google_places_api_key", "test-key")
        with patch.object(IntGooglePlaces, "_post", return_value=None):
            result = self.places.validate_address(street="1600 Amphitheatre", country_code="US")
        self.assertEqual(result["status"], "unavailable")
