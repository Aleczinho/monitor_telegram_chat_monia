from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, HttpUrl


class GitHubModel(BaseModel):
    model_config = ConfigDict(extra="ignore")


class GitHubUser(GitHubModel):
    login: str


class GitHubRepository(GitHubModel):
    full_name: str


class BranchRef(GitHubModel):
    ref: str


class PullRequestData(GitHubModel):
    number: int
    title: str
    html_url: HttpUrl
    user: GitHubUser | None = None
    head: BranchRef
    base: BranchRef
    merged: bool = False
    merged_by: GitHubUser | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    merged_at: datetime | None = None


class IssueData(GitHubModel):
    number: int
    title: str
    html_url: HttpUrl | None = None
    pull_request: dict[str, Any] | None = None


class CommentData(GitHubModel):
    body: str
    html_url: HttpUrl | None = None
    user: GitHubUser | None = None


class ReviewData(GitHubModel):
    state: str
    body: str | None = None
    html_url: HttpUrl | None = None
    user: GitHubUser | None = None


class WorkflowRunData(GitHubModel):
    name: str
    html_url: HttpUrl
    head_branch: str | None = None
    head_sha: str | None = None
    status: str
    conclusion: str | None = None
    run_number: int | None = None


class GitHubPayload(GitHubModel):
    repository: GitHubRepository
    action: str | None = None
    changes: dict[str, Any] = Field(default_factory=dict)
    pull_request: PullRequestData | None = None
    issue: IssueData | None = None
    comment: CommentData | None = None
    review: ReviewData | None = None
    workflow_run: WorkflowRunData | None = None
