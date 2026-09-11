"""
Lógica de retrieval + generación (RAG) sobre el índice ya construido en ChromaDB.

Este módulo NO indexa nada — asume que ./chroma_db ya existe (generado por el
notebook Portfolio_RAG_Chatbot.ipynb o por sync_index.py). Solo se encarga de
responder preguntas.
"""

import os
import time
import chromadb
import google.generativeai as genai
from google.api_core.exceptions import ResourceExhausted

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
EMBEDDING_MODEL = "models/gemini-embedding-001"
CHAT_MODEL = "gemini-3.6-flash"
CHROMA_PATH = os.environ.get("CHROMA_PATH", "./chroma_db")
COLLECTION_NAME = "portfolio_projects"

if not GEMINI_API_KEY:
    raise RuntimeError(
        "Falta la variable de entorno GEMINI_API_KEY. "
        "Crea un archivo .env (ver .env.example) o expórtala en tu shell."
    )

genai.configure(api_key=GEMINI_API_KEY)

_chroma_client = chromadb.PersistentClient(path=CHROMA_PATH)
_collection = _chroma_client.get_or_create_collection(name=COLLECTION_NAME)
_gemini_model = genai.GenerativeModel(CHAT_MODEL)

SYSTEM_PROMPT = (
    "Eres un asistente que responde preguntas sobre los proyectos de Data Science "
    "de Zaida, basándote ÚNICAMENTE en el contexto proporcionado. "
    "Si la respuesta no está en el contexto, dilo claramente en vez de inventar. "
    "Cuando menciones un proyecto, indica su nombre."
)


def get_embedding(text: str, task_type: str = "retrieval_query", max_retries: int = 5) -> list[float]:
    for _ in range(max_retries):
        try:
            result = genai.embed_content(model=EMBEDDING_MODEL, content=text, task_type=task_type)
            return result["embedding"]
        except ResourceExhausted as e:
            wait = getattr(e, "retry_delay", None)
            wait_seconds = wait.seconds if wait else 5
            time.sleep(wait_seconds + 1)
    raise RuntimeError("Se superó el número máximo de reintentos llamando a la API de embeddings.")


def retrieve(question: str, k: int = 4) -> list[dict]:
    if _collection.count() == 0:
        return []
    query_embedding = get_embedding(question, task_type="retrieval_query")
    results = _collection.query(query_embeddings=[query_embedding], n_results=min(k, _collection.count()))
    return [
        {"text": doc, "metadata": meta}
        for doc, meta in zip(results["documents"][0], results["metadatas"][0])
    ]


def ask(question: str, k: int = 4) -> dict:
    """Devuelve {'answer': str, 'sources': [{'project', 'url'}]}"""
    retrieved = retrieve(question, k=k)

    if not retrieved:
        return {
            "answer": "El índice todavía está vacío. Ejecuta el notebook o sync_index.py para indexar los proyectos primero.",
            "sources": [],
        }

    context = "\n\n---\n\n".join(r["text"] for r in retrieved)
    prompt = f"{SYSTEM_PROMPT}\n\nContexto:\n{context}\n\nPregunta: {question}"

    response = _gemini_model.generate_content(prompt)
    answer = response.text

    seen = set()
    sources = []
    for r in retrieved:
        project = r["metadata"]["project"]
        if project not in seen:
            seen.add(project)
            sources.append({"project": project, "url": r["metadata"]["url"]})

    return {"answer": answer, "sources": sources}
