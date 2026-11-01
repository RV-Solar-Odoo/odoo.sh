import json

from odoo import http
from odoo.http import request

from odoo.addons.website.controllers.form import WebsiteForm

# The name each form's model hands to the customer record.
NAME_FIELDS = {
    "helpdesk.ticket": "partner_name",
    "crm.lead": "contact_name",
}


class IntWebsiteForm(WebsiteForm):

    def _int_pop_name_part(self, label):
        """Take a custom form field out of the params, so it stays out of the description.

        The website editor names a custom field after its label, so match loosely.
        Returns None when the form has no such field.
        """
        for key in list(request.params):
            if key.strip().lower().replace("_", " ") == label:
                return str(request.params.pop(key)).strip()
        return None

    @http.route()
    def website_form(self, model_name, **kwargs):
        # Runs ahead of the helpdesk and CRM overrides because this module depends on
        # them. The base method rebuilds its values from request.params.
        name_field = NAME_FIELDS.get(model_name)
        if name_field:
            first = self._int_pop_name_part("first name")
            last = self._int_pop_name_part("last name")
            if first is not None or last is not None:
                if not first or not last:
                    return json.dumps({"error": request.env._("Please enter your first and last name.")})
                request.params[name_field] = f"{first} {last}"
        return super().website_form(model_name, **kwargs)
