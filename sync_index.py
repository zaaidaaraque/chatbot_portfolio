"""
sync_index.py

Script standalone que sincroniza el índice RAG (ChromaDB) con el contenido
actual de los repositorios públicos de GitHub del usuario. 

Variables de entorno necesarias:
  GEMINI_API_KEY   -> API key gratuita de Google AI Studio
  GITHUB_TOKEN     -> token de GitHub con permiso de lectura sobre los repos          

Uso local:
  export GEMINI_API_KEY="..."
  export GITHUB_TOKEN="..."
  python sync_index.py
"""

import os
import re
import sys
import json
import time
import base64
import requests
import chromadb
import google.generativeai as genai
from google.api_core.exceptions import ResourceExhausted

# --- Configuración ---
GITHUB_USER = "zaaidaaraque"
EMBEDDING_MODEL = "models/gemini-embedding-001"
CHAT_MODEL = "gemini-3.6-flash" 
CHROMA_PATH = "./chroma_db"
COLLECTION_NAME = "portfolio_projects"
SECONDS_BETWEEN_CALLS = 0.7 

# --- Credenciales desde variables de entorno ---
gemini_api_key = os.environ.get("GEMINI_API_KEY")
github_token = os.environ.get("GITHUB_TOKEN")

if not gemini_api_key:
    print("ERROR: falta la variable de entorno GEMINI_API_KEY.")
    sys.exit(1)

genai.configure(api_key=gemini_api_key)
GITHUB_HEADERS = {"Authorization": f"token {github_token}"} if github_token else {}


# --- GitHub: listar repos, README y notebooks ---
def get_public_repos(username):
    repos = []
    page = 1
    while True:
        url = f"https://api.github.com/users/{username}/repos"
        params = {"per_page": 100, "page": page, "type": "owner"}
        resp = requests.get(url, headers=GITHUB_HEADERS, params=params)
        resp.raise_for_status()
        batch = resp.json()
        if not batch:
            break
        repos.extend(batch)
        page += 1
    return [r for r in repos if not r["fork"]]


def get_readme(repo_full_name):
    url = f"https://api.github.com/repos/{repo_full_name}/readme"
    resp = requests.get(url, headers=GITHUB_HEADERS)
    if resp.status_code != 200:
        return None, None
    data = resp.json()
    content = base64.b64decode(data["content"]).decode("utf-8", errors="ignore")
    return content, data["sha"]


def get_repo_notebooks(repo_full_name):
    for branch in ("main", "master"):
        url = f"https://api.github.com/repos/{repo_full_name}/git/trees/{branch}?recursive=1"
        resp = requests.get(url, headers=GITHUB_HEADERS)
        if resp.status_code == 200:
            tree = resp.json().get("tree", [])
            return [item["path"] for item in tree if item["path"].endswith(".ipynb")]
    return []


def get_file_content(repo_full_name, path):
    url = f"https://api.github.com/repos/{repo_full_name}/contents/{path}"
    resp = requests.get(url, headers=GITHUB_HEADERS)
    if resp.status_code != 200:
        return None, None
    data = resp.json()
    content = base64.b64decode(data["content"]).decode("utf-8", errors="ignore")
    return content, data["sha"]


# --- Extracción de contenido de notebooks ---
def extract_notebook_summary(notebook_json_text):
    try:
        nb_data = json.loads(notebook_json_text)
    except json.JSONDecodeError:
        return "", []

    markdown_parts = []
    imports = set()
    import_pattern = re.compile(r"^\s*(?:import|from)\s+([a-zA-Z0-9_\.]+)", re.MULTILINE)

    for cell in nb_data.get("cells", []):
        source = "".join(cell.get("source", []))
        if cell.get("cell_type") == "markdown":
            markdown_parts.append(source)
        elif cell.get("cell_type") == "code":
            imports.update(import_pattern.findall(source))

    markdown_text = "\n\n".join(markdown_parts)
    return markdown_text, sorted(imports)


# --- Chunking ---
def split_by_headers(text):
    pattern = r"(?=^#{1,3}\s)"
    sections = re.split(pattern, text, flags=re.MULTILINE)
    sections = [s.strip() for s in sections if s.strip()]
    return sections if sections else [text.strip()]


def build_chunks(projects):
    chunks = []
    for p in projects:
        sections = split_by_headers(p["readme"])
        for i, section in enumerate(sections):
            chunk_text = f"Proyecto: {p['name']}\n{p['description']}\n\n{section}"
            chunks.append({
                "id": f"{p['name']}__readme__{i}",
                "text": chunk_text,
                "metadata": {
                    "project": p["name"],
                    "url": p["url"],
                    "sha": p["sha"],
                    "source": "readme",
                }
            })

        libraries = p.get("libraries", [])
        if libraries:
            lib_text = (
                f"Proyecto: {p['name']}\n{p['description']}\n\n"
                f"Librerías y herramientas usadas en el código: {', '.join(libraries)}"
            )
            chunks.append({
                "id": f"{p['name']}__libraries",
                "text": lib_text,
                "metadata": {
                    "project": p["name"],
                    "url": p["url"],
                    "sha": p["sha"],
                    "source": "notebook_libraries",
                }
            })

        notebook_content = p.get("notebook_content", "")
        if notebook_content.strip():
            nb_sections = split_by_headers(notebook_content)
            for i, section in enumerate(nb_sections):
                chunk_text = f"Proyecto: {p['name']}\n{p['description']}\n\n{section}"
                chunks.append({
                    "id": f"{p['name']}__notebook__{i}",
                    "text": chunk_text,
                    "metadata": {
                        "project": p["name"],
                        "url": p["url"],
                        "sha": p["sha"],
                        "source": "notebook",
                    }
                })
    return chunks


# --- Embeddings (con rate limiting y reintentos) ---
def get_embedding(text, task_type="retrieval_document", max_retries=5):
    for attempt in range(max_retries):
        try:
            result = genai.embed_content(model=EMBEDDING_MODEL, content=text, task_type=task_type)
            return result["embedding"]
        except ResourceExhausted as e:
            wait = getattr(e, "retry_delay", None)
            wait_seconds = wait.seconds if wait else 5
            print(f"Límite de la API alcanzado, esperando {wait_seconds}s antes de reintentar...")
            time.sleep(wait_seconds + 1)
    raise RuntimeError("Se superó el número máximo de reintentos llamando a la API de embeddings.")


chroma_client = chromadb.PersistentClient(path=CHROMA_PATH)
collection = chroma_client.get_or_create_collection(name=COLLECTION_NAME)


def index_chunks(chunks):
    for i, chunk in enumerate(chunks):
        embedding = get_embedding(chunk["text"], task_type="retrieval_document")
        collection.upsert(
            ids=[chunk["id"]],
            embeddings=[embedding],
            documents=[chunk["text"]],
            metadatas=[chunk["metadata"]],
        )
        time.sleep(SECONDS_BETWEEN_CALLS)
        if (i + 1) % 10 == 0:
            print(f"Indexados {i + 1}/{len(chunks)} chunks...")


def get_indexed_shas():
    all_data = collection.get(include=["metadatas"])
    shas = {}
    for meta in all_data["metadatas"]:
        shas[meta["project"]] = meta["sha"]
    return shas


def sync_index():
    print(f"Recorriendo los repos públicos de {GITHUB_USER}...")
    current_repos = get_public_repos(GITHUB_USER)
    indexed_shas = get_indexed_shas()

    updated_projects = []
    for r in current_repos:
        content, sha = get_readme(r["full_name"])
        if not content:
            continue
        if indexed_shas.get(r["name"]) != sha:
            notebook_paths = get_repo_notebooks(r["full_name"])
            notebook_texts, all_imports = [], set()
            for path in notebook_paths:
                nb_content, _ = get_file_content(r["full_name"], path)
                if not nb_content:
                    continue
                md_text, imports = extract_notebook_summary(nb_content)
                all_imports.update(imports)
                if md_text.strip():
                    notebook_texts.append(f"### Notebook: {path}\n{md_text}")

            updated_projects.append({
                "name": r["name"],
                "full_name": r["full_name"],
                "description": r.get("description") or "",
                "url": r["html_url"],
                "readme": content,
                "sha": sha,
                "notebook_content": "\n\n".join(notebook_texts),
                "libraries": sorted(all_imports),
            })

    if not updated_projects:
        print("No hay cambios: el índice ya está actualizado.")
        return

    new_chunks = build_chunks(updated_projects)
    index_chunks(new_chunks)
    print(f"Actualizados {len(updated_projects)} proyecto(s): "
          f"{', '.join(p['name'] for p in updated_projects)}")


if __name__ == "__main__":
    sync_index()
