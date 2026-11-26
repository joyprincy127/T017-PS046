# Decision Log — PS-046 (Team T017)

This log records the implementation/design decisions reflected in the current project and its supplied requirements. It is not a chronological meeting transcript.

| ID | Decision | Rationale / requirement addressed | Implementation area |
|---|---|---|---|
| DL-01 | Deliver the solution as a Python command-line application driven by CSV inputs and a pipe-separated command file. | The project is a backend pricing engine; deterministic batch processing keeps evaluation reproducible and avoids unnecessary UI scope. | `main.py`, `src/command_parser.py`, `data/` |
| DL-02 | Use Python's standard-library `csv` module for input and output. | The provided data pack and required reports are CSV; this keeps setup lightweight and portable. | `src/data_loader.py`, output/export code |
| DL-03 | Use `Decimal` for financial calculations and explicit currency rounding. | Avoid binary floating-point inaccuracies in room costs, discounts, taxes, and invoice reconciliation. | `src/pricing_engine.py`, `src/cost_engine.py` |
| DL-04 | Apply hotel seasonality by the date of each overnight stay, rather than one multiplier for the entire trip. | An itinerary can cross season boundaries; each night must use its own season rate. | `src/itinerary_engine.py`, season calendar data |
| DL-05 | Keep accommodation allocation and itinerary costing in separate modules. | Rooming rules and itinerary component rules are different responsibilities and are easier to test independently. | `src/room_allocator.py`, `src/itinerary_engine.py` |
| DL-06 | Determine child pricing category using age on departure, while checking service eligibility using age on the activity/service date. | The supplied edge case includes a child turning 12 during the trip; departure invoice category and actual service eligibility must not be conflated. | `src/itinerary_engine.py`, `src/cost_engine.py` |
| DL-07 | Charge child-minding only when the required parent participation conditions are met for an age-restricted activity. | This implements the stated child supervision rule and avoids charging when the participation condition is not satisfied. | Itinerary/activity eligibility logic |
| DL-08 | Apply group and early-bird discounts additively, subject to the specified combined maximum. | Implements the commercial policy while preventing the combined discount from exceeding the cap. | `src/pricing_engine.py` |
| DL-09 | Treat a qualifying group leader as free of charge, and redistribute their incurred costs among paying travellers. | The FOC benefit must not leave supplier costs unrecovered; invoices must reconcile to the quote total. | `src/cost_engine.py` |
| DL-10 | Lock the foreign-exchange rate at quote creation, including the specified buffer, for subsequent quote revisions. | Provides consistent repricing and protects against an unrelated daily rate change during quote lifecycle operations. | Quote state and costing logic |
| DL-11 | Preserve quote versions and record lifecycle changes in an audit log. | Traveller, date, room, and cancellation changes must be traceable, with revised prices and applicable fees. | `src/quote_manager.py`, `change_log.csv` |
| DL-12 | Validate key rules with automated `unittest` cases and the supplied planted scenarios. | Regression tests make edge cases repeatable and provide a quick verification step before submission. | `tests/test_engine.py` |

## Verification note

The project package includes the automated test suite. Run it from the repository root using:

```powershell
python -m unittest tests.test_engine -v
```

Record any future change to a business rule, output schema, or architectural choice as a new entry in this file.
