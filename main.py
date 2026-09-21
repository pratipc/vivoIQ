from fastapi import FastAPI, Request, Form, Depends
from fastapi.responses import HTMLResponse, Response, RedirectResponse
from fastapi.templating import Jinja2Templates
from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
import bcrypt

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from database import init_db, get_session
from models import User

load_dotenv(dotenv_path="../.env")

app = FastAPI(title="VivoIQ User Service")
templates = Jinja2Templates(directory="templates")

@app.on_event("startup")
async def on_startup():
    await init_db()

@app.post("/users/register", response_class=HTMLResponse)
async def register_user(
    name: str = Form(...), 
    email: str = Form(...), 
    password: str = Form(...),
    session: AsyncSession = Depends(get_session)
):
    # Check if user exists using Stored Procedure
    result = await session.execute(text("CALL GetUserByEmail(:email)"), {"email": email})
    existing_user = result.mappings().first()
    
    if existing_user:
        return HTMLResponse(
            '<div class="alert alert-error">Email already registered.</div>'
            '<button class="btn btn-primary mt-4 w-full" hx-get="/users/login-form" hx-target="#main-content">Go to Login</button>'
        )

    # Hash password and create user using Stored Procedure
    salt = bcrypt.gensalt()
    hashed_password = bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')
    
    create_result = await session.execute(
        text("CALL CreateUser(:name, :email, :password_hash)"),
        {"name": name, "email": email, "password_hash": hashed_password}
    )
    await session.commit()
    
    # Return success HTML that triggers a swap to the assessment service onboarding
    html_response = HTMLResponse(f"""
        <div class="w-full min-h-[60vh] flex flex-col items-center justify-center animate-fade-in-up">
            <div class="w-16 h-16 bg-blue-50/50 rounded-[16px] flex items-center justify-center mb-6 shadow-sm border border-blue-100">
                <svg class="w-8 h-8 text-vivo-brand" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"></path>
                </svg>
            </div>
            <h2 class="text-[22px] font-bold text-vivo-navy tracking-tight mb-3">Welcome to VivoIQ, {name.split()[0]}</h2>
            <div class="text-[13px] text-gray-500 font-medium flex items-center gap-2">
                <span class="loading loading-spinner loading-xs text-vivo-brand opacity-70"></span>
                <span>Preparing your secure workspace...</span>
            </div>
            
            <!-- Deliberate 600ms delay so the user sees the welcome state smoothly before transition -->
            <div hx-get="/assessment/onboarding" hx-trigger="load delay:600ms" hx-target="#main-content" hx-push-url="true" class="hidden"></div>
        </div>
    """)
    
    # Extract the new ID and set a session cookie
    new_user_row = create_result.mappings().first()
    if new_user_row and "new_id" in new_user_row:
        html_response.set_cookie(key="user_id", value=str(new_user_row["new_id"]), httponly=True)
        
    return html_response

@app.post("/users/login", response_class=HTMLResponse)
async def login_user(
    response: Response,
    email: str = Form(...), 
    password: str = Form(...),
    session: AsyncSession = Depends(get_session)
):
    result = await session.execute(text("CALL GetUserByEmail(:email)"), {"email": email})
    user = result.mappings().first()
    
    if not user or not bcrypt.checkpw(password.encode('utf-8'), user['password_hash'].encode('utf-8')):
        return await login_form(request=None, error_message="Invalid email or password. Please check your credentials and try again.")
        
    html_response = HTMLResponse(f"""
        <div class="w-full min-h-[60vh] flex flex-col items-center justify-center animate-fade-in-up">
            <div class="w-16 h-16 bg-blue-50/50 rounded-[16px] flex items-center justify-center mb-6 shadow-sm border border-blue-100">
                <svg class="w-8 h-8 text-vivo-brand" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"></path>
                </svg>
            </div>
            <h2 class="text-[22px] font-bold text-vivo-navy tracking-tight mb-3">Authenticating</h2>
            <div class="text-[13px] text-gray-500 font-medium flex items-center gap-2">
                <span class="loading loading-spinner loading-xs text-vivo-brand opacity-70"></span>
                <span>Securely accessing your workspace...</span>
            </div>
            
            <div hx-get="/assessment/onboarding" hx-trigger="load delay:400ms" hx-target="#main-content" hx-push-url="true" class="hidden"></div>
        </div>
    """)
    html_response.set_cookie(key="user_id", value=str(user["id"]), httponly=True)
    return html_response

@app.get("/users/signup-form", response_class=HTMLResponse)
async def signup_form(request: Request):
    html_content = """
    <div class="w-full max-w-4xl bg-white rounded-[12px] shadow-xl overflow-hidden flex flex-col md:flex-row animate-fade-in-up border border-gray-100">
        <!-- Left Side: Illustration & Tagline -->
        <div class="w-full md:w-5/12 bg-vivo-navy p-8 flex flex-col justify-between relative overflow-hidden">
            <!-- Decorative abstract AI background -->
            <div class="absolute top-0 right-0 -mr-16 -mt-16 w-64 h-64 rounded-full bg-vivo-brand opacity-20 blur-3xl"></div>
            <div class="absolute bottom-0 left-0 -ml-16 -mb-16 w-64 h-64 rounded-full bg-indigo-500 opacity-20 blur-3xl"></div>
            
            <div class="relative z-10">
                <div class="mt-4">
                    <h1 class="text-2xl lg:text-3xl font-bold text-white leading-tight mb-2 tracking-tight">Manage your data with AI</h1>
                    <p class="text-blue-100 text-[13px] leading-relaxed">Automate vendor assessments and optimize sourcing decisions instantly.</p>
                </div>
            </div>
            
            <div class="relative z-10 mt-6 mb-2">
                <!-- Illustration -->
                <div class="w-full h-32 bg-white/10 backdrop-blur-sm rounded-xl border border-white/20 shadow-inner flex flex-col items-center justify-center p-3">
                    <svg class="w-10 h-10 text-white/70 mb-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M19.428 15.428a2 2 0 00-1.022-.547l-2.387-.477a6 6 0 00-3.86.517l-.318.158a6 6 0 01-3.86.517L6.05 15.21a2 2 0 00-1.806.547M8 4h8l-1 1v5.172a2 2 0 00.586 1.414l5 5c1.26 1.26.367 3.414-1.415 3.414H4.828c-1.782 0-2.674-2.154-1.414-3.414l5-5A2 2 0 009 10.172V5L8 4z"></path>
                    </svg>
                    <div class="text-2xl font-extrabold tracking-tight text-white/90">vivo<span class="text-vivo-accent">IQ</span></div>
                </div>
            </div>
        </div>
        
        <!-- Right Side: Form -->
        <div class="w-full md:w-7/12 p-8 lg:p-10 bg-white flex flex-col justify-center">
            <div class="mb-6">
                <h2 class="text-2xl font-bold text-vivo-navy tracking-tight mb-1">Create your account</h2>
                <p class="text-[13px] text-gray-500">Enter your details to get started with VivoIQ.</p>
            </div>
            <form hx-post="/users/register" hx-target="#main-content" hx-indicator=".submit-spinner" class="space-y-4">
                <div class="space-y-1">
                    <label class="text-[12px] font-semibold text-vivo-navy uppercase tracking-wider">Name</label>
                    <input type="text" name="name" placeholder="John Doe" class="w-full px-4 py-2.5 rounded-[8px] border border-gray-300 bg-white text-[14px] text-gray-900 placeholder-gray-400 focus:border-vivo-brand focus:ring-1 focus:ring-vivo-brand outline-none transition-all" required />
                </div>
                <div class="space-y-1">
                    <label class="text-[12px] font-semibold text-vivo-navy uppercase tracking-wider">Email</label>
                    <input type="email" name="email" placeholder="john@example.com" class="w-full px-4 py-2.5 rounded-[8px] border border-gray-300 bg-white text-[14px] text-gray-900 placeholder-gray-400 focus:border-vivo-brand focus:ring-1 focus:ring-vivo-brand outline-none transition-all" required />
                </div>
                <div class="space-y-1">
                    <label class="text-[12px] font-semibold text-vivo-navy uppercase tracking-wider">Password</label>
                    <input type="password" name="password" placeholder="••••••••" class="w-full px-4 py-2.5 rounded-[8px] border border-gray-300 bg-white text-[14px] text-gray-900 placeholder-gray-400 focus:border-vivo-brand focus:ring-1 focus:ring-vivo-brand outline-none transition-all" required />
                </div>
                <button type="submit" class="w-full h-10 bg-vivo-brand hover:bg-blue-700 text-white text-[14px] font-medium rounded-[8px] shadow-sm hover:shadow transition-all flex items-center justify-center gap-2 mt-4">
                    <span>Continue</span>
                    <span class="loading loading-spinner loading-xs submit-spinner hidden"></span>
                </button>
                <div class="text-center mt-6 pt-6 border-t border-gray-100">
                    <span class="text-[13px] text-gray-500">Already have an account? </span>
                    <a class="text-[13px] font-medium text-vivo-brand hover:text-blue-700 cursor-pointer transition-colors" hx-get="/users/login-form" hx-target="#main-content">Log in</a>
                </div>
            </form>
        </div>
    </div>
    """
    return HTMLResponse(content=html_content)

@app.get("/users/login-form", response_class=HTMLResponse)
async def login_form(request: Request = None, error_message: str = None):
    error_html = ""
    if error_message:
        error_html = f"""
        <div class="mb-5 p-3.5 bg-red-50/50 border border-red-100 rounded-[8px] flex items-start gap-2.5 animate-fade-in">
            <svg class="w-4 h-4 text-red-500 mt-0.5 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"></path></svg>
            <p class="text-[13px] text-red-700 font-medium">{error_message}</p>
        </div>
        """
        
    html_content = f"""
    <div class="w-full max-w-4xl bg-white rounded-[12px] shadow-xl overflow-hidden flex flex-col md:flex-row animate-fade-in-up border border-gray-100">
        <!-- Left Side: Illustration & Tagline -->
        <div class="w-full md:w-5/12 bg-vivo-navy p-8 flex flex-col justify-between relative overflow-hidden">
            <!-- Decorative abstract AI background -->
            <div class="absolute top-0 right-0 -mr-16 -mt-16 w-64 h-64 rounded-full bg-vivo-brand opacity-20 blur-3xl"></div>
            <div class="absolute bottom-0 left-0 -ml-16 -mb-16 w-64 h-64 rounded-full bg-indigo-500 opacity-20 blur-3xl"></div>
            
            <div class="relative z-10">
                <div class="mt-4">
                    <h1 class="text-2xl lg:text-3xl font-bold text-white leading-tight mb-2 tracking-tight">Welcome Back</h1>
                    <p class="text-blue-100 text-[13px] leading-relaxed">Continue your AI-powered vendor assessment.</p>
                </div>
            </div>
            
            <div class="relative z-10 mt-6 mb-2">
                <!-- Illustration -->
                <div class="w-full h-32 bg-white/10 backdrop-blur-sm rounded-xl border border-white/20 shadow-inner flex flex-col items-center justify-center p-3">
                    <svg class="w-10 h-10 text-white/70 mb-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M11 16l-4-4m0 0l4-4m-4 4h14m-5 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h7a3 3 0 013 3v1"></path>
                    </svg>
                    <div class="text-2xl font-extrabold tracking-tight text-white/90">vivo<span class="text-vivo-accent">IQ</span></div>
                </div>
            </div>
        </div>
        
        <!-- Right Side: Form -->
        <div class="w-full md:w-7/12 p-8 lg:p-10 bg-white flex flex-col justify-center">
            <div class="mb-6">
                <h2 class="text-2xl font-bold text-vivo-navy tracking-tight mb-1">Log into your account</h2>
                <p class="text-[13px] text-gray-500">Enter your credentials to securely access your data.</p>
            </div>
            {error_html}
            <form hx-post="/users/login" hx-target="#main-content" hx-indicator=".submit-spinner" class="space-y-4">
                <div class="space-y-1">
                    <label class="text-[12px] font-semibold text-vivo-navy uppercase tracking-wider">Email</label>
                    <input type="email" name="email" placeholder="john@example.com" class="w-full px-4 py-2.5 rounded-[8px] border border-gray-300 bg-white text-[14px] text-gray-900 placeholder-gray-400 focus:border-vivo-brand focus:ring-1 focus:ring-vivo-brand outline-none transition-all" required />
                </div>
                <div class="space-y-1">
                    <label class="text-[12px] font-semibold text-vivo-navy uppercase tracking-wider">Password</label>
                    <input type="password" name="password" placeholder="••••••••" class="w-full px-4 py-2.5 rounded-[8px] border border-gray-300 bg-white text-[14px] text-gray-900 placeholder-gray-400 focus:border-vivo-brand focus:ring-1 focus:ring-vivo-brand outline-none transition-all" required />
                </div>
                <button type="submit" class="w-full h-10 bg-vivo-brand hover:bg-blue-700 text-white text-[14px] font-medium rounded-[8px] shadow-sm hover:shadow transition-all flex items-center justify-center gap-2 mt-4">
                    <span>Log In</span>
                    <span class="loading loading-spinner loading-xs submit-spinner hidden"></span>
                </button>
                <div class="text-center mt-6 pt-6 border-t border-gray-100">
                    <span class="text-[13px] text-gray-500">Don't have an account? </span>
                    <a class="text-[13px] font-medium text-vivo-brand hover:text-blue-700 cursor-pointer transition-colors" hx-get="/users/signup-form" hx-target="#main-content">Sign up</a>
                </div>
            </form>
        </div>
    </div>
    """
    return HTMLResponse(content=html_content)

@app.get("/users/logout")
async def logout():
    response = RedirectResponse(url="/", status_code=302)
    response.delete_cookie("user_id")
    return response


@app.get("/users/account", response_class=HTMLResponse)
async def account_page(request: Request, session: AsyncSession = Depends(get_session)):
    user_id_cookie = request.cookies.get("user_id")
    if not user_id_cookie:
        return RedirectResponse(url="/", status_code=302)
    
    user_id = int(user_id_cookie)
    
    # Fetch User
    u_res = await session.execute(
        text("SELECT name, email, created_at FROM user WHERE id = :u_id"),
        {"u_id": user_id}
    )
    user_row = u_res.mappings().first()
    
    if not user_row:
        return RedirectResponse(url="/", status_code=302)
        
    # Fetch Candidate Profile
    p_res = await session.execute(
        text("SELECT expected_level, profile_json FROM candidate_profiles WHERE user_id = :u_id ORDER BY created_at DESC LIMIT 1"),
        {"u_id": user_id}
    )
    prof_row = p_res.mappings().first()
    
    level_str = "Unassessed"
    role_str = "No resume uploaded"
    if prof_row:
        level_str = f"L{prof_row['expected_level']}" if prof_row['expected_level'] else "Unassessed"
        if prof_row['profile_json']:
            import json
            try:
                pj = json.loads(prof_row['profile_json'])
                role_str = pj.get("roles", ["Professional"])[0] if pj.get("roles") else "Professional"
            except:
                pass
                
    # Format date
    join_date = user_row['created_at'].strftime("%B %d, %Y") if user_row['created_at'] else "Recently"
    
    # HTML UI
    html = f'''
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Account - VivoIQ</title>
        <script src="https://cdn.tailwindcss.com"></script>
        <script>
            tailwind.config = {{
                theme: {{
                    extend: {{
                        colors: {{
                            'vivo-brand': '#3B82F6',
                            'vivo-navy': '#0F172A',
                            'vivo-bg': '#F8FAFC'
                        }},
                        animation: {{
                            'fade-in-up': 'fadeInUp 0.6s ease-out forwards',
                            'pulse': 'pulse 2s cubic-bezier(0.4, 0, 0.6, 1) infinite'
                        }},
                        keyframes: {{
                            fadeInUp: {{
                                '0%': {{ opacity: '0', transform: 'translateY(15px)' }},
                                '100%': {{ opacity: '1', transform: 'translateY(0)' }}
                            }}
                        }}
                    }}
                }}
            }}
        </script>
    </head>
    <body class="bg-vivo-bg min-h-screen text-slate-800 font-sans selection:bg-blue-100 selection:text-blue-900">
        <div class="w-full max-w-2xl mx-auto py-12 px-6 animate-fade-in-up mt-10">
            <!-- Header -->
            <div class="mb-8 flex items-center justify-between">
                <div>
                    <h1 class="text-3xl font-extrabold text-vivo-navy tracking-tight">Account Profile</h1>
                    <p class="text-[14px] text-gray-500 mt-1">Manage your personal information and capability level.</p>
                </div>
                <a href="/assessment/onboarding" class="px-5 py-2.5 bg-white border border-gray-200 text-gray-700 text-[13px] font-bold rounded-xl shadow-sm hover:bg-gray-50 transition-colors flex items-center gap-2 group">
                    <svg class="w-4 h-4 text-gray-400 group-hover:-translate-x-0.5 transition-transform" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10 19l-7-7m0 0l7-7m-7 7h18"></path></svg>
                    Back to Dashboard
                </a>
            </div>
            
            <!-- Main Card -->
            <div class="bg-white rounded-[24px] shadow-sm border border-gray-100 overflow-hidden">
                <!-- Top Color Bar -->
                <div class="h-28 bg-gradient-to-r from-vivo-brand to-indigo-600 relative overflow-hidden">
                    <div class="absolute inset-0 bg-white/10" style="background-image: radial-gradient(circle at 20% 150%, rgba(255,255,255,0.15) 0%, transparent 50%);"></div>
                </div>
                
                <div class="px-8 pb-8 relative">
                    <!-- Avatar -->
                    <div class="w-24 h-24 bg-white rounded-full p-1.5 absolute -top-12 shadow-sm border border-gray-100">
                        <div class="w-full h-full bg-blue-50/80 rounded-full flex items-center justify-center text-vivo-brand text-3xl font-extrabold ring-1 ring-blue-100/50">
                            {user_row['name'][0].upper()}
                        </div>
                    </div>
                    
                    <!-- Info Section -->
                    <div class="pt-16 flex justify-between items-start">
                        <div>
                            <h2 class="text-2xl font-extrabold text-gray-900 tracking-tight">{user_row['name']}</h2>
                            <p class="text-[14px] text-gray-500 font-medium mt-0.5">{role_str}</p>
                        </div>
                        <div class="px-4 py-2 bg-blue-50/50 border border-blue-100/50 rounded-xl flex flex-col items-center justify-center min-w-[100px]">
                            <span class="text-[10px] font-bold text-blue-500/80 uppercase tracking-widest block mb-0.5">Current Level</span>
                            <span class="text-lg font-black text-vivo-brand">{level_str}</span>
                        </div>
                    </div>
                    
                    <div class="mt-8 grid grid-cols-1 md:grid-cols-2 gap-4">
                        <div class="p-5 bg-slate-50/70 border border-slate-100 rounded-[16px]">
                            <div class="flex items-center gap-2 mb-1.5">
                                <svg class="w-4 h-4 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 8l7.89 5.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z"></path></svg>
                                <span class="text-[11px] font-bold text-gray-400 uppercase tracking-wider">Email Address</span>
                            </div>
                            <p class="text-[14px] font-bold text-gray-800">{user_row['email']}</p>
                        </div>
                        
                        <div class="p-5 bg-slate-50/70 border border-slate-100 rounded-[16px]">
                            <div class="flex items-center gap-2 mb-1.5">
                                <svg class="w-4 h-4 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z"></path></svg>
                                <span class="text-[11px] font-bold text-gray-400 uppercase tracking-wider">Member Since</span>
                            </div>
                            <p class="text-[14px] font-bold text-gray-800">{join_date}</p>
                        </div>
                    </div>
                    
                    <div class="mt-8 pt-6 border-t border-gray-100 flex justify-end">
                        <a href="/users/logout" class="px-6 py-2.5 bg-rose-50 hover:bg-rose-100 text-rose-600 font-bold text-[13px] rounded-xl transition-colors flex items-center gap-2">
                            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1"></path></svg>
                            Sign Out
                        </a>
                    </div>
                </div>
            </div>
        </div>
    </body>
    </html>
    '''
    return HTMLResponse(content=html)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8001, reload=True)

