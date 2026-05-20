# Profiler Validation

- Rows validated: 6858999
- Columns validated: 398
- PK precision: 1.0
- False PK count: 0
- Audit leakage: 0
- Temporal leakage: 0
- Float pollution count: 0
- UNKNOWN count: 128
- FK fields removed: True
- Relationship imports removed: True
- Output schema valid: True
- Profiler independent: True

## Sample Checks
- Sales_Customers.customerid: {"physical_type": "integer", "pk_candidate": false, "pk_score": 0.6991, "profile_hints": {"is_identifier": true, "is_temporal": false, "is_audit": false, "is_measure": false, "is_dimension": false, "is_text": false}}
- sales_invoices.invoiceid: {"physical_type": "integer", "pk_candidate": false, "pk_score": 0.2, "profile_hints": {"is_identifier": true, "is_temporal": false, "is_audit": false, "is_measure": false, "is_dimension": false, "is_text": false}}
- warehouse_colors.colorid: {"physical_type": "integer", "pk_candidate": true, "pk_score": 0.89, "profile_hints": {"is_identifier": true, "is_temporal": false, "is_audit": false, "is_measure": false, "is_dimension": false, "is_text": false}}
- Application_Cities.lasteditedby: {"physical_type": "integer", "pk_candidate": false, "pk_score": 0.0, "profile_hints": {"is_identifier": false, "is_temporal": false, "is_audit": true, "is_measure": false, "is_dimension": false, "is_text": false}}