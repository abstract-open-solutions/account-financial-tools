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
from openerp.osv import osv
from openerp.osv import fields as oldfields
from openerp.tools.translate import _
import openerp.addons.decimal_precision as dp


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


class AccountInvoiceLine(models.Model):
    _inherit = 'account.invoice.line'

    base_currency_price_unit = fields.Float(
        string='Base Currency Unit Price',
        digits=dp.get_precision('Product Price'))

    @api.onchange('base_currency_price_unit')
    def onchange_base_currency_price_unit(self):
        rate = self.invoice_id.custom_exchange_rate
        self.price_unit = self.base_currency_price_unit * rate


class AccountVoucherLine(models.Model):
    _inherit = 'account.voucher.line'

    @api.onchange('amount_currency')
    def onchange_amount_currency(self):
        move = self.move_line_id.move_id
        invoice_model = self.env['account.invoice']
        invoice = invoice_model.search([('move_id', '=', move.id)])
        rate = invoice.custom_exchange_rate
        if self.amount and rate:
            self.amount = self.amount_currency / rate

    @api.one
    def _get_amount_original_currency(self):
        move = self.move_line_id.move_id
        invoice_model = self.env['account.invoice']
        invoice = invoice_model.search([('move_id', '=', move.id)])
        rate = invoice.custom_exchange_rate
        self.amount_original_currency = self.amount_original * rate

    @api.one
    def _get_amount_unreconciled_currency(self):
        move = self.move_line_id.move_id
        invoice_model = self.env['account.invoice']
        invoice = invoice_model.search([('move_id', '=', move.id)])
        rate = invoice.custom_exchange_rate
        self.amount_unreconciled_currency = self.amount_unreconciled * rate

    amount_currency = fields.Float(
        string='Amount Currency',
        digits=dp.get_precision('Account'))
    amount_original_currency = fields.Float(
        string='Original Amount Currency',
        digits=dp.get_precision('Account'),
        compute='_get_amount_original_currency')
    amount_unreconciled_currency = fields.Float(
        string='Residual Amount Currency',
        digits=dp.get_precision('Account'),
        compute='_get_amount_unreconciled_currency')
    payment_rate = fields.Float(related='voucher_id.payment_rate')


class AccountVoucher(models.Model):
    _inherit = 'account.voucher'

    def create(self, cr, uid, vals, context=None):
        context = context or {}
        if vals['payment_rate'] != 1:
            dr_total = 0
            fee = vals['bank_fee']
            for line in vals['line_dr_ids']:
                dr_total += line[2]['amount_currency']

        if (dr_total + fee) != vals['amount']:
            raise osv.except_osv(
                _('Error'),
                _('Amount allocated differs from voucher amount'))

        return super(AccountVoucher, self).create(cr, uid, vals, context)

    def _get_writeoff_amount(self, cr, uid, ids, name, args, context=None):
        if not ids:
            return {}
        currency_obj = self.pool.get('res.currency')
        res = {}
        for voucher in self.browse(cr, uid, ids, context=context):
            debit = credit = 0.0
            sign = voucher.type == 'payment' and -1 or 1
            for l in voucher.line_dr_ids:
                debit += l.amount
            for l in voucher.line_cr_ids:
                credit += l.amount
            currency = voucher.currency_id or voucher.company_id.currency_id
            if voucher.payment_rate != 1:
                writeoff_amount = (
                    voucher.amount - voucher.bank_fee) / voucher.payment_rate
            else:
                writeoff_amount = voucher.amount - voucher.bank_fee
            res[voucher.id] = currency_obj.round(
                cr, uid, currency, writeoff_amount - sign * (credit - debit))
        return res

    def _get_custom_curr_help_label(
            self, cr, uid, currency_id, payment_rate, payment_rate_currency_id,
            context=None):
        currency_pool = self.pool.get('res.currency')
        currency_str = payment_rate_str = ''
        if currency_id:
            currency_str = currency_pool.browse(
                cr, uid, currency_id, context=context).symbol
        if payment_rate_currency_id:
            payment_rate_str = currency_pool.browse(
                cr, uid, payment_rate_currency_id, context=context).symbol
        currency_help_label = _('Rate %s/%s') % (
            currency_str, payment_rate_str)
        return currency_help_label

    def _fnct_custom_currency_help_label(
            self, cr, uid, ids, name, args, context=None):
        res = {}
        for voucher in self.browse(cr, uid, ids, context=context):
            res[voucher.id] = self._get_custom_curr_help_label(
                cr, uid, voucher.currency_id.id, voucher.payment_rate,
                voucher.payment_rate_currency_id.id, context=context)
        return res

    bank_fee = fields.Float(
        string='Bank Fees',
        digits=dp.get_precision('Account'))

    _columns = {
        'writeoff_amount': oldfields.function(
            _get_writeoff_amount,
            string='Difference Amount',
            type='float',
            readonly=True,
            help="Computed as the difference between the amount stated in the \
            voucher and the sum of allocation on the voucher lines."),
        'custom_currency_help_label': oldfields.function(
            _fnct_custom_currency_help_label, type='text',
            string="Custom Exchange Rate Help")
        }

    def onchange_line_rate_ids(
        self, cr, uid, ids, line_dr_ids, line_cr_ids, amount, voucher_currency,
            payment_currency_id, payment_rate, type, context=None):
        context = context.copy() or {}
        res = super(AccountVoucher, self).onchange_line_ids(
            cr, uid, ids, line_dr_ids, line_cr_ids, amount, voucher_currency,
            type, context)
        if payment_rate and payment_currency_id:
            cur_model = self.pool['res.currency']
            context.update({'custom_exchange_rate': payment_rate})
            amount_currency = cur_model.compute(
                cr, uid, payment_currency_id, voucher_currency, amount, True,
                context)
            line_dr_ids = self.resolve_2many_commands(
                cr, uid, 'line_dr_ids', line_dr_ids, ['amount'], context)
            line_cr_ids = self.resolve_2many_commands(
                cr, uid, 'line_cr_ids', line_cr_ids, ['amount'], context)
            amount_writeoff = self._compute_writeoff_amount(
                cr, uid, line_dr_ids, line_cr_ids, amount_currency, type)
            res['value']['writeoff_amount'] = amount_writeoff
        return res

    def first_move_line_get(
        self, cr, uid, voucher_id, move_id, company_currency, current_currency,
            context=None):
        context = context or {}
        res = super(AccountVoucher, self).first_move_line_get(
            cr, uid, voucher_id, move_id, company_currency, current_currency,
            context)
        voucher = self.browse(cr, uid, voucher_id, context)
        if voucher.payment_rate != 1:
            res['credit'] = res['credit'] / voucher.payment_rate
            res['debit'] = res['debit'] / voucher.payment_rate
        return res

    def writeoff_move_line_get(
        self, cr, uid, voucher_id, line_total, move_id, name, company_currency,
            current_currency, context=None):
        context = context or {}
        move_line_model = self.pool['account.move.line']
        res = super(AccountVoucher, self).writeoff_move_line_get(
            cr, uid, voucher_id, line_total, move_id, name, company_currency,
            current_currency, context)
        voucher = self.browse(cr, uid, voucher_id, context)
        company = voucher.company_id
        local_context = dict(
            context, force_company=voucher.journal_id.company_id.id)
        res2 = res.copy()
        if voucher.payment_rate != 1:
            if res['credit']:
                res['credit'] = voucher.bank_fee
            if res['debit']:
                res['debit'] = voucher.bank_fee
            if res2['credit']:
                res2['credit'] = res2['credit'] - voucher.bank_fee
                gain_acc_id = company.income_currency_exchange_account_id.id
                res2['account_id'] = gain_acc_id
                res2['name'] = _('change')
            if res2['debit']:
                res2['debit'] = res2['debit'] - voucher.bank_fee
                loss_acc_id = company.expense_currency_exchange_account_id.id
                res2['account_id'] = loss_acc_id
                res2['name'] = _('change')
            move_line_model.create(cr, uid, res2, local_context)
        if not voucher.bank_fee and voucher.payment_rate != 1:
            return False
        else:
            return res

    def voucher_move_line_create(
        self, cr, uid, voucher_id, line_total, move_id, company_currency,
            current_currency, context=None):
        context = context or {}
        move_line_model = self.pool['account.move.line']
        res = super(AccountVoucher, self).voucher_move_line_create(
            cr, uid, voucher_id, line_total, move_id, company_currency,
            current_currency)
        voucher = self.browse(cr, uid, voucher_id)
        for line_id in res[1][0]:
            line = move_line_model.browse(cr, uid, line_id)
            if line.amount_currency and voucher.payment_rate:
                if line.debit:
                    line.write(
                        {'amount_currency': voucher.amount})
                if line.credit:
                    line.write(
                        {'amount_currency': -(
                            voucher.amount)})
            if not line.credit and not line.debit:
                res[1][0].remove(line_id)
                line.unlink()
        return res

    # def recompute_payment_rate(
    #     self, cr, uid, ids, vals, currency_id, date, ttype, journal_id,
    #         amount, context=None):
    #     context = context or {}
    #     res = super(AccountVoucher, self).recompute_payment_rate(
    #         cr, uid, ids, vals, currency_id, date, ttype, journal_id, amount,
    #         context)
    #     if res['value'].get('payment_rate', False):
    #         del res['value']['payment_rate']
    #     return res

    def onchange_payment_rate(
            self, cr, uid, ids, amount, rate, partner_id, journal_id,
            currency_id, ttype, date, payment_rate_currency_id, company_id,
            context=None):
        context = context or {}
        res = super(AccountVoucher, self).onchange_amount(
            cr, uid, ids, amount, rate, partner_id, journal_id,
            currency_id, ttype, date, payment_rate_currency_id, company_id,
            context)
        del res['value']['line_dr_ids']
        del res['value']['line_cr_ids']
        return res

    def onchange_rate(
            self, cr, uid, ids, rate, amount, currency_id,
            payment_rate_currency_id, company_id, context=None):
        res = super(AccountVoucher, self).onchange_rate(
            cr, uid, ids, rate, amount, currency_id, payment_rate_currency_id,
            company_id, context)
        res['value'][
            'custom_currency_help_label'] = self._get_custom_curr_help_label(
            cr, uid, currency_id, rate, payment_rate_currency_id,
            context=context)
        return res
