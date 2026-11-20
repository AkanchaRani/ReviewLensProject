from collections import Counter, defaultdict

from pydantic import ValidationError

from .provider import ANALYSIS_PROMPT, GeminiUnavailableError
from .schema import ReviewResult

BATCH_SIZE = 5


async def analyse(rows, cache, provider):
    results = {}
    pending = []
    for row in rows:
        result = cache.get(row["key"])
        if result is None:
            pending.append(row)
        else:
            results[row["key"]] = result
    cached = len(results)
    for start in range(0, len(pending), BATCH_SIZE):
        batch = pending[start:start + BATCH_SIZE]
        unavailable = False
        for _ in range(2):
            if not batch:
                break
            try:
                output = await provider.generate(ANALYSIS_PROMPT, [r["review_text"] for r in batch])
            except GeminiUnavailableError:
                if not results:
                    raise
                unavailable = True
                break
            if not isinstance(output, list) or len(output) != len(batch):
                continue
            invalid = []
            for row, value in zip(batch, output):
                try:
                    analysis = ReviewResult.model_validate(value)
                except ValidationError:
                    invalid.append(row)
                    continue
                cache.put(row["key"], analysis)
                results[row["key"]] = analysis
            batch = invalid
        if unavailable:
            break
    return [
        {**row, "status": "analysed" if row["key"] in results else "analysis_failed",
         "analysis": results[row["key"]].analysis if row["key"] in results else None,
         "findings": results[row["key"]].findings if row["key"] in results else []}
        for row in rows
    ], cached


def dashboard(rows):
    counts = Counter()
    themes = defaultdict(lambda: defaultdict(list))
    needs_reply = matches = rated = 0
    for row in rows:
        findings = row["findings"]
        analysis = row["analysis"]
        if analysis is None:
            continue
        counts[analysis.sentiment] += 1
        needs_reply += analysis.needs_reply
        if row["rating"] is not None:
            rated += 1
            expected = ("negative", "negative", "neutral", "positive", "positive")[row["rating"] - 1]
            row["rating_mismatch"] = expected != analysis.sentiment
            matches += not row["rating_mismatch"]
        for finding in findings:
            themes[finding.sentiment][finding.topic].append(finding.evidence)

    def top(sentiment):
        return [{"topic": topic, "count": len(examples), "example": examples[0]}
                for topic, examples in sorted(themes[sentiment].items(), key=lambda item: (-len(item[1]), item[0]))[:3]]

    total = sum(counts.values())
    return {"total": total, "needs_reply": needs_reply,
            "sentiment": {name: round(100 * counts[name] / total, 1) if total else 0
                          for name in ("positive", "neutral", "negative")},
            "complaints": top("negative"), "praises": top("positive"),
            "agreement": round(matches * 100 / rated, 1) if rated else None}
