def get_progress_tracker(active_stage, resume_id=0):
    stages = [
        {"name": "Account", "url": "/users/account"},
        {"name": "Resume", "url": "/assessment/onboarding"},
        {"name": "Capability Mapping", "url": f"/assessment/build-profile?resume_id={resume_id}" if resume_id else "javascript:void(0)"},
        {"name": "Assessment", "url": f"/assessment/readiness?resume_id={resume_id}" if resume_id else "javascript:void(0)"},
        {"name": "Results", "url": f"/assessment/results?resume_id={resume_id}" if resume_id else "javascript:void(0)"}
    ]
    
    html = '<div id="main-progress-tracker" class="flex items-center justify-center mb-8 h-16 w-full max-w-3xl mx-auto px-4 animate-fade-in">\n'
    
    active_idx = next((i for i, s in enumerate(stages) if s["name"] == active_stage), 0)
    
    # Determine max accessible index based on urls
    max_accessible_idx = active_idx
    if resume_id > 0:
        max_accessible_idx = 3 # Up to Assessment Gate
    
    for i, stage in enumerate(stages):
        is_active = i == active_idx
        is_completed = i < active_idx or (i <= max_accessible_idx and not is_active)
        
        url = stage["url"]
        name = stage["name"]
        
        # Link logic: if completed and has a url, make it clickable, else just a div
        tag = "a" if (is_completed or is_active) and url != "javascript:void(0)" else "div"
        
        # If it's active, we probably don't want it to act like a link to itself, but we can allow it
        href = f'href="{url}"' if tag == "a" else ""
        cursor = "cursor-pointer group hover:scale-110" if tag == "a" else ""
        
        if is_active:
            html += f'''
            <{tag} {href} class="flex flex-col items-center relative z-10 w-8 {cursor} transition-all">
                <div class="w-8 h-8 rounded-full bg-vivo-brand text-white flex items-center justify-center shadow-lg ring-4 ring-blue-100">
                    <div class="w-2.5 h-2.5 rounded-full bg-white animate-pulse"></div>
                </div>
                <span class="text-[11px] md:text-[12px] font-extrabold text-vivo-navy mt-2 absolute top-8 whitespace-nowrap">{name}</span>
            </{tag}>
            '''
        elif is_completed:
            html += f'''
            <{tag} {href} class="flex flex-col items-center relative z-10 w-8 {cursor} transition-all">
                <div class="w-8 h-8 rounded-full bg-emerald-500 text-white flex items-center justify-center shadow-md {'group-hover:shadow-lg' if tag=='a' else ''}">
                    <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M5 13l4 4L19 7"></path></svg>
                </div>
                <span class="text-[11px] md:text-[12px] font-bold text-emerald-600 mt-2 absolute top-8 whitespace-nowrap">{name}</span>
            </{tag}>
            '''
        else:
            html += f'''
            <div class="flex flex-col items-center relative z-10 w-8">
                <div class="w-8 h-8 rounded-full bg-white border-[3px] border-gray-200 text-gray-300 flex items-center justify-center">
                </div>
                <span class="text-[11px] md:text-[12px] font-bold text-gray-400 mt-2 absolute top-8 whitespace-nowrap">{name}</span>
            </div>
            '''
            
        if i < len(stages) - 1:
            # Line should be green if the NEXT stage is completed or active
            next_is_active_or_completed = (i + 1) <= active_idx or ((i + 1) <= max_accessible_idx)
            line_color = "bg-emerald-500" if next_is_active_or_completed else "bg-gray-200"
            html += f'<div class="flex-grow h-[3px] {line_color} mx-1 md:mx-2 rounded-full"></div>\n'
            
    html += '</div>'
    return html
