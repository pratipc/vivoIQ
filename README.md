# Assessment Service

This branch contains the **Assessment Service** for VivoIQ. This is the heavy-lifting AI engine of the platform, responsible for dynamically assessing candidates, generating tests, ensuring test integrity, evaluating answers, and managing candidate progression.

## 🌟 Key Responsibilities

1. **AI Capability Profiling:** Ingests candidate data to build detailed capability profiles and expected levels.
2. **Dynamic Blueprinting (AI-3):** Generates targeted, context-aware assessment blueprints based on candidate gaps, previous attempts, and expected progression levels.
3. **Question Generation (AI-4) & Integrity Review (AI-5):** Synthesizes unique question pools dynamically, calibrates technical difficulty, and audits for leakage or ambiguity.
4. **Grading & Evaluation (AI-6 & AI-7):** Acts as a strict examiner to grade open-ended/technical responses, assigning scores and detailed reasoning across specific domains.
5. **Progression Engine:** Handles "Next-Level" attempts and reassessments. Utilizes a zero-data-loss architecture by cloning `resume_id` states via database stored procedures, ensuring a perfect audit trail of all past attempts.
6. **SaaS Report Generation:** Generates comprehensive PDF Learning Plans and dynamic HTMX capability reports.

## 🛠️ Tech Stack
* **Framework:** FastAPI
* **Database Access:** SQLAlchemy (Strict adherence to calling MySQL Stored Procedures)
* **PDF Generation:** ReportLab
* **Frontend Responses:** HTMX via FastAPI `HTMLResponse`

## ⚙️ Local Setup

1. Ensure you are in the `assessment_service` worktree or branch.
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
4. Configure your `.env` variables (Database credentials, LLM API keys).
5. Run the service:
   ```bash
   uvicorn main:app --host 0.0.0.0 --port 8002 --reload
   ```

## 📂 Architecture Note
This service exclusively communicates with the database via **Stored Procedures** (e.g., `CALL SaveAssessmentResult(...)`). Direct table queries are forbidden in the application layer to maintain strict data encapsulation and DB-level security.
