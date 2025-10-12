# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError
from datetime import datetime, timedelta


class CsStorageIntake(models.Model):
    _name = 'cs.storage.intake'
    _description = 'Cold Storage Intake'
    _order = 'date_in desc, name desc'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(
        string='Intake No.',
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
        help='Customer who owns the goods'
    )
    date_in = fields.Datetime(
        string='Check-in Time',
        required=True,
        default=fields.Datetime.now,
        tracking=True
    )
    planned_date_out = fields.Datetime(
        string='Planned Release',
        help='Expected release date (optional)'
    )
    location_id = fields.Many2one(
        'stock.location',
        string='Freezer Location',
        required=True,
        domain=[('is_freezer', '=', True)],
        help='Freezer location where goods are stored'
    )
    temperature_target = fields.Float(
        string='Target Temperature (°C)',
        help='Target storage temperature'
    )
    state = fields.Selection([
        ('draft', 'Draft'),
        ('checked_in', 'Checked In'),
        ('partially_out', 'Partially Released'),
        ('closed', 'Closed'),
        ('cancelled', 'Cancelled'),
    ], string='Status', default='draft', tracking=True, required=True)
    
    note = fields.Text(string='Notes')
    
    # Related fields
    line_ids = fields.One2many(
        'cs.storage.intake.line',
        'intake_id',
        string='Items',
        copy=True
    )
    release_ids = fields.One2many(
        'cs.stock.release',
        'intake_id',
        string='Releases'
    )
    temperature_log_ids = fields.One2many(
        'cs.temperature.log',
        'intake_id',
        string='Temperature Logs'
    )
    
    # Computed counts
    release_count = fields.Integer(
        string='Release Count',
        compute='_compute_release_count',
        store=True
    )
    invoice_count = fields.Integer(
        string='Invoice Count',
        compute='_compute_invoice_count',
        store=True
    )
    
    # Computed fields
    total_qty_in = fields.Float(
        string='Total Qty In',
        compute='_compute_totals',
        store=True
    )
    total_qty_out = fields.Float(
        string='Total Qty Out',
        compute='_compute_totals',
        store=True
    )
    total_weight = fields.Float(
        string='Total Weight (kg)',
        compute='_compute_totals',
        store=True
    )
    total_volume = fields.Float(
        string='Total Volume',
        compute='_compute_totals',
        store=True
    )
    total_amount = fields.Monetary(
        string='Total Storage Amount',
        compute='_compute_totals',
        store=True
    )
    currency_id = fields.Many2one(
        'res.currency',
        string='Currency',
        default=lambda self: self.env.company.currency_id,
        required=True
    )
    
    # Contract
    contract_id = fields.Many2one(
        'cs.storage.contract',
        string='Contract',
        help='Related storage contract (optional)'
    )
    
    # Company
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        default=lambda self: self.env.company,
        required=True
    )
    
    @api.depends('line_ids.qty_in', 'line_ids.qty_out', 'line_ids.weight', 
                 'line_ids.volume', 'line_ids.amount_subtotal')
    def _compute_totals(self):
        for record in self:
            record.total_qty_in = sum(record.line_ids.mapped('qty_in'))
            record.total_qty_out = sum(record.line_ids.mapped('qty_out'))
            record.total_weight = sum(record.line_ids.mapped('weight'))
            record.total_volume = sum(record.line_ids.mapped('volume'))
            record.total_amount = sum(record.line_ids.mapped('amount_subtotal'))
    
    @api.depends('release_ids')
    def _compute_release_count(self):
        for record in self:
            record.release_count = len(record.release_ids)
    
    @api.depends('name')
    def _compute_invoice_count(self):
        for record in self:
            # This would count invoices related to this intake
            record.invoice_count = 0
    
    @api.model
    def create(self, vals):
        if vals.get('name', _('New')) == _('New'):
            vals['name'] = self.env['ir.sequence'].next_by_code('cs.storage.intake') or _('New')
        return super().create(vals)
    
    def action_check_in(self):
        """Check in the intake and create stock moves if enabled"""
        for record in self:
            if record.state != 'draft':
                raise UserError(_('Only draft intakes can be checked in.'))
            
            if not record.line_ids:
                raise UserError(_('Please add at least one item line.'))
            
            # Create stock moves if location has stock tracking enabled
            if record.location_id.usage == 'internal':
                for line in record.line_ids:
                    if line.product_id.type in ['product', 'consu']:
                        # Create incoming move
                        move_vals = {
                            'name': f'IN-{record.name}',
                            'product_id': line.product_id.id,
                            'product_uom_qty': line.qty_in,
                            'product_uom': line.qty_uom_id.id,
                            'location_id': self.env.ref('stock.stock_location_suppliers').id,
                            'location_dest_id': record.location_id.id,
                            'origin': record.name,
                            'company_id': record.company_id.id,
                        }
                        if line.lot_id:
                            move_vals['lot_ids'] = [(4, line.lot_id.id)]
                        
                        move = self.env['stock.move'].create(move_vals)
                        move._action_confirm()
                        move._action_assign()
                        move._action_done()
            
            record.state = 'checked_in'
            record.message_post(body=_('Intake checked in successfully.'))
    
    def action_cancel(self):
        """Cancel the intake"""
        for record in self:
            if record.state in ['closed']:
                raise UserError(_('Cannot cancel a closed intake.'))
            record.state = 'cancelled'
            record.message_post(body=_('Intake cancelled.'))
    
    def action_close(self):
        """Close the intake when all items are released"""
        for record in self:
            if record.state != 'partially_out':
                raise UserError(_('Only partially released intakes can be closed.'))
            
            # Check if all lines are fully released
            unreleased_lines = record.line_ids.filtered(lambda l: l.qty_out < l.qty_in)
            if unreleased_lines:
                raise UserError(_('Cannot close intake with unreleased items.'))
            
            record.state = 'closed'
            record.message_post(body=_('Intake closed - all items released.'))
    
    def action_view_releases(self):
        """View related releases"""
        action = self.env.ref('cs_cold_storage.action_cs_stock_release').read()[0]
        action['domain'] = [('intake_id', '=', self.id)]
        return action
    
    def action_view_invoices(self):
        """View related invoices"""
        # This would be implemented to show invoices created from this intake
        return {
            'type': 'ir.actions.act_window',
            'name': _('Related Invoices'),
            'res_model': 'account.move',
            'view_mode': 'tree,form',
            'domain': [('ref', 'ilike', self.name)],
        }
    
    @api.model
    def _cron_refresh_durations(self):
        """Refresh durations for open intake lines"""
        open_lines = self.env['cs.storage.intake.line'].search([
            ('intake_id.state', 'in', ['checked_in', 'partially_out']),
            ('qty_out', '<', 'qty_in')
        ])
        for line in open_lines:
            line._compute_duration()
    
    @api.model
    def _cron_check_overdue_releases(self):
        """Check for overdue planned releases and send notifications"""
        overdue_intakes = self.search([
            ('planned_date_out', '<', fields.Date.today()),
            ('state', 'in', ['checked_in', 'partially_out'])
        ])
        
        for intake in overdue_intakes:
            # Send notification to customer
            intake.message_post(
                body=_('Your storage intake %s was planned for release on %s but is still in storage. Please contact us to arrange pickup.') % (
                    intake.name, intake.planned_date_out
                ),
                partner_ids=intake.partner_id.ids
            )


class CsStorageIntakeLine(models.Model):
    _name = 'cs.storage.intake.line'
    _description = 'Cold Storage Intake Line'
    _order = 'intake_id, id'

    intake_id = fields.Many2one(
        'cs.storage.intake',
        string='Intake',
        required=True,
        ondelete='cascade'
    )
    product_id = fields.Many2one(
        'product.product',
        string='Product',
        required=True,
        domain=[('type', 'in', ['product', 'consu'])],
        help='Product being stored'
    )
    lot_id = fields.Many2one(
        'stock.lot',
        string='Lot/Batch',
        domain="[('product_id', '=', product_id)]",
        help='Lot/Batch number for perishables'
    )
    qty_in = fields.Float(
        string='Qty In',
        required=True,
        help='Quantity received'
    )
    qty_uom_id = fields.Many2one(
        'uom.uom',
        string='UoM',
        required=True,
        default=lambda self: self.product_id.uom_id if self.product_id else False
    )
    qty_out = fields.Float(
        string='Qty Out',
        default=0,
        help='Quantity released'
    )
    volume = fields.Float(
        string='Volume',
        help='Volume in cubic meters or cubic feet'
    )
    weight = fields.Float(
        string='Weight (kg)',
        help='Weight in kilograms'
    )
    pallet_count = fields.Float(
        string='Pallet Count',
        help='Number of pallets'
    )
    
    date_in = fields.Datetime(
        string='Line Check-in',
        default=fields.Datetime.now,
        help='Check-in time for this line'
    )
    date_out = fields.Datetime(
        string='Line Release Time',
        help='Release time for this line'
    )
    
    # Duration and billing
    duration_hours = fields.Float(
        string='Duration (hrs)',
        compute='_compute_duration',
        store=True,
        help='Duration in hours'
    )
    duration_days = fields.Float(
        string='Duration (days)',
        compute='_compute_duration',
        store=True,
        help='Duration in days'
    )
    
    tariff_rule_id = fields.Many2one(
        'cs.tariff.rule',
        string='Tariff Rule',
        help='Applied tariff rule'
    )
    price_unit = fields.Monetary(
        string='Price / Unit / Day',
        help='Price per unit per day'
    )
    bill_basis = fields.Selection([
        ('day_weight', 'Per Kg per Day'),
        ('day_volume', 'Per Volume per Day'),
        ('day_pallet', 'Per Pallet per Day'),
        ('flat', 'Flat Rate per Day'),
    ], string='Billing Basis', help='Billing basis for this line')
    
    amount_subtotal = fields.Monetary(
        string='Storage Amount',
        compute='_compute_amount',
        store=True,
        help='Computed storage amount'
    )
    currency_id = fields.Many2one(
        'res.currency',
        string='Currency',
        related='intake_id.currency_id',
        store=True
    )
    
    remark = fields.Text(string='Remark', help='Damage/wastage/notes')
    
    # Additional fields
    expiry_date = fields.Date(
        string='Expiry Date',
        help='Expiry date for perishables'
    )
    # bin_id = fields.Many2one(
    #     'cs.storage.bin',
    #     string='Storage Bin',
    #     help='Assigned storage bin/rack'
    # )
    qc_state = fields.Selection([
        ('pending', 'Pending'),
        ('ok', 'OK'),
        ('reject', 'Rejected'),
    ], string='QC State', default='pending')
    
    @api.depends('date_in', 'date_out', 'intake_id.state', 'intake_id.date_in')
    def _compute_duration(self):
        for line in self:
            if line.intake_id.date_in:
                end_time = line.date_out or fields.Datetime.now()
                duration = (end_time - line.intake_id.date_in).total_seconds() / 3600  # hours
                line.duration_hours = duration
                line.duration_days = duration / 24
            else:
                line.duration_hours = 0
                line.duration_days = 0
    
    @api.depends('tariff_rule_id', 'price_unit', 'bill_basis', 'qty_in', 'weight', 'volume', 'pallet_count', 'duration_hours', 'duration_days')
    def _compute_amount(self):
        print(f"\n=== INTAKE LINE AMOUNT CALCULATION DEBUG ===")
        for line in self:
            print(f"Processing Intake Line ID: {line.id}")
            print(f"  Product: {line.product_id.name if line.product_id else 'None'}")
            print(f"  Qty In: {line.qty_in}")
            print(f"  Weight: {line.weight}")
            print(f"  Volume: {line.volume}")
            print(f"  Pallet Count: {line.pallet_count}")
            print(f"  Duration Hours: {line.duration_hours}")
            print(f"  Duration Days: {line.duration_days}")
            print(f"  Tariff Rule: {line.tariff_rule_id.name if line.tariff_rule_id else 'None'}")
            print(f"  Price Unit: {line.price_unit}")
            print(f"  Bill Basis: {line.bill_basis}")
            
            if line.tariff_rule_id:
                print(f"  Calling tariff rule calculation...")
                amount, duration_days = line.tariff_rule_id.compute_amount(line)
                line.amount_subtotal = amount
                print(f"  RESULT: Amount = {amount:,.2f}, Duration = {duration_days}")
            else:
                line.amount_subtotal = 0
                print(f"  RESULT: No tariff rule assigned, amount = 0")
        print(f"=== END INTAKE LINE AMOUNT CALCULATION DEBUG ===\n")
    
    @api.onchange('product_id')
    def _onchange_product_id(self):
        if self.product_id:
            self.qty_uom_id = self.product_id.uom_id
            # Auto-suggest tariff rule
            self._suggest_tariff_rule()
    
    @api.onchange('tariff_rule_id')
    def _onchange_tariff_rule_id(self):
        if self.tariff_rule_id:
            self.price_unit = self.tariff_rule_id.price_unit
            self.bill_basis = self.tariff_rule_id.basis
    
    def _suggest_tariff_rule(self):
        """Suggest appropriate tariff rule based on product and intake conditions"""
        if not self.product_id or not self.intake_id:
            return
        
        # Find matching tariff rules
        rules = self.env['cs.tariff.rule'].search([
            ('active', '=', True),
            ('company_id', '=', self.intake_id.company_id.id),
        ])
        
        for rule in rules:
            if rule.match_rule(self):
                self.tariff_rule_id = rule
                self.price_unit = rule.price_unit
                self.bill_basis = rule.basis
                break
    
    def debug_calculation(self):
        """Debug method to manually trigger calculation and show debug info"""
        print(f"\n=== MANUAL DEBUG CALCULATION ===")
        print(f"Intake Line ID: {self.id}")
        print(f"Product: {self.product_id.name if self.product_id else 'None'}")
        print(f"Qty In: {self.qty_in}")
        print(f"Weight: {self.weight}")
        print(f"Tariff Rule: {self.tariff_rule_id.name if self.tariff_rule_id else 'None'}")
        
        if self.tariff_rule_id:
            amount, duration_days = self.tariff_rule_id.compute_amount(self)
            print(f"Manual Calculation Result: {amount:,.2f}")
        else:
            print("No tariff rule assigned")
        print(f"=== END MANUAL DEBUG ===\n")
        
        return True
    
    @api.constrains('qty_in', 'qty_out')
    def _check_quantities(self):
        for line in self:
            if line.qty_out > line.qty_in:
                raise ValidationError(_('Quantity out cannot exceed quantity in.'))
            if line.qty_in <= 0:
                raise ValidationError(_('Quantity in must be positive.'))
    
    @api.constrains('weight', 'volume')
    def _check_physical_properties(self):
        for line in self:
            if line.weight and line.weight < 0:
                raise ValidationError(_('Weight cannot be negative.'))
            if line.volume and line.volume < 0:
                raise ValidationError(_('Volume cannot be negative.'))
