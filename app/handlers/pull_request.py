from app.formatting import escape_text, format_timestamp, github_link
from app.models import GitHubPayload

_ACTION_LABELS = {
    "opened": ("🟢 <b>NOVA PULL REQUEST</b>", "Aberta"),
    "reopened": ("🔄 <b>PULL REQUEST REABERTA</b>", "Reaberta"),
    "synchronize": ("🔧 <b>PULL REQUEST ATUALIZADA</b>", "Novos commits"),
    "ready_for_review": ("👀 <b>PR PRONTA PARA REVISÃO</b>", "Pronta para revisão"),
    "converted_to_draft": ("📝 <b>PR CONVERTIDA EM RASCUNHO</b>", "Rascunho"),
    "edited": ("✏️ <b>PULL REQUEST EDITADA</b>", "Editada"),
}


def format_pull_request(payload: GitHubPayload) -> str | None:
    action = payload.action
    pull_request = payload.pull_request
    if action is None or pull_request is None:
        return None
    if action == "edited" and not ({"title", "body"} & payload.changes.keys()):
        return None

    heading, status = _ACTION_LABELS.get(action, (None, None))
    timestamp = pull_request.updated_at or pull_request.created_at
    merged_by = ""

    if action == "closed":
        if pull_request.merged:
            heading = "🚀 <b>PULL REQUEST MERGED</b>"
            status = "Merge realizado com sucesso"
            timestamp = pull_request.merged_at or timestamp
            if pull_request.merged_by is not None:
                merged_by = (
                    f"\n👤 <b>Merge realizado por:</b> "
                    f"@{escape_text(pull_request.merged_by.login, 100)}"
                )
        else:
            heading = "🔒 <b>PULL REQUEST FECHADA</b>"
            status = "Fechada sem merge"
    elif heading is None:
        return None

    author = (
        f"@{escape_text(pull_request.user.login, 100)}"
        if pull_request.user is not None
        else "Não informado"
    )
    link = github_link(pull_request.html_url, "Visualizar Pull Request")
    link_line = f"\n\n{link}" if link else ""
    date_line = format_timestamp(timestamp)
    date_line = f"\n🕒 <b>Data:</b> {date_line}" if date_line else ""

    return (
        f"{heading}\n\n"
        f"📁 <b>Repositório:</b> {escape_text(payload.repository.full_name, 200)}\n"
        f"🔢 <b>PR:</b> #{pull_request.number}\n"
        f"📝 <b>Título:</b> {escape_text(pull_request.title, 500)}\n"
        f"👤 <b>Autor:</b> {author}{merged_by}\n\n"
        f"🌿 <b>Origem:</b> {escape_text(pull_request.head.ref, 200)}\n"
        f"🎯 <b>Destino:</b> {escape_text(pull_request.base.ref, 200)}\n"
        f"📌 <b>Status:</b> {status}{date_line}{link_line}"
    )
