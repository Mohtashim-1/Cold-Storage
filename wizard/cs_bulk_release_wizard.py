# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError


class CsBulkReleaseWizard(models.TransientModel):
    _name = 'cs.bulk.release.wizard'
    _description = 'Bulk Release Wizard'

    intake_id = fields.Many2one(
        'cs.storage.intake',
        string='Intake',
        required=True,
        domain=[('state', 'in', ['checked_in', 'partially_out'])]
    )
    partner_id = fields.Many2one(
        'res.partner',
        string='Customer',
        related='intake_id.partner_id',
        readonly=True
    )
    date_out = fields.Datetime(
        string='Release Time',
        required=True,
        default=fields.Datetime.now
    )
    line_ids = fields.One2many(
        'cs.bulk.release.wizard.line',
        'wizard_id',
        string='Release Lines'
    )
    
    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        if 'intake_id' in self.env.context:
            res['intake_id'] = self.env.context['intake_id']
        return res
    
    @api.onchange('intake_id')
    def _onchange_intake_id(self):
        if self.intake_id:
            lines = []
            for intake_line in self.intake_id.line_ids.filtered(lambda l: l.qty_out < l.qty_in):
                lines.append((0, 0, {
                    'intake_line_id': intake_line.id,
                    'product_id': intake_line.product_id.id,
                    'lot_id': intake_line.lot_id.id,
                    'qty_available': intake_line.qty_in - intake_line.qty_out,
                    'qty_out': intake_line.qty_in - intake_line.qty_out,  # Default to full release
                }))
            self.line_ids = lines
    
    def action_create_release(self):
        """Create release with selected lines"""
        if not self.line_ids:
            raise UserError(_('Please select at least one line to release.'))
        
        # Create release
        release_vals = {
            'intake_id': self.intake_id.id,
            'date_out': self.date_out,
            'line_ids': [],
        }
        
        for line in self.line_ids:
            if line.qty_out > 0:
                release_vals['line_ids'].append((0, 0, {
                    'intake_line_id': line.intake_line_id.id,
                    'qty_out': line.qty_out,
                }))
        
        if release_vals['line_ids']:
            release = self.env['cs.stock.release'].create(release_vals)
            release.action_validate()
            
            return {
                'type': 'ir.actions.act_window',
                'name': _('Release Created'),
                'res_model': 'cs.stock.release',
                'res_id': release.id,
                'view_mode': 'form',
                'target': 'current',
            }
        else:
            raise UserError(_('No valid lines to release.'))


class CsBulkReleaseWizardLine(models.TransientModel):
    _name = 'cs.bulk.release.wizard.line'
    _description = 'Bulk Release Wizard Line'

    wizard_id = fields.Many2one(
        'cs.bulk.release.wizard',
        string='Wizard',
        required=True,
        ondelete='cascade'
    )
    intake_line_id = fields.Many2one(
        'cs.storage.intake.line',
        string='Intake Line',
        required=True
    )
    product_id = fields.Many2one(
        'product.product',
        string='Product',
        related='intake_line_id.product_id',
        readonly=True
    )
    lot_id = fields.Many2one(
        'stock.lot',
        string='Lot',
        related='intake_line_id.lot_id',
        readonly=True
    )
    qty_available = fields.Float(
        string='Available Qty',
        readonly=True
    )
    qty_out = fields.Float(
        string='Qty Out',
        required=True
    )
    
    @api.constrains('qty_out')
    def _check_qty_out(self):
        for line in self:
            if line.qty_out <= 0:
                raise UserError(_('Quantity out must be positive.'))
            if line.qty_out > line.qty_available:
                raise UserError(_('Cannot release more than available quantity.'))
