
from decimal import Decimal, ROUND_CEILING


class PricingEngine:

    def __init__(
        self,
        markup_pct=18,
        gst_pct=5,
        group_discount_6_to_9=5,
        group_discount_10_plus=10,
        early_bird_pct=8,
        max_discount_pct=15
    ):
        self.markup_pct = Decimal(str(markup_pct))
        self.gst_pct = Decimal(str(gst_pct))
        self.group_discount_6_to_9 = Decimal(str(group_discount_6_to_9))
        self.group_discount_10_plus = Decimal(str(group_discount_10_plus))
        self.early_bird_pct = Decimal(str(early_bird_pct))
        self.max_discount_pct = Decimal(str(max_discount_pct))

    def calculate_discount(self, paying_travellers, days_before_departure):

        if paying_travellers <= 0:
            raise ValueError("Paying travellers must be greater than zero.")

        if days_before_departure < 0:
            raise ValueError("Days before departure cannot be negative.")

        group_discount = Decimal("0")
        early_bird_discount = Decimal("0")

        # Group discount
        if 6 <= paying_travellers <= 9:
            group_discount = self.group_discount_6_to_9

        elif paying_travellers >= 10:
            group_discount = self.group_discount_10_plus

        # Early-bird discount
        if days_before_departure >= 60:
            early_bird_discount = self.early_bird_pct

        # Combine discounts, but do not exceed maximum
        total_discount = min(
            group_discount + early_bird_discount,
            self.max_discount_pct
        )

        return {
            "group_discount_pct": group_discount,
            "early_bird_discount_pct": early_bird_discount,
            "total_discount_pct": total_discount
        }

    def calculate_price(
        self,
        total_cost,
        paying_travellers,
        days_before_departure
    ):

        total_cost = Decimal(str(total_cost))

        if total_cost < 0:
            raise ValueError("Total cost cannot be negative.")

        if paying_travellers <= 0:
            raise ValueError("Paying travellers must be greater than zero.")

        discounts = self.calculate_discount(
            paying_travellers,
            days_before_departure
        )

        # Step 1: Add markup to the total cost
        markup_amount = total_cost * self.markup_pct / Decimal("100")
        cost_with_markup = total_cost + markup_amount

        # Step 2: Apply discount
        discount_amount = (
            cost_with_markup
            * discounts["total_discount_pct"]
            / Decimal("100")
        )

        discounted_price = cost_with_markup - discount_amount

        # Step 3: Calculate GST
        gst_amount = discounted_price * self.gst_pct / Decimal("100")

        final_group_price = discounted_price + gst_amount

        # Step 4: Calculate per-person price
        per_person_exact = final_group_price / Decimal(paying_travellers)

        # Round UP to nearest ₹10
        per_person_price = (
            (per_person_exact / Decimal("10"))
            .quantize(Decimal("1"), rounding=ROUND_CEILING)
            * Decimal("10")
        )

        return {
            "total_cost": total_cost,
            "markup_amount": markup_amount,
            "cost_with_markup": cost_with_markup,
            "group_discount_pct": discounts["group_discount_pct"],
            "early_bird_discount_pct": discounts["early_bird_discount_pct"],
            "total_discount_pct": discounts["total_discount_pct"],
            "discount_amount": discount_amount,
            "discounted_price": discounted_price,
            "gst_amount": gst_amount,
            "final_group_price": final_group_price,
            "per_person_exact": per_person_exact,
            "per_person_price": per_person_price
        }


if __name__ == "__main__":

    engine = PricingEngine()

    print("\n--- PRICING ENGINE TESTS ---")

    test_cases = [
        (50000, 4, 30),
        (100000, 7, 30),
        (150000, 10, 30),
        (150000, 10, 60),
        (200000, 12, 90),
        (100000, 9, 60),
    ]

    for total_cost, travellers, days in test_cases:

        result = engine.calculate_price(
            total_cost,
            travellers,
            days
        )

        print("\n--------------------------------")
        print(f"Total cost: ₹{total_cost}")
        print(f"Paying travellers: {travellers}")
        print(f"Days before departure: {days}")
        print(f"Group discount: {result['group_discount_pct']}%")
        print(f"Early-bird discount: {result['early_bird_discount_pct']}%")
        print(f"Total discount: {result['total_discount_pct']}%")
        print(f"Markup: ₹{result['markup_amount']}")
        print(f"GST: ₹{result['gst_amount']}")
        print(f"Final group price: ₹{result['final_group_price']}")
        print(f"Final per-person price: ₹{result['per_person_price']}")
