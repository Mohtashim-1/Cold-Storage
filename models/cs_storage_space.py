# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError


class CsStorageSpace(models.Model):
    _name = 'cs.storage.space'
    _description = 'Storage Space/Bin'
    _order = 'location_id, name'

    name = fields.Char(
        string='Space Name',
        required=True,
        help='Name or code of the storage space/bin'
    )
    location_id = fields.Many2one(
        'stock.location',
        string='Freezer Location',
        required=True,
        domain=[('is_freezer', '=', True)],
        help='Freezer location where this space is located'
    )
    
    # Capacity
    max_volume = fields.Float(
        string='Max Volume (m³)',
        help='Maximum volume capacity'
    )
    max_weight = fields.Float(
        string='Max Weight (kg)',
        help='Maximum weight capacity'
    )
    
    # Current usage
    current_volume = fields.Float(
        string='Current Volume (m³)',
        compute='_compute_current_usage',
        store=True,
        help='Current volume usage'
    )
    current_weight = fields.Float(
        string='Current Weight (kg)',
        compute='_compute_current_usage',
        store=True,
        help='Current weight usage'
    )
    
    # Availability
    is_available = fields.Boolean(
        string='Available',
        compute='_compute_availability',
        store=True,
        help='Whether this space is available for new storage'
    )
    availability_status = fields.Selection([
        ('available', 'Available'),
        ('occupied', 'Occupied'),
        ('reserved', 'Reserved'),
        ('maintenance', 'Under Maintenance'),
    ], string='Status', compute='_compute_availability', store=True)
    
    # Related intakes
    intake_line_ids = fields.One2many(
        'cs.storage.intake.line',
        'space_id',
        string='Stored Items',
        help='Items currently stored in this space'
    )
    
    # Utilization
    volume_utilization = fields.Float(
        string='Volume Utilization %',
        compute='_compute_utilization',
        store=True,
        help='Volume utilization percentage'
    )
    weight_utilization = fields.Float(
        string='Weight Utilization %',
        compute='_compute_utilization',
        store=True,
        help='Weight utilization percentage'
    )
    
    @api.depends('current_volume', 'max_volume', 'current_weight', 'max_weight')
    def _compute_utilization(self):
        for space in self:
            if space.max_volume > 0:
                space.volume_utilization = (space.current_volume / space.max_volume) * 100
            else:
                space.volume_utilization = 0
            
            if space.max_weight > 0:
                space.weight_utilization = (space.current_weight / space.max_weight) * 100
            else:
                space.weight_utilization = 0
    
    # Company
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        default=lambda self: self.env.company,
        required=True
    )
    
    active = fields.Boolean(
        string='Active',
        default=True,
        help='Uncheck to disable this space'
    )
    
    notes = fields.Text(
        string='Notes',
        help='Additional notes about this space'
    )
    
    @api.depends('intake_line_ids.volume', 'intake_line_ids.weight', 'intake_line_ids.intake_id.state')
    def _compute_current_usage(self):
        for space in self:
            # Only count active intakes (checked in or partially out)
            active_lines = space.intake_line_ids.filtered(
                lambda l: l.intake_id.state in ['checked_in', 'partially_out'] and l.qty_out < l.qty_in
            )
            space.current_volume = sum(active_lines.mapped('volume'))
            space.current_weight = sum(active_lines.mapped('weight'))
    
    @api.depends('current_volume', 'max_volume', 'current_weight', 'max_weight', 'active')
    def _compute_availability(self):
        for space in self:
            if not space.active:
                space.is_available = False
                space.availability_status = 'maintenance'
            elif space.max_volume > 0 and space.current_volume >= space.max_volume:
                space.is_available = False
                space.availability_status = 'occupied'
            elif space.max_weight > 0 and space.current_weight >= space.max_weight:
                space.is_available = False
                space.availability_status = 'occupied'
            elif space.current_volume > 0 or space.current_weight > 0:
                space.is_available = True
                space.availability_status = 'occupied'
            else:
                space.is_available = True
                space.availability_status = 'available'
    
    def action_view_stored_items(self):
        """View items stored in this space"""
        return {
            'type': 'ir.actions.act_window',
            'name': _('Stored Items'),
            'res_model': 'cs.storage.intake.line',
            'view_mode': 'tree,form',
            'domain': [('space_id', '=', self.id)],
            'context': {'default_space_id': self.id},
        }
    
    @api.constrains('max_volume', 'max_weight')
    def _check_capacity(self):
        for space in self:
            if space.max_volume and space.max_volume <= 0:
                raise ValidationError(_('Maximum volume must be positive.'))
            if space.max_weight and space.max_weight <= 0:
                raise ValidationError(_('Maximum weight must be positive.'))

