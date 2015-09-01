# -*- coding: utf-8 -*-
##############################################################################
#
#    Copyright (C) 2014 Abstract (http://www.abstract.it)
#    Author: Davide Corio <davide.corio@abstract.it>
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation, either version 3 of the License, or
#    (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
##############################################################################

import time
from openerp import models, fields, api


class ResCurrency(models.Model):
    _inherit = 'res.currency'

    def _get_conversion_rate(
            self, cr, uid, from_currency, to_currency, context=None):
        if context is None:
            context = {}
        ctx = context.copy()
        from_currency = self.browse(cr, uid, from_currency.id, context=ctx)
        to_currency = self.browse(cr, uid, to_currency.id, context=ctx)

        from_currency_rate = ctx.get('custom_exchange_rate', False)
        if not from_currency_rate:
            from_currency_rate = from_currency.rate

        if from_currency_rate == 0 or to_currency.rate == 0:
            date = context.get('date', time.strftime('%Y-%m-%d'))
            if from_currency.rate == 0:
                currency_symbol = from_currency.symbol
            else:
                currency_symbol = to_currency.symbol
            raise osv.except_osv(_('Error'), _('No rate found \n' \
                    'for the currency: %s \n' \
                    'at the date: %s') % (currency_symbol, date))
        return to_currency.rate/from_currency_rate


class AccountInvoice(models.Model):
    _inherit = 'account.invoice'

    @api.one
    @api.onchange('currency_id')
    def _get_exchange_rate(self):
        self.custom_exchange_rate = self.currency_id.rate or 1

    custom_exchange_rate = fields.Float(
        'Currency Exchange Rate', digits=(12, 6), default=_get_exchange_rate)

    @api.multi
    def compute_invoice_totals(self, company_currency, ref, invoice_move_lines):
        total = 0
        total_currency = 0
        for line in invoice_move_lines:
            if self.currency_id != company_currency:
                currency = self.currency_id.with_context(
                    date=self.date_invoice or fields.Date.context_today(self))
                line['currency_id'] = currency.id
                line['amount_currency'] = line['price']
                if self.custom_exchange_rate and self.custom_exchange_rate != 1:
                    line['price'] = currency.with_context(
                        {'custom_exchange_rate': self.custom_exchange_rate}
                        ).compute(line['price'], company_currency)
                else:
                    line['price'] = currency.compute(
                        line['price'], company_currency)
            else:
                line['currency_id'] = False
                line['amount_currency'] = False
            line['ref'] = ref
            if self.type in ('out_invoice', 'in_refund'):
                total += line['price']
                total_currency += line['amount_currency'] or line['price']
                line['price'] = - line['price']
            else:
                total -= line['price']
                total_currency -= line['amount_currency'] or line['price']
        return total, total_currency, invoice_move_lines
