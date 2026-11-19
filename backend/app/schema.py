from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

Topic = Literal["quality", "delivery", "price", "packaging", "support", "size_fit", "other"]
Line = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=400, pattern=r"^[^\r\n]+$")]


class Analysis(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    sentiment: Literal["positive", "neutral", "negative"]
    topics: list[Topic] = Field(min_length=1, max_length=7)
    summary: Line
    needs_reply: bool


class TopicFinding(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    topic: Topic
    sentiment: Literal["positive", "neutral", "negative"]
    evidence: Line


class ReviewResult(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    analysis: Analysis
    findings: list[TopicFinding] = Field(min_length=1, max_length=7)

    @model_validator(mode="after")
    def match_topics(self):
        topics = {finding.topic for finding in self.findings}
        if len(topics) != len(self.findings) or topics != set(self.analysis.topics):
            raise ValueError("Provide exactly one finding for each analysis topic.")
        return self


class Reply(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    reply: Line
