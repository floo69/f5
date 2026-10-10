from fastapi import FastAPI

app = FastAPI(title="ThumbShield API")


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
