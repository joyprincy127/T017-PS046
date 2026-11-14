# PS-046 – Tour Package Pricing and Itinerary Cost Engine with Seasonality, Group Discounts and Child Policy — Sample Data Pack

Prepared by 10 SECONDS for Team T017.

## Files

| File | What it holds | Row count |
|---|---|---|
| `hotels.csv` | 25 hotels with LEAN-season twin-room cost per night (standard and deluxe) | 25 data rows |
| `activities.csv` | 12 activities with per-person cost and minimum age | 12 data rows |
| `vehicles.csv` | 4 vehicle types with pax band and day cost | 4 data rows |
| `meals.csv` | Meal plans with adult / child per-day cost | 3 data rows |
| `rate_parameters.csv` | Guide rates, supplements, child-minding, markup, GST, FX buffer | 10 data rows |
| `season_calendar.csv` | Season bands with hotel multipliers | 4 data rows |
| `fx_rates.csv` | Daily USD->INR reference rates | 212 data rows |
| `packages.csv` | 3 packages of 4 to 7 days | 3 data rows |
| `package_itinerary.csv` | Day-by-day components per package | 65 data rows |
| `travellers.csv` | Travellers per quote with DOB, parents and group-leader flag | 218 data rows |
| `activity_optouts.csv` | Travellers who skip a specific activity by choice | 7 data rows |
| `commands.txt` | 30 quotes, changes, 5 cancellations and print requests | 106 command lines (excluding comments) |

Row numbers quoted below are 1-based data-row numbers (the header is row 0). Line numbers for `commands.txt` are physical line numbers including comment lines.

## Column reference

Conventions: dates `YYYY-MM-DD`; timestamps `YYYY-MM-DD HH:MM:SS` (24h, IST, no timezone suffix); money in Rs as plain decimals with 2 places (no commas, no symbol); percentages as plain numbers (12.5 means 12.5%); booleans `true`/`false`; IDs uppercase with a fixed prefix.

### `hotels.csv`

| Column | Type | Units / format | Allowed values | Notes |
|---|---|---|---|---|
| `hotel_id` | string | HTL-nn | — | primary key |
| `hotel_name` | string | — | — | — |
| `city` | string | — | — | — |
| `star_rating` | int | — | 3-5 | — |
| `standard_twin_room_cost` | decimal | currency column, per room per night | — | LEAN base; multiply by season of the night date |
| `deluxe_twin_room_cost` | decimal | currency column, per room per night | — | used when room_preference = DELUXE |
| `currency` | enum | — | INR, USD | USD converts at quote-date rate + 2% |

### `activities.csv`

| Column | Type | Units / format | Allowed values | Notes |
|---|---|---|---|---|
| `activity_id` | string | ACT-nn | — | — |
| `activity_name` | string | — | — | — |
| `city` | string | — | — | — |
| `cost_per_person` | decimal | currency column | — | not seasonal |
| `currency` | enum | — | INR, USD | — |
| `min_age` | int | years | 0-18 | children below this age skip the activity and are not charged |

### `vehicles.csv`

| Column | Type | Units / format | Allowed values | Notes |
|---|---|---|---|---|
| `vehicle_type` | enum | — | SEDAN, INNOVA, TEMPO, MINIBUS | — |
| `min_pax` | int | seated pax | — | children under 5 are not seated |
| `max_pax` | int | seated pax | — | inclusive |
| `cost_per_day` | decimal | Rs | — | shared equally across seated travellers |
| `currency` | enum | — | INR | — |

### `meals.csv`

| Column | Type | Units / format | Allowed values | Notes |
|---|---|---|---|---|
| `meal_id` | string | MEAL-nn | — | — |
| `description` | string | — | — | — |
| `adult_cost_per_day` | decimal | currency column | — | age 12+ |
| `child_5_11_cost_per_day` | decimal | currency column | — | actual cost (not a shared component) |
| `child_under_5_cost_per_day` | decimal | currency column | — | — |
| `currency` | enum | — | INR, USD | — |

### `rate_parameters.csv`

| Column | Type | Units / format | Allowed values | Notes |
|---|---|---|---|---|
| `param` | string | — | — | key |
| `value` | decimal | see unit | — | percent values are plain numbers |
| `unit` | string | — | per_day, per_activity, per_traveller, percent | — |
| `notes` | string | — | — | — |

### `season_calendar.csv`

| Column | Type | Units / format | Allowed values | Notes |
|---|---|---|---|---|
| `from_date` | date | — | — | inclusive |
| `to_date` | date | — | — | inclusive |
| `season` | enum | — | LEAN, SHOULDER, PEAK | — |
| `hotel_multiplier` | decimal | — | 1.0, 1.2, 1.5 | applies to hotel nights only, by night date |

### `fx_rates.csv`

| Column | Type | Units / format | Allowed values | Notes |
|---|---|---|---|---|
| `rate_date` | date | — | — | one row per day |
| `currency` | enum | — | USD | — |
| `inr_per_unit` | decimal | Rs per USD | — | use the row for the QUOTE date, then add 2% |

### `packages.csv`

| Column | Type | Units / format | Allowed values | Notes |
|---|---|---|---|---|
| `package_id` | string | PKG-nn | — | — |
| `package_name` | string | — | — | — |
| `days` | int | — | 4-7 | — |
| `nights` | int | — | — | days - 1 |
| `region` | string | — | — | — |

### `package_itinerary.csv`

| Column | Type | Units / format | Allowed values | Notes |
|---|---|---|---|---|
| `package_id` | string | — | packages.csv | — |
| `day_no` | int | — | 1..days | day 1 = departure date |
| `component_type` | enum | — | HOTEL, VEHICLE, GUIDE, MEAL, ACTIVITY | — |
| `component_id` | string | — | hotels.csv / activities.csv / meals.csv id, AUTO, GUIDE | VEHICLE rows say AUTO = size by seated pax |
| `notes` | string | — | — | may be blank |

### `travellers.csv`

| Column | Type | Units / format | Allowed values | Notes |
|---|---|---|---|---|
| `traveller_id` | string | TRV-nnnn | — | primary key |
| `quote_id` | string | Q-nnn | — | quote this traveller belongs to |
| `full_name` | string | — | — | — |
| `gender` | enum | — | M, F | — |
| `date_of_birth` | date | — | — | age is computed from DOB; under 12 = child |
| `parent_1_id` | string | — | travellers.csv | children only; may be blank |
| `parent_2_id` | string | — | travellers.csv | children only; both parents needed for child-minding; may be blank |
| `group_leader` | bool | — | — | if the group earns an FOC, this adult is the FOC traveller |
| `on_initial_quote` | bool | — | — | false = joins later via ADD_TRAVELLER |

### `activity_optouts.csv`

| Column | Type | Units / format | Allowed values | Notes |
|---|---|---|---|---|
| `quote_id` | string | — | — | — |
| `traveller_id` | string | — | travellers.csv | — |
| `activity_id` | string | — | activities.csv | traveller is not charged and is not 'on' the activity |
| `reason` | string | — | — | free text |

## Command file format

`commands.txt` holds one command per line in the form `COMMAND_NAME|arg1|arg2|...`. Commands must be processed strictly in file order. Lines starting with `#` are comments and blank lines are ignored. Empty optional arguments are written as nothing between the pipes. Every command used in this pack:

| Command | Arguments (in order) | Meaning |
|---|---|---|
| `QUOTE` | `quote_id|package_id|departure_date|quote_date|room_preference|odd_adult_option` | Create and price a quote for all travellers of that quote with on_initial_quote=true. room_preference STANDARD or DELUXE; odd_adult_option SINGLE (odd adult in a single room, pays the supplement) or TRIPLE (odd adult joins a twin as third adult at 75%). A QUOTE for an existing quote_id is rejected |
| `ADD_TRAVELLER` | `quote_id|traveller_id|change_date` | Add the traveller and re-price the whole group; invoice the difference |
| `REMOVE_TRAVELLER` | `quote_id|traveller_id|change_date` | Remove the traveller (cancellation charge for them by days to departure) and re-price the rest at the new group size |
| `DATE_SHIFT` | `quote_id|new_departure_date|change_date` | <= 7 days: Rs 1,000 per traveller + season difference; > 7 days: cancellation + new booking |
| `ROOM_CHANGE` | `quote_id|new_room_preference|change_date` | Switch STANDARD/DELUXE and re-price (FX stays at the quote-date rate) |
| `CANCEL` | `quote_id|cancel_date` | Cancel the whole booking; charge by days before departure |
| `PRINT_COST_SHEET` | `quote_id` | Print cost vs sell for the latest version of the quote |
| `PRINT_INVOICE` | `quote_id` | Print the traveller-wise invoice (or the cancellation invoice) |

## Planted scenarios

Every edge case in the brief, mapped to the exact record where it occurs, followed by extra traps.

- **EC-01 Group of 3 adults and 1 child aged 4 (rooming and vehicle count)**
  - Q-010 (PKG-01): 3 adults + child TRV-0062 aged 4 (DOB 2022-01-20) — 2 adults twin, odd adult single supplement, child under 5 shares free; seated pax = 3 -> SEDAN; child also below ACT-01 min age 5 with both parents on it -> child-minding Rs 500 — `commands.txt line 13 (QUOTE Q-010); travellers.csv TRV-0062 (row 62)`
- **EC-02 Exactly 15 paying adults (FOC eligibility)**
  - Q-027: 16 adults, leader TRV-0186 flagged group_leader — exactly 15 paying adults + 1 FOC; FOC cost spread across the 15 — `commands.txt line 41 (QUOTE Q-027)`
- **EC-03 Group discount 10% plus early bird 8% (cap at 15%)**
  - Q-019: 12 paying adults (10% tier) quoted 2026-11-12, 90 days before departure 2027-02-10 (early bird 8%) — combined 18% capped at 15% — `commands.txt line 30 (QUOTE Q-019)`
- **EC-04 Child turning 12 on day 3 of the tour**
  - Q-009 (PKG-02, departs 2026-11-07): child TRV-0057 DOB 2014-11-09 turns 12 on 2026-11-09 = day 3 of the tour — `commands.txt line 12 (QUOTE Q-009); travellers.csv TRV-0057 (row 57)`
- **EC-05 Itinerary spanning SHOULDER into PEAK on the final night**
  - Q-017 (PKG-01, departs 2026-12-12): nights 12, 13, 14 Dec are SHOULDER (x1.2), final night 15 Dec is PEAK (x1.5) — price each night by its own date — `commands.txt line 27 (QUOTE Q-017)`
- **EC-06 Removing one traveller dropping the group from 10 to 9**
  - Q-026: 10 paying adults (10% tier); REMOVE_TRAVELLER TRV-0185 30 days out drops it to 9 -> 5% tier; difference invoiced to the remaining 9 (plus cancellation charge for the removed traveller) — `commands.txt line 40 (QUOTE Q-026); commands.txt line 45`
- **EC-07 Booking exactly 60 days before departure**
  - Q-008: QUOTE dated 2026-10-05, departure 2026-12-04 = exactly 60 days -> early bird applies (60+) — `commands.txt line 11 (QUOTE Q-008)`
- **EC-08 Per-person sell price ending in Rs 0 after GST (rounding no-op)**
  - Q-024: 2 adults, PKG-01 STANDARD, all nights LEAN, no discount — per-person cost Rs 30,000.00 (hotels 8,050 + vehicle 8,750 + guide 5,000 + meals 3,200 + activities 5,000) -> +18% markup = 35,400.00 -> +5% GST = 37,170.00, already a multiple of Rs 10 (round-up is a no-op) — `commands.txt line 38 (QUOTE Q-024)`
- **Extra traps (not in the brief, but realistic):**
  - Q-015: child TRV-0100 turns exactly 5 on the departure date 2026-11-26 — falls in the 5–11 band (extra bed 40%, 50% of shared components), not under-5 — `commands.txt line 23 (QUOTE Q-015)`
  - Q-016: 5 adults with odd_adult_option TRIPLE (third adult in a room at 75%); a later ADD_TRAVELLER makes it 6 paying -> enters the 5% group tier and seated pax 6 stays INNOVA — `commands.txt line 25 (QUOTE Q-016)`
  - Activity opt-out: one parent opts out of an age-restricted activity, so the skipped child does NOT attract child-minding (both parents must be on it) — `activity_optouts.csv row 1 (Q-003 / TRV-0017 / ACT-06)`
  - Q-025 (Dubai, USD components): quoted 2026-11-28 at USD 84.76 (+2% buffer); ROOM_CHANGE to DELUXE on 2027-01-02 when fx_rates shows 84.78 — keep the quote-date rate — `commands.txt line 39 (QUOTE Q-025); commands.txt line 48`
  - Q-001: DATE_SHIFT by exactly 7 days (2026-10-23 -> 2026-10-30) — Rs 1,000 per traveller plus any season difference, not a cancellation — `commands.txt line 9`
  - Q-002: DATE_SHIFT by 8 days (2026-11-29 -> 2026-12-07) on 2026-11-07 — beyond 7 days = cancellation (22 days out -> 50%) plus a new booking — `commands.txt line 28`
  - REMOVE_TRAVELLER on Q-007 names TRV-0063, who belongs to Q-011 — reject, no re-price — `commands.txt line 14`
  - CANCEL exactly 45 days before departure (Q-021) sits on the 45–30 band (25%), and exactly 15 days (Q-013) on the 29–15 band (50%); the others are 50 days (10%), 30 days (25%) and 10 days (100%) — `commands.txt line 43; commands.txt line 21`
  - Duplicate QUOTE for an existing id Q-019 — reject; the original quote stands — `commands.txt line 32`

## What is NOT in this pack

Expected outputs are not provided for this set. Validate your engine with your own test suite against the rules in your brief (BR-01 … BR-nn). A separate hidden input set with the same schema will be used at final evaluation; outputs are compared field-for-field, so follow the column formats above exactly in your own output.

## Output format expected at evaluation

Produce these CSV files (header row, same conventions as above, rows sorted as stated). Where the brief is silent on a format detail the choice below is binding for evaluation.

### `cost_sheet.csv`

One row per costed component per quote version, in quote_id, version, day_no order. Costs in Rs after FX conversion.

Columns, in order: `quote_id`, `version`, `day_no`, `night_date`, `component_type`, `component_id`, `season`, `multiplier`, `unit_cost_inr`, `units`, `cost_inr`

### `quote_summary.csv`

One row per quote version (version 1 = QUOTE, +1 per accepted change).

Columns, in order: `quote_id`, `version`, `package_id`, `departure_date`, `paying_travellers`, `foc_count`, `total_cost`, `markup`, `group_discount_pct`, `early_bird_pct`, `applied_discount_pct`, `discount_amount`, `sell_before_gst`, `gst`, `total_sell`, `status`

### `traveller_invoice.csv`

One row per traveller of the latest version, in traveller_id order.

Columns, in order: `quote_id`, `traveller_id`, `age_on_departure`, `pricing_category`, `room_cost`, `shared_cost`, `activity_cost`, `meal_cost`, `child_minding_cost`, `sell_before_gst`, `gst`, `per_person_sell`

### `change_log.csv`

One row per change or cancellation command, in file order; rejected commands appear with status REJECTED.

Columns, in order: `line_no`, `quote_id`, `command`, `status`, `old_total_sell`, `new_total_sell`, `difference`, `change_fee`, `cancellation_charge`, `reason`

Binding choices: `pricing_category` is ADULT, CHILD_5_11, CHILD_UNDER_5 or FOC; `status` in quote_summary is QUOTED, CHANGED or CANCELLED; change_log `status` is APPLIED or REJECTED; `per_person_sell` is the post-GST price rounded up to the next Rs 10; age is in completed years on the departure date.
