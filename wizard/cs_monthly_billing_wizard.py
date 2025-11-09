# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError
from datetime import datetime, timedelta


class CsMonthlyBillingWizard(models.TransientModel):
    _name = 'cs.monthly.billing.wizard'
    _description = 'Monthly Billing Wizard'

    company_id = fields.Many2one(
        'res.company',
        string='Company',
        required=True,
        default=lambda self: self.env.company
    )
    date_from = fields.Date(
        string='From Date',
        required=True,
        default=lambda self: (fields.Date.today() - timedelta(days=30)).replace(day=1)
    )
    date_to = fields.Date(
        string='To Date',
        required=True,
        default=lambda self: fields.Date.today()
    )
    bill_unbilled_only = fields.Boolean(
        string='Bill Unbilled Consignments Only',
        default=True,
        help='Bill only consignments that have not been billed yet and are not yet released'
    )
    reset_billing_date = fields.Boolean(
        string='Reset Last Billed Date',
        default=False,
        help='Reset last_billed_date for intakes that have no active invoices. Use this if invoices were deleted.'
    )
    partner_ids = fields.Many2many(
        'res.partner',
        string='Customers',
        help='Leave empty to process all customers'
    )
    contract_ids = fields.Many2many(
        'cs.storage.contract',
        string='Contracts',
        domain="[('state', '=', 'active')]",
        help='Leave empty to process all active contracts'
    )
    create_invoices = fields.Boolean(
        string='Create Invoices',
        default=True,
        help='Create actual invoices (uncheck for preview only)'
    )
    invoice_date = fields.Date(
        string='Invoice Date',
        default=lambda self: fields.Date.today(),
        required=True,
        help='Date to use for the invoice'
    )
    
    # Intake lines
    intake_line_ids = fields.One2many(
        'cs.billing.intake.line',
        'wizard_id',
        string='Intakes',
        help='Intakes available for billing'
    )
    
    # Results
    invoice_count = fields.Integer(
        string='Invoices Created',
        compute='_compute_results',
        store=True
    )
    total_amount = fields.Monetary(
        string='Total Amount',
        compute='_compute_results',
        store=True
    )
    currency_id = fields.Many2one(
        'res.currency',
        string='Currency',
        related='company_id.currency_id'
    )
    
    @api.depends('create_invoices', 'intake_line_ids.period_amount', 'intake_line_ids.select')
    def _compute_results(self):
        for record in self:
            selected_lines = record.intake_line_ids.filtered(lambda l: l.select)
            record.total_amount = sum(selected_lines.mapped('period_amount'))
            record.invoice_count = 0  # Will be updated after invoice creation
    
    @api.model
    def create(self, vals):
        """Load intakes when wizard is created"""
        wizard = super().create(vals)
        # Load intakes after creation
        wizard._load_intakes()
        return wizard
    
    @api.onchange('date_from', 'date_to', 'company_id', 'partner_ids', 'contract_ids', 'bill_unbilled_only')
    def _onchange_filters(self):
        """Update intake lines when filters change"""
        if self.id:  # Only if wizard is already created
            self._load_intakes()
    
    def action_load_intakes(self):
        """Manually load intakes"""
        self._load_intakes()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Intakes Loaded'),
                'message': _('Intakes have been loaded based on the selected filters.'),
                'type': 'success',
                'sticky': False,
            }
        }
    
    def _load_intakes(self):
        """Load intakes based on filters"""
        # Get billable intakes - intakes that are still active (not fully released)
        domain = [
            ('company_id', '=', self.company_id.id),
            ('state', 'in', ['checked_in', 'partially_out']),  # Only active intakes
        ]
        
        # Filter by date range - find intakes that need billing for this period
        if self.bill_unbilled_only:
            # Bill intakes that:
            # 1. Were checked in before or on date_to (still in storage during this period)
            # 2. Have not been billed yet OR last billed date is before date_from
            domain.append(('date_in', '<=', self.date_to))
            # Add condition for unbilled or needs billing for this period
            domain.append('|')
            domain.append(('last_billed_date', '=', False))
            domain.append(('last_billed_date', '<', self.date_from))
        else:
            # Bill all active intakes that were checked in before or on date_to
            domain.append(('date_in', '<=', self.date_to))
        
        if self.partner_ids:
            domain.append(('partner_id', 'in', self.partner_ids.ids))
        
        if self.contract_ids:
            domain.append(('contract_id', 'in', self.contract_ids.ids))
        
        intakes = self.env['cs.storage.intake'].search(domain)
        
        # Create or update intake lines
        # Use search to avoid ordering issues with empty recordset
        existing_lines = self.env['cs.billing.intake.line'].search([('wizard_id', '=', self.id)])
        existing_intakes = existing_lines.mapped('intake_id')
        
        # Remove lines for intakes that are no longer in the list
        to_remove = existing_lines.filtered(lambda l: l.intake_id not in intakes)
        to_remove.unlink()
        
        # Add new lines for intakes not yet in the list
        for intake in intakes:
            if intake not in existing_intakes:
                self.env['cs.billing.intake.line'].create({
                    'wizard_id': self.id,
                    'intake_id': intake.id,
                    'select': True,
                })
        
        # Update existing lines (re-fetch to get new ones)
        all_lines = self.env['cs.billing.intake.line'].search([('wizard_id', '=', self.id)])
        for line in all_lines:
            line._compute_days_info()
            line._compute_amount_info()
    
    def action_preview_billing(self):
        """Preview billing without creating invoices"""
        self.create_invoices = False
        return self.action_run_billing()
    
    def action_run_billing(self):
        """Run the monthly billing process"""
        if self.date_from > self.date_to:
            raise UserError(_('From date cannot be after to date.'))
        
        # Load intakes if not loaded
        existing_lines = self.env['cs.billing.intake.line'].search([('wizard_id', '=', self.id)])
        if not existing_lines:
            self._load_intakes()
            # Re-fetch after loading
            existing_lines = self.env['cs.billing.intake.line'].search([('wizard_id', '=', self.id)])
        
        # Reset last_billed_date if requested (for intakes with no active invoices)
        if self.reset_billing_date:
            self._reset_billing_dates()
        
        # Get selected intakes (allow even if period_amount is 0, as minimum charges might apply)
        selected_lines = existing_lines.filtered(lambda l: l.select)
        
        if not selected_lines:
            raise UserError(_('Please select at least one intake to bill.'))
        
        # Recalculate period amounts for selected lines to ensure they're up to date
        for line in selected_lines:
            line._compute_amount_info()
        
        # Filter out lines with 0 amount after recalculation (but warn user)
        lines_with_amount = selected_lines.filtered(lambda l: l.period_amount > 0)
        if not lines_with_amount:
            # Check if any selected intakes have tariff rules
            intakes_with_rules = selected_lines.mapped('intake_id').filtered(
                lambda i: i.line_ids.filtered(lambda l: l.tariff_rule_id)
            )
            if not intakes_with_rules:
                raise UserError(_('Selected intakes do not have tariff rules assigned. Please assign tariff rules to intake lines before billing.'))
            else:
                raise UserError(_('Selected intakes have a period amount of 0.00. This may be because:\n'
                                '- The billing period is too short\n'
                                '- The intake has no quantity/weight/volume\n'
                                '- The tariff rule has no price set\n\n'
                                'Please check the intake details and tariff rules.'))
        
        selected_lines = lines_with_amount
        
        intakes = selected_lines.mapped('intake_id')
        
        print(f"\n=== MONTHLY BILLING DEBUG ===")
        print(f"Date Range: {self.date_from} to {self.date_to}")
        print(f"Bill Unbilled Only: {self.bill_unbilled_only}")
        print(f"Selected Intakes: {len(intakes)}")
        
        if not intakes:
            # Provide helpful error message
            all_active_intakes = self.env['cs.storage.intake'].search([
                ('company_id', '=', self.company_id.id),
                ('state', 'in', ['checked_in', 'partially_out']),
            ])
            
            if not all_active_intakes:
                raise UserError(_('No active intakes found. Only intakes in "Checked In" or "Partially Released" state can be billed.'))
            
            # Check if date range is the issue
            intakes_in_range = self.env['cs.storage.intake'].search([
                ('company_id', '=', self.company_id.id),
                ('state', 'in', ['checked_in', 'partially_out']),
                ('date_in', '>=', self.date_from),
                ('date_in', '<=', self.date_to),
            ])
            
            if not intakes_in_range:
                raise UserError(_(
                    'No billable intakes found for the selected date range (%s to %s).\n\n'
                    'Please check:\n'
                    '1. The date range includes intake check-in dates\n'
                    '2. Intakes are in "Checked In" or "Partially Released" state\n'
                    '3. If "Bill Unbilled Consignments Only" is checked, ensure intakes have not been billed yet'
                ) % (self.date_from, self.date_to))
            
            # Check if all intakes are already billed
            if self.bill_unbilled_only:
                unbilled_count = len([i for i in intakes_in_range if not i.last_billed_date or i.last_billed_date < self.date_from])
                if unbilled_count == 0:
                    raise UserError(_(
                        'No unbilled intakes found for the selected criteria.\n\n'
                        'All intakes in the date range have already been billed.\n'
                        'To bill them again, uncheck "Bill Unbilled Consignments Only" or adjust the date range.'
                    ))
            
            raise UserError(_('No billable intakes found for the selected criteria.'))
        
        for intake in intakes:
            print(f"Intake {intake.name}: Partner={intake.partner_id.name}, Total Amount={intake.total_amount}")
            for line in intake.line_ids:
                print(f"  Line {line.id}: Product={line.product_id.name}, Qty={line.qty_in}, Amount={line.amount_subtotal}")
        print(f"=== END MONTHLY BILLING DEBUG ===\n")
        
        # Group by partner for invoice creation
        # Calculate amount for billing period only (from last_billed_date or date_in to date_to)
        partner_data = {}
        for intake in intakes:
            # Calculate billing period
            billing_start = intake.last_billed_date or intake.date_in.date() if intake.date_in else fields.Date.today()
            billing_end = self.date_to
            
            # Skip if billing period is invalid
            if billing_start >= billing_end:
                continue
            
            # Calculate amount for this billing period only
            period_amount = self._calculate_period_amount(intake, billing_start, billing_end)
            
            print(f"  Intake {intake.name}: billing_start={billing_start}, billing_end={billing_end}, period_amount={period_amount}")
            
            if period_amount > 0:
                partner = intake.partner_id
                if partner not in partner_data:
                    partner_data[partner] = {
                        'intakes': [],
                        'total_amount': 0,
                    }
                partner_data[partner]['intakes'].append(intake)
                partner_data[partner]['total_amount'] += period_amount
        
        invoices_created = []
        total_amount = 0
        
        for partner, data in partner_data.items():
            if data['total_amount'] > 0:
                if self.create_invoices:
                    invoice = self._create_partner_invoice(partner, data['intakes'], data['total_amount'])
                    invoices_created.append(invoice)
                    # Update last_billed_date for intakes
                    for intake in data['intakes']:
                        intake.last_billed_date = self.date_to
                total_amount += data['total_amount']
        
        # Update results
        self.invoice_count = len(invoices_created)
        self.total_amount = total_amount
        
        if self.create_invoices:
            if invoices_created:
                return {
                    'type': 'ir.actions.act_window',
                    'name': _('Billing Results'),
                    'res_model': 'account.move',
                    'view_mode': 'tree,form',
                    'domain': [('id', 'in', [inv.id for inv in invoices_created])],
                }
            else:
                raise UserError(_('No invoices were created.'))
        else:
            # Preview mode - show summary
            return {
                'type': 'ir.actions.act_window',
                'name': _('Billing Preview'),
                'res_model': 'cs.storage.intake',
                'view_mode': 'tree,form',
                'domain': [('id', 'in', intakes.ids)],
                'context': {'group_by': 'partner_id'},
            }
    
    def _reset_billing_dates(self):
        """Reset last_billed_date for intakes that have no active invoices"""
        # Find intakes with last_billed_date but no related invoices
        intakes_to_reset = self.env['cs.storage.intake'].search([
            ('company_id', '=', self.company_id.id),
            ('state', 'in', ['checked_in', 'partially_out']),
            ('last_billed_date', '!=', False),
        ])
        
        reset_count = 0
        for intake in intakes_to_reset:
            # Check if there are any invoices related to this intake
            invoices = self.env['account.move'].search([
                ('ref', 'ilike', intake.name),
                ('move_type', '=', 'out_invoice'),
                ('state', '!=', 'cancel'),
            ])
            
            if not invoices:
                intake.last_billed_date = False
                reset_count += 1
        
        if reset_count > 0:
            # Log the reset
            print(f"Reset last_billed_date for {reset_count} intakes with no active invoices.")
    
    def _create_partner_invoice(self, partner, intakes, total_amount):
        """Create invoice for a partner with intake-wise lines"""
        invoice_vals = {
            'partner_id': partner.id,
            'move_type': 'out_invoice',
            'invoice_date': self.invoice_date,
            'ref': f'Cold Storage charges from {self.date_from} to {self.date_to}',
            'company_id': self.company_id.id,
            'currency_id': self.currency_id.id,
            'invoice_line_ids': [],
        }
        
        # Get default income account (will be used for all lines)
        default_account = self._get_income_account()
        
        # Create one invoice line per intake with all details
        for intake in intakes:
            # Calculate billing period for this intake
            billing_start = intake.last_billed_date or intake.date_in.date() if intake.date_in else fields.Date.today()
            billing_end = self.date_to
            
            # Calculate amount for this billing period
            intake_total = self._calculate_period_amount(intake, billing_start, billing_end)
            
            if intake_total <= 0:
                continue
            
            intake_lines = intake.line_ids.filtered(lambda l: l.tariff_rule_id)
            
            # Build description with all details
            items_list = []
            for line in intake_lines:
                item_desc = f"{line.product_id.name}"
                if line.lot_id:
                    item_desc += f" (Lot: {line.lot_id.name})"
                if line.qty_in:
                    item_desc += f" - Qty: {line.qty_in} {line.qty_uom_id.name if line.qty_uom_id else ''}"
                if line.weight:
                    item_desc += f", Weight: {line.weight} kg"
                if line.volume:
                    item_desc += f", Volume: {line.volume} m³"
                items_list.append(item_desc)
            
            # Format date in
            date_in_str = intake.date_in.strftime('%d-%m-%Y %H:%M') if intake.date_in else 'N/A'
            
            # Format billing period
            if isinstance(billing_start, str):
                billing_start = fields.Date.from_string(billing_start)
            if isinstance(billing_end, str):
                billing_end = fields.Date.from_string(billing_end)
            
            billing_period_str = f"{billing_start.strftime('%d-%m-%Y')} to {billing_end.strftime('%d-%m-%Y')}"
            
            # Calculate duration for this billing period
            period_duration = (billing_end - billing_start).days
            duration_str = f"{period_duration} day(s)"
            
            # Build comprehensive description
            description = f"Intake: {intake.name}\n"
            description += f"Date In: {date_in_str}\n"
            description += f"Billing Period: {billing_period_str}\n"
            description += f"Duration: {duration_str}\n"
            description += f"Location: {intake.location_id.name if intake.location_id else 'N/A'}\n"
            description += f"Items:\n"
            for item in items_list:
                description += f"  • {item}\n"
            
            # Get product from first line (or use a default product)
            product = intake_lines[0].tariff_rule_id.price_product_id if intake_lines[0].tariff_rule_id and intake_lines[0].tariff_rule_id.price_product_id else self._get_default_product()
            
            # Get account for this product
            account_id = product.property_account_income_id.id if product else default_account
            if not account_id:
                account_id = product.categ_id.property_account_income_categ_id.id if product and product.categ_id else default_account
            if not account_id:
                account_id = default_account
            
            invoice_line_vals = {
                'product_id': product.id if product else False,
                'name': description.strip(),
                'quantity': 1,
                'price_unit': intake_total,
                'account_id': account_id,
            }
            invoice_vals['invoice_line_ids'].append((0, 0, invoice_line_vals))
        
        return self.env['account.move'].create(invoice_vals)
    
    def _format_duration(self, intake_lines):
        """Format duration string from intake lines"""
        if not intake_lines:
            return 'N/A'
        
        # Calculate duration from intake date to today (or last billed date)
        intake = intake_lines[0].intake_id
        if not intake.date_in:
            return 'N/A'
        
        # Calculate duration from date_in to today
        today = fields.Datetime.now()
        date_in = intake.date_in
        
        # Calculate difference
        delta = today - date_in
        total_days = delta.total_seconds() / 86400  # Convert to days
        
        days = int(total_days)
        hours = int((total_days - days) * 24)
        minutes = int(((total_days - days) * 24 - hours) * 60)
        
        if days > 0:
            if hours > 0:
                return f"{days} day(s), {hours} hour(s)"
            else:
                return f"{days} day(s)"
        elif hours > 0:
            if minutes > 0:
                return f"{hours} hour(s), {minutes} minute(s)"
            else:
                return f"{hours} hour(s)"
        elif minutes > 0:
            return f"{minutes} minute(s)"
        else:
            return f"{total_days:.2f} day(s)"
    
    def _get_income_account(self):
        """Get default income account"""
        # Try to get account from product
        account = self.env['account.account'].search([
            ('account_type', '=', 'income'),
            ('company_id', '=', self.company_id.id)
        ], limit=1)
        
        if not account:
            account = self.env['account.account'].search([
                ('company_id', '=', self.company_id.id),
                ('account_type', 'in', ['income', 'income_other', 'income_other_income'])
            ], limit=1)
        
        if not account:
            account = self.env['account.account'].search([
                ('name', 'ilike', 'revenue'),
                ('company_id', '=', self.company_id.id)
            ], limit=1)
        
        if not account:
            account = self.env['account.account'].search([
                ('name', 'ilike', 'income'),
                ('company_id', '=', self.company_id.id)
            ], limit=1)
        
        if not account:
            if not self.env['ir.module.module'].search([('name', '=', 'account'), ('state', '=', 'installed')]):
                raise UserError(_('Accounting module is not installed. Please install the Accounting app first.'))
            raise UserError(_(
                'No income accounts found. Please:\n'
                '1. Go to Accounting > Configuration > Chart of Accounts\n'
                '2. Install a Chart of Accounts if not already installed\n'
            ))
        
        return account.id
    
    def _get_default_product(self):
        """Get default product for invoice lines"""
        # Try to find a cold storage service product
        product = self.env['product.product'].search([
            ('name', 'ilike', 'cold storage'),
            ('type', '=', 'service')
        ], limit=1)
        
        if not product:
            # Get default product category
            category = self.env['product.category'].search([], limit=1)
            # Create a default service product if none exists
            product = self.env['product.product'].create({
                'name': 'Cold Storage Service',
                'type': 'service',
                'categ_id': category.id if category else False,
            })
        
        return product
    
    def _calculate_period_amount(self, intake, date_from, date_to):
        """Calculate billing amount for a specific period"""
        total_amount = 0
        
        # Convert dates to datetime for calculation
        from datetime import datetime, time as dt_time
        if isinstance(date_from, str):
            date_from = fields.Date.from_string(date_from)
        if isinstance(date_to, str):
            date_to = fields.Date.from_string(date_to)
        
        # Get intake start datetime
        if not intake.date_in:
            return 0
        
        intake_start = intake.date_in
        
        # Billing period starts from the later of: date_from or intake.date_in
        # Billing period ends at date_to (end of day)
        period_start_date = max(date_from, intake_start.date())
        period_end_date = date_to
        
        # If period start is after period end, no billing
        if period_start_date > period_end_date:
            return 0
        
        # Convert to datetime for calculation
        # If period starts on intake date, use actual intake time; otherwise use start of day
        if period_start_date == intake_start.date():
            period_start = intake_start
        else:
            period_start = datetime.combine(period_start_date, dt_time.min)
        
        period_end = datetime.combine(period_end_date, dt_time.max)
        
        # Calculate duration in days for this period
        period_duration = (period_end - period_start).total_seconds() / 86400  # days
        
        if period_duration <= 0:
            return 0
        
        print(f"\n=== PERIOD AMOUNT CALCULATION DEBUG ===")
        print(f"Intake: {intake.name}")
        print(f"Period Start: {period_start}")
        print(f"Period End: {period_end}")
        print(f"Period Duration (days): {period_duration}")
        
        # Calculate amount for each line based on billing period
        for line in intake.line_ids:
            if not line.tariff_rule_id:
                print(f"  Line {line.id}: No tariff rule, skipping")
                continue
            
            # Get billing basis and unit
            basis = line.bill_basis or line.tariff_rule_id.basis
            price_unit = line.price_unit or line.tariff_rule_id.price_unit
            
            # Calculate units based on basis (same logic as tariff rule)
            if basis == 'day_weight':
                # Use weight if available, otherwise use quantity as fallback
                units = line.weight or line.qty_in or 0
            elif basis == 'day_volume':
                units = line.volume or 0
            elif basis == 'day_pallet':
                units = line.pallet_count or 0
            elif basis == 'flat':
                units = 1
            else:
                units = line.qty_in or 0
            
            print(f"  Line {line.id}: basis={basis}, units={units}, price_unit={price_unit}")
            
            # Apply minimum billable days from tariff rule
            min_bill_days = line.tariff_rule_id.min_bill_days or 1.0
            effective_duration = max(period_duration, min_bill_days)
            
            print(f"    period_duration={period_duration}, min_bill_days={min_bill_days}, effective_duration={effective_duration}")
            
            # Calculate amount for this period
            line_amount = units * price_unit * effective_duration
            print(f"    line_amount = {units} × {price_unit} × {effective_duration} = {line_amount}")
            total_amount += line_amount
        
        print(f"Total Period Amount: {total_amount}")
        print(f"=== END PERIOD AMOUNT CALCULATION DEBUG ===\n")
        
        return total_amount
    