-- Schema for recruiting.db, the synthetic Northbeam Robotics recruiting database.
--
-- IDs are stable text keys such as JOB-2, APP-014, SC-031, EM-007, and TASK-012,
-- so tools can cite them directly. Timestamps are UTC text in the form
-- YYYY-MM-DDTHH:MM:SSZ, which sorts correctly and works with SQLite date functions.
-- JSON columns hold arrays or objects encoded as text.
-- The unit of analysis is the application: one candidate can apply to several jobs.

CREATE TABLE company (
    company_id TEXT PRIMARY KEY,
    name       TEXT NOT NULL,
    about      TEXT NOT NULL
);

CREATE TABLE teams (
    team_id TEXT PRIMARY KEY,
    name    TEXT NOT NULL UNIQUE
);

CREATE TABLE users (
    user_id TEXT PRIMARY KEY,
    name    TEXT NOT NULL,
    email   TEXT NOT NULL UNIQUE,
    role    TEXT NOT NULL CHECK (role IN ('admin', 'hr_manager', 'hr_user'))
);

-- Which teams each HR Manager is responsible for.
CREATE TABLE manager_teams (
    user_id TEXT NOT NULL REFERENCES users(user_id),
    team_id TEXT NOT NULL REFERENCES teams(team_id),
    PRIMARY KEY (user_id, team_id)
);

CREATE TABLE jobs (
    job_id            TEXT PRIMARY KEY,
    req_code          TEXT NOT NULL UNIQUE,
    title             TEXT NOT NULL,
    team_id           TEXT NOT NULL REFERENCES teams(team_id),
    location          TEXT NOT NULL,
    opened_at         TEXT NOT NULL,
    closed_at         TEXT,
    target_fill_days  INTEGER NOT NULL,
    hiring_manager    TEXT NOT NULL,
    status            TEXT NOT NULL CHECK (status IN ('open', 'filled', 'cancelled')),
    must_have_json    TEXT NOT NULL,
    nice_to_have_json TEXT NOT NULL,
    CHECK ((status = 'open') = (closed_at IS NULL))
);

-- The initial recruiter assignment for each job. Later reassignments are kept in
-- the app's separate writable change log, not in this read-only database.
CREATE TABLE job_assignments (
    job_id            TEXT PRIMARY KEY REFERENCES jobs(job_id),
    recruiter_user_id TEXT NOT NULL REFERENCES users(user_id),
    assigned_at       TEXT NOT NULL
);

CREATE TABLE candidates (
    candidate_id     TEXT PRIMARY KEY,
    full_name        TEXT NOT NULL,
    email            TEXT NOT NULL UNIQUE,
    phone            TEXT NOT NULL,
    location         TEXT NOT NULL,
    source           TEXT NOT NULL CHECK (source IN
        ('LinkedIn', 'Careers site', 'Referral', 'Job board', 'Agency')),
    years_experience INTEGER NOT NULL,
    current_title    TEXT NOT NULL,
    cv_text          TEXT NOT NULL
);

CREATE TABLE applications (
    application_id TEXT PRIMARY KEY,
    candidate_id   TEXT NOT NULL REFERENCES candidates(candidate_id),
    job_id         TEXT NOT NULL REFERENCES jobs(job_id),
    applied_at     TEXT NOT NULL,
    current_stage  TEXT NOT NULL CHECK (current_stage IN
        ('Applied', 'Recruiter Screen', 'Technical', 'Onsite', 'Offer', 'Hired')),
    status         TEXT NOT NULL CHECK (status IN
        ('active', 'rejected', 'withdrawn', 'hired', 'offer_declined')),
    outcome_reason TEXT,
    outcome_at     TEXT,
    UNIQUE (candidate_id, job_id),
    CHECK ((status = 'active') = (outcome_at IS NULL))
);

-- One row per stage an application entered. The current stage of an active
-- application has exited_at NULL. Hired is a final stage: its event closes at
-- the hire time with exit_type NULL.
CREATE TABLE stage_events (
    event_id       TEXT PRIMARY KEY,
    application_id TEXT NOT NULL REFERENCES applications(application_id),
    stage          TEXT NOT NULL CHECK (stage IN
        ('Applied', 'Recruiter Screen', 'Technical', 'Onsite', 'Offer', 'Hired')),
    entered_at     TEXT NOT NULL,
    exited_at      TEXT,
    exit_type      TEXT CHECK (exit_type IN ('advanced', 'rejected', 'withdrawn', 'offer_declined')
                               OR exit_type IS NULL),
    UNIQUE (application_id, stage)
);

-- Interviews happen in the Technical and Onsite stages. completed_at is NULL
-- when the interview has not taken place.
CREATE TABLE interviews (
    interview_id   TEXT PRIMARY KEY,
    application_id TEXT NOT NULL REFERENCES applications(application_id),
    stage          TEXT NOT NULL CHECK (stage IN ('Technical', 'Onsite')),
    interviewer    TEXT NOT NULL,
    scheduled_at   TEXT NOT NULL,
    completed_at   TEXT
);

CREATE TABLE scorecards (
    scorecard_id TEXT PRIMARY KEY,
    interview_id TEXT NOT NULL UNIQUE REFERENCES interviews(interview_id),
    interviewer  TEXT NOT NULL,
    submitted_at TEXT NOT NULL,
    overall      TEXT NOT NULL CHECK (overall IN ('strong_no', 'no', 'yes', 'strong_yes')),
    ratings_json TEXT NOT NULL,
    notes        TEXT NOT NULL
);

CREATE TABLE emails (
    email_id       TEXT PRIMARY KEY,
    application_id TEXT NOT NULL REFERENCES applications(application_id),
    direction      TEXT NOT NULL CHECK (direction IN ('inbound', 'outbound')),
    sent_at        TEXT NOT NULL,
    sender         TEXT NOT NULL,
    subject        TEXT NOT NULL,
    body           TEXT NOT NULL
);

-- Explicit to-dos. application_id is NULL for a task about the whole job.
CREATE TABLE tasks (
    task_id        TEXT PRIMARY KEY,
    application_id TEXT REFERENCES applications(application_id),
    job_id         TEXT NOT NULL REFERENCES jobs(job_id),
    owner_user_id  TEXT NOT NULL REFERENCES users(user_id),
    type           TEXT NOT NULL CHECK (type IN
        ('scorecard', 'reply', 'offer_follow_up', 'schedule', 'review', 'notify')),
    title          TEXT NOT NULL,
    due_at         TEXT NOT NULL,
    status         TEXT NOT NULL CHECK (status IN ('open', 'done')),
    created_at     TEXT NOT NULL,
    completed_at   TEXT,
    CHECK ((status = 'done') = (completed_at IS NOT NULL))
);

-- One row per sync run of each connected integration.
CREATE TABLE source_syncs (
    sync_id       TEXT PRIMARY KEY,
    integration   TEXT NOT NULL,
    started_at    TEXT NOT NULL,
    finished_at   TEXT NOT NULL,
    status        TEXT NOT NULL CHECK (status IN ('success', 'partial', 'failed')),
    records       INTEGER NOT NULL,
    error_message TEXT
);

-- Generation details: as_of, seed, generator_version, and data_hash.
CREATE TABLE meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE INDEX idx_applications_job ON applications(job_id);
CREATE INDEX idx_applications_candidate ON applications(candidate_id);
CREATE INDEX idx_stage_events_application ON stage_events(application_id);
CREATE INDEX idx_interviews_application ON interviews(application_id);
CREATE INDEX idx_emails_application ON emails(application_id);
CREATE INDEX idx_tasks_job ON tasks(job_id);
CREATE INDEX idx_source_syncs_integration ON source_syncs(integration, started_at);
