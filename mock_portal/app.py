"""Mock land-registry portal (port 8100). Placeholder until v3."""

from fastapi import FastAPI

app = FastAPI(title="Mock Registry Portal (SYNTHETIC)")


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
