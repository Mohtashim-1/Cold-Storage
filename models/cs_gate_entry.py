# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError
from datetime import datetime


class CsGateEntry(models.Model):
    _name = 'cs.gate.entry'
    _description = 'Gate Entry (In/Out)'
    _order = 'entry_time desc, name desc'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(
        string='Entry No.',
        required=True,
        copy=False,
        readonly=True,
        default=lambda self: _('New')
    )
    entry_type = fields.Selection([
        ('gate_in', 'Gate In'),
        ('gate_out', 'Gate Out'),
    ], string='Entry Type', required=True, default='gate_in', tracking=True)
    
    vehicle_number = fields.Char(
        string='Vehicle Number',
        required=True,
        tracking=True,
        help='Vehicle registration number'
    )
    driver_name = fields.Char(
        string='Driver Name',
        required=True,
        tracking=True,
        help='Name of the driver'
    )
    driver_contact = fields.Char(
        string='Driver Contact',
        help='Driver contact number'
    )
    
    entry_time = fields.Datetime(
        string='Entry Time',
        required=True,
        default=fields.Datetime.now,
        tracking=True,
        help='Time when vehicle entered/exited'
    )
    entry_date = fields.Date(
        string='Entry Date',
        compute='_compute_entry_date',
        store=True,
        help='Date of entry'
    )
    
    # Related to intake/release
    intake_id = fields.Many2one(
        'cs.storage.intake',
        string='Storage Intake',
        domain=[('state', '!=', 'cancelled')],
        help='Related storage intake (for Gate In)'
    )
    release_id = fields.Many2one(
        'cs.stock.release',
        string='Storage Release',
        domain=[('state', '!=', 'cancelled')],
        help='Related storage release (for Gate Out)'
    )
    
    # Guard information
    guard_user_id = fields.Many2one(
        'res.users',
        string='Guard User',
        default=lambda self: self.env.user,
        required=True,
        readonly=True,
        tracking=True,
        help='Guard who recorded this entry'
    )
    
    # Status
    state = fields.Selection([
        ('draft', 'Draft'),
        ('confirmed', 'Confirmed'),
        ('cancelled', 'Cancelled'),
    ], string='Status', default='draft', tracking=True, required=True)
    
    # Additional information
    notes = fields.Text(
        string='Notes',
        help='Additional notes or remarks'
    )
    
    # Company
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        default=lambda self: self.env.company,
        required=True
    )
    
    @api.depends('entry_time')
    def _compute_entry_date(self):
        for record in self:
            if record.entry_time:
                record.entry_date = record.entry_time.date()
            else:
                record.entry_date = False
    
    @api.model
    def create(self, vals):
        if vals.get('name', _('New')) == _('New'):
            seq_code = 'cs.gate.entry'
            if vals.get('entry_type') == 'gate_out':
                seq_code = 'cs.gate.exit'
            vals['name'] = self.env['ir.sequence'].next_by_code(seq_code) or _('New')
        return super().create(vals)
    
    def action_confirm(self):
        """Confirm the gate entry"""
        for record in self:
            if record.state != 'draft':
                raise UserError(_('Only draft entries can be confirmed.'))
            
            # Link to intake/release if linked (optional)
            if record.entry_type == 'gate_in' and record.intake_id:
                # Update intake with vehicle info
                record.intake_id.write({
                    'gate_in_id': record.id,
                    'vehicle_number': record.vehicle_number,
                    'driver_name': record.driver_name,
                })
            elif record.entry_type == 'gate_out' and record.release_id:
                # Update release with vehicle info
                record.release_id.write({
                    'gate_out_id': record.id,
                    'vehicle_number': record.vehicle_number,
                    'driver_name': record.driver_name,
                })
            
            record.state = 'confirmed'
            record.message_post(body=_('Gate entry confirmed by %s') % record.guard_user_id.name)
    
    def action_cancel(self):
        """Cancel the gate entry"""
        for record in self:
            if record.state == 'confirmed':
                raise UserError(_('Cannot cancel a confirmed entry.'))
            record.state = 'cancelled'
            record.message_post(body=_('Gate entry cancelled.'))
    
    def action_create_intake(self):
        """Open form to create a storage intake from this gate entry"""
        self.ensure_one()
        if self.entry_type != 'gate_in':
            raise UserError(_('Can only create intake from Gate In entries.'))
        
        if self.intake_id:
            # If intake already exists, just open it
            return {
                'type': 'ir.actions.act_window',
                'name': _('Storage Intake'),
                'res_model': 'cs.storage.intake',
                'res_id': self.intake_id.id,
                'view_mode': 'form',
                'target': 'current',
            }
        
        # Open intake form in create mode with pre-filled values
        return {
            'type': 'ir.actions.act_window',
            'name': _('Create Storage Intake'),
            'res_model': 'cs.storage.intake',
            'view_mode': 'form',
            'target': 'current',
            'context': {
                'default_gate_in_id': self.id,
                'default_vehicle_number': self.vehicle_number,
                'default_driver_name': self.driver_name,
                'default_date_in': self.entry_time,
                'default_note': _('Created from Gate Entry: %s\nVehicle: %s\nDriver: %s') % (
                    self.name, self.vehicle_number, self.driver_name
                ),
            },
        }

