from fastapi import FastAPI, Request, UploadFile, File, Form, Depends
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select
from sqlalchemy import text
import sys
import os
import io
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
                <span class="text-[11px] font-medium text-gray-400 mt-2 absolute top-6 whitespace-nowrap">Test</span>
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
                        <span class="text-[11px] font-semibold text-vivo-navy mt-2 absolute top-6 whitespace-nowrap">Test</span>
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
                <div class="bg-slate-50 border-b border-gray-100 px-8 py-6 text-center relative overflow-hidden">
                    <div class="w-14 h-14 bg-white rounded-full flex items-center justify-center mx-auto mb-4 shadow-sm border border-gray-100 relative z-10">
                        <svg class="w-6 h-6 text-vivo-brand" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z"></path>
                        </svg>
                    </div>
                    <h2 class="text-[20px] font-bold text-vivo-navy tracking-tight relative z-10">Assessment Readiness Gate</h2>
                    <p class="text-[13px] text-gray-500 mt-1 relative z-10">Your resume analysis is complete. A unique test has been configured.</p>
                </div>
                
                <!-- Body -->
                <div class="p-3">
                    <div class="space-y-6">
                        <div class="flex items-start gap-4">
                            <div class="w-10 h-10 rounded-full bg-blue-50 flex items-center justify-center flex-shrink-0 mt-0.5">
                                <svg class="w-5 h-5 text-vivo-brand" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z"></path></svg>
                            </div>
                            <div>
                                <h4 class="text-[14px] font-bold text-vivo-navy">Time Commitment</h4>
                                <p class="text-[13px] text-gray-600 mt-1 leading-relaxed">This assessment contains 20 personalized questions and requires approximately <strong>20–30 uninterrupted minutes</strong>. A strict 30-minute timer will begin once the assessment is generated.</p>
                            </div>
                        </div>
                        
                        <div class="flex items-start gap-4">
                            <div class="w-10 h-10 rounded-full bg-purple-50 flex items-center justify-center flex-shrink-0 mt-0.5">
                                <svg class="w-5 h-5 text-purple-600" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z"></path></svg>
                            </div>
                            <div>
                                <h4 class="text-[14px] font-bold text-vivo-navy">Assessment Integrity</h4>
                                <p class="text-[13px] text-gray-600 mt-1 leading-relaxed">Do not close your browser or navigate away. At 30 minutes, unanswered questions will be automatically treated as incomplete and the attempt will be securely closed.</p>
                            </div>
                        </div>
                    </div>
                    
                    <div class="mt-10 pt-6 border-t border-gray-100 flex flex-col items-center">
                        <div id="test-gen-container" class="w-full">
                            <button hx-get="/assessment/generate-test?resume_id={resume_id}" hx-target="#main-content" onclick="document.getElementById('test-gen-container').classList.add('hidden'); document.getElementById('test-gen-loading').classList.remove('hidden');" class="w-full h-12 bg-vivo-brand hover:bg-blue-700 text-white text-[14px] font-bold rounded-[8px] shadow-md hover:shadow-lg transition-all flex items-center justify-center gap-2">
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
                                            
                                            // Simulate progress up to 99% over 35 seconds
                                            let progress = 0;
                                            const totalDuration = 35000;
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
        
        # SAFETY CHECK
        check_result = await session.execute(text("CALL CheckAIAssessment(:r_id)"), {"r_id": resume_id})
        check_row = check_result.mappings().first()
        if check_row and check_row["raw_json"]:
            from fastapi.responses import Response
            res = Response()
            res.headers["HX-Redirect"] = f"/assessment/test-questions?resume_id={resume_id}"
            return res
        
        import json
        from ai_agents import run_question_generation_agent, run_assessment_integrity_agent
        
        # Fetch Profile & Blueprint
        prof_res = await session.execute(text("CALL GetCandidateProfile(:r_id)"), {"r_id": resume_id})
        prof_row = prof_res.mappings().first()
        profile_json = json.loads(prof_row["profile_json"]) if prof_row and prof_row["profile_json"] else {}
        
        bp_res = await session.execute(text("CALL GetAssessmentBlueprint(:r_id)"), {"r_id": resume_id})
        bp_row = bp_res.mappings().first()
        blueprint_json = json.loads(bp_row["blueprint_json"]) if bp_row and bp_row["blueprint_json"] else {}
        
        # Run AI-4 (Generator)
        ai4_json = run_question_generation_agent(blueprint_json, profile_json)
        
        # Run AI-5 (Integrity Reviewer)
        ai5_json = run_assessment_integrity_agent(ai4_json, blueprint_json)
        
        # Map AI-5's clean 20 questions into the new 4-dimension scoring model
        ui_json = {
            "sections": [
                {
                    "section_name": "Knowledge Accuracy",
                    "weightage": 35,
                    "total_score": 25,
                    "questions": []
                },
                {
                    "section_name": "Practical Application",
                    "weightage": 30,
                    "total_score": 25,
                    "questions": []
                },
                {
                    "section_name": "Commercial & Analytical Reasoning",
                    "weightage": 20,
                    "total_score": 25,
                    "questions": []
                },
                {
                    "section_name": "Judgment & Risk Awareness",
                    "weightage": 15,
                    "total_score": 25,
                    "questions": []
                }
            ]
        }
        
        final_questions = ai5_json.get("final_questions", [])
        
        if len(final_questions) == 0:
            return HTMLResponse(f"""
            <div class="w-[520px] mx-auto bg-white rounded-[12px] shadow-sm border border-red-200 p-8 text-center mt-12">
                <div class="w-12 h-12 rounded-full bg-red-100 flex items-center justify-center mx-auto mb-4 text-red-500">
                    <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"></path></svg>
                </div>
                <h2 class="text-xl font-bold text-red-600 mb-2">Generation Interrupted</h2>
                <p class="text-[13px] text-gray-600 mb-6 leading-relaxed">Our AI engine was unable to generate the assessment at this time. This occasionally happens due to rate limits or strict safety filters rejecting the generated text.</p>
                <div hx-get="/assessment/build-profile?resume_id={resume_id}" hx-target="#main-content" class="h-10 px-6 bg-red-50 text-red-700 font-semibold rounded-[8px] cursor-pointer inline-flex items-center justify-center hover:bg-red-100 transition-colors">
                    Try Again
                </div>
            </div>
            """, status_code=200)
            
        for i, q in enumerate(final_questions):
            q_ui = {
                "question": q.get("question", "Fallback question text"),
                "question_type": q.get("question_type", "mcq"),
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
        
    # 5. Deterministic Score Calculation
    final_score = 0.0
    breakdown = []
    
    # Reset global_idx for recalculation
    g_idx = 0
    for sec in sections:
        sec_weight = float(sec.get("weightage", 25))
        sec_total = float(sec.get("total_score", 25))
        sec_score = 0.0
        
        for q in sec.get("questions", []):
            r = raw_responses.get(g_idx)
            if r:
                sec_score += float(r["points_awarded"])
                breakdown.append({
                    "question_idx": g_idx,
                    "question": q.get("question"),
                    "user_answer": r.get("user_answer"),
                    "correct_answer": q.get("answer"),
                    "is_correct": r.get("is_correct"),
                    "points_awarded": float(r["points_awarded"]),
                    "ai_reasoning": r.get("ai_reasoning", "")
                })
            else:
                breakdown.append({
                    "question_idx": g_idx,
                    "question": q.get("question"),
                    "user_answer": None,
                    "correct_answer": q.get("answer"),
                    "is_correct": False,
                    "points_awarded": 0.0,
                    "ai_reasoning": ""
                })
            g_idx += 1
            
        weighted_sec = (sec_score / max(sec_total, 1.0)) * sec_weight
        final_score += weighted_sec
        
    # Save Final Result
    await session.execute(
        text("CALL SaveAssessmentResult(:u, :r, :tot, :bkd)"),
        {"u": user_id, "r": resume_id, "tot": final_score, "bkd": json.dumps(breakdown)}
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
    
    result = await session.execute(text("CALL GetLatestAssessmentResult(:r_id)"), {"r_id": resume_id})
    score_row = result.mappings().first()
    
    if not score_row: return HTMLResponse("Results not found", status_code=404)
    
    score = score_row["total_score"]
    
    # Evaluate Pass/Fail Rule-governed logic
    passed = True
    status_msg = "Passed"
    if score < 70.0:
        passed = False
        status_msg = "Development Required (Score < 70%)"
        
    # Later we will add the "No critical competency below 50%" rule, for now basic threshold
    
    html_content = f"""
    <div class="absolute top-6 right-8 z-50 animate-fade-in">
        <a href="/users/logout" class="text-[13px] font-semibold text-gray-400 hover:text-vivo-brand transition-colors flex items-center gap-1.5 cursor-pointer">
            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1"></path></svg> 
            Log out
        </a>
    </div>
    <div class="w-full max-w-4xl mx-auto py-12 animate-fade-in-up">
        <div class="bg-white rounded-[16px] shadow-sm border border-gray-100 p-10 text-center">
            <div class="w-24 h-24 mx-auto rounded-full flex items-center justify-center mb-6 {'bg-emerald-50 text-emerald-500' if passed else 'bg-amber-50 text-amber-500'}">
                {f'<svg class="w-12 h-12" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="3" d="M5 13l4 4L19 7"></path></svg>' if passed else f'<svg class="w-12 h-12" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"></path></svg>'}
            </div>
            
            <h1 class="text-3xl font-bold text-vivo-navy tracking-tight mb-2">{"Capability Verified" if passed else "Capability Gap Identified"}</h1>
            <p class="text-gray-500 mb-8">{status_msg}</p>
            
            <div class="inline-flex flex-col items-center justify-center border-[4px] {'border-emerald-500' if passed else 'border-amber-400'} rounded-full w-40 h-40 mb-8 shadow-sm">
                <span class="text-4xl font-bold text-vivo-navy">{score:.1f}%</span>
                <span class="text-[12px] font-semibold text-gray-400 uppercase tracking-wider mt-1">Final Score</span>
            </div>
            
            <div class="text-left mt-8 p-6 bg-gray-50 rounded-[12px] border border-gray-100">
                <h3 class="text-lg font-bold text-vivo-navy mb-4">Assessment Breakdown (AI Evaluated)</h3>
                <p class="text-sm text-gray-600 mb-4">Sprint 4 Deterministic Engine processed the score. Full Domain-by-Domain capability radar coming in Sprint 5!</p>
            </div>
        </div>
    </div>
    """
    return HTMLResponse(content=html_content)

    # We will build out a more beautiful results page next, this is just to show it worked    # We will build out a more beautiful results page next, this is just to show it worked
    html_content = f"""
    <div class="absolute top-6 right-8 z-50 animate-fade-in">
        <a href="/users/logout" class="text-[13px] font-semibold text-gray-400 hover:text-vivo-brand transition-colors flex items-center gap-1.5 cursor-pointer">
            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1"></path></svg> 
            Log out
        </a>
    </div>
    
    <div class="w-full max-w-3xl mx-auto pb-8 animate-fade-in-up">
        <div class="flex items-center justify-center mb-10 h-16 w-full px-12 max-w-lg mx-auto">
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
                <span class="text-[11px] font-medium text-gray-500 mt-2 absolute top-6 whitespace-nowrap">Test</span>
            </div>
            <div class="flex-grow h-[2px] bg-blue-500 mx-2"></div>
            <div class="flex flex-col items-center relative z-10 w-8">
                <div class="w-6 h-6 rounded-full bg-blue-500 text-white flex items-center justify-center shadow-sm"><div class="w-2 h-2 rounded-full bg-white"></div></div>
                <span class="text-[11px] font-semibold text-vivo-navy mt-2 absolute top-6 whitespace-nowrap">Results</span>
            </div>
        </div>

        <div class="bg-white rounded-[12px] shadow-sm border border-gray-200 p-12 text-center">
            <h2 class="text-3xl font-bold text-vivo-navy tracking-tight mb-2">Assessment Complete!</h2>
            <p class="text-[14px] text-gray-500 mb-8">You have successfully completed the AI procurement evaluation.</p>
            
            <div class="w-32 h-32 mx-auto bg-blue-50 rounded-full flex flex-col items-center justify-center border-[4px] border-blue-100 mb-6">
                <span class="text-3xl font-black text-vivo-brand">{score}%</span>
            </div>
            
            <p class="text-[13px] font-medium text-gray-600">Your results have been saved to your profile.</p>
        </div>
    </div>
    """
    return HTMLResponse(content=html_content)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8002, reload=True)
