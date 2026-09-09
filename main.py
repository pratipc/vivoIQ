from fastapi import FastAPI, Request, UploadFile, File, Form, Depends
from fastapi.responses import HTMLResponse, Response
from fastapi.templating import Jinja2Templates
from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select
from sqlalchemy import text
import sys
import os
import io
import base64
import qrcode
import PyPDF2
import google.generativeai as genai
import json

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from database import init_db, get_session
from models import Resume, User

load_dotenv(dotenv_path="../.env")

app = FastAPI(title="VivoIQ Assessment Service")
templates = Jinja2Templates(directory="templates")

@app.on_event("startup")
async def on_startup():
    await init_db()

@app.get("/assessment/onboarding", response_class=HTMLResponse)
async def assessment_onboarding(request: Request, session: AsyncSession = Depends(get_session)):
    """
    Returns the HTML fragment for Stage 2: Assessment Choice & Scheduling.
    This includes the Resume Upload step, and the Immediate vs Deferred choice.
    """
    user_id_cookie = request.cookies.get("user_id")
    if user_id_cookie:
        from sqlalchemy import text
        result = await session.execute(text("CALL GetUserStage(:u_id)"), {"u_id": user_id_cookie})
        user_row = result.mappings().first()
        
        if user_row and user_row["stage"] == "Results":
            r_result = await session.execute(
                text("CALL GetLatestResumeId(:u_id)"),
                {"u_id": user_id_cookie}
            )
            r_row = r_result.mappings().first()
            if r_row:
                new_resume_id = r_row["id"]
                if request.headers.get("hx-request"):
                    from fastapi.responses import Response
                    res = Response()
                    res.headers["HX-Redirect"] = f"/assessment/results?resume_id={new_resume_id}"
                    return res
                else:
                    from fastapi.responses import RedirectResponse
                    return RedirectResponse(url=f"/assessment/results?resume_id={new_resume_id}", status_code=303)
                
        if user_row and user_row["stage"] == "Test":
            sch_result = await session.execute(
                text("CALL GetLatestAssessmentSchedule(:u_id)"),
                {"u_id": user_id_cookie}
            )
            sch_row = sch_result.mappings().first()
            
            if sch_row:
                msg_title = "Test Scheduled!"
                msg_body = f"We will email you a secure link to take the test on {sch_row['scheduled_date']} at {sch_row['scheduled_time']}."
                btn_html = """<button class="w-full h-10 bg-white border border-gray-300 hover:bg-gray-50 text-gray-700 text-[13px] font-medium rounded-[8px] shadow-sm transition-colors">Return to Dashboard</button>"""
                
                return HTMLResponse(content=f"""
                <div class="absolute top-6 right-8 z-50 animate-fade-in">
                    <a href="/users/logout" class="text-[13px] font-semibold text-gray-400 hover:text-vivo-brand transition-colors flex items-center gap-1.5 cursor-pointer">
                        <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1"></path></svg> 
                        Log out
                    </a>
                </div>
                <div class="w-full animate-fade-in-up max-w-lg mx-auto">
                    <!-- Progress tracker elements omitted for brevity in response -->
                    <div class="w-[520px] mx-auto bg-white rounded-[12px] shadow-sm border border-gray-200 p-8 flex flex-col items-center justify-center text-center">
                        <h2 class="text-2xl font-bold text-vivo-navy mb-2 tracking-tight">{msg_title}</h2>
                        <p class="text-[13px] text-gray-500 mb-6 leading-relaxed">We successfully processed your resume. {msg_body}</p>
                        {btn_html}
                    </div>
                </div>
                """)
            else:
                # If they chose "Evaluate Now" but refreshed the page, seamlessly restore their state
                r_result = await session.execute(
                    text("CALL GetLatestResumeId(:u_id)"),
                    {"u_id": user_id_cookie}
                )
                r_row = r_result.mappings().first()
                new_resume_id = r_row["id"] if r_row else 0
                
                # Check if profile is already built
                prof_check = await session.execute(
                    text("CALL GetCandidateProfile(:r_id)"),
                    {"r_id": new_resume_id}
                )
                
                if prof_check.mappings().first():
                    from fastapi.responses import RedirectResponse
                    return RedirectResponse(url=f"/assessment/build-profile?resume_id={new_resume_id}", status_code=303)
                
                return HTMLResponse(content=f"""
                <div class="absolute top-6 right-8 z-50 animate-fade-in">
                    <a href="/users/logout" class="text-[13px] font-semibold text-gray-400 hover:text-vivo-brand transition-colors flex items-center gap-1.5 cursor-pointer">
                        <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1"></path></svg> 
                        Log out
                    </a>
                </div>
                <div class="w-full min-h-[60vh] flex flex-col items-center justify-center animate-fade-in-up">
                    <div class="w-16 h-16 bg-blue-50/50 rounded-[16px] flex items-center justify-center mb-6 shadow-sm border border-blue-100 relative">
                        <svg class="w-8 h-8 text-vivo-brand animate-pulse" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2"></path>
                        </svg>
                        <div class="absolute -bottom-1 -right-1 w-4 h-4 bg-green-500 rounded-full border-2 border-white"></div>
                    </div>
                    <h2 class="text-[22px] font-bold text-vivo-navy tracking-tight mb-5">Analyzing Resume</h2>
                    
                    <!-- Dynamic Text & Progress Bar -->
                    <div class="w-full max-w-[320px]">
                        <div class="flex justify-between items-center mb-2">
                            <span id="ai-status-text" class="text-[12px] font-medium text-gray-500 transition-opacity duration-300">Extracting professional experience...</span>
                            <span id="ai-progress-pct" class="text-[12px] font-bold text-vivo-brand">0%</span>
                        </div>
                        <div class="w-full h-2 bg-gray-100 rounded-full overflow-hidden">
                            <div id="ai-progress-bar" class="h-full bg-vivo-brand rounded-full transition-all duration-500 ease-out" style="width: 0%"></div>
                        </div>
                    </div>
                    
                    <!-- JavaScript for Dynamic Messaging and Progress -->
                    <script>
                    (function() {{
                        const statuses = [
                            "Extracting professional experience...",
                            "Mapping skills to VivoIQ framework...",
                            "Calibrating assessment difficulty...",
                            "Structuring personalized blueprint...",
                            "Finalizing capability profile..."
                        ];
                        let statusIdx = 0;
                        const textEl = document.getElementById("ai-status-text");
                        const barEl = document.getElementById("ai-progress-bar");
                        const pctEl = document.getElementById("ai-progress-pct");
                        
                        // Cycle text every 3.5 seconds
                        const textInterval = setInterval(() => {{
                            if (statusIdx < statuses.length - 1) statusIdx++;
                            if(textEl) {{
                                textEl.style.opacity = '0';
                                setTimeout(() => {{
                                    textEl.textContent = statuses[statusIdx];
                                    textEl.style.opacity = '1';
                                }}, 300);
                            }}
                        }}, 3500);
                        
                        // Simulate progress up to 99% over 30 seconds
                        let progress = 0;
                        const totalDuration = 30000;
                        const intervalTime = 500;
                        const progressIncrement = (99 / (totalDuration / intervalTime));
                        
                        const progInterval = setInterval(() => {{
                            progress += progressIncrement;
                            if(progress > 99) progress = 99;
                            if(barEl) barEl.style.width = progress + '%';
                            if(pctEl) pctEl.textContent = Math.floor(progress) + '%';
                        }}, intervalTime);
                        
                        // Cleanup
                        document.body.addEventListener("htmx:beforeSwap", function cleanup() {{
                            clearInterval(textInterval);
                            clearInterval(progInterval);
                            document.body.removeEventListener("htmx:beforeSwap", cleanup);
                        }});
                    }})();
                    </script>
                    
                    <!-- Triggers generation immediately on load -->
                    <div hx-get="/assessment/build-profile?resume_id={new_resume_id}" hx-trigger="load" hx-target="#main-content" class="hidden"></div>
                </div>
                """)
            
    html_content = """
    <div class="absolute top-6 right-8 z-50 animate-fade-in">
        <a href="/users/logout" class="text-[13px] font-semibold text-gray-400 hover:text-vivo-brand transition-colors flex items-center gap-1.5 cursor-pointer">
            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1"></path></svg> 
            Log out
        </a>
    </div>
    <div class="w-full animate-fade-in-up max-w-lg mx-auto">
        <!-- Progress Tracker (64px tall) -->
        <div class="flex items-center justify-center mb-10 h-16 w-full px-12">
            <!-- Account (Completed) -->
            <div class="flex flex-col items-center relative z-10 w-8">
                <div class="w-6 h-6 rounded-full bg-blue-500 text-white flex items-center justify-center text-[10px] shadow-sm">
                    <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M5 13l4 4L19 7"></path></svg>
                </div>
                <span class="text-[11px] font-medium text-gray-500 mt-2 absolute top-6 whitespace-nowrap">Account</span>
            </div>
            
            <div class="flex-grow h-[2px] bg-blue-500 mx-2"></div>
            
            <!-- Resume (Current) -->
            <div class="flex flex-col items-center relative z-10 w-8">
                <div class="w-6 h-6 rounded-full bg-blue-500 text-white flex items-center justify-center shadow-sm">
                    <div class="w-2 h-2 rounded-full bg-white"></div>
                </div>
                <span class="text-[11px] font-semibold text-vivo-navy mt-2 absolute top-6 whitespace-nowrap">Resume</span>
            </div>
            
            <div class="flex-grow h-[2px] bg-gray-200 mx-2"></div>
            
            <!-- Test (Upcoming) -->
            <div class="flex flex-col items-center relative z-10 w-8">
                <div class="w-6 h-6 rounded-full bg-white border-[2px] border-gray-200 text-gray-300 flex items-center justify-center">
                </div>
                <span class="text-[11px] font-medium text-gray-400 mt-2 absolute top-6 whitespace-nowrap">Assessment</span>
            </div>
            
            <div class="flex-grow h-[2px] bg-gray-200 mx-2"></div>
            
            <!-- Results (Upcoming) -->
            <div class="flex flex-col items-center relative z-10 w-8">
                <div class="w-6 h-6 rounded-full bg-white border-[2px] border-gray-200 text-gray-300 flex items-center justify-center">
                </div>
                <span class="text-[11px] font-medium text-gray-400 mt-2 absolute top-6 whitespace-nowrap">Results</span>
            </div>
        </div>
        
        <!-- Drag & Drop Upload Card -->
        <div class="w-[420px] mx-auto bg-white rounded-[12px] shadow-sm border border-gray-200 p-8 flex flex-col items-center justify-center text-center">
            
            <div class="mb-5 w-full">
                <h2 class="text-[18px] font-bold text-vivo-navy mb-1.5 tracking-tight">Upload your resume</h2>
                <p class="text-[12px] text-gray-500 leading-relaxed px-1">We'll use it to personalize your assessment based on your skills and experience.</p>
            </div>
            
            <form hx-post="/assessment/upload-resume" hx-encoding="multipart/form-data" hx-target="#main-content" class="w-full">
                
                <div class="relative w-full h-[150px] border-[2px] border-dashed border-gray-300 hover:border-vivo-brand rounded-[8px] bg-gray-50/50 hover:bg-blue-50/30 transition-all flex flex-col items-center justify-center group cursor-pointer mb-6 overflow-hidden">
                    
                    <input type="file" name="resume" class="absolute inset-0 w-full h-full opacity-0 cursor-pointer z-20" accept=".pdf,.doc,.docx" required onchange="updateFileName(this)" />
                    
                    <div id="upload-prompt" class="flex flex-col items-center pointer-events-none">
                        <div class="text-gray-400 group-hover:text-vivo-brand transition-colors mb-3">
                            <svg class="w-7 h-7 mx-auto" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12"></path>
                            </svg>
                        </div>
                        <p class="text-[14px] font-semibold text-vivo-navy mb-1.5">Drop your resume here</p>
                        <p class="text-[13px] text-gray-500 mb-4">or click to browse your files</p>
                        <p class="text-[11px] font-semibold text-gray-400 tracking-wider">PDF / DOCX &middot; 5 MB MAX</p>
                    </div>
                    
                    <div id="file-name-display" class="hidden flex-col items-center text-center pointer-events-none px-4">
                        <!-- Filled by JS -->
                    </div>
                </div>

                <!-- Immediate vs Schedule Toggle -->
                <div class="mb-5 w-full">
                    <p class="text-[12px] font-semibold text-vivo-navy mb-2 uppercase tracking-wider text-center">When would you like to take the assessment?</p>
                    <div class="w-full flex items-center justify-between bg-gray-100 rounded-lg p-1">
                        <label class="flex-1 cursor-pointer relative group" title="Our AI will instantly parse your resume and generate the 20-question test now. Takes ~15 mins.">
                            <input type="radio" name="action_type" value="immediate" class="peer sr-only" checked onchange="document.getElementById('schedule-summary').classList.add('hidden')" />
                            <div class="text-center py-2 text-[12px] font-medium text-gray-500 peer-checked:bg-vivo-brand peer-checked:text-white peer-checked:shadow-sm rounded-md transition-all flex items-center justify-center gap-1"><svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 10V3L4 14h7v7l9-11h-7z"></path></svg> Evaluate Now</div>
                        </label>
                        <label class="flex-1 cursor-pointer relative group" title="We'll save your resume and email you a secure link to take the test when you're ready.">
                            <input type="radio" name="action_type" value="schedule" class="peer sr-only" onclick="document.getElementById('schedule-modal').showModal()" />
                            <div class="text-center py-2 text-[12px] font-medium text-gray-500 peer-checked:bg-vivo-brand peer-checked:text-white peer-checked:shadow-sm rounded-md transition-all flex items-center justify-center gap-1"><svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z"></path></svg> Schedule Later</div>
                        </label>
                    </div>
                    <div id="schedule-summary" class="hidden text-[11px] text-vivo-brand font-semibold mt-1.5 text-center transition-all animate-fade-in-up tracking-wide cursor-pointer hover:underline" onclick="document.getElementById('schedule-modal').showModal()" title="Click to edit schedule"></div>
                    
                    <!-- Schedule Modal -->
                    <dialog id="schedule-modal" class="modal">
                        <div class="modal-box w-11/12 max-w-[500px] bg-white rounded-[12px] p-8 shadow-2xl">
                            <h3 class="font-bold text-lg text-vivo-navy mb-5 text-left tracking-tight">Pick a Date & Time</h3>
                            
                            <div class="flex gap-6 w-full text-left">
                                <!-- Date side -->
                                <div class="flex-1">
                                    <label class="block text-[11px] font-bold text-gray-400 uppercase tracking-wider mb-2 ml-1">Date</label>
                                    <div class="relative">
                                        <input type="text" id="flatpickr-date" name="scheduled_date" placeholder="Select date..." class="w-full px-4 py-2.5 rounded-[8px] border border-gray-300 bg-white text-[13px] font-medium text-gray-900 focus:border-vivo-brand focus:ring-1 focus:ring-vivo-brand outline-none transition-all cursor-pointer shadow-sm" />
                                        <div class="absolute inset-y-0 right-0 pr-4 flex items-center pointer-events-none text-gray-400 text-lg">
                                            📅
                                        </div>
                                    </div>
                                </div>
                                
                                <!-- Time side -->
                                <div class="flex-1">
                                    <label class="block text-[11px] font-bold text-gray-400 uppercase tracking-wider mb-2 ml-1">Time</label>
                                    <div class="grid grid-cols-3 gap-2">
                                        <label class="cursor-pointer">
                                            <input type="radio" name="scheduled_time" value="09:00" class="peer sr-only" checked>
                                            <div class="py-2 text-center text-[12px] font-semibold text-gray-600 bg-white border border-gray-200 rounded-[6px] peer-checked:bg-vivo-navy peer-checked:text-white peer-checked:border-vivo-navy hover:bg-gray-50 transition-all shadow-sm">09:00</div>
                                        </label>
                                        <label class="cursor-pointer">
                                            <input type="radio" name="scheduled_time" value="09:30" class="peer sr-only">
                                            <div class="py-2 text-center text-[12px] font-semibold text-gray-600 bg-white border border-gray-200 rounded-[6px] peer-checked:bg-vivo-navy peer-checked:text-white peer-checked:border-vivo-navy hover:bg-gray-50 transition-all shadow-sm">09:30</div>
                                        </label>
                                        <label class="cursor-pointer">
                                            <input type="radio" name="scheduled_time" value="10:00" class="peer sr-only">
                                            <div class="py-2 text-center text-[12px] font-semibold text-gray-600 bg-white border border-gray-200 rounded-[6px] peer-checked:bg-vivo-navy peer-checked:text-white peer-checked:border-vivo-navy hover:bg-gray-50 transition-all shadow-sm">10:00</div>
                                        </label>
                                        <label class="cursor-pointer">
                                            <input type="radio" name="scheduled_time" value="10:30" class="peer sr-only">
                                            <div class="py-2 text-center text-[12px] font-semibold text-gray-600 bg-white border border-gray-200 rounded-[6px] peer-checked:bg-vivo-navy peer-checked:text-white peer-checked:border-vivo-navy hover:bg-gray-50 transition-all shadow-sm">10:30</div>
                                        </label>
                                        <label class="cursor-pointer">
                                            <input type="radio" name="scheduled_time" value="11:00" class="peer sr-only">
                                            <div class="py-2 text-center text-[12px] font-semibold text-gray-600 bg-white border border-gray-200 rounded-[6px] peer-checked:bg-vivo-navy peer-checked:text-white peer-checked:border-vivo-navy hover:bg-gray-50 transition-all shadow-sm">11:00</div>
                                        </label>
                                        <label class="cursor-pointer">
                                            <input type="radio" name="scheduled_time" value="11:30" class="peer sr-only">
                                            <div class="py-2 text-center text-[12px] font-semibold text-gray-600 bg-white border border-gray-200 rounded-[6px] peer-checked:bg-vivo-navy peer-checked:text-white peer-checked:border-vivo-navy hover:bg-gray-50 transition-all shadow-sm">11:30</div>
                                        </label>
                                    </div>
                                </div>
                            </div>
                            
                            <div class="modal-action mt-8">
                                <button type="button" class="h-10 bg-vivo-brand hover:bg-blue-700 text-white text-[13px] font-medium rounded-[8px] shadow-sm px-6 transition-all" onclick="saveSchedule()">Save Schedule</button>
                            </div>
                        </div>
                        <!-- Clicking outside closes it, but since it's in a form, we need to prevent submission on close, using method="dialog" helps natively, but we can also just use a button type="button" with onclick -->
                        <div class="modal-backdrop bg-black/20" onclick="document.getElementById('schedule-modal').close()"></div>
                    </dialog>
                </div>
                
                <button type="submit" class="w-full h-10 bg-vivo-brand hover:bg-blue-700 text-white text-[13px] font-medium rounded-[8px] shadow-sm hover:shadow transition-all flex items-center justify-center gap-2">
                    <span>Continue</span>
                    <span class="loading loading-spinner loading-xs submit-spinner hidden"></span>
                </button>
            </form>
        </div>
    </div>
    <script>
        // Initialize Flatpickr immediately upon loading the partial
        if (typeof flatpickr !== 'undefined') {
            flatpickr('#flatpickr-date', {
                dateFormat: 'F j, Y',
                minDate: 'today',
                defaultDate: 'today',
                appendTo: document.getElementById('schedule-modal') || document.body
            });
        }
        
        function saveSchedule() {
            const dateVal = document.getElementById('flatpickr-date').value;
            const timeInput = document.querySelector('input[name="scheduled_time"]:checked');
            const summary = document.getElementById('schedule-summary');
            
            if (dateVal && timeInput) {
                summary.innerHTML = `✓ Scheduled for ${dateVal} at ${timeInput.value}`;
                summary.classList.remove('hidden');
            }
            document.getElementById('schedule-modal').close();
        }

        function updateFileName(input) {
            const fileNameElement = document.getElementById('file-name-display');
            const uploadPrompt = document.getElementById('upload-prompt');
            
            if (input.files && input.files[0]) {
                uploadPrompt.classList.add('hidden');
                fileNameElement.classList.remove('hidden');
                fileNameElement.classList.add('flex');
                
                // SVG Checkmark icon
                fileNameElement.innerHTML = `
                    <svg class="w-8 h-8 mx-auto mb-3 text-green-500" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"></path></svg>
                    <span class="text-vivo-navy font-semibold block truncate max-w-[280px] w-full">${input.files[0].name}</span>
                    <span class="text-[12px] text-gray-500 mt-2 block font-medium">Click box to change</span>
                `;
            } else {
                uploadPrompt.classList.remove('hidden');
                fileNameElement.classList.add('hidden');
                fileNameElement.classList.remove('flex');
            }
        }
    </script>
    """
    return HTMLResponse(content=html_content)

@app.post("/assessment/upload-resume", response_class=HTMLResponse)
async def upload_resume(
    request: Request,
    resume: UploadFile = File(...),
    action_type: str = Form(...),
    scheduled_date: str = Form(None),
    scheduled_time: str = Form(None),
    session: AsyncSession = Depends(get_session)
):
    try:
        content = await resume.read()
        
        # Save the file physically to an 'uploads' folder
        upload_dir = os.path.join(os.path.dirname(__file__), "uploads")
        if not os.path.exists(upload_dir):
            os.makedirs(upload_dir)
            
        file_path = os.path.join(upload_dir, resume.filename)
        with open(file_path, "wb") as f:
            f.write(content)
        
        # Identify the current user using the cookie
        user_id_cookie = request.cookies.get("user_id")
        if not user_id_cookie:
            return HTMLResponse("Unauthorized", status_code=401)
        
        user_id = int(user_id_cookie)
        
        # Save Resume to DB using Stored Procedure
        # Note: We must convert file_path back to str/posix format if needed, but absolute is fine.
        result = await session.execute(
            text("CALL CreateResume(:u_id, :fname, :fpath, :content)"),
            {"u_id": user_id, "fname": resume.filename, "fpath": file_path, "content": content}
        )
        new_resume_record = result.mappings().first()
        new_resume_id = new_resume_record["new_id"]
        
        # Update User stage to 'Test' in DB using Stored Procedure
        await session.execute(
            text("CALL UpdateUserStage(:u_id, :stage)"),
            {"u_id": user_id, "stage": "Test"}
        )
        await session.commit()
        
        if action_type == "schedule":
            await session.execute(
                text("CALL SaveAssessmentSchedule(:u_id, :r_id, :s_date, :s_time)"),
                {
                    "u_id": user_id,
                    "r_id": new_resume_id,
                    "s_date": scheduled_date,
                    "s_time": scheduled_time
                }
            )
            await session.commit()
        
            html_content = """
            <div class="w-full animate-fade-in-up max-w-lg mx-auto">
                <!-- Progress Tracker (64px tall) - TEST STAGE -->
                <div class="flex items-center justify-center mb-10 h-16 w-full px-12">
                    <div class="flex flex-col items-center relative z-10 w-8">
                        <div class="w-6 h-6 rounded-full bg-blue-500 text-white flex items-center justify-center text-[10px] shadow-sm"><svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M5 13l4 4L19 7"></path></svg></div>
                        <span class="text-[11px] font-medium text-gray-500 mt-2 absolute top-6 whitespace-nowrap">Account</span>
                    </div>
                    <div class="flex-grow h-[2px] bg-blue-500 mx-2"></div>
                    <div class="flex flex-col items-center relative z-10 w-8">
                        <div class="w-6 h-6 rounded-full bg-blue-500 text-white flex items-center justify-center text-[10px] shadow-sm"><svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M5 13l4 4L19 7"></path></svg></div>
                        <span class="text-[11px] font-medium text-gray-500 mt-2 absolute top-6 whitespace-nowrap">Resume</span>
                    </div>
                    <div class="flex-grow h-[2px] bg-blue-500 mx-2"></div>
                    <div class="flex flex-col items-center relative z-10 w-8">
                        <div class="w-6 h-6 rounded-full bg-blue-500 text-white flex items-center justify-center shadow-sm"><div class="w-2 h-2 rounded-full bg-white"></div></div>
                        <span class="text-[11px] font-semibold text-vivo-navy mt-2 absolute top-6 whitespace-nowrap">Assessment</span>
                    </div>
                    <div class="flex-grow h-[2px] bg-gray-200 mx-2"></div>
                    <div class="flex flex-col items-center relative z-10 w-8">
                        <div class="w-6 h-6 rounded-full bg-white border-[2px] border-gray-200 text-gray-300 flex items-center justify-center"></div>
                        <span class="text-[11px] font-medium text-gray-400 mt-2 absolute top-6 whitespace-nowrap">Results</span>
                    </div>
                </div>
                
                <div class="w-[520px] mx-auto bg-white rounded-[12px] shadow-sm border border-gray-200 p-8 flex flex-col items-center justify-center text-center">
                    <h2 class="text-2xl font-bold text-vivo-navy mb-2 tracking-tight">Test Scheduled!</h2>
                    <p class="text-[13px] text-gray-500 mb-6 leading-relaxed">We successfully processed <strong>""" + resume.filename + """</strong>. We will email you a secure link to take the test on """ + scheduled_date + """ at """ + scheduled_time + """.</p>
                    <button class="w-full h-10 bg-white border border-gray-300 hover:bg-gray-50 text-gray-700 text-[13px] font-medium rounded-[8px] shadow-sm transition-colors">Return to Dashboard</button>
                </div>
            </div>
            """
            return HTMLResponse(content=html_content)
        
        elif action_type == "immediate":
            # Return loading screen immediately. This screen will trigger the heavy Gemini generation in the background.
            html_content = f"""
            <div class="w-full min-h-[60vh] flex flex-col items-center justify-center animate-fade-in-up">
                    <div class="w-16 h-16 bg-blue-50/50 rounded-[16px] flex items-center justify-center mb-6 shadow-sm border border-blue-100 relative">
                        <svg class="w-8 h-8 text-vivo-brand animate-pulse" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2"></path>
                        </svg>
                        <div class="absolute -bottom-1 -right-1 w-4 h-4 bg-green-500 rounded-full border-2 border-white"></div>
                    </div>
                    <h2 class="text-[22px] font-bold text-vivo-navy tracking-tight mb-5">Analyzing Resume</h2>
                    
                    <!-- Dynamic Text & Progress Bar -->
                    <div class="w-full max-w-[320px]">
                        <div class="flex justify-between items-center mb-2">
                            <span id="ai-status-text" class="text-[12px] font-medium text-gray-500 transition-opacity duration-300">Extracting professional experience...</span>
                            <span id="ai-progress-pct" class="text-[12px] font-bold text-vivo-brand">0%</span>
                        </div>
                        <div class="w-full h-2 bg-gray-100 rounded-full overflow-hidden">
                            <div id="ai-progress-bar" class="h-full bg-vivo-brand rounded-full transition-all duration-500 ease-out" style="width: 0%"></div>
                        </div>
                    </div>
                    
                    <!-- JavaScript for Dynamic Messaging and Progress -->
                    <script>
                    (function() {{
                        const statuses = [
                            "Extracting professional experience...",
                            "Mapping skills to VivoIQ framework...",
                            "Calibrating assessment difficulty...",
                            "Structuring personalized blueprint...",
                            "Finalizing capability profile..."
                        ];
                        let statusIdx = 0;
                        const textEl = document.getElementById("ai-status-text");
                        const barEl = document.getElementById("ai-progress-bar");
                        const pctEl = document.getElementById("ai-progress-pct");
                        
                        // Cycle text every 3.5 seconds
                        const textInterval = setInterval(() => {{
                            if (statusIdx < statuses.length - 1) statusIdx++;
                            if(textEl) {{
                                textEl.style.opacity = '0';
                                setTimeout(() => {{
                                    textEl.textContent = statuses[statusIdx];
                                    textEl.style.opacity = '1';
                                }}, 300);
                            }}
                        }}, 3500);
                        
                        // Simulate progress up to 99% over 30 seconds
                        let progress = 0;
                        const totalDuration = 30000;
                        const intervalTime = 500;
                        const progressIncrement = (99 / (totalDuration / intervalTime));
                        
                        const progInterval = setInterval(() => {{
                            progress += progressIncrement;
                            if(progress > 99) progress = 99;
                            if(barEl) barEl.style.width = progress + '%';
                            if(pctEl) pctEl.textContent = Math.floor(progress) + '%';
                        }}, intervalTime);
                        
                        // Cleanup
                        document.body.addEventListener("htmx:beforeSwap", function cleanup() {{
                            clearInterval(textInterval);
                            clearInterval(progInterval);
                            document.body.removeEventListener("htmx:beforeSwap", cleanup);
                        }});
                    }})();
                    </script>
                    
                    <!-- Triggers generation immediately on load -->
                    <div hx-get="/assessment/build-profile?resume_id={new_resume_id}" hx-trigger="load" hx-target="#main-content" class="hidden"></div>
                </div>
            """
            return HTMLResponse(content=html_content)
        
    except Exception as e:
        import traceback
        error_msg = traceback.format_exc()
        return HTMLResponse(f"<div class='alert alert-error'><pre>{error_msg}</pre></div>", status_code=500)

@app.get("/assessment/build-profile", response_class=HTMLResponse)
async def build_profile(resume_id: int, request: Request, session: AsyncSession = Depends(get_session)):
    try:
        user_id_cookie = request.cookies.get("user_id")
        if not user_id_cookie:
            return HTMLResponse("Unauthorized", status_code=401)
        user_id = int(user_id_cookie)
        
        import json
        
        # 1. Check if AI-1 & AI-3 already completed for this resume
        prof_res = await session.execute(
            text("CALL GetCandidateProfile(:r_id)"),
            {"r_id": resume_id}
        )
        bp_res = await session.execute(
            text("CALL GetAssessmentBlueprint(:r_id)"),
            {"r_id": resume_id}
        )
        
        prof_row = prof_res.mappings().first()
        bp_row = bp_res.mappings().first()
        
        profile_json = {}
        blueprint_json = {}
        
        if prof_row and bp_row and prof_row.get("profile_json") and bp_row.get("blueprint_json"):
            # Load from DB Cache (Prevents calling AI on refresh)
            profile_json = json.loads(prof_row["profile_json"])
            blueprint_json = json.loads(bp_row["blueprint_json"])
        else:
            # Run AI-1 & AI-3
            fp_result = await session.execute(text("CALL GetResumeFilePath(:r_id)"), {"r_id": resume_id})
            fp_row = fp_result.mappings().first()
            
            if fp_row and fp_row.get("file_path"):
                import os
                from ai_agents import extract_text_from_pdf, run_resume_intelligence_agent, run_assessment_blueprint_agent
                file_path = fp_row["file_path"]
                if os.path.exists(file_path):
                    # Run AI-1
                    resume_text = extract_text_from_pdf(file_path)
                    profile_json = run_resume_intelligence_agent(resume_text)
                    
                    # Save Profile
                    expected_level = profile_json.get("expected_vivoiq_level", 1)
                    if not isinstance(expected_level, int): expected_level = 1
                    await session.execute(
                        text("CALL SaveCandidateProfile(:u_id, :r_id, :prof, :lvl)"),
                        {"u_id": user_id, "r_id": resume_id, "prof": json.dumps(profile_json), "lvl": expected_level}
                    )
                    
                    # Run AI-3
                    blueprint_json = run_assessment_blueprint_agent(profile_json)
                    
                    # Save Blueprint
                    await session.execute(
                        text("CALL SaveAssessmentBlueprint(:u_id, :r_id, :bp)"),
                        {"u_id": user_id, "r_id": resume_id, "bp": json.dumps(blueprint_json)}
                    )
                    await session.commit()
                
        # Generate Readiness HTML
        level_str = profile_json.get("expected_vivoiq_level", "Unknown")
        roles = ", ".join(profile_json.get("roles", []))
        
        html_content = f"""
        <div class="absolute top-6 right-8 z-50 animate-fade-in">
            <a href="/users/logout" class="text-[13px] font-semibold text-gray-400 hover:text-vivo-brand transition-colors flex items-center gap-1.5 cursor-pointer">
                <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1"></path></svg> 
                Log out
            </a>
        </div>
        <div class="w-full h-full flex flex-col items-center justify-center animate-fade-in-up">
            
            <div class="w-full max-w-xl bg-white rounded-[16px] shadow-[0_8px_30px_rgb(0,0,0,0.06)] border border-gray-100 overflow-hidden">
                <!-- Header -->
                <div class="bg-slate-50 border-b border-gray-100 px-6 py-4 text-center relative overflow-hidden">
                    <div class="w-10 h-10 bg-white rounded-full flex items-center justify-center mx-auto mb-2 shadow-sm border border-gray-100 relative z-10">
                        <svg class="w-5 h-5 text-vivo-brand" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z"></path>
                        </svg>
                    </div>
                    <h2 class="text-[20px] font-bold text-vivo-navy tracking-tight relative z-10">Assessment Readiness Gate</h2>
                    <p class="text-[13px] text-gray-500 mt-1 relative z-10">Your resume analysis is complete. A unique test has been configured.</p>
                </div>
                
                                <!-- Body -->
                <div class="p-4">
                    <div class="space-y-2">
                        <!-- Item 1 -->
                        <label class="flex items-start gap-2 p-2 border border-gray-100 rounded-lg cursor-pointer hover:bg-gray-50 transition-colors group">
                            <div class="pt-1">
                                <input type="checkbox" class="checkbox checkbox-primary chk-req" onchange="checkReadiness()">
                            </div>
                            <div class="w-10 h-10 rounded-full bg-blue-50 flex items-center justify-center flex-shrink-0 mt-0.5 text-vivo-brand">
                                <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5.586 15H4a1 1 0 01-1-1v-4a1 1 0 011-1h1.586l4.707-4.707C10.923 3.663 12 4.109 12 5v14c0 .891-1.077 1.337-1.707.707L5.586 15z" clip-rule="evenodd"></path><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M17 14l2-2m0 0l2-2m-2 2l-2-2m2 2l2 2"></path></svg>
                            </div>
                            <div>
                                <h4 class="text-[14px] font-bold text-vivo-navy">Quiet Environment</h4>
                                <p class="text-[13px] text-gray-600 mt-0.5 leading-snug">Ensure you are in a distraction-free space to focus entirely on complex scenario reasoning.</p>
                            </div>
                        </label>
                        
                        <!-- Item 2 -->
                        <label class="flex items-start gap-2 p-2 border border-gray-100 rounded-lg cursor-pointer hover:bg-gray-50 transition-colors group">
                            <div class="pt-1">
                                <input type="checkbox" class="checkbox checkbox-primary chk-req" onchange="checkReadiness()">
                            </div>
                            <div class="w-10 h-10 rounded-full bg-emerald-50 flex items-center justify-center flex-shrink-0 mt-0.5 text-emerald-600">
                                <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8.111 16.404a5.5 5.5 0 017.778 0M12 20h.01m-7.08-7.071c3.904-3.905 10.236-3.905 14.141 0M1.394 9.393c5.857-5.857 15.355-5.857 21.213 0"></path></svg>
                            </div>
                            <div>
                                <h4 class="text-[14px] font-bold text-vivo-navy">Stable Connection</h4>
                                <p class="text-[13px] text-gray-600 mt-0.5 leading-snug">Do not refresh or navigate away during the test. A dropped connection may result in a locked attempt.</p>
                            </div>
                        </label>
                        
                        <!-- Item 3 -->
                        <label class="flex items-start gap-2 p-2 border border-gray-100 rounded-lg cursor-pointer hover:bg-gray-50 transition-colors group">
                            <div class="pt-1">
                                <input type="checkbox" class="checkbox checkbox-primary chk-req" onchange="checkReadiness()">
                            </div>
                            <div class="w-10 h-10 rounded-full bg-purple-50 flex items-center justify-center flex-shrink-0 mt-0.5 text-purple-600">
                                <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z"></path></svg>
                            </div>
                            <div>
                                <h4 class="text-[14px] font-bold text-vivo-navy">30 Minutes Blocked</h4>
                                <p class="text-[13px] text-gray-600 mt-0.5 leading-snug">Once you generate the assessment, a strict 30-minute timer begins. It cannot be paused.</p>
                            </div>
                        </label>
                    </div>
                    
                    <div class="mt-4 pt-4 border-t border-gray-100 flex flex-col items-center">
                        <div id="test-gen-container" class="w-full">
                            <button id="btn-generate" disabled hx-get="/assessment/generate-test?resume_id={resume_id}" hx-target="#main-content" onclick="document.getElementById('test-gen-container').classList.add('hidden'); document.getElementById('test-gen-loading').classList.remove('hidden');" class="w-full h-11 bg-vivo-brand hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed text-white text-[14px] font-bold rounded-[8px] shadow-md hover:shadow-lg transition-all flex items-center justify-center gap-2">
                                <span>I'm Ready — Generate My Assessment</span>
                            </button>
                        </div>
                        
                        <!-- Dynamic Loading State -->
                        <div id="test-gen-loading" class="w-full hidden flex flex-col items-center">
                            <div class="flex justify-between items-center w-full mb-2">
                                <span id="gen-status-text" class="text-[12px] font-medium text-vivo-brand transition-opacity duration-300">Summoning Assessment Generation Agent (AI-4)...</span>
                                <span id="gen-progress-pct" class="text-[12px] font-bold text-vivo-brand">0%</span>
                            </div>
                            <div class="w-full h-2 bg-blue-50 rounded-full overflow-hidden">
                                <div id="gen-progress-bar" class="h-full bg-vivo-brand rounded-full transition-all duration-500 ease-out" style="width: 0%"></div>
                            </div>
                            
                            <script>
                                function checkReadiness() {{
                                    const boxes = document.querySelectorAll('.chk-req');
                                    const allChecked = Array.from(boxes).every(b => b.checked);
                                    const btn = document.getElementById('btn-generate');
                                    btn.disabled = !allChecked;
                                }}
                                
                                (function() {{
                                    document.body.addEventListener('htmx:beforeRequest', function(evt) {{
                                        if (evt.detail.elt.getAttribute('hx-get') && evt.detail.elt.getAttribute('hx-get').includes('generate-test')) {{
                                            const statuses = [
                                                "Summoning Assessment Generation Agent (AI-4)...",
                                                "Synthesizing unique question pool...",
                                                "Calibrating technical difficulty...",
                                                "Summoning Integrity Agent (AI-5)...",
                                                "Auditing for leakage & ambiguity...",
                                                "Finalizing secure test packet..."
                                            ];
                                            let statusIdx = 0;
                                            const textEl = document.getElementById("gen-status-text");
                                            const barEl = document.getElementById("gen-progress-bar");
                                            const pctEl = document.getElementById("gen-progress-pct");
                                            
                                            // Cycle text every 4 seconds
                                            const textInterval = setInterval(() => {{
                                                if (statusIdx < statuses.length - 1) statusIdx++;
                                                if(textEl) {{
                                                    textEl.style.opacity = '0';
                                                    setTimeout(() => {{
                                                        textEl.textContent = statuses[statusIdx];
                                                        textEl.style.opacity = '1';
                                                    }}, 300);
                                                }}
                                            }}, 4000);
                                            
                                            // Simulate progress up to 99% over 50 seconds
                                            let progress = 0;
                                            const totalDuration = 50000;
                                            const intervalTime = 500;
                                            const progressIncrement = (99 / (totalDuration / intervalTime));
                                            
                                            const progInterval = setInterval(() => {{
                                                progress += progressIncrement;
                                                if(progress > 99) progress = 99;
                                                if(barEl) barEl.style.width = progress + '%';
                                                if(pctEl) pctEl.textContent = Math.floor(progress) + '%';
                                            }}, intervalTime);
                                            
                                            // Cleanup
                                            document.body.addEventListener("htmx:beforeSwap", function cleanup() {{
                                                clearInterval(textInterval);
                                                clearInterval(progInterval);
                                                document.body.removeEventListener("htmx:beforeSwap", cleanup);
                                            }});
                                        }}
                                    }});
                                }})();
                            </script>
                        </div>
                        
                        <p class="text-[11px] text-gray-400 mt-4 text-center">By selecting “I’m Ready — Generate My Assessment,” you confirm you’re in a quiet environment and ready to begin.</p>
                    </div>
                </div>
            </div>
            
        </div>
        """
        return HTMLResponse(content=html_content)
    except Exception as e:
        import traceback
        return HTMLResponse(f"<div class='alert alert-error'><pre>{traceback.format_exc()}</pre></div>", status_code=500)

@app.get("/assessment/generate-test", response_class=HTMLResponse)
async def generate_test(resume_id: int, request: Request, session: AsyncSession = Depends(get_session)):
    try:
        user_id_cookie = request.cookies.get("user_id")
        if not user_id_cookie:
            return HTMLResponse("Unauthorized", status_code=401)
        user_id = int(user_id_cookie)
        
        import json
        from ai_agents import run_question_generation_agent, run_assessment_integrity_agent
        
        # SAFETY CHECK & PHASE DETECTION
        check_result = await session.execute(text("CALL CheckAIAssessment(:r_id)"), {"r_id": resume_id})
        check_row = check_result.mappings().first()
        
        saved_json = None
        if check_row and check_row.get("raw_json"):
            try:
                saved_json = json.loads(check_row["raw_json"])
            except:
                pass
                
        if saved_json and saved_json.get("status") != "pending_ai5":
            from fastapi.responses import Response
            res = Response()
            res.headers["HX-Redirect"] = f"/assessment/test-questions?resume_id={resume_id}"
            return res
            
        if saved_json and saved_json.get("status") == "pending_ai5":
            # ==========================================
            # PHASE 2: Integrity Review (AI-5)
            # ==========================================
            ai4_json = saved_json.get("ai4_json", {})
            bp_res = await session.execute(text("CALL GetAssessmentBlueprint(:r_id)"), {"r_id": resume_id})
            bp_row = bp_res.mappings().first()
            blueprint_json = json.loads(bp_row["blueprint_json"]) if bp_row and bp_row["blueprint_json"] else {}
            
            ai5_json = run_assessment_integrity_agent(ai4_json, blueprint_json)
            
            ui_json = {
                "sections": [
                    {"section_name": "Knowledge Accuracy", "weightage": 35, "total_score": 25, "questions": []},
                    {"section_name": "Practical Application", "weightage": 30, "total_score": 25, "questions": []},
                    {"section_name": "Commercial & Analytical Reasoning", "weightage": 20, "total_score": 25, "questions": []},
                    {"section_name": "Judgment & Risk Awareness", "weightage": 15, "total_score": 25, "questions": []}
                ]
            }
            
            final_questions = ai5_json.get("final_questions", [])
            if len(final_questions) == 0:
                # If AI-5 completely fails or hits a rate limit, fallback to AI-4's output
                final_questions = ai4_json.get("questions", [])
                
            if len(final_questions) == 0:
                return HTMLResponse("<div class='p-8 text-center text-red-600'>Generation Failed. Please try again.</div>", status_code=200)
                
            for i, q in enumerate(final_questions):
                q_ui = {
                    "question": q.get("question", "Fallback question text"),
                    "question_type": q.get("question_type", "mcq"),
                    "domain": q.get("domain", "General Procurement"),
                    "options": q.get("options", []),
                    "answer": q.get("answer", ""),
                    "rubric": q.get("rubric", ""),
                    "score": q.get("max_score", 5)
                }
                if i < 5: ui_json["sections"][0]["questions"].append(q_ui)
                elif i < 10: ui_json["sections"][1]["questions"].append(q_ui)
                elif i < 15: ui_json["sections"][2]["questions"].append(q_ui)
                else: ui_json["sections"][3]["questions"].append(q_ui)
                    
            raw_json = json.dumps(ui_json)
            await session.execute(
                text("CALL SaveAIAssessment(:u_id, :r_id, :test_json)"),
                {"u_id": user_id, "r_id": resume_id, "test_json": raw_json}
            )
            await session.commit()
            
            from fastapi.responses import Response
            res = Response()
            res.headers["HX-Redirect"] = f"/assessment/test-questions?resume_id={resume_id}"
            return res
            
        else:
            # ==========================================
            # PHASE 1: Question Generation (AI-4)
            # ==========================================
            prof_res = await session.execute(text("CALL GetCandidateProfile(:r_id)"), {"r_id": resume_id})
            prof_row = prof_res.mappings().first()
            profile_json = json.loads(prof_row["profile_json"]) if prof_row and prof_row["profile_json"] else {}
            
            bp_res = await session.execute(text("CALL GetAssessmentBlueprint(:r_id)"), {"r_id": resume_id})
            bp_row = bp_res.mappings().first()
            blueprint_json = json.loads(bp_row["blueprint_json"]) if bp_row and bp_row["blueprint_json"] else {}
            
            ai4_json = run_question_generation_agent(blueprint_json, profile_json)
            
            # Save intermediate state
            intermediate_state = {"status": "pending_ai5", "ai4_json": ai4_json}
            await session.execute(
                text("CALL SaveAIAssessment(:u_id, :r_id, :test_json)"),
                {"u_id": user_id, "r_id": resume_id, "test_json": json.dumps(intermediate_state)}
            )
            await session.commit()
            
            # Return HTMX Response that immediately triggers Phase 2 without changing the visual loading container!
            # The hx-target="this" and hx-swap="outerHTML" ensures we just swap the loading guts, keeping the animation alive.
            return HTMLResponse(f'''
            <div id="test-gen-loading" class="w-full flex flex-col items-center">
                <div class="flex justify-between items-center w-full mb-2">
                    <span class="text-[12px] font-medium text-vivo-brand">Phase 1 Complete! Initializing Integrity Reviewer (AI-5)...</span>
                    <span class="text-[12px] font-bold text-vivo-brand">50%</span>
                </div>
                <div class="w-full h-2 bg-blue-50 rounded-full overflow-hidden">
                    <div class="h-full bg-vivo-brand rounded-full transition-all duration-1000 ease-out" style="width: 50%"></div>
                </div>
                <!-- Phase 2 Trigger -->
                <div hx-get="/assessment/generate-test?resume_id={resume_id}" hx-trigger="load" hx-target="#main-content" class="hidden"></div>
            </div>
            ''', status_code=200)

    except Exception as e:
        import traceback
        error_msg = traceback.format_exc()
        return HTMLResponse(f"<div class='alert alert-error'><pre>{error_msg}</pre></div>", status_code=500)

@app.get("/assessment/test-questions", response_class=HTMLResponse)
async def test_questions(request: Request, resume_id: int, q_idx: int = 0, session: AsyncSession = Depends(get_session)):
    user_id_cookie = request.cookies.get("user_id")
    if not user_id_cookie: return HTMLResponse("Unauthorized", status_code=401)
    user_id = int(user_id_cookie)
    
    # 1. Load schema & check expiry
    result = await session.execute(
        text("CALL GetAIAssessment(:r_id)"),
        {"r_id": resume_id}
    )
    test_row = result.mappings().first()
    if not test_row or not test_row["raw_json"]: return HTMLResponse("No assessment found.", status_code=404)
        
    import datetime
    expires_at = test_row.get("expires_at")
    if expires_at:
        now_utc = datetime.datetime.utcnow()
        if now_utc > expires_at:
            return HTMLResponse(f"<script>window.location.href = '/assessment/finish-test?resume_id={resume_id}';</script>")
        time_left_secs = int((expires_at - now_utc).total_seconds())
    else:
        time_left_secs = 1800

    try:
        data = json.loads(test_row["raw_json"])
        sections = data.get("sections", [])
    except:
        sections = []

    all_questions = []
    for sec in sections:
        for q in sec.get("questions", []):
            q["section_name"] = sec.get("section_name", "")
            q["sec_weight"] = sec.get("weightage", 0)
            q["sec_total"] = sec.get("total_score", 50)
            all_questions.append(q)
            
    total_q = len(all_questions)
    
    # 2. Fetch all existing responses to determine progress & allowed jumps
    resp_result = await session.execute(
        text("CALL GetAssessmentResponses(:r_id)"),
        {"r_id": resume_id}
    )
    responses = {row.question_idx: row.user_answer for row in resp_result.mappings().all()}
    
    # Calculate Max Allowed Question Index (highest visited + 1, capped at total_q)
    max_allowed_idx = 0
    if responses:
        max_allowed_idx = max(responses.keys()) + 1
    max_allowed_idx = min(max_allowed_idx, total_q)
    
    # Force user back if they try to jump too far ahead
    if q_idx > max_allowed_idx and q_idx < total_q:
        q_idx = max_allowed_idx
        
    if q_idx >= total_q:
        return HTMLResponse(f"<script>window.location.href = '/assessment/finish-test?resume_id={resume_id}';</script>")

    q = all_questions[q_idx]
    
    # If they are revisiting a question, pre-select their answer
    saved_answer = responses.get(q_idx, "")
    
    options_html = ""
    q_type = q.get("question_type", "mcq")
    if q_type == "short_response":
        options_html = f"""
        <textarea name="answer" rows="5" class="w-full p-5 bg-white border border-gray-200 rounded-[12px] text-[14px] leading-relaxed text-gray-800 placeholder-gray-400 focus:bg-white focus:outline-none focus:border-vivo-brand focus:ring-4 focus:ring-vivo-brand/10 transition-all duration-300 shadow-sm resize-y min-h-[140px]" placeholder="Type your reasoning and approach here..." required>{saved_answer}</textarea>
        """
    elif q_type == "multi_select":
        saved_list = [s.strip() for s in str(saved_answer).split("||")] if saved_answer else []
        for opt in q.get("options", []):
            checked = "checked" if str(opt).strip() in saved_list else ""
            options_html += f"""
            <label class="flex items-center gap-3 p-3 border border-gray-200 rounded-[8px] cursor-pointer hover:bg-gray-50 transition-colors {'bg-blue-50/30 border-blue-200' if checked else ''}">
                <input type="checkbox" name="answer" value="{opt}" class="checkbox checkbox-primary checkbox-sm" {checked} />
                <span class="text-[13px] text-gray-700 font-medium">{opt}</span>
            </label>
            """
    else:
        for opt in q.get("options", []):
            checked = "checked" if str(opt) == str(saved_answer) else ""
            options_html += f"""
            <label class="flex items-center gap-3 p-3 border border-gray-200 rounded-[8px] cursor-pointer hover:bg-gray-50 transition-colors {'bg-blue-50/30 border-blue-200' if checked else ''}">
                <input type="radio" name="answer" value="{opt}" class="radio radio-primary radio-sm" required {checked} />
                <span class="text-[13px] text-gray-700 font-medium">{opt}</span>
            </label>
            """
        
    # 3. Build Progress Bar
    progress_pct = 0
    if total_q > 1:
        progress_pct = (q_idx / (total_q - 1)) * 100

    progress_bar_html = f'''
    <div class="w-full bg-white rounded-[16px] shadow-[0_2px_10px_rgb(0,0,0,0.02)] border border-slate-200 p-5 mb-8">
        <div class="flex items-center justify-between mb-8 px-1">
            <h3 class="text-[13px] font-bold text-slate-700 tracking-tight">Assessment Progress</h3>
            <div class="flex items-center gap-4 text-[11px] font-semibold text-slate-500 bg-slate-50 py-1.5 px-3 rounded-full border border-slate-100">
                <div class="flex items-center gap-1.5"><span class="w-2.5 h-2.5 rounded-full bg-emerald-500 shadow-[0_0_8px_rgba(16,185,129,0.3)]"></span> Answered</div>
                <div class="flex items-center gap-1.5"><span class="w-2.5 h-2.5 rounded-full bg-amber-400 shadow-[0_0_8px_rgba(251,191,36,0.3)]"></span> Skipped</div>
                <div class="flex items-center gap-1.5"><span class="w-2.5 h-2.5 rounded-full bg-slate-200"></span> Locked</div>
            </div>
        </div>
        
        <div class="relative flex items-center justify-between w-full px-1">
            <!-- Connecting Background Line -->
            <div class="absolute top-1/2 left-0 w-full h-[2px] bg-slate-100 -translate-y-1/2 z-0 rounded-full"></div>
            <!-- Active Progress Line -->
            <div class="absolute top-1/2 left-0 h-[2px] bg-vivo-brand -translate-y-1/2 z-0 transition-all duration-500 rounded-full" style="width: {progress_pct}%"></div>
    '''

    for i in range(total_q):
        q_num = i + 1
        if i == q_idx:
            # Active
            style_cls = "bg-vivo-brand text-white shadow-[0_4px_12px_rgba(37,99,235,0.4)] scale-125 z-20"
            link = f"#"
        elif i in responses:
            if responses[i] == "":
                # Skipped (Amber)
                style_cls = "bg-amber-400 text-white shadow-[0_2px_8px_rgba(251,191,36,0.3)] cursor-pointer hover:scale-110 z-10"
            else:
                # Answered (Emerald)
                style_cls = "bg-emerald-500 text-white shadow-[0_2px_8px_rgba(16,185,129,0.3)] cursor-pointer hover:scale-110 z-10"
            link = f"/assessment/test-questions?resume_id={resume_id}&q_idx={i}"
        elif i == max_allowed_idx:
            # Next Available (White/Gray)
            style_cls = "bg-white text-slate-600 border border-slate-200 shadow-sm cursor-pointer hover:border-slate-300 hover:bg-slate-50 z-10"
            link = f"/assessment/test-questions?resume_id={resume_id}&q_idx={i}"
        else:
            # Locked (Light Gray)
            style_cls = "bg-slate-50 text-slate-400 border border-slate-100 cursor-not-allowed z-10"
            link = f"#"
            
        progress_bar_html += f'''
            <a hx-get="{link}" hx-target="#main-content" class="relative w-7 h-7 flex items-center justify-center rounded-full text-[11px] font-bold transition-all duration-300 ring-[3px] ring-white {style_cls}" title="Question {q_num}">
                {q_num}
            </a>
        '''
    progress_bar_html += "</div></div>"

        
    js_timer = f'''
    <script>
    (function() {{
        var timeLeft = {time_left_secs};
        var timerEl = document.getElementById('timer-display');
        var interval = setInterval(function() {{
            timeLeft--;
            if (timeLeft <= 0) {{
                clearInterval(interval);
                window.location.href = '/assessment/finish-test?resume_id={resume_id}';
            }}
            var m = Math.floor(timeLeft / 60);
            var s = timeLeft % 60;
            if(timerEl) timerEl.innerText = (m < 10 ? '0' : '') + m + ':' + (s < 10 ? '0' : '') + s;
        }}, 1000);
    }})();
    </script>
    '''
    
    html_content = f"""
    <div class="w-full max-w-3xl mx-auto pb-8 pt-4 animate-fade-in-up">
        
        {progress_bar_html}
        
        <div class="flex items-center justify-between mb-4 px-2">
            <div>
                <h2 class="text-xl font-bold text-vivo-navy tracking-tight">{q.get('section_name')}</h2>
                <p class="text-[13px] text-gray-500 mt-1">Question {q_idx + 1} of {total_q}</p>
            </div>
            <div class="flex items-center gap-4">
                <div class="px-4 py-2 bg-red-50 text-red-600 rounded-[8px] border border-red-100 flex items-center gap-2 shadow-sm">
                    <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z"></path></svg>
                    <span id="timer-display" class="font-bold text-[15px] tracking-wider font-mono">--:--</span>
                </div>
            </div>
        </div>
        
        <div class="bg-white rounded-[12px] shadow-sm border border-gray-200 p-8 relative">
            <form id="qForm" hx-post="/assessment/submit-answer" hx-target="#main-content">
                <input type="hidden" name="resume_id" value="{resume_id}" />
                <input type="hidden" name="q_idx" value="{q_idx}" />
                <input type="hidden" name="correct_answer" value="{q.get('answer', '')}" />
                <input type="hidden" name="score_val" value="{q.get('score', 5)}" />
                <input type="hidden" id="is_skip" name="is_skip" value="0" />
                
                <h4 class="text-[15px] font-bold text-vivo-navy leading-relaxed mb-6"><span class="text-vivo-brand mr-2">Q{q_idx+1}.</span> {q.get("question", "")}</h4>
                
                <div class="space-y-3 mb-10">
                    {options_html}
                </div>
                
                <div class="flex justify-between items-center pt-6 border-t border-gray-100">
                    <div>
                        {f'''<button type="button" onclick="document.getElementById('is_skip').value='1'; document.querySelectorAll('input, textarea').forEach(r=>r.required=false); htmx.trigger('#qForm', 'submit');" class="h-10 px-6 bg-white border border-gray-300 hover:bg-gray-50 text-gray-600 text-[13px] font-medium rounded-[8px] shadow-sm transition-all">
                            Skip Question
                        </button>''' if not saved_answer else ''}
                    </div>
                    <button type="submit" class="h-10 px-8 bg-vivo-brand hover:bg-blue-700 text-white text-[13px] font-bold rounded-[8px] shadow-sm transition-all flex items-center justify-center gap-2">
                        <span>{"Submit Final & Finish" if q_idx == total_q - 1 else "Save & Next"}</span>
                        <span class="loading loading-spinner loading-xs htmx-indicator hidden"></span>
                    </button>
                </div>
            </form>
        </div>
    </div>
    {js_timer}
    """
    return HTMLResponse(content=html_content)

@app.post("/assessment/submit-answer", response_class=HTMLResponse)
async def submit_answer(request: Request, session: AsyncSession = Depends(get_session)):
    user_id_cookie = request.cookies.get("user_id")
    if not user_id_cookie: return HTMLResponse("Unauthorized", status_code=401)
    user_id = int(user_id_cookie)
    
    form_data = await request.form()
    resume_id = int(form_data.get("resume_id", 0))
    q_idx = int(form_data.get("q_idx", 0))
    is_skip = form_data.get("is_skip", "0")
    # Handle multi_select (multiple checkboxes with same name)
    answers = form_data.getlist("answer")
    user_answer = " || ".join(answers) if len(answers) > 1 else (answers[0] if answers else "")
    correct_answer = form_data.get("correct_answer", "")
    score_val = float(form_data.get("score_val", 5.0))
    
    if is_skip == "1":
        user_answer = ""
        is_correct = False
        points = 0.0
    else:
        is_correct = (str(user_answer).strip().lower() == str(correct_answer).strip().lower())
        points = score_val if is_correct else 0.0
    
    # Check expiry
    result = await session.execute(
        text("CALL GetAIAssessment(:r_id)"),
        {"r_id": resume_id}
    )
    test_row = result.mappings().first()
    
    import datetime
    if test_row and test_row.get("expires_at"):
        if datetime.datetime.utcnow() > test_row["expires_at"]:
            return HTMLResponse(f"<script>window.location.href = '/assessment/finish-test?resume_id={resume_id}';</script>")

    # Upsert Response (passing nulls for AI fields initially)
    await session.execute(
        text("CALL SaveAssessmentResponse(:u, :r, :q, :ans, :isc, :pts, :rsn, :cnf)"),
        {"u": user_id, "r": resume_id, "q": q_idx, "ans": user_answer, "isc": is_correct, "pts": points, "rsn": "", "cnf": ""}
    )
    await session.commit()
    
    # Check if we are jumping forward past the end.
    # Actually, we just go to the next logical question, OR jump to the next un-answered if they are filling gaps.
    # But standard behavior is just q_idx + 1. If q_idx+1 >= 20, finish.
    next_idx = q_idx + 1
    from fastapi.responses import Response
    res = Response()
    if next_idx >= 20:
        res.headers["HX-Redirect"] = f"/assessment/finish-test?resume_id={resume_id}"
    else:
        res.headers["HX-Redirect"] = f"/assessment/test-questions?resume_id={resume_id}&q_idx={next_idx}"
    return res

@app.get("/assessment/finish-test", response_class=HTMLResponse)
async def finish_test_loading(resume_id: int, request: Request, session: AsyncSession = Depends(get_session)):
    user_id_cookie = request.cookies.get("user_id")
    if not user_id_cookie: return HTMLResponse("Unauthorized", status_code=401)
    
    # Render Loading Screen that calls process-results
    html_content = f"""
    <div class="w-full min-h-[70vh] flex flex-col items-center justify-center animate-fade-in py-16">
        <div class="w-full max-w-lg bg-white rounded-[16px] shadow-sm border border-gray-100 overflow-hidden text-center p-12">
            <div class="relative w-20 h-20 mx-auto mb-6">
                <div class="absolute inset-0 rounded-full border-[3px] border-gray-100"></div>
                <div class="absolute inset-0 rounded-full border-[3px] border-vivo-brand border-t-transparent animate-spin"></div>
                <svg class="absolute inset-0 m-auto w-8 h-8 text-vivo-brand" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z"></path></svg>
            </div>
            
            <h2 class="text-[22px] font-bold text-vivo-navy mb-2 tracking-tight">AI-6 Evaluation Engine</h2>
            <p id="eval-status-text" class="text-[14px] text-gray-500 mb-8 transition-opacity duration-300">Summoning Response Evaluator...</p>
            
            <div class="w-full h-1.5 bg-gray-50 rounded-full overflow-hidden mb-2">
                <div id="eval-progress-bar" class="h-full bg-vivo-brand transition-all duration-[400ms]" style="width: 0%"></div>
            </div>
            
            <div hx-get="/assessment/process-results?resume_id={resume_id}" hx-trigger="load" hx-target="#main-content" class="hidden"></div>
            
            <script>
                (function() {{
                    const statuses = [
                        "Extracting scenario responses...",
                        "Applying question-specific rubrics...",
                        "Evaluating commercial & analytical reasoning...",
                        "Running deterministic pass thresholds...",
                        "Generating Verified Capability Certificate..."
                    ];
                    let sIdx = 0;
                    const textEl = document.getElementById("eval-status-text");
                    const barEl = document.getElementById("eval-progress-bar");
                    
                    const tInt = setInterval(() => {{
                        if (sIdx < statuses.length - 1) sIdx++;
                        if(textEl) {{
                            textEl.style.opacity = '0';
                            setTimeout(() => {{ textEl.textContent = statuses[sIdx]; textEl.style.opacity = '1'; }}, 300);
                        }}
                    }}, 4500);
                    
                    let p = 0;
                    const pInt = setInterval(() => {{
                        p += (95 / (25000 / 500));
                        if(p > 95) p = 95;
                        if(barEl) barEl.style.width = p + '%';
                    }}, 500);
                    
                    document.body.addEventListener("htmx:beforeSwap", function cleanup() {{
                        clearInterval(tInt);
                        clearInterval(pInt);
                        document.body.removeEventListener("htmx:beforeSwap", cleanup);
                    }});
                }})();
            </script>
        </div>
    </div>
    """
    return HTMLResponse(content=html_content)

@app.get("/assessment/process-results", response_class=HTMLResponse)
async def process_results(resume_id: int, request: Request, session: AsyncSession = Depends(get_session)):
    user_id_cookie = request.cookies.get("user_id")
    if not user_id_cookie: return HTMLResponse("Unauthorized", status_code=401)
    user_id = int(user_id_cookie)
    
    # 1. Load the Assessment Schema
    result = await session.execute(text("CALL GetAIAssessment(:r_id)"), {"r_id": resume_id})
    test_row = result.mappings().first()
    if not test_row: return HTMLResponse("Assessment not found", status_code=404)
    
    data = json.loads(test_row["raw_json"])
    sections = data.get("sections", [])
    
    # Flatten questions
    all_qs = []
    global_idx = 0
    for sec in sections:
        for q in sec.get("questions", []):
            q["q_idx"] = global_idx
            q["section_name"] = sec.get("section_name", "General")
            all_qs.append(q)
            global_idx += 1
            
    # 2. Fetch all user responses
    resp_res = await session.execute(text("CALL GetAssessmentResponses(:r_id)"), {"r_id": resume_id})
    raw_responses = {row.question_idx: dict(row) for row in resp_res.mappings().all()}
    
    # 3. Filter short_response questions that need AI evaluation
    short_qs_to_eval = []
    user_answers_dict = {}
    for q in all_qs:
        idx = q["q_idx"]
        ans = raw_responses.get(idx, {}).get("user_answer", "")
        if q.get("question_type") in ["short_response", "multi_select"] and ans.strip() != "":
            short_qs_to_eval.append(q)
            user_answers_dict[idx] = ans
            
    # 4. Call AI-6 if needed
    from ai_agents import run_response_evaluation_agent
    if len(short_qs_to_eval) > 0:
        eval_result = run_response_evaluation_agent(short_qs_to_eval, user_answers_dict)
        evals = eval_result.get("evaluations", [])
        
        for ev in evals:
            idx = ev.get("q_idx")
            pts = float(ev.get("awarded_score", 0))
            is_c = (pts > 0)
            rsn = ev.get("reasoning_quality", "")
            cnf = ev.get("confidence", "Medium")
            ans = user_answers_dict.get(idx, "")
            
            # Update DB with AI score
            await session.execute(
                text("CALL SaveAssessmentResponse(:u, :r, :q, :ans, :isc, :pts, :rsn, :cnf)"),
                {"u": user_id, "r": resume_id, "q": idx, "ans": ans, "isc": is_c, "pts": pts, "rsn": rsn, "cnf": cnf}
            )
            # Update local memory for score calculation
            if idx in raw_responses:
                raw_responses[idx]["points_awarded"] = pts
                raw_responses[idx]["is_correct"] = is_c
                raw_responses[idx]["ai_reasoning"] = rsn
                
        await session.commit()
        
    # 5. AI-7: Deterministic Capability Scoring Engine
    
    # We will score by domain
    domain_scores = {}
    final_score = 0.0
    breakdown = []
    total_max_score = 0.0
    
    g_idx = 0
    for sec in sections:
        for q in sec.get("questions", []):
            r = raw_responses.get(g_idx)
            domain = q.get("domain", "General Procurement")
            max_pts = float(q.get("score", 5)) # In main.py, it's saved as "score" in UI JSON
            
            if domain not in domain_scores:
                domain_scores[domain] = {"earned": 0.0, "possible": 0.0}
            
            domain_scores[domain]["possible"] += max_pts
            total_max_score += max_pts
            
            if r:
                pts = float(r.get("points_awarded", 0))
                domain_scores[domain]["earned"] += pts
                final_score += pts
                
                breakdown.append({
                    "question_idx": g_idx,
                    "domain": domain,
                    "question": q.get("question"),
                    "user_answer": r.get("user_answer"),
                    "is_correct": r.get("is_correct"),
                    "points_awarded": pts,
                    "max_points": max_pts,
                    "ai_reasoning": r.get("ai_reasoning", "")
                })
            else:
                breakdown.append({
                    "question_idx": g_idx,
                    "domain": domain,
                    "question": q.get("question"),
                    "user_answer": None,
                    "is_correct": False,
                    "points_awarded": 0.0,
                    "max_points": max_pts,
                    "ai_reasoning": ""
                })
            g_idx += 1
            
    # Calculate percentage
    if total_max_score > 0:
        overall_percentage = (final_score / total_max_score) * 100.0
    else:
        overall_percentage = 0.0
        
    for dom, scores in domain_scores.items():
        if scores["possible"] > 0:
            scores["percentage"] = (scores["earned"] / scores["possible"]) * 100.0
        else:
            scores["percentage"] = 0.0
            
    # AI-7 Pass/Fail Rules
    passed = True
    critical_failure = False
    
    if overall_percentage < 70.0:
        passed = False
        
    for dom, scores in domain_scores.items():
        if scores["percentage"] < 50.0:
            passed = False
            critical_failure = True
            
    ai7_results = {
        "overall_percentage": overall_percentage,
        "domain_scores": domain_scores,
        "passed": passed,
        "critical_failure": critical_failure,
        "breakdown": breakdown
    }
        
    # Save Final Result
    await session.execute(
        text("CALL SaveAssessmentResult(:u, :r, :tot, :bkd)"),
        {"u": user_id, "r": resume_id, "tot": overall_percentage, "bkd": json.dumps(ai7_results)}
    )
    await session.execute(
        text("CALL UpdateUserStage(:u_id, :stage)"),
        {"u_id": user_id, "stage": "Results"}
    )
    await session.commit()
    
    # Trigger HTMX redirect to the final results screen
    from fastapi.responses import Response
    res = Response()
    res.headers["HX-Redirect"] = f"/assessment/results?resume_id={resume_id}"
    return res

@app.get("/assessment/results", response_class=HTMLResponse)
async def view_results(request: Request, resume_id: int, session: AsyncSession = Depends(get_session)):
    user_id_cookie = request.cookies.get("user_id")
    if not user_id_cookie: return HTMLResponse("Unauthorized", status_code=401)
    user_id = int(user_id_cookie)
    
    # 1. Get Assessment Result
    result = await session.execute(text("CALL GetLatestAssessmentResult(:r_id)"), {"r_id": resume_id})
    score_row = result.mappings().first()
    if not score_row: return HTMLResponse("Results not found", status_code=404)
    
    score = score_row["total_score"]
    try:
        ai7_results = json.loads(score_row["breakdown_json"])
        if isinstance(ai7_results, list): ai7_results = {"overall_percentage": score, "domain_scores": {}, "passed": (score >= 70.0), "critical_failure": False}
    except:
        ai7_results = {"overall_percentage": score, "domain_scores": {}, "passed": (score >= 70.0), "critical_failure": False}
        
    passed = ai7_results.get("passed", score >= 70.0)
    critical = ai7_results.get("critical_failure", False)
    domain_scores = ai7_results.get("domain_scores", {})
    
    # 2. Get Expected Level & Profile via Stored Procedure
    prof_res = await session.execute(text("CALL GetCandidateProfileWithLevel(:r_id)"), {"r_id": resume_id})
    prof_row = prof_res.mappings().first()
    expected_level = 1
    level_name = "Foundation"
    if prof_row:
        expected_level = prof_row.get("expected_level", 1)
        
    levels_map = {1: "Level 1 — Foundation", 2: "Level 2 — Practitioner", 3: "Level 3 — Advanced", 4: "Level 4 — Expert", 5: "Level 5 — Leader"}
    level_text = levels_map.get(expected_level, f"Level {expected_level}")
    
    # 3. Calculate Strengths and Gaps
    sorted_domains = sorted(domain_scores.items(), key=lambda item: item[1].get("percentage", 0), reverse=True)
    top_3_strengths = [dom for dom, data in sorted_domains if data.get("percentage", 0) >= 50][:3]
    bottom_3_gaps = [dom for dom, data in reversed(sorted_domains) if data.get("percentage", 0) < 70][:3]
    
    strengths_html = ""
    if top_3_strengths:
        for s in top_3_strengths:
            strengths_html += f'<li class="flex items-center gap-2 text-[13px] text-gray-700 mb-1"><svg class="w-4 h-4 text-emerald-500 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"></path></svg>{s}</li>'
    else:
        strengths_html = '<li class="text-[13px] text-gray-400 italic">No strong domains identified</li>'
        
    gaps_html = ""
    if bottom_3_gaps:
        for g in bottom_3_gaps:
            gaps_html += f'<li class="flex items-center gap-2 text-[13px] text-gray-700 mb-1"><svg class="w-4 h-4 text-amber-500 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"></path></svg>{g}</li>'
    else:
        gaps_html = '<li class="text-[13px] text-gray-400 italic">No critical gaps identified</li>'
    
    if passed:
        if score >= 90.0:
            status_msg = "Distinguished Performance"
            cert_color = "text-purple-500"
            cert_bg = "bg-purple-50 border-purple-200"
        else:
            status_msg = "Capability Verified"
            cert_color = "text-emerald-500"
            cert_bg = "bg-emerald-50 border-emerald-200"
    else:
        if critical:
            status_msg = "Critical Gap Identified"
        else:
            status_msg = "Development Required"
        cert_color = "text-amber-500"
        cert_bg = "bg-amber-50 border-amber-200"
    # Domains below 50% for clear feedback
    sub_50_domains = [f"{dom} ({data.get('percentage', 0):.1f}%)" for dom, data in domain_scores.items() if data.get('percentage', 0) < 50.0]

    if passed:
        action_cta_html = f"""
        <div class="bg-white rounded-[16px] shadow-sm border border-emerald-200 p-6">
            <div class="flex items-center justify-between mb-3">
                <h3 class="text-[14px] font-bold text-vivo-navy">VivoIQ Credential</h3>
                <span class="inline-flex items-center px-2 py-0.5 rounded text-[10px] font-bold bg-emerald-100 text-emerald-800">Verified</span>
            </div>
            <p class="text-[13px] text-gray-500 mb-5">Your capability profile has been verified. You have earned your official VivoIQ Credential and are eligible to proceed.</p>
            <div class="space-y-3">
                <a href="/assessment/certificate?resume_id={resume_id}" class="w-full px-5 py-3.5 bg-vivo-brand hover:bg-blue-600 text-white font-bold text-[13px] rounded-[10px] transition-colors shadow-sm shadow-blue-200 flex items-center justify-center gap-2 cursor-pointer">
                    <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z"></path></svg>
                    Claim & View Certificate
                </a>
                <button class="w-full px-5 py-2.5 bg-slate-100 hover:bg-slate-200 text-slate-700 font-semibold text-[13px] rounded-[10px] transition-colors">
                    Attempt Next Level
                </button>
            </div>
        </div>
        """
    else:
        if score >= 70.0 and sub_50_domains:
            lock_desc = f"Overall score achieved is <strong>{score:.1f}%</strong> (≥ 70% threshold met), but credential issuance is currently locked because Section 9 requires a minimum of 50% across all competency domains. Domain gap(s) below 50%: <span class='font-semibold text-amber-700'>{', '.join(sub_50_domains)}</span>."
        else:
            lock_desc = f"VivoIQ certification requires an overall score of <strong>≥ 70%</strong> with no critical domain below 50% (Current score: <strong>{score:.1f}%</strong>)."
            
        action_cta_html = f"""
        <div class="bg-white rounded-[16px] shadow-sm border border-amber-200 p-6">
            <div class="flex items-center justify-between mb-3">
                <h3 class="text-[14px] font-bold text-vivo-navy">VivoIQ Credential Status</h3>
                <span class="inline-flex items-center px-2 py-0.5 rounded text-[10px] font-bold bg-amber-100 text-amber-800">Certificate Locked</span>
            </div>
            <p class="text-[12px] text-gray-600 mb-4 leading-relaxed">{lock_desc}</p>
            <div class="space-y-3">
                <label for="learning-drawer" hx-get="/assessment/learning-recommendations?resume_id={resume_id}" hx-target="#drawer-content" class="w-full px-5 py-3 bg-slate-900 hover:bg-slate-800 text-white font-bold text-[13px] rounded-[10px] transition-colors shadow-sm cursor-pointer flex items-center justify-center gap-2">
                    <svg class="w-4 h-4 text-emerald-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 10V3L4 14h7v7l9-11h-7z"></path></svg>
                    Build My Capability
                </label>
                <div class="w-full px-4 py-2 bg-slate-50 border border-dashed border-slate-200 text-slate-400 text-[11px] font-medium rounded-[10px] flex items-center justify-center gap-2 select-none text-center">
                    <svg class="w-3.5 h-3.5 text-slate-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z"></path></svg>
                    Complete pathway to unlock certificate upon reassessment
                </div>
            </div>
        </div>
        """

    # Build Domain Radar HTML
    domains_html = ""
    for dom, data in domain_scores.items():
        pct = data.get("percentage", 0)
        dom_color = "bg-emerald-500" if pct >= 70 else ("bg-amber-400" if pct >= 50 else "bg-red-500")
        domains_html += f'''
        <div class="mb-4">
            <div class="flex justify-between items-center mb-1">
                <span class="text-[13px] font-bold text-vivo-navy">{dom}</span>
                <span class="text-[12px] font-bold text-gray-500">{pct:.1f}%</span>
            </div>
            <div class="w-full h-2 bg-gray-100 rounded-full overflow-hidden">
                <div class="h-full {dom_color} rounded-full" style="width: {pct}%"></div>
            </div>
        </div>
        '''
    
    html_content = f'''
    <div class="absolute top-6 right-8 z-50 animate-fade-in">
        <a href="/users/logout" class="text-[13px] font-semibold text-gray-400 hover:text-vivo-brand transition-colors flex items-center gap-1.5 cursor-pointer">
            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1"></path></svg> 
            Log out
        </a>
    </div>
    
    <div class="w-full max-w-5xl mx-auto py-10 animate-fade-in-up">
        
        <div class="flex items-center justify-center mb-8 h-12 w-full px-12 max-w-lg mx-auto">
            <div class="flex flex-col items-center relative z-10 w-8">
                <div class="w-6 h-6 rounded-full bg-blue-500 text-white flex items-center justify-center text-[10px] shadow-sm"><svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M5 13l4 4L19 7"></path></svg></div>
                <span class="text-[11px] font-medium text-gray-500 mt-2 absolute top-6 whitespace-nowrap">Account</span>
            </div>
            <div class="flex-grow h-[2px] bg-blue-500 mx-2"></div>
            <div class="flex flex-col items-center relative z-10 w-8">
                <div class="w-6 h-6 rounded-full bg-blue-500 text-white flex items-center justify-center text-[10px] shadow-sm"><svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M5 13l4 4L19 7"></path></svg></div>
                <span class="text-[11px] font-medium text-gray-500 mt-2 absolute top-6 whitespace-nowrap">Resume</span>
            </div>
            <div class="flex-grow h-[2px] bg-blue-500 mx-2"></div>
            <div class="flex flex-col items-center relative z-10 w-8">
                <div class="w-6 h-6 rounded-full bg-blue-500 text-white flex items-center justify-center text-[10px] shadow-sm"><svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M5 13l4 4L19 7"></path></svg></div>
                <span class="text-[11px] font-medium text-gray-500 mt-2 absolute top-6 whitespace-nowrap">Assessment</span>
            </div>
            <div class="flex-grow h-[2px] bg-blue-500 mx-2"></div>
            <div class="flex flex-col items-center relative z-10 w-8">
                <div class="w-6 h-6 rounded-full bg-blue-500 text-white flex items-center justify-center shadow-sm"><div class="w-2 h-2 rounded-full bg-white"></div></div>
                <span class="text-[11px] font-semibold text-vivo-navy mt-2 absolute top-6 whitespace-nowrap">Results</span>
            </div>
        </div>
        
        <!-- Capability Report White Card Wrapper -->
        <div class="w-full bg-white rounded-[12px] shadow-sm border border-gray-200 p-8 lg:p-10 mx-auto">
            <div class="text-center mb-8">
                <h1 class="text-3xl font-extrabold text-vivo-navy tracking-tight mb-2">VivoIQ Capability Report</h1>
                <p class="text-[14px] text-gray-500 font-medium">Verified assessment evaluation & capability tier credential</p>
            </div>
            
            <div class="grid grid-cols-1 lg:grid-cols-3 gap-6">
                
                <!-- Left Column: Primary Verified Score & Level Card -->
                <div class="lg:col-span-1 flex flex-col gap-6">
                    <!-- Score Badge Card -->
                    <div class="bg-white rounded-[16px] shadow-sm border {cert_bg} p-8 text-center flex flex-col items-center justify-center">
                        <div class="w-16 h-16 rounded-full bg-white border border-gray-100 flex items-center justify-center mb-4 {cert_color} shadow-sm">
                        </div>
                        
                        <h2 class="text-[22px] font-bold text-vivo-navy tracking-tight mb-1">{"Capability Verified" if passed else "Capability Gap Identified"}</h2>
                        <p class="text-[13px] font-bold {cert_color} mb-6">{status_msg}</p>
                        
                        <div class="inline-flex flex-col items-center justify-center border-[4px] {cert_color.replace('text', 'border')} rounded-full w-36 h-36 shadow-sm bg-white">
                            <span class="text-4xl font-bold text-vivo-navy">{score:.1f}%</span>
                            <span class="text-[10px] font-bold text-gray-400 uppercase tracking-wider mt-1">Overall Score</span>
                        </div>
                    </div>
                    <!-- Action CTA -->
                    {action_cta_html}
                </div>
                
                <!-- Right Column: Radar & Breakdown -->
                <div class="lg:col-span-2 flex flex-col gap-6">
                    <!-- Top 3 Strengths / Priorities -->
                    <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
                        <div class="bg-white rounded-[16px] shadow-sm border border-emerald-100 p-6">
                            <h3 class="text-[14px] font-bold text-emerald-700 mb-3">Top Demonstrated Strengths</h3>
                            <ul class="space-y-1">
                                {strengths_html}
                            </ul>
                        </div>
                        <div class="bg-white rounded-[16px] shadow-sm border border-amber-100 p-6">
                            <h3 class="text-[14px] font-bold text-amber-700 mb-3">Development Priorities</h3>
                            <ul class="space-y-1">
                                {gaps_html}
                            </ul>
                        </div>
                    </div>
                    
                    <!-- Domain Radar -->
                    <div class="bg-white rounded-[16px] shadow-sm border border-gray-100 p-8 flex-grow">
                        <h3 class="text-lg font-bold text-vivo-navy mb-1">Domain-by-Domain Capability</h3>
                        <p class="text-[13px] text-gray-500 mb-8">Performance against {level_text} expectations. (Pass criteria: 70% overall, no critical domain below 50%)</p>
                        
                        <div class="space-y-3">
                            {domains_html}
                        </div>
                    </div>
                
                </div>
            </div>
        </div>
            
        </div>
        
    </div>
    
    <!-- Slide-Over Drawer Component -->
    <style>
      #learning-drawer:not(:checked) ~ #drawer-backdrop,
      #learning-drawer:not(:checked) ~ #drawer-panel {{
          display: none !important;
      }}
      @keyframes slideInRight {{
          from {{ transform: translateX(100%); }}
          to {{ transform: translateX(0); }}
      }}
      .animate-slide-in {{
          animation: slideInRight 0.3s cubic-bezier(0.16, 1, 0.3, 1) forwards;
      }}
    </style>

    <input id="learning-drawer" type="checkbox" class="hidden" />

    <!-- Backdrop Overlay (Strictly hidden when drawer is closed) -->
    <label for="learning-drawer" id="drawer-backdrop" class="fixed inset-0 bg-slate-900/40 backdrop-blur-sm z-[100] cursor-pointer transition-opacity"></label>

    <!-- Drawer Panel (Strictly hidden when drawer is closed) -->
    <div id="drawer-panel" class="fixed inset-y-0 right-0 z-[101] w-full sm:w-[500px] bg-white shadow-2xl flex flex-col animate-slide-in">
        <!-- Drawer Header -->
        <div class="p-8 border-b border-gray-100 flex items-center justify-between bg-white sticky top-0 z-20">
            <div class="flex items-center gap-4">
                <div class="w-12 h-12 rounded-2xl bg-gradient-to-br from-indigo-500 to-purple-600 flex items-center justify-center text-white shadow-lg shadow-indigo-200">
                    <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19.428 15.428a2 2 0 00-1.022-.547l-2.387-.477a6 6 0 00-3.86.517l-.318.158a6 6 0 01-3.86.517L6.05 15.21a2 2 0 00-1.806.547M8 4h8l-1 1v5.172a2 2 0 00.586 1.414l5 5c1.26 1.26.367 3.414-1.415 3.414H4.828c-1.782 0-2.674-2.154-1.414-3.414l5-5A2 2 0 009 10.172V5L8 4z"></path></svg>
                </div>
                <div>
                    <h3 class="text-xl font-extrabold text-vivo-navy tracking-tight">AI Capability Pathway</h3>
                    <p class="text-[13px] text-gray-500 font-medium">Your personalized recovery plan</p>
                </div>
            </div>
            <label for="learning-drawer" class="w-8 h-8 rounded-full bg-gray-50 hover:bg-gray-100 flex items-center justify-center text-gray-500 cursor-pointer transition-colors">
              <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M6 18L18 6M6 6l12 12"></path></svg>
            </label>
        </div>
        
        <!-- Drawer Content Area (Targeted by HTMX) -->
        <div id="drawer-content" class="p-8 overflow-y-auto flex-grow bg-slate-50 relative">
            <!-- Animated Skeleton Loader (Replaced by HTMX) -->
            <div class="animate-pulse flex flex-col gap-8 relative z-10 pl-2">
                <div class="absolute top-2 left-3 bottom-0 w-0.5 bg-gray-200"></div>
                
                <div class="relative pl-8">
                    <div class="absolute top-1.5 -left-1.5 w-6 h-6 rounded-full bg-gray-200 border-2 border-white shadow-sm z-10"></div>
                    <div class="bg-white rounded-[20px] p-6 border border-gray-100 shadow-sm">
                        <div class="w-24 h-3 bg-gray-200 rounded-full mb-4"></div>
                        <div class="w-48 h-5 bg-gray-300 rounded mb-8"></div>
                        <div class="w-full h-16 bg-gray-100 rounded-xl mb-4"></div>
                        <div class="flex justify-between mt-6">
                            <div class="w-24 h-4 bg-gray-100 rounded"></div>
                            <div class="w-24 h-4 bg-gray-100 rounded"></div>
                        </div>
                    </div>
                </div>
                
                <div class="relative pl-8">
                    <div class="absolute top-1.5 -left-1.5 w-6 h-6 rounded-full bg-gray-200 border-2 border-white shadow-sm z-10"></div>
                    <div class="bg-white rounded-[20px] p-6 border border-gray-100 shadow-sm">
                        <div class="w-20 h-3 bg-gray-200 rounded-full mb-4"></div>
                        <div class="w-40 h-5 bg-gray-300 rounded mb-8"></div>
                        <div class="w-full h-16 bg-gray-100 rounded-xl mb-4"></div>
                    </div>
                </div>
            </div>
        </div>
        
        <!-- Drawer Footer -->
        <div class="p-6 border-t border-gray-100 bg-white">
            <button class="w-full py-3.5 bg-vivo-brand hover:bg-blue-600 text-white font-bold text-[14px] rounded-xl shadow-sm shadow-blue-200 transition-colors flex items-center justify-center gap-2">
                <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"></path></svg>
                Export Learning Plan to PDF
            </button>
        </div>
    </div>
    '''
    return HTMLResponse(content=html_content)



def format_evidence_user_friendly(evidence_text: str) -> str:
    if not evidence_text:
        return ""
    import re
    cleaned = re.sub(r'\s*\([qQ]\d+\)', '', evidence_text).strip()
    score_match = re.match(r'Scored\s+(\d+(?:\.\d+)?%)\s+in\s+([^,]+),\s*(.*)', cleaned, re.IGNORECASE)
    score_badge = ""
    details = cleaned
    
    if score_match:
        score_val = score_match.group(1)
        details = score_match.group(3).strip()
        score_badge = f'''
        <div class="flex items-center gap-2 mb-2">
            <span class="inline-flex items-center px-2 py-0.5 rounded-md text-[11px] font-bold bg-rose-50 text-rose-700 border border-rose-200">
                Score: {score_val}
            </span>
            <span class="text-[11px] font-medium text-slate-500">Benchmark target not met</span>
        </div>
        '''
    
    softened = re.sub(r'^(failed calculations for|failed|failing to|struggling to articulate|struggling to|inability to)\s+', '', details, flags=re.IGNORECASE).strip()
    if softened:
        softened = softened[0].upper() + softened[1:]
    else:
        softened = details
        
    return f'''
    {score_badge}
    <div class="flex items-start gap-2 text-slate-700 text-[13px] leading-relaxed">
        <svg class="w-4 h-4 text-amber-500 flex-shrink-0 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"></path>
        </svg>
        <span class="font-normal text-slate-700">{softened}</span>
    </div>
    '''

@app.get("/assessment/learning-recommendations", response_class=HTMLResponse)
async def generate_learning_recommendations(resume_id: int, request: Request, session: AsyncSession = Depends(get_session)):
    user_id_cookie = request.cookies.get("user_id")
    if not user_id_cookie: return HTMLResponse("Unauthorized", status_code=401)
    user_id = int(user_id_cookie)
    
    # 0. Check if learning pathway was already generated and cached in DB via Stored Procedure
    cached_res = await session.execute(
        text("CALL GetLearningPathwayByResumeId(:r_id)"),
        {"r_id": resume_id}
    )
    cached_row = cached_res.mappings().first()
    
    recommendations = None
    if cached_row and cached_row.get("pathway_json"):
        try:
            recommendations = json.loads(cached_row["pathway_json"])
        except Exception:
            recommendations = None
            
    if not recommendations:
        # 1. Get Assessment Result via Stored Procedure
        result = await session.execute(text("CALL GetLatestAssessmentResult(:r_id)"), {"r_id": resume_id})
        score_row = result.mappings().first()
        if not score_row: return HTMLResponse("Results not found", status_code=404)
        
        try:
            ai7_results = json.loads(score_row["breakdown_json"])
        except:
            return HTMLResponse("Invalid results format", status_code=500)
            
        # 2. Get Expected Level via Stored Procedure
        prof_res = await session.execute(text("CALL GetCandidateProfileWithLevel(:r_id)"), {"r_id": resume_id})
        prof_row = prof_res.mappings().first()
        expected_level = prof_row.get("expected_level", 1) if prof_row else 1
        
        # 3. Call AI-8
        from ai_agents import run_learning_recommendation_agent
        recommendations = run_learning_recommendation_agent(ai7_results, expected_level)
        
        pathway = recommendations.get("learning_pathway", [])
        if not pathway:
            return HTMLResponse("<div class='p-6 bg-red-50 text-red-600 rounded-[16px] shadow-sm'>Failed to generate learning pathway. Please try again.</div>")
            
        # 4. Cache in Database via Stored Procedure
        try:
            await session.execute(
                text("CALL SaveLearningPathway(:u_id, :r_id, :p_json)"),
                {"u_id": user_id, "r_id": resume_id, "p_json": json.dumps(recommendations)}
            )
            await session.commit()
        except Exception as e:
            print(f"Error caching learning pathway: {e}")
            
    pathway = recommendations.get("learning_pathway", [])
        
    cards_html = ""
    for i, rec in enumerate(pathway):
        priority = str(rec.get("priority", "")).lower()
        if priority == "high":
            icon_color = "text-rose-500"
            bg_color = "bg-rose-50"
            border_color = "border-rose-100"
            icon = '<svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 10V3L4 14h7v7l9-11h-7z"></path></svg>'
        elif priority == "medium":
            icon_color = "text-amber-500"
            bg_color = "bg-amber-50"
            border_color = "border-amber-100"
            icon = '<svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"></path></svg>'
        else:
            icon_color = "text-emerald-500"
            bg_color = "bg-emerald-50"
            border_color = "border-emerald-100"
            icon = '<svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"></path></svg>'
            
        is_mandatory = str(rec.get("type", "")).lower() == "mandatory"
        badge_html = f'<span class="px-2.5 py-1 bg-slate-800 text-white rounded-full text-[10px] font-bold uppercase tracking-wider shadow-sm">{"Mandatory" if is_mandatory else "Optional"}</span>'
        formatted_evidence = format_evidence_user_friendly(rec.get("evidence", ""))
        
        cards_html += f'''
        <div class="relative pl-8 pb-8 group">
            <!-- Timeline Line -->
            <div class="absolute top-8 left-[11px] bottom-0 w-0.5 bg-gray-100 group-last:bg-transparent"></div>
            
            <!-- Timeline Dot -->
            <div class="absolute top-1.5 left-0 w-6 h-6 rounded-full {bg_color} flex items-center justify-center border-2 border-white shadow-sm z-10 {icon_color}">
                {icon}
            </div>
            
            <!-- Card -->
            <div class="bg-white rounded-[20px] p-6 shadow-[0_2px_12px_-4px_rgba(0,0,0,0.06)] border border-gray-100 transition-all hover:shadow-[0_8px_24px_-8px_rgba(0,0,0,0.12)] hover:border-gray-200">
                
                <div class="flex flex-wrap items-start justify-between gap-4 mb-5">
                    <div>
                        <span class="text-[12px] font-bold uppercase tracking-wider {icon_color} mb-1 block">{rec.get("domain")}</span>
                        <h4 class="text-[18px] font-extrabold text-vivo-navy leading-tight">{rec.get("recommended_asset", "Targeted Training")}</h4>
                    </div>
                    <div>{badge_html}</div>
                </div>
                
                <div class="space-y-3 mb-5">
                    <!-- Identified Gap Focus -->
                    <div class="bg-amber-50/50 rounded-[14px] p-4 border border-amber-200/60">
                        <span class="text-[11px] font-bold text-amber-800 uppercase tracking-wider mb-1 flex items-center gap-1.5">
                            <svg class="w-3.5 h-3.5 text-amber-600" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"></path></svg>
                            Capability Gap Focus
                        </span>
                        <p class="text-[13px] text-slate-800 leading-relaxed font-semibold">{rec.get("gap")}</p>
                    </div>
                    
                    <!-- Observed in Assessment (User-Friendly Evidence) -->
                    <div class="bg-slate-50/80 rounded-[14px] p-4 border border-slate-200/80">
                        <div class="flex items-center justify-between mb-2">
                            <span class="text-[11px] font-bold text-slate-500 uppercase tracking-wider flex items-center gap-1.5">
                                <svg class="w-3.5 h-3.5 text-blue-500" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2"></path></svg>
                                Observed in Assessment
                            </span>
                            <span class="text-[10px] font-semibold text-slate-400 bg-white px-2 py-0.5 rounded border border-slate-200">Diagnostic Insight</span>
                        </div>
                        {formatted_evidence}
                    </div>
                </div>
                
                <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pt-1">
                    <div class="flex items-center gap-2">
                        <div class="w-8 h-8 rounded-full bg-blue-50 flex items-center justify-center text-vivo-brand">
                            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 7h8m0 0v8m0-8l-8 8-4-4-6 6"></path></svg>
                        </div>
                        <div>
                            <span class="text-[11px] font-bold text-gray-400 uppercase tracking-wider block">Expected Outcome</span>
                            <span class="text-[13px] font-semibold text-vivo-navy">{rec.get("expected_outcome")}</span>
                        </div>
                    </div>
                    <div class="flex items-center gap-2">
                        <div class="w-8 h-8 rounded-full bg-purple-50 flex items-center justify-center text-purple-600">
                            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z"></path></svg>
                        </div>
                        <div>
                            <span class="text-[11px] font-bold text-gray-400 uppercase tracking-wider block">Reassessment</span>
                            <span class="text-[13px] font-semibold text-vivo-navy">{rec.get("suggested_reassessment")}</span>
                        </div>
                    </div>
                </div>
                
            </div>
        </div>
        '''
        

    html = f'''
    <div class="animate-fade-in pl-2 relative pb-8">
        {cards_html}
    </div>
    '''
    return HTMLResponse(content=html)

def build_certificate_pdf(
    candidate_name: str,
    cred_id: str,
    verified_level: str,
    cert_title: str,
    score: float,
    issued_date: str,
    narrative_summary: str,
    verified_domains: list,
    scope_of_practice: str = "",
    has_distinction: bool = False,
    distinction_title: str = "Conferred with High Distinction"
) -> bytes:
    from reportlab.lib.pagesizes import landscape, A4
    from reportlab.lib import colors
    from reportlab.pdfgen import canvas
    from reportlab.platypus import Paragraph
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.utils import ImageReader
    import qrcode

    buffer = io.BytesIO()
    page_w, page_h = landscape(A4)
    c = canvas.Canvas(buffer, pagesize=(page_w, page_h))
    
    margin = 22
    c.setFillColor(colors.HexColor("#FFFFFF"))
    c.rect(0, 0, page_w, page_h, fill=1, stroke=0)
    
    # Outer Border
    c.setStrokeColor(colors.HexColor("#0f172a"))
    c.setLineWidth(4)
    c.roundRect(margin, margin, page_w - 2 * margin, page_h - 2 * margin, 12, fill=0, stroke=1)
    
    # Second Thin Border
    c.setStrokeColor(colors.HexColor("#334155"))
    c.setLineWidth(0.8)
    c.roundRect(margin + 4, margin + 4, page_w - 2 * margin - 8, page_h - 2 * margin - 8, 10, fill=0, stroke=1)

    # Inner Gold Border
    gold_color = colors.HexColor("#d97706")
    c.setStrokeColor(gold_color)
    c.setLineWidth(1.5)
    c.roundRect(margin + 10, margin + 10, page_w - 2 * margin - 20, page_h - 2 * margin - 20, 8, fill=0, stroke=1)

    # Corner Accents (Gold)
    accent_len = 25
    c.setStrokeColor(gold_color)
    c.setLineWidth(2)
    c.line(margin + 16, page_h - margin - 16, margin + 16 + accent_len, page_h - margin - 16)
    c.line(margin + 16, page_h - margin - 16, margin + 16, page_h - margin - 16 - accent_len)
    c.line(page_w - margin - 16, page_h - margin - 16, page_w - margin - 16 - accent_len, page_h - margin - 16)
    c.line(page_w - margin - 16, page_h - margin - 16, page_w - margin - 16, page_h - margin - 16 - accent_len)
    c.line(margin + 16, margin + 16, margin + 16 + accent_len, margin + 16)
    c.line(margin + 16, margin + 16, margin + 16, margin + 16 + accent_len)
    c.line(page_w - margin - 16, margin + 16, page_w - margin - 16 - accent_len, margin + 16)
    c.line(page_w - margin - 16, margin + 16, page_w - margin - 16, margin + 16 + accent_len)

    # Header Branding
    c.setFont("Helvetica-Bold", 24)
    c.setFillColor(colors.HexColor("#0f172a"))
    c.drawCentredString(page_w / 2.0, page_h - 60, "V I V O I Q")
    
    c.setFont("Helvetica-Bold", 7.5)
    c.setFillColor(colors.HexColor("#64748b"))
    c.drawCentredString(page_w / 2.0, page_h - 73, "GLOBAL PROCUREMENT CAPABILITY VERIFICATION REGISTRY")

    # Credential Type Badge
    badge_text = "OFFICIAL EVALUATION CREDENTIAL • SECTION 11 VERIFIED"
    c.setFont("Helvetica-Bold", 8)
    badge_w = c.stringWidth(badge_text, "Helvetica-Bold", 8) + 16
    badge_x = (page_w - badge_w) / 2.0
    c.setFillColor(colors.HexColor("#eff6ff"))
    c.setStrokeColor(colors.HexColor("#bfdbfe"))
    c.setLineWidth(0.8)
    c.roundRect(badge_x, page_h - 96, badge_w, 16, 4, fill=1, stroke=1)
    c.setFillColor(colors.HexColor("#1d4ed8"))
    c.drawCentredString(page_w / 2.0, page_h - 92, badge_text)

    # Credential Title
    c.setFont("Helvetica-Bold", 18)
    c.setFillColor(colors.HexColor("#0f172a"))
    c.drawCentredString(page_w / 2.0, page_h - 122, cert_title)

    # Optional Distinction
    if has_distinction:
        c.setFont("Helvetica-Bold", 9)
        c.setFillColor(colors.HexColor("#b45309"))
        dist_text = f"★  {distinction_title} • Top Tier Performance ({score:.1f}%)  ★"
        c.drawCentredString(page_w / 2.0, page_h - 138, dist_text)
        current_y = page_h - 156
    else:
        current_y = page_h - 146

    # Candidate Name
    c.setFont("Helvetica-Oblique", 10.5)
    c.setFillColor(colors.HexColor("#64748b"))
    c.drawCentredString(page_w / 2.0, current_y, "This certifies that")
    current_y -= 26

    c.setFont("Times-Bold", 26)
    c.setFillColor(colors.HexColor("#0f172a"))
    c.drawCentredString(page_w / 2.0, current_y, candidate_name)
    
    name_w = c.stringWidth(candidate_name, "Times-Bold", 26)
    c.setStrokeColor(gold_color)
    c.setLineWidth(1.5)
    c.line((page_w - name_w) / 2.0, current_y - 4, (page_w + name_w) / 2.0, current_y - 4)
    current_y -= 20

    # Framework Standard Statement (Section 11)
    c.setFont("Helvetica", 9.5)
    c.setFillColor(colors.HexColor("#475569"))
    stmt1 = "has demonstrated verified professional capability through the VivoIQ AI-Enabled Adaptive Assessment."
    stmt2 = f"Verified Competency Tier: {verified_level}   |   Evaluation Score: {score:.1f}%"
    c.drawCentredString(page_w / 2.0, current_y, stmt1)
    current_y -= 14
    c.setFont("Helvetica-Bold", 10)
    c.setFillColor(colors.HexColor("#1e3a8a"))
    c.drawCentredString(page_w / 2.0, current_y, stmt2)
    current_y -= 24

    # Middle Grid: Narrative & Competencies
    grid_y = current_y
    grid_h = 105
    col_w = (page_w - 2 * margin - 70) / 2.0
    left_x = margin + 30
    right_x = left_x + col_w + 10

    # Left Box: AI Capability Narrative
    c.setFillColor(colors.HexColor("#f8fafc"))
    c.setStrokeColor(colors.HexColor("#e2e8f0"))
    c.setLineWidth(0.8)
    c.roundRect(left_x, grid_y - grid_h, col_w, grid_h, 6, fill=1, stroke=1)

    c.setFont("Helvetica-Bold", 8)
    c.setFillColor(colors.HexColor("#2563eb"))
    c.drawString(left_x + 12, grid_y - 18, "VERIFIED CAPABILITY NARRATIVE")

    styles = getSampleStyleSheet()
    narrative_style = ParagraphStyle(
        'Narrative',
        fontName='Helvetica-Oblique',
        fontSize=8.5,
        leading=12.5,
        textColor=colors.HexColor("#334155")
    )
    p_narrative = Paragraph(f'"{narrative_summary}"', narrative_style)
    w_p, h_p = p_narrative.wrap(col_w - 24, grid_h - 30)
    p_narrative.drawOn(c, left_x + 12, grid_y - 26 - h_p)

    # Right Box: Verified Domains & Scope
    c.setFillColor(colors.HexColor("#f8fafc"))
    c.setStrokeColor(colors.HexColor("#e2e8f0"))
    c.setLineWidth(0.8)
    c.roundRect(right_x, grid_y - grid_h, col_w, grid_h, 6, fill=1, stroke=1)

    c.setFont("Helvetica-Bold", 8)
    c.setFillColor(colors.HexColor("#059669"))
    c.drawString(right_x + 12, grid_y - 18, "PRIMARY VERIFIED COMPETENCY DOMAINS")

    d_x = right_x + 12
    d_y = grid_y - 38
    for d in verified_domains[:6]:
        c.setFont("Helvetica-Bold", 7.5)
        t_w = c.stringWidth(d, "Helvetica-Bold", 7.5) + 12
        if d_x + t_w > right_x + col_w - 12:
            d_x = right_x + 12
            d_y -= 18
        c.setFillColor(colors.HexColor("#ecfdf5"))
        c.setStrokeColor(colors.HexColor("#a7f3d0"))
        c.setLineWidth(0.6)
        c.roundRect(d_x, d_y, t_w, 14, 3, fill=1, stroke=1)
        c.setFillColor(colors.HexColor("#065f46"))
        c.drawString(d_x + 6, d_y + 3.5, d)
        d_x += t_w + 6

    if scope_of_practice:
        c.setFont("Helvetica-Bold", 7.5)
        c.setFillColor(colors.HexColor("#64748b"))
        c.drawString(right_x + 12, grid_y - 74, "OPERATIONAL SCOPE:")
        scope_style = ParagraphStyle(
            'Scope',
            fontName='Helvetica',
            fontSize=7.5,
            leading=10.5,
            textColor=colors.HexColor("#475569")
        )
        p_scope = Paragraph(scope_of_practice, scope_style)
        w_s, h_s = p_scope.wrap(col_w - 24, 26)
        p_scope.drawOn(c, right_x + 12, grid_y - 78 - h_s)

    # Bottom Signatures, QR Code & Seal
    bottom_y = grid_y - grid_h - 15
    c.setStrokeColor(colors.HexColor("#cbd5e1"))
    c.setLineWidth(0.6)
    c.line(margin + 30, bottom_y + 5, page_w - margin - 30, bottom_y + 5)

    # Left: QR Code & Verification URL
    qr_url = f"https://verify.vivoiq.com/credential/{cred_id}"
    qr = qrcode.QRCode(box_size=3, border=1)
    qr.add_data(qr_url)
    qr.make(fit=True)
    qr_img = qr.make_image(fill_color="black", back_color="white")
    qr_io = io.BytesIO()
    qr_img.save(qr_io, format="PNG")
    qr_io.seek(0)
    
    qr_reader = ImageReader(qr_io)
    c.drawImage(qr_reader, margin + 30, bottom_y - 60, width=54, height=54)

    c.setFont("Helvetica-Bold", 8)
    c.setFillColor(colors.HexColor("#0f172a"))
    c.drawString(margin + 92, bottom_y - 18, f"Credential ID: {cred_id}")
    
    c.setFont("Helvetica", 7.5)
    c.setFillColor(colors.HexColor("#64748b"))
    c.drawString(margin + 92, bottom_y - 30, f"Assessment Date: {issued_date}")
    c.drawString(margin + 92, bottom_y - 42, "Validity / Policy: Annual Reassessment Recommended")
    c.setFillColor(colors.HexColor("#2563eb"))
    c.drawString(margin + 92, bottom_y - 54, qr_url)

    # Center: Embossed Gold Seal
    seal_cx = page_w / 2.0
    seal_cy = bottom_y - 32
    c.setFillColor(colors.HexColor("#fef3c7"))
    c.setStrokeColor(colors.HexColor("#d97706"))
    c.setLineWidth(2)
    c.circle(seal_cx, seal_cy, 28, fill=1, stroke=1)
    c.setStrokeColor(colors.HexColor("#b45309"))
    c.setLineWidth(1)
    c.circle(seal_cx, seal_cy, 24, fill=0, stroke=1)
    c.setFont("Helvetica-Bold", 6.5)
    c.setFillColor(colors.HexColor("#78350f"))
    c.drawCentredString(seal_cx, seal_cy + 8, "VIVO-IQ")
    c.setFont("Helvetica-Bold", 7.5)
    c.drawCentredString(seal_cx, seal_cy - 2, "VERIFIED")
    c.setFont("Helvetica", 6)
    c.drawCentredString(seal_cx, seal_cy - 12, "REGISTRY SEAL")

    # Right: Board of Assessors
    right_align_x = page_w - margin - 30
    c.setFont("Times-BoldItalic", 15)
    c.setFillColor(colors.HexColor("#0f172a"))
    c.drawRightString(right_align_x, bottom_y - 20, "VivoIQ Board of Assessors")
    
    c.setStrokeColor(colors.HexColor("#94a3b8"))
    c.setLineWidth(0.8)
    c.line(right_align_x - 180, bottom_y - 24, right_align_x, bottom_y - 24)

    c.setFont("Helvetica-Bold", 7.5)
    c.setFillColor(colors.HexColor("#64748b"))
    c.drawRightString(right_align_x, bottom_y - 35, "Capability Verification Standard 1.0")
    c.setFont("Helvetica", 7)
    c.setFillColor(colors.HexColor("#059669"))
    c.drawRightString(right_align_x, bottom_y - 47, "AI-Evaluated & Cryptographically Registered")

    # Section 11 Legal Disclaimer Footnote
    c.setFont("Helvetica", 6.8)
    c.setFillColor(colors.HexColor("#94a3b8"))
    disclaimer = "Section 11 Notice: This credential certifies verified capability demonstrated under the VivoIQ AI-Enabled Assessment Framework 1.0. This represents an AI-enabled self-evaluation and does not imply a proctored professional license."
    c.drawCentredString(page_w / 2.0, margin + 14, disclaimer)

    c.save()
    buffer.seek(0)
    return buffer.getvalue()


@app.get("/assessment/certificate/pdf")
async def download_certificate_pdf(resume_id: int, request: Request, session: AsyncSession = Depends(get_session)):
    user_id_cookie = request.cookies.get("user_id")
    if not user_id_cookie: return HTMLResponse("Unauthorized", status_code=401)
    user_id = int(user_id_cookie)
    
    # Check Certificate via Stored Procedure
    cert_res = await session.execute(text("CALL GetCertificateByResumeId(:r_id)"), {"r_id": resume_id})
    cert_row = cert_res.mappings().first()
    
    # If not generated yet, generate and save it via Stored Procedure
    if not cert_row:
        score_res = await session.execute(text("CALL GetLatestAssessmentResult(:r_id)"), {"r_id": resume_id})
        score_row = score_res.mappings().first()
        if not score_row:
            return HTMLResponse("Assessment result not found", status_code=404)
        score = float(score_row["total_score"])
        try:
            ai7 = json.loads(score_row["breakdown_json"])
            if isinstance(ai7, list): ai7 = {"overall_percentage": score, "domain_scores": {}, "passed": (score >= 70.0), "critical_failure": False}
        except Exception:
            ai7 = {"overall_percentage": score, "domain_scores": {}, "passed": (score >= 70.0), "critical_failure": False}
        if not ai7.get("passed", score >= 70.0) or ai7.get("critical_failure", False) or score < 70.0:
            return HTMLResponse("Candidate not eligible for certificate", status_code=403)
            
        user_res = await session.execute(text("CALL GetUserById(:u_id)"), {"u_id": user_id})
        user_row = user_res.mappings().first()
        candidate_name = user_row["name"].title() if (user_row and user_row.get("name")) else "Procurement Professional"
        
        prof_res = await session.execute(text("CALL GetCandidateProfileWithLevel(:r_id)"), {"r_id": resume_id})
        prof_row = prof_res.mappings().first()
        expected_level = prof_row.get("expected_level", 1) if prof_row else 1
        levels_map = {1: "Foundation", 2: "Practitioner", 3: "Advanced", 4: "Expert", 5: "Leader"}
        level_name = levels_map.get(expected_level, "Practitioner")
        
        import secrets
        from datetime import datetime
        cred_id = f"VIQ-{datetime.now().year}-L{expected_level}-{secrets.token_hex(3).upper()}"
        
        from ai_agents import run_certificate_narrative_agent
        narrative_data = run_certificate_narrative_agent(candidate_name, ai7, expected_level, level_name)
        
        cert_title = "VivoIQ Procurement Capability — Self-Evaluation"
        verified_level_str = f"Level {expected_level} — {level_name}"
        has_distinction = 1 if (narrative_data.get("has_distinction") or score >= 90.0) else 0
        narrative_summary = narrative_data.get("verified_capability_summary", "")
        verified_domains = narrative_data.get("primary_verified_domains", [])
        
        metadata = {
            "evaluation_standard": "VivoIQ AI-Enabled Capability Verification Framework 1.0",
            "scope_of_practice": narrative_data.get("scope_of_practice", ""),
            "distinction_title": narrative_data.get("distinction_title", "Conferred with High Distinction" if has_distinction else ""),
            "candidate_name": candidate_name,
            "overall_score": score,
            "verification_url": f"https://verify.vivoiq.com/credential/{cred_id}"
        }
        
        await session.execute(
            text("CALL SaveCertificate(:u_id, :r_id, :cred_id, :title, :level, :score, :distinction, :narrative, :domains_json, :meta_json)"),
            {
                "u_id": user_id,
                "r_id": resume_id,
                "cred_id": cred_id,
                "title": cert_title,
                "level": verified_level_str,
                "score": score,
                "distinction": has_distinction,
                "narrative": narrative_summary,
                "domains_json": json.dumps(verified_domains),
                "meta_json": json.dumps(metadata)
            }
        )
        await session.commit()
        cert_res = await session.execute(text("CALL GetCertificateByResumeId(:r_id)"), {"r_id": resume_id})
        cert_row = cert_res.mappings().first()

    # Parse stored record
    cert_title = "VivoIQ Procurement Capability — Self-Evaluation"
    verified_level_str = cert_row["verified_level"]
    score = float(cert_row["overall_score"])
    has_distinction = bool(cert_row["has_distinction"])
    narrative_summary = cert_row["narrative_summary"]
    cred_id = cert_row["credential_id"]
    issued_date = cert_row["issued_at"].strftime("%B %d, %Y") if hasattr(cert_row["issued_at"], "strftime") else str(cert_row["issued_at"])
    
    try:
        verified_domains = json.loads(cert_row["verified_domains_json"])
    except Exception:
        verified_domains = []
        
    try:
        metadata = json.loads(cert_row["metadata_json"])
    except Exception:
        metadata = {}
        
    candidate_name = metadata.get("candidate_name", "Procurement Professional").title()
    scope_of_practice = metadata.get("scope_of_practice", "")
    distinction_title = metadata.get("distinction_title", "Conferred with High Distinction" if has_distinction else "")
    
    pdf_bytes = build_certificate_pdf(
        candidate_name=candidate_name,
        cred_id=cred_id,
        verified_level=verified_level_str,
        cert_title=cert_title,
        score=score,
        issued_date=issued_date,
        narrative_summary=narrative_summary,
        verified_domains=verified_domains,
        scope_of_practice=scope_of_practice,
        has_distinction=has_distinction,
        distinction_title=distinction_title
    )
    
    safe_name = candidate_name.replace(" ", "_").replace("'", "")
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="VivoIQ_Certificate_{safe_name}_{cred_id}.pdf"'
        }
    )


@app.get("/assessment/certificate", response_class=HTMLResponse)
async def view_certificate(resume_id: int, request: Request, session: AsyncSession = Depends(get_session)):
    user_id_cookie = request.cookies.get("user_id")
    if not user_id_cookie: return HTMLResponse("Unauthorized", status_code=401)
    user_id = int(user_id_cookie)
    
    # 1. Check if Certificate is already generated in DB via Stored Procedure
    cert_res = await session.execute(text("CALL GetCertificateByResumeId(:r_id)"), {"r_id": resume_id})
    cert_row = cert_res.mappings().first()
    
    if not cert_row:
        # 2. Check Assessment Results via Stored Procedure
        score_res = await session.execute(text("CALL GetLatestAssessmentResult(:r_id)"), {"r_id": resume_id})
        score_row = score_res.mappings().first()
        if not score_row:
            return HTMLResponse("Assessment result not found", status_code=404)
            
        score = float(score_row["total_score"])
        try:
            ai7_results = json.loads(score_row["breakdown_json"])
            if isinstance(ai7_results, list):
                ai7_results = {"overall_percentage": score, "domain_scores": {}, "passed": (score >= 70.0), "critical_failure": False}
        except Exception:
            ai7_results = {"overall_percentage": score, "domain_scores": {}, "passed": (score >= 70.0), "critical_failure": False}
            
        passed = ai7_results.get("passed", score >= 70.0)
        critical = ai7_results.get("critical_failure", False)
        
        # Section 9 Rule: 70% overall, no critical domain < 50%
        if not passed or critical or score < 70.0:
            return HTMLResponse(f"""
            <div class="min-h-[70vh] flex items-center justify-center p-4">
                <div class="max-w-md w-full bg-white rounded-2xl shadow-sm border border-amber-200 p-8 text-center">
                    <div class="w-14 h-14 rounded-full bg-amber-50 text-amber-500 border border-amber-200 flex items-center justify-center mx-auto mb-5 shadow-sm">
                        <svg class="w-7 h-7" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"></path></svg>
                    </div>
                    <h3 class="text-xl font-extrabold text-slate-800 mb-2">Certificate Requirement Not Met</h3>
                    <p class="text-sm text-slate-500 mb-6 leading-relaxed">VivoIQ credentials require an overall score of at least <strong>70%</strong> with no critical domain below 50%. Your verified score was <strong>{score:.1f}%</strong>.</p>
                    <a href="/assessment/results?resume_id={resume_id}" class="inline-flex items-center justify-center px-6 py-3 bg-slate-900 hover:bg-slate-800 text-white text-xs font-bold uppercase tracking-wider rounded-xl transition-colors shadow-sm">Return to Capability Dashboard</a>
                </div>
            </div>
            """, status_code=403)
            
        # 3. Retrieve Candidate & Profile via Stored Procedures
        user_res = await session.execute(text("CALL GetUserById(:u_id)"), {"u_id": user_id})
        user_row = user_res.mappings().first()
        candidate_name = user_row["name"].title() if (user_row and user_row.get("name")) else "Procurement Professional"
        
        prof_res = await session.execute(text("CALL GetCandidateProfileWithLevel(:r_id)"), {"r_id": resume_id})
        prof_row = prof_res.mappings().first()
        expected_level = prof_row.get("expected_level", 1) if prof_row else 1
        levels_map = {1: "Foundation", 2: "Practitioner", 3: "Advanced", 4: "Expert", 5: "Leader"}
        level_name = levels_map.get(expected_level, "Practitioner")
        
        # 4. Generate Credential ID
        import secrets
        from datetime import datetime
        cred_id = f"VIQ-{datetime.now().year}-L{expected_level}-{secrets.token_hex(3).upper()}"
        
        # 5. Invoke AI-9 (Certificate Narrative Agent)
        from ai_agents import run_certificate_narrative_agent
        narrative_data = run_certificate_narrative_agent(candidate_name, ai7_results, expected_level, level_name)
        
        cert_title = "VivoIQ Procurement Capability — Self-Evaluation"
        verified_level_str = f"Level {expected_level} — {level_name}"
        has_distinction = 1 if (narrative_data.get("has_distinction") or score >= 90.0) else 0
        narrative_summary = narrative_data.get("verified_capability_summary", "")
        verified_domains = narrative_data.get("primary_verified_domains", [])
        
        metadata = {
            "evaluation_standard": "VivoIQ AI-Enabled Capability Verification Framework 1.0",
            "scope_of_practice": narrative_data.get("scope_of_practice", ""),
            "distinction_title": narrative_data.get("distinction_title", "Conferred with High Distinction" if has_distinction else ""),
            "candidate_name": candidate_name,
            "overall_score": score,
            "verification_url": f"https://verify.vivoiq.com/credential/{cred_id}"
        }
        
        # 6. Save Certificate to Database via Stored Procedure
        await session.execute(
            text("CALL SaveCertificate(:u_id, :r_id, :cred_id, :title, :level, :score, :distinction, :narrative, :domains_json, :meta_json)"),
            {
                "u_id": user_id,
                "r_id": resume_id,
                "cred_id": cred_id,
                "title": cert_title,
                "level": verified_level_str,
                "score": score,
                "distinction": has_distinction,
                "narrative": narrative_summary,
                "domains_json": json.dumps(verified_domains),
                "meta_json": json.dumps(metadata)
            }
        )
        await session.commit()
        
        # Reload via Stored Procedure
        cert_res = await session.execute(text("CALL GetCertificateByResumeId(:r_id)"), {"r_id": resume_id})
        cert_row = cert_res.mappings().first()

    # Parse stored record
    cert_title = "VivoIQ Procurement Capability — Self-Evaluation"
    verified_level_str = cert_row["verified_level"]
    score = float(cert_row["overall_score"])
    has_distinction = bool(cert_row["has_distinction"])
    narrative_summary = cert_row["narrative_summary"]
    cred_id = cert_row["credential_id"]
    issued_date = cert_row["issued_at"].strftime("%B %d, %Y") if hasattr(cert_row["issued_at"], "strftime") else str(cert_row["issued_at"])
    
    try:
        verified_domains = json.loads(cert_row["verified_domains_json"])
    except Exception:
        verified_domains = []
        
    try:
        metadata = json.loads(cert_row["metadata_json"])
    except Exception:
        metadata = {}
        
    candidate_name = metadata.get("candidate_name", "Procurement Professional").title()
    scope_of_practice = metadata.get("scope_of_practice", "")
    distinction_title = metadata.get("distinction_title", "Conferred with High Distinction" if has_distinction else "")
    
    # Generate QR Code as data URI for web preview
    qr = qrcode.QRCode(box_size=3, border=1)
    qr_url = f"https://verify.vivoiq.com/credential/{cred_id}"
    qr.add_data(qr_url)
    qr.make(fit=True)
    qr_img = qr.make_image(fill_color="black", back_color="white")
    qr_buf = io.BytesIO()
    qr_img.save(qr_buf, format="PNG")
    qr_img_src = f"data:image/png;base64,{base64.b64encode(qr_buf.getvalue()).decode('utf-8')}"

    # Mastered Domains Badges HTML
    domains_badges_html = "".join([
        f'<span class="inline-flex items-center gap-1 px-2.5 py-1 rounded-md text-[11px] font-bold bg-emerald-50 text-emerald-800 border border-emerald-200/80"><svg class="w-3 h-3 text-emerald-600" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M5 13l4 4L19 7"></path></svg>{d}</span>'
        for d in verified_domains
    ])
    
    distinction_ribbon_html = f'''
    <div class="inline-flex items-center gap-1.5 px-3.5 py-1 rounded-full bg-gradient-to-r from-amber-400/20 via-yellow-500/20 to-amber-400/20 border border-amber-300 text-amber-900 font-extrabold text-[11px] tracking-wider uppercase mb-2 shadow-sm">
        <svg class="w-3.5 h-3.5 text-amber-600" fill="currentColor" viewBox="0 0 20 20"><path d="M9.049 2.927c.3-.921 1.603-.921 1.902 0l1.07 3.292a1 1 0 00.95.69h3.462c.969 0 1.371 1.24.588 1.81l-2.8 2.034a1 1 0 00-.364 1.118l1.07 3.292c.3.921-.755 1.688-1.54 1.118l-2.8-2.034a1 1 0 00-1.175 0l-2.8 2.034c-.784.57-1.838-.197-1.539-1.118l1.07-3.292a1 1 0 00-.364-1.118L2.98 8.72c-.783-.57-.38-1.81.588-1.81h3.461a1 1 0 00.951-.69l1.07-3.292z"></path></svg>
        {distinction_title if distinction_title else "Conferred with High Distinction"} • Top Tier Performance ({score:.1f}%)
    </div>
    ''' if has_distinction else ""

    safe_candidate_filename = candidate_name.replace(" ", "_").replace("'", "")
    certificate_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>VivoIQ Credential — {candidate_name}</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <link href="https://fonts.googleapis.com/css2?family=Cinzel:wght@600;700;900&family=Playfair+Display:ital,wght@0,600;0,700;0,800;1,400&family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap" rel="stylesheet">
    <style>
        @page {{
            size: A4 landscape;
            margin: 0;
        }}
        @media print {{
            body {{
                background: white !important;
                padding: 0 !important;
                margin: 0 !important;
                -webkit-print-color-adjust: exact !important;
                print-color-adjust: exact !important;
            }}
            .no-print {{
                display: none !important;
            }}
            .cert-viewport {{
                padding: 0 !important;
                margin: 0 !important;
                display: block !important;
                transform: none !important;
                height: 100vh !important;
                width: 100vw !important;
            }}
            #cert-scaler {{
                transform: none !important;
                margin: 0 !important;
            }}
            #certificate-canvas {{
                box-shadow: none !important;
                border-width: 6px !important;
                width: 100% !important;
                height: 100% !important;
                border-radius: 0 !important;
                margin: 0 !important;
            }}
        }}
        .font-cinzel {{ font-family: 'Cinzel', serif; }}
        .font-serif-display {{ font-family: 'Playfair Display', serif; }}
        .font-sans-modern {{ font-family: 'Plus Jakarta Sans', sans-serif; }}
    </style>
</head>
<body class="bg-slate-950 text-slate-100 font-sans-modern antialiased min-h-screen flex flex-col overflow-x-hidden selection:bg-blue-600 selection:text-white">

    <!-- Top Action Toolbar (Hidden on Print) -->
    <header class="no-print fixed top-0 left-0 right-0 h-14 bg-slate-900/95 backdrop-blur border-b border-slate-800 z-50 px-4 sm:px-6 flex items-center justify-between shadow-lg">
        <div class="flex items-center gap-3">
            <a href="/assessment/results?resume_id={resume_id}" class="inline-flex items-center gap-2 px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-semibold transition-colors border border-slate-700 shadow-sm cursor-pointer">
                <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10 19l-7-7m0 0l7-7m-7 7h18"></path></svg>
                <span>Dashboard</span>
            </a>
            <div class="h-4 w-[1px] bg-slate-800 hidden sm:block"></div>
            <div class="hidden sm:flex items-center gap-2 text-xs">
                <span class="w-2 h-2 rounded-full bg-emerald-400 animate-pulse"></span>
                <span class="font-mono text-slate-400 font-medium">{cred_id}</span>
            </div>
        </div>

        <div class="flex items-center gap-2 sm:gap-3">
            <!-- Toggle Fit / Actual -->
            <button onclick="toggleFit()" id="fit-btn" class="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs font-medium border border-slate-700 transition-colors cursor-pointer">
                <svg class="w-3.5 h-3.5 text-slate-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 8V4m0 0h4M4 4l5 5m11-1V4m0 0h-4m4 0l-5 5M4 16v4m0 0h4m-4 0l5-5m11 5l-5-5m5 5v-4m0 4h-4"></path></svg>
                <span id="fit-btn-label">100% Size</span>
            </button>

            <!-- Download Official PDF (Direct Vector Download from Server) -->
            <a href="/assessment/certificate/pdf?resume_id={resume_id}" download="VivoIQ_Certificate_{safe_candidate_filename}_{cred_id}.pdf" class="inline-flex items-center gap-2 px-4 py-1.5 rounded-lg bg-blue-600 hover:bg-blue-500 text-white text-xs font-bold shadow-md shadow-blue-500/20 transition-all cursor-pointer">
                <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"></path></svg>
                <span>Download PDF (Official A4)</span>
            </a>

            <!-- Print -->
            <button onclick="window.print()" class="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs font-medium border border-slate-700 transition-colors cursor-pointer">
                <svg class="w-3.5 h-3.5 text-slate-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M17 17h2a2 2 0 002-2v-4a2 2 0 00-2-2H5a2 2 0 00-2 2v4a2 2 0 002 2h2m2 4h6a2 2 0 002-2v-4a2 2 0 00-2-2H9a2 2 0 00-2 2v4a2 2 0 002 2zm8-12V5a2 2 0 00-2-2H9a2 2 0 00-2 2v4h10z"></path></svg>
                <span class="hidden sm:inline">Print</span>
            </button>
        </div>
    </header>

    <!-- Certificate Viewport Area -->
    <main class="cert-viewport flex-grow pt-20 pb-10 px-4 flex items-center justify-center overflow-auto">
        <div id="cert-scaler" class="transition-transform duration-200 ease-out origin-top sm:origin-center">
            
            <!-- MASTER CERTIFICATE CANVAS (1060px x 748px standard A4 Landscape) -->
            <div id="certificate-canvas" class="w-[1060px] h-[748px] min-w-[1060px] min-h-[748px] max-h-[748px] bg-white text-slate-900 border-[10px] border-double border-slate-900 rounded-[28px] p-9 shadow-2xl relative overflow-hidden flex flex-col justify-between select-none">
                
                <!-- Ornate Gold Corner Ornaments -->
                <div class="absolute top-3 left-3 w-12 h-12 border-t-[3px] border-l-[3px] border-amber-500/80 pointer-events-none"></div>
                <div class="absolute top-3 right-3 w-12 h-12 border-t-[3px] border-r-[3px] border-amber-500/80 pointer-events-none"></div>
                <div class="absolute bottom-3 left-3 w-12 h-12 border-b-[3px] border-l-[3px] border-amber-500/80 pointer-events-none"></div>
                <div class="absolute bottom-3 right-3 w-12 h-12 border-b-[3px] border-r-[3px] border-amber-500/80 pointer-events-none"></div>

                <!-- Inner Gold Line Border -->
                <div class="border border-amber-400/50 rounded-[18px] p-7 h-full flex flex-col justify-between relative bg-gradient-to-b from-amber-50/20 via-white to-slate-50/20">
                    
                    <!-- Top Branding & Title -->
                    <div class="text-center">
                        <div class="flex items-center justify-center gap-2 mb-1">
                            <span class="font-cinzel text-3xl font-black tracking-[0.25em] text-slate-950">V I V O <span class="text-blue-600">I Q</span></span>
                        </div>
                        <p class="text-[9px] uppercase font-bold tracking-[0.35em] text-slate-400 mb-2">Global Procurement Capability Verification Registry</p>
                        
                        <div class="inline-flex items-center gap-2 px-3 py-0.5 rounded-full bg-blue-50 border border-blue-200/80 text-blue-700 text-[9.5px] font-extrabold uppercase tracking-widest mb-1.5">
                            Official Evaluation Credential • Section 11 Verified
                        </div>
                        <h2 class="font-cinzel text-2xl font-bold tracking-tight text-slate-900">{cert_title}</h2>
                        {distinction_ribbon_html}
                    </div>

                    <!-- Candidate Conferred Centerpiece -->
                    <div class="text-center my-1.5">
                        <p class="text-[12px] text-slate-500 font-medium italic mb-1">This certifies that</p>
                        <h1 class="font-serif-display text-4xl font-extrabold text-slate-950 tracking-tight capitalize underline decoration-amber-400/80 decoration-2 underline-offset-8 mb-2.5">
                            {candidate_name}
                        </h1>
                        <p class="text-[12px] text-slate-600 max-w-xl mx-auto leading-relaxed">
                            has demonstrated verified professional capability through the VivoIQ AI-Enabled Adaptive Assessment.
                        </p>
                        <div class="inline-flex items-center gap-2 text-xs font-bold text-blue-900 uppercase tracking-wider mt-1.5">
                            <span>Verified Competency Tier: {verified_level_str}</span>
                            <span>•</span>
                            <span class="text-emerald-700">Evaluation Score: {score:.1f}%</span>
                        </div>
                    </div>

                    <!-- Mid Section: Narrative & Competency Domains -->
                    <div class="grid grid-cols-12 gap-5 items-stretch my-1.5">
                        <!-- AI-9 Narrative Quote -->
                        <div class="col-span-7 bg-slate-50/90 border border-slate-200/80 rounded-xl p-4 flex flex-col justify-center text-left shadow-sm">
                            <div class="flex items-center gap-1.5 text-blue-600 text-[10px] font-extrabold uppercase tracking-wider mb-1.5">
                                <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z"></path></svg>
                                <span>Verified Capability Narrative</span>
                            </div>
                            <p class="text-[11.5px] text-slate-700 leading-relaxed italic font-normal line-clamp-4">
                                "{narrative_summary}"
                            </p>
                        </div>

                        <!-- Domains & Scope -->
                        <div class="col-span-5 bg-slate-50/90 border border-slate-200/80 rounded-xl p-4 flex flex-col justify-between text-left shadow-sm">
                            <div>
                                <span class="text-[9px] font-bold text-slate-400 uppercase tracking-wider block mb-1.5">Primary Verified Competency Domains</span>
                                <div class="flex flex-wrap gap-1.5">
                                    {domains_badges_html}
                                </div>
                            </div>
                            {f'''<div class="mt-2 pt-2 border-t border-slate-200/60">
                                <span class="text-[9px] font-bold text-slate-400 uppercase tracking-wider block">Operational Scope:</span>
                                <p class="text-[10px] text-slate-600 leading-snug line-clamp-2">{scope_of_practice}</p>
                            </div>''' if scope_of_practice else ''}
                        </div>
                    </div>

                    <!-- Bottom Signatures & Seal (Section 11) -->
                    <div class="pt-3 mt-1 border-t border-slate-200/90 grid grid-cols-12 items-center text-left">
                        <!-- Left: QR Code + Credential Metadata -->
                        <div class="col-span-5 flex items-center gap-3">
                            <img src="{qr_img_src}" alt="QR Verification" class="w-14 h-14 border border-slate-200 rounded-lg p-0.5 bg-white shadow-sm flex-shrink-0" />
                            <div class="space-y-0.5">
                                <span class="text-[9px] font-bold text-slate-400 uppercase tracking-wider block">Credential ID: <span class="font-mono text-slate-900 font-bold">{cred_id}</span></span>
                                <span class="text-[9.5px] text-slate-600 block">Assessment Date: {issued_date}</span>
                                <span class="text-[9px] text-amber-800 font-medium block">Validity: Annual Reassessment Recommended</span>
                                <span class="text-[8.5px] text-blue-600 font-mono block truncate">{qr_url}</span>
                            </div>
                        </div>

                        <!-- Center: 3D Gold Seal -->
                        <div class="col-span-3 flex flex-col items-center justify-center">
                            <div class="relative w-15 h-15 rounded-full bg-gradient-to-br from-amber-300 via-yellow-400 to-amber-600 p-[3px] shadow-lg shadow-amber-300/40 flex items-center justify-center">
                                <div class="w-full h-full rounded-full border-2 border-dashed border-amber-900/30 flex flex-col items-center justify-center text-amber-950 font-black text-[7.5px] uppercase tracking-tighter text-center leading-tight bg-gradient-to-tr from-amber-200 to-yellow-100 p-2">
                                    <svg class="w-4 h-4 text-amber-900 mb-0.5" fill="currentColor" viewBox="0 0 20 20"><path fill-rule="evenodd" d="M6.267 3.455a3.066 3.066 0 001.745-.723 3.066 3.066 0 013.976 0 3.066 3.066 0 001.745.723 3.066 3.066 0 012.812 2.812c.051.643.304 1.254.723 1.745a3.066 3.066 0 010 3.976 3.066 3.066 0 00-.723 1.745 3.066 3.066 0 01-2.812 2.812 3.066 3.066 0 00-1.745.723 3.066 3.066 0 01-3.976 0 3.066 3.066 0 00-1.745-.723 3.066 3.066 0 01-2.812-2.812 3.066 3.066 0 00-.723-1.745 3.066 3.066 0 010-3.976 3.066 3.066 0 00.723-1.745 3.066 3.066 0 012.812-2.812zm7.44 5.252a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clip-rule="evenodd"></path></svg>
                                    <span>VERIFIED</span>
                                    <span>REGISTRY SEAL</span>
                                </div>
                            </div>
                        </div>

                        <!-- Right: Board of Assessors -->
                        <div class="col-span-4 text-right space-y-0.5">
                            <div class="font-serif-display italic text-base text-slate-900 font-bold border-b border-slate-300 pb-0.5 inline-block">
                                VivoIQ Board of Assessors
                            </div>
                            <span class="text-[9px] font-bold text-slate-400 uppercase tracking-wider block">Capability Verification Standard 1.0</span>
                            <span class="text-[9px] text-emerald-700 font-semibold block">AI-Evaluated & Cryptographically Registered</span>
                        </div>
                    </div>

                    <!-- Bottom Disclaimer Footnote (Section 11 Notice) -->
                    <p class="text-[8px] text-slate-400 text-center tracking-tight mt-1">
                        Section 11 Notice: This credential certifies verified capability demonstrated under the VivoIQ AI-Enabled Assessment Framework 1.0. This represents an AI-enabled self-evaluation and does not imply a proctored professional license.
                    </p>
                </div>
            </div>
            
        </div>
    </main>

    <!-- Interactive Scripts: Auto-Fit -->
    <script>
        let isFit = true;

        function autoScale() {{
            const scaler = document.getElementById('cert-scaler');
            if (!scaler) return;
            
            if (!isFit) {{
                scaler.style.transform = 'scale(1)';
                scaler.parentElement.style.height = 'auto';
                document.getElementById('fit-btn-label').innerText = 'Fit to Screen';
                return;
            }}
            
            const availW = window.innerWidth - 32;
            const availH = window.innerHeight - 90;
            const scaleW = availW / 1060;
            const scaleH = availH / 748;
            const scale = Math.min(scaleW, scaleH, 1.0);
            
            scaler.style.transform = `scale(${{scale}})`;
            scaler.style.transformOrigin = 'center top';
            scaler.parentElement.style.height = `${{Math.round(748 * scale + 40)}}px`;
            document.getElementById('fit-btn-label').innerText = '100% Size';
        }}

        function toggleFit() {{
            isFit = !isFit;
            autoScale();
        }}

        window.addEventListener('resize', autoScale);
        window.addEventListener('DOMContentLoaded', autoScale);
        setTimeout(autoScale, 150);
    </script>
</body>
</html>"""
    return HTMLResponse(content=certificate_html)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8002, reload=True)

