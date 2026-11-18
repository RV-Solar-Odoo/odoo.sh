import io

from werkzeug.datastructures import FileStorage

from odoo.tests import TransactionCase, tagged

from odoo.addons.int_crm_customizations.controllers.main import (
    DOCUMENT_FIELD,
    int_tax_exemption_error,
)

PDF = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF\n"


@tagged("post_install", "-at_install")
class TestTaxExemptionForm(TransactionCase):

    def _file(self, name="certificate.pdf", content=PDF):
        return FileStorage(stream=io.BytesIO(content), filename=name, content_type="application/pdf")

    def _reason(self):
        return self.env["crm.lead"]._fields["x_tax_exemption_reason"].get_values(self.env)[0]

    def test_custom_exemption_certificate_upload_counts_and_lands_on_the_lead_field(self):
        # The live form posts the editor's custom upload under its label.
        params = {
            "x_is_tax_exempt": "Yes",
            "x_tax_exemption_reason": self._reason(),
            "Exemption Certificate[2][0]": self._file(),
        }
        self.assertIsNone(int_tax_exemption_error(self.env, params))
        self.assertNotIn("Exemption Certificate[2][0]", params)
        self.assertIn(DOCUMENT_FIELD + "[2][0]", params)

    def test_bound_field_still_works_and_a_missing_file_is_still_refused(self):
        params = {
            "x_is_tax_exempt": "Yes",
            "x_tax_exemption_reason": self._reason(),
            DOCUMENT_FIELD + "[0][0]": self._file(),
        }
        self.assertIsNone(int_tax_exemption_error(self.env, params))
        missing = {"x_is_tax_exempt": "Yes", "x_tax_exemption_reason": self._reason()}
        self.assertIn("upload", int_tax_exemption_error(self.env, missing))

    def test_bmp_certificate_is_accepted(self):
        # A 1x1 BMP: 14-byte file header, 40-byte info header, one padded pixel.
        bmp = (b"BM" + (58).to_bytes(4, "little") + b"\0\0\0\0" + (54).to_bytes(4, "little")
               + (40).to_bytes(4, "little") + (1).to_bytes(4, "little") + (1).to_bytes(4, "little")
               + (1).to_bytes(2, "little") + (24).to_bytes(2, "little") + b"\0" * 24 + b"\xff\xff\xff\0")
        params = {
            "x_is_tax_exempt": "Yes",
            "x_tax_exemption_reason": self._reason(),
            "Exemption Certificate[0][0]": self._file("certificate.BMP", bmp),
        }
        self.assertIsNone(int_tax_exemption_error(self.env, params))

    def test_wrong_file_type_is_refused(self):
        params = {
            "x_is_tax_exempt": "Yes",
            "x_tax_exemption_reason": self._reason(),
            "Exemption Certificate[0][0]": self._file("certificate.pdf", b"not a pdf at all"),
        }
        self.assertIn("PDF, JPG, PNG or BMP", int_tax_exemption_error(self.env, params))

    def test_unticked_box_drops_the_certificate(self):
        params = {
            "x_tax_exemption_reason": self._reason(),
            "Exemption Certificate[0][0]": self._file(),
        }
        self.assertIsNone(int_tax_exemption_error(self.env, params))
        self.assertEqual(params, {})

    def test_studio_checkbox_counts_as_the_claim(self):
        # The form once used the old Studio "Tax Exempt" box with the custom upload.
        params = {
            "x_studio_tax_exempt": "Yes",
            "x_tax_exemption_reason": self._reason(),
            "Exemption Certificate[1][0]": self._file(),
        }
        self.assertIsNone(int_tax_exemption_error(self.env, params))
        self.assertEqual(params["x_is_tax_exempt"], "Yes")
        self.assertIn(DOCUMENT_FIELD + "[1][0]", params)
        self.assertEqual(params["x_tax_exemption_reason"], self._reason())
        missing = {"x_studio_tax_exempt": "Yes", "x_tax_exemption_reason": self._reason()}
        self.assertIn("upload", int_tax_exemption_error(self.env, missing))
