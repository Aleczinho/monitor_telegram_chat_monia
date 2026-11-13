import pytest

from app.formatting import github_link
from app.handlers import format_event
from app.models import GitHubPayload


def test_pull_request_message_escapes_untrusted_html(pull_request_payload):
    pull_request_payload["pull_request"]["title"] = "<img src=x onerror=alert(1)>"
    pull_request_payload["pull_request"]["user"]["login"] = "alice&bob"

    message = format_event(
        "pull_request",
        GitHubPayload.model_validate(pull_request_payload),
    )

    assert message is not None
    assert "&lt;img" in message
    assert "onerror=alert" in message
    assert "alice&amp;bob" in message
    assert "<img" not in message


def test_closed_pull_request_is_reported_as_merged_when_merged(pull_request_payload):
    pull_request_payload["action"] = "closed"
    pull_request_payload["pull_request"]["merged"] = True
    pull_request_payload["pull_request"]["merged_by"] = {"login": "reviewer"}

    message = format_event(
        "pull_request",
        GitHubPayload.model_validate(pull_request_payload),
    )

    assert message is not None
    assert "PULL REQUEST MERGED" in message
    assert "Merge realizado por:</b> @reviewer" in message
    assert "Fechada sem merge" not in message


def test_closed_pull_request_without_merge_is_not_reported_as_merged(pull_request_payload):
    pull_request_payload["action"] = "closed"
    pull_request_payload["pull_request"]["merged"] = False

    message = format_event(
        "pull_request",
        GitHubPayload.model_validate(pull_request_payload),
    )

    assert message is not None
    assert "PULL REQUEST FECHADA" in message
    assert "Fechada sem merge" in message
    assert "PULL REQUEST MERGED" not in message


def test_edit_without_title_or_body_change_is_ignored(pull_request_payload):
    pull_request_payload["action"] = "edited"
    pull_request_payload["changes"] = {"base": {"ref": {"from": "main"}}}

    assert format_event("pull_request", GitHubPayload.model_validate(pull_request_payload)) is None


@pytest.mark.parametrize(
    ("state", "expected"),
    [
        ("approved", "PULL REQUEST APROVADA"),
        ("changes_requested", "ALTERAÇÕES SOLICITADAS"),
        ("commented", "COMENTÁRIO DE REVISÃO"),
    ],
)
def test_review_states_are_formatted(pull_request_payload, state, expected):
    pull_request_payload["action"] = "submitted"
    pull_request_payload["review"] = {
        "state": state,
        "user": {"login": "reviewer"},
        "body": "<b>comentário</b>",
        "html_url": "https://github.com/healthdevio/projeto-itia-dois/pull/42#review",
    }

    message = format_event(
        "pull_request_review",
        GitHubPayload.model_validate(pull_request_payload),
    )

    assert message is not None
    assert expected in message
    assert "&lt;b&gt;comentário&lt;/b&gt;" in message


def test_dismissed_review_is_reported(pull_request_payload):
    pull_request_payload["action"] = "dismissed"
    pull_request_payload["review"] = {"state": "approved", "user": {"login": "reviewer"}}

    message = format_event(
        "pull_request_review",
        GitHubPayload.model_validate(pull_request_payload),
    )

    assert message is not None
    assert "REVISÃO DESCARTADA" in message


def test_issue_comment_only_notifies_pull_request_comments():
    payload = GitHubPayload.model_validate(
        {
            "repository": {"full_name": "healthdevio/projeto-itia-dois"},
            "action": "created",
            "issue": {"number": 12, "title": "Uma issue comum"},
            "comment": {"body": "texto", "user": {"login": "dev"}},
        }
    )
    assert format_event("issue_comment", payload) is None


def test_pull_request_comment_is_escaped():
    payload = GitHubPayload.model_validate(
        {
            "repository": {"full_name": "healthdevio/projeto-itia-dois"},
            "action": "created",
            "issue": {
                "number": 42,
                "title": "PR",
                "pull_request": {"url": "https://api.github.com/repos/example/pulls/42"},
            },
            "comment": {
                "body": "<script>alert(1)</script>",
                "html_url": "https://github.com/healthdevio/projeto-itia-dois/pull/42#issuecomment",
                "user": {"login": "reviewer"},
            },
        }
    )

    message = format_event("issue_comment", payload)

    assert message is not None
    assert "&lt;script&gt;" in message
    assert "<script>" not in message


@pytest.mark.parametrize(
    ("conclusion", "expected"),
    [
        ("success", "Sucesso"),
        ("failure", "Falha"),
        ("cancelled", "Cancelado"),
        ("neutral", "Neutro"),
        ("skipped", "Ignorado"),
        ("timed_out", "Tempo esgotado"),
        ("action_required", "Ação necessária"),
        ("startup_failure", "Falha ao iniciar"),
        ("stale", "Obsoleto"),
    ],
)
def test_workflow_conclusions_are_reported(conclusion, expected):
    payload = GitHubPayload.model_validate(
        {
            "repository": {"full_name": "healthdevio/projeto-itia-dois"},
            "action": "completed",
            "workflow_run": {
                "name": "CI",
                "html_url": "https://github.com/healthdevio/projeto-itia-dois/actions/runs/42",
                "status": "completed",
                "conclusion": conclusion,
                "head_branch": "develop",
                "run_number": 42,
            },
        }
    )

    message = format_event("workflow_run", payload)

    assert message is not None
    assert expected in message


def test_unsupported_event_and_action_are_ignored(pull_request_payload):
    payload = GitHubPayload.model_validate(pull_request_payload)
    assert format_event("push", payload) is None
    payload.action = "labeled"
    assert format_event("pull_request", payload) is None


def test_link_formatter_rejects_non_github_or_userinfo_urls():
    assert github_link("https://evil.example/path", "link") == ""
    assert github_link("https://user@github.com/path", "link") == ""
    assert github_link("http://github.com/path", "link") == ""
