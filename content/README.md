# Content files: what each one controls

These six files hold the rules, numbers and words the app uses. You can change them without touching any code. The app re-reads a file whenever it changes, so an edit shows on the next page load, with no restart.

| File | What it controls | Where you see it |
|---|---|---|
| `brand.json` | The council's name, colours, crest and case reference prefix | Both sites; `scripts/brand_check.py` checks every page after a change |
| `config.json` | The demo date, the city, the depot, the quarter for the WasteDataFlow return, which wards have bin day today, booked bulky collections, and the room switches that `scripts/room.sh` sets | Everywhere; the bin-day and bulky-booking flags on triage cards |
| `triage_rules.json` | Which waste goes to a specialist, which is held for an officer, and the bin-day and bulky-booking rules | The decision on each triage card and the "why" line under it |
| `whose_job.json` | Who must clear the waste, and under which law | "Whose job" on triage cards |
| `reduce.json` | Hotspot rules, the prevention actions and the student move-out calendar | The "Reduce" screen |
| `copy.json` | The words the public sees: app name, button text, thank-you messages, privacy note, "how it works" | The public portal |

## How decisions are made

The AI looks at the photo and suggests a Defra size, waste type and land type. It doesn't make the decision: the rules in `triage_rules.json` do, in this order, and the first one that applies wins. If the AI couldn't read the photo, none of them applies: a person checks it.

1. **Specialist removal** if the waste type is in `specialist_waste_types`, or the AI's hazards or description mention a word in `specialist_hazard_keywords` (for example "corrugated" or "paint tin").
2. **Not fly-tipping** if a bulky collection is booked within `radius_m` of the spot today (`config.json`, `bulky_bookings`).
3. **Needs a person** if it's bin day in that ward (`config.json`, `collection_day_wards`) and the waste is black bags.
4. **Needs a person** if the AI says it isn't fly-tipping, or isn't sure. The AI alone never closes a report.
5. **Officer to inspect** if the waste type is in `hold_waste_types` (bags and trade waste, which often contain addresses).
6. Otherwise **Crew today**.

`whose_job.json` works the same way: rules are checked from the top, and the first match wins. For example, a pile within 20 m of railway land goes to Network Rail before anything else is checked.

## Editing safely

- **Names must match the Defra lists exactly**, including capitals, spaces and hyphens: for example `Black bags - household`, `Car boot or less`, `Chemical drums, oil or fuel`. The full lists are `SIZES`, `WASTE` and `LAND` in `common.py`. A misspelt name is simply ignored, so `tests/test_units.py` checks every name in these files against those lists.
- **Keep the JSON valid.** Every string needs double quotes, items in a list are separated by commas, and there's no comma after the last item. To check a file, run `python3 -m json.tool content/triage_rules.json`. It prints the file if it's fine and names the line if it isn't. A broken file doesn't stop the app: it keeps using the last good copy, so a broken edit looks as if it did nothing.
- **Keys starting with `_`** (such as `_about`) are notes for people; the app ignores them.
- **Evidence strength** must be `strong`, `moderate` or `weak`.
- **Wards** must match the ward names in `seed/wards.geojson` (for example `Kensington & Fairfield`).

Example: to make it bin day in Toxteth as well, change

```json
"collection_day_wards": ["Kensington & Fairfield"],
```

to

```json
"collection_day_wards": ["Kensington & Fairfield", "Toxteth"],
```

## Where the numbers come from

- **Whose job:** the Environmental Protection Act 1990: s.89 for the duty to keep land clear (the council's, Network Rail's and National Highways'), and s.59 for private land. Each rule in `whose_job.json` names its section.
- **Prevention actions and the move-out calendar:** drawn from published research on fly-tipping prevention and near-repeat patterns. The student wards are a best guess, to confirm with the council.
