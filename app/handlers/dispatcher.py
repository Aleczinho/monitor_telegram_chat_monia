from app.handlers.issue_comment import format_issue_comment
from app.handlers.pull_request import format_pull_request
from app.handlers.pull_request_review import format_pull_request_review
from app.handlers.workflow_run import format_workflow_run
from app.models import GitHubPayload

_HANDLERS = {
    "pull_request": format_pull_request,
    "pull_request_review": format_pull_request_review,
    "issue_comment": format_issue_comment,
    "workflow_run": format_workflow_run,
}


def format_event(event_type: str, payload: GitHubPayload) -> str | None:
    handler = _HANDLERS.get(event_type)
    if handler is None:
        return None
    return handler(payload)
