from app.formatting import escape_text, github_link
from app.models import GitHubPayload

_REVIEW_LABELS = {
    "approved": "✅ <b>PULL REQUEST APROVADA</b>",
    "changes_requested": "🛠️ <b>ALTERAÇÕES SOLICITADAS</b>",
    "commented": "💬 <b>COMENTÁRIO DE REVISÃO</b>",
}


def format_pull_request_review(payload: GitHubPayload) -> str | None:
    pull_request = payload.pull_request
    review = payload.review
    if pull_request is None or review is None:
        return None

    if payload.action == "dismissed":
        heading = "↩️ <b>REVISÃO DESCARTADA</b>"
        status = "Revisão descartada"
    elif payload.action == "submitted":
        heading = _REVIEW_LABELS.get(review.state.lower())
        if heading is None:
            return None
        status = escape_text(review.state.replace("_", " ").capitalize(), 100)
    else:
        return None

    reviewer = (
        f"@{escape_text(review.user.login, 100)}" if review.user is not None else "Não informado"
    )
    review_comment = ""
    if review.body and review.body.strip():
        review_comment = f"\n\n<b>Comentário:</b>\n{escape_text(review.body)}"

    link = github_link(
        review.html_url or pull_request.html_url,
        "Visualizar revisão",
    )
    link_line = f"\n\n{link}" if link else ""

    return (
        f"{heading}\n\n"
        f"📁 <b>Repositório:</b> {escape_text(payload.repository.full_name, 200)}\n"
        f"🔢 <b>PR:</b> #{pull_request.number} — {escape_text(pull_request.title, 500)}\n"
        f"👤 <b>Revisor:</b> {reviewer}\n"
        f"📌 <b>Status:</b> {status}"
        f"{review_comment}{link_line}"
    )
