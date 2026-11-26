# Tour Package Pricing and Itinerary Cost Engine

**Problem Statement:** PS-046  
**Team:** T017  
**Project:** Tour Package Pricing and Itinerary Cost Engine with Seasonality, Group Discounts and Child Policy

A Python command-line engine that prices multi-day tour packages from CSV master data and an ordered command file. It calculates supplier costs, customer selling prices, traveller-wise invoices, and quote change/cancellation records.

## Features

- Hotel cost calculation using the season applicable to each night
- Room allocation for adult groups and child accommodation policies
- Vehicle, guide, meal, activity, and child-minding cost calculations
- Group and early-bird discounts with a combined cap
- Markup and GST calculation with financial rounding
- Quote lifecycle commands: create quote, add/remove traveller, date shift, room change, cancellation, and report printing
- Quote versioning and change log
- CSV reports with traveller invoice reconciliation
- Automated tests for business rules and edge cases

## Requirements

- Python 3.10 or later
- No external Python packages are required for the standard project run/test workflow; the implementation uses Python standard-library modules.

## Project structure

```text
T017-PS046/
├── main.py
├── src/                  # pricing, costing, data, itinerary, room and quote logic
├── tests/                # automated unittest suite
├── data/                 # supplied CSV datasets and commands.txt
├── docs/
│   ├── PS046_Tour_Package_Pricing_Engine_Design_Document.pdf
│   ├── PROJECT_REPORT.md
│   ├── DECISION_LOG.md
│   └── DEMO_SCRIPT.md
├── outputs/               # generated report CSVs
└── README.md
```

## Run the project

Open PowerShell or a terminal in the repository root.

```powershell
python main.py
```

The program reads the input datasets and command stream from `data/` and generates the report CSV files. Review the generated files in `outputs/` and, where applicable, the project root:

- `cost_sheet.csv` — component-level cost breakdown
- `quote_summary.csv` — quote totals and pricing summary by version
- `traveller_invoice.csv` — traveller-wise invoice
- `change_log.csv` — quote changes, fees, and audit entries

## Run automated tests

From the repository root:

```powershell
python -m unittest tests.test_engine -v
```

## Input data

The input data files, their column definitions, command syntax, and supplied edge-case descriptions are documented in [`data/README.md`](data/README.md). The command file is [`data/commands.txt`](data/commands.txt); commands are processed in file order.

## Documentation

- [Project report](docs/PROJECT_REPORT.md)
- [Design document (PDF)](docs/PS046_Tour_Package_Pricing_Engine_Design_Document.pdf)
- [Decision log](docs/DECISION_LOG.md)
- [Demo script](docs/DEMO_SCRIPT.md)

## Demo video

**Demo video link:** Add the final 5-minute demonstration URL here after recording and uploading the video.

## Team

- Jeevitha R – 1AT24CD034
- Joy Princy S – 1AT24CD035
- Section: CSDS 'A'
- Team ID: T017
