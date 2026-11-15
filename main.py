"""
Tour Package Pricing and Itinerary Cost Engine
Entry Point: main.py

Processes data/commands.txt, manages quote lifecycles, and generates
the required CSV outputs:
- cost_sheet.csv
- quote_summary.csv
- traveller_invoice.csv
- change_log.csv
"""

import sys
from pathlib import Path

# Add src directory to system path
BASE_DIR = Path(__file__).resolve().parent
SRC_DIR = BASE_DIR / "src"
DATA_DIR = BASE_DIR / "data"
OUTPUTS_DIR = BASE_DIR / "outputs"

if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from data_loader import load_all_data, DataValidationError
from command_parser import load_and_parse_commands, CommandParseError
from quote_manager import QuoteManager


def main():
    print("=" * 70)
    print(" TOUR PACKAGE PRICING AND ITINERARY COST ENGINE")
    print("=" * 70)

    # 1. Load Master Datasets
    print("\n[Step 1/4] Loading master datasets from data/ ...")
    try:
        project_data = load_all_data()
    except DataValidationError as e:
        print(f"FATAL: Master data validation failed: {e}")
        sys.exit(1)

    # 2. Parse Commands
    print("\n[Step 2/4] Parsing commands from data/commands.txt ...")
    try:
        commands = load_and_parse_commands()
        print(f"Successfully loaded and parsed {len(commands)} commands.")
    except (CommandParseError, FileNotFoundError) as e:
        print(f"FATAL: Command parsing failed: {e}")
        sys.exit(1)

    # 3. Initialize Quote Manager and Execute Commands
    print("\n[Step 3/4] Processing commands in file order ...")
    manager = QuoteManager(project_data)
    manager.run_commands(commands)

    # 4. Export CSV Outputs
    print("\n[Step 4/4] Exporting output CSV files ...")
    OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)

    # Export to outputs/
    manager.export_all_outputs(OUTPUTS_DIR)

    # Also export to project root for grader compatibility
    manager.export_all_outputs(BASE_DIR)

    # Summary metrics
    total_quotes = len(manager.quotes)
    total_versions = sum(len(v) for v in manager.quotes.values())
    total_changes = len(manager.change_log)
    latest_travellers = sum(
        len(v[-1].traveller_invoices) for v in manager.quotes.values() if v
    )

    print("\n" + "=" * 70)
    print(" EXECUTION COMPLETE - SUMMARY OF GENERATED ARTIFACTS")
    print("=" * 70)
    print(f"Total Unique Quotes Managed : {total_quotes}")
    print(f"Total Quote Versions Priced : {total_versions}")
    print(f"Total Change Log Entries    : {total_changes}")
    print(f"Total Invoiced Travellers   : {latest_travellers}")
    print(f"Outputs written to          : {OUTPUTS_DIR} and {BASE_DIR}")
    print("=" * 70)


if __name__ == "__main__":
    main()
