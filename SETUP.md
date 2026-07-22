# LancersPulse — Setup Instructions

## First time setup

```bash
# 1. Create and activate virtual environment
python -m venv .venv

# Windows
.venv\Scripts\activate

# Mac/Linux
source .venv/bin/activate

# 2. Install dependencies
pip install -r requirements.txt
pip install Pillow

# 3. Run migrations
python manage.py migrate

# 4. Load demo data (creates all teams, players, injuries)
python manage.py load_demo_data

# 5. Start server
python manage.py runserver
```

## Demo login credentials

All demo accounts use password: `1234`

| Role | Username |
|------|----------|
| Admin | admin |
| Athletic Therapist (Doctor) | therapist |
| Coach (Men's Ice Hockey) | coach |
| Coach (Women's Ice Hockey) | coach_hockeyw |
| Coach (Men's Soccer) | coach_soccerm |
| Coach (Women's Soccer) | coach_soccerw |
| Coach (Football) | coach_football |
| Player | player_mh1 (or any player_* account) |

## Demo highlights
- Men's Hockey: 8 shoulder injuries (80% of team injuries) — admin dashboard example
- Women's Soccer: 17 missed games 2025 vs 34 in 2024 — year-over-year comparison
- 5 teams, 44 players, 40+ injuries across 2024 and 2025 seasons
