
from decimal import Decimal
from datetime import date, timedelta

from room_allocator import RoomAllocator
from data_loader import load_all_data
from cost_engine import CostEngine


class ItineraryEngine:
    """Calculates package costs using itinerary and component data."""

    def __init__(self, data, cost_engine):

        self.data = data
        self.cost_engine = cost_engine

        # Reuse CostEngine lookup dictionaries.
        self.hotels = cost_engine.hotels
        self.activities = cost_engine.activities
        self.vehicles = cost_engine.vehicles
        self.meals = cost_engine.meals

        self.packages = {
            row["package_id"]: row
            for row in data["packages"]
        }

        self.parameters = cost_engine.parameters
        self.seasons = cost_engine.seasons
        self.fx_rates = cost_engine.fx_rates

        self.itinerary = data["package_itinerary"]
        self.activity_optouts = data.get("activity_optouts", [])

    # --------------------------------------------------
    # 1. GENERAL HELPERS
    # --------------------------------------------------

    @staticmethod
    def money(value):
        return Decimal(str(value))

    @staticmethod
    def convert_to_date(value):
        if isinstance(value, date):
            return value

        return date.fromisoformat(str(value))

    def calculate_component_cost(
        self, component_type, unit_cost, units=1
    ):

        component_type = component_type.upper()
        unit_cost = self.money(unit_cost)
        units = self.money(units)

        if unit_cost < 0 or units < 0:
            raise ValueError(
                "Unit cost and units cannot be negative."
            )

        return {
            "component_type": component_type,
            "unit_cost": unit_cost,
            "units": units,
            "total_cost": unit_cost * units
        }

    # --------------------------------------------------
    # 2. HOTEL COST
    # --------------------------------------------------

    def calculate_hotel_costs(
        self,
        package_id,
        departure_date,
        quote_date,
        room_preference,
        odd_adult_option,
        travellers
    ):

        departure_date = self.convert_to_date(departure_date)
        quote_date = self.convert_to_date(quote_date)

        room_preference = room_preference.upper()
        odd_adult_option = odd_adult_option.upper()

        if package_id not in self.packages:
            raise ValueError(f"Unknown package: {package_id}")

        hotel_records = [
            row for row in self.itinerary
            if row["package_id"] == package_id
            and row["component_type"] == "HOTEL"
        ]

        night_breakdown = []
        total_hotel_cost = Decimal("0")

        for record in sorted(
            hotel_records,
            key=lambda row: int(row["day_no"])
        ):

            day_no = int(record["day_no"])
            hotel_id = record["component_id"]

            night_date = departure_date + timedelta(
                days=day_no - 1
            )

            hotel_details = (
                self.cost_engine.calculate_hotel_night(
                    hotel_id,
                    room_preference,
                    night_date,
                    quote_date
                )
            )

            adults = 0
            children_under_5 = 0
            children_5_11 = 0

            for traveller in travellers:

                age = self.cost_engine.get_age(
                    traveller,
                    night_date
                )

                if age >= 12:
                    adults += 1
                elif age >= 5:
                    children_5_11 += 1
                else:
                    children_under_5 += 1

            # Read percentages from rate_parameters.csv.
            allocator = RoomAllocator(
                hotel_details["room_cost_inr"],
                single_pct=(
                    self.cost_engine.get_parameter(
                        "SINGLE_SUPPLEMENT_PCT"
                    ) / Decimal("100")
                ),
                third_adult_pct=(
                    self.cost_engine.get_parameter(
                        "THIRD_ADULT_PCT"
                    ) / Decimal("100")
                ),
                child_extra_bed_pct=(
                    self.cost_engine.get_parameter(
                        "EXTRA_BED_CHILD_PCT"
                    ) / Decimal("100")
                )
            )

            allocation = allocator.allocate(
                adults=adults,
                children_under_5=children_under_5,
                children_5_11=children_5_11,
                odd_adult_option=odd_adult_option
            )

            night_cost = allocation["total_room_cost"]
            total_hotel_cost += night_cost

            night_breakdown.append({
                "day_no": day_no,
                "hotel_id": hotel_id,
                "night_date": night_date.isoformat(),
                "season": hotel_details["season"],
                "multiplier": hotel_details["multiplier"],
                "twin_room_cost": hotel_details["room_cost_inr"],
                "adults": adults,
                "children_under_5": children_under_5,
                "children_5_11": children_5_11,
                "room_allocation": allocation,
                "night_cost": night_cost
            })

        return {
            "total_hotel_cost": total_hotel_cost,
            "night_breakdown": night_breakdown
        }

    # --------------------------------------------------
    # 3. VEHICLE COST
    # --------------------------------------------------

    def calculate_vehicle_day_cost(
        self, travellers, travel_date
    ):

        seated_pax = (
            self.cost_engine.count_seated_travellers(
                travellers,
                travel_date
            )
        )

        if seated_pax == 0:
            return {
                "seated_pax": 0,
                "vehicle_type": None,
                "total_cost": Decimal("0")
            }

        result = self.cost_engine.calculate_vehicle_cost(
            seated_pax
        )

        return {
            "seated_pax": seated_pax,
            "vehicle_type": result["vehicle_type"],
            "total_cost": result["total_cost_inr"],
            "cost_per_seated_person": (
                result["cost_per_seated_person"]
            )
        }

    # --------------------------------------------------
    # 4. GUIDE COST
    # --------------------------------------------------

    def calculate_guide_day_cost(self, paying_travellers):

        if paying_travellers <= 0:
            return Decimal("0")

        result = self.cost_engine.calculate_guide_cost(
            paying_travellers
        )

        return result["total_cost_inr"]

    # --------------------------------------------------
    # 5. MEAL COST
    # --------------------------------------------------

    def calculate_meal_day_cost(
        self,
        meal_id,
        travellers,
        meal_date,
        quote_date
    ):

        total_meal_cost = Decimal("0")
        traveller_breakdown = []

        for traveller in travellers:

            result = self.cost_engine.calculate_meal_cost(
                meal_id,
                traveller,
                meal_date,
                quote_date
            )

            total_meal_cost += result["cost_inr"]

            traveller_breakdown.append({
                "traveller_id": traveller["traveller_id"],
                "age": result["age"],
                "cost": result["cost_inr"]
            })

        return {
            "meal_id": meal_id,
            "total_cost": total_meal_cost,
            "traveller_breakdown": traveller_breakdown
        }

    # --------------------------------------------------
    # 6. ACTIVITY OPT-OUT HELPERS
    # --------------------------------------------------

    def is_opted_out(
        self, quote_id, traveller_id, activity_id
    ):

        if not quote_id:
            return False

        return any(
            row["quote_id"] == quote_id
            and row["traveller_id"] == traveller_id
            and row["activity_id"] == activity_id
            for row in self.activity_optouts
        )

    # --------------------------------------------------
    # 7. ACTIVITY AND CHILD-MINDING COST
    # --------------------------------------------------

    def calculate_activity_day_cost(
        self,
        activity_id,
        travellers,
        activity_date,
        quote_date,
        quote_id=None
    ):

        total_activity_cost = Decimal("0")
        total_child_minding_cost = Decimal("0")

        traveller_lookup = {
            traveller["traveller_id"]: traveller
            for traveller in travellers
        }

        activity_breakdown = []

        for traveller in travellers:

            traveller_id = traveller["traveller_id"]

            result = self.cost_engine.calculate_activity_cost(
                activity_id,
                traveller,
                activity_date,
                quote_date
            )

            opted_out = self.is_opted_out(
                quote_id,
                traveller_id,
                activity_id
            )

            participating = result["eligible"] and not opted_out

            if participating:

                total_activity_cost += result["cost_inr"]

            child_minding = Decimal("0")

            # Check whether an ineligible child needs supervision
            # while both parents participate in this activity.
            if not result["eligible"] and (
                traveller.get("parent_1_id")
                and traveller.get("parent_2_id")
            ):

                parent_1 = traveller_lookup.get(
                    traveller["parent_1_id"]
                )

                parent_2 = traveller_lookup.get(
                    traveller["parent_2_id"]
                )

                if parent_1 and parent_2:

                    parent_1_result = (
                        self.cost_engine.calculate_activity_cost(
                            activity_id,
                            parent_1,
                            activity_date,
                            quote_date
                        )
                    )

                    parent_2_result = (
                        self.cost_engine.calculate_activity_cost(
                            activity_id,
                            parent_2,
                            activity_date,
                            quote_date
                        )
                    )

                    parent_1_participates = (
                        parent_1_result["eligible"]
                        and not self.is_opted_out(
                            quote_id,
                            parent_1["traveller_id"],
                            activity_id
                        )
                    )

                    parent_2_participates = (
                        parent_2_result["eligible"]
                        and not self.is_opted_out(
                            quote_id,
                            parent_2["traveller_id"],
                            activity_id
                        )
                    )

                    if (
                        parent_1_participates
                        and parent_2_participates
                    ):
                        child_minding = (
                            self.cost_engine.calculate_child_minding_cost(
                                True, True
                            )
                        )

                        total_child_minding_cost += child_minding

            activity_breakdown.append({
                "traveller_id": traveller_id,
                "eligible": result["eligible"],
                "opted_out": opted_out,
                "participating": participating,
                "activity_cost": (
                    result["cost_inr"]
                    if participating
                    else Decimal("0")
                ),
                "child_minding_cost": child_minding
            })

        return {
            "activity_id": activity_id,
            "activity_cost": total_activity_cost,
            "child_minding_cost": total_child_minding_cost,
            "total_cost": (
                total_activity_cost
                + total_child_minding_cost
            ),
            "traveller_breakdown": activity_breakdown
        }

    # --------------------------------------------------
    # 8. COMPLETE PACKAGE COST CALCULATION
    # --------------------------------------------------

    def calculate_package_costs(
        self,
        package_id,
        departure_date,
        quote_date,
        room_preference,
        odd_adult_option,
        travellers,
        paying_travellers=None,
        quote_id=None
    ):

        departure_date = self.convert_to_date(departure_date)
        quote_date = self.convert_to_date(quote_date)

        if package_id not in self.packages:
            raise ValueError(f"Unknown package: {package_id}")

        if not travellers:
            raise ValueError("At least one traveller is required.")

        if paying_travellers is None:
            paying_travellers = len(travellers)

        if (
            not isinstance(paying_travellers, int)
            or isinstance(paying_travellers, bool)
            or paying_travellers < 0
        ):
            raise ValueError(
                "Paying traveller count must be a non-negative integer."
            )

        package_records = [
            row for row in self.itinerary
            if row["package_id"] == package_id
        ]

        daily_results = {}
        grand_total = Decimal("0")

        for record in package_records:

            day_no = int(record["day_no"])

            if day_no not in daily_results:
                travel_date = departure_date + timedelta(
                    days=day_no - 1
                )

                daily_results[day_no] = {
                    "date": travel_date.isoformat(),
                    "components": [],
                    "daily_total": Decimal("0")
                }

            else:
                travel_date = departure_date + timedelta(
                    days=day_no - 1
                )

            component_type = record["component_type"]
            component_id = record["component_id"]

            component_result = None

            if component_type == "HOTEL":

                hotel_details = (
                    self.cost_engine.calculate_hotel_night(
                        component_id,
                        room_preference.upper(),
                        travel_date,
                        quote_date
                    )
                )

                adults = 0
                under_5 = 0
                children_5_11 = 0

                for traveller in travellers:

                    age = self.cost_engine.get_age(
                        traveller, travel_date
                    )

                    if age >= 12:
                        adults += 1
                    elif age >= 5:
                        children_5_11 += 1
                    else:
                        under_5 += 1

                allocator = RoomAllocator(
                    hotel_details["room_cost_inr"],
                    single_pct=(
                        self.cost_engine.get_parameter(
                            "SINGLE_SUPPLEMENT_PCT"
                        ) / Decimal("100")
                    ),
                    third_adult_pct=(
                        self.cost_engine.get_parameter(
                            "THIRD_ADULT_PCT"
                        ) / Decimal("100")
                    ),
                    child_extra_bed_pct=(
                        self.cost_engine.get_parameter(
                            "EXTRA_BED_CHILD_PCT"
                        ) / Decimal("100")
                    )
                )

                allocation = allocator.allocate(
                    adults,
                    under_5,
                    children_5_11,
                    odd_adult_option
                )

                component_result = {
                    "component_type": "HOTEL",
                    "component_id": component_id,
                    "season": hotel_details["season"],
                    "multiplier": hotel_details["multiplier"],
                    "room_allocation": allocation,
                    "total_cost": allocation["total_room_cost"]
                }

            elif component_type == "VEHICLE":

                vehicle_result = (
                    self.calculate_vehicle_day_cost(
                        travellers, travel_date
                    )
                )

                component_result = {
                    "component_type": "VEHICLE",
                    "component_id": component_id,
                    **vehicle_result
                }

                component_result["total_cost"] = (
                    vehicle_result["total_cost"]
                )

            elif component_type == "GUIDE":

                guide_cost = self.calculate_guide_day_cost(
                    paying_travellers
                )

                component_result = {
                    "component_type": "GUIDE",
                    "component_id": component_id,
                    "total_cost": guide_cost
                }

            elif component_type == "MEAL":

                meal_result = self.calculate_meal_day_cost(
                    component_id,
                    travellers,
                    travel_date,
                    quote_date
                )

                component_result = {
                    "component_type": "MEAL",
                    "component_id": component_id,
                    **meal_result
                }

            elif component_type == "ACTIVITY":

                activity_result = (
                    self.calculate_activity_day_cost(
                        component_id,
                        travellers,
                        travel_date,
                        quote_date,
                        quote_id
                    )
                )

                component_result = {
                    "component_type": "ACTIVITY",
                    **activity_result
                }

            else:
                raise ValueError(
                    f"Unknown itinerary component: {component_type}"
                )

            component_cost = component_result["total_cost"]

            daily_results[day_no]["components"].append(
                component_result
            )

            daily_results[day_no]["daily_total"] += component_cost

        for day_result in daily_results.values():
            grand_total += day_result["daily_total"]

        return {
            "package_id": package_id,
            "departure_date": departure_date.isoformat(),
            "quote_date": quote_date.isoformat(),
            "daily_results": daily_results,
            "grand_total": grand_total
        }

    # --------------------------------------------------
    # 9. GENERIC DAILY TOTAL
    # --------------------------------------------------

    def calculate_daily_total(self, daily_components):

        daily_total = Decimal("0")
        component_results = []

        for component in daily_components:

            result = self.calculate_component_cost(
                component["component_type"],
                component["unit_cost"],
                component.get("units", 1)
            )

            component_results.append(result)
            daily_total += result["total_cost"]

        return {
            "components": component_results,
            "daily_total": daily_total
        }

    def calculate_itinerary_total(self, itinerary):

        grand_total = Decimal("0")
        daily_results = {}

        for day_no, components in itinerary.items():

            result = self.calculate_daily_total(components)

            daily_results[day_no] = result
            grand_total += result["daily_total"]

        return {
            "daily_results": daily_results,
            "grand_total": grand_total
        }


# --------------------------------------------------
# TEST THE ITINERARY ENGINE
# --------------------------------------------------

if __name__ == "__main__":

    print("\n--- ITINERARY ENGINE INTEGRATION TEST ---")

    try:

        project_data = load_all_data()

        cost_engine = CostEngine(project_data)

        engine = ItineraryEngine(
            project_data,
            cost_engine
        )

        print("\nCSV CONNECTION SUCCESSFUL")

        print("Hotels:", len(engine.hotels))
        print("Activities:", len(engine.activities))
        print("Vehicles:", len(engine.vehicles))
        print("Meals:", len(engine.meals))
        print("Packages:", len(engine.packages))
        print("Itinerary records:", len(engine.itinerary))

        # Q-001 details from commands.txt.
        quote_id = "Q-001"
        package_id = "PKG-02"
        departure_date = "2026-10-23"
        quote_date = "2026-08-20"
        room_preference = "DELUXE"
        odd_adult_option = "SINGLE"

        travellers = [
            row for row in project_data["travellers"]
            if row["quote_id"] == quote_id
            and row["on_initial_quote"].strip().lower() == "true"
        ]

        print("\nQ-001 TRAVELLERS:", len(travellers))

        result = engine.calculate_package_costs(
            package_id=package_id,
            departure_date=departure_date,
            quote_date=quote_date,
            room_preference=room_preference,
            odd_adult_option=odd_adult_option,
            travellers=travellers,
            quote_id=quote_id
        )

        print("\n--- DAILY COST BREAKDOWN ---")

        for day_no, day_result in sorted(
            result["daily_results"].items()
        ):

            print(f"\nDAY {day_no} - {day_result['date']}")

            for component in day_result["components"]:

                print(
                    component["component_type"],
                    component.get("component_id", ""),
                    "Cost:",
                    component["total_cost"]
                )

            print(
                "Daily total:",
                day_result["daily_total"]
            )

        print("\n--- PACKAGE TOTAL ---")
        print("Grand total:", result["grand_total"])

    except Exception as error:

        print("\nITINERARY ENGINE ERROR:", error)
        raise
