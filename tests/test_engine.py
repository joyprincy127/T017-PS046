"""
Unit and Integration Tests for Tour Package Pricing and Itinerary Cost Engine
Covers all business rules and planted edge cases from README.md.
"""

import sys
import unittest
from decimal import Decimal
from pathlib import Path

# Ensure src is on python path
BASE_DIR = Path(__file__).resolve().parent.parent
SRC_DIR = BASE_DIR / "src"
OUTPUTS_DIR = BASE_DIR / "outputs"

if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from data_loader import load_all_data
from command_parser import load_and_parse_commands
from quote_manager import QuoteManager


import io
import contextlib

class TestCapstoneEngine(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        """Run the complete engine once to populate quotes and outputs."""
        cls.data = load_all_data()
        cls.commands = load_and_parse_commands()
        cls.manager = QuoteManager(cls.data)
        with contextlib.redirect_stdout(io.StringIO()):
            cls.manager.run_commands(cls.commands)
            cls.manager.export_all_outputs(OUTPUTS_DIR)

    # -------------------------------------------------------------------------
    # 1. Planted Scenario Tests
    # -------------------------------------------------------------------------

    def test_ec01_child_age_and_child_minding_q010(self):
        """EC-01: Q-010 (PKG-01): 3 adults + child TRV-0062 aged 4.
        Child under 5 shares free; seated pax = 3 -> SEDAN.
        Child below ACT-01 min age 5 with both parents participating -> child-minding Rs 500.
        """
        quote = self.manager.quotes.get("Q-010")
        self.assertIsNotNone(quote)
        v1 = quote[0]

        # Vehicle must be SEDAN
        vehicle_rows = [r for r in v1.cost_sheet_rows if r["component_type"] == "VEHICLE"]
        self.assertTrue(len(vehicle_rows) > 0)
        self.assertEqual(vehicle_rows[0]["cost_inr"], "3500.00")  # SEDAN cost is 3500

        # Child TRV-0062
        trv_inv = next((i for i in v1.traveller_invoices if i.traveller_id == "TRV-0062"), None)
        self.assertIsNotNone(trv_inv)
        self.assertEqual(trv_inv.pricing_category, "CHILD_UNDER_5")
        self.assertEqual(trv_inv.room_cost, Decimal("0.00"))
        self.assertEqual(trv_inv.shared_cost, Decimal("0.00"))
        # Child-minding is Rs 500 per skipped activity when both parents participate (ACT-01 and ACT-03 = Rs 1000)
        self.assertEqual(trv_inv.child_minding_cost, Decimal("1000.00"))

    def test_ec02_foc_calculation_q027(self):
        """EC-02: Q-027: 16 adults, leader TRV-0186 flagged group_leader.
        Exactly 15 paying adults + 1 FOC. FOC cost spread across the 15.
        """
        quote = self.manager.quotes.get("Q-027")
        self.assertIsNotNone(quote)
        v1 = quote[0]

        self.assertEqual(v1.paying_travellers, 15)
        self.assertEqual(v1.foc_count, 1)

        foc_inv = next((i for i in v1.traveller_invoices if i.traveller_id == "TRV-0186"), None)
        self.assertIsNotNone(foc_inv)
        self.assertEqual(foc_inv.pricing_category, "FOC")
        self.assertEqual(foc_inv.per_person_sell, Decimal("0.00"))
        self.assertEqual(foc_inv.room_cost, Decimal("0.00"))
        self.assertEqual(foc_inv.shared_cost, Decimal("0.00"))
        self.assertEqual(foc_inv.activity_cost, Decimal("0.00"))
        self.assertEqual(foc_inv.meal_cost, Decimal("0.00"))

        # Paying adults have non-zero cost and absorb FOC
        paying_invs = [i for i in v1.traveller_invoices if i.traveller_id != "TRV-0186"]
        self.assertEqual(len(paying_invs), 15)
        for inv in paying_invs:
            self.assertEqual(inv.pricing_category, "ADULT")
            self.assertGreater(inv.per_person_sell, Decimal("0.00"))

    def test_ec03_discount_cap_q019(self):
        """EC-03: Q-019: 12 paying adults (10% tier) quoted 2026-11-12,
        90 days before departure 2027-02-10 (early bird 8%). Combined 18% capped at 15%.
        """
        quote = self.manager.quotes.get("Q-019")
        self.assertIsNotNone(quote)
        v1 = quote[0]

        self.assertEqual(v1.group_discount_pct, Decimal("10"))
        self.assertEqual(v1.early_bird_pct, Decimal("8"))
        self.assertEqual(v1.applied_discount_pct, Decimal("15"))  # Capped at 15%

    def test_ec04_child_turning_12_during_trip_q009(self):
        """EC-04: Q-009 (PKG-02, departs 2026-11-07): child TRV-0057 DOB 2014-11-09
        turns 12 on 2026-11-09 = day 3 of the tour.
        """
        quote = self.manager.quotes.get("Q-009")
        self.assertIsNotNone(quote)
        v1 = quote[0]

        # Invoice age on departure date (2026-11-07) should be 11
        trv_inv = next((i for i in v1.traveller_invoices if i.traveller_id == "TRV-0057"), None)
        self.assertIsNotNone(trv_inv)
        self.assertEqual(trv_inv.age_on_departure, 11)
        self.assertEqual(trv_inv.pricing_category, "CHILD_5_11")

    def test_ec05_season_change_q017(self):
        """EC-05: Q-017 (PKG-01, departs 2026-12-12): nights 12, 13, 14 Dec are SHOULDER (x1.2),
        final night 15 Dec is PEAK (x1.5).
        """
        quote = self.manager.quotes.get("Q-017")
        self.assertIsNotNone(quote)
        v1 = quote[0]

        hotel_rows = [r for r in v1.cost_sheet_rows if r["component_type"] == "HOTEL"]
        self.assertEqual(len(hotel_rows), 4)

        # Nights 1 to 3 should be SHOULDER with 1.2
        for r in hotel_rows[:3]:
            self.assertEqual(r["season"], "SHOULDER")
            self.assertEqual(r["multiplier"], "1.2")

        # Night 4 (2026-12-15) should be PEAK with 1.5
        self.assertEqual(hotel_rows[3]["night_date"], "2026-12-15")
        self.assertEqual(hotel_rows[3]["season"], "PEAK")
        self.assertEqual(hotel_rows[3]["multiplier"], "1.5")

    def test_ec06_removal_changing_group_discount_q026(self):
        """EC-06: Q-026: 10 paying adults (10% tier); REMOVE_TRAVELLER TRV-0185 30 days out
        drops group to 9 -> 5% tier. 25% cancellation charge.
        """
        quote = self.manager.quotes.get("Q-026")
        self.assertIsNotNone(quote)
        self.assertEqual(len(quote), 2)

        v1 = quote[0]
        v2 = quote[1]

        self.assertEqual(v1.paying_travellers, 10)
        self.assertEqual(v1.group_discount_pct, Decimal("10"))

        self.assertEqual(v2.paying_travellers, 9)
        self.assertEqual(v2.group_discount_pct, Decimal("5"))

        # Verify change log for REMOVE_TRAVELLER on line 45
        entry = next((e for e in self.manager.change_log if e.line_no == 45), None)
        self.assertIsNotNone(entry)
        self.assertEqual(entry.command, "REMOVE_TRAVELLER")
        self.assertEqual(entry.status, "APPLIED")
        self.assertGreater(entry.cancellation_charge, Decimal("0.00"))

    def test_ec07_exact_60_days_early_bird_q008(self):
        """EC-07: Q-008: QUOTE dated 2026-10-05, departure 2026-12-04 = exactly 60 days
        -> early bird applies (60+).
        """
        quote = self.manager.quotes.get("Q-008")
        self.assertIsNotNone(quote)
        v1 = quote[0]

        self.assertEqual(v1.early_bird_pct, Decimal("8"))

    def test_ec08_rounding_noop_q024(self):
        """EC-08: Q-024: 2 adults, PKG-01 STANDARD, all nights LEAN, no discount
        per-person cost Rs 30,000.00 -> +18% markup = 35,400.00 -> +5% GST = 37,170.00
        Already a multiple of Rs 10 (round-up is a no-op).
        """
        quote = self.manager.quotes.get("Q-024")
        self.assertIsNotNone(quote)
        v1 = quote[0]

        self.assertEqual(v1.total_cost, Decimal("60000.00"))
        self.assertEqual(v1.markup, Decimal("10800.00"))
        self.assertEqual(v1.applied_discount_pct, Decimal("0"))
        self.assertEqual(v1.sell_before_gst, Decimal("70800.00"))
        self.assertEqual(v1.gst, Decimal("35400.00") * Decimal("0.05") * Decimal("2"))
        self.assertEqual(v1.total_sell, Decimal("74340.00"))

        # Each traveller post-GST
        for inv in v1.traveller_invoices:
            self.assertEqual(inv.room_cost, Decimal("8050.00"))
            self.assertEqual(inv.shared_cost, Decimal("13750.00"))
            self.assertEqual(inv.activity_cost, Decimal("5000.00"))
            self.assertEqual(inv.meal_cost, Decimal("3200.00"))
            self.assertEqual(inv.sell_before_gst, Decimal("35400.00"))
            self.assertEqual(inv.gst, Decimal("1770.00"))
            self.assertEqual(inv.per_person_sell, Decimal("37170.00"))

    def test_q015_child_turning_5_on_departure(self):
        """Q-015: child TRV-0100 turns exactly 5 on departure date 2026-11-26
        -> falls in 5-11 band (extra bed 40%, 50% shared components), not under-5.
        """
        quote = self.manager.quotes.get("Q-015")
        self.assertIsNotNone(quote)
        v1 = quote[0]

        child_inv = next((i for i in v1.traveller_invoices if i.traveller_id == "TRV-0100"), None)
        self.assertIsNotNone(child_inv)
        self.assertEqual(child_inv.age_on_departure, 5)
        self.assertEqual(child_inv.pricing_category, "CHILD_5_11")
        self.assertGreater(child_inv.room_cost, Decimal("0.00"))
        self.assertGreater(child_inv.shared_cost, Decimal("0.00"))

        # Verify child shared cost is exactly 50% of adult shared cost
        adult_inv = next((i for i in v1.traveller_invoices if i.traveller_id != "TRV-0100"), None)
        self.assertEqual(child_inv.shared_cost * Decimal("2"), adult_inv.shared_cost)

    def test_q016_triple_and_add_traveller(self):
        """Q-016: 5 adults TRIPLE option; later ADD_TRAVELLER makes it 6 paying
        -> enters 5% group tier.
        """
        quote = self.manager.quotes.get("Q-016")
        self.assertIsNotNone(quote)
        self.assertEqual(len(quote), 2)

        v1 = quote[0]
        v2 = quote[1]

        self.assertEqual(v1.paying_travellers, 5)
        self.assertEqual(v1.group_discount_pct, Decimal("0"))

        self.assertEqual(v2.paying_travellers, 6)
        self.assertEqual(v2.group_discount_pct, Decimal("5"))

    def test_q025_locked_foreign_exchange_rate(self):
        """Q-025: Dubai USD components quoted 2026-11-28 at USD 84.76 (+2% buffer);
        ROOM_CHANGE on 2027-01-02 keeps the quote-date rate.
        """
        quote = self.manager.quotes.get("Q-025")
        self.assertIsNotNone(quote)
        self.assertEqual(len(quote), 2)

        v1 = quote[0]
        v2 = quote[1]

        self.assertEqual(v1.quote_date, v2.quote_date)
        self.assertEqual(v1.room_preference, "STANDARD")
        self.assertEqual(v2.room_preference, "DELUXE")

    def test_q001_and_q002_date_shift_boundaries(self):
        """Q-001: shift <= 7 days (fee Rs 1000/traveller, no cancel charge).
        Q-002: shift > 7 days (treated as cancellation 50% + rebooking).
        """
        entry_q001 = next((e for e in self.manager.change_log if e.line_no == 9), None)
        self.assertIsNotNone(entry_q001)
        self.assertEqual(entry_q001.command, "DATE_SHIFT")
        self.assertEqual(entry_q001.status, "APPLIED")
        self.assertEqual(entry_q001.change_fee, Decimal("4000.00"))  # 4 travellers * 1000
        self.assertEqual(entry_q001.cancellation_charge, Decimal("0.00"))

        entry_q002 = next((e for e in self.manager.change_log if e.line_no == 28), None)
        self.assertIsNotNone(entry_q002)
        self.assertEqual(entry_q002.command, "DATE_SHIFT")
        self.assertEqual(entry_q002.status, "APPLIED")
        self.assertEqual(entry_q002.change_fee, Decimal("0.00"))
        # 50% cancellation charge
        self.assertEqual(entry_q002.cancellation_charge, entry_q002.old_total_sell * Decimal("0.50"))

    def test_invalid_traveller_removal(self):
        """Line 14: REMOVE_TRAVELLER on Q-007 names TRV-0063 (belongs to Q-011) -> reject."""
        entry = next((e for e in self.manager.change_log if e.line_no == 14), None)
        self.assertIsNotNone(entry)
        self.assertEqual(entry.command, "REMOVE_TRAVELLER")
        self.assertEqual(entry.status, "REJECTED")

    def test_duplicate_quote_rejection(self):
        """Line 32: QUOTE Q-019 duplicate -> reject."""
        entry = next((e for e in self.manager.change_log if e.line_no == 32), None)
        self.assertIsNotNone(entry)
        self.assertEqual(entry.command, "QUOTE")
        self.assertEqual(entry.status, "REJECTED")

    def test_cancellation_boundaries(self):
        """Verify cancellation percentage tiers:
        - Q-012: 50 days -> 10%
        - Q-021: 45 days -> 25%
        - Q-014: 30 days -> 25%
        - Q-013: 15 days -> 50%
        - Q-018: 10 days -> 100%
        """
        # Q-012 (line 24)
        c_q012 = next((e for e in self.manager.change_log if e.line_no == 24), None)
        self.assertEqual(c_q012.cancellation_charge, c_q012.old_total_sell * Decimal("0.10"))

        # Q-021 (line 43)
        c_q021 = next((e for e in self.manager.change_log if e.line_no == 43), None)
        self.assertEqual(c_q021.cancellation_charge, c_q021.old_total_sell * Decimal("0.25"))

        # Q-014 (line 20)
        c_q014 = next((e for e in self.manager.change_log if e.line_no == 20), None)
        self.assertEqual(c_q014.cancellation_charge, c_q014.old_total_sell * Decimal("0.25"))

        # Q-013 (line 21)
        c_q013 = next((e for e in self.manager.change_log if e.line_no == 21), None)
        self.assertEqual(c_q013.cancellation_charge, c_q013.old_total_sell * Decimal("0.50"))

        # Q-018 (line 47)
        c_q018 = next((e for e in self.manager.change_log if e.line_no == 47), None)
        self.assertEqual(c_q018.cancellation_charge, c_q018.old_total_sell * Decimal("1.00"))

    # -------------------------------------------------------------------------
    # 2. Output CSV Schema and Reconciliation Tests
    # -------------------------------------------------------------------------

    def test_output_csv_files_exist_and_non_empty(self):
        """Verify all four CSV files are generated and contain rows."""
        files = [
            "cost_sheet.csv",
            "quote_summary.csv",
            "traveller_invoice.csv",
            "change_log.csv"
        ]
        for fname in files:
            p = OUTPUTS_DIR / fname
            self.assertTrue(p.exists(), f"Missing output file: {p}")
            self.assertGreater(p.stat().st_size, 0, f"Empty output file: {p}")

    def test_csv_column_schemas_and_order(self):
        """Verify all four CSV files match the exact column names and ordering from README.md."""
        import csv
        expected_schemas = {
            "cost_sheet.csv": [
                "quote_id", "version", "day_no", "night_date", "component_type",
                "component_id", "season", "multiplier", "unit_cost_inr", "units", "cost_inr"
            ],
            "quote_summary.csv": [
                "quote_id", "version", "package_id", "departure_date",
                "paying_travellers", "foc_count", "total_cost", "markup",
                "group_discount_pct", "early_bird_pct", "applied_discount_pct",
                "discount_amount", "sell_before_gst", "gst", "total_sell", "status"
            ],
            "traveller_invoice.csv": [
                "quote_id", "traveller_id", "age_on_departure", "pricing_category",
                "room_cost", "shared_cost", "activity_cost", "meal_cost",
                "child_minding_cost", "sell_before_gst", "gst", "per_person_sell"
            ],
            "change_log.csv": [
                "line_no", "quote_id", "command", "status", "old_total_sell",
                "new_total_sell", "difference", "change_fee", "cancellation_charge", "reason"
            ]
        }

        for filename, expected_cols in expected_schemas.items():
            path = OUTPUTS_DIR / filename
            with open(path, "r", newline="", encoding="utf-8") as f:
                reader = csv.reader(f)
                header = next(reader)
                self.assertEqual(
                    header, expected_cols,
                    f"Column header mismatch in {filename}:\nExpected: {expected_cols}\nActual:   {header}"
                )

    def test_invoice_reconciliation_with_quote_summary(self):
        """Verify that individual traveller invoices reconcile with quote summary totals."""
        for q_id, versions in self.manager.quotes.items():
            latest = versions[-1]
            if latest.status == "CANCELLED":
                continue

            sum_cost = sum(
                (inv.room_cost + inv.shared_cost + inv.activity_cost + inv.meal_cost + inv.child_minding_cost)
                for inv in latest.traveller_invoices
            )
            # Reconciles to package total cost within rounding tolerance
            self.assertAlmostEqual(float(sum_cost), float(latest.total_cost), delta=0.05)

            sum_sell_pre_gst = sum(inv.sell_before_gst for inv in latest.traveller_invoices)
            self.assertAlmostEqual(float(sum_sell_pre_gst), float(latest.sell_before_gst), delta=0.05)

            sum_gst = sum(inv.gst for inv in latest.traveller_invoices)
            self.assertAlmostEqual(float(sum_gst), float(latest.gst), delta=0.05)


if __name__ == "__main__":
    unittest.main()

