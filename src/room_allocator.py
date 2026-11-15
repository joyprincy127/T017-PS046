
from decimal import Decimal, InvalidOperation


class RoomAllocationError(Exception):
    """Raised when room allocation cannot be completed."""


class RoomAllocator:
    """
    Allocates hotel rooms based on adult and child counts.

    Business rules:
    - Adults share twin rooms.
    - An odd adult can choose SINGLE or TRIPLE.
    - SINGLE: 60% supplement on the odd adult's half-room share.
    - TRIPLE: 75% supplement on the odd adult's half-room share.
    - Children under 5 share free with two adults.
    - Children aged 5-11 use an extra bed at 40% of room cost.
    """

    def __init__(
        self,
        room_cost,
        single_pct=Decimal("0.60"),
        third_adult_pct=Decimal("0.75"),
        child_extra_bed_pct=Decimal("0.40")
    ):

        try:
            self.room_cost = Decimal(str(room_cost))
            self.single_pct = Decimal(str(single_pct))
            self.third_adult_pct = Decimal(str(third_adult_pct))
            self.child_extra_bed_pct = Decimal(str(child_extra_bed_pct))

        except (InvalidOperation, ValueError, TypeError):
            raise RoomAllocationError(
                "Room cost and pricing percentages must be valid numbers"
            )

        if not self.room_cost.is_finite() or self.room_cost <= 0:
            raise RoomAllocationError(
                "Room cost must be a positive finite number"
            )

        percentages = [
            self.single_pct,
            self.third_adult_pct,
            self.child_extra_bed_pct
        ]

        if any(
            not percentage.is_finite() or percentage < 0
            for percentage in percentages
        ):
            raise RoomAllocationError(
                "Pricing percentages must be non-negative finite numbers"
            )

    def allocate(
        self,
        adults,
        children_under_5=0,
        children_5_11=0,
        odd_adult_option="SINGLE"
    ):

        # Validate traveller counts.
        counts = [adults, children_under_5, children_5_11]

        if any(
            not isinstance(number, int)
            or isinstance(number, bool)
            or number < 0
            for number in counts
        ):
            raise RoomAllocationError(
                "Traveller counts must be non-negative integers"
            )

        # Children must share accommodation with two adults.
        total_children = children_under_5 + children_5_11

        if total_children > 0 and adults < 2:
            raise RoomAllocationError(
                "Children must share accommodation with at least two adults"
            )

        # Validate odd adult option.
        if not isinstance(odd_adult_option, str):
            raise RoomAllocationError(
                "Odd adult option must be SINGLE or TRIPLE"
            )

        odd_adult_option = odd_adult_option.strip().upper()

        if odd_adult_option not in ("SINGLE", "TRIPLE"):
            raise RoomAllocationError(
                "Odd adult option must be SINGLE or TRIPLE"
            )

        # Calculate the cost of one adult's share of a twin room.
        per_person_cost = self.room_cost / Decimal("2")

        # Initialize cost components.
        base_room_cost = Decimal("0")
        single_supplement = Decimal("0")
        third_adult_supplement = Decimal("0")
        under_5_cost = Decimal("0")
        child_extra_bed_cost = Decimal("0")

        # Allocate rooms for adults.
        full_twin_rooms = adults // 2
        odd_adult = adults % 2

        base_room_cost = (
            Decimal(full_twin_rooms) * self.room_cost
        )

        if odd_adult:

            if odd_adult_option == "SINGLE":

                # Odd adult pays half-room cost plus 60% supplement.
                base_room_cost += per_person_cost

                single_supplement = (
                    per_person_cost * self.single_pct
                )

            elif odd_adult_option == "TRIPLE":

                # Odd adult joins a twin room and pays 75% supplement.
                third_adult_supplement = (
                    per_person_cost * self.third_adult_pct
                )

        # Children under 5 stay free when sharing with two adults.
        under_5_cost = Decimal("0")

        # Children aged 5-11 require an extra bed.
        child_extra_bed_cost = (
            Decimal(children_5_11)
            * self.room_cost
            * self.child_extra_bed_pct
        )

        # Calculate total accommodation cost.
        total_cost = (
            base_room_cost
            + single_supplement
            + third_adult_supplement
            + child_extra_bed_cost
        )

        return {
            "adults": adults,
            "children_under_5": children_under_5,
            "children_5_11": children_5_11,
            "odd_adult_option": odd_adult_option,
            "full_twin_rooms": full_twin_rooms,
            "odd_adult": odd_adult,
            "base_room_cost": base_room_cost,
            "single_supplement": single_supplement,
            "third_adult_supplement": third_adult_supplement,
            "child_extra_bed_cost": child_extra_bed_cost,
            "under_5_cost": under_5_cost,
            "total_room_cost": total_cost
        }


if __name__ == "__main__":

    print("\n--- ROOM ALLOCATION TESTS ---")

    allocator = RoomAllocator(5000)

    test_cases = [
        (2, 0, 0, "SINGLE"),
        (3, 0, 0, "SINGLE"),
        (3, 0, 0, "TRIPLE"),
        (4, 0, 0, "SINGLE"),
        (5, 0, 0, "SINGLE"),
        (5, 0, 0, "TRIPLE"),
        (2, 1, 0, "SINGLE"),
        (2, 0, 1, "SINGLE"),
    ]

    for adults, under_5, children_5_11, option in test_cases:

        result = allocator.allocate(
            adults=adults,
            children_under_5=under_5,
            children_5_11=children_5_11,
            odd_adult_option=option
        )

        print(
            f"\nTest: {adults} adults, "
            f"{under_5} under-5 children, "
            f"{children_5_11} children aged 5-11, "
            f"Option: {option}"
        )

        print("Total room cost:", result["total_room_cost"])
        print("Breakdown:", result)

    # Q-010: 3 adults + 1 child aged 4, SINGLE.
    print("\n--- Q-010 ROOM TEST ---")

    q010 = allocator.allocate(
        adults=3,
        children_under_5=1,
        children_5_11=0,
        odd_adult_option="SINGLE"
    )

    print("Q-010 total:", q010["total_room_cost"])

    # Q-016: 5 adults, TRIPLE.
    print("\n--- Q-016 ROOM TEST ---")

    q016 = allocator.allocate(
        adults=5,
        children_under_5=0,
        children_5_11=0,
        odd_adult_option="TRIPLE"
    )

    print("Q-016 total:", q016["total_room_cost"])

    # Validation test: children without two adults.
    print("\n--- VALIDATION TEST ---")

    try:
        allocator.allocate(
            adults=1,
            children_under_5=1
        )

    except RoomAllocationError as error:
        print("Validation successful:", error)
