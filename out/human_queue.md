# Human queue
_generated 2026-08-18 18:06 UTC - run #1_

The machine handles the rest. These are the only items that need a person.

## 1. Fix the top block reason

- **2x** - empty subject
- **2x** - empty body
- **2x** - body too short (0 words)

_Each of these is a one-line edit to `config/guardrails.yaml` or `config/fact_pack.md`._

## 3. Refresh the roster

- Add any clinician who replied positively to `inbox/advocates.csv` so the machine can quote them next cycle.
- Drop anyone who asked to be left alone into `inbox/suppress.csv`.
