# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError
from datetime import datetime, timedelta


class CsStorageContract(models.Model):
    _name = 'cs.storage.contract'
    _description = 'Storage Contract'
    _order = 'name desc'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(
        string='Contract No.',
        required=True,
        copy=False,
        readonly=True,
        default=lambda self: _('New')
    )
    partner_id = fields.Many2one(
        'res.partner',
        string='Customer',
        required=True,
        tracking=True,
        help='Contract customer'
    )
    
    # Contract details
    pricing_model = fields.Selection([
        ('pre_paid', 'Pre-paid'),
        ('post_paid', 'Post-paid'),
        ('cap', 'Capacity-based'),
    ], string='Pricing Model', required=True, default='post_paid', tracking=True)
    
    tariff_rule_id = fields.Many2one(
        'cs.tariff.rule',
        string='Default Tariff',
        help='Default tariff rule for this contract'
    )
    
    credit_limit = fields.Monetary(
        string='Storage Credit',
        help='Credit limit for pre-paid contracts'
    )
    currency_id = fields.Many2one(
        'res.currency',
        string='Currency',
        default=lambda self: self.env.company.currency_id,
        required=True
    )
    
    # Billing cycle
    invoice_cycle = fields.Selection([
        ('monthly', 'Monthly'),
        ('weekly', 'Weekly'),
        ('manual', 'Manual'),
    ], string='Billing Cycle', required=True, default='monthly', tracking=True)
    
    next_invoice_date = fields.Date(
        string='Next Invoice Date',
        help='Next scheduled invoice date'
    )
    
    state = fields.Selection([
        ('draft', 'Draft'),
        ('active', 'Active'),
        ('suspended', 'Suspended'),
        ('closed', 'Closed'),
    ], string='Status', default='draft', tracking=True, required=True)
    
    # Contract period
    date_start = fields.Date(
        string='Start Date',
        required=True,
        default=fields.Date.today,
        tracking=True
    )
    date_end = fields.Date(
        string='End Date',
        help='Leave empty for open-ended contract'
    )
    
    # Related data
    intake_ids = fields.One2many(
        'cs.storage.intake',
        'contract_id',
        string='Intakes'
    )
    # Note: invoice_ids would need to be implemented with a custom field on account.move
    # For now, we'll use a computed field to find related invoices
    invoice_ids = fields.Many2many(
        'account.move',
        string='Invoices',
        compute='_compute_invoice_ids',
        search='_search_invoice_ids'
    )
    
    # Computed counts
    intake_count = fields.Integer(
        string='Intake Count',
        compute='_compute_intake_count',
        store=True
    )
    invoice_count = fields.Integer(
        string='Invoice Count',
        compute='_compute_invoice_count',
        store=True
    )
    
    # Computed fields
    total_storage_amount = fields.Monetary(
        string='Total Storage Amount',
        compute='_compute_totals',
        store=True
    )
    total_invoiced = fields.Monetary(
        string='Total Invoiced',
        compute='_compute_totals',
        store=True
    )
    balance_due = fields.Monetary(
        string='Balance Due',
        compute='_compute_totals',
        store=True
    )
    
    # Company
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        default=lambda self: self.env.company,
        required=True
    )
    
    @api.depends('intake_ids.total_amount', 'invoice_ids.amount_total')
    def _compute_totals(self):
        for record in self:
            record.total_storage_amount = sum(record.intake_ids.mapped('total_amount'))
            record.total_invoiced = sum(record.invoice_ids.filtered(lambda inv: inv.state == 'posted').mapped('amount_total'))
            record.balance_due = record.total_storage_amount - record.total_invoiced
    
    @api.depends('intake_ids')
    def _compute_intake_count(self):
        for record in self:
            record.intake_count = len(record.intake_ids)
    
    def _compute_invoice_ids(self):
        for record in self:
            # Find invoices that reference this contract in their ref field
            invoices = self.env['account.move'].search([
                ('ref', 'ilike', record.name),
                ('move_type', '=', 'out_invoice')
            ])
            record.invoice_ids = invoices
    
    def _search_invoice_ids(self, operator, value):
        """Search method for invoice_ids field"""
        if operator == 'in':
            return [('id', 'in', value)]
        elif operator == 'not in':
            return [('id', 'not in', value)]
        else:
            return []
    
    @api.depends('invoice_ids')
    def _compute_invoice_count(self):
        for record in self:
            record.invoice_count = len(record.invoice_ids)
    
    @api.model
    def create(self, vals):
        if vals.get('name', _('New')) == _('New'):
            vals['name'] = self.env['ir.sequence'].next_by_code('cs.storage.contract') or _('New')
        
        # Set next invoice date based on cycle
        if 'invoice_cycle' in vals and 'next_invoice_date' not in vals:
            vals['next_invoice_date'] = self._get_next_invoice_date(vals.get('invoice_cycle', 'monthly'))
        
        return super().create(vals)
    
    def _get_next_invoice_date(self, cycle):
        """Get next invoice date based on cycle"""
        today = fields.Date.today()
        if cycle == 'weekly':
            return today + timedelta(days=7)
        elif cycle == 'monthly':
            return today + timedelta(days=30)
        else:
            return today
    
    def action_activate(self):
        """Activate the contract"""
        for record in self:
            if record.state != 'draft':
                raise UserError(_('Only draft contracts can be activated.'))
            record.state = 'active'
            record.message_post(body=_('Contract activated.'))
    
    def action_suspend(self):
        """Suspend the contract"""
        for record in self:
            if record.state != 'active':
                raise UserError(_('Only active contracts can be suspended.'))
            record.state = 'suspended'
            record.message_post(body=_('Contract suspended.'))
    
    def action_close(self):
        """Close the contract"""
        for record in self:
            if record.state not in ['active', 'suspended']:
                raise UserError(_('Only active or suspended contracts can be closed.'))
            record.state = 'closed'
            record.message_post(body=_('Contract closed.'))
    
    def action_create_invoice(self):
        """Create invoice for contract billing cycle"""
        for record in self:
            if record.state != 'active':
                raise UserError(_('Only active contracts can be invoiced.'))
            
            if record.pricing_model == 'pre_paid' and record.credit_limit <= 0:
                raise UserError(_('Pre-paid contract has no credit available.'))
            
            # Get billable intakes for the period
            billable_intakes = self._get_billable_intakes()
            
            if not billable_intakes:
                raise UserError(_('No billable intakes found for this contract.'))
            
            # Create invoice
            invoice_vals = {
                'partner_id': record.partner_id.id,
                'move_type': 'out_invoice',
                'invoice_date': fields.Date.today(),
                'ref': f'Storage charges for contract {record.name}',
                'company_id': record.company_id.id,
                'currency_id': record.currency_id.id,
                'contract_id': record.id,
                'invoice_line_ids': [],
            }
            
            total_amount = 0
            for intake in billable_intakes:
                for line in intake.line_ids.filtered(lambda l: l.amount_subtotal > 0):
                    invoice_line_vals = {
                        'product_id': line.tariff_rule_id.price_product_id.id,
                        'name': f'Storage: {line.product_id.name} ({line.lot_id.name or "No Lot"}) from {line.date_in.strftime("%Y-%m-%d")} to {line.date_out.strftime("%Y-%m-%d") if line.date_out else "ongoing"}, {line.duration_days:.2f} days @ {line.price_unit:.2f}/{line.bill_basis}',
                        'quantity': 1,
                        'price_unit': line.amount_subtotal,
                        'account_id': line.tariff_rule_id.price_product_id.property_account_income_id.id,
                    }
                    invoice_vals['invoice_line_ids'].append((0, 0, invoice_line_vals))
                    total_amount += line.amount_subtotal
            
            if invoice_vals['invoice_line_ids']:
                invoice = self.env['account.move'].create(invoice_vals)
                
                # Update next invoice date
                record.next_invoice_date = self._get_next_invoice_date(record.invoice_cycle)
                
                return {
                    'type': 'ir.actions.act_window',
                    'name': _('Contract Invoice'),
                    'res_model': 'account.move',
                    'res_id': invoice.id,
                    'view_mode': 'form',
                    'target': 'current',
                }
            else:
                raise UserError(_('No charges to invoice.'))
    
    def _get_billable_intakes(self):
        """Get intakes that need to be billed for this contract"""
        # This is a simplified version - in practice, you'd want more sophisticated logic
        # to determine which intakes should be billed based on the contract cycle
        return self.intake_ids.filtered(lambda i: i.state in ['checked_in', 'partially_out', 'closed'])
    
    @api.constrains('date_start', 'date_end')
    def _check_dates(self):
        for record in self:
            if record.date_end and record.date_start and record.date_end < record.date_start:
                raise ValidationError(_('End date cannot be before start date.'))
    
    @api.constrains('credit_limit')
    def _check_credit_limit(self):
        for record in self:
            if record.pricing_model == 'pre_paid' and record.credit_limit <= 0:
                raise ValidationError(_('Pre-paid contracts must have a positive credit limit.'))
    
    @api.model
    def _cron_monthly_billing(self):
        """Monthly billing cron job"""
        active_contracts = self.search([
            ('state', '=', 'active'),
            ('invoice_cycle', '!=', 'manual'),
            ('next_invoice_date', '<=', fields.Date.today())
        ])
        
        for contract in active_contracts:
            try:
                contract.action_create_invoice()
            except Exception as e:
                # Log error but continue with other contracts
                contract.message_post(
                    body=_('Monthly billing failed: %s') % str(e),
                    message_type='notification'
                )
    
    def action_view_intakes(self):
        """View related intakes"""
        return {
            'type': 'ir.actions.act_window',
            'name': _('Contract Intakes'),
            'res_model': 'cs.storage.intake',
            'view_mode': 'tree,form',
            'domain': [('contract_id', '=', self.id)],
            'context': {'default_contract_id': self.id},
        }
    
    def action_view_invoices(self):
        """View related invoices"""
        return {
            'type': 'ir.actions.act_window',
            'name': _('Contract Invoices'),
            'res_model': 'account.move',
            'view_mode': 'tree,form',
            'domain': [('contract_id', '=', self.id)],
        }
