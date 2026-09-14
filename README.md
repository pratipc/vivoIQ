# VivoIQ - AI-Powered Procurement Platform

Welcome to the **VivoIQ** repository! VivoIQ is an advanced, AI-driven platform designed to assess, evaluate, and progress candidates based on their technical and strategic capabilities. 

## 🏗️ Repository Architecture

To maintain strict separation of concerns and a clean microservices architecture, this repository is organized into distinct branches instead of monolithic folders. 

This `main` branch serves as the central anchor and documentation hub. The actual microservices reside in their respective isolated branches:

*   **[`assessment_service`]((https://github.com/pratipc/vivoIQ/tree/assessment_service)):** The core AI engine. Handles AI blueprint generation, dynamic test generation, integrity reviews, AI grading, progression logic, and PDF learning plan generation.
*   **[`gateway`]((https://github.com/pratipc/vivoIQ/tree/gateway)):** The central API Gateway and frontend App Shell. Proxies requests to underlying services and handles HTMX Server-Side Rendering (SSR) middleware.
*   **[`user_service`]((https://github.com/pratipc/vivoIQ/tree/user_service)):** Manages candidate authentication, session states, and basic onboarding data.

## 🚀 How to Work with This Repository

If you want to run the entire platform locally, the best approach is to use **Git Worktrees**. This allows you to have all three services checked out in separate directories simultaneously without conflicting branches.

### Setup Instructions

1. Clone the repository (starts on `main`):
   ```bash
   git clone https://github.com/your-username/your-repo.git VivoIQ
   cd VivoIQ
   ```

2. Create separate directories (worktrees) for each microservice:
   ```bash
   git worktree add ../gateway gateway
   git worktree add ../user_service user_service
   git worktree add ../assessment_service assessment_service
   ```

3. You will now have three separate folders outside your main folder. Navigate into each, set up your Python virtual environments, and install dependencies.

## 🧠 Core Technologies
- **Backend:** FastAPI, Python 3
- **Database:** MySQL (interacted via SQLAlchemy and stored procedures)
- **Frontend UI:** HTMX, TailwindCSS (Server-Side Rendered via Jinja2)
- **AI/LLMs:** LangChain / Core LLM integrations for autonomous evaluation.

---
*For detailed setup and operational instructions for a specific service, please switch to that branch and read its `README.md`.*
