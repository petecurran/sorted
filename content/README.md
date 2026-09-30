# Content files: what each one controls

These six files hold the rules, numbers and words the app uses. You can change them without touching any code. The app re-reads a file whenever it changes, so an edit shows on the next page load, with no restart.

| File | What it controls | Where you see it |
|---|---|---|
| `config.json` | The demo date, the city, the depot, the quarter for the WasteDataFlow return, which wards have bin day today, and booked bulky collections | Everywhere; the bin-day and bulky-booking flags on triage cards |
| `triage_rules.json` | Which waste goes to a specialist, which is held for an officer, and the bin-day and bulky-booking rules | The decision on each triage card and the "why" line under it |
| `costs.json` | Clearance cost for each Defra size, the officer inspection cost and the specialist uplift | Cost on triage cards; estimated cost in the return |
| `whose_job.json` | Who must clear the waste, and under which law | "Whose job" on triage cards |
| `reduce.json` | Hotspot rules, the prevention actions and the student move-out calendar | The "Reduce" screen |
| `copy.json` | The words the public sees: app name, button text, thank-you messages, privacy note, "how it works" | The public portal |

## How decisions are made

The AI looks at the photo and suggests a Defra size, waste type and land type. The rules in `triage_rules.json` then decide, in this order, and the first one that applies wins:

1. **Specialist removal** if the waste type is in `specialist_waste_types`, or the AI's description contains a word in `specialist_hazard_keywords` (for example "corrugated" or "asbestos").
2. **Not fly-tipping** if a bulky collection is booked within `radius_m` of the spot today (`config.json`, `bulky_bookings`).
3. **Needs a person** if it's bin day in that ward (`config.json`, `collection_day_wards`) and the waste is black bags.
4. **Not fly-tipping** if the AI says it isn't one.
5. **Officer to inspect** if the waste type is in `hold_waste_types` (bags and trade waste, which often contain addresses).
6. Otherwise **Crew today**. If the AI is unsure, a person checks it.

`whose_job.json` works the same way: rules are checked from the top, and the first match wins. For example, a pile within 20 m of railway land goes to Network Rail before anything else is checked.

## Editing safely

- **Names must match the Defra lists exactly**, including capitals, spaces and hyphens: for example `Black bags - household`, `Car boot or less`, `Chemical drums, oil or fuel`. The full lists are in `SPEC.md` under "Data shapes". A misspelt name is simply ignored.
- **Keep the JSON valid.** Every string needs double quotes, items in a list are separated by commas, and there's no comma after the last item. To check a file, run `python3 -m json.tool content/costs.json`. It prints the file if it's fine and names the line if it isn't.
- **Keys starting with `_`** (such as `_about`) are notes for people; the app ignores them.
- **Money** is a plain number of pounds, with no `£` sign: `"clear_now_gbp": 51`.
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

- **Costs:** Defra's standard unit costs (set in 2003 to 2006) uplifted to 2025 prices by CPI (×1.77). Tipper and significant/multiple loads use councils' actual 2024/25 averages. The specialist uplift of £250 is a placeholder. Replace them with your own council's costs.
- **Whose job:** Environmental Protection Act 1990 s.59 and s.89.md`.
- **Prevention actions and the move-out calendar:** drawn from published research on fly-tipping prevention and near-repeat patterns. The student wards are a best guess, to confirm with the council.
