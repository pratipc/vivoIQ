# User Service

This branch contains the **User Service** for VivoIQ. This microservice is responsible for managing candidate identity, onboarding forms, and basic session management.

## 🌟 Key Responsibilities

1. **Candidate Onboarding:** Handles the initial signup and login flows for candidates entering the platform.
2. **Session Management:** Sets and manages secure HTTP-only cookies (`user_id`) that authenticate candidates across the gateway and underlying services.
3. **Database Anchoring:** Manages the base `users` table operations (via Stored Procedures), ensuring that all subsequent capabilities, assessments, and AI evaluations are correctly anchored to a verified user entity.
4. **Initial HTML Fragments:** Serves the split-screen landing page and signup/login HTML components via FastAPI and HTMX.

## 🛠️ Tech Stack
* **Framework:** FastAPI
* **Database Access:** SQLAlchemy (Strict adherence to calling MySQL Stored Procedures)
* **Frontend Integration:** HTMX (Forms, inline validation, and redirects)

## ⚙️ Local Setup

1. Ensure you are in the `user_service` worktree or branch.
2. Create a virtual environment:
   ```bash
   python -m venv venv
   # Windows
   venv\Scripts\activate
   # macOS/Linux
   source venv/bin/activate
   ```
3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
4. Configure your `.env` variables (Database credentials).
5. Run the service:
   ```bash
   uvicorn main:app --host 0.0.0.0 --port 8001 --reload
   ```

## 📂 Architecture Note
Like the Assessment Service, this service communicates with the database exclusively via **Stored Procedures** (e.g., `CALL VerifyUser(...)`, `CALL CreateUser(...)`). Do not write direct SQL queries or ORM commands that bypass the procedure layer.
