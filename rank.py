import json
import csv
import re
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

# Keywords for text matching (capped weight to avoid over-dependence)
CORE_KEYWORDS = [
    "vector search", "pinecone", "weaviate", "qdrant", "milvus", "faiss",
    "opensearch", "elasticsearch", "learning to rank", "ndcg", "reranking",
    "re-ranking", "recommendation system", "embeddings", "sentence transformers"
]

# Relevant skill names for assessment score lookup
RELEVANT_SKILL_NAMES = [
    "python", "pytorch", "tensorflow", "machine learning", "deep learning",
    "nlp", "embeddings", "vector search", "information retrieval", "ranking",
    "recommendation", "xgboost", "lightgbm", "transformers", "bert", "rag",
    "faiss", "elasticsearch", "opensearch", "semantic search", "fine-tuning"
]

# These are known template first-sentences in job descriptions — skip them when
# looking for a specific, unique accomplishment sentence.
TEMPLATE_SENTENCE_FRAGMENTS = [
    "trained and shipped multiple ranking models for",
    "owned the ranking layer for an e-commerce",
    "implemented a rag-based customer support chatbot",
    "built a content recommendation system serving",
    "developed a semantic search feature for an internal knowledge base",
    "built nlp pipelines for sentiment analysis",
    "built recommendation-style features at a mid-stage startup",
    "built a rag-based ranking pipeline serving",
    "built and operated production ml pipelines",
    "built and shipped a production recommendation system",
    "built computer vision models for",
    "worked on time-series forecasting",
    "worked on customer-facing predictive modeling",
    "owned the search and discovery experience",
    "owned the end-to-end ranking pipeline",
    "designed the ranking layer for the company",
    "owned the design and rollout of a large-scale",
    "built recommendation-style features at a mid-stage",
]

# Markers that indicate a sentence has specific, unique content worth extracting
SPECIFICITY_MARKERS = [
    r"\d+[mkb]\+?",           # 50M+, 10K+, 1B+
    r"\d+%",                   # 12%, 80%
    r"\d+\s*months",           # 9 months
    r"revenue",
    r"latency",
    r"throughput",
    r"a/b test",
    r"offline.online",
    r"offline experiment",
    r"feature pipeline",
    r"training pipeline",
    r"distilbert",
    r"gradient.boost",
    r"matrix factori",
    r"collaborative filter",
    r"hand-tuned",
    r"my main role",
    r"my primary",
    r"most of the work",
    r"most of my",
    r"the key challenge",
    r"improved .* by",
    r"reduced .* by",
    r"designed features",
    r"owned the offline",
    r"worked closely with pm",
    r"\d+\s*warehouse",
    r"three families",
]


def is_template_sentence(sentence_lower):
    """Return True if the sentence matches a known template fragment."""
    for frag in TEMPLATE_SENTENCE_FRAGMENTS:
        if frag in sentence_lower:
            return True
    return False


def specificity_score(sentence):
    """Score how specific / unique a sentence is based on markers."""
    sl = sentence.lower()
    score = 0
    for pattern in SPECIFICITY_MARKERS:
        if re.search(pattern, sl):
            score += 1
    # Longer non-template sentences generally carry more information
    if len(sentence) > 80:
        score += 0.5
    return score


def find_best_sentence(description, company):
    """
    From a job description, find the most specific, non-template sentence.
    Falls back to a constructed fact if nothing beats the templates.
    Returns a cleaned string starting with 'they' or a noun phrase.
    """
    if not description:
        return None

    sentences = [s.strip() for s in description.split(".") if s.strip() and len(s.strip()) > 25]
    if not sentences:
        return None

    # Score all sentences; prefer non-template ones
    best_non_template = None
    best_non_template_score = -1
    best_template = sentences[0]  # fallback

    for sent in sentences:
        sl = sent.lower()
        if is_template_sentence(sl):
            continue
        score = specificity_score(sent)
        if score > best_non_template_score:
            best_non_template_score = score
            best_non_template = sent

    chosen = best_non_template if best_non_template else best_template

    # Clean third-person pronouns
    chosen = chosen.replace("our ", "their ").replace(" our ", " their ")
    chosen = chosen.replace("my ", "their ").replace(" my ", " their ")
    chosen = chosen.replace("I ", "They ").replace(" I ", " they ")
    chosen = chosen.replace("We ", "They ").replace(" we ", " they ")

    # Normalise capitalisation of first word
    words = chosen.split()
    if words:
        first = words[0]
        if first not in ("They", "I", "We") and not first.isupper():
            if len(first) > 1 and first[0].isupper() and first[1].islower():
                words[0] = first[0].lower() + first[1:]
        chosen = " ".join(words)

    # Prefix company context if we fell back to a template sentence
    if best_non_template is None:
        return f"at {company}: {chosen}"
    return f"at {company}, {chosen}"


def check_honeypot(cand):
    """Checks for structural and temporal inconsistencies that signal a honeypot."""
    skills = cand.get("skills", [])
    history = cand.get("career_history", [])
    education = cand.get("education", [])

    # 1. Expert proficiency with 0 duration
    for s in skills:
        if s.get("proficiency") == "expert" and s.get("duration_months", 0) == 0:
            return True

    # 2. Startup founding date timeline violation
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
        if comp in founding_years and start_str:
            try:
                start_yr = datetime.strptime(start_str, "%Y-%m-%d").year
                if start_yr < founding_years[comp]:
                    return True
            except Exception:
                pass

        # 3. Calendar duration vs listed duration mismatch
        end_str = job.get("end_date")
        dur = job.get("duration_months", 0)
        if start_str:
            try:
                s_dt = datetime.strptime(start_str, "%Y-%m-%d")
                e_dt = datetime.strptime(end_str, "%Y-%m-%d") if end_str else REF_DATE
                cal_months = (e_dt.year - s_dt.year) * 12 + (e_dt.month - s_dt.month)
                if dur > cal_months + 2:
                    return True
            except Exception:
                pass

    # 4. Overlapping non-concurrent jobs (>90 day overlap)
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
        next_start = parsed_jobs[i + 1][0]
        if (curr_end - next_start).days > 90:
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
    Multi-stage scorer: honeypot filter → title relevance → career evidence →
    keyword match → experience fit → location → company quality → trajectory →
    education tier → extended behavioral signals.
    """
    profile = cand.get("profile", {})
    skills = cand.get("skills", [])
    history = cand.get("career_history", [])
    signals = cand.get("redrob_signals", {})
    education = cand.get("education", [])

    # ── 1. Honeypot hard filter ──────────────────────────────────────────────
    if check_honeypot(cand):
        return 0.0

    # ── 2. Soft title filters ────────────────────────────────────────────────
    curr_title = profile.get("current_title", "").lower()
    title_multiplier = 1.0
    if any(irr in curr_title for irr in IRRELEVANT_TITLES):
        title_multiplier = 0.05

    tech_history = any(
        not any(irr in job.get("title", "").lower() for irr in IRRELEVANT_TITLES)
        for job in history
    )
    if not tech_history:
        title_multiplier *= 0.05

    # ── 3. Base title score ──────────────────────────────────────────────────
    is_elite = any(el in curr_title for el in ELITE_TITLES)
    title_score = 30.0 if is_elite else 10.0

    # ── 4. Career evidence match ─────────────────────────────────────────────
    career_evidence_score = 0.0

    relevant_jobs_count = sum(
        1 for job in history
        if any(el in job.get("title", "").lower() for el in ELITE_TITLES)
    )
    career_evidence_score += min(relevant_jobs_count, 2) * 10.0  # up to +20

    action_verbs = ["deploy", "scale", "architect", "optimi", "build", "train",
                    "implement", "migrate", "ship", "designed", "owned", "led"]
    ml_nouns = ["retrieval", "vector search", "pinecone", "weaviate", "qdrant",
                "milvus", "faiss", "elasticsearch", "opensearch", "ranking",
                "learning to rank", "ndcg", "recommender", "recommendation",
                "embedding", "semantic search"]
    system_build_count = sum(
        1 for job in history
        if any(v in job.get("description", "").lower() for v in action_verbs)
        and any(n in job.get("description", "").lower() for n in ml_nouns)
    )
    career_evidence_score += min(system_build_count, 3) * 5.0  # up to +15

    # ── 5. Controlled keyword match ──────────────────────────────────────────
    summary = profile.get("summary", "").lower()
    headline = profile.get("headline", "").lower()
    history_text = " ".join(j.get("description", "").lower() for j in history)

    matched_kws = sum(
        1 for kw in CORE_KEYWORDS
        if kw in summary or kw in headline or kw in history_text
    )
    keyword_score = min(matched_kws, 5) * 3.0  # max +15

    # ── 6. Experience fit ────────────────────────────────────────────────────
    exp = profile.get("years_of_experience", 0.0)
    if 5.0 <= exp <= 9.0:
        exp_score = 20.0
    elif 4.0 <= exp < 5.0:
        exp_score = 20.0 - (5.0 - exp) * 10.0
    elif 9.0 < exp <= 12.0:
        exp_score = 20.0 - (exp - 9.0) * 5.0
    else:
        exp_score = 2.0

    # ── 7. Location score (now checks country field) ─────────────────────────
    loc = profile.get("location", "").lower()
    country = profile.get("country", "India")
    willing_relocate = signals.get("willing_to_relocate", False)

    in_india = (country == "India" or not country)
    in_primary = any(city in loc for city in
                     ["noida", "pune", "delhi", "ncr", "gurgaon", "hyderabad",
                      "mumbai", "bangalore", "bengaluru", "chennai"])

    if in_india and in_primary:
        loc_score = 15.0
    elif in_india and willing_relocate:
        loc_score = 10.0
    elif in_india:
        loc_score = 6.0
    elif willing_relocate:
        # Outside India but willing to relocate; visa sponsorship not offered
        loc_score = 4.0
    else:
        # Outside India, not willing to relocate
        loc_score = 0.5

    # ── 8. Company quality ───────────────────────────────────────────────────
    company_score = 0.0
    curr_size = profile.get("current_company_size", "")
    if curr_size in ["11-50", "51-200", "201-500", "501-1000"]:
        company_score += 5.0

    curr_ind = profile.get("current_industry", "").lower()
    if any(ind in curr_ind for ind in RELEVANT_INDUSTRIES):
        company_score += 5.0

    # Past career industry diversity bonus (up to +5)
    relevant_past_industries = sum(
        1 for job in history
        if any(ind in job.get("industry", "").lower() for ind in RELEVANT_INDUSTRIES)
    )
    company_score += min(relevant_past_industries, 5) * 1.0

    curr_comp = profile.get("current_company", "").lower()
    is_curr_service = any(svc in curr_comp for svc in SERVICE_COMPANIES)
    only_service = all(
        any(svc in job.get("company", "").lower() for svc in SERVICE_COMPANIES)
        for job in history
    )

    company_multiplier = 1.0
    if is_curr_service:
        company_multiplier -= 0.15
    if only_service:
        company_multiplier -= 0.50

    # ── 9. Career trajectory ─────────────────────────────────────────────────
    trajectory_score = 0.0
    num_jobs = len(history)
    if num_jobs > 0:
        avg_tenure = exp / num_jobs
        if avg_tenure < 1.5 and num_jobs >= 3:
            trajectory_score -= 10.0
        elif avg_tenure >= 2.5:
            trajectory_score += 5.0

    # Seniority progression bonus
    has_junior_past = any(
        any(j in job.get("title", "").lower() for j in ["junior", "associate", "intern"])
        for job in history[1:]
    )
    has_senior_now = any(
        s in history[0].get("title", "").lower() if history else ""
        for s in ["senior", "lead", "principal", "head", "staff"]
    )
    if has_senior_now and has_junior_past:
        trajectory_score += 5.0

    # ── 10. Education tier bonus ─────────────────────────────────────────────
    edu_score = 0.0
    tier_map = {"tier_1": 4.0, "tier_2": 2.0, "tier_3": 0.5, "tier_4": 0.0, "unknown": 0.0}
    for edu in education:
        tier = edu.get("tier", "unknown")
        edu_score = max(edu_score, tier_map.get(tier, 0.0))

    # ── 11. Skill assessment score bonus ─────────────────────────────────────
    assessment_bonus = 0.0
    skill_assessments = signals.get("skill_assessment_scores", {})
    if skill_assessments:
        relevant_scores = []
        for skill_name, score in skill_assessments.items():
            if any(rel in skill_name.lower() for rel in RELEVANT_SKILL_NAMES):
                relevant_scores.append(score)
        if relevant_scores:
            avg_assessment = sum(relevant_scores) / len(relevant_scores)
            assessment_bonus = (avg_assessment / 100.0) * 6.0  # up to +6 points

    # ── 12. Behavioral modifier (expanded to 12 signals) ─────────────────────
    behavioral_mult = 1.0

    # Recruiter response rate
    rrr = signals.get("recruiter_response_rate", 0.0)
    if rrr >= 0.80:
        behavioral_mult += 0.15
    elif rrr < 0.30:
        behavioral_mult -= 0.25

    # Last active date — fixed branch order (365 before 180)
    last_active = signals.get("last_active_date", "")
    if last_active:
        try:
            la_dt = datetime.strptime(last_active, "%Y-%m-%d")
            days_inactive = (REF_DATE - la_dt).days
            if days_inactive > 365:
                behavioral_mult -= 0.60
            elif days_inactive > 180:
                behavioral_mult -= 0.30
        except Exception:
            pass

    # Notice period (tightened thresholds)
    np_days = signals.get("notice_period_days", 60)
    if np_days <= 30:
        behavioral_mult += 0.10
    elif 90 <= np_days < 120:
        behavioral_mult -= 0.20
    elif np_days >= 120:
        behavioral_mult -= 0.35

    # Relocation willingness
    if willing_relocate:
        behavioral_mult += 0.05

    # GitHub activity
    gh = signals.get("github_activity_score", -1)
    if gh >= 40:
        behavioral_mult += 0.05
    elif gh == -1:
        behavioral_mult -= 0.05

    # Open to work
    if signals.get("open_to_work_flag", False):
        behavioral_mult += 0.05

    # Profile completeness
    completeness = signals.get("profile_completeness_score", 50)
    if completeness >= 80:
        behavioral_mult += 0.05
    elif completeness < 40:
        behavioral_mult -= 0.05

    # Saved by recruiters in last 30 days (external quality signal)
    saved = signals.get("saved_by_recruiters_30d", 0)
    if saved >= 10:
        behavioral_mult += 0.12
    elif saved >= 5:
        behavioral_mult += 0.07
    elif saved >= 2:
        behavioral_mult += 0.03

    # Interview completion rate
    icr = signals.get("interview_completion_rate", 0.5)
    if icr >= 0.80:
        behavioral_mult += 0.05
    elif icr < 0.40:
        behavioral_mult -= 0.05

    # Active job seeker signal
    apps = signals.get("applications_submitted_30d", 0)
    if apps >= 3:
        behavioral_mult += 0.03

    # Work mode preference — JD says hybrid; remote-only is a mild mismatch
    work_mode = signals.get("preferred_work_mode", "flexible")
    if work_mode == "remote":
        behavioral_mult -= 0.05

    # Verification signals (identity authenticity)
    if signals.get("verified_email", False) and signals.get("verified_phone", False):
        behavioral_mult += 0.03

    # ── 13. Final score assembly ─────────────────────────────────────────────
    base_sum = (title_score + career_evidence_score + keyword_score +
                exp_score + loc_score + company_score + trajectory_score +
                edu_score + assessment_bonus)

    # Over-experience multiplier
    over_exp_multiplier = 1.0
    if exp > 12.0:
        over_exp_multiplier = 0.85
    if exp > 15.0:
        over_exp_multiplier = 0.70

    final_score = (base_sum * title_multiplier * company_multiplier *
                   over_exp_multiplier * max(0.1, behavioral_mult))

    return final_score


# ── Reasoning helpers ─────────────────────────────────────────────────────────

def capitalize_first(s):
    if not s:
        return s
    return s[0].upper() + s[1:]


def get_most_relevant_job(history):
    """Return the career history entry most relevant to the JD."""
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


def get_rank_label(rank):
    """Return a rank-appropriate quality label."""
    if rank <= 10:
        return "A standout fit"
    elif rank <= 30:
        return "A strong match"
    elif rank <= 60:
        return "A solid candidate"
    elif rank <= 80:
        return "A qualified candidate"
    else:
        return "An adjacent candidate"


def get_relevant_skills_str(skills):
    """Return a formatted string of the top relevant verified skills."""
    relevant_found = []
    seen = set()
    all_targets = (CORE_KEYWORDS +
                   ["rag", "llms", "fine-tuning", "nlp", "pytorch", "xgboost",
                    "lightgbm", "vector search", "semantic search",
                    "information retrieval", "reranking"])
    for s in skills:
        s_name = s.get("name", "")
        s_lower = s_name.lower()
        if any(t in s_lower for t in all_targets) and s_lower not in seen:
            seen.add(s_lower)
            relevant_found.append(s_name)

    if len(relevant_found) >= 3:
        return f"skills in {relevant_found[0]}, {relevant_found[1]}, and {relevant_found[2]}"
    elif len(relevant_found) == 2:
        return f"skills in {relevant_found[0]} and {relevant_found[1]}"
    elif len(relevant_found) == 1:
        return f"skill in {relevant_found[0]}"
    else:
        return "strong foundational engineering background"


def get_education_str(education):
    """Extract the best education entry as a formatted string."""
    if not education:
        return ""
    best_edu = education[0]
    for edu in education:
        deg = edu.get("degree", "").lower()
        if any(x in deg for x in ["m.tech", "m.s", "m.sc", "phd", "ph.d", "master"]):
            best_edu = edu
            break
    deg_name = best_edu.get("degree", "")
    field = best_edu.get("field_of_study", "")
    inst = best_edu.get("institution", "")
    if deg_name and field and inst:
        return f"a {deg_name} in {field} from {inst}"
    elif deg_name and inst:
        return f"a {deg_name} from {inst}"
    elif deg_name and field:
        return f"a {deg_name} in {field}"
    return ""


def generate_reasoning(cand, rank):
    """
    Generates a high-quality, factual, evidence-first 1-2 sentence explanation.
    Four structural styles rotate by rank. No template phrases like 'Earning a top
    rank'. Accomplishment is extracted from the most specific (non-template)
    sentence in the candidate's most relevant job description.
    """
    profile = cand.get("profile", {})
    skills = cand.get("skills", [])
    history = cand.get("career_history", [])
    education = cand.get("education", [])
    signals = cand.get("redrob_signals", {})

    exp = profile.get("years_of_experience", 0)
    title = profile.get("current_title", "Engineer")
    company = profile.get("current_company", "their current company")
    loc = profile.get("location", "India")
    country = profile.get("country", "India")
    rrr = int(signals.get("recruiter_response_rate", 0) * 100)
    notice = signals.get("notice_period_days", 60)
    willing_relocate = signals.get("willing_to_relocate", False)
    open_to_work = signals.get("open_to_work_flag", False)
    saved = signals.get("saved_by_recruiters_30d", 0)

    # Accomplishment from most relevant job
    relevant_job = get_most_relevant_job(history)
    if relevant_job:
        job_comp = relevant_job.get("company", company)
        job_desc = relevant_job.get("description", "")
        accomplishment = find_best_sentence(job_desc, job_comp)
    else:
        accomplishment = None
    if not accomplishment:
        accomplishment = f"at {company}, currently serving as {title}"

    # Skills string
    skills_str = get_relevant_skills_str(skills)

    # Location string
    loc_clean = (loc or "India").strip()
    if country and country != "India":
        loc_clean = f"{loc_clean} ({country})"
    relocate_txt = ", open to relocation" if willing_relocate else ""

    # Notice and response rate
    if not notice or notice == 0:
        notice_txt = "immediately available"
    else:
        notice_txt = f"{notice}-day notice"
    rrr_str = f"{rrr}% recruiter response rate"

    # Education
    edu_str = get_education_str(education)

    # Tenure
    num_jobs = len(history)
    avg_tenure = exp / num_jobs if num_jobs > 0 else 0

    # A/An prefix for title
    an_starters = ["ai", "ml", "nlp", "applied", "associate", "information", "engineer"]
    prefix = "an" if any(title.lower().startswith(x) for x in an_starters) else "a"

    # Rank label (replaces "Earning a top rank")
    rank_label = get_rank_label(rank)

    # Open to work supplement
    otw_txt = " and actively open to new opportunities" if open_to_work else ""
    saved_txt = f"; bookmarked by {saved} recruiters recently" if saved >= 3 else ""

    # Concern flags for lower ranks
    concerns = []
    if notice and notice >= 90:
        concerns.append(f"{notice}-day notice")
    if country and country != "India" and not willing_relocate:
        concerns.append("international location without relocation intent")
    concern_str = ("; note: " + ", ".join(concerns)) if concerns else ""

    style_idx = rank % 4

    if style_idx == 0:
        # Style A: Accomplishment-first
        edu_part = f", with {edu_str}" if edu_str else ""
        reasoning = (
            f"{rank_label}: {capitalize_first(accomplishment)}. "
            f"They bring {exp} years as {prefix} {title}{edu_part} "
            f"and verified {skills_str}. "
            f"Located in {loc_clean}{relocate_txt}{otw_txt}, {notice_txt} ({rrr_str}{saved_txt}){concern_str}."
        )
    elif style_idx == 1:
        # Style B: Role + company first
        edu_part = f" — {edu_str}" if edu_str else ""
        reasoning = (
            f"{capitalize_first(prefix)} {title} at {company} with {exp} years{edu_part}. "
            f"Demonstrated {skills_str}: {accomplishment}{concern_str}. "
            f"Based in {loc_clean}{relocate_txt}; {notice_txt}, {rrr_str}{saved_txt}{otw_txt}."
        )
    elif style_idx == 2:
        # Style C: Skills + trajectory first
        edu_part = f" ({edu_str})" if edu_str else ""
        reasoning = (
            f"With {exp} years of experience and verified {skills_str}{edu_part}, "
            f"they show a stable career averaging {avg_tenure:.1f} years per role. "
            f"Notably {accomplishment}{concern_str}. "
            f"In {loc_clean}{relocate_txt}{otw_txt}; {notice_txt}, {rrr_str}{saved_txt}."
        )
    else:
        # Style D: JD-fit framing
        edu_part = f" and holds {edu_str}" if edu_str else ""
        reasoning = (
            f"{rank_label} for this role: {exp} years as {prefix} {title}{edu_part}. "
            f"Verified {skills_str}. {capitalize_first(accomplishment)}{concern_str}. "
            f"{loc_clean}{relocate_txt}{otw_txt} — {notice_txt}, {rrr_str}{saved_txt}."
        )

    return reasoning


def main():
    parser = argparse.ArgumentParser(description="Rank candidates for Track 1.")
    parser.add_argument("--candidates", required=True, help="Path to candidates.jsonl, .jsonl.gz, or .json")
    parser.add_argument("--out", required=True, help="Path to output submission.csv")
    parser.add_argument("--top-n", type=int, default=100,
                        help="Number of top candidates to output (default: 100). "
                             "Use a smaller value for demo/sandbox runs with fewer candidates.")
    args = parser.parse_args()

    scored_candidates = []
    print("Reading and scoring candidates...")

    # Auto-detect format: .json (array), .jsonl, or .jsonl.gz
    candidates_path = args.candidates
    if candidates_path.endswith(".gz"):
        import gzip
        with gzip.open(candidates_path, "rt", encoding="utf-8") as f:
            raw = f.read()
        lines = raw.splitlines()
        for line in lines:
            if not line.strip():
                continue
            cand = json.loads(line)
            cid = cand["candidate_id"]
            score = round(score_candidate(cand), 4)
            if score > 0:
                scored_candidates.append((cid, score, cand))
    elif candidates_path.endswith(".json"):
        # JSON array format (e.g. sample_candidates.json)
        with open(candidates_path, "r", encoding="utf-8") as f:
            candidates_list = json.load(f)
        for cand in candidates_list:
            cid = cand["candidate_id"]
            score = round(score_candidate(cand), 4)
            if score > 0:
                scored_candidates.append((cid, score, cand))
    else:
        # Plain .jsonl
        with open(candidates_path, "r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                cand = json.loads(line)
                cid = cand["candidate_id"]
                score = round(score_candidate(cand), 4)
                if score > 0:
                    scored_candidates.append((cid, score, cand))

    # Deterministic sort: score descending, then candidate_id ascending for ties
    scored_candidates.sort(key=lambda x: (-x[1], x[0]))

    top_n = min(getattr(args, 'top_n', 100), len(scored_candidates))
    top_candidates = scored_candidates[:top_n]
    print(f"Scored {len(scored_candidates)} valid candidates.")
    print(f"Top score: {top_candidates[0][1]:.4f}. Rank-{top_n} score: {top_candidates[-1][1]:.4f}.")

    print(f"Writing top {top_n} to {args.out}...")
    with open(args.out, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["candidate_id", "rank", "score", "reasoning"])
        for i, (cid, score, cand) in enumerate(top_candidates):
            rank = i + 1
            reasoning = generate_reasoning(cand, rank)
            writer.writerow([cid, rank, score, reasoning])

    print("Done.")


if __name__ == "__main__":
    main()
