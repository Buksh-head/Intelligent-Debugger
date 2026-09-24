"""FastAPI application entrypoint for the debugging assistant API.

Orchestrates the static analysis engine, sandboxed execution, and
hint generation service described in the project's C4 diagram
(spec/statement_of_work.md). Route definitions live in app.routers.
"""
from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers import analysis, execution, generation, instructor, analytics

app = FastAPI(title="Intelligent Debugging Assistant API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://intelligent-debugger.vercel.app", "http://localhost:5173"],  # Vite dev server
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(analysis.router)
app.include_router(execution.router)
app.include_router(generation.router)
app.include_router(instructor.router)
app.include_router(analytics.router)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
