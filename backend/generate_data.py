"""Build recruiting.db (SQLite) filled with synthetic recruiting data.

Everything here is made up: first names come from a fixed list, and there are
no emails, phone numbers or other personal data. random.seed(42) makes every
random choice the same on each run. Dates are measured back from AS_OF
(today at 09:00), so "the last 90 days" always ends today.

Usage:
    python generate_data.py            # writes recruiting.db next to this file
    python generate_data.py out.db     # writes to another path
"""

from __future__ import annotations

import random
import sqlite3
import sys
from datetime import date, datetime, time, timedelta
from pathlib import Path

SEED = 42
AS_OF = datetime.combine(date.today(), time(9, 0))
WINDOW_DAYS = 90
NUM_APPLICATIONS = 120
NUM_FILLED_JOBS = 3
NUM_STUCK = 10
STUCK_THRESHOLD_DAYS = 7

STAGES = ["Applied", "Recruiter Screen", "Technical", "Onsite", "Offer", "Hired"]

# Chance of moving on from each stage. Most candidates drop out early.
PASS_RATE = {
    "Applied": 0.45,
    "Recruiter Screen": 0.55,
    "Technical": 0.50,
    "Onsite": 0.45,
    "Offer": 0.75,
}

# How long a candidate stays in each stage, in days (min, max). Every max is
# under the 7-day threshold, so only the candidates we pick on purpose end up
# stuck.
STAGE_DAYS = {
    "Applied": (0.5, 5.0),
    "Recruiter Screen": (1.0, 5.0),
    "Technical": (2.0, 6.0),
    "Onsite": (2.0, 6.0),
    "Offer": (1.0, 5.0),
}

JOBS = [
    ("Senior Backend Engineer", "Engineering"),
    ("Firmware Engineer", "Engineering"),
    ("Data Platform Engineer", "Engineering"),
    ("Process Technician", "Fab Operations"),
    ("Equipment Maintenance Lead", "Fab Operations"),
    ("HR Business Partner", "People"),
    ("Partnerships Manager", "Business Development"),
    ("Account Executive", "Business Development"),
]

# Relative number of applicants per job (same order as JOBS).
JOB_WEIGHTS = [22, 14, 16, 18, 10, 8, 12, 20]

SOURCES = ["LinkedIn", "Careers Site", "Referral", "Job Board", "Agency"]
SOURCE_WEIGHTS = [35, 25, 15, 18, 7]

FIRST_NAMES = [
    "Avery", "Blake", "Casey", "Dakota", "Emerson", "Finley", "Gray", "Harper",
    "Indigo", "Jules", "Kai", "Lane", "Marlowe", "Nico", "Oakley", "Parker",
    "Quinn", "Reese", "Sage", "Tatum", "Umi", "Vale", "Wren", "Xen", "Yael",
    "Zion", "Arlo", "Bexley", "Cove", "Darby", "Ellis", "Fable", "Galen",
    "Hollis", "Ira", "Jory", "Kit", "Linden", "Merritt", "Noor", "Orrin",
    "Pax", "Rowan", "Shiloh", "Teagan", "Valen", "Winslow", "Yarrow", "Zephyr",
    "Ash", "Briar", "Cyan", "Del", "Eden", "Fern", "Gentry", "Haven", "Iris",
    "Jett", "Koa", "Lark", "Moss", "Nova", "Onyx", "Perrin", "Rain", "Sky",
    "True", "Vesper", "Wilder",
]

SCHEMA = """
CREATE TABLE jobs (
    job_id     INTEGER PRIMARY KEY,
    title      TEXT NOT NULL,
    team       TEXT NOT NULL,
    opened_at  TEXT NOT NULL,
    filled_at  TEXT
);

CREATE TABLE candidates (
    candidate_id INTEGER PRIMARY KEY,
    first_name   TEXT NOT NULL,
    source       TEXT NOT NULL
);

CREATE TABLE applications (
    application_id INTEGER PRIMARY KEY,
    candidate_id   INTEGER NOT NULL REFERENCES candidates(candidate_id),
    job_id         INTEGER NOT NULL REFERENCES jobs(job_id),
    current_stage  TEXT NOT NULL CHECK (current_stage IN
        ('Applied','Recruiter Screen','Technical','Onsite','Offer','Hired')),
    status         TEXT NOT NULL CHECK (status IN ('active','rejected','hired'))
);

CREATE TABLE stage_events (
    application_id INTEGER NOT NULL REFERENCES applications(application_id),
    stage          TEXT NOT NULL CHECK (stage IN
        ('Applied','Recruiter Screen','Technical','Onsite','Offer','Hired')),
    entered_at     TEXT NOT NULL,
    exited_at      TEXT,
    PRIMARY KEY (application_id, stage)
);

CREATE INDEX idx_applications_job ON applications(job_id);
CREATE INDEX idx_applications_status_stage ON applications(status, current_stage);
CREATE INDEX idx_stage_events_open ON stage_events(application_id) WHERE exited_at IS NULL;
"""


def ts(dt: datetime | None) -> str | None:
    return dt.strftime("%Y-%m-%d %H:%M:%S") if dt else None


def stage_duration(stage: str) -> timedelta:
    lo, hi = STAGE_DAYS[stage]
    return timedelta(days=random.uniform(lo, hi))


def simulate(applied_at: datetime, end: datetime, *, can_hire: bool,
             force_hire: bool = False):
    """Walk one application through the funnel until it is rejected, hired or
    still in progress at `end`.

    Returns (events, current_stage, status), where events is a list of
    (stage, entered_at, exited_at) and exited_at is None for the current stage.
    """
    events = []
    t = applied_at
    for stage in STAGES:
        if stage == "Hired":
            events.append((stage, t, None))
            return events, stage, "hired"

        exit_t = t + stage_duration(stage)
        if exit_t >= end and not force_hire:
            # Still in this stage when the clock stops.
            events.append((stage, t, None))
            return events, stage, "active"

        events.append((stage, t, exit_t))
        if force_hire:
            moves_on = True
        elif stage == "Offer" and not can_hire:
            moves_on = False  # offer declined, or the role went to someone else
        else:
            moves_on = random.random() < PASS_RATE[stage]

        if not moves_on:
            return events, stage, "rejected"
        t = exit_t
    raise AssertionError("unreachable")


def stuck_history(target: str, earliest: datetime):
    """Build the events for an active candidate who has sat in `target` for
    more than STUCK_THRESHOLD_DAYS. Returns None if the history would start
    before `earliest`."""
    stuck_days = random.uniform(STUCK_THRESHOLD_DAYS + 1, 24)
    entered_target = AS_OF - timedelta(days=stuck_days)
    prior = STAGES[: STAGES.index(target)]
    durations = [stage_duration(s) for s in prior]
    applied_at = entered_target - sum(durations, timedelta())
    if applied_at < earliest:
        return None

    events = []
    t = applied_at
    for stage, d in zip(prior, durations):
        events.append((stage, t, t + d))
        t += d
    events.append((target, entered_target, None))
    return events


def build(db_path: Path) -> dict[str, int]:
    random.seed(SEED)
    window_start = AS_OF - timedelta(days=WINDOW_DAYS)

    # Jobs. The filled ones are opened earlier so a hire has time to happen.
    filled_idx = set(random.sample(range(len(JOBS)), NUM_FILLED_JOBS))
    jobs = []
    for i, (title, team) in enumerate(JOBS):
        days_ago = random.randint(62, 88) if i in filled_idx else random.randint(45, 85)
        opened = (AS_OF - timedelta(days=days_ago)).replace(
            hour=random.randint(8, 17), minute=random.choice([0, 15, 30, 45]))
        jobs.append({"job_id": i + 1, "title": title, "team": team,
                     "opened_at": opened, "filled_at": None,
                     "filled": i in filled_idx})

    applications = []  # dicts: job_id, events, current_stage, status

    # 1) One hire for each filled job; the hire date becomes filled_at.
    for job in jobs:
        if not job["filled"]:
            continue
        applied = job["opened_at"] + timedelta(days=random.uniform(1, 10))
        events, stage, status = simulate(applied, AS_OF, can_hire=True, force_hire=True)
        job["filled_at"] = events[-1][1]
        applications.append({"job_id": job["job_id"], "events": events,
                             "current_stage": stage, "status": status})

    # 2) Candidates stuck in a stage, only on jobs that are still open.
    open_jobs = [j for j in jobs if not j["filled"]]
    stuck_targets = random.choices(
        ["Applied", "Recruiter Screen", "Technical", "Onsite", "Offer"],
        weights=[3, 3, 2, 1.5, 0.5], k=NUM_STUCK)
    for target in stuck_targets:
        while True:
            job = random.choice(open_jobs)
            events = stuck_history(target, max(job["opened_at"], window_start))
            if events:
                break
        applications.append({"job_id": job["job_id"], "events": events,
                             "current_stage": target, "status": "active"})

    # 3) Everyone else follows the normal funnel.
    remaining = NUM_APPLICATIONS - len(applications)
    job_picks = random.choices(jobs, weights=JOB_WEIGHTS, k=remaining)
    for job in job_picks:
        start = max(job["opened_at"], window_start)
        if job["filled"]:
            # Applicants before the role closed; anyone still in play when it
            # is filled gets closed out on that date.
            end = job["filled_at"]
            latest_apply = end - timedelta(days=1)
        else:
            end = AS_OF
            latest_apply = AS_OF - timedelta(hours=6)
        applied = start + (latest_apply - start) * random.random()
        events, stage, status = simulate(applied, end, can_hire=False)
        if job["filled"] and status == "active":
            s, entered, _ = events[-1]
            events[-1] = (s, entered, end)
            status = "rejected"
        applications.append({"job_id": job["job_id"], "events": events,
                             "current_stage": stage, "status": status})

    # Number applications in the order people applied.
    applications.sort(key=lambda a: a["events"][0][1])

    if db_path.exists():
        db_path.unlink()
    con = sqlite3.connect(db_path)
    try:
        con.executescript(SCHEMA)
        con.executemany(
            "INSERT INTO jobs VALUES (?, ?, ?, ?, ?)",
            [(j["job_id"], j["title"], j["team"], ts(j["opened_at"]), ts(j["filled_at"]))
             for j in jobs])

        for app_id, app in enumerate(applications, start=1):
            # One candidate per application.
            source = random.choices(SOURCES, weights=SOURCE_WEIGHTS)[0]
            con.execute("INSERT INTO candidates VALUES (?, ?, ?)",
                        (app_id, random.choice(FIRST_NAMES), source))
            con.execute("INSERT INTO applications VALUES (?, ?, ?, ?, ?)",
                        (app_id, app_id, app["job_id"], app["current_stage"], app["status"]))
            con.executemany(
                "INSERT INTO stage_events VALUES (?, ?, ?, ?)",
                [(app_id, stage, ts(entered), ts(exited))
                 for stage, entered, exited in app["events"]])
        con.commit()

        tables = ["jobs", "candidates", "applications", "stage_events"]
        return {t: con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in tables}
    finally:
        con.close()


def main() -> None:
    db_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).with_name("recruiting.db")
    counts = build(db_path)
    print(f"Wrote {db_path} (as of {ts(AS_OF)}, seed {SEED})")
    for table, n in counts.items():
        print(f"  {table:<13} {n:>4}")


if __name__ == "__main__":
    main()
