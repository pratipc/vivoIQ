# API Gateway

This branch contains the **API Gateway** for VivoIQ. This service acts as the central entry point for all client requests, managing routing to underlying microservices and serving the frontend App Shell.

## 🌟 Key Responsibilities

1. **Request Proxying:** Intercepts incoming requests and proxies them to the correct microservice:
   * `/users/*` routes to the **User Service**.
   * `/assessment/*` routes to the **Assessment Service**.
2. **HTMX Middleware (SSR):** Implements a custom HTTP middleware that determines if an incoming GET request is a full page load (standard browser navigation) or an HTMX asynchronous swap.
   * If it's a full page load, the gateway intercepts the microservice's raw HTML response, wraps it inside the `index.html` App Shell (containing the sidebar, header, and global styles), and serves a complete page.
   * If it's an HTMX request, it allows the raw HTML fragments to pass through directly.
3. **Binary Stream Handling:** Specifically excludes specific routes (like PDF downloads) from UTF-8 decoding in the middleware, allowing raw binary file streams to pass through uncorrupted.

## 🛠️ Tech Stack
* **Framework:** FastAPI
* **Proxy Client:** HTTPX (Asynchronous HTTP client)
* **Templating:** Jinja2 (For the App Shell)

## ⚙️ Local Setup

1. Ensure you are in the `gateway` worktree or branch.
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
4. Make sure your underlying services (User Service, Assessment Service) are running on their respective ports. Update `.env` or configuration variables if their URLs differ from defaults.
5. Run the gateway:
   ```bash
   uvicorn main:app --host 0.0.0.0 --port 8000 --reload
   ```

*Note: All browser traffic should be directed to the Gateway port (8000).*
