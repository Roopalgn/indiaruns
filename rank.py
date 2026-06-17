import json
import csv
import argparse
from datetime import datetime

# Reference date for calculating inactivity and durations
REF_DATE = datetime(2026, 6, 18)

# Predefined list of service companies to penalize
SERVICE_COMPANIES = {
    "infosys", "tcs", "wipro", "capgemini", "accenture", "cognizant", 
    "tech mahindra", "mphasis", "mindtree", "hcl"
}

# Relevant industries for product alignment
RELEVANT_INDUSTRIES = {
    "software", "ai/ml", "fintech", "e-commerce", "food delivery", "saas", 
    "adtech", "edtech", "conversational ai", "voice ai", "healthtech ai", "internet"
}

# Elite AI/ML/Search titles to award higher relevance
ELITE_TITLES = [
    "recommendation", "search engineer", "retrieval engineer", "nlp engineer",
    "applied ml", "machine learning", "ml engineer", "ai engineer", "ai specialist",
    "ai research engineer"
]

# Irrelevant titles to penalize
IRRELEVANT_TITLES = [
    "hr manager", "accountant", "customer support", "content writer", 
    "sales executive", "civil engineer", "mechanical engineer", "graphic designer", 
    "marketing manager", "operations manager"
]

# Keywords for text matching (lowered weight to avoid over-dependence)
CORE_KEYWORDS = [
    "vector search", "pinecone", "weaviate", "qdrant", "milvus", "faiss", "opensearch", "elasticsearch",
    "learning to rank", "ndcg", "reranking", "re-ranking", "recommendation system", "embeddings", 
    "sentence transformers"
]

def check_honeypot(cand):
    """
    Checks for structural and temporal inconsistencies that signal a honeypot.
    """
    skills = cand.get("skills", [])
    history = cand.get("career_history", [])
    education = cand.get("education", [])
    
    # 1. Expert proficiency with 0 duration check
    for s in skills:
        if s.get("proficiency") == "expert" and s.get("duration_months", 0) == 0:
            return True
            
    # 2. Startup founding date timeline violation check
    founding_years = {
        "Krutrim": 2023,
        "Sarvam AI": 2023,
        "CRED": 2018,
        "Glance": 2019,
        "Rephrase.ai": 2019,
    }
    
    for job in history:
        comp = job.get("company")
        start_str = job.get("start_date")
        end_str = job.get("end_date")
        dur = job.get("duration_months", 0)
        
        if comp in founding_years and start_str:
            try:
                start_yr = datetime.strptime(start_str, "%Y-%m-%d").year
                if start_yr < founding_years[comp]:
                    return True
            except Exception:
                pass
                
        # 3. Calendar duration vs listed duration check
        if start_str:
            try:
                s_dt = datetime.strptime(start_str, "%Y-%m-%d")
                e_dt = datetime.strptime(end_str, "%Y-%m-%d") if end_str else REF_DATE
                cal_months = (e_dt.year - s_dt.year) * 12 + (e_dt.month - s_dt.month)
                if dur > cal_months + 2:
                    return True
            except Exception:
                pass
                
    # 4. Overlapping non-concurrent jobs
    parsed_jobs = []
    for job in history:
        start_str = job.get("start_date")
        end_str = job.get("end_date") or "2026-06-18"
        try:
            s_dt = datetime.strptime(start_str, "%Y-%m-%d")
            e_dt = datetime.strptime(end_str, "%Y-%m-%d")
            parsed_jobs.append((s_dt, e_dt))
        except Exception:
            pass
    parsed_jobs.sort(key=lambda x: x[0])
    for i in range(len(parsed_jobs) - 1):
        curr_end = parsed_jobs[i][1]
        next_start = parsed_jobs[i+1][0]
        if (curr_end - next_start).days > 90: # Overlap > 3 months
            return True
            
    # 5. Career starts before college start year
    min_job_year = 9999
    for job in history:
        start_str = job.get("start_date")
        if start_str:
            try:
                yr = datetime.strptime(start_str, "%Y-%m-%d").year
                if yr < min_job_year:
                    min_job_year = yr
            except Exception:
                pass
    for edu in education:
        start_yr = edu.get("start_year")
        if start_yr and min_job_year < start_yr - 1:
            return True
                
    return False

def score_candidate(cand):
    """
    Scores a candidate based on title relevance, career evidence, experience, 
    derived company quality, career trajectory, and behavioral metrics.
    """
    profile = cand.get("profile", {})
    skills = cand.get("skills", [])
    history = cand.get("career_history", [])
    signals = cand.get("redrob_signals", {})
    
    # 1. Honeypot Hard Filter
    if check_honeypot(cand):
        return 0.0
        
    # 2. Soft title filters (convert hard exclusions to penalties)
    curr_title = profile.get("current_title", "").lower()
    title_multiplier = 1.0
    if any(irr in curr_title for irr in IRRELEVANT_TITLES):
        title_multiplier = 0.05
        
    # Check if they have only worked in irrelevant titles in history
    tech_history = False
    for job in history:
        title = job.get("title", "").lower()
        if not any(irr in title for irr in IRRELEVANT_TITLES):
            tech_history = True
            break
    if not tech_history:
        title_multiplier *= 0.05

    # 3. Base Title Score
    is_elite = any(el in curr_title for el in ELITE_TITLES)
    title_score = 30.0 if is_elite else 10.0
    
    # 4. Career Evidence Match (System design & past roles)
    career_evidence_score = 0.0
    
    # Relevant past titles held
    relevant_jobs_count = 0
    for job in history:
        t = job.get("title", "").lower()
        if any(el in t for el in ELITE_TITLES):
            relevant_jobs_count += 1
    career_evidence_score += min(relevant_jobs_count, 2) * 10.0 # Up to +20 points
    
    # System building achievements (action verb + ml noun in description)
    action_verbs = ["deploy", "scale", "architect", "optimi", "build", "train", "implement", "migrate", "ship"]
    ml_nouns = ["retrieval", "vector search", "pinecone", "weaviate", "qdrant", "milvus", "faiss", "elasticsearch", "opensearch", "ranking", "learning to rank", "ndcg", "recommender", "recommendation"]
    
    system_build_count = 0
    for job in history:
        desc = job.get("description", "").lower()
        has_verb = any(v in desc for v in action_verbs)
        has_noun = any(n in desc for n in ml_nouns)
        if has_verb and has_noun:
            system_build_count += 1
    career_evidence_score += min(system_build_count, 3) * 5.0 # Up to +15 points
    
    # 5. Controlled Keyword Match (de-emphasized)
    keyword_score = 0.0
    summary = profile.get("summary", "").lower()
    headline = profile.get("headline", "").lower()
    history_text = " ".join([j.get("description", "").lower() for j in history])
    
    matched_kws = 0
    for kw in CORE_KEYWORDS:
        if kw in summary or kw in headline or kw in history_text:
            matched_kws += 1
    keyword_score += min(matched_kws, 5) * 3.0 # Max +15 points
    
    # 6. Experience Fit Score
    exp = profile.get("years_of_experience", 0.0)
    if 5.0 <= exp <= 9.0:
        exp_score = 20.0
    elif 4.0 <= exp < 5.0:
        exp_score = 20.0 - (5.0 - exp) * 10.0
    elif 9.0 < exp <= 12.0:
        exp_score = 20.0 - (exp - 9.0) * 5.0
    else:
        exp_score = 2.0 # Heavy penalty
        
    # 7. Location Score
    loc = profile.get("location", "").lower()
    willing_relocate = signals.get("willing_to_relocate", False)
    in_primary = "noida" in loc or "pune" in loc or "delhi" in loc or "ncr" in loc or "gurgaon" in loc
    
    if in_primary:
        loc_score = 15.0
    elif willing_relocate:
        loc_score = 10.0
    else:
        loc_score = 1.0 # Heavy penalty if not local and not willing to relocate
        
    # 8. Derived Company Quality Score (based on size and industry)
    company_score = 0.0
    
    # Startup/Mid-market boost (sizes 11-50, 51-200, 201-500, 501-1000)
    curr_size = profile.get("current_company_size", "")
    if curr_size in ["11-50", "51-200", "201-500", "501-1000"]:
        company_score += 5.0
        
    # Industry alignment boost
    curr_ind = profile.get("current_industry", "").lower()
    if any(ind in curr_ind for ind in RELEVANT_INDUSTRIES):
        company_score += 5.0
        
    # Conservative Service Company Penalty Multiplier
    curr_comp = profile.get("current_company", "").lower()
    is_curr_service = any(svc in curr_comp for svc in SERVICE_COMPANIES)
    
    only_service = True
    for job in history:
        comp = job.get("company", "").lower()
        if not any(svc in comp for svc in SERVICE_COMPANIES):
            only_service = False
            break
            
    company_multiplier = 1.0
    if is_curr_service:
        company_multiplier -= 0.15
    if only_service:
        company_multiplier -= 0.50

    # 9. Career Trajectory Score
    trajectory_score = 0.0
    num_jobs = len(history)
    if num_jobs > 0:
        avg_tenure = exp / num_jobs
        # Job hopper penalty
        if avg_tenure < 1.5 and num_jobs >= 3:
            trajectory_score -= 10.0
        # Tenure stability boost
        elif avg_tenure >= 2.5:
            trajectory_score += 5.0
            
    # Seniority Progression boost (Associate/Junior -> Senior/Lead)
    has_junior_past = False
    has_senior_now = False
    for i, job in enumerate(history):
        t = job.get("title", "").lower()
        if i == 0:
            if "senior" in t or "lead" in t or "principal" in t or "head" in t:
                has_senior_now = True
        else:
            if "junior" in t or "associate" in t or "intern" in t:
                has_junior_past = True
    if has_senior_now and has_junior_past:
        trajectory_score += 5.0

    # 10. Behavioral Modifier Multiplier (Fixed branching logic)
    behavioral_mult = 1.0
    
    # Recruiter response rate
    rrr = signals.get("recruiter_response_rate", 0.0)
    if rrr >= 0.80:
        behavioral_mult += 0.15
    elif rrr < 0.30:
        behavioral_mult -= 0.25
        
    # Last active date
    last_active = signals.get("last_active_date", "")
    if last_active:
        try:
            la_dt = datetime.strptime(last_active, "%Y-%m-%d")
            days_inactive = (REF_DATE - la_dt).days
            # FIXED BRANCH ORDER
            if days_inactive > 365:
                behavioral_mult -= 0.60
            elif days_inactive > 180:
                behavioral_mult -= 0.30
        except Exception:
            pass
            
    # Notice Period
    np = signals.get("notice_period_days", 60)
    if np <= 30:
        behavioral_mult += 0.10
    elif np >= 90:
        behavioral_mult -= 0.15
        
    if willing_relocate:
        behavioral_mult += 0.05
    gh = signals.get("github_activity_score", -1)
    if gh >= 40:
        behavioral_mult += 0.05
    elif gh == -1:
        behavioral_mult -= 0.05
    if signals.get("open_to_work_flag", False):
        behavioral_mult += 0.05
        
    # Calculate final score
    base_sum = title_score + career_evidence_score + keyword_score + exp_score + loc_score + company_score + trajectory_score
    
    # Over-experience multiplier to penalize candidates far beyond the 5-9 year target
    over_exp_multiplier = 1.0
    if exp > 12.0:
        over_exp_multiplier = 0.85
    if exp > 15.0:
        over_exp_multiplier = 0.70
        
    final_score = base_sum * title_multiplier * company_multiplier * over_exp_multiplier * max(0.1, behavioral_mult)
    
    return final_score

def capitalize_first(s):
    if not s:
        return s
    return s[0].upper() + s[1:]

def clean_accomplishment(company, desc):
    if not desc:
        return ""
    sentences = [s.strip() for s in desc.split(". ") if s.strip()]
    if not sentences:
        return ""
    first_sent = sentences[0]
    if first_sent.endswith("."):
        first_sent = first_sent[:-1]
    
    first_sent = first_sent.replace("our ", "the ").replace("my ", "the ").replace("We ", "They ").replace("I ", "They ")
    
    words = first_sent.split()
    if words:
        first_word = words[0]
        if first_word.isupper():
            pass
        elif first_word in ["Owned", "Trained", "Implemented", "Developed", "Led", "Built", "Designed", "Created", "Evolved"]:
            words[0] = first_word.lower()
        else:
            if len(first_word) > 1 and first_word[0].isupper() and first_word[1].islower():
                words[0] = first_word.lower()
            
    clean_sent = " ".join(words)
    return f"they {clean_sent} at {company}"

def get_most_relevant_job(history):
    if not history:
        return None
    best_job = history[0]
    best_score = -1
    for job in history:
        score = 0
        title = job.get("title", "").lower()
        desc = job.get("description", "").lower()
        for elite in ELITE_TITLES:
            if elite in title:
                score += 10
        for kw in CORE_KEYWORDS:
            if kw in desc:
                score += 2
        if score > best_score:
            best_score = score
            best_job = job
    return best_job

def generate_reasoning(cand, rank):
    """
    Generates a high-quality, factual, and deterministic 1-2 sentence explanation
    explaining why this candidate is at this rank, grounded in their profile evidence.
    """
    profile = cand.get("profile", {})
    skills = cand.get("skills", [])
    history = cand.get("career_history", [])
    education = cand.get("education", [])
    signals = cand.get("redrob_signals", {})
    
    exp = profile.get("years_of_experience")
    title = profile.get("current_title")
    company = profile.get("current_company")
    loc = profile.get("location")
    rrr = int(signals.get("recruiter_response_rate", 0) * 100)
    notice = signals.get("notice_period_days")
    willing_relocate = signals.get("willing_to_relocate")
    curr_size = profile.get("current_company_size")
    
    # 1. Accomplishment extraction
    relevant_job = get_most_relevant_job(history)
    accomplishment = ""
    if relevant_job:
        job_comp = relevant_job.get("company", "their past role")
        job_desc = relevant_job.get("description", "")
        accomplishment = clean_accomplishment(job_comp, job_desc)
    if not accomplishment:
        accomplishment = f"worked as a {title} at {company}"
        
    # 2. Verified skills extraction
    relevant_found = []
    seen_skills = set()
    for s in skills:
        s_name = s.get("name", "")
        s_name_lower = s_name.lower()
        is_relevant = False
        # Match against CORE_KEYWORDS or other key AI/ML skills
        for target in CORE_KEYWORDS + ["rag", "llms", "fine-tuning", "nlp", "pytorch", "xgboost", "lightgbm", "vector search", "semantic search", "information retrieval", "reranking"]:
            if target in s_name_lower:
                is_relevant = True
                break
        if is_relevant and s_name_lower not in seen_skills:
            seen_skills.add(s_name_lower)
            relevant_found.append(s_name)
            
    if len(relevant_found) >= 3:
        skills_str = f"verified skills in {', '.join(relevant_found[:2])}, and {relevant_found[2]}"
    elif len(relevant_found) == 2:
        skills_str = f"verified skills in {relevant_found[0]} and {relevant_found[1]}"
    elif len(relevant_found) == 1:
        skills_str = f"verified skill in {relevant_found[0]}"
    else:
        skills_str = "strong foundational engineering skills"
        
    # 3. Location and notice period
    loc_clean = (loc or "India").replace("based in ", "").replace("Based in ", "").strip()
    relocate_txt = ", open to relocation" if willing_relocate else ""
    rrr_str = f"{rrr}% response rate"
    
    # 4. Tenure stability
    num_jobs = len(history)
    avg_tenure = exp / num_jobs if num_jobs > 0 else 0
    tenure_str = f"average tenure of {avg_tenure:.1f} years"
    
    # 5. Education extraction
    edu_str = ""
    if education:
        best_edu = education[0]
        for edu in education:
            deg = edu.get("degree", "").lower()
            if any(x in deg for x in ["m.tech", "m.s", "m.sc", "phd", "ph.d", "master", "ph.d."]):
                best_edu = edu
                break
        deg_name = best_edu.get("degree", "")
        field_name = best_edu.get("field_of_study", "")
        inst_name = best_edu.get("institution", "")
        if deg_name and field_name and inst_name:
            edu_str = f"a {deg_name} in {field_name} from {inst_name}"
        elif deg_name and field_name:
            edu_str = f"a {deg_name} in {field_name}"
        elif deg_name and inst_name:
            edu_str = f"a {deg_name} from {inst_name}"

    # Styles rotation
    style_idx = rank % 4
    
    # Prefix
    an_titles = ["ai", "ml", "nlp", "applied", "associate", "intern", "infrastructure", "information", "engineer"]
    prefix = "An" if any(title.lower().startswith(x) for x in an_titles) else "A"
    
    notice_txt = "immediate notice" if (notice == 0 or not notice) else f"a {notice}-day notice"
    notice_lbl = "immediate notice" if (notice == 0 or not notice) else f"{notice}-day notice"
    
    if style_idx == 0:
        edu_part = f", who holds {edu_str}," if edu_str else ""
        reasoning = (
            f"{capitalize_first(accomplishment)}. Earning a top rank, they bring {exp} years of experience as {prefix.lower()} {title}{edu_part} "
            f"with {skills_str}. Based in {loc_clean}{relocate_txt}, they maintain a {rrr_str} and {notice_txt}."
        )
    elif style_idx == 1:
        edu_part = f" They also hold {edu_str}." if edu_str else ""
        reasoning = (
            f"{prefix} {title} at {company} with {exp} years of experience, they have {skills_str}. "
            f"{capitalize_first(accomplishment)}.{edu_part} They are located in {loc_clean}{relocate_txt} with {notice_txt} ({rrr_str})."
        )
    elif style_idx == 2:
        edu_part = f" holding {edu_str}," if edu_str else ""
        reasoning = (
            f"With {exp} years of professional experience and {skills_str}, they showcase a stable career trajectory "
            f"({tenure_str}). A candidate{edu_part} {accomplishment}. Currently residing in {loc_clean}{relocate_txt}, "
            f"they have {notice_txt} and a {rrr_str}."
        )
    else:
        edu_part = f" and holding {edu_str}," if edu_str else ""
        reasoning = (
            f"This candidate offers {exp} years of expertise as {prefix.lower()} {title}, currently at {company}. "
            f"{capitalize_first(accomplishment)}. Supported by {skills_str}{edu_part} they are based in {loc_clean}{relocate_txt} "
            f"({notice_lbl}, {rrr_str})."
        )
        
    return reasoning

def main():
    parser = argparse.ArgumentParser(description="Rank candidates for Track 1.")
    parser.add_argument("--candidates", required=True, help="Path to candidates.jsonl")
    parser.add_argument("--out", required=True, help="Path to output submission.csv")
    args = parser.parse_args()
    
    scored_candidates = []
    
    # Read and score candidates
    print("Reading and scoring candidates...")
    with open(args.candidates, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            cand = json.loads(line)
            cid = cand["candidate_id"]
            score = round(score_candidate(cand), 4)
            if score > 0:
                scored_candidates.append((cid, score, cand))
                
    # Deterministic sorting: score descending, then candidate_id ascending
    scored_candidates.sort(key=lambda x: (-x[1], x[0]))
    
    # Take top 100
    top_100 = scored_candidates[:100]
    print(f"Scored {len(scored_candidates)} valid candidates. Top score: {top_100[0][1]:.4f}. Lower bound score: {top_100[-1][1]:.4f}")
    
    # Write submission CSV
    print(f"Writing submission to {args.out}...")
    with open(args.out, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["candidate_id", "rank", "score", "reasoning"])
        
        for i, (cid, score, cand) in enumerate(top_100):
            rank = i + 1
            reasoning = generate_reasoning(cand, rank)
            writer.writerow([cid, rank, score, reasoning])
            
    print("Done!")

if __name__ == "__main__":
    main()
