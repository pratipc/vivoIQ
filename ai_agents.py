import os
import json
import google.generativeai as genai
from dotenv import load_dotenv
import pdfplumber

load_dotenv(os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env"))
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

COMPETENCY_ONTOLOGY = [
    "Procurement Fundamentals",
    "Strategic Sourcing",
    "Category Management",
    "Supplier Management",
    "Commercial & Cost",
    "Contracts",
    "Procurement Analytics",
    "Digital Procurement",
    "Risk, ESG & Compliance",
    "Stakeholder & Leadership"
]

def extract_text_from_pdf(pdf_path: str) -> str:
    text = ""
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"
    except Exception as e:
        print(f"Error extracting PDF: {e}")
    return text

def run_resume_intelligence_agent(resume_text: str) -> dict:
    """
    AI-1: Resume Intelligence Agent
    Parses resume text into a structured capability profile.
    """
    model = genai.GenerativeModel("gemini-3.6-flash")
    
    prompt = f"""
    SYSTEM ROLE:
    You are the VivoIQ Procurement Resume Intelligence Agent. Your task is to convert a candidate resume into a structured, evidence-based procurement capability profile.
    
    RULES:
    1. Use only evidence present in the resume. Do not invent experience.
    2. Separate explicit evidence from reasonable inference.
    3. Identify total experience and procurement-relevant experience separately.
    4. Extract roles, seniority, industries, procurement categories, geographies, processes, systems, certifications, leadership and transformation exposure.
    5. Map evidence to the VivoIQ Procurement Competency Framework: {json.dumps(COMPETENCY_ONTOLOGY)}
    6. For each competency, return evidence, estimated proficiency (0-5), confidence (0-100), and areas that must be verified by assessment.
    7. Flag exaggerated, vague or unsupported claims for verification; do not accuse the candidate.
    8. Do not score the candidate as passed or failed.
    
    OUTPUT FORMAT:
    Return ONLY a valid JSON object without any markdown formatting. The JSON must exactly match this schema:
    {{
        "total_experience_years": number,
        "procurement_experience_years": number,
        "expected_vivoiq_level": number (1-5),
        "roles": ["string"],
        "seniority": "string",
        "industries": ["string"],
        "categories": ["string"],
        "geographies": ["string"],
        "systems": ["string"],
        "certifications": ["string"],
        "leadership_exposure": "string",
        "competency_mapping": [
            {{
                "domain": "string (must be from the framework)",
                "evidence": "string",
                "estimated_proficiency": number (0-5),
                "confidence": number (0-100),
                "verification_priorities": ["string"]
            }}
        ],
        "flags": ["string"]
    }}
    
    RESUME TEXT:
    {resume_text}
    """
    
    try:
        response = model.generate_content(prompt)
        json_str = response.text.strip()
        if json_str.startswith("```json"):
            json_str = json_str[7:]
        if json_str.endswith("```"):
            json_str = json_str[:-3]
        return json.loads(json_str)
    except Exception as e:
        print(f"Error parsing AI-1 JSON: {e}")
        return {}

def run_assessment_blueprint_agent(capability_profile: dict) -> dict:
    """
    AI-3: Assessment Blueprint Agent
    Builds a 20-slot question blueprint from the candidate's capability profile.
    """
    model = genai.GenerativeModel("gemini-3.6-flash")
    
    prompt = f"""
    SYSTEM ROLE:
    You are the VivoIQ Assessment Architect. Build a 20-question personalized assessment blueprint from the structured candidate capability profile.
    
    OBJECTIVE:
    Verify whether the candidate's demonstrated knowledge supports the experience and expertise indicated by the profile.
    
    RULES:
    1. Exactly 20 questions total.
    2. Allocate greater depth to claimed core expertise (e.g. 6-8 questions on their primary domains) while retaining coverage of essential procurement breadth.
    3. Calibrate difficulty to the expected VivoIQ level indicated in the profile.
    4. Include a mix of knowledge, application, commercial reasoning, scenario judgment and digital/risk/governance.
    5. Senior candidates must receive proportionately more ambiguous scenario and strategic judgment questions.
    6. Do NOT write the actual questions yet.
    7. For every question slot specify competency, sub_competency, difficulty (1-5), question_type, purpose, weight, and resume_claim_being_verified.
    8. Ensure the complete assessment can reasonably be completed within 30 minutes.
    
    OUTPUT FORMAT:
    Return ONLY a valid JSON object without any markdown formatting. The JSON must exactly match this schema:
    {{
        "domain_weight_summary": {{
            "domain_name": "number_of_questions"
        }},
        "blueprint_slots": [
            {{
                "slot_id": 1,
                "competency": "string (must be from the VivoIQ ontology)",
                "sub_competency": "string",
                "difficulty": 3,
                "question_type": "string (e.g. MCQ, Scenario, Calculation, Multi-Select)",
                "purpose": "string",
                "weight": 2.5,
                "resume_claim_being_verified": "string"
            }}
        ]
    }}
    
    CANDIDATE CAPABILITY PROFILE:
    {json.dumps(capability_profile, indent=2)}
    """
    
    try:
        response = model.generate_content(prompt)
        json_str = response.text.strip()
        if json_str.startswith("```json"):
            json_str = json_str[7:]
        if json_str.endswith("```"):
            json_str = json_str[:-3]
        return json.loads(json_str)
    except Exception as e:
        print(f"Error parsing AI-3 JSON: {e}")
        return {}

def run_question_generation_agent(blueprint: dict, capability_profile: dict) -> dict:
    """
    AI-4: Question Generation Agent
    Generates the actual 20 questions based on the blueprint and capability profile.
    """
    model = genai.GenerativeModel("gemini-3.6-flash")
    
    prompt = f"""
    SYSTEM ROLE:
    You are the VivoIQ Procurement Assessment Question Generator.
    
    RULES:
    1. Generate exactly one question for each of the 20 blueprint slots.
    2. Do not expose resume wording or employer-confidential information.
    3. Questions must be practical, unambiguous and appropriate to the assigned difficulty.
    4. Use realistic procurement situations.
    5. Do not require web research.
    6. Generate a mix of "mcq" and "short_response" question types. For each question provide: question text, question_type, options (empty array for short_response), correct/expected response, scoring rubric, maximum score, competency tags and difficulty.
    7. For scenario questions, allow more than one defensible approach where appropriate and define what excellent reasoning contains.
    8. Avoid duplicate concepts across the 20 questions.
    
    OUTPUT FORMAT:
    Return ONLY a valid JSON object without any markdown formatting. The JSON must exactly match this schema:
    {{
        "questions": [
            {{
                "slot_id": number,
                "domain": "string (from ontology)",
                "difficulty": number,
                "question": "string",
                "question_type": "string (mcq, multi_select, or short_response)",
                "options": ["string", "string", "string", "string"],
                "answer": "string (must exactly match one option)",
                "rationale": "string",
                "max_score": number
            }}
        ]
    }}
    
    VIVOIQ COMPETENCY ONTOLOGY:
    {json.dumps(COMPETENCY_ONTOLOGY)}
    
    CANDIDATE CAPABILITY PROFILE:
    {json.dumps(capability_profile, indent=2)}
    
    ASSESSMENT BLUEPRINT:
    {json.dumps(blueprint, indent=2)}
    """
    
    try:
        response = model.generate_content(prompt)
        json_str = response.text.strip()
        if json_str.startswith("```json"):
            json_str = json_str[7:]
        if json_str.endswith("```"):
            json_str = json_str[:-3]
        return json.loads(json_str)
    except Exception as e:
        print(f"Error parsing AI-4 JSON: {e}")
        return {}


def run_assessment_integrity_agent(generated_questions: dict, blueprint: dict) -> dict:
    """
    AI-5: Assessment Integrity Agent (Prompt D)
    Reviews the generated questions for ambiguity, leakage, duplicates, factual quality and level appropriateness.
    Replaces defective questions while preserving the original blueprint objective.
    """
    model = genai.GenerativeModel("gemini-3.6-flash")
    
    prompt = f"""
    SYSTEM ROLE:
    You are the VivoIQ Assessment Quality Reviewer.
    
    REVIEW EACH QUESTION FOR:
    relevance, factual accuracy, ambiguity, duplicate testing, difficulty fit, answer leakage, bias, excessive reading time, proprietary/company-specific knowledge and rubric quality.
    
    ACTION:
    Return APPROVE or REPLACE for every question. For REPLACE, state the defect and generate a compliant replacement preserving the original blueprint objective. Ensure the final set remains exactly 20 questions and can be completed within 30 minutes.
    
    OUTPUT FORMAT:
    Return ONLY a valid JSON object without any markdown formatting. The JSON must exactly match this schema:
    {{
        "audit_log": [
            {{
                "slot_id": number,
                "status": "APPROVE or REPLACE",
                "defect_reason": "string (null if approved)"
            }}
        ],
        "replacements": [
            {{
                "slot_id": number,
                "domain": "string",
                "difficulty": number,
                "question": "string",
                "question_type": "string (mcq, multi_select, or short_response)",
                "options": ["string", "string", "string", "string"],
                "answer": "string",
                "rationale": "string",
                "max_score": number
            }}
        ]
    }}
    
    ASSESSMENT BLUEPRINT:
    {json.dumps(blueprint, indent=2)}
    
    GENERATED QUESTIONS (DRAFT):
    {json.dumps(generated_questions, indent=2)}
    """
    
    try:
        response = model.generate_content(prompt)
        json_str = response.text.strip()
        if json_str.startswith("```json"):
            json_str = json_str[7:]
        if json_str.endswith("```"):
            json_str = json_str[:-3]
        ai5_output = json.loads(json_str)
        
        # Merge replacements with original questions to construct final_questions
        replacements_map = {q["slot_id"]: q for q in ai5_output.get("replacements", [])}
        final_questions = []
        
        original_questions = generated_questions.get("questions", [])
        for q in original_questions:
            slot_id = q.get("slot_id")
            if slot_id in replacements_map:
                final_questions.append(replacements_map[slot_id])
            else:
                final_questions.append(q)
                
        ai5_output["final_questions"] = final_questions
        return ai5_output
    except Exception as e:
        print(f"Error parsing AI-5 JSON: {e}")
        # Fallback to the original generated questions if the integrity agent fails
        return {"audit_log": [], "final_questions": generated_questions.get("questions", [])}


def run_response_evaluation_agent(questions: list, user_responses: dict) -> dict:
    """
    AI-6: Response Evaluation Agent (Prompt E)
    Evaluates submitted free-text answers against question-specific rubrics.
    Returns per-question score, evidence, reasoning quality, and confidence.
    """
    model = genai.GenerativeModel("gemini-3.6-flash") # Using flash for high-speed evaluation
    
    payload = []
    for q in questions:
        q_idx = q.get("q_idx")
        ans = user_responses.get(q_idx, "")
        payload.append({
            "q_idx": q_idx,
            "question": q.get("question"),
            "expected_answer": q.get("answer"),
            "rubric": q.get("rubric"),
            "max_score": q.get("max_score", 5),
            "user_answer": ans
        })
        
    prompt = f"""
    SYSTEM ROLE:
    You are the VivoIQ Response Evaluation Agent. Your task is to grade free-form candidate answers against the provided rubrics.
    
    RULES:
    1. For each question, evaluate the user_answer against the expected_answer and rubric.
    2. Be objective, fair, and rigorous.
    3. Determine the score (0 to max_score).
    4. Provide a brief reasoning explaining why the score was awarded based on the rubric.
    5. State your confidence in this evaluation (Low, Medium, High).
    
    INPUT PAYLOAD:
    {json.dumps(payload, indent=2)}
    
    OUTPUT FORMAT:
    Return ONLY a valid JSON object.
    {{
        "evaluations": [
            {{
                "q_idx": number,
                "awarded_score": number,
                "reasoning_quality": "string (brief assessment of candidate's logic)",
                "evidence_found": "string (what part of rubric was met)",
                "confidence": "High | Medium | Low"
            }}
        ]
    }}
    """
    
    try:
        response = model.generate_content(prompt)
        json_str = response.text.strip()
        if json_str.startswith("```json"):
            json_str = json_str[7:]
        if json_str.endswith("```"):
            json_str = json_str[:-3]
        return json.loads(json_str)
    except Exception as e:
        print(f"Error parsing AI-6 JSON: {e}")
        return {"evaluations": []}


def run_learning_recommendation_agent(assessment_results: dict, expected_level: int) -> dict:
    """
    AI-8: Learning Recommendation Agent (Prompt F)
    Translates demonstrated gaps into focused development actions.
    """
    model = genai.GenerativeModel("gemini-3.5-flash") # Using 3.5 flash to bypass rate limits
    
    prompt = f"""
    SYSTEM ROLE
    You are the VivoIQ Procurement Capability Development Advisor.
    
    OBJECTIVE
    Recommend only learning that closes demonstrated capability gaps.
    
    RULES
    1. Prioritize gaps that materially affect the candidate's current or target capability level.
    2. Do not recommend training in areas already strongly demonstrated unless it is an optional advanced pathway.
    3. For each recommendation state: gap, evidence, priority, recommended VivoIQ learning asset, expected outcome and suggested reassessment point.
    4. Distinguish mandatory development from optional enrichment.
    5. Keep the learning pathway focused and achievable (maximum 4 recommendations).
    
    OUTPUT FORMAT:
    Return ONLY a valid JSON object without any markdown formatting. The JSON must exactly match this schema:
    {{
        "learning_pathway": [
            {{
                "domain": "string (from ontology)",
                "gap": "string",
                "evidence": "string (brief context from assessment)",
                "priority": "High | Medium | Low",
                "type": "mandatory | optional",
                "recommended_asset": "string (e.g. Cost modelling micro-course, Advanced sourcing strategy workshop)",
                "expected_outcome": "string",
                "suggested_reassessment": "string (e.g. After 2 weeks of practice)"
            }}
        ]
    }}
    
    VIVOIQ COMPETENCY ONTOLOGY:
    {json.dumps(COMPETENCY_ONTOLOGY)}
    
    EXPECTED VIVOIQ LEVEL: {expected_level}
    
    VERIFIED ASSESSMENT RESULTS (AI-7 Breakdown):
    {json.dumps(assessment_results, indent=2)}
    """
    
    try:
        response = model.generate_content(prompt)
        json_str = response.text.strip()
        if json_str.startswith("```json"):
            json_str = json_str[7:]
        if json_str.endswith("```"):
            json_str = json_str[:-3]
        return json.loads(json_str)
    except Exception as e:
        print(f"Error parsing AI-8 JSON: {e}")
        return {"learning_pathway": []}
