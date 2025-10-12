# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class CsTemperatureLog(models.Model):
    _name = 'cs.temperature.log'
    _description = 'Temperature Log'
    _order = 'timestamp desc'
    _rec_name = 'display_name'

    intake_id = fields.Many2one(
        'cs.storage.intake',
        string='Intake',
        help='Related intake (optional)'
    )
    location_id = fields.Many2one(
        'stock.location',
        string='Location',
        required=True,
        domain=[('is_freezer', '=', True)],
        help='Freezer location being monitored'
    )
    timestamp = fields.Datetime(
        string='Time',
        required=True,
        default=fields.Datetime.now,
        help='Time of temperature reading'
    )
    temperature = fields.Float(
        string='Temperature (°C)',
        required=True,
        help='Temperature reading in Celsius'
    )
    sensor_id = fields.Char(
        string='Sensor Reference',
        help='Sensor identifier or reference'
    )
    
    # Computed fields
    display_name = fields.Char(
        string='Display Name',
        compute='_compute_display_name',
        store=True
    )
    temperature_status = fields.Selection([
        ('normal', 'Normal'),
        ('high', 'High'),
        ('low', 'Low'),
        ('critical', 'Critical'),
    ], string='Status', compute='_compute_temperature_status', store=True)
    
    # Company
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        default=lambda self: self.env.company,
        required=True
    )
    
    @api.depends('location_id', 'timestamp', 'temperature')
    def _compute_display_name(self):
        for record in self:
            record.display_name = f"{record.location_id.name} - {record.temperature}°C - {record.timestamp.strftime('%Y-%m-%d %H:%M') if record.timestamp else ''}"
    
    @api.depends('temperature', 'intake_id.temperature_target')
    def _compute_temperature_status(self):
        for record in self:
            if not record.temperature:
                record.temperature_status = 'normal'
                continue
            
            target_temp = record.intake_id.temperature_target if record.intake_id else 0
            temp_diff = abs(record.temperature - target_temp) if target_temp else 0
            
            if temp_diff <= 2:
                record.temperature_status = 'normal'
            elif temp_diff <= 5:
                record.temperature_status = 'high' if record.temperature > target_temp else 'low'
            else:
                record.temperature_status = 'critical'
    
    @api.constrains('temperature')
    def _check_temperature(self):
        for record in self:
            if record.temperature < -50 or record.temperature > 50:
                raise ValidationError(_('Temperature must be between -50°C and 50°C.'))
    
    @api.constrains('timestamp')
    def _check_timestamp(self):
        for record in self:
            if record.timestamp > fields.Datetime.now():
                raise ValidationError(_('Temperature log timestamp cannot be in the future.'))
    
    def action_view_intake(self):
        """View related intake"""
        if self.intake_id:
            return {
                'type': 'ir.actions.act_window',
                'name': _('Related Intake'),
                'res_model': 'cs.storage.intake',
                'res_id': self.intake_id.id,
                'view_mode': 'form',
                'target': 'current',
            }
    
    def action_view_location(self):
        """View related location"""
        return {
            'type': 'ir.actions.act_window',
            'name': _('Freezer Location'),
            'res_model': 'stock.location',
            'res_id': self.location_id.id,
            'view_mode': 'form',
            'target': 'current',
        }
