from app.formatting import escape_text, github_link
from app.models import GitHubPayload


def format_issue_comment(payload: GitHubPayload) -> str | None:
    issue = payload.issue
    comment = payload.comment
    if payload.action != "created" or issue is None or comment is None:
        return None
    if issue.pull_request is None:
        return None

    author = (
        f"@{escape_text(comment.user.login, 100)}" if comment.user is not None else "Não informado"
    )
    comment_text = escape_text(comment.body)
    link = github_link(comment.html_url or issue.html_url, "Visualizar comentário")
    link_line = f"\n\n{link}" if link else ""

    return (
        f"💬 <b>NOVO COMENTÁRIO EM PULL REQUEST</b>\n\n"
        f"📁 <b>Repositório:</b> {escape_text(payload.repository.full_name, 200)}\n"
        f"🔢 <b>PR:</b> #{issue.number} — {escape_text(issue.title, 500)}\n"
        f"👤 <b>Autor:</b> {author}\n\n"
        f"{comment_text}{link_line}"
    )
