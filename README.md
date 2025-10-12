# Cold Storage Services Module for Odoo 18

A comprehensive cold storage and freezer management system for Odoo 18 that provides complete tracking, billing, and management capabilities for cold storage operations.

## Features

### Core Functionality
- **Intake Management**: Track goods received for cold storage with detailed item lines
- **Release Management**: Handle partial and full releases with pro-rata billing
- **Duration-based Billing**: Flexible pricing based on weight, volume, or flat rates
- **Temperature Monitoring**: Track and log freezer temperatures with compliance alerts
- **Contract Management**: Support for recurring customers with automated billing cycles
- **Inventory Integration**: Seamless integration with Odoo's stock management

### Key Models

#### Storage Intake (`cs.storage.intake`)
- Customer goods check-in with timestamps
- Freezer location assignment
- Target temperature tracking
- Status workflow: Draft → Checked In → Partially Out → Closed → Cancelled

#### Storage Intake Lines (`cs.storage.intake.line`)
- Individual product lines with quantities
- Weight, volume, and pallet count tracking
- Lot/batch number support for perishables
- Automatic tariff rule matching
- Duration and amount calculations

#### Stock Release (`cs.stock.release`)
- Goods release with validation
- Partial release support
- Automatic stock move creation
- Invoice generation

#### Tariff Rules (`cs.tariff.rule`)
- Flexible pricing models:
  - Per kg per day
  - Per volume per day
  - Per pallet per day
  - Flat rate per day
- Product and temperature filters
- Rounding policies (ceiling, half-up, exact hours, 2-hour steps)
- Minimum billing days

#### Temperature Logs (`cs.temperature.log`)
- Temperature monitoring and logging
- Compliance status tracking
- Sensor integration support
- Historical trend analysis

#### Storage Contracts (`cs.storage.contract`)
- Recurring customer management
- Pre-paid and post-paid billing models
- Automated monthly billing cycles
- Credit limit controls

### Advanced Features

#### Billing & Invoicing
- Pro-rata calculations for partial releases
- Multiple rounding policies
- Tax integration
- Automated invoice generation
- Monthly billing cycles

#### Reporting & Analytics
- Aging in storage reports
- Revenue analysis by customer/product/month
- Freezer utilization tracking
- Temperature compliance monitoring
- Wastage and expiry summaries

#### Automation
- Daily duration refresh for open intakes
- Overdue release notifications
- Monthly billing automation
- Temperature compliance alerts

### Security & Access Control
- **Cold Storage User**: Create intakes/releases, read tariffs
- **Cold Storage Manager**: Approve/cancel, edit tariffs, run billing
- **Cold Storage Accountant**: Validate invoices
- **Cold Storage Warehouse**: Execute stock pickings

### Integration Points
- **Inventory**: Stock moves for goods in/out
- **Accounting**: Invoice generation and tax handling
- **Partners**: Customer management
- **Products**: Service product for storage charges
- **Analytic**: Optional analytic account tracking

## Installation

1. Copy the module to your Odoo addons directory
2. Update the app list in Odoo
3. Install the "Cold Storage Services" module
4. Configure freezer locations in Inventory > Locations
5. Set up tariff rules in Cold Storage > Configuration > Tariff Rules

## Configuration

### 1. Freezer Locations
- Mark locations as freezers (`is_freezer = True`)
- Set temperature ranges and capacity limits
- Monitor utilization rates

### 2. Tariff Rules
- Create pricing rules based on your business model
- Set up product and temperature filters
- Configure rounding policies

### 3. Service Products
- Ensure storage service products are configured
- Set up proper income accounts and taxes

### 4. User Groups
- Assign users to appropriate security groups
- Configure access rights as needed

## Usage

### Creating an Intake
1. Go to Cold Storage > Intakes
2. Create new intake with customer and location
3. Add item lines with products, quantities, and physical properties
4. Check in the intake to create stock moves

### Processing a Release
1. Go to Cold Storage > Releases
2. Select intake and add release lines
3. Set quantities to release
4. Validate to create stock moves and update billing

### Monthly Billing
1. Go to Cold Storage > Billing > Monthly Billing
2. Set date range and filters
3. Preview or run billing to generate invoices

### Temperature Monitoring
1. Go to Cold Storage > Temperature Logs
2. Record temperature readings
3. Monitor compliance status
4. View trends and alerts

## Technical Details

### Dependencies
- `base`
- `stock`
- `account`
- `product`
- `sale`
- `purchase`
- `analytic`
- `mail`

### Key Methods
- `_compute_duration()`: Calculate storage duration
- `_compute_amount()`: Calculate storage charges
- `action_check_in()`: Process intake check-in
- `action_release()`: Process goods release
- `match_tariff_rule()`: Find applicable pricing rules

### Cron Jobs
- Daily duration refresh
- Overdue release notifications
- Monthly billing automation

## Support

For support and customization requests, please contact your Odoo implementation partner.

## License

LGPL-3
# Cold-Storage
