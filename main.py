import os
import httpx
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from dotenv import load_dotenv

load_dotenv(dotenv_path="../.env")

app = FastAPI(title="VivoIQ Gateway")
templates = Jinja2Templates(directory="templates")

# Microservice URLs
USER_SERVICE_URL = os.getenv("USER_SERVICE_URL", "http://localhost:8001")
ASSESSMENT_SERVICE_URL = os.getenv("ASSESSMENT_SERVICE_URL", "http://localhost:8002")

async def proxy_request(request: Request, service_url: str, path: str):
    async with httpx.AsyncClient(timeout=180.0) as client:
        # Forward headers, but you might want to filter them in a real app
        headers = dict(request.headers)
        headers.pop("host", None)
        headers.pop("content-length", None)
        headers.pop("content-type", None)  # Let httpx reconstruct this for multipart forms
        
        url = f"{service_url}/{path}"
        try:
            if request.method == "GET":
                response = await client.get(url, params=request.query_params, headers=headers, cookies=request.cookies)
            elif request.method == "POST":
                # Handle form data / JSON appropriately
                content_type = request.headers.get("content-type", "")
                if "multipart/form-data" in content_type:
                    form = await request.form()
                    files = {}
                    data = {}
                    for k, v in form.items():
                        if hasattr(v, "filename"):
                             # It's an UploadFile
                             files[k] = (v.filename, await v.read(), v.content_type)
                        else:
                             data[k] = v
                    response = await client.post(url, data=data, files=files, headers=headers, cookies=request.cookies)
                elif "application/x-www-form-urlencoded" in content_type:
                    form_data = await request.form()
                    response = await client.post(url, data=dict(form_data), headers=headers, cookies=request.cookies)
                else:
                    body = await request.body()
                    response = await client.post(url, content=body, headers=headers, cookies=request.cookies)
            else:
                 raise HTTPException(status_code=405, detail="Method not allowed by gateway")
            proxy_response = Response(content=response.content, status_code=response.status_code, media_type=response.headers.get("content-type"))
            # Forward headers back to the browser (crucial for Set-Cookie and Content-Disposition!)
            for k, v in response.headers.multi_items():
                if k.lower() not in ("content-length", "content-encoding", "transfer-encoding", "connection", "server", "date", "content-type"):
                    proxy_response.headers.append(k, v)
                    
            return proxy_response
        
        except httpx.RequestError as exc:
            raise HTTPException(status_code=503, detail=f"Service unavailable: {exc}")

@app.middleware("http")
async def htmx_middleware(request: Request, call_next):
    """
    If the request is NOT an HTMX request (full page load), and it's a GET request to a standard page route,
    we serve the App Shell (index.html) and inject the inner content directly (SSR).
    """
    hx_request = request.headers.get("hx-request")
    
    response = await call_next(request)
    
    if not hx_request and request.method == "GET" and response.status_code == 200 and not request.url.path.startswith(("/api", "/docs", "/openapi.json", "/favicon.ico", "/assessment/certificate")):
        # Read the inner HTML body
        body_chunks = []
        async for chunk in response.body_iterator:
            body_chunks.append(chunk)
        inner_html = b"".join(body_chunks).decode("utf-8")
        
        # Inject it into index.html
        return templates.TemplateResponse(
            request=request, 
            name="index.html", 
            context={"path": request.url.path, "inner_html": inner_html}
        )
        
    return response

# Route specific paths to specific microservices
@app.api_route("/users/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
async def route_user_service(request: Request, path: str):
    return await proxy_request(request, USER_SERVICE_URL, f"users/{path}")

@app.api_route("/assessment/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
async def route_assessment_service(request: Request, path: str):
    return await proxy_request(request, ASSESSMENT_SERVICE_URL, f"assessment/{path}")

@app.get("/")
async def root(request: Request):
    """Serve the split-screen landing page/signup form"""
    if request.cookies.get("user_id"):
        # Very basic session handling: if a user is logged in, redirect them to the onboarding
        return RedirectResponse(url="/assessment/onboarding")
    return await proxy_request(request, USER_SERVICE_URL, "users/signup-form")

if __name__ == "__main__":
    import uvicorn
    # Gateway port is typically 8000
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
