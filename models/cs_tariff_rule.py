# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class CsTariffRule(models.Model):
    _name = 'cs.tariff.rule'
    _description = 'Cold Storage Tariff Rule'
    _order = 'sequence, name'

    name = fields.Char(
        string='Rule Name',
        required=True,
        help='Name of the tariff rule (e.g., "Frozen per kg/day")'
    )
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        default=lambda self: self.env.company,
        required=True
    )
    active = fields.Boolean(
        string='Active',
        default=True,
        help='Uncheck to disable this tariff rule'
    )
    sequence = fields.Integer(
        string='Sequence',
        default=10,
        help='Order of evaluation (lower numbers first)'
    )
    
    # Pricing basis
    basis = fields.Selection([
        ('day_weight', 'Per Kg per Day'),
        ('day_volume', 'Per Volume per Day'),
        ('day_pallet', 'Per Pallet per Day'),
        ('flat', 'Flat Rate per Day'),
    ], string='Billing Basis', required=True, default='day_weight')
    
    # Product filters
    product_category_id = fields.Many2one(
        'product.category',
        string='Product Category',
        help='Optional filter by product category'
    )
    product_id = fields.Many2one(
        'product.product',
        string='Product',
        help='Optional filter by specific product'
    )
    
    # Temperature filters
    min_temp = fields.Float(
        string='Min Temperature (°C)',
        help='Minimum temperature for this rule to apply'
    )
    max_temp = fields.Float(
        string='Max Temperature (°C)',
        help='Maximum temperature for this rule to apply'
    )
    
    # Quantity filters
    min_qty = fields.Float(
        string='Min Quantity',
        help='Minimum quantity for this rule to apply'
    )
    
    # Pricing
    price_unit = fields.Monetary(
        string='Rate',
        required=True,
        help='Price per basis unit per day'
    )
    currency_id = fields.Many2one(
        'res.currency',
        string='Currency',
        default=lambda self: self.env.company.currency_id,
        required=True
    )
    
    # Rounding and billing policies
    rounding_policy = fields.Selection([
        ('ceil_day', 'Ceiling to Full Day'),
        ('half_up', 'Half Day Up'),
        ('exact_hours', 'Exact Hours (2 decimals)'),
        ('2h_step', '2-Hour Steps'),
    ], string='Rounding Policy', required=True, default='ceil_day')
    
    min_bill_days = fields.Float(
        string='Min Billable Days',
        default=1.0,
        help='Minimum number of days to bill (e.g., 1.0)'
    )
    
    # Taxes and invoicing
    taxes_id = fields.Many2many(
        'account.tax',
        'cs_tariff_rule_tax_rel',
        'rule_id',
        'tax_id',
        string='Taxes',
        help='Taxes to apply to storage charges'
    )
    price_product_id = fields.Many2one(
        'product.product',
        string='Storage Service Product',
        required=True,
        domain=[('type', '=', 'service')],
        help='Product used on invoices for storage charges'
    )
    
    # Computed count
    intake_count = fields.Integer(
        string='Intake Count',
        compute='_compute_intake_count',
        store=True
    )
    
    def _compute_intake_count(self):
        for record in self:
            record.intake_count = len(self.env['cs.storage.intake.line'].search([('tariff_rule_id', '=', record.id)]))
    
    @api.constrains('min_temp', 'max_temp')
    def _check_temperature_range(self):
        for record in self:
            if record.min_temp and record.max_temp and record.min_temp > record.max_temp:
                raise ValidationError(_('Minimum temperature cannot be greater than maximum temperature.'))
    
    @api.constrains('min_qty')
    def _check_min_qty(self):
        for record in self:
            if record.min_qty and record.min_qty < 0:
                raise ValidationError(_('Minimum quantity cannot be negative.'))
    
    def match_rule(self, intake_line):
        """
        Check if this tariff rule matches the given intake line
        """
        self.ensure_one()
        
        # Check product filters
        if self.product_id and intake_line.product_id != self.product_id:
            return False
        if self.product_category_id and intake_line.product_id.categ_id != self.product_category_id:
            return False
        
        # Check temperature filters
        if self.min_temp is not False and intake_line.intake_id.temperature_target < self.min_temp:
            return False
        if self.max_temp is not False and intake_line.intake_id.temperature_target > self.max_temp:
            return False
        
        # Check quantity filters
        if self.min_qty and intake_line.qty_in < self.min_qty:
            return False
        
        return True
    
    def compute_duration_days(self, duration_hours):
        """
        Compute duration in days based on rounding policy
        """
        self.ensure_one()
        
        if self.rounding_policy == 'ceil_day':
            return max(1.0, (duration_hours + 23) // 24)  # Ceiling to full day
        elif self.rounding_policy == 'half_up':
            days = duration_hours / 24
            if days >= 0.5:
                return 1.0 if days >= 1.0 else 0.5
            return 0.5
        elif self.rounding_policy == 'exact_hours':
            return round(duration_hours / 24, 2)
        elif self.rounding_policy == '2h_step':
            # Round up to next 2-hour block
            hours_rounded = ((int(duration_hours) + 1) // 2) * 2
            return hours_rounded / 24
        else:
            return duration_hours / 24
    
    def compute_amount(self, intake_line):
        """
        Compute storage amount for the given intake line
        """
        self.ensure_one()
        
        print(f"\n=== TARIFF CALCULATION DEBUG ===")
        print(f"Rule ID: {self.id}")
        print(f"Rule Name: {self.name}")
        print(f"Basis: {self.basis}")
        print(f"Price Unit: {self.price_unit}")
        print(f"Rounding Policy: {self.rounding_policy}")
        print(f"Min Bill Days: {self.min_bill_days}")
        
        print(f"\nIntake Line Data:")
        print(f"  Weight: {intake_line.weight}")
        print(f"  Qty In: {intake_line.qty_in}")
        print(f"  Volume: {intake_line.volume}")
        print(f"  Pallet Count: {intake_line.pallet_count}")
        print(f"  Duration Hours: {intake_line.duration_hours}")
        print(f"  Duration Days: {intake_line.duration_days}")
        
        # Get billable quantity based on basis
        if self.basis == 'day_weight':
            # Use weight if available, otherwise use quantity as fallback
            billable_qty = intake_line.weight or intake_line.qty_in or 0
            print(f"  Using day_weight: weight={intake_line.weight}, qty_in={intake_line.qty_in}, billable_qty={billable_qty}")
        elif self.basis == 'day_volume':
            billable_qty = intake_line.volume or 0
            print(f"  Using day_volume: volume={intake_line.volume}, billable_qty={billable_qty}")
        elif self.basis == 'day_pallet':
            billable_qty = intake_line.pallet_count or 0
            print(f"  Using day_pallet: pallet_count={intake_line.pallet_count}, billable_qty={billable_qty}")
        else:  # flat
            billable_qty = 1
            print(f"  Using flat rate: billable_qty={billable_qty}")
        
        # Compute duration
        duration_hours = intake_line.duration_hours
        duration_days = self.compute_duration_days(duration_hours)
        duration_days = max(duration_days, self.min_bill_days)
        
        print(f"\nDuration Calculation:")
        print(f"  Duration Hours: {duration_hours}")
        print(f"  Computed Duration Days: {duration_days}")
        print(f"  Min Bill Days: {self.min_bill_days}")
        print(f"  Final Duration Days: {duration_days}")
        
        # Compute amount
        amount = self.price_unit * billable_qty * duration_days
        
        print(f"\nAmount Calculation:")
        print(f"  Formula: {self.price_unit} × {billable_qty} × {duration_days}")
        print(f"  Result: {amount:,.2f}")
        print(f"  Expected for 3500 qty: {3500 * 3600 * 1:,.2f}")
        print(f"=== END TARIFF CALCULATION DEBUG ===\n")
        
        return amount, duration_days
    
    def action_view_intakes(self):
        """View intakes using this tariff rule"""
        return {
            'type': 'ir.actions.act_window',
            'name': _('Intakes using this Tariff'),
            'res_model': 'cs.storage.intake',
            'view_mode': 'tree,form',
            'domain': [('line_ids.tariff_rule_id', '=', self.id)],
        }
