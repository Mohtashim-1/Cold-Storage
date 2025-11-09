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
        default=lambda self: (fields.Date.today() - timedelta(days=30)).replace(day=1)
    )
    date_to = fields.Date(
        string='To Date',
        required=True,
        default=lambda self: fields.Date.today()
    )
    bill_unbilled_only = fields.Boolean(
        string='Bill Unbilled Consignments Only',
        default=True,
        help='Bill only consignments that have not been billed yet and are not yet released'
    )
    reset_billing_date = fields.Boolean(
        string='Reset Last Billed Date',
        default=False,
        help='Reset last_billed_date for intakes that have no active invoices. Use this if invoices were deleted.'
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
        
        # Reset last_billed_date if requested (for intakes with no active invoices)
        if self.reset_billing_date:
            self._reset_billing_dates()
        
        # Get billable intakes
        domain = [
            ('company_id', '=', self.company_id.id),
            ('state', 'in', ['checked_in', 'partially_out']),  # Only active intakes
        ]
        
        # Date range filter - check if intake date is within range OR if it's unbilled
        if self.bill_unbilled_only:
            # Bill unbilled consignments that are still in storage (not released)
            # Check if last_billed_date is None or before date_from
            # AND intake date is before or equal to date_to
            domain.append('&')
            domain.append('|')
            domain.append(('last_billed_date', '=', False))
            domain.append(('last_billed_date', '<', self.date_from))
            domain.append(('date_in', '<=', self.date_to))
        else:
            # Bill all intakes in date range
            domain.append(('date_in', '>=', self.date_from))
            domain.append(('date_in', '<=', self.date_to))
        
        if self.partner_ids:
            domain.append(('partner_id', 'in', self.partner_ids.ids))
        
        if self.contract_ids:
            domain.append(('contract_id', 'in', self.contract_ids.ids))
        
        intakes = self.env['cs.storage.intake'].search(domain)
        
        print(f"\n=== MONTHLY BILLING DEBUG ===")
        print(f"Date Range: {self.date_from} to {self.date_to}")
        print(f"Bill Unbilled Only: {self.bill_unbilled_only}")
        print(f"Domain: {domain}")
        print(f"Found Intakes: {len(intakes)}")
        
        if not intakes:
            # Provide helpful error message
            all_active_intakes = self.env['cs.storage.intake'].search([
                ('company_id', '=', self.company_id.id),
                ('state', 'in', ['checked_in', 'partially_out']),
            ])
            
            if not all_active_intakes:
                raise UserError(_('No active intakes found. Only intakes in "Checked In" or "Partially Released" state can be billed.'))
            
            # Check if date range is the issue
            intakes_in_range = self.env['cs.storage.intake'].search([
                ('company_id', '=', self.company_id.id),
                ('state', 'in', ['checked_in', 'partially_out']),
                ('date_in', '>=', self.date_from),
                ('date_in', '<=', self.date_to),
            ])
            
            if not intakes_in_range:
                raise UserError(_(
                    'No billable intakes found for the selected date range (%s to %s).\n\n'
                    'Please check:\n'
                    '1. The date range includes intake check-in dates\n'
                    '2. Intakes are in "Checked In" or "Partially Released" state\n'
                    '3. If "Bill Unbilled Consignments Only" is checked, ensure intakes have not been billed yet'
                ) % (self.date_from, self.date_to))
            
            # Check if all intakes are already billed
            if self.bill_unbilled_only:
                unbilled_count = len([i for i in intakes_in_range if not i.last_billed_date or i.last_billed_date < self.date_from])
                if unbilled_count == 0:
                    raise UserError(_(
                        'No unbilled intakes found for the selected criteria.\n\n'
                        'All intakes in the date range have already been billed.\n'
                        'To bill them again, uncheck "Bill Unbilled Consignments Only" or adjust the date range.'
                    ))
            
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
                    # Update last_billed_date for intakes
                    for intake in data['intakes']:
                        intake.last_billed_date = self.date_to
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
    
    def _reset_billing_dates(self):
        """Reset last_billed_date for intakes that have no active invoices"""
        # Find intakes with last_billed_date but no related invoices
        intakes_to_reset = self.env['cs.storage.intake'].search([
            ('company_id', '=', self.company_id.id),
            ('state', 'in', ['checked_in', 'partially_out']),
            ('last_billed_date', '!=', False),
        ])
        
        reset_count = 0
        for intake in intakes_to_reset:
            # Check if there are any invoices related to this intake
            invoices = self.env['account.move'].search([
                ('ref', 'ilike', intake.name),
                ('move_type', '=', 'out_invoice'),
                ('state', '!=', 'cancel'),
            ])
            
            if not invoices:
                intake.last_billed_date = False
                reset_count += 1
        
        if reset_count > 0:
            # Log the reset
            print(f"Reset last_billed_date for {reset_count} intakes with no active invoices.")
    
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
                # Try to get account from company's chart template
                # Look for common income account types
                account = self.env['account.account'].search([
                    ('company_id', '=', self.company_id.id),
                    ('account_type', 'in', ['income', 'income_other', 'income_other_income'])
                ], limit=1)
                if account:
                    account_id = account.id
                    print(f"Found Income Account by type: {account_id}")
                else:
                    # Try to find any account with revenue/income in name
                    account = self.env['account.account'].search([
                        ('name', 'ilike', 'revenue'),
                        ('company_id', '=', self.company_id.id)
                    ], limit=1)
                    if not account:
                        account = self.env['account.account'].search([
                            ('name', 'ilike', 'income'),
                            ('company_id', '=', self.company_id.id)
                        ], limit=1)
                    if account:
                        account_id = account.id
                        print(f"Found Income Account by name: {account_id}")
                    else:
                        # Last resort: check if accounting is installed
                        if not self.env['ir.module.module'].search([('name', '=', 'account'), ('state', '=', 'installed')]):
                            raise UserError(_('Accounting module is not installed. Please install the Accounting app first.'))
                        
                        # If accounting is installed but no accounts exist, guide user
                        print("ERROR: No accounts found in company!")
                        raise UserError(_(
                            'No income accounts found. Please:\n'
                            '1. Go to Accounting > Configuration > Chart of Accounts\n'
                            '2. Install a Chart of Accounts if not already installed\n'
                            '3. Or configure the income account for the product: %s'
                        ) % product.name)
            
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
