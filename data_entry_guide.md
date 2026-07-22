# LancersPulse — Data Entry Guide

Hi Chad,

To add injury records to the system, here's what you need:

---

## Before Adding Injuries

Make sure the following exist in the Django Admin (`/admin/`) first:

- **BodyPart** — e.g. Knee, Shoulder, Ankle
- **InjuryType** — e.g. Sprain, Fracture, Concussion
- **InjurySeverity** — e.g. Minor, Moderate, Severe, Critical (each needs a hex color code)

---

## Mandatory Fields (InjuryRecord)

| Field | Description |
|---|---|
| **player** | The athlete who was injured (must have Player role) |
| **reported_by** | The doctor or coach logging the injury |
| **injury_date** | Date the injury occurred |
| **injury_type** | Select from InjuryType table |
| **body_part** | Select from BodyPart table |
| **severity** | Select from InjurySeverity table |
| **description** | Free text — describe what happened |
| **treatment** | One of: `REST`, `PHYSIO`, `SURGERY`, `MEDICATION`, `OTHER` |

---

## Optional Fields (can be filled in later)

| Field | Description |
|---|---|
| status | ACTIVE / RECOVERING / RECOVERED / CHRONIC (default: ACTIVE) |
| contact_type | CONTACT / NON_CONTACT / OVERUSE / UNKNOWN (default: UNKNOWN) |
| symptoms | Free text |
| treatment_notes | Free text |
| context | Where it happened: PRACTICE / GAME / OTHER |
| pain_level | 0–10 scale |
| estimated_recovery_time | Number of days |
| missed_games | Number of games missed |
| missed_practices | Number of practices missed |
| return_to_play_date | Date |
| requires_surgery | Yes/No (default: No) |
| medical_clearance | Yes/No (default: No) |
| follow_up_required | Yes/No (default: No) |

> **Note:** `season_year` and `reported_date` are auto-filled by the system — no need to enter these.

---

Let me know if you have any questions!
