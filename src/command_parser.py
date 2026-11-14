
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent
COMMAND_FILE = BASE_DIR / "data" / "commands.txt"


# Expected number of arguments after the command name
COMMAND_ARGUMENTS = {
    "QUOTE": 6,
    "ADD_TRAVELLER": 3,
    "REMOVE_TRAVELLER": 3,
    "DATE_SHIFT": 3,
    "ROOM_CHANGE": 3,
    "CANCEL": 2,
    "PRINT_COST_SHEET": 1,
    "PRINT_INVOICE": 1
}


@dataclass
class Command:
    line_no: int
    name: str
    args: list
    raw: str


class CommandParseError(Exception):
    """Raised when a command has invalid syntax or arguments."""


def validate_date(value, line_no, field_name):
    """Validate dates using YYYY-MM-DD format."""

    try:
        datetime.strptime(value, "%Y-%m-%d")
    except ValueError:
        raise CommandParseError(
            f"Line {line_no}: Invalid {field_name}: {value}"
        )


def parse_command_line(line, line_no):
    """Parse and validate one command line."""

    line = line.strip()

    # Ignore blank lines and comments
    if not line or line.startswith("#"):
        return None

    parts = [part.strip() for part in line.split("|")]

    command_name = parts[0].upper()
    args = parts[1:]

    if command_name not in COMMAND_ARGUMENTS:
        raise CommandParseError(
            f"Line {line_no}: Unknown command '{command_name}'"
        )

    expected_count = COMMAND_ARGUMENTS[command_name]

    if len(args) != expected_count:
        raise CommandParseError(
            f"Line {line_no}: {command_name} expects "
            f"{expected_count} arguments, received {len(args)}"
        )

    if any(not arg for arg in args):
        raise CommandParseError(
            f"Line {line_no}: Empty required argument in {command_name}"
        )

    # Command-specific validation
    if command_name == "QUOTE":
        quote_id, package_id, departure, quote_date, room, odd_option = args

        validate_date(departure, line_no, "departure date")
        validate_date(quote_date, line_no, "quote date")

        if room not in ("STANDARD", "DELUXE"):
            raise CommandParseError(
                f"Line {line_no}: Invalid room preference '{room}'"
            )

        if odd_option not in ("SINGLE", "TRIPLE"):
            raise CommandParseError(
                f"Line {line_no}: Invalid odd adult option '{odd_option}'"
            )

    elif command_name in ("ADD_TRAVELLER", "REMOVE_TRAVELLER"):
        validate_date(args[2], line_no, "change date")

    elif command_name == "DATE_SHIFT":
        validate_date(args[1], line_no, "new departure date")
        validate_date(args[2], line_no, "change date")

    elif command_name == "ROOM_CHANGE":
        if args[1] not in ("STANDARD", "DELUXE"):
            raise CommandParseError(
                f"Line {line_no}: Invalid room preference '{args[1]}'"
            )

        validate_date(args[2], line_no, "change date")

    elif command_name == "CANCEL":
        validate_date(args[1], line_no, "cancellation date")

    return Command(
        line_no=line_no,
        name=command_name,
        args=args,
        raw=line
    )


def load_and_parse_commands():
    """Read and parse the complete command file in original order."""

    if not COMMAND_FILE.exists():
        raise FileNotFoundError(
            f"Command file not found: {COMMAND_FILE}"
        )

    commands = []

    with open(COMMAND_FILE, "r", encoding="utf-8-sig") as file:

        for line_no, line in enumerate(file, start=1):

            command = parse_command_line(line, line_no)

            if command is not None:
                commands.append(command)

    return commands


def display_commands(commands):
    """Display parsed commands."""

    for command in commands:
        print(f"\nLine number : {command.line_no}")
        print(f"Command     : {command.name}")
        print(f"Arguments   : {command.args}")


if __name__ == "__main__":

    try:
        print("\n--- COMMAND PARSER ---\n")

        commands = load_and_parse_commands()

        print(f"Successfully parsed {len(commands)} commands.")

        print("\nFirst 5 parsed commands:")

        display_commands(commands[:5])

        print("\nCommand parsing completed successfully!")

    except (CommandParseError, FileNotFoundError) as error:
        print(f"\nCOMMAND ERROR: {error}")
