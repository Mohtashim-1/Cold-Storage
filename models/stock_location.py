# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class StockLocation(models.Model):
    _inherit = 'stock.location'

    is_freezer = fields.Boolean(
        string='Is Freezer',
        default=False,
        help='Check if this location is a freezer/cold storage'
    )
    temperature_range_min = fields.Float(
        string='Min Temperature (°C)',
        help='Minimum temperature for this freezer'
    )
    temperature_range_max = fields.Float(
        string='Max Temperature (°C)',
        help='Maximum temperature for this freezer'
    )
    max_volume = fields.Float(
        string='Max Volume (m³)',
        help='Maximum volume capacity in cubic meters'
    )
    max_weight = fields.Float(
        string='Max Weight (kg)',
        help='Maximum weight capacity in kilograms'
    )
    current_volume = fields.Float(
        string='Current Volume (m³)',
        compute='_compute_current_capacity',
        store=True,
        help='Current volume usage'
    )
    current_weight = fields.Float(
        string='Current Weight (kg)',
        compute='_compute_current_capacity',
        store=True,
        help='Current weight usage'
    )
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
    
    # Related fields
    intake_ids = fields.One2many(
        'cs.storage.intake',
        'location_id',
        string='Active Intakes'
    )
    temperature_log_ids = fields.One2many(
        'cs.temperature.log',
        'location_id',
        string='Temperature Logs'
    )
    
    # Computed counts
    intake_count = fields.Integer(
        string='Intake Count',
        compute='_compute_intake_count',
        store=True
    )
    temperature_log_count = fields.Integer(
        string='Temperature Log Count',
        compute='_compute_temperature_log_count',
        store=True
    )
    
    @api.depends('intake_ids.total_volume', 'intake_ids.total_weight')
    def _compute_current_capacity(self):
        for location in self:
            if location.is_freezer:
                location.current_volume = sum(location.intake_ids.filtered(lambda i: i.state in ['checked_in', 'partially_out']).mapped('total_volume'))
                location.current_weight = sum(location.intake_ids.filtered(lambda i: i.state in ['checked_in', 'partially_out']).mapped('total_weight'))
            else:
                location.current_volume = 0
                location.current_weight = 0
    
    @api.depends('current_volume', 'max_volume', 'current_weight', 'max_weight')
    def _compute_utilization(self):
        for location in self:
            if location.max_volume > 0:
                location.volume_utilization = (location.current_volume / location.max_volume) * 100
            else:
                location.volume_utilization = 0
            
            if location.max_weight > 0:
                location.weight_utilization = (location.current_weight / location.max_weight) * 100
            else:
                location.weight_utilization = 0
    
    @api.depends('intake_ids')
    def _compute_intake_count(self):
        for location in self:
            location.intake_count = len(location.intake_ids.filtered(lambda i: i.state in ['checked_in', 'partially_out']))
    
    @api.depends('temperature_log_ids')
    def _compute_temperature_log_count(self):
        for location in self:
            location.temperature_log_count = len(location.temperature_log_ids)
    
    @api.constrains('temperature_range_min', 'temperature_range_max')
    def _check_temperature_range(self):
        for location in self:
            if location.is_freezer and location.temperature_range_min and location.temperature_range_max:
                if location.temperature_range_min > location.temperature_range_max:
                    raise ValidationError(_('Minimum temperature cannot be greater than maximum temperature.'))
    
    @api.constrains('max_volume', 'max_weight')
    def _check_capacity(self):
        for location in self:
            if location.is_freezer:
                if location.max_volume and location.max_volume <= 0:
                    raise ValidationError(_('Maximum volume must be positive.'))
                if location.max_weight and location.max_weight <= 0:
                    raise ValidationError(_('Maximum weight must be positive.'))
    
    def action_view_intakes(self):
        """View intakes for this freezer"""
        return {
            'type': 'ir.actions.act_window',
            'name': _('Freezer Intakes'),
            'res_model': 'cs.storage.intake',
            'view_mode': 'tree,form',
            'domain': [('location_id', '=', self.id)],
            'context': {'default_location_id': self.id},
        }
    
    def action_view_temperature_logs(self):
        """View temperature logs for this freezer"""
        return {
            'type': 'ir.actions.act_window',
            'name': _('Temperature Logs'),
            'res_model': 'cs.temperature.log',
            'view_mode': 'tree,form,graph',
            'domain': [('location_id', '=', self.id)],
            'context': {'default_location_id': self.id},
        }
