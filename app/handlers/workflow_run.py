from app.formatting import escape_text, github_link
from app.models import GitHubPayload

_CONCLUSION_LABELS = {
    "success": "Sucesso",
    "failure": "Falha",
    "cancelled": "Cancelado",
    "neutral": "Neutro",
    "skipped": "Ignorado",
    "timed_out": "Tempo esgotado",
    "action_required": "Ação necessária",
    "startup_failure": "Falha ao iniciar",
    "stale": "Obsoleto",
}

_ACTION_LABELS = {
    "requested": "⏳ <b>WORKFLOW SOLICITADO</b>",
    "in_progress": "🔄 <b>WORKFLOW EM EXECUÇÃO</b>",
}


def format_workflow_run(payload: GitHubPayload) -> str | None:
    workflow_run = payload.workflow_run
    action = payload.action
    if workflow_run is None or action is None:
        return None

    if action == "completed":
        heading = "🏁 <b>WORKFLOW CONCLUÍDO</b>"
        conclusion = workflow_run.conclusion
        status = (
            _CONCLUSION_LABELS.get(conclusion, "Resultado não reconhecido")
            if conclusion
            else "Resultado não informado"
        )
    else:
        heading = _ACTION_LABELS.get(action)
        if heading is None:
            return None
        status = "Solicitado" if action == "requested" else "Em execução"

    branch = (
        f"\n🌿 <b>Branch:</b> {escape_text(workflow_run.head_branch, 200)}"
        if workflow_run.head_branch
        else ""
    )
    run_number = (
        f"\n🔢 <b>Execução:</b> #{workflow_run.run_number}"
        if workflow_run.run_number is not None
        else ""
    )
    link = github_link(workflow_run.html_url, "Visualizar execução")
    link_line = f"\n\n{link}" if link else ""

    return (
        f"{heading}\n\n"
        f"📁 <b>Repositório:</b> {escape_text(payload.repository.full_name, 200)}\n"
        f"⚙️ <b>Workflow:</b> {escape_text(workflow_run.name, 300)}"
        f"{run_number}{branch}\n"
        f"📌 <b>Status:</b> {status}{link_line}"
    )
