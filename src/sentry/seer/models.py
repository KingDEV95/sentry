from pydantic import BaseModel


class SummarizeIssueScores(BaseModel):
    possible_cause_confidence: float | None = None
    possible_cause_novelty: float | None = None
    is_fixable: bool | None = None
    fixability_score: float | None = None
    fixability_score_version: int | None = None


class SummarizeIssueResponse(BaseModel):
    group_id: str
    headline: str
    whats_wrong: str | None = None
    trace: str | None = None
    possible_cause: str | None = None
    scores: SummarizeIssueScores | None = None
