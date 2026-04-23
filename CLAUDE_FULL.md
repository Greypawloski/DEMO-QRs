# CLAUDE_FULL.md

This file provides a detailed overview of the project architecture, workflows, and constraints.
Use this as a deeper reference. For daily work, prefer `CLAUDE.md`.

---

## 🧠 Project Overview

This is a Flask + SQLite web application for managing a **tennis shop demo and restring request system**.

The system consists of two primary operational components:

1. Demo equipment management (QR-based checkouts + waitlists)
2. Restring request workflow (job intake + status tracking)

The application includes both **customer-facing flows** and **admin-facing workflows**.

---

## ⚙️ Tech Stack

- Backend: Python (Flask)
- Database: SQLite
- Frontend: Server-rendered HTML (Jinja templates)
- Integrations:
  - QR code generation
  - SMS notifications via Twilio

---

## 🚀 Deployment / Runtime Context

This app is deployed on **PythonAnywhere**, not primarily run locally.

Key assumptions:
- The production environment is PythonAnywhere
- Changes require updating code and reloading the web app in PythonAnywhere
- Avoid assuming a local Flask development workflow unless explicitly requested

When modifying code:
- Preserve compatibility with PythonAnywhere environment
- Be careful with:
  - file paths
  - environment variables
  - deployment-specific configurations

---

## 🧩 System Breakdown

### 1. Demo Equipment System

Flow:
1. Customer scans QR code
2. Equipment is identified
3. Checkout is created
4. Item marked unavailable
5. Customer returns item
6. Availability is restored

Responsibilities:
- Track active checkouts
- Prevent duplicate checkouts
- Maintain accurate availability

---

### 2. Waitlist System

Flow:
1. Customer joins waitlist
2. Queue order is stored (FIFO)
3. When item becomes available:
   - Next user is notified via SMS
4. User converts to checkout

Constraints:
- Strict FIFO ordering
- No queue skipping
- Notifications must not duplicate

---

### 3. Restring Request System

This is a **state-based workflow system**.

Flow:
1. Request created
2. Job enters queue (queued)
3. Technician starts (in progress)
4. Job completed
5. Customer notified for pickup

Status lifecycle:
- queued → in progress → completed

Constraints:
- Maintain valid status transitions
- Do not skip steps
- Ensure accurate job tracking

---

### 4. Admin Dashboard

Admin capabilities include:
- Managing inventory
- Viewing checkouts
- Managing waitlists
- Managing restring jobs
- Updating statuses

---

### 5. QR Code System

- Each equipment item has a unique QR code
- QR codes map directly to database records

Constraints:
- Mapping must remain stable
- Do not regenerate or break associations

---

### 6. SMS Notification System (Twilio)

Used for:
- Waitlist availability alerts
- Restring completion notifications

Constraints:
- Avoid duplicate messages
- Trigger only on correct workflow events
- Requires valid Twilio configuration

---

## 🗂️ Project Structure

- `app.py` → main Flask app (routes + business logic)
- `templates/` → Jinja templates
- `static/` → frontend assets
- SQLite database → stores:
  - equipment
  - checkouts
  - waitlists
  - restring jobs

Optional helpers:
- QR generation utilities
- SMS utilities

---

## 🧱 Key Patterns

- Route-driven Flask architecture
- Server-rendered UI (no frontend framework)
- Centralized logic in routes
- SQLite for persistent state
- Workflow-driven design (especially restring system)

---

## ⚠️ Important Constraints

- Do NOT duplicate routes or logic
- Always check existing implementation before adding new code
- Maintain database schema integrity
- Preserve:
  - QR mapping
  - waitlist ordering
  - checkout consistency
  - restring workflow transitions
- Avoid duplicate SMS triggers

---

## 🧪 Development Philosophy

- Modify existing logic rather than creating parallel systems
- Keep changes minimal and targeted
- Avoid unnecessary abstraction
- Keep logic readable and centralized
- Validate assumptions by inspecting actual code

---

## 📌 Guidance for Claude

- Use `CLAUDE.md` for fast context
- Use this file for deeper understanding only when needed
- Always treat the codebase as the source of truth
- Do not assume missing features
- Be especially careful when modifying:
  - checkout flows
  - waitlist logic
  - restring workflows
  - SMS triggers

---

## 🧠 Mental Model

This application combines:

- Inventory system (demo equipment)
- Queue system (waitlists)
- Workflow/state machine system (restring jobs)

These systems interact but must remain logically consistent.
