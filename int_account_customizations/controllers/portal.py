from odoo.http import request, route

from odoo.addons.account.controllers.portal import PortalAccount


def _int_hide_invoices():
    user = request.env.user
    return not user._is_public() and user.share and not user.int_portal_can("view_invoices")


class PortalAccount(PortalAccount):

    @route(["/my/invoices", "/my/invoices/page/<int:page>"], type="http", auth="user", website=True)
    def portal_my_invoices(self, page=1, date_begin=None, date_end=None, sortby=None, filterby=None, **kw):
        if _int_hide_invoices():
            return request.redirect("/my")
        return super().portal_my_invoices(
            page=page, date_begin=date_begin, date_end=date_end, sortby=sortby, filterby=filterby, **kw,
        )

    @route(["/my/invoices/<int:invoice_id>"], type="http", auth="public", website=True)
    def portal_my_invoice_detail(self, invoice_id, access_token=None, report_type=None, download=False, **kw):
        if _int_hide_invoices():
            return request.redirect("/my")
        return super().portal_my_invoice_detail(
            invoice_id, access_token=access_token, report_type=report_type, download=download, **kw,
        )

