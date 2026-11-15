
from datetime import date
from decimal import Decimal
from pathlib import Path


class CostEngineError(Exception):
    """Raised when a cost calculation cannot be completed."""


def money(value):
    """Convert a value safely into Decimal."""
    return Decimal(str(value))


def parse_date(value):
    """Convert a date string into a date object."""
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


def age_on(date_of_birth, reference_date):
    """Calculate completed age on a particular date."""

    dob = parse_date(date_of_birth)
    reference_date = parse_date(reference_date)

    return (
        reference_date.year
        - dob.year
        - (
            (reference_date.month, reference_date.day)
            < (dob.month, dob.day)
        )
    )


class CostEngine:
    """Handles the foundational component cost calculations."""

    def __init__(self, data):

        self.data = data

        # Create lookup dictionaries for faster access.
        self.hotels = {
            row["hotel_id"]: row
            for row in data["hotels"]
        }

        self.activities = {
            row["activity_id"]: row
            for row in data["activities"]
        }

        self.vehicles = data["vehicles"]

        self.meals = {
            row["meal_id"]: row
            for row in data["meals"]
        }

        self.parameters = {
            row["param"]: money(row["value"])
            for row in data["rate_parameters"]
        }

        self.seasons = data["season_calendar"]

        self.fx_rates = {
            (row["rate_date"], row["currency"]):
                money(row["inr_per_unit"])
            for row in data["fx_rates"]
        }

    # --------------------------------------------------
    # 1. BUSINESS PARAMETERS
    # --------------------------------------------------

    def get_parameter(self, parameter_name):

        if parameter_name not in self.parameters:
            raise CostEngineError(
                f"Missing rate parameter: {parameter_name}"
            )

        return self.parameters[parameter_name]

    # --------------------------------------------------
    # 2. AGE CALCULATION
    # --------------------------------------------------

    def get_age(self, traveller, reference_date):

        return age_on(
            traveller["date_of_birth"],
            reference_date
        )

    # --------------------------------------------------
    # 3. SEASON CALCULATION
    # --------------------------------------------------

    def get_season(self, night_date):

        night_date = parse_date(night_date)

        for season in self.seasons:

            start = parse_date(season["from_date"])
            end = parse_date(season["to_date"])

            if start <= night_date <= end:

                return {
                    "season": season["season"],
                    "multiplier": money(
                        season["hotel_multiplier"]
                    )
                }

        raise CostEngineError(
            f"No season found for date {night_date}"
        )

    # --------------------------------------------------
    # 4. FOREIGN CURRENCY CONVERSION
    # --------------------------------------------------

    def get_exchange_rate(self, currency, quote_date):

        currency = currency.upper()
        quote_date = parse_date(quote_date)

        if currency == "INR":
            return Decimal("1")

        key = (quote_date.isoformat(), currency)

        if key not in self.fx_rates:
            raise CostEngineError(
                f"No {currency} exchange rate found "
                f"for quote date {quote_date}"
            )

        base_rate = self.fx_rates[key]

        buffer_pct = self.get_parameter(
            "FX_BUFFER_PCT"
        )

        buffered_rate = base_rate * (
            Decimal("1") + buffer_pct / Decimal("100")
        )

        return buffered_rate

    def convert_to_inr(self, amount, currency, quote_date):

        amount = money(amount)

        exchange_rate = self.get_exchange_rate(
            currency,
            quote_date
        )

        return amount * exchange_rate

    # --------------------------------------------------
    # 5. HOTEL COST
    # --------------------------------------------------

    def calculate_hotel_night(
        self,
        hotel_id,
        room_preference,
        night_date,
        quote_date
    ):

        if hotel_id not in self.hotels:
            raise CostEngineError(
                f"Unknown hotel: {hotel_id}"
            )

        if room_preference not in ("STANDARD", "DELUXE"):
            raise CostEngineError(
                f"Invalid room preference: {room_preference}"
            )

        hotel = self.hotels[hotel_id]

        column = (
            "standard_twin_room_cost"
            if room_preference == "STANDARD"
            else "deluxe_twin_room_cost"
        )

        base_cost = self.convert_to_inr(
            hotel[column],
            hotel["currency"],
            quote_date
        )

        season_details = self.get_season(night_date)

        multiplier = season_details["multiplier"]

        final_room_cost = base_cost * multiplier

        return {
            "hotel_id": hotel_id,
            "night_date": parse_date(night_date).isoformat(),
            "season": season_details["season"],
            "multiplier": multiplier,
            "unit_cost_inr": base_cost,
            "room_cost_inr": final_room_cost
        }

    # --------------------------------------------------
    # 6. VEHICLE COST
    # --------------------------------------------------

    def select_vehicle(self, seated_pax):

        seated_pax = int(seated_pax)

        for vehicle in self.vehicles:

            minimum = int(vehicle["min_pax"])
            maximum = int(vehicle["max_pax"])

            if minimum <= seated_pax <= maximum:
                return vehicle

        raise CostEngineError(
            f"No vehicle available for {seated_pax} passengers"
        )

    def calculate_vehicle_cost(self, seated_pax):

        vehicle = self.select_vehicle(seated_pax)

        total_cost = money(vehicle["cost_per_day"])

        cost_per_person = (
            total_cost / Decimal(seated_pax)
        )

        return {
            "vehicle_type": vehicle["vehicle_type"],
            "seated_pax": seated_pax,
            "total_cost_inr": total_cost,
            "cost_per_seated_person": cost_per_person
        }

    def count_seated_travellers(self, travellers, travel_date):

        count = 0

        for traveller in travellers:

            age = self.get_age(traveller, travel_date)

            # Children under five are excluded from vehicle count.
            if age >= 5:
                count += 1

        return count

    # --------------------------------------------------
    # 7. GUIDE COST
    # --------------------------------------------------

    def calculate_guide_cost(self, paying_travellers):

        if paying_travellers <= 0:
            raise CostEngineError(
                "Paying traveller count must be positive"
            )

        if paying_travellers <= 8:

            total_cost = self.get_parameter(
                "GUIDE_DAY_UPTO_8"
            )

        else:

            total_cost = self.get_parameter(
                "GUIDE_DAY_ABOVE_8"
            )

        return {
            "total_cost_inr": total_cost,
            "paying_travellers": paying_travellers,
            "cost_per_paying_traveller": (
                total_cost / Decimal(paying_travellers)
            )
        }

    # --------------------------------------------------
    # 8. ACTIVITY COST
    # --------------------------------------------------

    def calculate_activity_cost(
        self,
        activity_id,
        traveller,
        activity_date,
        quote_date
    ):

        if activity_id not in self.activities:
            raise CostEngineError(
                f"Unknown activity: {activity_id}"
            )

        activity = self.activities[activity_id]

        age = self.get_age(traveller, activity_date)

        minimum_age = int(activity["min_age"])

        if age < minimum_age:

            return {
                "activity_id": activity_id,
                "eligible": False,
                "age": age,
                "cost_inr": Decimal("0")
            }

        cost = self.convert_to_inr(
            activity["cost_per_person"],
            activity["currency"],
            quote_date
        )

        return {
            "activity_id": activity_id,
            "eligible": True,
            "age": age,
            "cost_inr": cost
        }

    # --------------------------------------------------
    # 9. CHILD-MINDING COST
    # --------------------------------------------------

    def calculate_child_minding_cost(
        self,
        child_skipped,
        both_parents_participating
    ):

        if child_skipped and both_parents_participating:

            return self.get_parameter("CHILD_MINDING")

        return Decimal("0")

    # --------------------------------------------------
    # 10. MEAL COST
    # --------------------------------------------------

    def calculate_meal_cost(
        self,
        meal_id,
        traveller,
        meal_date,
        quote_date
    ):

        if meal_id not in self.meals:
            raise CostEngineError(
                f"Unknown meal plan: {meal_id}"
            )

        meal = self.meals[meal_id]

        age = self.get_age(traveller, meal_date)

        if age < 5:
            column = "child_under_5_cost_per_day"

        elif age < 12:
            column = "child_5_11_cost_per_day"

        else:
            column = "adult_cost_per_day"

        cost = self.convert_to_inr(
            meal[column],
            meal["currency"],
            quote_date
        )

        return {
            "meal_id": meal_id,
            "age": age,
            "cost_inr": cost
        }


# ------------------------------------------------------
# TEST THE FOUNDATIONAL COST ENGINE
# ------------------------------------------------------

if __name__ == "__main__":

    from data_loader import load_all_data

    try:

        print("\n--- COMPONENT COST ENGINE ---\n")

        data = load_all_data()

        engine = CostEngine(data)

        # Test 1: Seasonal hotel pricing
        hotel_result = engine.calculate_hotel_night(
            hotel_id="HTL-01",
            room_preference="STANDARD",
            night_date="2026-12-15",
            quote_date="2026-11-15"
        )

        print("\nHOTEL TEST:")
        print(hotel_result)

        # Test 2: Vehicle sizing
        vehicle_result = engine.calculate_vehicle_cost(3)

        print("\nVEHICLE TEST:")
        print(vehicle_result)

        # Test 3: Guide pricing
        guide_result = engine.calculate_guide_cost(9)

        print("\nGUIDE TEST:")
        print(guide_result)

        # Test 4: Age calculation
        age = age_on(
            "2014-11-09",
            "2026-11-09"
        )

        print("\nAGE TEST:")
        print("Age:", age)

        # Test 5: Currency conversion
        exchange_rate = engine.get_exchange_rate(
            "USD",
            "2026-11-28"
        )

        print("\nUSD EXCHANGE RATE TEST:")
        print("Buffered rate:", exchange_rate)

        # Test 6: Hotel seasonal pricing
        hotel_lean = engine.calculate_hotel_night(
            "HTL-01", "STANDARD",
            "2026-11-20", "2026-11-15"
        )

        hotel_peak = engine.calculate_hotel_night(
            "HTL-01", "STANDARD",
            "2026-12-15", "2026-11-15"
        )

        print("\nHOTEL SEASON TEST:")
        print("Lean:", hotel_lean)
        print("Peak:", hotel_peak)

        # Test 7: Vehicle cost
        print("\nVEHICLE TESTS:")

        for pax in [4, 5, 8, 12, 13]:
            print(pax, "travellers:",
                  engine.calculate_vehicle_cost(pax))

        # Test 8: Activity eligibility
        traveller = {
            "date_of_birth": "2020-01-01"
        }

        activity_result = engine.calculate_activity_cost(
            "ACT-01", traveller,
            "2026-11-15", "2026-11-15"
        )

        print("\nACTIVITY TEST:")
        print(activity_result)

        # Test 9: Child-minding
        print("\nCHILD-MINDING TEST:")

        print(
            engine.calculate_child_minding_cost(
                True, True
            )
        )

        # Test 10: Meal pricing
        print("\nMEAL TEST:")

        traveller = {
            "date_of_birth": "2020-01-01"
        }

        print(
            engine.calculate_meal_cost(
                "MEAL-01", traveller,
                "2026-11-15", "2026-11-15"
            )
        )

        print("\nAll foundational cost engine tests completed.")

    except (CostEngineError, FileNotFoundError, ValueError) as error:

        print(f"\nCOST ENGINE ERROR: {error}")
