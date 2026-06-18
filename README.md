# Track 1 — Intelligent Candidate Discovery & Ranking

## Quick Start

**Requirements:** Python 3.8+ (standard library only — no pip installs needed)

```bash
# Clone and enter the repo
git clone https://github.com/Roopalgn/indiaruns
cd indiaruns

# Run the ranker (produces submission.csv)
python rank.py \
  --candidates ./candidates.jsonl \
  --out ./submission.csv

# Validate the output format
python "[PUB] India_runs_data_and_ai_challenge/India_runs_data_and_ai_challenge/validate_submission.py" submission.csv
```

**Expected runtime:** ~2 seconds on any modern CPU  
**Memory:** <500 MB peak  
**No GPU, no network, no external APIs required**

---

## Architecture & Methodology

A deterministic, multi-stage heuristic ranker designed to score candidates against the Senior AI Engineer JD without keyword stuffing, honeypot contamination, or template-driven reasoning.

### Scoring Pipeline

All scoring happens in `rank.py` in a single sequential pass over `candidates.jsonl`.

#### Stage 1 — Honeypot Filter (hard exclusion → score = 0)
Five independent checks flag structurally impossible profiles:
- Expert-proficiency skills with 0 months of use
- Employment start dates before a known company's founding year (e.g., Sarvam AI founded 2023)
- Listed `duration_months` greater than the calendar span of the role by >2 months
- Overlapping non-concurrent jobs (>90 day overlap)
- Career start year predating college entry year

#### Stage 2 — Weighted Component Scoring

| Component | Max Points | Rationale |
|---|---|---|
| Base title score | 30 | Elite ML/search titles vs. irrelevant titles (0.05× multiplier) |
| Career evidence | 35 | Past elite titles (+10 ea.) + system-building descriptions (+5 ea.) |
| Keyword match | 15 | Capped diversity matching over summary, headline, and history |
| Experience fit | 20 | Gaussian-style penalty away from 5–9 year target band |
| Location | 15 | Primary cities > India + willing to relocate > outside India |
| Company quality | 15 | Startup/mid-market size + industry alignment + past industry diversity |
| Career trajectory | 10 | Tenure stability bonus; job-hopper penalty; seniority progression |
| Education tier | 4 | Uses dataset's pre-computed `tier` field (tier_1=+4, tier_2=+2) |
| Skill assessments | 6 | Platform-validated assessment scores for relevant skill names |

#### Stage 3 — Multipliers

Three multiplicative adjustments applied to the base sum:

1. **Title multiplier** (0.05–1.0): Irrelevant-title candidates are near-zeroed
2. **Company multiplier** (0.35–1.0): Service-only career → 0.5× penalty
3. **Over-experience multiplier** (0.7–1.0): >12y → 0.85×; >15y → 0.70×

#### Stage 4 — 12-Signal Behavioral Modifier

A single behavioral multiplier incorporating all available Redrob platform signals:

| Signal | Effect |
|---|---|
| `recruiter_response_rate` ≥80% | +0.15 |
| `recruiter_response_rate` <30% | −0.25 |
| `last_active_date` >365 days ago | −0.60 |
| `last_active_date` >180 days ago | −0.30 |
| `notice_period_days` ≤30 | +0.10 |
| `notice_period_days` 90–119 | −0.20 |
| `notice_period_days` ≥120 | −0.35 |
| `open_to_work_flag` = true | +0.05 |
| `willing_to_relocate` = true | +0.05 |
| `github_activity_score` ≥40 | +0.05 |
| `profile_completeness_score` ≥80 | +0.05 |
| `saved_by_recruiters_30d` ≥10 | +0.12 |
| `saved_by_recruiters_30d` ≥5 | +0.07 |
| `interview_completion_rate` ≥80% | +0.05 |
| `interview_completion_rate` <40% | −0.05 |
| `applications_submitted_30d` ≥3 | +0.03 |
| `preferred_work_mode` = remote | −0.05 |
| `verified_email` AND `verified_phone` | +0.03 |

---

### Reasoning Generation

Each candidate's 1–2 sentence reasoning is built by extracting **specific, non-template content** from their most relevant job description. The extractor:

1. Identifies the most JD-relevant role in the candidate's history (scoring by elite title match + keyword hits)
2. Scores every sentence in that description for specificity markers (numeric metrics, outcome verbs, specific tool names)
3. Skips known template first-sentences shared across many candidates
4. Uses the highest-specificity non-template sentence as the accomplishment claim
5. Combines with verified profile facts: experience years, verified skills, education tier, location, notice period, and response rate

Four structural styles rotate by rank position. Tone is rank-calibrated:
- Ranks 1–10: "A standout fit..."
- Ranks 11–30: "A strong match..."
- Ranks 31–60: "A solid candidate..."
- Ranks 61–80: "A qualified candidate..."
- Ranks 81–100: "An adjacent candidate..."

---

## Audit Results

| Check | Result |
|---|---|
| Honeypot candidates in top 100 | None triggered our detection checks |
| "Earning a top rank" or rank-mismatched language | Removed; rank-calibrated labels used throughout |
| Accomplishment sentence duplication | Non-template sentence extraction applied; first-sentence templates skipped |
| Unsupported skill/company/experience claims | No claims detected beyond what appears in each candidate's profile |
| Candidates with 90+ day notice in top 100 | Ranked lower relative to comparable candidates; concern noted in reasoning |
| Non-India candidates in top 100 | Country field checked; outside-India without relocation intent penalised |
| Score uniqueness | 68+ unique score values across 100 candidates |
| Format validation | Passed official `validate_submission.py` |

---

## File Structure

```
indiaruns/
├── rank.py                    # Core ranking + reasoning (single file, stdlib only)
├── submission.csv             # Final top-100 output
├── submission_metadata.yaml   # Portal metadata
├── requirements.txt           # Dependency manifest (stdlib only)
└── README.md                  # This file
```

---

## Reproduce Exact Submission

```bash
python rank.py \
  --candidates ./candidates.jsonl \
  --out ./submission.csv
```

Pre-computation required: **No**. The ranker runs end-to-end from raw `candidates.jsonl` in a single command. No embeddings, no model weights, no pre-built indexes.
