from odoo.http import route

from odoo.addons.website_sale.controllers.main import WebsiteSale


class WebsiteSaleDocumentView(WebsiteSale):

    @route()
    def product_document(self, product_template, document_id, download='1', **kwargs):
        """Same route as website_sale (/shop/<product>/document/<id>), with one
        addition: ``?download=0`` serves a PDF or image inline so the browser can
        show it in a tab instead of saving it. Other file types are still saved.
        All access checks are still done by the parent method; we only rewrite the
        Content-Disposition header.
        """
        response = super().product_document(product_template, document_id)
        viewable = response.mimetype == 'application/pdf' or response.mimetype.startswith('image/')
        if str(download).lower() in ('0', 'false', 'no', 'inline') and viewable:
            disposition = response.headers.get('Content-Disposition', '')
            if disposition.startswith('attachment'):
                response.headers['Content-Disposition'] = 'inline' + disposition[len('attachment'):]
        return response
