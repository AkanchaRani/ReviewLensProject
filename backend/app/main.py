import asyncio
import csv
import os
import time
from pathlib import Path

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, UploadFile
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, ValidationError

from .cache import Cache
from .clean import clean_csv
from .provider import Gemini, GeminiConfigurationError, GeminiUnavailableError, REPLY_PROMPT
from .schema import Reply
from .service import analyse, dashboard

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")
app = FastAPI(title="ReviewLens")
analysis_lock = asyncio.Lock()
MAX_BYTES = 1024 * 1024


class ReplyRequest(BaseModel):
    review_text: str = Field(min_length=1, max_length=100_000)


@app.post("/api/analyse")
async def upload(file: UploadFile):
    started = time.monotonic()
    data = await file.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise HTTPException(413, "Use a CSV file under 1 MiB.")
    try:
        rows, skipped = clean_csv(data)
    except (ValueError, csv.Error) as error:
        raise HTTPException(422, f"Could not read CSV: {error}") from error
    cache = Cache(os.getenv("REVIEWLENS_CACHE", ROOT / "data" / "analysis.sqlite3"))
    async with analysis_lock, httpx.AsyncClient(timeout=45) as client:
        provider = Gemini(client)
        try:
            results, cached = await analyse(rows, cache, provider)
        except (GeminiConfigurationError, GeminiUnavailableError) as error:
            raise HTTPException(503, str(error)) from error
    stats = dashboard(results)
    for row in results:
        del row["findings"]
    return {"reviews": results, "dashboard": stats, "skipped": skipped,
            "metrics": {"api_calls": provider.calls, "cached": cached,
                        "seconds": round(time.monotonic() - started, 2)}}


@app.post("/api/reply")
async def reply(request: ReplyRequest):
    async with httpx.AsyncClient(timeout=45) as client:
        provider = Gemini(client)
        for _ in range(2):
            try:
                return Reply.model_validate(await provider.generate(REPLY_PROMPT, request.model_dump()))
            except ValidationError:
                continue
            except (GeminiConfigurationError, GeminiUnavailableError) as error:
                raise HTTPException(503, str(error)) from error
    raise HTTPException(502, "Could not generate a reply. Please try again.")

@app.get("/api/health")
async def health():
    return {"status": "ok"}


static_dir = os.getenv("REVIEWLENS_STATIC_DIR")
if static_dir:
    app.mount("/", StaticFiles(directory=static_dir, html=True), name="dashboard")
