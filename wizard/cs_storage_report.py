# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError
from datetime import datetime, timedelta
import base64
import io
try:
    import xlsxwriter
except ImportError:
    xlsxwriter = None


class CsStorageReport(models.TransientModel):
    _name = 'cs.storage.report'
    _description = 'Cold Storage Report'

    report_type = fields.Selection([
        ('consignment_detail', 'Consignment Detail Report'),
        ('location_wise', 'Location-wise Consignment Report'),
        ('material_received', 'Material Received from Party Report'),
        ('storage_capacity', 'Storage Capacity & Utilization Report'),
    ], string='Report Type', required=True, default='consignment_detail')
    
    date_from = fields.Date(
        string='From Date',
        required=True,
        default=lambda self: fields.Date.today() - timedelta(days=30)
    )
    date_to = fields.Date(
        string='To Date',
        required=True,
        default=lambda self: fields.Date.today()
    )
    
    partner_ids = fields.Many2many(
        'res.partner',
        string='Customers',
        help='Leave empty to include all customers'
    )
    location_ids = fields.Many2many(
        'stock.location',
        string='Locations',
        domain=[('is_freezer', '=', True)],
        help='Leave empty to include all locations'
    )
    
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        default=lambda self: self.env.company,
        required=True
    )
    
    export_format = fields.Selection([
        ('pdf', 'PDF'),
        ('excel', 'Excel'),
    ], string='Export Format', default='pdf')
    
    def action_generate_report(self):
        """Generate the selected report"""
        self.ensure_one()
        
        if self.export_format == 'excel':
            return self._export_excel()
        else:
            return self._export_pdf()
    
    def _export_pdf(self):
        """Export report as PDF"""
        self.ensure_one()
        
        if self.report_type == 'consignment_detail':
            return self._generate_consignment_detail_pdf()
        elif self.report_type == 'location_wise':
            return self._generate_location_wise_pdf()
        elif self.report_type == 'material_received':
            return self._generate_material_received_pdf()
        elif self.report_type == 'storage_capacity':
            return self._generate_storage_capacity_pdf()
    
    def _export_excel(self):
        """Export report as Excel"""
        self.ensure_one()
        
        if not xlsxwriter:
            raise UserError(_('xlsxwriter library is not installed. Please install it: pip install xlsxwriter'))
        
        if self.report_type == 'consignment_detail':
            return self._generate_consignment_detail_excel()
        elif self.report_type == 'location_wise':
            return self._generate_location_wise_excel()
        elif self.report_type == 'material_received':
            return self._generate_material_received_excel()
        elif self.report_type == 'storage_capacity':
            return self._generate_storage_capacity_excel()
    
    def _generate_consignment_detail_report(self):
        """Generate consignment detail report with days, pricing, invoicing"""
        domain = [
            ('company_id', '=', self.company_id.id),
            ('date_in', '>=', self.date_from),
            ('date_in', '<=', self.date_to),
        ]
        
        if self.partner_ids:
            domain.append(('partner_id', 'in', self.partner_ids.ids))
        
        intakes = self.env['cs.storage.intake'].search(domain)
        
        return {
            'type': 'ir.actions.act_window',
            'name': _('Consignment Detail Report'),
            'res_model': 'cs.storage.intake',
            'view_mode': 'tree,form',
            'domain': domain,
            'context': {
                'search_default_group_partner': 1,
                'search_default_group_location': 1,
            },
        }
    
    def _generate_location_wise_report(self):
        """Generate location-wise consignment report"""
        domain = [
            ('company_id', '=', self.company_id.id),
            ('state', 'in', ['checked_in', 'partially_out']),
        ]
        
        if self.location_ids:
            domain.append(('location_id', 'in', self.location_ids.ids))
        
        if self.partner_ids:
            domain.append(('partner_id', 'in', self.partner_ids.ids))
        
        intakes = self.env['cs.storage.intake'].search(domain)
        
        return {
            'type': 'ir.actions.act_window',
            'name': _('Location-wise Consignment Report'),
            'res_model': 'cs.storage.intake',
            'view_mode': 'tree,form',
            'domain': domain,
            'context': {
                'search_default_group_location': 1,
                'search_default_group_partner': 1,
            },
        }
    
    def _generate_material_received_report(self):
        """Generate material received from party report"""
        domain = [
            ('company_id', '=', self.company_id.id),
            ('date_in', '>=', self.date_from),
            ('date_in', '<=', self.date_to),
        ]
        
        if self.partner_ids:
            domain.append(('partner_id', 'in', self.partner_ids.ids))
        
        if self.location_ids:
            domain.append(('location_id', 'in', self.location_ids.ids))
        
        intakes = self.env['cs.storage.intake'].search(domain)
        
        return {
            'type': 'ir.actions.act_window',
            'name': _('Material Received from Party Report'),
            'res_model': 'cs.storage.intake',
            'view_mode': 'tree,form',
            'domain': domain,
            'context': {
                'search_default_group_partner': 1,
                'search_default_group_date_in': 1,
            },
        }
    
    def _generate_consignment_detail_pdf(self):
        """Generate consignment detail PDF report"""
        domain = [
            ('company_id', '=', self.company_id.id),
            ('date_in', '>=', self.date_from),
            ('date_in', '<=', self.date_to),
        ]
        
        if self.partner_ids:
            domain.append(('partner_id', 'in', self.partner_ids.ids))
        
        intakes = self.env['cs.storage.intake'].search(domain)
        
        return self.env.ref('cs_cold_storage.action_report_consignment_detail_pdf').report_action(intakes)
    
    def _generate_location_wise_pdf(self):
        """Generate location-wise PDF report"""
        domain = [
            ('company_id', '=', self.company_id.id),
            ('state', 'in', ['checked_in', 'partially_out']),
        ]
        
        if self.location_ids:
            domain.append(('location_id', 'in', self.location_ids.ids))
        
        if self.partner_ids:
            domain.append(('partner_id', 'in', self.partner_ids.ids))
        
        intakes = self.env['cs.storage.intake'].search(domain)
        
        return self.env.ref('cs_cold_storage.action_report_location_wise_pdf').report_action(intakes)
    
    def _generate_material_received_pdf(self):
        """Generate material received PDF report"""
        domain = [
            ('company_id', '=', self.company_id.id),
            ('date_in', '>=', self.date_from),
            ('date_in', '<=', self.date_to),
        ]
        
        if self.partner_ids:
            domain.append(('partner_id', 'in', self.partner_ids.ids))
        
        if self.location_ids:
            domain.append(('location_id', 'in', self.location_ids.ids))
        
        intakes = self.env['cs.storage.intake'].search(domain)
        
        return self.env.ref('cs_cold_storage.action_report_material_received_pdf').report_action(intakes)
    
    def _generate_consignment_detail_excel(self):
        """Generate consignment detail Excel report"""
        domain = [
            ('company_id', '=', self.company_id.id),
            ('date_in', '>=', self.date_from),
            ('date_in', '<=', self.date_to),
        ]
        
        if self.partner_ids:
            domain.append(('partner_id', 'in', self.partner_ids.ids))
        
        intakes = self.env['cs.storage.intake'].search(domain)
        
        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})
        worksheet = workbook.add_worksheet('Consignment Detail Report')
        
        # Header format
        header_format = workbook.add_format({
            'bold': True,
            'bg_color': '#366092',
            'font_color': 'white',
            'align': 'center',
            'valign': 'vcenter',
            'border': 1
        })
        
        # Title format
        title_format = workbook.add_format({
            'bold': True,
            'font_size': 14,
            'align': 'center'
        })
        
        # Data format
        data_format = workbook.add_format({
            'border': 1,
            'align': 'left'
        })
        
        # Number format
        number_format = workbook.add_format({
            'border': 1,
            'num_format': '#,##0.00'
        })
        
        # Date format
        date_format = workbook.add_format({
            'border': 1,
            'num_format': 'dd/mm/yyyy'
        })
        
        # Write title
        worksheet.merge_range(0, 0, 0, 10, 'CONSIGNMENT DETAIL REPORT', title_format)
        worksheet.merge_range(1, 0, 1, 10, f'From: {self.date_from} To: {self.date_to}', title_format)
        worksheet.set_row(0, 20)
        worksheet.set_row(1, 20)
        
        # Headers
        headers = ['Intake No.', 'Date In', 'Customer', 'Location', 'Vehicle No.', 'Driver', 
                  'Product', 'Lot', 'Qty In', 'Qty Out', 'Weight (kg)', 'Volume', 
                  'Duration (Days)', 'Amount', 'Status']
        col = 0
        for header in headers:
            worksheet.write(3, col, header, header_format)
            col += 1
        
        # Data rows
        row = 4
        for intake in intakes:
            for line in intake.line_ids:
                worksheet.write(row, 0, intake.name, data_format)
                worksheet.write_datetime(row, 1, intake.date_in, date_format)
                worksheet.write(row, 2, intake.partner_id.name or '', data_format)
                worksheet.write(row, 3, intake.location_id.name or '', data_format)
                worksheet.write(row, 4, intake.vehicle_number or '', data_format)
                worksheet.write(row, 5, intake.driver_name or '', data_format)
                worksheet.write(row, 6, line.product_id.name or '', data_format)
                worksheet.write(row, 7, line.lot_id.name or '', data_format)
                worksheet.write(row, 8, line.qty_in, number_format)
                worksheet.write(row, 9, line.qty_out, number_format)
                worksheet.write(row, 10, line.weight or 0, number_format)
                worksheet.write(row, 11, line.volume or 0, number_format)
                worksheet.write(row, 12, line.duration_days or 0, number_format)
                worksheet.write(row, 13, line.amount_subtotal or 0, number_format)
                worksheet.write(row, 14, dict(intake._fields['state'].selection).get(intake.state, ''), data_format)
                row += 1
        
        # Set column widths
        worksheet.set_column(0, 0, 15)  # Intake No.
        worksheet.set_column(1, 1, 12)   # Date In
        worksheet.set_column(2, 2, 20)  # Customer
        worksheet.set_column(3, 3, 20)  # Location
        worksheet.set_column(4, 4, 15)  # Vehicle No.
        worksheet.set_column(5, 5, 15)  # Driver
        worksheet.set_column(6, 6, 20)  # Product
        worksheet.set_column(7, 7, 15)  # Lot
        worksheet.set_column(8, 11, 12)  # Qty, Weight, Volume
        worksheet.set_column(12, 12, 15) # Duration
        worksheet.set_column(13, 13, 15) # Amount
        worksheet.set_column(14, 14, 15) # Status
        
        workbook.close()
        output.seek(0)
        
        # Create attachment
        filename = f'Consignment_Detail_Report_{self.date_from}_{self.date_to}.xlsx'
        attachment = self.env['ir.attachment'].create({
            'name': filename,
            'type': 'binary',
            'datas': base64.b64encode(output.read()),
            'mimetype': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        })
        
        return {
            'type': 'ir.actions.act_url',
            'url': f'/web/content/{attachment.id}?download=true',
            'target': 'self',
        }
    
    def _generate_location_wise_excel(self):
        """Generate location-wise Excel report"""
        domain = [
            ('company_id', '=', self.company_id.id),
            ('state', 'in', ['checked_in', 'partially_out']),
        ]
        
        if self.location_ids:
            domain.append(('location_id', 'in', self.location_ids.ids))
        
        if self.partner_ids:
            domain.append(('partner_id', 'in', self.partner_ids.ids))
        
        intakes = self.env['cs.storage.intake'].search(domain)
        
        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})
        
        # Group by location
        locations = {}
        for intake in intakes:
            location = intake.location_id.name or 'No Location'
            if location not in locations:
                locations[location] = []
            locations[location].append(intake)
        
        # Create worksheet for each location
        for location_name, location_intakes in locations.items():
            worksheet = workbook.add_worksheet(location_name[:31])  # Excel sheet name limit
            
            header_format = workbook.add_format({
                'bold': True,
                'bg_color': '#366092',
                'font_color': 'white',
                'align': 'center',
                'border': 1
            })
            
            title_format = workbook.add_format({
                'bold': True,
                'font_size': 14,
                'align': 'center'
            })
            
            data_format = workbook.add_format({'border': 1, 'align': 'left'})
            number_format = workbook.add_format({'border': 1, 'num_format': '#,##0.00'})
            date_format = workbook.add_format({'border': 1, 'num_format': 'dd/mm/yyyy'})
            
            # Title
            worksheet.merge_range(0, 0, 0, 9, f'LOCATION: {location_name}', title_format)
            worksheet.set_row(0, 20)
            
            # Headers
            headers = ['Intake No.', 'Date In', 'Customer', 'Vehicle No.', 'Driver', 
                      'Product', 'Qty In', 'Qty Out', 'Weight (kg)', 'Amount']
            for col, header in enumerate(headers):
                worksheet.write(2, col, header, header_format)
            
            # Data
            row = 3
            for intake in location_intakes:
                for line in intake.line_ids:
                    worksheet.write(row, 0, intake.name, data_format)
                    worksheet.write_datetime(row, 1, intake.date_in, date_format)
                    worksheet.write(row, 2, intake.partner_id.name or '', data_format)
                    worksheet.write(row, 3, intake.vehicle_number or '', data_format)
                    worksheet.write(row, 4, intake.driver_name or '', data_format)
                    worksheet.write(row, 5, line.product_id.name or '', data_format)
                    worksheet.write(row, 6, line.qty_in, number_format)
                    worksheet.write(row, 7, line.qty_out, number_format)
                    worksheet.write(row, 8, line.weight or 0, number_format)
                    worksheet.write(row, 9, line.amount_subtotal or 0, number_format)
                    row += 1
            
            # Set column widths
            worksheet.set_column(0, 0, 15)
            worksheet.set_column(1, 1, 12)
            worksheet.set_column(2, 2, 20)
            worksheet.set_column(3, 4, 15)
            worksheet.set_column(5, 5, 20)
            worksheet.set_column(6, 9, 12)
        
        workbook.close()
        output.seek(0)
        
        from datetime import date
        filename = f'Location_wise_Report_{date.today()}.xlsx'
        attachment = self.env['ir.attachment'].create({
            'name': filename,
            'type': 'binary',
            'datas': base64.b64encode(output.read()),
            'mimetype': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        })
        
        return {
            'type': 'ir.actions.act_url',
            'url': f'/web/content/{attachment.id}?download=true',
            'target': 'self',
        }
    
    def _generate_material_received_excel(self):
        """Generate material received Excel report"""
        domain = [
            ('company_id', '=', self.company_id.id),
            ('date_in', '>=', self.date_from),
            ('date_in', '<=', self.date_to),
        ]
        
        if self.partner_ids:
            domain.append(('partner_id', 'in', self.partner_ids.ids))
        
        if self.location_ids:
            domain.append(('location_id', 'in', self.location_ids.ids))
        
        intakes = self.env['cs.storage.intake'].search(domain, order='date_in, partner_id')
        
        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})
        worksheet = workbook.add_worksheet('Material Received')
        
        header_format = workbook.add_format({
            'bold': True,
            'bg_color': '#366092',
            'font_color': 'white',
            'align': 'center',
            'border': 1
        })
        
        title_format = workbook.add_format({
            'bold': True,
            'font_size': 14,
            'align': 'center'
        })
        
        data_format = workbook.add_format({'border': 1, 'align': 'left'})
        number_format = workbook.add_format({'border': 1, 'num_format': '#,##0.00'})
        date_format = workbook.add_format({'border': 1, 'num_format': 'dd/mm/yyyy'})
        
        # Title
        worksheet.merge_range(0, 0, 0, 9, 'MATERIAL RECEIVED FROM PARTY REPORT', title_format)
        worksheet.merge_range(1, 0, 1, 9, f'From: {self.date_from} To: {self.date_to}', title_format)
        worksheet.set_row(0, 20)
        worksheet.set_row(1, 20)
        
        # Headers
        headers = ['Date', 'Intake No.', 'Party/Customer', 'Location', 'Vehicle No.', 'Driver',
                  'Product', 'Lot', 'Qty In', 'Weight (kg)']
        for col, header in enumerate(headers):
            worksheet.write(3, col, header, header_format)
        
        # Data
        row = 4
        for intake in intakes:
            for line in intake.line_ids:
                worksheet.write_datetime(row, 0, intake.date_in, date_format)
                worksheet.write(row, 1, intake.name, data_format)
                worksheet.write(row, 2, intake.partner_id.name or '', data_format)
                worksheet.write(row, 3, intake.location_id.name or '', data_format)
                worksheet.write(row, 4, intake.vehicle_number or '', data_format)
                worksheet.write(row, 5, intake.driver_name or '', data_format)
                worksheet.write(row, 6, line.product_id.name or '', data_format)
                worksheet.write(row, 7, line.lot_id.name or '', data_format)
                worksheet.write(row, 8, line.qty_in, number_format)
                worksheet.write(row, 9, line.weight or 0, number_format)
                row += 1
        
        # Set column widths
        worksheet.set_column(0, 0, 12)
        worksheet.set_column(1, 1, 15)
        worksheet.set_column(2, 2, 25)
        worksheet.set_column(3, 3, 20)
        worksheet.set_column(4, 5, 15)
        worksheet.set_column(6, 6, 20)
        worksheet.set_column(7, 7, 15)
        worksheet.set_column(8, 9, 12)
        
        workbook.close()
        output.seek(0)
        
        filename = f'Material_Received_Report_{self.date_from}_{self.date_to}.xlsx'
        attachment = self.env['ir.attachment'].create({
            'name': filename,
            'type': 'binary',
            'datas': base64.b64encode(output.read()),
            'mimetype': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        })
        
        return {
            'type': 'ir.actions.act_url',
            'url': f'/web/content/{attachment.id}?download=true',
            'target': 'self',
        }
    
    def _generate_storage_capacity_pdf(self):
        """Generate storage capacity PDF report"""
        domain = [
            ('is_freezer', '=', True),
        ]
        
        if self.location_ids:
            domain.append(('id', 'in', self.location_ids.ids))
        
        locations = self.env['stock.location'].search(domain)
        
        return self.env.ref('cs_cold_storage.action_report_storage_capacity_pdf').report_action(locations)
    
    def _generate_storage_capacity_excel(self):
        """Generate storage capacity Excel report"""
        domain = [
            ('is_freezer', '=', True),
        ]
        
        if self.location_ids:
            domain.append(('id', 'in', self.location_ids.ids))
        
        locations = self.env['stock.location'].search(domain)
        
        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})
        worksheet = workbook.add_worksheet('Storage Capacity Report')
        
        header_format = workbook.add_format({
            'bold': True,
            'bg_color': '#366092',
            'font_color': 'white',
            'align': 'center',
            'border': 1
        })
        
        title_format = workbook.add_format({
            'bold': True,
            'font_size': 14,
            'align': 'center'
        })
        
        data_format = workbook.add_format({'border': 1, 'align': 'left'})
        number_format = workbook.add_format({'border': 1, 'num_format': '#,##0.00'})
        percent_format = workbook.add_format({'border': 1, 'num_format': '0.00%'})
        
        # Title
        worksheet.merge_range(0, 0, 0, 9, 'STORAGE CAPACITY & UTILIZATION REPORT', title_format)
        worksheet.set_row(0, 20)
        
        # Headers
        headers = ['Location', 'Max Volume (m³)', 'Current Volume (m³)', 'Available Volume (m³)', 
                  'Volume Utilization %', 'Max Weight (kg)', 'Current Weight (kg)', 
                  'Available Weight (kg)', 'Weight Utilization %', 'Active Intakes']
        for col, header in enumerate(headers):
            worksheet.write(2, col, header, header_format)
        
        # Data
        row = 3
        for location in locations:
            available_volume = (location.max_volume - location.current_volume) if location.max_volume else 0
            available_weight = (location.max_weight - location.current_weight) if location.max_weight else 0
            volume_util = (location.volume_utilization / 100) if location.volume_utilization else 0
            weight_util = (location.weight_utilization / 100) if location.weight_utilization else 0
            
            worksheet.write(row, 0, location.name or '', data_format)
            worksheet.write(row, 1, location.max_volume or 0, number_format)
            worksheet.write(row, 2, location.current_volume or 0, number_format)
            worksheet.write(row, 3, available_volume, number_format)
            worksheet.write(row, 4, volume_util, percent_format)
            worksheet.write(row, 5, location.max_weight or 0, number_format)
            worksheet.write(row, 6, location.current_weight or 0, number_format)
            worksheet.write(row, 7, available_weight, number_format)
            worksheet.write(row, 8, weight_util, percent_format)
            worksheet.write(row, 9, location.intake_count or 0, number_format)
            row += 1
        
        # Set column widths
        worksheet.set_column(0, 0, 25)  # Location
        worksheet.set_column(1, 9, 18)  # All other columns
        
        workbook.close()
        output.seek(0)
        
        from datetime import date
        filename = f'Storage_Capacity_Report_{date.today()}.xlsx'
        attachment = self.env['ir.attachment'].create({
            'name': filename,
            'type': 'binary',
            'datas': base64.b64encode(output.read()),
            'mimetype': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        })
        
        return {
            'type': 'ir.actions.act_url',
            'url': f'/web/content/{attachment.id}?download=true',
            'target': 'self',
        }

