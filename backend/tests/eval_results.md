# Eval results: 2026-11-06

**Pass rate: 10/10**

- **Setup:** each question in [eval_questions.md](eval_questions.md) was asked in a separate headless Claude Code session (`claude -p`, default model Sonnet 5.5).
- **Tools:** the session had only the `recruiting-pipeline` server. Built-in tools were off, so Claude couldn't read the database or the expected answers directly.
- **Timing:** the runs were at about 12:49, two hours after the expected answers were written down. That's why a few day counts are 0.1 higher.
- **Pass rule:** a question passes when every number in the expected answer is right and the answer uses the expected tool.

| # | Question | Tool called | Result | Notes |
|---|---|---|---|---|
| 1 | Stuck more than a week | `stuck_candidates(days=7)` | Pass | All 10 correct, in order. One summary bullet is muddled: it counts Noor (at Technical) among the Data Platform Engineer candidates stuck at Applied. |
| 2 | Stuck more than two weeks | `stuck_candidates(days=14)` | Pass | All 5 correct, with stages. |
| 3 | Waiting at Technical | `stuck_candidates()` | Pass | Noor 21.0 and Fable 13.8. Says it used the 7-day default. |
| 4 | Engineering Technical → Onsite | `pipeline_by_job()` | Pass | 50% (5 of 10) from the totals, with the per-role breakdown. Says it added up the three jobs itself. |
| 5 | Median time to fill, open jobs | `time_to_fill()` | Pass | 24.9 days and 5 open. Mentions the small sample. |
| 6 | Fastest team | `time_to_fill()` | Pass | Engineering at 23.6 days. Warns the gap over People is too small to mean much. |
| 7 | Biggest funnel drop | `pipeline_by_job()` | Pass | Applied → Recruiter Screen: 35.8%, 77 candidates lost. |
| 8 | Hire share, offers accepted | `pipeline_by_job()` | Pass | 2.5% hired. 3 of 4 offers accepted; the Equipment Maintenance Lead offer wasn't. |
| 9 | Account Executive pipeline | `pipeline_by_job()`, then `stuck_candidates()` | Pass | Funnel and 4 active candidates correct, including Oakley and Zephyr stuck. One sentence about "the other 2 of those 4" is garbled. |
| 10 | Marketing time to fill | `time_to_fill(team="Marketing")`, which returned an error | Pass | Says there's no Marketing team, lists the real teams, and doesn't guess. |
