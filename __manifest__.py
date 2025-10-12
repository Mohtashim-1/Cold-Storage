# -*- coding: utf-8 -*-
{
    'name': 'Cold Storage Services',
    'version': '17.0.1.0.0',
    'category': 'Inventory/Inventory',
    'summary': 'Cold Storage and Freezer Management System',
    'description': """
        Cold Storage Services Module
        ===========================

        This module provides comprehensive cold storage and freezer management capabilities:

        * Intake and release tracking for cold storage goods
        * Duration-based billing with flexible tariff rules
        * Temperature monitoring and logging
        * Inventory integration with stock moves
        * Automated invoicing and billing cycles
        * Partial release support with pro-rata billing
        * Contract management for recurring customers
        * Comprehensive reporting and analytics

        Key Features:
        - Track goods in/out with timestamps and duration
        - Flexible pricing based on weight, volume, or flat rates
        - Support for partial releases and wastage tracking
        - Temperature compliance monitoring
        - Automated monthly billing cycles
        - Integration with Odoo Inventory and Accounting
        - Multi-company support
        - Advanced reporting and KPIs
    """,
    'author': 'Mohtashim Shoaib',
    'depends': [
        'base',
        'stock',
        'account',
        'product',
        'sale',
        'purchase',
        'analytic',
        'mail',
    ],
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'data/sequence_data.xml',
        'data/product_data.xml',
        'data/ir_cron_data.xml',
        'views/cs_tariff_rule_views.xml',
        'views/cs_storage_intake_views.xml',
        'views/cs_stock_release_views.xml',
        'views/cs_temperature_log_views.xml',
        'views/cs_storage_contract_views.xml',
        'views/stock_location_views.xml',
        'views/cs_wizard_views.xml',
        'views/menu_views.xml',
        'reports/cs_storage_reports.xml',
        'reports/cs_storage_templates.xml',
    ],
    'demo': [
        'demo/demo_data.xml',
    ],
    'installable': True,
    'application': True,
    'auto_install': False,
    'license': 'LGPL-3',
    'icon': '/cs_cold_storage/static/description/icon.png',
}
