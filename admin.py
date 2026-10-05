from fastapi import APIRouter, Request, Form, Depends
from fastapi.responses import HTMLResponse, Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from database import get_session
import bcrypt
import html

admin_router = APIRouter()

# ----------------------------------------------------------------------
# Admin Login HTML Form
# ----------------------------------------------------------------------

# ----------------------------------------------------------------------
# Admin Resume Download
# ----------------------------------------------------------------------
@admin_router.get("/download-resume/{resume_id}")
async def admin_download_resume(resume_id: int, request: Request, session: AsyncSession = Depends(get_session)):
    admin_id = request.cookies.get("admin_id")
    if not admin_id:
        return HTMLResponse("Unauthorized", status_code=401)
        
    res = await session.execute(text("SELECT filename, file_content FROM resume WHERE id = :r_id"), {"r_id": resume_id})
    row = res.mappings().first()
    
    if not row or not row.get("file_content"):
        return HTMLResponse("File not found in database", status_code=404)
        
    from fastapi.responses import Response
    headers = {
        'Content-Disposition': f'attachment; filename="{row["filename"]}"'
    }
    return Response(content=row["file_content"], media_type="application/pdf", headers=headers)

@admin_router.get("/login", response_class=HTMLResponse)
async def admin_login_form(request: Request, error_message: str = None):
    error_html = f'<div class="mb-6 p-4 bg-rose-50 border-l-4 border-rose-500 text-rose-700 text-sm font-medium animate-fade-in-up">{html.escape(error_message)}</div>' if error_message else ''
    
    # --- Tab 3: Question Generation & Integrity ---
    # Fetch AI assessment data
    ai_res = await session.execute(text("CALL GetAIAssessment(:r_id)"), {"r_id": resume_id})
    ai_row = ai_res.mappings().first()
    ai_data = {}
    if ai_row and ai_row.get("raw_json"):
        try:
            ai_data = json.loads(ai_row["raw_json"])
        except json.JSONDecodeError:
            pass
            
    ai4 = ai_data.get("ai4_json", {})
    ai5 = ai_data.get("ai5_json", {})
    
    # 1. AI-5 Integrity Logs HTML
    audit_log = ai5.get("audit_log", [])
    replaced_count = sum(1 for log in audit_log if log.get("status") == "REPLACE")
    total_audited = len(audit_log)
    
    integrity_html = ""
    if total_audited == 0:
        integrity_html = "<div class='text-sm text-slate-500 italic text-center py-4'>Integrity logs not generated yet.</div>"
    else:
        for log in audit_log:
            status = log.get("status")
            slot = log.get("slot_id")
            reason = log.get("defect_reason")
            
            if status == "REPLACE":
                integrity_html += f'''
                <div class="flex items-start gap-3 p-3 border-l-4 border-amber-500 bg-amber-50/50 rounded-r-lg mb-2">
                    <svg class="w-5 h-5 text-amber-500 mt-0.5 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"></path></svg>
                    <div>
                        <p class="text-[13px] font-bold text-amber-900">Slot #{slot} Rejected</p>
                        <p class="text-[12px] text-amber-700 mt-0.5">{html.escape(reason or "Unknown reason")}</p>
                    </div>
                </div>
                '''
            else:
                integrity_html += f'''
                <div class="flex items-center gap-3 p-3 border-l-4 border-emerald-500 bg-emerald-50/50 rounded-r-lg mb-2">
                    <svg class="w-5 h-5 text-emerald-500 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"></path></svg>
                    <p class="text-[13px] font-bold text-emerald-900">Slot #{slot} Approved</p>
                </div>
                '''

    # 2. Side-by-Side Question Viewer
    final_questions = ai5.get("final_questions", [])
    if not final_questions and ai4.get("questions"):
        final_questions = ai4.get("questions")
        
    questions_html = ""
    if not final_questions:
        questions_html = "<div class='text-sm text-slate-500 italic text-center py-4'>Questions not generated yet.</div>"
    else:
        for q in final_questions:
            q_slot = q.get("slot_id")
            q_domain = html.escape(q.get("domain", ""))
            q_text = html.escape(q.get("question", ""))
            q_type = html.escape(q.get("question_type", ""))
            q_answer = html.escape(q.get("answer", ""))
            q_rubric = html.escape(q.get("rubric", ""))
            q_diff = q.get("difficulty", 1)
            
            # Check if this slot was replaced by AI-5
            is_replaced = any(log.get("slot_id") == q_slot and log.get("status") == "REPLACE" for log in audit_log)
            badge_html = f'<span class="bg-amber-100 text-amber-700 px-2 py-0.5 rounded text-[10px] font-bold uppercase tracking-wider ml-2">Replaced by AI-5</span>' if is_replaced else ''
            
            diff_stars = "".join(['<svg class="w-3.5 h-3.5 text-amber-400 inline" fill="currentColor" viewBox="0 0 20 20"><path d="M9.049 2.927c.3-.921 1.603-.921 1.902 0l1.07 3.292a1 1 0 00.95.69h3.462c.969 0 1.371 1.24.588 1.81l-2.8 2.034a1 1 0 00-.364 1.118l1.07 3.292c.3.921-.755 1.688-1.54 1.118l-2.8-2.034a1 1 0 00-1.175 0l-2.8 2.034c-.784.57-1.838-.197-1.539-1.118l1.07-3.292a1 1 0 00-.364-1.118L2.98 8.72c-.783-.57-.38-1.81.588-1.81h3.461a1 1 0 00.951-.69l1.07-3.292z"></path></svg>' for _ in range(q_diff)])
            
            questions_html += f'''
            <div class="border border-gray-200 rounded-xl overflow-hidden mb-6 bg-white shadow-sm">
                <!-- Header -->
                <div class="bg-slate-50 px-5 py-3 border-b border-gray-200 flex items-center justify-between">
                    <div class="flex items-center gap-3">
                        <span class="w-6 h-6 rounded-full bg-blue-100 text-blue-700 flex items-center justify-center text-xs font-bold">{q_slot}</span>
                        <span class="text-xs font-bold text-slate-700 uppercase tracking-wider">{q_domain}</span>
                        <span class="text-xs text-slate-400 px-2 border-l border-gray-300">{q_type}</span>
                        {badge_html}
                    </div>
                    <div class="flex items-center gap-1">
                        {diff_stars}
                    </div>
                </div>
                
                <!-- Side-by-Side Content -->
                <div class="grid grid-cols-1 md:grid-cols-2 divide-y md:divide-y-0 md:divide-x divide-gray-200">
                    <!-- Payload (Candidate View) -->
                    <div class="p-5">
                        <h4 class="text-[11px] font-bold text-slate-500 uppercase tracking-wider mb-3">Candidate Payload</h4>
                        <p class="text-sm text-slate-900 font-medium mb-4">{q_text}</p>
                        '''
                        
            if q_type == "mcq" and "options" in q:
                options = q.get("options", [])
                questions_html += '<div class="space-y-2">'
                for opt in options:
                    questions_html += f'<div class="px-3 py-2 border border-gray-100 rounded bg-gray-50 text-xs text-slate-700">{html.escape(opt)}</div>'
                questions_html += '</div>'
                
            questions_html += f'''
                    </div>
                    <!-- Rubric (Evaluator View) -->
                    <div class="p-5 bg-blue-50/30">
                        <h4 class="text-[11px] font-bold text-blue-600 uppercase tracking-wider mb-3">Evaluator Rubric (Hidden)</h4>
                        <div class="mb-4">
                            <span class="text-xs font-semibold text-slate-500 block mb-1">Expected Answer:</span>
                            <div class="px-3 py-2 border border-emerald-200 rounded bg-emerald-50 text-xs font-medium text-emerald-800">{q_answer}</div>
                        </div>
                        <div>
                            <span class="text-xs font-semibold text-slate-500 block mb-1">Scoring Criteria:</span>
                            <p class="text-[13px] text-slate-700 leading-relaxed">{q_rubric}</p>
                        </div>
                    </div>
                </div>
            </div>
            '''

    html_content = f'''
    <!-- Alpine.js injected for ephemeral state -->
    <script defer src="https://cdn.jsdelivr.net/npm/alpinejs@3.x.x/dist/cdn.min.js"></script>
    
    <div class="w-full min-h-screen flex bg-slate-50 overflow-hidden font-sans">
      
      <!-- Left Side: Vibrant Blue Trust/Branding -->
      <div class="hidden lg:flex lg:w-1/2 bg-blue-600 flex-col justify-between p-12 text-white relative">
          <!-- Decorative background blob -->
          <div class="absolute top-0 left-0 w-full h-full overflow-hidden opacity-10 pointer-events-none">
              <svg class="absolute w-[800px] h-[800px] -top-20 -left-20 text-white" fill="currentColor" viewBox="0 0 100 100"><circle cx="50" cy="50" r="50"></circle></svg>
          </div>
          
          <div class="relative z-10">
              <h1 class="text-3xl font-extrabold tracking-tight flex items-center gap-2">
                  vivo<span class="text-sky-300">IQ</span>
              </h1>
              <p class="text-blue-100 font-medium tracking-wider text-sm mt-1 uppercase">Enterprise Audit Portal</p>
          </div>
          
          <div class="relative z-10 max-w-md">
              <h2 class="text-4xl font-bold mb-6 leading-tight">Zero-Trust AI Evaluation Transparency.</h2>
              <p class="text-blue-100 text-lg mb-10 leading-relaxed">Ensure compliance, audit candidate payloads, and trace deterministic evaluation pathways securely.</p>
              
              <div class="flex flex-col gap-4">
                  <div class="flex items-center gap-3 bg-blue-700/50 p-4 rounded-xl backdrop-blur-sm border border-blue-500/30">
                      <svg class="w-6 h-6 text-emerald-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z"></path></svg>
                      <div>
                          <p class="font-bold text-sm">SOC-2 Audit Ready</p>
                          <p class="text-xs text-blue-200">Rubrics isolated from evaluation logic.</p>
                      </div>
                  </div>
                  <div class="flex items-center gap-3 bg-blue-700/50 p-4 rounded-xl backdrop-blur-sm border border-blue-500/30">
                      <svg class="w-6 h-6 text-sky-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z"></path></svg>
                      <div>
                          <p class="font-bold text-sm">Deterministic Integrity</p>
                          <p class="text-xs text-blue-200">Algorithmic gates override LLM scoring.</p>
                      </div>
                  </div>
              </div>
          </div>
          
          <div class="relative z-10 text-blue-200 text-xs">
              &copy; 2026 VivoIQ Platform. Secured by Enterprise Auth.
          </div>
      </div>
      
      <!-- Right Side: Login Form -->
      <div class="w-full lg:w-1/2 flex items-center justify-center p-8 sm:p-12">
          <div class="w-full max-w-md">
              <div class="lg:hidden mb-8">
                  <h1 class="text-2xl font-extrabold tracking-tight text-slate-900 flex items-center gap-1">
                      vivo<span class="text-blue-600">IQ</span>
                  </h1>
              </div>
              
              <h2 class="text-3xl font-extrabold text-slate-900 tracking-tight mb-2">Admin Portal</h2>
              <p class="text-slate-500 text-sm font-medium mb-8">Sign in with your administrative credentials.</p>
              
              {error_html}
              
              <form hx-post="/admin/login" hx-target="#main-content" class="space-y-6">
                  <div>
                      <label class="block text-xs font-bold text-slate-700 uppercase tracking-wide mb-2">Email Address</label>
                      <input type="email" name="email" required class="w-full h-12 px-4 bg-white border border-gray-200 rounded-lg text-sm text-slate-900 focus:outline-none focus:border-blue-600 focus:ring-1 focus:ring-blue-600 shadow-sm transition-colors" placeholder="admin@vivoiq.com">
                  </div>
                  
                  <div>
                      <div class="flex items-center justify-between mb-2">
                          <label class="block text-xs font-bold text-slate-700 uppercase tracking-wide">Password</label>
                      </div>
                      <input type="password" name="password" required class="w-full h-12 px-4 bg-white border border-gray-200 rounded-lg text-sm text-slate-900 focus:outline-none focus:border-blue-600 focus:ring-1 focus:ring-blue-600 shadow-sm transition-colors" placeholder="••••••••">
                  </div>
                  
                  <button type="submit" class="w-full h-12 bg-blue-600 hover:bg-blue-700 text-white text-sm font-bold rounded-lg shadow-sm transition-colors flex items-center justify-center gap-2">
                      <span>Authenticate Session</span>
                      <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M14 5l7 7m0 0l-7 7m7-7H3"></path></svg>
                  </button>
              </form>
          </div>
      </div>
      
    </div>
    '''
    return HTMLResponse(content=html_content)

# ----------------------------------------------------------------------
# Admin Login POST
# ----------------------------------------------------------------------
@admin_router.post("/login", response_class=HTMLResponse)
async def admin_login_post(
    response: Response,
    email: str = Form(...), 
    password: str = Form(...),
    session: AsyncSession = Depends(get_session)
):
    result = await session.execute(text("CALL GetUserByEmail(:email)"), {"email": email})
    user = result.mappings().first()
    
    if not user or not bcrypt.checkpw(password.encode('utf-8'), user['password_hash'].encode('utf-8')):
      return await admin_login_form(request=None, error_message="Invalid credentials.")
      
    if not user.get('is_admin'):
      return await admin_login_form(request=None, error_message="Access Denied: You do not have administrator privileges.")
      
    html_response = HTMLResponse(f'''
      <div class="w-full min-h-[60vh] flex flex-col items-center justify-center animate-fade-in-up">
          <div class="w-16 h-16 bg-emerald-50 rounded-[16px] flex items-center justify-center mb-6 shadow-sm border border-emerald-100">
              <svg class="w-8 h-8 text-emerald-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"></path>
              </svg>
          </div>
          <h2 class="text-[22px] font-bold text-slate-900 tracking-tight mb-3">Admin Authenticated</h2>
          <div class="text-[13px] text-slate-500 font-medium flex items-center gap-2">
              <span class="loading loading-spinner loading-xs text-emerald-500 opacity-70"></span>
              <span>Initializing secure audit dashboard...</span>
          </div>
          <div hx-get="/admin/dashboard" hx-trigger="load delay:600ms" hx-target="#main-content" hx-push-url="true" class="hidden"></div>
      </div>
    ''')
    html_response.set_cookie(key="admin_id", value=str(user["id"]), httponly=True)
    return html_response

# ----------------------------------------------------------------------
# Admin Logout
# ----------------------------------------------------------------------
@admin_router.get("/logout", response_class=HTMLResponse)
async def admin_logout(request: Request, response: Response):
    html_res = HTMLResponse("<script>window.location.href = '/admin/login';</script>")
    html_res.delete_cookie("admin_id")
    return html_res


def get_admin_sidebar(active_page: str) -> str:
    """Returns the common sidebar HTML for the admin dashboard."""
    
    # Define styles for active vs inactive links
    active_class = "bg-blue-600/10 text-blue-400 font-medium"
    inactive_class = "hover:bg-slate-800 hover:text-white transition-colors text-slate-300"
    
    assessments_class = active_class if active_page == "dashboard" else inactive_class
    candidates_class = active_class if active_page == "candidates" else inactive_class
    
    return f"""
      <!-- Sidebar Navigation -->
      <aside class="w-64 bg-slate-900 text-slate-300 flex flex-col transition-transform duration-300 z-20 shrink-0"
             :class="sidebarOpen ? 'translate-x-0 absolute inset-y-0 left-0' : '-translate-x-full absolute inset-y-0 left-0 lg:relative lg:translate-x-0'">
          <div class="h-16 flex items-center px-6 border-b border-slate-800 bg-slate-950 shrink-0">
              <a href="/admin/dashboard" hx-get="/admin/dashboard" hx-target="#main-content" hx-push-url="true" class="text-xl font-extrabold tracking-tight text-white flex items-center gap-2 hover:opacity-80">
                  vivo<span class="text-blue-500">IQ</span> <span class="text-xs font-medium uppercase tracking-wider text-slate-500 ml-1">Admin</span>
              </a>
          </div>
          
          <div class="flex-grow overflow-y-auto py-6 px-4 space-y-1">
              <div class="text-xs font-bold text-slate-500 uppercase tracking-wider mb-3 px-3">Audit Trails</div>
              <a href="/admin/dashboard" hx-get="/admin/dashboard" hx-target="#main-content" hx-push-url="true" class="flex items-center gap-3 px-3 py-2.5 rounded-lg {assessments_class}">
                  <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z"></path></svg>
                  Assessments
              </a>
              <a href="/admin/Candidates" hx-get="/admin/Candidates" hx-target="#main-content" hx-push-url="true" class="flex items-center gap-3 px-3 py-2.5 rounded-lg {candidates_class}">
                  <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4.354a4 4 0 110 5.292M15 21H3v-1a6 6 0 0112 0v1zm0 0h6v-1a6 6 0 00-9-5.197M13 7a4 4 0 11-8 0 4 4 0 018 0z"></path></svg>
                  Candidate Profiles
              </a>
              <a href="#" class="flex items-center gap-3 px-3 py-2.5 rounded-lg {inactive_class}">
                  <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z"></path></svg>
                  Integrity Logs
              </a>
          </div>
          
          <div class="p-4 border-t border-slate-800">
              <a href="/admin/logout" class="flex items-center gap-3 px-3 py-2.5 rounded-lg hover:bg-rose-500/10 hover:text-rose-400 transition-colors text-slate-300">
                  <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1"></path></svg>
                  Secure Logout
              </a>
          </div>
      </aside>
"""

# ----------------------------------------------------------------------
# Admin Dashboard (Enterprise Data-Dense Frame)
# ----------------------------------------------------------------------
@admin_router.get("/dashboard", response_class=HTMLResponse)
async def admin_dashboard(request: Request):
    admin_id = request.cookies.get("admin_id")
    if not admin_id:
      return HTMLResponse("<script>window.location.href = '/admin/login';</script>")

    # --- Tab 3: Question Generation & Integrity ---
    # Fetch AI assessment data
    ai_res = await session.execute(text("CALL GetAIAssessment(:r_id)"), {"r_id": resume_id})
    ai_row = ai_res.mappings().first()
    ai_data = {}
    if ai_row and ai_row.get("raw_json"):
        try:
            ai_data = json.loads(ai_row["raw_json"])
        except json.JSONDecodeError:
            pass
            
    ai4 = ai_data.get("ai4_json", {})
    ai5 = ai_data.get("ai5_json", {})
    
    # 1. AI-5 Integrity Logs HTML
    audit_log = ai5.get("audit_log", [])
    replaced_count = sum(1 for log in audit_log if log.get("status") == "REPLACE")
    total_audited = len(audit_log)
    
    integrity_html = ""
    if total_audited == 0:
        integrity_html = "<div class='text-sm text-slate-500 italic text-center py-4'>Integrity logs not generated yet.</div>"
    else:
        for log in audit_log:
            status = log.get("status")
            slot = log.get("slot_id")
            reason = log.get("defect_reason")
            
            if status == "REPLACE":
                integrity_html += f'''
                <div class="flex items-start gap-3 p-3 border-l-4 border-amber-500 bg-amber-50/50 rounded-r-lg mb-2">
                    <svg class="w-5 h-5 text-amber-500 mt-0.5 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"></path></svg>
                    <div>
                        <p class="text-[13px] font-bold text-amber-900">Slot #{slot} Rejected</p>
                        <p class="text-[12px] text-amber-700 mt-0.5">{html.escape(reason or "Unknown reason")}</p>
                    </div>
                </div>
                '''
            else:
                integrity_html += f'''
                <div class="flex items-center gap-3 p-3 border-l-4 border-emerald-500 bg-emerald-50/50 rounded-r-lg mb-2">
                    <svg class="w-5 h-5 text-emerald-500 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"></path></svg>
                    <p class="text-[13px] font-bold text-emerald-900">Slot #{slot} Approved</p>
                </div>
                '''

    # 2. Side-by-Side Question Viewer
    final_questions = ai5.get("final_questions", [])
    if not final_questions and ai4.get("questions"):
        final_questions = ai4.get("questions")
        
    questions_html = ""
    if not final_questions:
        questions_html = "<div class='text-sm text-slate-500 italic text-center py-4'>Questions not generated yet.</div>"
    else:
        for q in final_questions:
            q_slot = q.get("slot_id")
            q_domain = html.escape(q.get("domain", ""))
            q_text = html.escape(q.get("question", ""))
            q_type = html.escape(q.get("question_type", ""))
            q_answer = html.escape(q.get("answer", ""))
            q_rubric = html.escape(q.get("rubric", ""))
            q_diff = q.get("difficulty", 1)
            
            # Check if this slot was replaced by AI-5
            is_replaced = any(log.get("slot_id") == q_slot and log.get("status") == "REPLACE" for log in audit_log)
            badge_html = f'<span class="bg-amber-100 text-amber-700 px-2 py-0.5 rounded text-[10px] font-bold uppercase tracking-wider ml-2">Replaced by AI-5</span>' if is_replaced else ''
            
            diff_stars = "".join(['<svg class="w-3.5 h-3.5 text-amber-400 inline" fill="currentColor" viewBox="0 0 20 20"><path d="M9.049 2.927c.3-.921 1.603-.921 1.902 0l1.07 3.292a1 1 0 00.95.69h3.462c.969 0 1.371 1.24.588 1.81l-2.8 2.034a1 1 0 00-.364 1.118l1.07 3.292c.3.921-.755 1.688-1.54 1.118l-2.8-2.034a1 1 0 00-1.175 0l-2.8 2.034c-.784.57-1.838-.197-1.539-1.118l1.07-3.292a1 1 0 00-.364-1.118L2.98 8.72c-.783-.57-.38-1.81.588-1.81h3.461a1 1 0 00.951-.69l1.07-3.292z"></path></svg>' for _ in range(q_diff)])
            
            questions_html += f'''
            <div class="border border-gray-200 rounded-xl overflow-hidden mb-6 bg-white shadow-sm">
                <!-- Header -->
                <div class="bg-slate-50 px-5 py-3 border-b border-gray-200 flex items-center justify-between">
                    <div class="flex items-center gap-3">
                        <span class="w-6 h-6 rounded-full bg-blue-100 text-blue-700 flex items-center justify-center text-xs font-bold">{q_slot}</span>
                        <span class="text-xs font-bold text-slate-700 uppercase tracking-wider">{q_domain}</span>
                        <span class="text-xs text-slate-400 px-2 border-l border-gray-300">{q_type}</span>
                        {badge_html}
                    </div>
                    <div class="flex items-center gap-1">
                        {diff_stars}
                    </div>
                </div>
                
                <!-- Side-by-Side Content -->
                <div class="grid grid-cols-1 md:grid-cols-2 divide-y md:divide-y-0 md:divide-x divide-gray-200">
                    <!-- Payload (Candidate View) -->
                    <div class="p-5">
                        <h4 class="text-[11px] font-bold text-slate-500 uppercase tracking-wider mb-3">Candidate Payload</h4>
                        <p class="text-sm text-slate-900 font-medium mb-4">{q_text}</p>
                        '''
                        
            if q_type == "mcq" and "options" in q:
                options = q.get("options", [])
                questions_html += '<div class="space-y-2">'
                for opt in options:
                    questions_html += f'<div class="px-3 py-2 border border-gray-100 rounded bg-gray-50 text-xs text-slate-700">{html.escape(opt)}</div>'
                questions_html += '</div>'
                
            questions_html += f'''
                    </div>
                    <!-- Rubric (Evaluator View) -->
                    <div class="p-5 bg-blue-50/30">
                        <h4 class="text-[11px] font-bold text-blue-600 uppercase tracking-wider mb-3">Evaluator Rubric (Hidden)</h4>
                        <div class="mb-4">
                            <span class="text-xs font-semibold text-slate-500 block mb-1">Expected Answer:</span>
                            <div class="px-3 py-2 border border-emerald-200 rounded bg-emerald-50 text-xs font-medium text-emerald-800">{q_answer}</div>
                        </div>
                        <div>
                            <span class="text-xs font-semibold text-slate-500 block mb-1">Scoring Criteria:</span>
                            <p class="text-[13px] text-slate-700 leading-relaxed">{q_rubric}</p>
                        </div>
                    </div>
                </div>
            </div>
            '''

    html_content = f'''
    <!-- Dashboard Full View: Overrides index.html container constraints via fixed positioning if needed, 
       but fits perfectly into #main-content as a sub-app -->
    <div class="fixed inset-0 z-50 flex h-screen w-full bg-slate-50 overflow-hidden font-sans text-slate-900" x-data="{{ sidebarOpen: false }}">
      
{get_admin_sidebar("dashboard")}

      <!-- Main Content Wrapper -->
      <div class="flex-1 flex flex-col min-w-0 bg-slate-50">
          
          <!-- Global Header -->
          <header class="h-16 bg-white border-b border-gray-200 shadow-sm flex items-center justify-between px-6 shrink-0 z-10">
              <div class="flex items-center gap-4">
                  <button @click="sidebarOpen = !sidebarOpen" class="lg:hidden p-2 text-slate-500 hover:text-slate-900 rounded-md">
                      <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 6h16M4 12h16M4 18h16"></path></svg>
                  </button>
                  <div class="relative max-w-md w-full hidden sm:block">
                      <svg class="absolute left-3 top-2.5 w-4 h-4 text-slate-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"></path></svg>
                      <input type="text" placeholder="Search by Candidate ID, Email, or Skill..." class="w-96 h-9 pl-9 pr-4 bg-slate-100/50 border border-transparent rounded-md text-sm text-slate-900 placeholder-slate-400 focus:bg-white focus:border-blue-500 focus:ring-1 focus:ring-blue-500 transition-all">
                  </div>
              </div>
              
              <div class="flex items-center gap-4">
                  <span class="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-emerald-100 text-emerald-800 text-xs font-bold border border-emerald-200">
                      <span class="w-2 h-2 rounded-full bg-emerald-500 animate-pulse"></span>
                      AI Engine: Active
                  </span>
                  <div class="w-8 h-8 rounded-full bg-blue-600 flex items-center justify-center text-white text-sm font-bold shadow-sm ring-2 ring-white">
                      A
                  </div>
              </div>
          </header>

          <!-- Scrollable Page Content -->
          <main class="flex-1 overflow-y-auto">
              
              <!-- Hero Section: Macro KPIs -->
              <div class="bg-white border-b border-gray-200 p-8">
                  <div class="max-w-7xl mx-auto">
                      <div class="flex justify-between items-end mb-6">
                          <div>
                              <h2 class="text-2xl font-extrabold text-slate-900 tracking-tight">Audit Overview</h2>
                              <p class="text-slate-500 text-sm mt-1">Real-time metrics for AI-evaluated assessments.</p>
                          </div>
                          <div class="flex gap-2">
                              <button class="px-4 py-2 bg-white hover:bg-slate-50 text-slate-700 text-xs font-bold rounded-lg border border-gray-200 shadow-sm transition-colors flex items-center gap-2">
                                  <svg class="w-4 h-4 text-slate-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 4a1 1 0 011-1h16a1 1 0 011 1v2.586a1 1 0 01-.293.707l-6.414 6.414a1 1 0 00-.293.707V17l-4 4v-6.586a1 1 0 00-.293-.707L3.293 7.293A1 1 0 013 6.586V4z"></path></svg>
                                  Filter Range
                              </button>
                              <button class="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white text-xs font-bold rounded-lg shadow-sm transition-colors flex items-center gap-2">
                                  <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"></path></svg>
                                  Sync Data
                              </button>
                          </div>
                      </div>
                      
                      <div class="grid grid-cols-1 md:grid-cols-4 gap-4">
                          <div class="bg-slate-50 p-5 rounded-xl border border-gray-100 shadow-sm">
                              <div class="text-slate-500 text-xs font-bold uppercase tracking-wider mb-2">Total Candidates</div>
                              <div class="text-3xl font-extrabold text-slate-900">0</div>
                          </div>
                          <div class="bg-slate-50 p-5 rounded-xl border border-gray-100 shadow-sm">
                              <div class="text-slate-500 text-xs font-bold uppercase tracking-wider mb-2">Assessments Completed</div>
                              <div class="text-3xl font-extrabold text-blue-600">0</div>
                          </div>
                          <div class="bg-slate-50 p-5 rounded-xl border border-gray-100 shadow-sm">
                              <div class="text-slate-500 text-xs font-bold uppercase tracking-wider mb-2">Credentials Issued</div>
                              <div class="text-3xl font-extrabold text-emerald-600">0</div>
                          </div>
                          <div class="bg-slate-50 p-5 rounded-xl border border-gray-100 shadow-sm">
                              <div class="text-slate-500 text-xs font-bold uppercase tracking-wider mb-2">Integrity Interventions</div>
                              <div class="text-3xl font-extrabold text-amber-500">0</div>
                          </div>
                      </div>
                  </div>
              </div>

              <!-- Content Area: White Cards -->
              <div class="p-8 max-w-7xl mx-auto w-full">
                  <div class="bg-white rounded-[12px] shadow-sm border border-gray-200 overflow-hidden">
                      <div class="px-6 py-5 border-b border-gray-200 flex justify-between items-center bg-slate-50/50">
                          <h3 class="text-sm font-bold text-slate-800 uppercase tracking-wide">Assessment Audit Log</h3>
                      </div>
                      
                      <!-- Empty State -->
                      <div class="p-16 flex flex-col items-center justify-center text-center">
                          <div class="w-16 h-16 bg-slate-100 rounded-2xl flex items-center justify-center mb-4 border border-gray-200 shadow-sm">
                              <svg class="w-8 h-8 text-slate-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10"></path></svg>
                          </div>
                          <h4 class="text-base font-bold text-slate-800 mb-1">No Assessment Data Yet</h4>
                          <p class="text-sm text-slate-500 max-w-sm">Candidate assessment pipelines and their corresponding deterministic evaluation traces will populate here automatically.</p>
                      </div>
                  </div>
              </div>
              
          </main>
      </div>
    </div>
    '''
    return HTMLResponse(content=html_content)

# ----------------------------------------------------------------------
# Admin Candidate Profiles List
# ----------------------------------------------------------------------
@admin_router.get("/Candidates", response_class=HTMLResponse)
async def admin_candidates(request: Request, session: AsyncSession = Depends(get_session)):
    admin_id = request.cookies.get("admin_id")
    if not admin_id:
      return HTMLResponse("<script>window.location.href = '/admin/login';</script>")

    # Fetch candidate profiles using Zero-Inline SQL
    res = await session.execute(text("CALL GetAllCandidateProfiles()"))
    candidates = res.mappings().fetchall()

    table_rows = ""
    if not candidates:
      table_rows = '''
      <tr>
          <td colspan="5" class="px-6 py-12 text-center">
              <div class="flex flex-col items-center justify-center text-slate-500">
                  <svg class="w-10 h-10 text-slate-300 mb-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0zm6 3a2 2 0 11-4 0 2 2 0 014 0zM7 10a2 2 0 11-4 0 2 2 0 014 0z"></path></svg>
                  <p class="text-sm font-medium text-slate-600">No candidates found.</p>
                  <p class="text-xs text-slate-400 mt-1">Candidate profiles will appear here once parsed.</p>
              </div>
          </td>
      </tr>'''
    else:
      for c in candidates:
          date_str = c["created_at"].strftime("%b %d, %Y") if c["created_at"] else "N/A"
          resume_id = c["resume_id"]
          # Badge logic for expected level
          if c["expected_level"]:
              level_badge = f'<span class="inline-flex items-center px-2.5 py-0.5 rounded-md text-xs font-medium bg-blue-50 text-blue-700 border border-blue-100">Level {c["expected_level"]}</span>'
          else:
              level_badge = '<span class="inline-flex items-center px-2.5 py-0.5 rounded-md text-xs font-medium bg-gray-100 text-gray-500 border border-gray-200 border-dashed">Yet to give assessment</span>'
          
          table_rows += f'''
          <tr class="hover:bg-slate-50 transition-colors border-b border-gray-100 last:border-0 group">
              <td class="px-6 py-4 whitespace-nowrap">
                  <div class="flex items-center">
                      <div class="h-9 w-9 rounded-full bg-blue-600 flex items-center justify-center text-white font-bold text-sm shadow-sm ring-2 ring-white">
                          {html.escape(c["name"][0].upper() if c["name"] else "?")}
                      </div>
                      <div class="ml-4">
                          <div class="text-sm font-bold text-slate-900">{html.escape(c["name"] or "")}</div>
                          <div class="text-xs text-slate-500">{html.escape(c["email"] or "")}</div>
                      </div>
                  </div>
              </td>
              <td class="px-6 py-4 whitespace-nowrap">
                  <div class="text-sm text-slate-900 font-medium">#{c["resume_id"]}</div>
              </td>
              <td class="px-6 py-4 whitespace-nowrap">
                  {level_badge}
              </td>
              <td class="px-6 py-4 whitespace-nowrap text-sm text-slate-500">
                  {date_str}
              </td>
              <td class="px-6 py-4 whitespace-nowrap text-right text-sm font-medium">
                  <a href="/admin/audit/{resume_id}" hx-get="/admin/audit/{resume_id}" hx-target="#main-content" hx-push-url="true" class="inline-block text-blue-600 hover:text-blue-900 bg-blue-50 hover:bg-blue-100 px-3 py-1.5 rounded-md transition-colors opacity-0 group-hover:opacity-100 focus:opacity-100">
                      View Audit Trail
                  </a>
              </td>
          </tr>
          '''

    # --- Tab 3: Question Generation & Integrity ---
    # Fetch AI assessment data
    ai_res = await session.execute(text("CALL GetAIAssessment(:r_id)"), {"r_id": resume_id})
    ai_row = ai_res.mappings().first()
    ai_data = {}
    if ai_row and ai_row.get("raw_json"):
        try:
            ai_data = json.loads(ai_row["raw_json"])
        except json.JSONDecodeError:
            pass
            
    ai4 = ai_data.get("ai4_json", {})
    ai5 = ai_data.get("ai5_json", {})
    
    # 1. AI-5 Integrity Logs HTML
    audit_log = ai5.get("audit_log", [])
    replaced_count = sum(1 for log in audit_log if log.get("status") == "REPLACE")
    total_audited = len(audit_log)
    
    integrity_html = ""
    if total_audited == 0:
        integrity_html = "<div class='text-sm text-slate-500 italic text-center py-4'>Integrity logs not generated yet.</div>"
    else:
        for log in audit_log:
            status = log.get("status")
            slot = log.get("slot_id")
            reason = log.get("defect_reason")
            
            if status == "REPLACE":
                integrity_html += f'''
                <div class="flex items-start gap-3 p-3 border-l-4 border-amber-500 bg-amber-50/50 rounded-r-lg mb-2">
                    <svg class="w-5 h-5 text-amber-500 mt-0.5 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"></path></svg>
                    <div>
                        <p class="text-[13px] font-bold text-amber-900">Slot #{slot} Rejected</p>
                        <p class="text-[12px] text-amber-700 mt-0.5">{html.escape(reason or "Unknown reason")}</p>
                    </div>
                </div>
                '''
            else:
                integrity_html += f'''
                <div class="flex items-center gap-3 p-3 border-l-4 border-emerald-500 bg-emerald-50/50 rounded-r-lg mb-2">
                    <svg class="w-5 h-5 text-emerald-500 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"></path></svg>
                    <p class="text-[13px] font-bold text-emerald-900">Slot #{slot} Approved</p>
                </div>
                '''

    # 2. Side-by-Side Question Viewer
    final_questions = ai5.get("final_questions", [])
    if not final_questions and ai4.get("questions"):
        final_questions = ai4.get("questions")
        
    questions_html = ""
    if not final_questions:
        questions_html = "<div class='text-sm text-slate-500 italic text-center py-4'>Questions not generated yet.</div>"
    else:
        for q in final_questions:
            q_slot = q.get("slot_id")
            q_domain = html.escape(q.get("domain", ""))
            q_text = html.escape(q.get("question", ""))
            q_type = html.escape(q.get("question_type", ""))
            q_answer = html.escape(q.get("answer", ""))
            q_rubric = html.escape(q.get("rubric", ""))
            q_diff = q.get("difficulty", 1)
            
            # Check if this slot was replaced by AI-5
            is_replaced = any(log.get("slot_id") == q_slot and log.get("status") == "REPLACE" for log in audit_log)
            badge_html = f'<span class="bg-amber-100 text-amber-700 px-2 py-0.5 rounded text-[10px] font-bold uppercase tracking-wider ml-2">Replaced by AI-5</span>' if is_replaced else ''
            
            diff_stars = "".join(['<svg class="w-3.5 h-3.5 text-amber-400 inline" fill="currentColor" viewBox="0 0 20 20"><path d="M9.049 2.927c.3-.921 1.603-.921 1.902 0l1.07 3.292a1 1 0 00.95.69h3.462c.969 0 1.371 1.24.588 1.81l-2.8 2.034a1 1 0 00-.364 1.118l1.07 3.292c.3.921-.755 1.688-1.54 1.118l-2.8-2.034a1 1 0 00-1.175 0l-2.8 2.034c-.784.57-1.838-.197-1.539-1.118l1.07-3.292a1 1 0 00-.364-1.118L2.98 8.72c-.783-.57-.38-1.81.588-1.81h3.461a1 1 0 00.951-.69l1.07-3.292z"></path></svg>' for _ in range(q_diff)])
            
            questions_html += f'''
            <div class="border border-gray-200 rounded-xl overflow-hidden mb-6 bg-white shadow-sm">
                <!-- Header -->
                <div class="bg-slate-50 px-5 py-3 border-b border-gray-200 flex items-center justify-between">
                    <div class="flex items-center gap-3">
                        <span class="w-6 h-6 rounded-full bg-blue-100 text-blue-700 flex items-center justify-center text-xs font-bold">{q_slot}</span>
                        <span class="text-xs font-bold text-slate-700 uppercase tracking-wider">{q_domain}</span>
                        <span class="text-xs text-slate-400 px-2 border-l border-gray-300">{q_type}</span>
                        {badge_html}
                    </div>
                    <div class="flex items-center gap-1">
                        {diff_stars}
                    </div>
                </div>
                
                <!-- Side-by-Side Content -->
                <div class="grid grid-cols-1 md:grid-cols-2 divide-y md:divide-y-0 md:divide-x divide-gray-200">
                    <!-- Payload (Candidate View) -->
                    <div class="p-5">
                        <h4 class="text-[11px] font-bold text-slate-500 uppercase tracking-wider mb-3">Candidate Payload</h4>
                        <p class="text-sm text-slate-900 font-medium mb-4">{q_text}</p>
                        '''
                        
            if q_type == "mcq" and "options" in q:
                options = q.get("options", [])
                questions_html += '<div class="space-y-2">'
                for opt in options:
                    questions_html += f'<div class="px-3 py-2 border border-gray-100 rounded bg-gray-50 text-xs text-slate-700">{html.escape(opt)}</div>'
                questions_html += '</div>'
                
            questions_html += f'''
                    </div>
                    <!-- Rubric (Evaluator View) -->
                    <div class="p-5 bg-blue-50/30">
                        <h4 class="text-[11px] font-bold text-blue-600 uppercase tracking-wider mb-3">Evaluator Rubric (Hidden)</h4>
                        <div class="mb-4">
                            <span class="text-xs font-semibold text-slate-500 block mb-1">Expected Answer:</span>
                            <div class="px-3 py-2 border border-emerald-200 rounded bg-emerald-50 text-xs font-medium text-emerald-800">{q_answer}</div>
                        </div>
                        <div>
                            <span class="text-xs font-semibold text-slate-500 block mb-1">Scoring Criteria:</span>
                            <p class="text-[13px] text-slate-700 leading-relaxed">{q_rubric}</p>
                        </div>
                    </div>
                </div>
            </div>
            '''

    html_content = f'''
    <div class="fixed inset-0 z-50 flex h-screen w-full bg-slate-50 overflow-hidden font-sans text-slate-900" x-data="{{ sidebarOpen: false }}">
{get_admin_sidebar("candidates")}

      <!-- Main Content Wrapper -->
      <div class="flex-1 flex flex-col min-w-0 bg-slate-50">
          <!-- Global Header -->
          <header class="h-16 bg-white border-b border-gray-200 shadow-sm flex items-center justify-between px-6 shrink-0 z-10">
              <div class="flex items-center gap-4">
                  <button @click="sidebarOpen = !sidebarOpen" class="lg:hidden p-2 text-slate-500 hover:text-slate-900 rounded-md">
                      <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 6h16M4 12h16M4 18h16"></path></svg>
                  </button>
                  <div class="relative max-w-md w-full hidden sm:block">
                      <svg class="absolute left-3 top-2.5 w-4 h-4 text-slate-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"></path></svg>
                      <input type="text" placeholder="Search Candidate Profiles..." class="w-96 h-9 pl-9 pr-4 bg-slate-100/50 border border-transparent rounded-md text-sm text-slate-900 placeholder-slate-400 focus:bg-white focus:border-blue-500 focus:ring-1 focus:ring-blue-500 transition-all">
                  </div>
              </div>
          </header>

          <!-- Scrollable Page Content -->
          <main class="flex-1 overflow-y-auto p-8">
              <div class="max-w-7xl mx-auto w-full">
                  
                  <div class="flex justify-between items-end mb-6">
                      <div>
                          <h2 class="text-2xl font-extrabold text-slate-900 tracking-tight">Candidate Profiles</h2>
                          <p class="text-slate-500 text-sm mt-1">Review AI-extracted profiles, expected levels, and competency matrices.</p>
                      </div>
                      <button class="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white text-xs font-bold rounded-lg shadow-sm transition-colors flex items-center gap-2">
                          <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"></path></svg>
                          Sync Candidates
                      </button>
                  </div>

                  <div class="bg-white rounded-[12px] shadow-sm border border-gray-200 overflow-hidden">
                      <div class="overflow-x-auto">
                          <table class="w-full text-left border-collapse">
                              <thead>
                                  <tr class="bg-slate-50 border-b border-gray-200 text-xs font-bold text-slate-500 uppercase tracking-wider">
                                      <th class="px-6 py-4">Candidate</th>
                                      <th class="px-6 py-4">Resume ID</th>
                                      <th class="px-6 py-4">Est. Level</th>
                                      <th class="px-6 py-4">Date Parsed</th>
                                      <th class="px-6 py-4 text-right">Actions</th>
                                  </tr>
                              </thead>
                              <tbody class="bg-white divide-y divide-gray-100">
                                  {table_rows}
                              </tbody>
                          </table>
                      </div>
                      <!-- Pagination footer -->
                      <div class="px-6 py-4 border-t border-gray-200 bg-slate-50 flex items-center justify-between">
                          <p class="text-xs text-slate-500">Showing all {len(candidates)} candidates.</p>
                      </div>
                  </div>
                  
              </div>
          </main>
      </div>
    </div>
    '''
    return HTMLResponse(content=html_content)


# ----------------------------------------------------------------------
# Admin Detailed Audit Trail (5-Tab UI) - Tab 1: Profile & Mapping
# ----------------------------------------------------------------------
@admin_router.get("/audit/{resume_id}", response_class=HTMLResponse)
async def admin_audit_dashboard(resume_id: int, request: Request, session: AsyncSession = Depends(get_session)):
    admin_id = request.cookies.get("admin_id")
    if not admin_id:
      return HTMLResponse("<script>window.location.href = '/admin/login';</script>")

    res = await session.execute(text("CALL GetAuditProfile(:r_id)"), {"r_id": resume_id})
    audit_data = res.mappings().first()
    
    if not audit_data:
      return HTMLResponse("<div class='p-8 text-center text-red-500 font-bold'>Audit data not found for this candidate.</div>")
    
    import json
    import html
    prof = json.loads(audit_data["profile_json"]) if audit_data["profile_json"] else {}
    ai2_html = prof.get("ai2_narrative_html", "<div class='text-slate-500'>Profile narrative pending generation...</div>")
    

    # --- Tab 2: Blueprint Data Fetching ---
    bp_res = await session.execute(text("CALL GetAssessmentBlueprint(:r_id)"), {"r_id": resume_id})
    bp_row = bp_res.mappings().first()
    blueprint_json = {}
    if bp_row and bp_row.get("blueprint_json"):
        try:
            blueprint_json = json.loads(bp_row["blueprint_json"])
        except json.JSONDecodeError:
            pass
            
    bp_slots = blueprint_json.get("blueprint_slots", [])
    total_slots = len(bp_slots)
    
    from collections import Counter
    comp_counter = Counter(s.get("competency", "Unknown") for s in bp_slots)
    type_counter = Counter(s.get("question_type", "Unknown") for s in bp_slots)
    
    # Generate HTML for Competency Breakdown
    comp_html = ""
    if not bp_slots:
        comp_html = "<div class=\'text-sm text-slate-500 italic text-center py-4\'>Blueprint not generated yet.</div>"
    else:
        for comp, count in comp_counter.most_common():
            pct = int((count / total_slots) * 100)
            comp_html += f'''
            <div class="mb-3 last:mb-0">
                <div class="flex justify-between text-sm mb-1">
                    <span class="font-bold text-slate-700">{html.escape(comp)}</span>
                    <span class="text-slate-500 font-medium">{count} slots ({pct}%)</span>
                </div>
                <div class="w-full bg-slate-100 rounded-full h-1.5">
                    <div class="bg-blue-600 h-1.5 rounded-full" style="width: {pct}%"></div>
                </div>
            </div>
            '''
            
    # Generate HTML for Question Types
    type_html = ""
    if not bp_slots:
        type_html = "<div class='text-sm text-slate-500 italic text-center py-4'>Blueprint not generated yet.</div>"
    else:
        for qtype, count in type_counter.most_common():
            pct = int((count / total_slots) * 100)
            type_html += f'''
            <div class="mb-3 last:mb-0">
                <div class="flex justify-between text-sm mb-1">
                    <span class="font-bold text-slate-700">{html.escape(qtype)}</span>
                    <span class="text-slate-500 font-medium">{count} slots ({pct}%)</span>
                </div>
                <div class="w-full bg-slate-100 rounded-full h-1.5">
                    <div class="bg-indigo-500 h-1.5 rounded-full" style="width: {pct}%"></div>
                </div>
            </div>
            '''
            
    # Generate HTML for the 20-Slot Matrix Table
    slots_html = ""
    if not bp_slots:
        slots_html = "<tr><td colspan='5' class='px-5 py-12 text-center text-sm text-slate-500 italic'>Waiting for AI-3 Blueprint Generation.</td></tr>"
    else:
        for slot in bp_slots:
            slot_id = slot.get("slot_id", "-")
            comp = html.escape(slot.get("competency", ""))
            sub_comp = html.escape(slot.get("sub_competency", ""))
            qtype = html.escape(slot.get("question_type", ""))
            diff = slot.get("difficulty", 1)
            diff_stars = "★" * diff + "☆" * (5 - diff)
            claim = html.escape(slot.get("resume_claim_being_verified", ""))
            
            slots_html += f'''
            <tr class="border-b border-gray-50 last:border-0 hover:bg-slate-50/50 transition-colors">
                <td class="px-5 py-4 font-bold text-slate-900">#{slot_id}</td>
                <td class="px-5 py-4">
                    <div class="font-bold text-slate-700">{comp}</div>
                    <div class="text-xs text-slate-500 mt-0.5">{sub_comp}</div>
                </td>
                <td class="px-5 py-4">
                    <span class="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-slate-100 text-slate-700 border border-slate-200">
                        {qtype}
                    </span>
                </td>
                <td class="px-5 py-4 text-amber-500 text-xs tracking-widest">{diff_stars}</td>
                <td class="px-5 py-4 text-slate-600 italic text-sm line-clamp-2 max-w-sm" title="{claim}">
                    "{claim}"
                </td>
            </tr>
            '''

    # Modular Data Extraction
    competencies = prof.get("competency_mapping", prof.get("capability_mapping", prof.get("competencies", [])))
    flags = prof.get("flags", [])
    
    # Sort competencies by confidence
    high_conf = [c for c in competencies if c.get("confidence", 0) >= 85]
    verify_prio = [c for c in competencies if c.get("confidence", 0) < 85]
    
    # Build Modular Widgets HTML
    
    # 1. Verification Priorities Widget
    vp_html = ""
    for c in verify_prio:
      domain = html.escape(c.get("domain", "Unknown"))
      vp_list = c.get("verification_priorities", [])
      vp_text = html.escape(vp_list[0]) if vp_list else "Verification required during assessment."
      vp_html += f'''
      <div class="p-4 rounded-lg border border-amber-100 bg-amber-50/20 flex gap-3 mb-3 last:mb-0">
          <div class="mt-1"><div class="w-1.5 h-1.5 rounded-full bg-amber-400"></div></div>
          <div>
              <p class="text-sm font-bold text-slate-900">{domain}</p>
              <p class="text-sm text-slate-600 leading-snug mt-1">{vp_text}</p>
          </div>
      </div>
      '''
    if not vp_html:
      vp_html = '''
      <div class="flex flex-col items-center justify-center p-8 bg-slate-50 rounded-lg border border-slate-100 border-dashed">
          <svg class="w-8 h-8 text-slate-300 mb-2" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z"></path></svg>
          <p class="text-sm font-medium text-slate-400">No verification priorities flagged</p>
      </div>'''
      
    # 2. High Confidence Competencies Widget
    hc_html = ""
    for c in high_conf:
      domain = html.escape(c.get("domain", "Unknown"))
      conf = c.get("confidence", 0)
      evidence = html.escape(c.get("evidence", ""))
      hc_html += f'''
      <div class="p-4 rounded-lg border border-gray-100 bg-slate-50/50 flex flex-col justify-between">
          <div class="flex justify-between items-start mb-2">
              <span class="text-sm font-bold text-slate-900">{domain}</span>
              <span class="inline-flex items-center px-2 py-0.5 rounded text-[10px] font-bold bg-emerald-50 text-emerald-700 border border-emerald-100">{conf}% Match</span>
          </div>
          <p class="text-xs text-slate-500 leading-snug">{evidence}</p>
      </div>
      '''
    if not hc_html:
      hc_html = '''
      <div class="col-span-full flex flex-col items-center justify-center p-8 bg-slate-50 rounded-lg border border-slate-100 border-dashed">
          <svg class="w-8 h-8 text-slate-300 mb-2" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10"></path></svg>
          <p class="text-sm font-medium text-slate-400">No high-confidence competencies identified</p>
      </div>'''
      
    # 3. Flags Widget
    flags_html = ""
    for flag in flags:
      flags_html += f'''
      <div class="pl-3 py-1.5 border-l-4 border-rose-400 mb-3 last:mb-0">
          <p class="text-sm text-slate-700 leading-snug">{html.escape(flag)}</p>
      </div>
      '''
    if not flags_html:
      flags_html = '''
      <div class="flex flex-col items-center justify-center py-6">
          <div class="w-8 h-8 rounded-full bg-slate-50 flex items-center justify-center mb-2 border border-slate-100">
              <svg class="w-4 h-4 text-emerald-500" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"></path></svg>
          </div>
          <p class="text-sm text-slate-400 italic">No discrepancy flags detected.</p>
      </div>'''

    name = html.escape(audit_data.get("name") or "")
    email = html.escape(audit_data.get("email") or "")
    filename = html.escape(audit_data.get("filename") or "")
    
    # --- Tab 3: Question Generation & Integrity ---
    # Fetch AI assessment data
    ai_res = await session.execute(text("CALL GetAIAssessment(:r_id)"), {"r_id": resume_id})
    ai_row = ai_res.mappings().first()
    ai_data = {}
    if ai_row and ai_row.get("raw_json"):
        try:
            ai_data = json.loads(ai_row["raw_json"])
        except json.JSONDecodeError:
            pass
            
    ai4 = ai_data.get("ai4_json", {})
    ai5 = ai_data.get("ai5_json", {})
    
    # 1. AI-5 Integrity Logs HTML
    audit_log = ai5.get("audit_log", [])
    replaced_count = sum(1 for log in audit_log if log.get("status") == "REPLACE")
    total_audited = len(audit_log)
    
    integrity_html = ""
    if total_audited == 0:
        integrity_html = "<div class='text-sm text-slate-500 italic text-center py-4'>Integrity logs not generated yet.</div>"
    else:
        for log in audit_log:
            status = log.get("status")
            slot = log.get("slot_id")
            reason = log.get("defect_reason")
            
            if status == "REPLACE":
                integrity_html += f'''
                <div class="flex items-start gap-3 p-3 border-l-4 border-amber-500 bg-amber-50/50 rounded-r-lg mb-2">
                    <svg class="w-5 h-5 text-amber-500 mt-0.5 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"></path></svg>
                    <div>
                        <p class="text-[13px] font-bold text-amber-900">Slot #{slot} Rejected</p>
                        <p class="text-[12px] text-amber-700 mt-0.5">{html.escape(reason or "Unknown reason")}</p>
                    </div>
                </div>
                '''
            else:
                integrity_html += f'''
                <div class="flex items-center gap-3 p-3 border-l-4 border-emerald-500 bg-emerald-50/50 rounded-r-lg mb-2">
                    <svg class="w-5 h-5 text-emerald-500 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"></path></svg>
                    <p class="text-[13px] font-bold text-emerald-900">Slot #{slot} Approved</p>
                </div>
                '''

    # 2. Side-by-Side Question Viewer
    final_questions = ai5.get("final_questions", [])
    if not final_questions and ai4.get("questions"):
        final_questions = ai4.get("questions")
        
    questions_html = ""
    if not final_questions:
        questions_html = "<div class='text-sm text-slate-500 italic text-center py-4'>Questions not generated yet.</div>"
    else:
        for q in final_questions:
            q_slot = q.get("slot_id")
            q_domain = html.escape(q.get("domain", ""))
            q_text = html.escape(q.get("question", ""))
            q_type = html.escape(q.get("question_type", ""))
            q_answer = html.escape(q.get("answer", ""))
            q_rubric = html.escape(q.get("rubric", ""))
            q_diff = q.get("difficulty", 1)
            
            # Check if this slot was replaced by AI-5
            is_replaced = any(log.get("slot_id") == q_slot and log.get("status") == "REPLACE" for log in audit_log)
            badge_html = f'<span class="bg-amber-100 text-amber-700 px-2 py-0.5 rounded text-[10px] font-bold uppercase tracking-wider ml-2">Replaced by AI-5</span>' if is_replaced else ''
            
            diff_stars = "".join(['<svg class="w-3.5 h-3.5 text-amber-400 inline" fill="currentColor" viewBox="0 0 20 20"><path d="M9.049 2.927c.3-.921 1.603-.921 1.902 0l1.07 3.292a1 1 0 00.95.69h3.462c.969 0 1.371 1.24.588 1.81l-2.8 2.034a1 1 0 00-.364 1.118l1.07 3.292c.3.921-.755 1.688-1.54 1.118l-2.8-2.034a1 1 0 00-1.175 0l-2.8 2.034c-.784.57-1.838-.197-1.539-1.118l1.07-3.292a1 1 0 00-.364-1.118L2.98 8.72c-.783-.57-.38-1.81.588-1.81h3.461a1 1 0 00.951-.69l1.07-3.292z"></path></svg>' for _ in range(q_diff)])
            
            questions_html += f'''
            <div class="border border-gray-200 rounded-xl overflow-hidden mb-6 bg-white shadow-sm">
                <!-- Header -->
                <div class="bg-slate-50 px-5 py-3 border-b border-gray-200 flex items-center justify-between">
                    <div class="flex items-center gap-3">
                        <span class="w-6 h-6 rounded-full bg-blue-100 text-blue-700 flex items-center justify-center text-xs font-bold">{q_slot}</span>
                        <span class="text-xs font-bold text-slate-700 uppercase tracking-wider">{q_domain}</span>
                        <span class="text-xs text-slate-400 px-2 border-l border-gray-300">{q_type}</span>
                        {badge_html}
                    </div>
                    <div class="flex items-center gap-1">
                        {diff_stars}
                    </div>
                </div>
                
                <!-- Side-by-Side Content -->
                <div class="grid grid-cols-1 md:grid-cols-2 divide-y md:divide-y-0 md:divide-x divide-gray-200">
                    <!-- Payload (Candidate View) -->
                    <div class="p-5">
                        <h4 class="text-[11px] font-bold text-slate-500 uppercase tracking-wider mb-3">Candidate Payload</h4>
                        <p class="text-sm text-slate-900 font-medium mb-4">{q_text}</p>
                        '''
                        
            if q_type == "mcq" and "options" in q:
                options = q.get("options", [])
                questions_html += '<div class="space-y-2">'
                for opt in options:
                    questions_html += f'<div class="px-3 py-2 border border-gray-100 rounded bg-gray-50 text-xs text-slate-700">{html.escape(opt)}</div>'
                questions_html += '</div>'
                
            questions_html += f'''
                    </div>
                    <!-- Rubric (Evaluator View) -->
                    <div class="p-5 bg-blue-50/30">
                        <h4 class="text-[11px] font-bold text-blue-600 uppercase tracking-wider mb-3">Evaluator Rubric (Hidden)</h4>
                        <div class="mb-4">
                            <span class="text-xs font-semibold text-slate-500 block mb-1">Expected Answer:</span>
                            <div class="px-3 py-2 border border-emerald-200 rounded bg-emerald-50 text-xs font-medium text-emerald-800">{q_answer}</div>
                        </div>
                        <div>
                            <span class="text-xs font-semibold text-slate-500 block mb-1">Scoring Criteria:</span>
                            <p class="text-[13px] text-slate-700 leading-relaxed">{q_rubric}</p>
                        </div>
                    </div>
                </div>
            </div>
            '''

    html_content = f'''
    <div class="fixed inset-0 z-50 flex h-screen w-full bg-slate-50 overflow-hidden font-sans text-slate-900" x-data="{{ sidebarOpen: false, activeTab: 'profile' }}">
      
{get_admin_sidebar("audit")}

      <!-- Main Content Wrapper -->
      <div class="flex-1 flex flex-col min-w-0 bg-slate-50">
          <!-- Global Header -->
          <header class="h-16 bg-white border-b border-gray-200 shadow-sm flex items-center px-6 shrink-0 z-10">
              <button @click="sidebarOpen = !sidebarOpen" class="lg:hidden p-2 mr-4 text-slate-500 hover:text-slate-900 rounded-md">
                  <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 6h16M4 12h16M4 18h16"></path></svg>
              </button>
              <div class="flex items-center gap-3 text-sm font-medium text-slate-500">
                  <a href="/admin/Candidates" hx-get="/admin/Candidates" hx-target="#main-content" hx-push-url="true" class="hover:text-blue-600 transition-colors">Candidates</a>
                  <svg class="w-4 h-4 text-slate-300" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7"></path></svg>
                  <span class="text-slate-900">Audit Trail: {name}</span>
              </div>
          </header>

          <!-- Scrollable Page Content -->
          <main class="flex-1 overflow-y-auto bg-slate-50">
              
              <!-- Horizontal Tab Navigation -->
              <div class="bg-white border-b border-gray-200 px-8 pt-8">
                  <div class="max-w-6xl mx-auto w-full">
                      <div class="mb-6">
                          <h2 class="text-3xl font-extrabold text-slate-900 tracking-tight">Audit Trail: {name}</h2>
                          <p class="text-slate-500 text-sm mt-1">Candidate #{resume_id} &bull; {filename}</p>
                      </div>
                      <nav class="flex space-x-8" aria-label="Tabs">
                          <a href="#" @click.prevent="activeTab = 'profile'"
                             :class="activeTab === 'profile' ? 'border-blue-500 text-blue-600' : 'border-transparent text-slate-500 hover:text-slate-700 hover:border-gray-300'"
                             class="whitespace-nowrap py-4 px-1 border-b-2 font-medium text-sm transition-colors">
                              1. Profile & Mapping
                          </a>
                          <a href="#" @click.prevent="activeTab = 'blueprint'"
                             :class="activeTab === 'blueprint' ? 'border-blue-500 text-blue-600' : 'border-transparent text-slate-500 hover:text-slate-700 hover:border-gray-300'"
                             class="whitespace-nowrap py-4 px-1 border-b-2 font-medium text-sm transition-colors">
                              2. Blueprint
                          </a>
                          <a href="#" @click.prevent="activeTab = 'generation'"
                             :class="activeTab === 'generation' ? 'border-blue-500 text-blue-600' : 'border-transparent text-slate-500 hover:text-slate-700 hover:border-gray-300'"
                             class="whitespace-nowrap py-4 px-1 border-b-2 font-medium text-sm transition-colors">
                              3. Generation
                          </a>
                          <a href="#" @click.prevent="activeTab = 'evaluation'"
                             :class="activeTab === 'evaluation' ? 'border-blue-500 text-blue-600' : 'border-transparent text-slate-500 hover:text-slate-700 hover:border-gray-300'"
                             class="whitespace-nowrap py-4 px-1 border-b-2 font-medium text-sm transition-colors">
                              4. Evaluation
                          </a>
                          <a href="#" @click.prevent="activeTab = 'decision'"
                             :class="activeTab === 'decision' ? 'border-blue-500 text-blue-600' : 'border-transparent text-slate-500 hover:text-slate-700 hover:border-gray-300'"
                             class="whitespace-nowrap py-4 px-1 border-b-2 font-medium text-sm transition-colors">
                              5. Decision
                          </a>
                      </nav>
                  </div>
              </div>

              <div class="p-8">
                  <div class="max-w-6xl mx-auto w-full">
                  
                      <!-- TAB 1: PROFILE & MAPPING -->
                      <div x-show="activeTab === 'profile'" x-transition.opacity class="space-y-6">
                      
                      <!-- Top Row: 3 Equal Columns Grid -->
                      <div class="grid grid-cols-1 lg:grid-cols-3 gap-6">
                          
                          <!-- Input Source -->
                          <div class="bg-white rounded-xl shadow-sm border border-gray-200 flex flex-col">
                              <div class="px-5 py-3 border-b border-gray-100 flex items-center justify-between">
                                  <h3 class="text-[11px] font-bold text-slate-500 uppercase tracking-wider">Input Source</h3>
                                  <span class="w-2 h-2 rounded-full bg-slate-300"></span>
                              </div>
                              <div class="p-5 flex-grow flex items-center gap-4">
                                  <div class="w-12 h-12 rounded-lg bg-indigo-50 border border-indigo-100 flex items-center justify-center text-indigo-500 shrink-0">
                                      <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M7 21h10a2 2 0 002-2V9.414a1 1 0 00-.293-.707l-5.414-5.414A1 1 0 0012.586 3H7a2 2 0 00-2 2v14a2 2 0 002 2z"></path></svg>
                                  </div>
                                  <div class="w-full">
                                        <div class="flex items-center justify-between gap-4">
                                            <div>
                                                <p class="text-sm font-bold text-slate-900 break-all">{filename}</p>
                                                <p class="text-[11px] text-slate-400 mt-0.5 uppercase font-semibold">Uploaded Resume</p>
                                            </div>
                                            <a href="/admin/download-resume/{resume_id}" target="_blank" title="Download Resume" class="flex-shrink-0 inline-flex items-center justify-center w-10 h-10 bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg shadow-md hover:shadow-lg transition-all focus:ring-2 focus:ring-offset-2 focus:ring-indigo-500">
                                                <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"></path>
                                                </svg>
                                            </a>
                                        </div>
                                    </div>
                              </div>
                          </div>

                          <!-- Candidate Meta -->
                          <div class="bg-white rounded-xl shadow-sm border border-gray-200 flex flex-col">
                              <div class="px-5 py-3 border-b border-gray-100 flex items-center justify-between">
                                  <h3 class="text-[11px] font-bold text-slate-500 uppercase tracking-wider">Candidate Meta</h3>
                                  <span class="w-2 h-2 rounded-full bg-blue-500"></span>
                              </div>
                              <div class="p-5 flex-grow flex flex-col justify-center gap-3">
                                  <div class="flex items-center justify-between">
                                      <span class="text-xs text-slate-400 font-medium">Name</span>
                                      <span class="text-sm font-bold text-slate-900">{name}</span>
                                  </div>
                                  <div class="flex items-center justify-between">
                                      <span class="text-xs text-slate-400 font-medium">Email</span>
                                      <span class="text-sm font-bold text-slate-900 truncate max-w-[150px]">{email}</span>
                                  </div>
                                  <div class="flex items-center justify-between">
                                      <span class="text-xs text-slate-400 font-medium">Resume ID</span>
                                      <span class="text-sm font-bold text-slate-900">#{resume_id}</span>
                                  </div>
                              </div>
                          </div>

                          <!-- AI-1 Parsed Flags -->
                          <div class="bg-white rounded-xl shadow-sm border border-gray-200 flex flex-col">
                              <div class="px-5 py-3 border-b border-gray-100 flex items-center justify-between">
                                  <h3 class="text-[11px] font-bold text-slate-500 uppercase tracking-wider">AI-1 Parsed Flags</h3>
                                  <span class="w-2 h-2 rounded-full bg-rose-500"></span>
                              </div>
                              <div class="p-5 flex-grow overflow-y-auto max-h-[140px] custom-scrollbar">
                                  {flags_html}
                              </div>
                          </div>
                          
                      </div>
                      
                      <!-- Bottom Row: Full-width spanning cards -->
                      <div class="space-y-6">
                          <!-- Verification Targets -->
                          <div class="bg-white rounded-xl shadow-sm border border-gray-200">
                              <div class="px-5 py-3 border-b border-gray-100 flex items-center justify-between">
                                  <h3 class="text-[11px] font-bold text-slate-500 uppercase tracking-wider">Verification Targets (AI-6)</h3>
                                  <span class="w-2 h-2 rounded-full bg-amber-400"></span>
                              </div>
                              <div class="p-5">
                                  {vp_html}
                              </div>
                          </div>

                          <!-- Verified Domain Competencies -->
                          <div class="bg-white rounded-xl shadow-sm border border-gray-200">
                              <div class="px-5 py-3 border-b border-gray-100 flex items-center justify-between">
                                  <h3 class="text-[11px] font-bold text-slate-500 uppercase tracking-wider">Verified Domain Competencies (AI-2)</h3>
                                  <span class="w-2 h-2 rounded-full bg-emerald-500"></span>
                              </div>
                              <div class="p-5 grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                                  {hc_html}
                              </div>
                          </div>
                      </div>
                  </div>
                  
                  <!-- PLACEHOLDERS FOR OTHER TABS -->
                  <!-- TAB 2: BLUEPRINT -->
                  <div x-show="activeTab === 'blueprint'" x-transition.opacity class="space-y-6">
                      <div class="flex justify-between items-end mb-4">
                          <div>
                              <h2 class="text-2xl font-extrabold text-slate-900 tracking-tight">Tab 2: Assessment Blueprint</h2>
                              <p class="text-slate-500 text-sm mt-1">Audit the AI-3 dynamic 20-slot allocation matrix tailored to the candidate's core expertise.</p>
                          </div>
                      </div>
                      
                      <!-- Top Row: Blueprint Analytics -->
                      <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
                          <!-- Competency Breakdown -->
                          <div class="bg-white rounded-xl shadow-sm border border-gray-200 flex flex-col">
                              <div class="px-5 py-3 border-b border-gray-100 flex items-center justify-between">
                                  <h3 class="text-[11px] font-bold text-slate-500 uppercase tracking-wider">Competency Domain Skew</h3>
                              </div>
                              <div class="p-5 flex-grow">
                                  {comp_html}
                              </div>
                          </div>
                          
                          <!-- Question Type Breakdown -->
                          <div class="bg-white rounded-xl shadow-sm border border-gray-200 flex flex-col">
                              <div class="px-5 py-3 border-b border-gray-100 flex items-center justify-between">
                                  <h3 class="text-[11px] font-bold text-slate-500 uppercase tracking-wider">Format Distribution</h3>
                              </div>
                              <div class="p-5 flex-grow">
                                  {type_html}
                              </div>
                          </div>
                      </div>
                      
                      <!-- 20-Slot Allocation Matrix -->
                      <div class="bg-white rounded-xl shadow-sm border border-gray-200 overflow-hidden">
                          <div class="px-5 py-3 border-b border-gray-100 flex items-center justify-between bg-slate-50/50">
                              <h3 class="text-[11px] font-bold text-slate-500 uppercase tracking-wider">20-Slot Allocation Matrix</h3>
                              <span class="text-xs font-bold text-blue-600 bg-blue-50 px-2 py-0.5 rounded-full border border-blue-100">{total_slots} Slots Generated</span>
                          </div>
                          <div class="overflow-x-auto">
                              <table class="w-full text-left border-collapse">
                                  <thead>
                                      <tr class="bg-white border-b border-gray-100 text-[10px] font-bold text-slate-400 uppercase tracking-wider">
                                          <th class="px-5 py-3">Slot #</th>
                                          <th class="px-5 py-3">Domain</th>
                                          <th class="px-5 py-3">Format</th>
                                          <th class="px-5 py-3">Difficulty</th>
                                          <th class="px-5 py-3">Target Verification Claim</th>
                                      </tr>
                                  </thead>
                                  <tbody class="text-sm">
                                      {slots_html}
                                  </tbody>
                              </table>
                          </div>
                      </div>
                  </div>
                  <!-- TAB 3: GENERATION & INTEGRITY -->
                    <div x-show="activeTab === 'generation'" x-transition.opacity class="space-y-6">
                        <div class="flex justify-between items-end mb-4">
                            <div>
                                <h2 class="text-2xl font-extrabold text-slate-900 tracking-tight">Tab 3: Generation & Integrity</h2>
                                <p class="text-slate-500 text-sm mt-1">Audit the AI-4 generated questions and the AI-5 security/integrity filtering logs.</p>
                            </div>
                        </div>
                        
                        <div class="grid grid-cols-1 lg:grid-cols-4 gap-6">
                            <!-- Left Sidebar: AI-5 Integrity Logs -->
                            <div class="lg:col-span-1">
                                <div class="bg-white rounded-xl shadow-sm border border-gray-200 flex flex-col h-full">
                                    <div class="px-5 py-3 border-b border-gray-100 flex items-center justify-between">
                                        <h3 class="text-[11px] font-bold text-slate-500 uppercase tracking-wider">AI-5 Integrity Overview</h3>
                                    </div>
                                    <div class="p-5 bg-slate-50/50 border-b border-gray-100 flex items-center justify-between">
                                        <div class="text-center">
                                            <p class="text-2xl font-bold text-slate-800">{total_audited}</p>
                                            <p class="text-[10px] font-bold text-slate-500 uppercase tracking-wider">Audited</p>
                                        </div>
                                        <div class="text-center">
                                            <p class="text-2xl font-bold text-emerald-600">{total_audited - replaced_count}</p>
                                            <p class="text-[10px] font-bold text-emerald-600 uppercase tracking-wider">Approved</p>
                                        </div>
                                        <div class="text-center">
                                            <p class="text-2xl font-bold text-amber-500">{replaced_count}</p>
                                            <p class="text-[10px] font-bold text-amber-500 uppercase tracking-wider">Replaced</p>
                                        </div>
                                    </div>
                                    <div class="p-4 flex-grow overflow-y-auto max-h-[600px]">
                                        {integrity_html}
                                    </div>
                                </div>
                            </div>
                            
                            <!-- Right Content: Side-by-Side Questions -->
                            <div class="lg:col-span-3">
                                {questions_html}
                            </div>
                        </div>
                    </div>
                    <div x-show="activeTab === 'evaluation'" x-transition.opacity class="bg-white rounded-xl shadow-sm border border-gray-200 p-16 text-center">
                      <div class="w-16 h-16 bg-slate-50 rounded-2xl mx-auto flex items-center justify-center border border-gray-100 mb-4 shadow-sm">
                          <svg class="w-8 h-8 text-slate-300" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10"></path></svg>
                      </div>
                      <h2 class="text-lg font-bold text-slate-800 mb-2">Tab 4: Evaluation</h2>
                      <p class="text-slate-500 text-sm">This tab will display AI-6 grading and suspicious pattern flags.</p>
                  </div>
                  <div x-show="activeTab === 'decision'" x-transition.opacity class="bg-white rounded-xl shadow-sm border border-gray-200 p-16 text-center">
                      <div class="w-16 h-16 bg-slate-50 rounded-2xl mx-auto flex items-center justify-center border border-gray-100 mb-4 shadow-sm">
                          <svg class="w-8 h-8 text-slate-300" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10"></path></svg>
                      </div>
                      <h2 class="text-lg font-bold text-slate-800 mb-2">Tab 5: Decision</h2>
                      <p class="text-slate-500 text-sm">This tab will display AI-7 thresholds and final certification.</p>
                  </div>

              </div>
          </main>
      </div>
    </div>
    '''
    return HTMLResponse(content=html_content)
