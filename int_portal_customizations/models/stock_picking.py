from odoo import models


class StockPicking(models.Model):
    _inherit = "stock.picking"

    def _int_portal_tracking_links(self):
        """Tracking numbers on this shipment, each with a link when one exists.

        Several numbers in one reference are split. A link is kept only when it
        belongs to a single number. A missing link leaves the number as text.
        """
        self.ensure_one()
        multiple = self._int_portal_multiple_tracking()
        if multiple:
            return multiple
        ref = (self.carrier_tracking_ref or "").strip()
        if not ref:
            return []
        parts = [part.strip() for part in ref.split(",") if part.strip()]
        url = self.carrier_tracking_url or ""
        if len(parts) == 1 and self._int_portal_http_url(url):
            return [{"number": parts[0], "url": url}]
        return [{"number": part, "url": False} for part in parts]

    def _int_portal_multiple_tracking(self):
        if not hasattr(self, "get_multiple_carrier_tracking"):
            return []
        parsed = self.get_multiple_carrier_tracking()
        if not isinstance(parsed, (list, tuple)):
            return []
        links = []
        for line in parsed:
            number = False
            url = False
            if isinstance(line, (list, tuple)) and line:
                number = str(line[0] or "").strip()
                url = line[1] if len(line) > 1 else False
            elif isinstance(line, dict):
                number = str(line.get("tracking_number") or line.get("name") or "").strip()
                url = line.get("url")
            if not number:
                continue
            links.append({
                "number": number,
                "url": url if self._int_portal_http_url(url) else False,
            })
        return links

    @staticmethod
    def _int_portal_http_url(url):
        return isinstance(url, str) and url.startswith(("http://", "https://"))
