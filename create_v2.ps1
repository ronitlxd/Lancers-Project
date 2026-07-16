# =============================================================
# create_v2.ps1  —  Build a clean GitHub-ready V2 folder
# Run from inside LancersPulse:  .\create_v2.ps1
# =============================================================

$src = Split-Path -Parent $MyInvocation.MyCommand.Path
$dst = Join-Path $src "V2"

# Abort if V2 already exists so we don't overwrite anything by accident
if (Test-Path $dst) {
    Write-Host "V2 already exists at $dst" -ForegroundColor Yellow
    $confirm = Read-Host "Delete and recreate it? (y/N)"
    if ($confirm -ne "y") { exit }
    Remove-Item $dst -Recurse -Force
}

New-Item -ItemType Directory -Path $dst | Out-Null
Write-Host "Creating V2..." -ForegroundColor Cyan

# ── Django apps & project config ─────────────────────────────
$folders = @("accounts", "injury_tracking", "injuries", "lancer_project", "templates", "static")

foreach ($folder in $folders) {
    $from = Join-Path $src $folder
    $to   = Join-Path $dst $folder
    if (Test-Path $from) {
        robocopy $from $to /E /XD "__pycache__" /XF "*.pyc" "*.pyo" | Out-Null
        Write-Host "  Copied $folder/" -ForegroundColor Green
    } else {
        Write-Host "  SKIP (not found): $folder/" -ForegroundColor DarkGray
    }
}

# ── Root files ───────────────────────────────────────────────
$rootFiles = @("manage.py", "requirements.txt", "README.md", "SETUP.md")

foreach ($file in $rootFiles) {
    $from = Join-Path $src $file
    if (Test-Path $from) {
        Copy-Item $from (Join-Path $dst $file)
        Write-Host "  Copied $file" -ForegroundColor Green
    } else {
        Write-Host "  SKIP (not found): $file" -ForegroundColor DarkGray
    }
}

# ── .gitignore ───────────────────────────────────────────────
$gitignore = @"
# Python
__pycache__/
*.py[cod]
*.pyo
*.pyd

# Virtual environment
.venv/
venv/
env/
ENV/

# Django
db.sqlite3
*.sqlite3
/staticfiles/
/media/
/uploads/

# Environment variables
.env
.env.*
!.env.example

# IDE
.idea/
.vscode/
*.iml

# OS
.DS_Store
Thumbs.db

# Secrets / keys
*.pem
*.key
"@

$gitignore | Set-Content (Join-Path $dst ".gitignore") -Encoding UTF8
Write-Host "  Created .gitignore" -ForegroundColor Green

# ── Summary ──────────────────────────────────────────────────
Write-Host ""
Write-Host "Done! V2 is at: $dst" -ForegroundColor Cyan
Write-Host ""
Write-Host "Next steps:" -ForegroundColor White
Write-Host "  cd V2" -ForegroundColor DarkCyan
Write-Host "  git init" -ForegroundColor DarkCyan
Write-Host "  git add ." -ForegroundColor DarkCyan
Write-Host "  git commit -m 'Initial V2 commit'" -ForegroundColor DarkCyan
Write-Host "  git remote add origin <your-repo-url>" -ForegroundColor DarkCyan
Write-Host "  git push -u origin master" -ForegroundColor DarkCyan
