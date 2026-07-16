# Deploy LancersPulse V2 → PythonAnywhere (lad91)

Follow these steps **in order**. Part 1 runs on your Windows machine; Part 2 runs in the PythonAnywhere browser console.

---

## PART 1 — Push V2 to GitHub (Windows)

Open **Git Bash** or **PowerShell** in the `LancersPulse` folder (where `V2/` lives).

```bash
# 1. Stage the entire V2 folder (db.sqlite3, .env, staticfiles are gitignored automatically)
git add V2/

# 2. Also stage the settings fix we just made (ALLOWED_HOSTS)
git add V2/lancer_project/settings.py

# 3. Commit
git commit -m "Add V2 — fully redesigned LancersPulse"

# 4. Push to GitHub (player-dashboard branch, which already exists on origin)
git push origin player-dashboard
```

✅ Check: visit https://github.com/ronitlxd/Lancers-Project/tree/player-dashboard  
You should see the `V2/` folder there.

---

## PART 2 — Update PythonAnywhere

Go to https://www.pythonanywhere.com → **Consoles** → open (or start) a **Bash** console.

### Step 1 — Pull the new code

```bash
# If the repo is already cloned (common path — adjust if yours differs)
cd ~/Lancers-Project
git fetch origin
git checkout player-dashboard
git pull origin player-dashboard
```

If the repo is **not** cloned yet:
```bash
cd ~
git clone --branch player-dashboard https://github.com/ronitlxd/Lancers-Project.git
cd Lancers-Project
```

### Step 2 — Set up / update the virtualenv

```bash
# Create a new venv pointing at V2 (skip if you want to reuse your existing one)
mkvirtualenv --python=python3.12 lancerspulse_v2

# Or activate your existing venv:
# workon your_existing_venv_name

# Install / update dependencies
pip install -r ~/Lancers-Project/V2/requirements.txt
```

> **Note:** `reportlab` and `openpyxl` are now in requirements.txt — they'll install automatically.

### Step 3 — Create the .env file

```bash
cd ~/Lancers-Project/V2
nano .env
```

Paste this, then save (Ctrl+O, Enter, Ctrl+X):

```
SECRET_KEY=77_Q_6XmRPYeDx9cBAM4Cy0ponYdQg4oJeIICDA6SpXpopgDspnsvlZaz7_jDp9Au6A
DEBUG=False
ALLOWED_HOSTS=lad91.pythonanywhere.com
```

### Step 4 — Run migrations & collect static files

```bash
cd ~/Lancers-Project/V2
python manage.py migrate
python manage.py collectstatic --noinput
```

### Step 5 — Create your admin superuser (if starting fresh)

```bash
python manage.py createsuperuser
```

---

## PART 3 — Update the Web App Config on PythonAnywhere

Go to **Web** tab → click your web app (lad91.pythonanywhere.com).

### Source code directory
Set to:
```
/home/lad91/Lancers-Project/V2
```

### Virtualenv
Set to the path of the venv you created/activated, e.g.:
```
/home/lad91/.virtualenvs/lancerspulse_v2
```

### WSGI configuration file
Click **"WSGI configuration file"** link to edit it. Replace **all** contents with:

```python
import sys
import os

# Point to the V2 project root
path = '/home/lad91/Lancers-Project/V2'
if path not in sys.path:
    sys.path.insert(0, path)

os.environ['DJANGO_SETTINGS_MODULE'] = 'lancer_project.settings'

from django.core.wsgi import get_wsgi_application
application = get_wsgi_application()
```

### Static files mapping
In the **Static files** section, add:

| URL       | Directory                                          |
|-----------|----------------------------------------------------|
| `/static/`| `/home/lad91/Lancers-Project/V2/staticfiles`       |
| `/media/` | `/home/lad91/Lancers-Project/V2/media`             |

### Reload
Click the green **Reload** button at the top of the Web tab.

---

## PART 4 — Verify

Visit https://lad91.pythonanywhere.com — you should see the new LancersPulse login page.

**If you get a 500 error:** Go to **Web** → **Error log** and check the last few lines.

**Common issues:**
- `ModuleNotFoundError: decouple` → venv not set correctly, or pip install missed
- `ALLOWED_HOSTS` error → make sure `.env` has `ALLOWED_HOSTS=lad91.pythonanywhere.com`
- Static files 404 → re-run `collectstatic` and check the Static files mapping paths

---

## Future updates (after this deployment)

Whenever you make local changes:
```bash
# On Windows
git add -A
git commit -m "your message"
git push origin player-dashboard

# On PythonAnywhere Bash
cd ~/Lancers-Project && git pull origin player-dashboard
# If there are model changes:
python V2/manage.py migrate
python V2/manage.py collectstatic --noinput
# Then reload the web app from the Web tab
```
