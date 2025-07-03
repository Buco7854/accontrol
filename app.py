import os
import sys
import asyncio
from contextlib import asynccontextmanager
from urllib.parse import urljoin, urlparse

import aiosqlite
import httpx
import uvicorn
import websockets
from dotenv import load_dotenv
from fastapi import (
    FastAPI, Request, HTTPException, Depends,
    WebSocket, WebSocketDisconnect
)
from fastapi.responses import StreamingResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

# --- Configuration (Unchanged) ---
load_dotenv()
BASE_DOMAIN = os.getenv('BASE_DOMAIN', 'localhost:8000')
# Ensure data directory exists
os.makedirs("data", exist_ok=True)
DATABASE = os.path.join('data', 'database.db')


@asynccontextmanager
async def lifespan(app: FastAPI):
    print("Lifespan: Startup")
    timeout = httpx.Timeout(10.0, read=None) # Increased connect timeout
    app.state.httpx_client = httpx.AsyncClient(timeout=timeout)
    # You might also want to initialize your DB schema here on first run
    yield
    print("Lifespan: Shutdown")
    await app.state.httpx_client.aclose()

app = FastAPI(lifespan=lifespan)
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

def get_httpx_client(request: Request) -> httpx.AsyncClient:
    return request.app.state.httpx_client


class SplitBase(BaseModel):
    name: str = Field(..., description="The unique subdomain name for the proxy.")
    label: str = Field(..., description="A user-friendly display label.")
    url: str = Field(..., description="The target URL to proxy to.")

class SplitInDB(SplitBase):
    id: int

async def get_db():
    db = await aiosqlite.connect(DATABASE)
    db.row_factory = aiosqlite.Row
    try:
        yield db
    finally:
        await db.close()

async def get_split_target_url(split_name: str) -> str | None:
    async with aiosqlite.connect(DATABASE) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute('SELECT url FROM splits WHERE name = ?', (split_name,))
        split = await cursor.fetchone()
    return split['url'] if split else None


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


@app.websocket("/{path:path}")
async def websocket_proxy(websocket: WebSocket, path: str):
    host = websocket.headers.get("host", "").split(':')[0]
    base_domain_name = BASE_DOMAIN.split(':')[0]

    if not host.endswith(f".{base_domain_name}"):
        await websocket.close(code=1008, reason="Invalid host for WebSocket proxy.")
        return

    split_name = host.removesuffix(f".{base_domain_name}")
    target_base_url = await get_split_target_url(split_name)

    if not target_base_url:
        await websocket.close(code=4004, reason=f"Subdomain proxy '{split_name}' not found.")
        return

    target_ws_url = urljoin(target_base_url, path).replace("http", "ws", 1)
    if websocket.url.query:
        target_ws_url += "?" + websocket.url.query

    await websocket.accept(subprotocol=websocket.scope.get('subprotocols', [None])[0])

    try:
        async with websockets.connect(target_ws_url, subprotocols=websocket.scope.get("subprotocols", [])) as upstream_ws:
            # This is the core of the proxy: two concurrent tasks to forward messages
            async def forward_client_to_upstream():
                while True:
                    data = await websocket.receive()
                    # `receive` raises WebSocketDisconnect, which is caught below
                    if "bytes" in data:
                        await upstream_ws.send(data["bytes"])
                    elif "text" in data:
                        await upstream_ws.send(data["text"])

            async def forward_upstream_to_client():
                while True:
                    message = await upstream_ws.recv()
                    # `recv` raises ConnectionClosedError, which is caught below
                    if isinstance(message, bytes):
                        await websocket.send_bytes(message)
                    elif isinstance(message, str):
                        await websocket.send_text(message)

            # Run both forwarding tasks concurrently until one of them fails
            await asyncio.gather(
                forward_client_to_upstream(),
                forward_upstream_to_client()
            )

    except (WebSocketDisconnect, websockets.exceptions.ConnectionClosedError, websockets.exceptions.ConnectionClosedOK):
        print(f"Connection closed for WebSocket proxy to '{split_name}'.")
    except Exception as e:
        print(f"An unexpected error occurred in WebSocket proxy for '{split_name}': {e}")
        await websocket.close(code=1011)


@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD"])
async def router_and_proxy(
    request: Request,
    path: str,
    client: httpx.AsyncClient = Depends(get_httpx_client)
):
    host = request.headers.get("host", "").split(':')[0]
    base_domain_name = BASE_DOMAIN.split(':')[0]

    # Serve the main page for the base domain
    if host == base_domain_name:
        return templates.TemplateResponse(
            "index.html",
            {"request": request, "base_domain": BASE_DOMAIN}
        )

    if host.endswith(f".{base_domain_name}"):
        split_name = host.removesuffix(f".{base_domain_name}")
        target_base_url = await get_split_target_url(split_name)

        if not target_base_url:
            raise HTTPException(status_code=404, detail=f"Subdomain proxy '{split_name}' not found.")

        target_url = urljoin(target_base_url, path)
        if request.url.query:
            target_url += "?" + request.url.query

        # We cleanly forward most headers, letting httpx handle host and content-length.
        headers_to_forward = {
            k: v for k, v in request.headers.items() if k.lower() not in ['host']
        }
        # Set the host header to match the target URL for services that require it
        headers_to_forward['host'] = urlparse(target_base_url).netloc

        req = client.build_request(
            method=request.method,
            url=target_url,
            headers=headers_to_forward,
            cookies=request.cookies,
            content=request.stream()
        )

        try:
            resp = await client.send(req, stream=True)

            # These headers are managed by the proxy server (Uvicorn) and should not be passed through.
            excluded_response_headers = {
                'content-encoding',
                'content-length',
                'transfer-encoding',
                'connection'
            }
            response_headers = {
                k: v for k, v in resp.headers.items() if k.lower() not in excluded_response_headers
            }

            return StreamingResponse(
                resp.aiter_raw(),
                status_code=resp.status_code,
                headers=response_headers,
                media_type=resp.headers.get('content-type')
            )
        except httpx.ConnectError:
            raise HTTPException(status_code=502, detail=f"Bad Gateway: Could not connect to '{split_name}'.")
        except httpx.RequestError as e:
            raise HTTPException(status_code=500, detail=f"Proxy error for {target_url}: {e}")

    raise HTTPException(status_code=400, detail="Invalid host")

if __name__ == "__main__":

    print(f"Access at http://{BASE_DOMAIN} or subdomains.")