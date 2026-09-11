import os
from pathlib import Path

from dotenv import load_dotenv

# Cargar variables de entorno desde .env ANTES de importar rag (que las necesita al arrancar)
load_dotenv()

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app.rag import ask as rag_ask

app = FastAPI(title="Catálogo de Proyectos — Chatbot RAG")

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"


class Question(BaseModel):
    question: str


class SourceItem(BaseModel):
    project: str
    url: str


class Answer(BaseModel):
    answer: str
    sources: list[SourceItem]


@app.post("/api/ask", response_model=Answer)
def api_ask(payload: Question):
    result = rag_ask(payload.question)
    return result


@app.get("/")
def serve_index():
    return FileResponse(STATIC_DIR / "index.html")


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
