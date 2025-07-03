import os
import sys

import httpx
import aiosqlite
from urllib.parse import urljoin, urlparse
from dotenv import load_dotenv

# NEW: Import StreamingResponse along with other response types
from fastapi import FastAPI, Request, HTTPException, Depends
from fastapi.responses import StreamingResponse, Response  # Add StreamingResponse here
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

# --- Configuration (Unchanged) ---
load_dotenv()
BASE_DOMAIN = os.getenv('BASE_DOMAIN', 'localhost:8000')
DATABASE = os.path.join('data', 'database.db')

# --- FastAPI App Initialization (Unchanged) ---
app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# --- Pydantic Data Models (Unchanged) ---
class SplitBase(BaseModel):
    name: str = Field(..., description="The unique subdomain name for the proxy.")
    label: str = Field(..., description="A user-friendly display label.")
    url: str = Field(..., description="The target URL to proxy to.")

class SplitInDB(SplitBase):
    id: int

# --- Database & HTTPX Client Dependencies (Unchanged) ---
async def get_db():
    db = await aiosqlite.connect(DATABASE)
    db.row_factory = aiosqlite.Row
    try:
        yield db
    finally:
        await db.close()

_httpx_client = None

@app.on_event("startup")
async def startup_event():
    global _httpx_client
    timeout = httpx.Timeout(5.0, read=None)
    _httpx_client = httpx.AsyncClient(timeout=timeout)

@app.on_event("shutdown")
async def shutdown_event():
    await _httpx_client.aclose()

def get_httpx_client():
    return _httpx_client

# --- API Routes (Unchanged and Correct) ---
@app.get("/api/splits", response_model=list[SplitInDB])
async def get_splits(db: aiosqlite.Connection = Depends(get_db)):
    cursor = await db.execute('SELECT id, name, label, url FROM splits ORDER BY label')
    rows = await cursor.fetchall()
    return [dict(row) for row in rows]

@app.post("/api/splits", response_model=SplitInDB, status_code=201)
async def add_split(split: SplitBase, db: aiosqlite.Connection = Depends(get_db)):
    try:
        cursor = await db.execute("INSERT INTO splits (name, label, url) VALUES (?, ?, ?)",
                                  (split.name, split.label, split.url))
        await db.commit()
        return SplitInDB(id=cursor.lastrowid, **split.dict())
    except aiosqlite.IntegrityError:
        raise HTTPException(status_code=409, detail="A split with this name already exists.")

@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD"])
async def router_and_proxy(request: Request, path: str):
    host = request.headers.get("host", "").split(':')[0]
    base_domain_name = BASE_DOMAIN.split(':')[0]

    if host == base_domain_name:
        return templates.TemplateResponse(
            "index.html",
            {"request": request, "base_domain": BASE_DOMAIN}
        )

    if host.endswith(f".{base_domain_name}"):
        split_name = host.removesuffix(f".{base_domain_name}")

        async with aiosqlite.connect(DATABASE) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute('SELECT url FROM splits WHERE name = ?', (split_name,))
            split = await cursor.fetchone()

        if not split:
            raise HTTPException(status_code=404, detail=f"Subdomain proxy '{split_name}' not found.")

        target_url = urljoin(split['url'], path)
        if request.url.query:
            target_url += "?" + request.url.query

        client = get_httpx_client()

        #--- THE FIX IS HERE ---
        # Explicitly remove the 'connection' header to prevent the upstream
        # connection from being prematurely closed.
        excluded_incoming_headers = {'host', 'connection'}
        req_headers = {
            key: value for key, value in request.headers.items()
            if key.lower() not in excluded_incoming_headers
        }
        req_headers['host'] = urlparse(target_url).netloc

        req = client.build_request(
            method=request.method,
            url=target_url,
            headers=req_headers,
            cookies=request.cookies,
            content=request.stream()
        )

        try:
            resp = await client.send(req, stream=True)

            async def stream_generator():
                async for chunk in resp.aiter_raw():
                    yield chunk

            response_headers = [(name, value) for (name, value) in resp.headers.items() if name.lower() not in ('transfer-encoding', 'connection', 'content-length', 'content-encoding')]

            return StreamingResponse(
                content=stream_generator(),
                status_code=resp.status_code,
                headers=dict(response_headers)
            )
        except httpx.RequestError as e:
            raise HTTPException(status_code=502, detail=f"Proxy error for {target_url}: {e}")

    raise HTTPException(status_code=400, detail="Invalid host")