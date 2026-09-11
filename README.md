# Chatbot RAG sobre mi Portfolio de GitHub
 
Un chatbot que responde preguntas sobre mis propios proyectos públicos en GitHub, usando **Retrieval-Augmented Generation (RAG)**.
 
**Enlace al Chatbot:** [chatbot-portfolio-co0v.onrender.com](https://chatbot-portfolio-co0v.onrender.com)
*(el plan gratuito de Render apaga el servicio tras 15 min de inactividad, por lo que la primera visita puede tardar unos segundos en cargar)*
 
---
## Estructura del repositorio
 
```
chatbot_portfolio/
├── app/
│   ├── main.py                  # FastAPI: sirve el frontend + endpoint /api/ask
│   └── rag.py                   # Lógica de retrieval + generación
├── static/
│   ├── index.html
│   ├── style.css
│   └── script.js
├── chroma_db/                   # Índice vectorial ya generado
├── RAG_chatbot_portfolio.ipynb  # Notebook de exploración e indexación inicial
├── sync_index.py                # Script de sincronización (usado por GitHub Actions)
├── requirements.txt
```

 
## Pipeline

El sistema **recupera** los fragmentos más relevantes de mis proyectos (README + notebooks) y usa un LLM para generar una respuesta fundamentada en ellos, citando siempre de qué proyecto viene la información, con enlace directo al repo.

1. **Indexación** (`Portfolio_RAG_Chatbot.ipynb` / `sync_index.py`)
   - Se listan todos mis repositorios públicos de GitHub vía su API
   - De cada uno se extrae el README y el contenido de sus notebooks (solo celdas markdown + librerías importadas en el código ya que el resto puede generar ruido)
   - El texto se trocea (*chunking*) por secciones, respetando los encabezados Markdown, en lugar de hacerlo por tamaño.
   - Cada chunk se convierte en un vector (*embedding*) con la API gratuita de **Google Gemini**
   - Los vectores se guardan en **ChromaDB**, una base de datos vectorial local y persistente
2. **Consulta** (app FastAPI)
   - La pregunta del usuario se convierte también en embedding
   - Se recuperan los `k` fragmentos más similares de ChromaDB (*retrieval*)
   - Esos fragmentos y la pregunta se pasan a Gemini, que genera la respuesta final (*generation*)
   - Se devuelven también las fuentes usadas, con enlace al repo correspondiente
3. **Automatización** (GitHub Actions)
   - Un workflow programado ejecuta `sync_index.py` periódicamente
   - Compara el hash de cada README/notebook con lo ya indexado, y solo reprocesa lo que cambió
   - Así el índice se mantiene al día sin intervención manual cada vez que actualizo un proyecto

## Stack técnico
 
| Componente | Tecnología |
|---|---|
| Embeddings | Google Gemini (`gemini-embedding-001`) |
| Generación de respuestas | Google Gemini (`gemini-3.6-flash`) |
| Base de datos vectorial | ChromaDB |
| Backend | FastAPI |
| Frontend | HTML / CSS / JavaScript vanilla |
| Automatización | GitHub Actions (cron) |
| Despliegue | Render |
 
>Se usa exclusivamente niveles gratuitos (Gemini API, ChromaDB local, GitHub Actions, Render Free).

 
