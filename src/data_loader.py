
import csv
from pathlib import Path


# Project directory
BASE_DIR = Path(__file__).resolve().parent.parent

# Data directory
DATA_DIR = BASE_DIR / "data"


# Required CSV files and their columns
REQUIRED_COLUMNS = {
    "hotels.csv": [
        "hotel_id",
        "hotel_name",
        "city",
        "star_rating",
        "standard_twin_room_cost",
        "deluxe_twin_room_cost",
        "currency"
    ],

    "activities.csv": [
        "activity_id",
        "activity_name",
        "city",
        "cost_per_person",
        "currency",
        "min_age"
    ],

    "vehicles.csv": [
        "vehicle_type",
        "min_pax",
        "max_pax",
        "cost_per_day",
        "currency"
    ],

    "meals.csv": [
        "meal_id",
        "description",
        "adult_cost_per_day",
        "child_5_11_cost_per_day",
        "child_under_5_cost_per_day",
        "currency"
    ],

    "rate_parameters.csv": [
        "param",
        "value",
        "unit",
        "notes"
    ],

    "season_calendar.csv": [
        "from_date",
        "to_date",
        "season",
        "hotel_multiplier"
    ],

    "fx_rates.csv": [
        "rate_date",
        "currency",
        "inr_per_unit"
    ],

    "packages.csv": [
        "package_id",
        "package_name",
        "days",
        "nights",
        "region"
    ],

    "package_itinerary.csv": [
        "package_id",
        "day_no",
        "component_type",
        "component_id",
        "notes"
    ],

    "travellers.csv": [
        "traveller_id",
        "quote_id",
        "full_name",
        "gender",
        "date_of_birth",
        "parent_1_id",
        "parent_2_id",
        "group_leader",
        "on_initial_quote"
    ],

    "activity_optouts.csv": [
        "quote_id",
        "traveller_id",
        "activity_id",
        "reason"
    ]
}


class DataValidationError(Exception):
    """Raised when input data is missing or invalid."""


def load_csv(filename):
    """Load and validate one CSV file."""

    file_path = DATA_DIR / filename

    if not file_path.exists():
        raise DataValidationError(
            f"Missing required file: {filename}"
        )

    with open(file_path, "r", newline="", encoding="utf-8-sig") as file:
        reader = csv.DictReader(file)

        actual_columns = reader.fieldnames or []
        expected_columns = REQUIRED_COLUMNS[filename]

        missing_columns = [
            column for column in expected_columns
            if column not in actual_columns
        ]

        if missing_columns:
            raise DataValidationError(
                f"{filename} is missing columns: {missing_columns}"
            )

        records = []

        for row in reader:
            cleaned_row = {
                key: (value.strip() if value is not None else "")
                for key, value in row.items()
            }
            records.append(cleaned_row)

        return records


def load_all_data():
    """Load all master CSV files."""

    data = {}

    for filename in REQUIRED_COLUMNS:
        key = filename.replace(".csv", "")

        data[key] = load_csv(filename)

        print(
            f"Loaded {filename}: {len(data[key])} records"
        )

    return data


def load_commands():
    """Load commands while preserving their original line numbers."""

    command_file = DATA_DIR / "commands.txt"

    if not command_file.exists():
        raise DataValidationError(
            "Missing required file: commands.txt"
        )

    commands = []

    with open(command_file, "r", encoding="utf-8-sig") as file:
        for line_number, line in enumerate(file, start=1):

            line = line.strip()

            if not line or line.startswith("#"):
                continue

            commands.append({
                "line_no": line_number,
                "raw": line,
                "parts": line.split("|")
            })

    print(f"Loaded commands.txt: {len(commands)} commands")

    return commands


if __name__ == "__main__":

    try:
        print("\n--- LOADING PROJECT DATA ---\n")

        project_data = load_all_data()
        commands = load_commands()

        print("\nAll input files loaded successfully!")

        print("\nTotal CSV master records:",
              sum(len(records) for records in project_data.values()))

        print("Total commands:", len(commands))

    except DataValidationError as error:
        print(f"\nDATA ERROR: {error}")
