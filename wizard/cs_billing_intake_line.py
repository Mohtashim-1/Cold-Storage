# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from datetime import datetime, timedelta


class CsBillingIntakeLine(models.TransientModel):
    _name = 'cs.billing.intake.line'
    _description = 'Billing Intake Line'
    _order = 'id desc'

    wizard_id = fields.Many2one(
        'cs.monthly.billing.wizard',
        string='Wizard',
        required=True,
        ondelete='cascade'
    )
    intake_id = fields.Many2one(
        'cs.storage.intake',
        string='Intake',
        required=True,
        readonly=True
    )
    partner_id = fields.Many2one(
        'res.partner',
        string='Customer',
        related='intake_id.partner_id',
        readonly=True
    )
    date_in = fields.Datetime(
        string='Check-in Date',
        related='intake_id.date_in',
        readonly=True
    )
    location_id = fields.Many2one(
        'stock.location',
        string='Location',
        related='intake_id.location_id',
        readonly=True
    )
    
    # Days information
    total_days = fields.Float(
        string='Total Days',
        compute='_compute_days_info',
        store=False,
        digits=(16, 2),
        help='Total days since check-in'
    )
    billed_days = fields.Float(
        string='Billed Days',
        compute='_compute_days_info',
        store=False,
        digits=(16, 2),
        help='Days already billed'
    )
    pending_days = fields.Float(
        string='Pending Days',
        compute='_compute_days_info',
        store=False,
        digits=(16, 2),
        help='Days pending billing'
    )
    
    # Amount information
    period_amount = fields.Monetary(
        string='Period Amount',
        compute='_compute_amount_info',
        store=False,
        help='Amount for this billing period'
    )
    total_amount = fields.Monetary(
        string='Total Amount',
        related='intake_id.total_amount',
        readonly=True
    )
    currency_id = fields.Many2one(
        'res.currency',
        string='Currency',
        related='wizard_id.currency_id',
        readonly=True
    )
    
    # Selection
    select = fields.Boolean(
        string='Select',
        default=True,
        help='Select this intake for billing'
    )
    
    @api.depends('intake_id.date_in', 'intake_id.last_billed_date', 'wizard_id.date_to', 'wizard_id.date_from')
    def _compute_days_info(self):
        for line in self:
            if not line.intake_id or not line.intake_id.date_in or not line.wizard_id:
                line.total_days = 0
                line.billed_days = 0
                line.pending_days = 0
                continue
            
            from datetime import datetime, time as dt_time
            today = fields.Datetime.now()
            date_in = line.intake_id.date_in
            
            # Total days since check-in
            total_delta = today - date_in
            line.total_days = total_delta.total_seconds() / 86400  # days
            
            # Billed days (from date_in to last_billed_date)
            if line.intake_id.last_billed_date:
                billed_end = datetime.combine(line.intake_id.last_billed_date, dt_time.max)
                billed_delta = billed_end - date_in
                line.billed_days = billed_delta.total_seconds() / 86400
            else:
                line.billed_days = 0
            
            # Pending days (from last_billed_date or date_in to date_to)
            billing_start_date = line.intake_id.last_billed_date or date_in.date()
            billing_end_date = line.wizard_id.date_to
            
            # Use the later of billing_start_date or date_from
            period_start_date = max(billing_start_date, line.wizard_id.date_from)
            
            if period_start_date > billing_end_date:
                line.pending_days = 0
            else:
                # If period starts on intake date, use actual intake time
                if period_start_date == date_in.date():
                    pending_start = date_in
                else:
                    pending_start = datetime.combine(period_start_date, dt_time.min)
                
                pending_end = datetime.combine(billing_end_date, dt_time.max)
                pending_delta = pending_end - pending_start
                line.pending_days = pending_delta.total_seconds() / 86400
    
    @api.depends('intake_id', 'wizard_id.date_from', 'wizard_id.date_to', 'wizard_id.company_id')
    def _compute_amount_info(self):
        for line in self:
            if not line.intake_id or not line.wizard_id:
                line.period_amount = 0
                continue
            
            # Calculate billing period
            billing_start = line.intake_id.last_billed_date or line.intake_id.date_in.date() if line.intake_id.date_in else fields.Date.today()
            billing_end = line.wizard_id.date_to
            
            if billing_start >= billing_end:
                line.period_amount = 0
            else:
                # Use wizard's method to calculate period amount
                line.period_amount = line.wizard_id._calculate_period_amount(line.intake_id, billing_start, billing_end)

