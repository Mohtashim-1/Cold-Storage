# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError


class CsStockRelease(models.Model):
    _name = 'cs.stock.release'
    _description = 'Cold Storage Release'
    _order = 'date_out desc, name desc'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(
        string='Release No.',
        required=True,
        copy=False,
        readonly=True,
        default=lambda self: _('New')
    )
    intake_id = fields.Many2one(
        'cs.storage.intake',
        string='Intake',
        required=True,
        tracking=True,
        help='Related intake document'
    )
    partner_id = fields.Many2one(
        'res.partner',
        string='Customer',
        related='intake_id.partner_id',
        store=True,
        readonly=True
    )
    date_out = fields.Datetime(
        string='Release Time',
        required=True,
        default=fields.Datetime.now,
        tracking=True
    )
    
    state = fields.Selection([
        ('draft', 'Draft'),
        ('done', 'Done'),
        ('cancelled', 'Cancelled'),
    ], string='Status', default='draft', tracking=True, required=True)
    
    # Related fields
    line_ids = fields.One2many(
        'cs.stock.release.line',
        'release_id',
        string='Release Lines',
        copy=True
    )
    move_ids = fields.One2many(
        'stock.move',
        'origin',
        string='Stock Moves',
        domain=[('origin', '=', False)]  # Will be set after creation
    )
    
    # Computed fields
    total_qty_out = fields.Float(
        string='Total Qty Out',
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
        related='intake_id.currency_id',
        store=True
    )
    
    # Gate Entry
    gate_out_id = fields.Many2one(
        'cs.gate.entry',
        string='Gate Out Entry',
        readonly=True,
        help='Gate entry record for this release'
    )
    vehicle_number = fields.Char(
        string='Vehicle Number',
        help='Vehicle registration number (from gate entry)'
    )
    driver_name = fields.Char(
        string='Driver Name',
        help='Driver name (from gate entry)'
    )
    
    # Company
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        default=lambda self: self.env.company,
        required=True
    )
    
    @api.depends('line_ids.qty_out', 'line_ids.amount_line')
    def _compute_totals(self):
        for record in self:
            record.total_qty_out = sum(record.line_ids.mapped('qty_out'))
            record.total_amount = sum(record.line_ids.mapped('amount_line'))
    
    @api.model
    def create(self, vals):
        if vals.get('name', _('New')) == _('New'):
            vals['name'] = self.env['ir.sequence'].next_by_code('cs.stock.release') or _('New')
        return super().create(vals)
    
    def action_validate(self):
        """Validate the release and create stock moves"""
        for record in self:
            if record.state != 'draft':
                raise UserError(_('Only draft releases can be validated.'))
            
            if not record.line_ids:
                raise UserError(_('Please add at least one release line.'))
            
            # Update intake lines with release quantities
            for line in record.line_ids:
                if line.intake_line_id:
                    # Update intake line
                    intake_line = line.intake_line_id
                    new_qty_out = intake_line.qty_out + line.qty_out
                    
                    if new_qty_out > intake_line.qty_in:
                        raise UserError(_('Cannot release more than available quantity for product %s.') % intake_line.product_id.name)
                    
                    intake_line.qty_out = new_qty_out
                    intake_line.date_out = record.date_out
                    
                    # Update intake state
                    if new_qty_out >= intake_line.qty_in:
                        # Line fully released
                        pass
                    elif intake_line.qty_out > 0:
                        # Line partially released
                        if record.intake_id.state == 'checked_in':
                            record.intake_id.state = 'partially_out'
            
            # Create stock moves if location has stock tracking enabled
            if record.intake_id.location_id.usage == 'internal':
                for line in record.line_ids:
                    if line.product_id.type in ['product', 'consu']:
                        # Create outgoing move
                        move_vals = {
                            'name': f'OUT-{record.name}',
                            'product_id': line.product_id.id,
                            'product_uom_qty': line.qty_out,
                            'product_uom': line.intake_line_id.qty_uom_id.id,
                            'location_id': record.intake_id.location_id.id,
                            'location_dest_id': self.env.ref('stock.stock_location_customers').id,
                            'origin': record.name,
                            'company_id': record.company_id.id,
                        }
                        if line.lot_id:
                            move_vals['lot_ids'] = [(4, line.lot_id.id)]
                        
                        move = self.env['stock.move'].create(move_vals)
                        move._action_confirm()
                        move._action_assign()
                        move._action_done()
            
            record.state = 'done'
            record.message_post(body=_('Release validated successfully.'))
    
    def action_cancel(self):
        """Cancel the release"""
        for record in self:
            if record.state == 'done':
                raise UserError(_('Cannot cancel a validated release.'))
            record.state = 'cancelled'
            record.message_post(body=_('Release cancelled.'))
    
    def action_create_invoice(self):
        """Create customer invoice for storage charges"""
        for record in self:
            if record.state != 'done':
                raise UserError(_('Only validated releases can be invoiced.'))
            
            if not record.line_ids:
                raise UserError(_('No release lines to invoice.'))
            
            # Create invoice
            invoice_vals = {
                'partner_id': record.partner_id.id,
                'move_type': 'out_invoice',
                'invoice_date': fields.Date.today(),
                'ref': f'Storage charges for {record.name}',
                'company_id': record.company_id.id,
                'currency_id': record.currency_id.id,
                'invoice_line_ids': [],
            }
            
            for line in record.line_ids:
                if line.amount_line > 0:
                    invoice_line_vals = {
                        'product_id': line.intake_line_id.tariff_rule_id.price_product_id.id,
                        'name': f'Storage: {line.product_id.name} ({line.intake_line_id.lot_id.name or "No Lot"}) from {line.intake_line_id.date_in.strftime("%Y-%m-%d")} to {record.date_out.strftime("%Y-%m-%d")}, {line.intake_line_id.duration_days:.2f} days @ {line.intake_line_id.price_unit:.2f}/{line.intake_line_id.bill_basis}',
                        'quantity': 1,
                        'price_unit': line.amount_line,
                        'account_id': line.intake_line_id.tariff_rule_id.price_product_id.property_account_income_id.id,
                    }
                    invoice_vals['invoice_line_ids'].append((0, 0, invoice_line_vals))
            
            if invoice_vals['invoice_line_ids']:
                invoice = self.env['account.move'].create(invoice_vals)
                return {
                    'type': 'ir.actions.act_window',
                    'name': _('Customer Invoice'),
                    'res_model': 'account.move',
                    'res_id': invoice.id,
                    'view_mode': 'form',
                    'target': 'current',
                }
            else:
                raise UserError(_('No charges to invoice.'))


class CsStockReleaseLine(models.Model):
    _name = 'cs.stock.release.line'
    _description = 'Cold Storage Release Line'
    _order = 'release_id, id'

    release_id = fields.Many2one(
        'cs.stock.release',
        string='Release',
        required=True,
        ondelete='cascade'
    )
    intake_line_id = fields.Many2one(
        'cs.storage.intake.line',
        string='Intake Line',
        required=True,
        domain="[('intake_id', '=', parent.intake_id)]"
    )
    product_id = fields.Many2one(
        'product.product',
        string='Product',
        related='intake_line_id.product_id',
        store=True,
        readonly=True
    )
    lot_id = fields.Many2one(
        'stock.lot',
        string='Lot',
        related='intake_line_id.lot_id',
        store=True,
        readonly=True
    )
    qty_available = fields.Float(
        string='Available Qty',
        related='intake_line_id.qty_in',
        store=True,
        readonly=True
    )
    qty_released = fields.Float(
        string='Previously Released',
        related='intake_line_id.qty_out',
        store=True,
        readonly=True
    )
    qty_out = fields.Float(
        string='Qty Out',
        required=True,
        help='Quantity to release'
    )
    amount_line = fields.Monetary(
        string='Storage Charge',
        compute='_compute_amount_line',
        store=True,
        help='Storage charge for this release'
    )
    currency_id = fields.Many2one(
        'res.currency',
        string='Currency',
        related='release_id.currency_id',
        store=True
    )
    
    @api.depends('qty_out', 'intake_line_id.amount_subtotal', 'intake_line_id.qty_in')
    def _compute_amount_line(self):
        print(f"\n=== RELEASE LINE AMOUNT CALCULATION DEBUG ===")
        for line in self:
            print(f"Processing Release Line ID: {line.id}")
            print(f"  Product: {line.product_id.name if line.product_id else 'None'}")
            print(f"  Qty Out: {line.qty_out}")
            print(f"  Intake Line ID: {line.intake_line_id.id}")
            print(f"  Intake Line Qty In: {line.intake_line_id.qty_in}")
            print(f"  Intake Line Amount Subtotal: {line.intake_line_id.amount_subtotal}")
            
            if line.intake_line_id.qty_in > 0:
                # Pro-rata calculation for partial release
                amount = (line.intake_line_id.amount_subtotal * line.qty_out) / line.intake_line_id.qty_in
                line.amount_line = amount
                print(f"  Pro-rata calculation: ({line.intake_line_id.amount_subtotal} × {line.qty_out}) ÷ {line.intake_line_id.qty_in} = {amount:,.2f}")
            else:
                line.amount_line = 0
                print(f"  Intake line qty_in is 0, amount = 0")
        print(f"=== END RELEASE LINE AMOUNT CALCULATION DEBUG ===\n")
    
    @api.constrains('qty_out')
    def _check_qty_out(self):
        for line in self:
            if line.qty_out <= 0:
                raise ValidationError(_('Quantity out must be positive.'))
            
            available_qty = line.qty_available - line.qty_released
            if line.qty_out > available_qty:
                raise ValidationError(_('Cannot release more than available quantity. Available: %s') % available_qty)
    
    @api.onchange('intake_line_id')
    def _onchange_intake_line_id(self):
        if self.intake_line_id:
            self.qty_out = min(1.0, self.intake_line_id.qty_in - self.intake_line_id.qty_out)
