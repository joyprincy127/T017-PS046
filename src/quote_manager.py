"""
Tour Package Pricing and Itinerary Cost Engine
Module: QuoteManager

Orchestrates quotes, versioning, traveller management, pricing,
command processing, and CSV exports.
"""

import csv
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal, ROUND_CEILING
from pathlib import Path
from typing import Dict, List, Optional, Any

from cost_engine import CostEngine, age_on, parse_date, money
from itinerary_engine import ItineraryEngine
from pricing_engine import PricingEngine


def ceil_10(amount: Decimal) -> Decimal:
    """Round up to the nearest Rs 10."""
    return (
        (amount / Decimal("10")).quantize(Decimal("1"), rounding=ROUND_CEILING)
        * Decimal("10")
    )


def fmt_money(value: Decimal) -> str:
    """Format Decimal currency to 2 decimal places."""
    return f"{Decimal(str(value)):.2f}"


def get_cancellation_pct(days_before: int) -> Decimal:
    """
    Cancellation charges by days before departure:
    - > 45 days: 10%
    - 45 to 30 days: 25% (inclusive)
    - 29 to 15 days: 50% (inclusive)
    - < 15 days: 100%
    """
    if days_before > 45:
        return Decimal("10")
    elif days_before >= 30:
        return Decimal("25")
    elif days_before >= 15:
        return Decimal("50")
    else:
        return Decimal("100")


@dataclass
class TravellerInvoiceItem:
    quote_id: str
    traveller_id: str
    age_on_departure: int
    pricing_category: str  # ADULT, CHILD_5_11, CHILD_UNDER_5, FOC
    room_cost: Decimal
    shared_cost: Decimal
    activity_cost: Decimal
    meal_cost: Decimal
    child_minding_cost: Decimal
    sell_before_gst: Decimal
    gst: Decimal
    per_person_sell: Decimal

    def to_csv_dict(self) -> Dict[str, str]:
        return {
            "quote_id": self.quote_id,
            "traveller_id": self.traveller_id,
            "age_on_departure": str(self.age_on_departure),
            "pricing_category": self.pricing_category,
            "room_cost": fmt_money(self.room_cost),
            "shared_cost": fmt_money(self.shared_cost),
            "activity_cost": fmt_money(self.activity_cost),
            "meal_cost": fmt_money(self.meal_cost),
            "child_minding_cost": fmt_money(self.child_minding_cost),
            "sell_before_gst": fmt_money(self.sell_before_gst),
            "gst": fmt_money(self.gst),
            "per_person_sell": fmt_money(self.per_person_sell),
        }


@dataclass
class QuoteVersion:
    quote_id: str
    version: int
    package_id: str
    departure_date: date
    quote_date: date
    room_preference: str
    odd_adult_option: str
    travellers: List[Dict[str, Any]]
    status: str  # QUOTED, CHANGED, CANCELLED
    paying_travellers: int = 0
    foc_count: int = 0
    total_cost: Decimal = Decimal("0.00")
    markup: Decimal = Decimal("0.00")
    group_discount_pct: Decimal = Decimal("0.00")
    early_bird_pct: Decimal = Decimal("0.00")
    applied_discount_pct: Decimal = Decimal("0.00")
    discount_amount: Decimal = Decimal("0.00")
    sell_before_gst: Decimal = Decimal("0.00")
    gst: Decimal = Decimal("0.00")
    total_sell: Decimal = Decimal("0.00")
    cost_sheet_rows: List[Dict[str, str]] = field(default_factory=list)
    traveller_invoices: List[TravellerInvoiceItem] = field(default_factory=list)

    def to_summary_dict(self) -> Dict[str, str]:
        return {
            "quote_id": self.quote_id,
            "version": str(self.version),
            "package_id": self.package_id,
            "departure_date": self.departure_date.isoformat(),
            "paying_travellers": str(self.paying_travellers),
            "foc_count": str(self.foc_count),
            "total_cost": fmt_money(self.total_cost),
            "markup": fmt_money(self.markup),
            "group_discount_pct": str(self.group_discount_pct),
            "early_bird_pct": str(self.early_bird_pct),
            "applied_discount_pct": str(self.applied_discount_pct),
            "discount_amount": fmt_money(self.discount_amount),
            "sell_before_gst": fmt_money(self.sell_before_gst),
            "gst": fmt_money(self.gst),
            "total_sell": fmt_money(self.total_sell),
            "status": self.status,
        }


@dataclass
class ChangeLogEntry:
    line_no: int
    quote_id: str
    command: str
    status: str  # APPLIED, REJECTED
    old_total_sell: Decimal
    new_total_sell: Decimal
    difference: Decimal
    change_fee: Decimal
    cancellation_charge: Decimal
    reason: str

    def to_csv_dict(self) -> Dict[str, str]:
        return {
            "line_no": str(self.line_no),
            "quote_id": self.quote_id,
            "command": self.command,
            "status": self.status,
            "old_total_sell": fmt_money(self.old_total_sell),
            "new_total_sell": fmt_money(self.new_total_sell),
            "difference": fmt_money(self.difference),
            "change_fee": fmt_money(self.change_fee),
            "cancellation_charge": fmt_money(self.cancellation_charge),
            "reason": self.reason,
        }


class QuoteManager:
    """Manages quotes, price calculations, changes, cancellations and CSV outputs."""

    def __init__(self, data: Dict[str, Any]):
        self.data = data
        self.cost_engine = CostEngine(data)
        self.itinerary_engine = ItineraryEngine(data, self.cost_engine)
        self.pricing_engine = PricingEngine()

        # All travellers lookup by ID
        self.all_travellers = {
            row["traveller_id"]: row
            for row in data["travellers"]
        }

        # Quotes state: quote_id -> list of QuoteVersion
        self.quotes: Dict[str, List[QuoteVersion]] = {}

        # Change log records in order of commands processed
        self.change_log: List[ChangeLogEntry] = []

    def get_latest_version(self, quote_id: str) -> Optional[QuoteVersion]:
        if quote_id in self.quotes and self.quotes[quote_id]:
            return self.quotes[quote_id][-1]
        return None

    # -------------------------------------------------------------------------
    # Core Pricing and Component Allocation
    # -------------------------------------------------------------------------

    def _price_quote_version(
        self,
        quote_id: str,
        version_num: int,
        package_id: str,
        departure_date: date,
        quote_date: date,
        room_preference: str,
        odd_adult_option: str,
        travellers: List[Dict[str, Any]],
        status: str
    ) -> QuoteVersion:
        """
        Price a complete quote version and generate detailed component allocations.
        """
        if status == "CANCELLED":
            # For a cancelled quote, version amounts become 0.00
            cancelled_version = QuoteVersion(
                quote_id=quote_id,
                version=version_num,
                package_id=package_id,
                departure_date=departure_date,
                quote_date=quote_date,
                room_preference=room_preference,
                odd_adult_option=odd_adult_option,
                travellers=list(travellers),
                status="CANCELLED",
                paying_travellers=0,
                foc_count=0,
                total_cost=Decimal("0.00"),
                markup=Decimal("0.00"),
                group_discount_pct=Decimal("0"),
                early_bird_pct=Decimal("0"),
                applied_discount_pct=Decimal("0"),
                discount_amount=Decimal("0.00"),
                sell_before_gst=Decimal("0.00"),
                gst=Decimal("0.00"),
                total_sell=Decimal("0.00"),
                cost_sheet_rows=[],
                traveller_invoices=[]
            )
            for trv in travellers:
                age_dep = age_on(trv["date_of_birth"], departure_date)
                if trv.get("group_leader", "").strip().lower() == "true":
                    cat = "FOC"
                elif age_dep >= 12:
                    cat = "ADULT"
                elif age_dep >= 5:
                    cat = "CHILD_5_11"
                else:
                    cat = "CHILD_UNDER_5"
                cancelled_version.traveller_invoices.append(
                    TravellerInvoiceItem(
                        quote_id=quote_id,
                        traveller_id=trv["traveller_id"],
                        age_on_departure=age_dep,
                        pricing_category=cat,
                        room_cost=Decimal("0.00"),
                        shared_cost=Decimal("0.00"),
                        activity_cost=Decimal("0.00"),
                        meal_cost=Decimal("0.00"),
                        child_minding_cost=Decimal("0.00"),
                        sell_before_gst=Decimal("0.00"),
                        gst=Decimal("0.00"),
                        per_person_sell=Decimal("0.00")
                    )
                )
            return cancelled_version

        # 1. Analyse travellers on departure date
        classified = []
        adult_count = 0
        child_5_11_count = 0
        child_under_5_count = 0

        for trv in travellers:
            age_dep = age_on(trv["date_of_birth"], departure_date)
            is_leader = trv.get("group_leader", "").strip().lower() == "true"
            if age_dep >= 12:
                adult_count += 1
                role = "ADULT"
            elif age_dep >= 5:
                child_5_11_count += 1
                role = "CHILD_5_11"
            else:
                child_under_5_count += 1
                role = "CHILD_UNDER_5"

            classified.append({
                "trv": trv,
                "age_dep": age_dep,
                "role": role,
                "is_leader": is_leader
            })

        # 2. Check FOC eligibility (EC-02: 16 adults, leader earns FOC -> exactly 15 paying adults + 1 FOC)
        foc_traveller_id = None
        paying_adult_count = adult_count
        foc_count = 0

        # If there are at least 15 paying adults (i.e. >= 16 adults total) and an adult leader exists
        if adult_count >= 16:
            for item in classified:
                if item["role"] == "ADULT" and item["is_leader"]:
                    foc_traveller_id = item["trv"]["traveller_id"]
                    item["role"] = "FOC"
                    foc_count = 1
                    paying_adult_count = adult_count - 1
                    break

        paying_travellers = paying_adult_count

        # 3. Calculate itinerary package costs using ItineraryEngine
        pkg_result = self.itinerary_engine.calculate_package_costs(
            package_id=package_id,
            departure_date=departure_date,
            quote_date=quote_date,  # locked quote-date rate + 2%
            room_preference=room_preference,
            odd_adult_option=odd_adult_option,
            travellers=travellers,
            paying_travellers=paying_adult_count,
            quote_id=quote_id
        )

        grand_total_cost = pkg_result["grand_total"]

        # 4. Generate cost sheet rows
        cost_sheet_rows = []
        for day_no, day_data in sorted(pkg_result["daily_results"].items()):
            travel_date = departure_date + timedelta(days=day_no - 1)
            for comp in day_data["components"]:
                c_type = comp["component_type"]
                c_id = comp.get("component_id") or comp.get("activity_id") or ""
                c_cost = comp["total_cost"]

                if c_type == "HOTEL":
                    night_date_str = travel_date.isoformat()
                    season = comp["season"]
                    multiplier = str(comp["multiplier"])
                    alloc = comp["room_allocation"]
                    hotel_details = self.cost_engine.calculate_hotel_night(
                        c_id, room_preference, travel_date, quote_date
                    )
                    unit_cost = hotel_details["unit_cost_inr"]
                    effective_rate = unit_cost * comp["multiplier"]
                    units = (c_cost / effective_rate) if effective_rate > 0 else Decimal("1")
                    units_str = f"{units:.2f}" if units % 1 != 0 else str(int(units))

                elif c_type == "VEHICLE":
                    night_date_str = ""
                    season = ""
                    multiplier = ""
                    unit_cost = c_cost
                    units_str = "1"

                elif c_type == "GUIDE":
                    night_date_str = ""
                    season = ""
                    multiplier = ""
                    unit_cost = c_cost
                    units_str = "1"

                elif c_type == "MEAL":
                    night_date_str = ""
                    season = ""
                    multiplier = ""
                    meal_obj = self.cost_engine.meals.get(c_id, {})
                    unit_cost = self.cost_engine.convert_to_inr(
                        meal_obj.get("adult_cost_per_day", 0),
                        meal_obj.get("currency", "INR"),
                        quote_date
                    )
                    units_str = str(len(travellers))

                elif c_type == "ACTIVITY":
                    night_date_str = ""
                    season = ""
                    multiplier = ""
                    act_obj = self.cost_engine.activities.get(c_id, {})
                    unit_cost = self.cost_engine.convert_to_inr(
                        act_obj.get("cost_per_person", 0),
                        act_obj.get("currency", "INR"),
                        quote_date
                    )
                    breakdown = comp.get("traveller_breakdown", [])
                    part_count = sum(1 for b in breakdown if b.get("participating", False))
                    units_str = str(part_count)

                else:
                    night_date_str = ""
                    season = ""
                    multiplier = ""
                    unit_cost = c_cost
                    units_str = "1"

                cost_sheet_rows.append({
                    "quote_id": quote_id,
                    "version": str(version_num),
                    "day_no": str(day_no),
                    "night_date": night_date_str,
                    "component_type": c_type,
                    "component_id": c_id,
                    "season": season,
                    "multiplier": multiplier,
                    "unit_cost_inr": fmt_money(unit_cost),
                    "units": units_str,
                    "cost_inr": fmt_money(c_cost),
                })

        # 5. Group Pricing Calculations
        days_before_departure = (departure_date - quote_date).days
        discounts = self.pricing_engine.calculate_discount(
            paying_travellers, days_before_departure
        )
        group_disc_pct = discounts["group_discount_pct"]
        early_bird_pct = discounts["early_bird_discount_pct"]
        applied_disc_pct = discounts["total_discount_pct"]

        markup_amount = grand_total_cost * Decimal("18") / Decimal("100")
        cost_with_markup = grand_total_cost + markup_amount
        discount_amount = cost_with_markup * applied_disc_pct / Decimal("100")
        sell_before_gst = cost_with_markup - discount_amount
        gst_amount = sell_before_gst * Decimal("5") / Decimal("100")
        total_sell = sell_before_gst + gst_amount

        # 6. Detailed Traveller Invoice Allocation
        traveller_components = {
            trv["traveller_id"]: {
                "room_cost": Decimal("0.00"),
                "shared_cost": Decimal("0.00"),
                "activity_cost": Decimal("0.00"),
                "meal_cost": Decimal("0.00"),
                "child_minding_cost": Decimal("0.00"),
            }
            for trv in travellers
        }

        # (a) Room Cost Allocation across days
        for day_no, day_data in pkg_result["daily_results"].items():
            travel_date = departure_date + timedelta(days=day_no - 1)
            for comp in day_data["components"]:
                if comp["component_type"] == "HOTEL":
                    night_room_cost = comp["room_allocation"]["total_room_cost"]
                    hotel_details = self.cost_engine.calculate_hotel_night(
                        comp["component_id"], room_preference, travel_date, quote_date
                    )
                    base_twin_cost = hotel_details["room_cost_inr"]

                    child_extra_bed_rate = base_twin_cost * Decimal("0.40")

                    adults_on_night = []
                    for item in classified:
                        t_id = item["trv"]["traveller_id"]
                        t_age = self.cost_engine.get_age(item["trv"], travel_date)
                        if t_age >= 12:
                            adults_on_night.append(t_id)
                        elif t_age >= 5:
                            traveller_components[t_id]["room_cost"] += child_extra_bed_rate

                    total_child_room = child_extra_bed_rate * Decimal(
                        sum(1 for item in classified if 5 <= self.cost_engine.get_age(item["trv"], travel_date) < 12)
                    )
                    adult_room_cost_total = night_room_cost - total_child_room

                    if foc_traveller_id and foc_traveller_id in adults_on_night:
                        paying_adults_on_night = [
                            aid for aid in adults_on_night if aid != foc_traveller_id
                        ]
                        share = adult_room_cost_total / Decimal(len(paying_adults_on_night))
                        for aid in paying_adults_on_night:
                            traveller_components[aid]["room_cost"] += share
                    else:
                        full_twins = len(adults_on_night) // 2
                        odd_adult = len(adults_on_night) % 2
                        twin_half = base_twin_cost / Decimal("2")

                        if odd_adult == 0:
                            for aid in adults_on_night:
                                traveller_components[aid]["room_cost"] += twin_half
                        else:
                            for i, aid in enumerate(adults_on_night):
                                if i < len(adults_on_night) - 1:
                                    traveller_components[aid]["room_cost"] += twin_half
                                else:
                                    if odd_adult_option == "SINGLE":
                                        traveller_components[aid]["room_cost"] += (
                                            twin_half * Decimal("1.60")
                                        )
                                    else:  # TRIPLE
                                        traveller_components[aid]["room_cost"] += (
                                            twin_half * Decimal("0.75")
                                        )

        # (b) Shared Cost Allocation (Vehicle + Guide)
        total_shared_cost = Decimal("0.00")
        for day_no, day_data in pkg_result["daily_results"].items():
            for comp in day_data["components"]:
                if comp["component_type"] in ("VEHICLE", "GUIDE"):
                    total_shared_cost += comp["total_cost"]

        total_weight = Decimal("0.00")
        for item in classified:
            if item["role"] == "ADULT":
                total_weight += Decimal("1.0")
            elif item["role"] == "CHILD_5_11":
                total_weight += Decimal("0.5")

        if total_weight > 0:
            adult_shared_share = total_shared_cost / total_weight
            child_shared_share = adult_shared_share * Decimal("0.5")
            for item in classified:
                t_id = item["trv"]["traveller_id"]
                if item["role"] == "ADULT":
                    traveller_components[t_id]["shared_cost"] += adult_shared_share
                elif item["role"] == "CHILD_5_11":
                    traveller_components[t_id]["shared_cost"] += child_shared_share

        # (c) Meal Cost Allocation
        for day_no, day_data in pkg_result["daily_results"].items():
            for comp in day_data["components"]:
                if comp["component_type"] == "MEAL":
                    breakdown = comp.get("traveller_breakdown", [])
                    foc_meal_accum = Decimal("0.00")
                    for b in breakdown:
                        t_id = b["traveller_id"]
                        cost = b["cost"]
                        if t_id == foc_traveller_id:
                            foc_meal_accum += cost
                        else:
                            traveller_components[t_id]["meal_cost"] += cost

                    if foc_meal_accum > 0 and paying_adult_count > 0:
                        foc_meal_share = foc_meal_accum / Decimal(paying_adult_count)
                        for item in classified:
                            if item["role"] == "ADULT":
                                traveller_components[item["trv"]["traveller_id"]]["meal_cost"] += foc_meal_share

        # (d) Activity & Child-Minding Cost Allocation
        for day_no, day_data in pkg_result["daily_results"].items():
            for comp in day_data["components"]:
                if comp["component_type"] == "ACTIVITY":
                    breakdown = comp.get("traveller_breakdown", [])
                    foc_act_accum = Decimal("0.00")
                    for b in breakdown:
                        t_id = b["traveller_id"]
                        act_cost = b["activity_cost"]
                        cm_cost = b["child_minding_cost"]

                        if t_id == foc_traveller_id:
                            foc_act_accum += act_cost
                        else:
                            traveller_components[t_id]["activity_cost"] += act_cost

                        if cm_cost > 0:
                            traveller_components[t_id]["child_minding_cost"] += cm_cost

                    if foc_act_accum > 0 and paying_adult_count > 0:
                        foc_act_share = foc_act_accum / Decimal(paying_adult_count)
                        for item in classified:
                            if item["role"] == "ADULT":
                                traveller_components[item["trv"]["traveller_id"]]["activity_cost"] += foc_act_share

        # 7. Compute individual sells and build TravellerInvoiceItem list
        traveller_invoices = []
        for item in classified:
            t_id = item["trv"]["traveller_id"]
            role = item["role"]
            comp = traveller_components[t_id]

            if role == "FOC":
                t_sell_before_gst = Decimal("0.00")
                t_gst = Decimal("0.00")
                per_person_sell = Decimal("0.00")
            else:
                t_cost = (
                    comp["room_cost"]
                    + comp["shared_cost"]
                    + comp["activity_cost"]
                    + comp["meal_cost"]
                    + comp["child_minding_cost"]
                )
                t_markup = t_cost * Decimal("18") / Decimal("100")
                t_with_markup = t_cost + t_markup
                t_discount = t_with_markup * applied_disc_pct / Decimal("100")
                t_sell_before_gst = t_with_markup - t_discount
                t_gst = t_sell_before_gst * Decimal("5") / Decimal("100")
                per_person_sell = ceil_10(t_sell_before_gst + t_gst)

            traveller_invoices.append(
                TravellerInvoiceItem(
                    quote_id=quote_id,
                    traveller_id=t_id,
                    age_on_departure=item["age_dep"],
                    pricing_category=role,
                    room_cost=comp["room_cost"],
                    shared_cost=comp["shared_cost"],
                    activity_cost=comp["activity_cost"],
                    meal_cost=comp["meal_cost"],
                    child_minding_cost=comp["child_minding_cost"],
                    sell_before_gst=t_sell_before_gst,
                    gst=t_gst,
                    per_person_sell=per_person_sell
                )
            )

        return QuoteVersion(
            quote_id=quote_id,
            version=version_num,
            package_id=package_id,
            departure_date=departure_date,
            quote_date=quote_date,
            room_preference=room_preference,
            odd_adult_option=odd_adult_option,
            travellers=list(travellers),
            status=status,
            paying_travellers=paying_travellers,
            foc_count=foc_count,
            total_cost=grand_total_cost,
            markup=markup_amount,
            group_discount_pct=group_disc_pct,
            early_bird_pct=early_bird_pct,
            applied_discount_pct=applied_disc_pct,
            discount_amount=discount_amount,
            sell_before_gst=sell_before_gst,
            gst=gst_amount,
            total_sell=total_sell,
            cost_sheet_rows=cost_sheet_rows,
            traveller_invoices=traveller_invoices
        )

    # -------------------------------------------------------------------------
    # Command Handlers
    # -------------------------------------------------------------------------

    def handle_quote(self, line_no: int, args: List[str]) -> bool:
        quote_id, package_id, dep_str, quote_str, room_pref, odd_opt = args
        departure_date = parse_date(dep_str)
        quote_date = parse_date(quote_str)
        room_pref = room_pref.strip().upper()
        odd_opt = odd_opt.strip().upper()

        if quote_id in self.quotes:
            curr = self.quotes[quote_id][-1]
            self.change_log.append(
                ChangeLogEntry(
                    line_no=line_no,
                    quote_id=quote_id,
                    command="QUOTE",
                    status="REJECTED",
                    old_total_sell=curr.total_sell,
                    new_total_sell=curr.total_sell,
                    difference=Decimal("0.00"),
                    change_fee=Decimal("0.00"),
                    cancellation_charge=Decimal("0.00"),
                    reason=f"Quote {quote_id} already exists"
                )
            )
            print(f"[{line_no}] REJECTED: Quote {quote_id} already exists.")
            return False

        initial_travellers = [
            row for row in self.data["travellers"]
            if row["quote_id"] == quote_id
            and row.get("on_initial_quote", "").strip().lower() == "true"
        ]

        if not initial_travellers:
            print(f"[{line_no}] ERROR: No initial travellers found for {quote_id}.")
            return False

        version_1 = self._price_quote_version(
            quote_id=quote_id,
            version_num=1,
            package_id=package_id,
            departure_date=departure_date,
            quote_date=quote_date,
            room_preference=room_pref,
            odd_adult_option=odd_opt,
            travellers=initial_travellers,
            status="QUOTED"
        )

        self.quotes[quote_id] = [version_1]
        print(f"[{line_no}] QUOTE {quote_id} v1 created: Total Sell Rs {fmt_money(version_1.total_sell)} ({version_1.paying_travellers} paying, {version_1.foc_count} FOC)")
        return True

    def handle_add_traveller(self, line_no: int, args: List[str]) -> bool:
        quote_id, traveller_id, change_str = args
        change_date = parse_date(change_str)

        latest = self.get_latest_version(quote_id)
        if not latest or latest.status == "CANCELLED":
            self.change_log.append(
                ChangeLogEntry(
                    line_no=line_no,
                    quote_id=quote_id,
                    command="ADD_TRAVELLER",
                    status="REJECTED",
                    old_total_sell=Decimal("0.00"),
                    new_total_sell=Decimal("0.00"),
                    difference=Decimal("0.00"),
                    change_fee=Decimal("0.00"),
                    cancellation_charge=Decimal("0.00"),
                    reason=f"Quote {quote_id} not active"
                )
            )
            return False

        if traveller_id not in self.all_travellers:
            self.change_log.append(
                ChangeLogEntry(
                    line_no=line_no,
                    quote_id=quote_id,
                    command="ADD_TRAVELLER",
                    status="REJECTED",
                    old_total_sell=latest.total_sell,
                    new_total_sell=latest.total_sell,
                    difference=Decimal("0.00"),
                    change_fee=Decimal("0.00"),
                    cancellation_charge=Decimal("0.00"),
                    reason=f"Unknown traveller {traveller_id}"
                )
            )
            return False

        new_trv = self.all_travellers[traveller_id]
        new_travellers = list(latest.travellers) + [new_trv]

        new_version = self._price_quote_version(
            quote_id=quote_id,
            version_num=latest.version + 1,
            package_id=latest.package_id,
            departure_date=latest.departure_date,
            quote_date=latest.quote_date,
            room_preference=latest.room_preference,
            odd_adult_option=latest.odd_adult_option,
            travellers=new_travellers,
            status="CHANGED"
        )

        diff = new_version.total_sell - latest.total_sell
        self.quotes[quote_id].append(new_version)
        self.change_log.append(
            ChangeLogEntry(
                line_no=line_no,
                quote_id=quote_id,
                command="ADD_TRAVELLER",
                status="APPLIED",
                old_total_sell=latest.total_sell,
                new_total_sell=new_version.total_sell,
                difference=diff,
                change_fee=Decimal("0.00"),
                cancellation_charge=Decimal("0.00"),
                reason=f"Added traveller {traveller_id}"
            )
        )
        print(f"[{line_no}] ADD_TRAVELLER {traveller_id} to {quote_id} (v{new_version.version}): New Sell Rs {fmt_money(new_version.total_sell)} (Diff: Rs {fmt_money(diff)})")
        return True

    def handle_remove_traveller(self, line_no: int, args: List[str]) -> bool:
        quote_id, traveller_id, change_str = args
        change_date = parse_date(change_str)

        latest = self.get_latest_version(quote_id)
        if not latest or latest.status == "CANCELLED":
            self.change_log.append(
                ChangeLogEntry(
                    line_no=line_no,
                    quote_id=quote_id,
                    command="REMOVE_TRAVELLER",
                    status="REJECTED",
                    old_total_sell=Decimal("0.00"),
                    new_total_sell=Decimal("0.00"),
                    difference=Decimal("0.00"),
                    change_fee=Decimal("0.00"),
                    cancellation_charge=Decimal("0.00"),
                    reason=f"Quote {quote_id} not active"
                )
            )
            return False

        trv_in_quote = [t for t in latest.travellers if t["traveller_id"] == traveller_id]
        if not trv_in_quote:
            self.change_log.append(
                ChangeLogEntry(
                    line_no=line_no,
                    quote_id=quote_id,
                    command="REMOVE_TRAVELLER",
                    status="REJECTED",
                    old_total_sell=latest.total_sell,
                    new_total_sell=latest.total_sell,
                    difference=Decimal("0.00"),
                    change_fee=Decimal("0.00"),
                    cancellation_charge=Decimal("0.00"),
                    reason=f"Traveller {traveller_id} does not belong to quote {quote_id}"
                )
            )
            print(f"[{line_no}] REJECTED: Traveller {traveller_id} does not belong to quote {quote_id}.")
            return False

        prev_inv = next((inv for inv in latest.traveller_invoices if inv.traveller_id == traveller_id), None)
        prev_sell = prev_inv.per_person_sell if prev_inv else (latest.total_sell / Decimal(len(latest.travellers)))

        days_before = (latest.departure_date - change_date).days
        cancel_pct = get_cancellation_pct(days_before)
        cancellation_charge = prev_sell * cancel_pct / Decimal("100")

        remaining_travellers = [t for t in latest.travellers if t["traveller_id"] != traveller_id]

        new_version = self._price_quote_version(
            quote_id=quote_id,
            version_num=latest.version + 1,
            package_id=latest.package_id,
            departure_date=latest.departure_date,
            quote_date=latest.quote_date,
            room_preference=latest.room_preference,
            odd_adult_option=latest.odd_adult_option,
            travellers=remaining_travellers,
            status="CHANGED"
        )

        diff = new_version.total_sell - latest.total_sell
        self.quotes[quote_id].append(new_version)
        self.change_log.append(
            ChangeLogEntry(
                line_no=line_no,
                quote_id=quote_id,
                command="REMOVE_TRAVELLER",
                status="APPLIED",
                old_total_sell=latest.total_sell,
                new_total_sell=new_version.total_sell,
                difference=diff,
                change_fee=Decimal("0.00"),
                cancellation_charge=cancellation_charge,
                reason=f"Removed traveller {traveller_id} ({cancel_pct}% charge)"
            )
        )
        print(f"[{line_no}] REMOVE_TRAVELLER {traveller_id} from {quote_id} (v{new_version.version}): Charge Rs {fmt_money(cancellation_charge)}, New Sell Rs {fmt_money(new_version.total_sell)}")
        return True

    def handle_date_shift(self, line_no: int, args: List[str]) -> bool:
        quote_id, new_dep_str, change_str = args
        new_departure_date = parse_date(new_dep_str)
        change_date = parse_date(change_str)

        latest = self.get_latest_version(quote_id)
        if not latest or latest.status == "CANCELLED":
            self.change_log.append(
                ChangeLogEntry(
                    line_no=line_no,
                    quote_id=quote_id,
                    command="DATE_SHIFT",
                    status="REJECTED",
                    old_total_sell=Decimal("0.00"),
                    new_total_sell=Decimal("0.00"),
                    difference=Decimal("0.00"),
                    change_fee=Decimal("0.00"),
                    cancellation_charge=Decimal("0.00"),
                    reason=f"Quote {quote_id} not active"
                )
            )
            return False

        shift_days = abs((new_departure_date - latest.departure_date).days)

        if shift_days <= 7:
            change_fee_param = self.cost_engine.get_parameter("DATE_SHIFT_FEE")
            change_fee = change_fee_param * Decimal(len(latest.travellers))
            cancel_charge = Decimal("0.00")
            reason = f"Date shift by {shift_days} days (<= 7 days)"
        else:
            days_before = (latest.departure_date - change_date).days
            cancel_pct = get_cancellation_pct(days_before)
            cancel_charge = latest.total_sell * cancel_pct / Decimal("100")
            change_fee = Decimal("0.00")
            reason = f"Date shift by {shift_days} days (> 7 days treated as cancellation {cancel_pct}% and rebooking)"

        new_version = self._price_quote_version(
            quote_id=quote_id,
            version_num=latest.version + 1,
            package_id=latest.package_id,
            departure_date=new_departure_date,
            quote_date=latest.quote_date,
            room_preference=latest.room_preference,
            odd_adult_option=latest.odd_adult_option,
            travellers=latest.travellers,
            status="CHANGED"
        )

        diff = new_version.total_sell - latest.total_sell
        self.quotes[quote_id].append(new_version)
        self.change_log.append(
            ChangeLogEntry(
                line_no=line_no,
                quote_id=quote_id,
                command="DATE_SHIFT",
                status="APPLIED",
                old_total_sell=latest.total_sell,
                new_total_sell=new_version.total_sell,
                difference=diff,
                change_fee=change_fee,
                cancellation_charge=cancel_charge,
                reason=reason
            )
        )
        print(f"[{line_no}] DATE_SHIFT for {quote_id} to {new_departure_date} (v{new_version.version}): Shift {shift_days}d, Fee Rs {fmt_money(change_fee)}, Cancel Rs {fmt_money(cancel_charge)}, New Sell Rs {fmt_money(new_version.total_sell)}")
        return True

    def handle_room_change(self, line_no: int, args: List[str]) -> bool:
        quote_id, new_room_pref, change_str = args
        new_room_pref = new_room_pref.strip().upper()
        change_date = parse_date(change_str)

        latest = self.get_latest_version(quote_id)
        if not latest or latest.status == "CANCELLED":
            self.change_log.append(
                ChangeLogEntry(
                    line_no=line_no,
                    quote_id=quote_id,
                    command="ROOM_CHANGE",
                    status="REJECTED",
                    old_total_sell=Decimal("0.00"),
                    new_total_sell=Decimal("0.00"),
                    difference=Decimal("0.00"),
                    change_fee=Decimal("0.00"),
                    cancellation_charge=Decimal("0.00"),
                    reason=f"Quote {quote_id} not active"
                )
            )
            return False

        new_version = self._price_quote_version(
            quote_id=quote_id,
            version_num=latest.version + 1,
            package_id=latest.package_id,
            departure_date=latest.departure_date,
            quote_date=latest.quote_date,
            room_preference=new_room_pref,
            odd_adult_option=latest.odd_adult_option,
            travellers=latest.travellers,
            status="CHANGED"
        )

        diff = new_version.total_sell - latest.total_sell
        self.quotes[quote_id].append(new_version)
        self.change_log.append(
            ChangeLogEntry(
                line_no=line_no,
                quote_id=quote_id,
                command="ROOM_CHANGE",
                status="APPLIED",
                old_total_sell=latest.total_sell,
                new_total_sell=new_version.total_sell,
                difference=diff,
                change_fee=Decimal("0.00"),
                cancellation_charge=Decimal("0.00"),
                reason=f"Room preference changed to {new_room_pref}"
            )
        )
        print(f"[{line_no}] ROOM_CHANGE for {quote_id} to {new_room_pref} (v{new_version.version}): New Sell Rs {fmt_money(new_version.total_sell)} (Diff: Rs {fmt_money(diff)})")
        return True

    def handle_cancel(self, line_no: int, args: List[str]) -> bool:
        quote_id, cancel_str = args
        cancel_date = parse_date(cancel_str)

        latest = self.get_latest_version(quote_id)
        if not latest or latest.status == "CANCELLED":
            self.change_log.append(
                ChangeLogEntry(
                    line_no=line_no,
                    quote_id=quote_id,
                    command="CANCEL",
                    status="REJECTED",
                    old_total_sell=Decimal("0.00"),
                    new_total_sell=Decimal("0.00"),
                    difference=Decimal("0.00"),
                    change_fee=Decimal("0.00"),
                    cancellation_charge=Decimal("0.00"),
                    reason=f"Quote {quote_id} already cancelled or not found"
                )
            )
            return False

        days_before = (latest.departure_date - cancel_date).days
        cancel_pct = get_cancellation_pct(days_before)
        cancel_charge = latest.total_sell * cancel_pct / Decimal("100")

        new_version = self._price_quote_version(
            quote_id=quote_id,
            version_num=latest.version + 1,
            package_id=latest.package_id,
            departure_date=latest.departure_date,
            quote_date=latest.quote_date,
            room_preference=latest.room_preference,
            odd_adult_option=latest.odd_adult_option,
            travellers=latest.travellers,
            status="CANCELLED"
        )

        diff = Decimal("0.00") - latest.total_sell
        self.quotes[quote_id].append(new_version)
        self.change_log.append(
            ChangeLogEntry(
                line_no=line_no,
                quote_id=quote_id,
                command="CANCEL",
                status="APPLIED",
                old_total_sell=latest.total_sell,
                new_total_sell=Decimal("0.00"),
                difference=diff,
                change_fee=Decimal("0.00"),
                cancellation_charge=cancel_charge,
                reason=f"Booking cancelled {days_before} days before departure ({cancel_pct}%)"
            )
        )
        print(f"[{line_no}] CANCEL {quote_id} (v{new_version.version}): Days before: {days_before}, Charge ({cancel_pct}%): Rs {fmt_money(cancel_charge)}")
        return True

    def handle_print_cost_sheet(self, quote_id: str) -> None:
        latest = self.get_latest_version(quote_id)
        if not latest:
            print(f"Quote {quote_id} not found.")
            return

        print(f"\n=======================================================")
        print(f" COST SHEET: {quote_id} (v{latest.version}) - Status: {latest.status}")
        print(f" Package: {latest.package_id} | Dep: {latest.departure_date} | Quoted: {latest.quote_date}")
        print(f" Room: {latest.room_preference} | Odd Adult: {latest.odd_adult_option}")
        print(f"=======================================================")
        print(f"{'Day':<4} {'Type':<10} {'ID':<10} {'Season':<10} {'Mult':<6} {'Unit (Rs)':<12} {'Units':<6} {'Cost (Rs)':<12}")
        print(f"-------------------------------------------------------------------------------")
        for row in latest.cost_sheet_rows:
            print(f"{row['day_no']:<4} {row['component_type']:<10} {row['component_id']:<10} {row['season']:<10} {row['multiplier']:<6} {row['unit_cost_inr']:<12} {row['units']:<6} {row['cost_inr']:<12}")
        print(f"-------------------------------------------------------------------------------")
        print(f" Total Net Cost       : Rs {fmt_money(latest.total_cost)}")
        print(f" Markup (+18%)        : Rs {fmt_money(latest.markup)}")
        print(f" Group Discount       : {latest.group_discount_pct}%")
        print(f" Early Bird Discount  : {latest.early_bird_pct}%")
        print(f" Applied Discount     : {latest.applied_discount_pct}% (Amount: Rs {fmt_money(latest.discount_amount)})")
        print(f" Sell Before GST      : Rs {fmt_money(latest.sell_before_gst)}")
        print(f" GST (+5%)            : Rs {fmt_money(latest.gst)}")
        print(f" Total Sell Price     : Rs {fmt_money(latest.total_sell)}")
        print(f"=======================================================\n")

    def handle_print_invoice(self, quote_id: str) -> None:
        latest = self.get_latest_version(quote_id)
        if not latest:
            print(f"Quote {quote_id} not found.")
            return

        if latest.status == "CANCELLED":
            last_change = next(
                (c for c in reversed(self.change_log) if c.quote_id == quote_id and c.command == "CANCEL"),
                None
            )
            charge = last_change.cancellation_charge if last_change else Decimal("0.00")
            orig_sell = last_change.old_total_sell if last_change else Decimal("0.00")
            print(f"\n=======================================================")
            print(f" CANCELLATION INVOICE: {quote_id} (Status: CANCELLED)")
            print(f" Package: {latest.package_id} | Departure Date: {latest.departure_date}")
            print(f" Original Sell Price  : Rs {fmt_money(orig_sell)}")
            print(f" Cancellation Charge  : Rs {fmt_money(charge)}")
            print(f" Amount Payable       : Rs {fmt_money(charge)}")
            print(f"=======================================================\n")
            return

        print(f"\n=========================================================================================")
        print(f" TRAVELLER INVOICE: {quote_id} (v{latest.version}) - Status: {latest.status}")
        print(f" Package: {latest.package_id} | Dep: {latest.departure_date} | Paying: {latest.paying_travellers} | FOC: {latest.foc_count}")
        print(f"=========================================================================================")
        print(f"{'Traveller':<10} {'Age':<4} {'Category':<12} {'Room':<10} {'Shared':<10} {'Act':<10} {'Meal':<10} {'ChildMind':<10} {'Pre-GST':<12} {'GST':<10} {'Per Person':<12}")
        print(f"-----------------------------------------------------------------------------------------")
        for inv in latest.traveller_invoices:
            d = inv.to_csv_dict()
            print(f"{d['traveller_id']:<10} {d['age_on_departure']:<4} {d['pricing_category']:<12} {d['room_cost']:<10} {d['shared_cost']:<10} {d['activity_cost']:<10} {d['meal_cost']:<10} {d['child_minding_cost']:<10} {d['sell_before_gst']:<12} {d['gst']:<10} {d['per_person_sell']:<12}")
        print(f"-----------------------------------------------------------------------------------------")
        print(f" Total Sell: Rs {fmt_money(latest.total_sell)} | Status: {latest.status}")
        print(f"=========================================================================================\n")

    def process_command(self, cmd: Any) -> bool:
        name = cmd.name.upper()
        line_no = cmd.line_no
        args = cmd.args

        try:
            if name == "QUOTE":
                return self.handle_quote(line_no, args)
            elif name == "ADD_TRAVELLER":
                return self.handle_add_traveller(line_no, args)
            elif name == "REMOVE_TRAVELLER":
                return self.handle_remove_traveller(line_no, args)
            elif name == "DATE_SHIFT":
                return self.handle_date_shift(line_no, args)
            elif name == "ROOM_CHANGE":
                return self.handle_room_change(line_no, args)
            elif name == "CANCEL":
                return self.handle_cancel(line_no, args)
            elif name == "PRINT_COST_SHEET":
                self.handle_print_cost_sheet(args[0])
                return True
            elif name == "PRINT_INVOICE":
                self.handle_print_invoice(args[0])
                return True
            else:
                print(f"[{line_no}] UNKNOWN COMMAND: {name}")
                return False
        except Exception as ex:
            print(f"[{line_no}] ERROR executing {name}: {ex}")
            return False

    def run_commands(self, commands: List[Any]) -> None:
        for cmd in commands:
            self.process_command(cmd)

    def export_cost_sheet(self, filepath: Path) -> None:
        fieldnames = [
            "quote_id", "version", "day_no", "night_date",
            "component_type", "component_id", "season", "multiplier",
            "unit_cost_inr", "units", "cost_inr"
        ]
        rows = []
        for q_id in sorted(self.quotes.keys()):
            for ver in self.quotes[q_id]:
                for r in ver.cost_sheet_rows:
                    rows.append(r)

        rows.sort(key=lambda r: (r["quote_id"], int(r["version"]), int(r["day_no"])))

        filepath.parent.mkdir(parents=True, exist_ok=True)
        with open(filepath, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)

    def export_quote_summary(self, filepath: Path) -> None:
        fieldnames = [
            "quote_id", "version", "package_id", "departure_date",
            "paying_travellers", "foc_count", "total_cost", "markup",
            "group_discount_pct", "early_bird_pct", "applied_discount_pct",
            "discount_amount", "sell_before_gst", "gst", "total_sell", "status"
        ]
        rows = []
        for q_id in sorted(self.quotes.keys()):
            for ver in self.quotes[q_id]:
                rows.append(ver.to_summary_dict())

        rows.sort(key=lambda r: (r["quote_id"], int(r["version"])))

        filepath.parent.mkdir(parents=True, exist_ok=True)
        with open(filepath, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)

    def export_traveller_invoice(self, filepath: Path) -> None:
        fieldnames = [
            "quote_id", "traveller_id", "age_on_departure", "pricing_category",
            "room_cost", "shared_cost", "activity_cost", "meal_cost",
            "child_minding_cost", "sell_before_gst", "gst", "per_person_sell"
        ]
        rows = []
        for q_id, versions in self.quotes.items():
            if not versions:
                continue
            latest = versions[-1]
            for inv in latest.traveller_invoices:
                rows.append(inv.to_csv_dict())

        rows.sort(key=lambda r: r["traveller_id"])

        filepath.parent.mkdir(parents=True, exist_ok=True)
        with open(filepath, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)

    def export_change_log(self, filepath: Path) -> None:
        fieldnames = [
            "line_no", "quote_id", "command", "status",
            "old_total_sell", "new_total_sell", "difference",
            "change_fee", "cancellation_charge", "reason"
        ]
        rows = [entry.to_csv_dict() for entry in self.change_log]
        rows.sort(key=lambda r: int(r["line_no"]))

        filepath.parent.mkdir(parents=True, exist_ok=True)
        with open(filepath, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)

    def export_all_outputs(self, target_dir: Path) -> None:
        self.export_cost_sheet(target_dir / "cost_sheet.csv")
        self.export_quote_summary(target_dir / "quote_summary.csv")
        self.export_traveller_invoice(target_dir / "traveller_invoice.csv")
        self.export_change_log(target_dir / "change_log.csv")
        print(f"\nAll 4 output CSV files successfully exported to {target_dir}")
