# Paired benchmark instances

This folder contains 15 reproducible cases: five easy, five medium and five hard. Every case has three files:

- `<id>.json`: structured source-of-truth instance for the solver and validator;
- `<id>.txt`: equivalent natural-language input for the frontier-model experiments; and
- `<id>.witness.json`: one schema-valid, feasible schedule used only for generator verification.

Do not expose witness files to either experimental method. They are not guaranteed to be optimal.

| Instance | Scenario | Organisations | Households | Duplicates | Refrigerated vehicles |
|---|---|---:|---:|---:|---:|
| easy_001 | fully serviceable | 2 | 7 | 1 | 0 |
| easy_002 | fully serviceable | 2 | 7 | 1 | 1 |
| easy_003 | fully serviceable | 2 | 7 | 1 | 2 |
| easy_004 | fully serviceable | 2 | 6 | 1 | 0 |
| easy_005 | partially serviceable | 2 | 8 | 1 | 2 |
| medium_001 | fully serviceable | 3 | 13 | 2 | 3 |
| medium_002 | fully serviceable | 2 | 13 | 3 | 2 |
| medium_003 | fully serviceable | 2 | 15 | 2 | 2 |
| medium_004 | fully serviceable | 3 | 13 | 2 | 3 |
| medium_005 | partially serviceable | 2 | 13 | 3 | 2 |
| hard_001 | fully serviceable | 3 | 24 | 4 | 3 |
| hard_002 | fully serviceable | 3 | 24 | 5 | 3 |
| hard_003 | fully serviceable | 3 | 22 | 4 | 3 |
| hard_004 | fully serviceable | 3 | 23 | 4 | 3 |
| hard_005 | partially serviceable | 3 | 23 | 4 | 3 |

The fifth instance of each difficulty has exactly one intentionally impossible, non-duplicate household. Its ambient demand is greater than the capacity of every vehicle belonging to the request's organisation. The 45-minute chilled-delivery constraint remains disabled in every case.
