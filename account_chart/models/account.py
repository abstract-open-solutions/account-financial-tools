# -*- coding: utf-8 -*-

import openerp.addons.decimal_precision as dp
from openerp import fields, models, api


class AccountAccount(models.Model):
    _inherit = 'account.account'

    @api.one
    @api.depends('credit')
    def _get_credit(self):
        aml_model = self.env['account.move.line']
        amls = aml_model.search([('account_id', '=', self.id)])
        if not self.children_ids and amls:
            self.credit = sum([line.credit for line in amls])
        elif self.children_ids:
            credit = 0
            for children in self.children_ids:
                credit += children.credit
            self.credit = credit
        else:
            self.credit = 0.0

    @api.one
    @api.depends('debit')
    def _get_debit(self):
        aml_model = self.env['account.move.line']
        amls = aml_model.search([('account_id', '=', self.id)])
        if not self.children_ids and amls:
            self.debit = sum([line.debit for line in amls])
        elif self.children_ids:
            debit = 0
            for children in self.children_ids:
                debit += children.debit
            self.debit = debit
        else:
            self.debit = 0.0

    @api.one
    @api.depends('balance')
    def _get_balance(self):
        self.balance = self.credit - self.debit

    parent_id = fields.Many2one('account.account', 'Parent Account')
    consolidated_ids = fields.Many2many(
        comodel_name='account.account',
        relation='account_consolidation_rel',
        column1='children_id',
        column2='parent_id',
        string='Consolidated Accounts')
    children_ids = fields.One2many(
        'account.account', 'parent_id', string="Children Accounts")
    debit = fields.Monetary(
        string='Debit',
        compute='_get_debit',
        digits=dp.get_precision('Account'))
    credit = fields.Monetary(
        string='Credit',
        compute='_get_credit',
        digits=dp.get_precision('Account'))
    balance = fields.Monetary(
        string='Balance',
        compute='_get_balance',
        digits=dp.get_precision('Account'))


class AccountAccountTemplate(models.Model):
    _inherit = 'account.account.template'

    parent_id = fields.Many2one('account.account.template', 'Parent Account')
    consolidated_ids = fields.Many2many(
        comodel_name='account.account.template',
        relation='account_consolidation_rel',
        column1='children_id',
        column2='parent_id',
        string='Consolidated Accounts')


class AccountChartTemplate(models.Model):
    _inherit = "account.chart.template"

    @api.multi
    def generate_account(self, tax_template_ref, acc_template_ref, code_digits, company):
        """ This method for generating accounts from templates.

            :param tax_template_ref: Taxes templates reference for write taxes_id in account_account.
            :param acc_template_ref: dictionary with the mappping between the account templates and the real accounts.
            :param code_digits: number of digits got from wizard.multi.charts.accounts, this is use for account code.
            :param company_id: company_id selected from wizard.multi.charts.accounts.
            :returns: return acc_template_ref for reference purpose.
            :rtype: dict
        """
        self.ensure_one()
        account_tmpl_obj = self.env['account.account.template']
        acc_template = account_tmpl_obj.search([('nocreate', '!=', True), ('chart_template_id', '=', self.id)], order='id')
        for account_template in acc_template:
            tax_ids = []
            for tax in account_template.tax_ids:
                tax_ids.append(tax_template_ref[tax.id])

            code_main = account_template.code and len(account_template.code) or 0
            code_acc = account_template.code or ''
            if code_main > 0 and code_main <= code_digits:
                code_acc = str(code_acc) + (str('0'*(code_digits-code_main)))
            vals = {
                'name': account_template.name,
                'currency_id': account_template.currency_id and account_template.currency_id.id or False,
                'code': code_acc,
                'user_type_id': account_template.user_type_id and account_template.user_type_id.id or False,
                'reconcile': account_template.reconcile,
                'note': account_template.note,
                'tax_ids': [(6, 0, tax_ids)],
                'company_id': company.id,
                'parent_id': account_template.parent_id and account_template.parent_id.id or False,
                'tag_ids': [(6, 0, [t.id for t in account_template.tag_ids])],
            }
            new_account = self.env['account.account'].create(vals)
            acc_template_ref[account_template.id] = new_account.id
        return acc_template_ref
