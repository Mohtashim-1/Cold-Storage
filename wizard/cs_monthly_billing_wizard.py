# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError
from datetime import datetime, timedelta


class CsMonthlyBillingWizard(models.TransientModel):
    _name = 'cs.monthly.billing.wizard'
    _description = 'Monthly Billing Wizard'

    company_id = fields.Many2one(
        'res.company',
        string='Company',
        required=True,
        default=lambda self: self.env.company
    )
    date_from = fields.Date(
        string='From Date',
        required=True,
        default=lambda self: fields.Date.today().replace(day=1)
    )
    date_to = fields.Date(
        string='To Date',
        required=True,
        default=lambda self: fields.Date.today()
    )
    partner_ids = fields.Many2many(
        'res.partner',
        string='Customers',
        help='Leave empty to process all customers'
    )
    contract_ids = fields.Many2many(
        'cs.storage.contract',
        string='Contracts',
        domain="[('state', '=', 'active')]",
        help='Leave empty to process all active contracts'
    )
    create_invoices = fields.Boolean(
        string='Create Invoices',
        default=True,
        help='Create actual invoices (uncheck for preview only)'
    )
    
    # Results
    invoice_count = fields.Integer(
        string='Invoices Created',
        compute='_compute_results',
        store=True
    )
    total_amount = fields.Monetary(
        string='Total Amount',
        compute='_compute_results',
        store=True
    )
    currency_id = fields.Many2one(
        'res.currency',
        string='Currency',
        related='company_id.currency_id'
    )
    
    @api.depends('create_invoices')
    def _compute_results(self):
        # This would be computed after running the billing process
        pass
    
    def action_preview_billing(self):
        """Preview billing without creating invoices"""
        self.create_invoices = False
        return self.action_run_billing()
    
    def action_run_billing(self):
        """Run the monthly billing process"""
        if self.date_from > self.date_to:
            raise UserError(_('From date cannot be after to date.'))
        
        # Get billable intakes
        domain = [
            ('company_id', '=', self.company_id.id),
            ('state', 'in', ['checked_in', 'partially_out', 'closed']),
            ('date_in', '>=', self.date_from),
            ('date_in', '<=', self.date_to),
        ]
        
        if self.partner_ids:
            domain.append(('partner_id', 'in', self.partner_ids.ids))
        
        if self.contract_ids:
            domain.append(('contract_id', 'in', self.contract_ids.ids))
        
        intakes = self.env['cs.storage.intake'].search(domain)
        
        print(f"\n=== MONTHLY BILLING DEBUG ===")
        print(f"Date Range: {self.date_from} to {self.date_to}")
        print(f"Domain: {domain}")
        print(f"Found Intakes: {len(intakes)}")
        
        if not intakes:
            raise UserError(_('No billable intakes found for the selected criteria.'))
        
        for intake in intakes:
            print(f"Intake {intake.name}: Partner={intake.partner_id.name}, Total Amount={intake.total_amount}")
            for line in intake.line_ids:
                print(f"  Line {line.id}: Product={line.product_id.name}, Qty={line.qty_in}, Amount={line.amount_subtotal}")
        print(f"=== END MONTHLY BILLING DEBUG ===\n")
        
        # Group by partner for invoice creation
        partner_data = {}
        for intake in intakes:
            partner = intake.partner_id
            if partner not in partner_data:
                partner_data[partner] = {
                    'intakes': [],
                    'total_amount': 0,
                }
            partner_data[partner]['intakes'].append(intake)
            partner_data[partner]['total_amount'] += intake.total_amount
        
        invoices_created = []
        total_amount = 0
        
        for partner, data in partner_data.items():
            if data['total_amount'] > 0:
                if self.create_invoices:
                    invoice = self._create_partner_invoice(partner, data['intakes'], data['total_amount'])
                    invoices_created.append(invoice)
                total_amount += data['total_amount']
        
        # Update results
        self.invoice_count = len(invoices_created)
        self.total_amount = total_amount
        
        if self.create_invoices:
            if invoices_created:
                return {
                    'type': 'ir.actions.act_window',
                    'name': _('Billing Results'),
                    'res_model': 'account.move',
                    'view_mode': 'tree,form',
                    'domain': [('id', 'in', [inv.id for inv in invoices_created])],
                }
            else:
                raise UserError(_('No invoices were created.'))
        else:
            # Preview mode - show summary
            return {
                'type': 'ir.actions.act_window',
                'name': _('Billing Preview'),
                'res_model': 'cs.storage.intake',
                'view_mode': 'tree,form',
                'domain': [('id', 'in', intakes.ids)],
                'context': {'group_by': 'partner_id'},
            }
    
    def _create_partner_invoice(self, partner, intakes, total_amount):
        """Create invoice for a partner"""
        invoice_vals = {
            'partner_id': partner.id,
            'move_type': 'out_invoice',
            'invoice_date': fields.Date.today(),
            'ref': f'Cold Storage charges from {self.date_from} to {self.date_to}',
            'company_id': self.company_id.id,
            'currency_id': self.currency_id.id,
            'invoice_line_ids': [],
        }
        
        # Group by product for invoice lines
        product_data = {}
        for intake in intakes:
            for line in intake.line_ids.filtered(lambda l: l.amount_subtotal > 0):
                product = line.tariff_rule_id.price_product_id
                if product not in product_data:
                    product_data[product] = {
                        'amount': 0,
                        'description': f'Cold Storage charges for {intake.name}',
                    }
                product_data[product]['amount'] += line.amount_subtotal
        
        for product, data in product_data.items():
            print(f"\n=== INVOICE CREATION DEBUG ===")
            print(f"Product: {product.name}")
            print(f"Product ID: {product.id}")
            print(f"Amount: {data['amount']:,.2f}")
            
            # Get the income account for the product
            account_id = product.property_account_income_id.id
            print(f"Product Income Account: {account_id}")
            
            if not account_id:
                # Fallback to product category income account
                account_id = product.categ_id.property_account_income_categ_id.id
                print(f"Category Income Account: {account_id}")
            
            if not account_id:
                # Fallback to default income account
                account_id = self.env['account.account'].search([
                    ('account_type', '=', 'income'),
                    ('company_id', '=', self.company_id.id)
                ], limit=1).id
                print(f"Default Income Account: {account_id}")
            
            if not account_id:
                # Last resort: use any account with 'income' in the name
                account = self.env['account.account'].search([
                    ('name', 'ilike', 'income'),
                    ('company_id', '=', self.company_id.id)
                ], limit=1)
                if account:
                    account_id = account.id
                    print(f"Found Income Account by name: {account_id}")
                else:
                    # Use any account that exists
                    account = self.env['account.account'].search([
                        ('company_id', '=', self.company_id.id)
                    ], limit=1)
                    if account:
                        account_id = account.id
                        print(f"Using any available account: {account_id}")
                    else:
                        print("ERROR: No accounts found in company!")
                        raise UserError(_('No accounting accounts found. Please install and configure the Accounting app first.'))
            
            print(f"Final Account ID: {account_id}")
            print(f"=== END INVOICE CREATION DEBUG ===\n")
            
            invoice_line_vals = {
                'product_id': product.id,
                'name': data['description'],
                'quantity': 1,
                'price_unit': data['amount'],
                'account_id': account_id,
            }
            invoice_vals['invoice_line_ids'].append((0, 0, invoice_line_vals))
        
        return self.env['account.move'].create(invoice_vals)
