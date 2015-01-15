# -*- encoding: utf-8 -*-
##############################################################################
#
#    Copyright (C) 2011 Agile Business Group sagl (<http://www.agilebg.com>)
#    Copyright (C) 2011 Domsense srl (<http://www.domsense.com>)
#    $Id$
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Affero General Public License as published
#    by the Free Software Foundation, either version 3 of the License, or
#    (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.
##############################################################################

from openerp import fields, osv


class account_tax_group(osv.osv):
    _name = 'account.tax.group'
    _description = 'Tax Group'

    _columns = {
        'name': fields.char('Name', size=32, translate=True)
    }


class account_tax(osv.osv):
    _inherit = 'account.tax'

    _columns = {
	   'tax_group': fields.many2one('account.tax.group', 'Group')
    }
