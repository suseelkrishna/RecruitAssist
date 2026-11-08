# Eval questions for the recruiting-pipeline MCP server

Ask Claude each question in a session where `recruiting-pipeline` is connected, then
compare its answer to the expected answer. "Tool" is the call a good answer should
rely on.

**About dates.** These answers come from the data as generated on **2026-11-06**
and checked at about 10:50 that morning. `generate_data.py` measures every date
back from today at 09:00, and the seed keeps everything else the same. So on any
later day, run `python generate_data.py` first and these answers still hold.
Days in stage are measured against the current time, so they can run up to about
0.5 day higher if you ask later in the day.

---

### 1. Which candidates have been stuck in a stage for more than a week?

**Tool:** `stuck_candidates(days=7)`

**Expected:** 10 candidates, longest first:

| Candidate | Job | Stage | Days |
|---|---|---|---|
| Oakley | Account Executive | Recruiter Screen | 22.1 |
| Moss | Equipment Maintenance Lead | Applied | 21.6 |
| Noor | Data Platform Engineer | Technical | 21.0 |
| Avery | Data Platform Engineer | Applied | 17.8 |
| Nova | Process Technician | Applied | 16.6 |
| Fable | Equipment Maintenance Lead | Technical | 13.8 |
| Ellis | Partnerships Manager | Applied | 12.4 |
| Lark | Data Platform Engineer | Applied | 11.7 |
| Zephyr | Account Executive | Applied | 11.6 |
| Emerson | Process Technician | Applied | 10.7 |

### 2. Who has been stuck for more than two weeks, and in which stage?

**Tool:** `stuck_candidates(days=14)`

**Expected:** 5 candidates: Oakley (Recruiter Screen, 22.1), Moss (Applied, 21.6),
Noor (Technical, 21.0), Avery (Applied, 17.8), Nova (Applied, 16.6).

### 3. Is anyone waiting at the Technical stage too long?

**Tool:** `stuck_candidates(days=7)`, filtered to the Technical stage

**Expected:** 2 candidates: Noor (Data Platform Engineer, 21.0 days) and Fable
(Equipment Maintenance Lead, 13.8 days).

### 4. What's the Technical to Onsite conversion for Engineering roles?

**Tool:** `pipeline_by_job()`, summing the three Engineering jobs

**Expected:** **50%** overall (5 of 10 reached Onsite).

| Role | Technical | Onsite | Conversion |
|---|---|---|---|
| Senior Backend Engineer | 4 | 1 | 25.0% |
| Firmware Engineer | 4 | 3 | 75.0% |
| Data Platform Engineer | 2 | 1 | 50.0% |

A good answer says the numbers are small. Watch for a wrong answer that averages
the three percentages (50.0%, which matches here only by luck) instead of using the
totals.

### 5. What's our median time to fill, and how many jobs are still open?

**Tool:** `time_to_fill()`

**Expected:** median **24.9 days** (average 24.1) across 3 filled jobs; **5 jobs open**.

### 6. Which team fills roles fastest?

**Tool:** `time_to_fill()`

**Expected:** Engineering, with a median of 23.6 days across 2 filled roles
(Senior Backend Engineer 17.2 days, Firmware Engineer 30.0 days). People is next at
24.9 days (1 role). Business Development and Fab Operations haven't filled a role
yet, so they have no time to fill. A good answer says these sample sizes are tiny.

### 7. Where in the funnel do we lose the most candidates?

**Tool:** `pipeline_by_job()`, the `all_jobs` funnel

**Expected:** Applied to Recruiter Screen: only 35.8% move on (43 of 120). The
full funnel is 120 → 43 (35.8%) → 24 (55.8%) → 11 (45.8%) → 4 (36.4%) → 3 hired
(75.0%).

### 8. What share of applicants end up hired, and how many offers were accepted?

**Tool:** `pipeline_by_job()`

**Expected:** 3 of 120 applicants hired (2.5%). 4 offers were made and 3 accepted
(75%). The one that wasn't was for Equipment Maintenance Lead.

### 9. How does the Account Executive pipeline look?

**Tool:** `pipeline_by_job(job_id=8)`

**Expected:** 21 applied → 10 Recruiter Screen (47.6%) → 6 Technical (60.0%) →
2 Onsite (33.3%) → 0 Offer. The role is still open. 4 candidates are active:
2 at Applied, 1 at Recruiter Screen and 1 at Technical. Two of them are stuck:
Oakley (Recruiter Screen, 22.1 days) and Zephyr (Applied, 11.6 days).

### 10. What's the time to fill for the Marketing team?

**Tool:** `time_to_fill(team="Marketing")`, which returns an error

**Expected:** Claude should say there is no Marketing team in the data and list
the real teams: Business Development, Engineering, Fab Operations and People. A
wrong answer makes up a number.
