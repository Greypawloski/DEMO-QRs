# CLAUDE.md

Flask + SQLite web app for a tennis shop demo + restring request system.

Features:
- QR-based equipment demo checkout + returns
- Waitlist queue for unavailable demo items
- Restring request system (job intake + status tracking)
- Admin dashboard (inventory, demos, waitlists, restring jobs)
- SMS notifications via Twilio

Structure:
- app.py = main routes + core logic
- templates/ = Jinja UI
- static/ = assets
- SQLite DB already exists and is in use
- App is deployed on PythonAnywhere (not local-first)

Core flows:
- Demo flow: QR scan → checkout → active demo → return
- Waitlist flow: join queue → notify when available → convert to checkout
- Restring flow: request created → queued → in progress → completed → pickup

Rules:
- Do NOT duplicate routes or logic
- Reuse existing demo, waitlist, and restring flows
- Preserve QR → equipment mapping
- Maintain waitlist ordering
- Maintain correct restring status transitions
- Avoid duplicate SMS triggers
- Do NOT recreate or reset database schema unless explicitly required

Workflow:
- Check existing routes before adding new ones
- Prefer modifying existing logic over creating new parallel flows
- Make minimal, targeted changes
- Verify features exist in code before assuming they are missing

Guidance:
- Read this file before making changes
- Use existing code as source of truth
- Do not scan the entire repo unless necessary
- Do not assume the app runs locally; it is deployed on PythonAnywhere

Git / Deployment Rules:
- Only work on the current active branch unless explicitly instructed.
- Before git operations, confirm the branch with `git branch --show-current`.
- Do not pull from branches suggested by other Claude windows.
- Do not run merge, rebase, checkout, or pull commands without confirmation.
- PythonAnywhere `config.py` contains server-specific settings and should not be overwritten unless explicitly requested.
