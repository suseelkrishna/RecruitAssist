"""The verifier: known-good answers pass, and known-bad answers fail the right check.

The tool outputs here are small hand-written fixtures, so the expected results
do not depend on the logic modules.
"""

from __future__ import annotations

from app.agent.verify import verify

RANKED = {
    "name": "score_candidates",
    "input": {"job_id": "JOB-2", "top_n": 3},
    "is_error": False,
    "output": {
        "job_id": "JOB-2",
        "as_of": "2026-11-09T17:00:00Z",
        "weights": {"scorecards": 0.5, "must_have": 0.3, "stage": 0.2},
        "ranked": [
            {"rank": 1, "application_id": "APP-068", "full_name": "Hollis Bellweather", "score": 0.9089,
             "components": {"scorecards": {"avg_points": 4.0, "evidence": ["SC-045", "SC-060"]}}},
            {"rank": 2, "application_id": "APP-067", "full_name": "Harper Oakhurst", "score": 0.8089,
             "components": {"scorecards": {"avg_points": 3.67, "evidence": ["SC-046"]}}},
            {"rank": 3, "application_id": "APP-065", "full_name": "Marlowe Sterling", "score": 0.72,
             "components": {"scorecards": {"avg_points": 3.33, "evidence": ["SC-044"]}}},
        ],
    },
}
TASKS = {
    "name": "pending_tasks",
    "input": {"job_id": "JOB-3"},
    "is_error": False,
    "output": {"count": 6, "overdue_count": 4,
               "tasks": [{"task_id": "TASK-011", "days_overdue": 3.8, "due_at": "2026-11-05T21:01:00Z"},
                         {"task_id": "TASK-017", "days_overdue": 2.2, "due_at": "2026-11-07T12:12:00Z"}]},
}

GOOD_RANKING = """\
| Rank | Candidate | Score |
|---|---|---|
| 1 | Hollis Bellweather [APP-068] | 0.91 |
| 2 | Harper Oakhurst [APP-067] | 0.81 |
| 3 | Marlowe Sterling [APP-065] | 0.72 |

Hollis averages 4.0 scorecard points [SC-045] [SC-060]. Scorecards carry 50% of the score.
People make the hiring decision."""


def test_grounded_ranking_passes():
    report = verify(GOOD_RANKING, [RANKED])
    assert report["passed"], report["failures"]
    assert report["checks"]["ranking"]["lists_checked"] == 1


def test_grounded_task_answer_with_declared_sum_and_percent_passes():
    answer = ("There are 6 open items on JOB-3 and 4 are overdue. TASK-011 is 3.8 days overdue (due "
              "2026-11-05) [TASK-011] and TASK-017 is 2.2 days overdue [TASK-017]. Together that is "
              "3.8 + 2.2 = 6 days in total. 4 of 6 items, about 66.7%, are overdue.")
    report = verify(answer, [TASKS], context={"as_of": "2026-11-09T17:00:00Z"})
    assert report["passed"], report["failures"]


def test_wrong_number_fails():
    answer = "There are 6 open items on JOB-3 and 5 are overdue [TASK-011]."
    report = verify(answer, [TASKS])
    assert not report["passed"]
    assert report["checks"]["numbers"]["unsupported"] == ["5"]
    assert report["checks"]["citations"]["passed"]


def test_wrong_declared_sum_fails():
    answer = "TASK-011 and TASK-017 add up to 3.8 + 2.2 = 7 days overdue [TASK-011] [TASK-017]."
    assert verify(answer, [TASKS])["checks"]["numbers"]["unsupported"] == ["7"]


def test_wrong_date_fails():
    answer = "TASK-011 was due on 2026-11-04 [TASK-011]."
    assert verify(answer, [TASKS])["checks"]["numbers"]["unsupported"] == ["2026-11-04"]


def test_fake_id_fails():
    answer = GOOD_RANKING.replace("[SC-060]", "[SC-999]")
    report = verify(answer, [RANKED])
    assert not report["passed"]
    assert report["checks"]["citations"]["unknown"] == ["SC-999"]


def test_reordered_ranking_fails():
    lines = GOOD_RANKING.splitlines()
    lines[2], lines[3] = lines[3].replace("| 2 |", "| 1 |"), lines[2].replace("| 1 |", "| 2 |")
    swapped = "\n".join(lines)
    report = verify(swapped, [RANKED])
    assert not report["passed"]
    assert not report["checks"]["ranking"]["passed"]
    assert "APP-067, APP-068" in report["failures"][0]


def test_ranking_by_name_only_is_still_checked():
    answer = "1. Marlowe Sterling\n2. Hollis Bellweather\n"
    assert not verify(answer, [RANKED])["checks"]["ranking"]["passed"]


def test_leaving_candidates_out_keeps_order():
    answer = "- Hollis Bellweather [APP-068]\n- Marlowe Sterling [APP-065]\n"
    assert verify(answer, [RANKED])["checks"]["ranking"]["passed"]


def test_leaked_email_and_phone_fail():
    answer = "Reach Hollis at hollis.b@example.com or 555-0142 [APP-068]."
    report = verify(answer, [RANKED])
    assert not report["passed"]
    assert report["checks"]["pii"]["found"] == 2
    assert "example.com" not in " ".join(report["failures"])


def test_masked_contact_passes():
    assert verify("Contact details are hidden: [email hidden] [APP-068].", [RANKED])["checks"]["pii"]["passed"]


def test_numbers_from_the_question_are_allowed():
    report = verify("Here are the top 3 [APP-068].", [RANKED], question="Who are the top 3 candidates?")
    assert report["checks"]["numbers"]["passed"]
