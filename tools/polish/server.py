"""FastAPI server for the Reborn polish tool.

Run from this directory:
    uvicorn server:app --reload --port 8000

Then open http://localhost:8000
"""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import List

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from deepseek_client import DeepSeekError, polish_paragraph
from md_splitter import join, split, to_dicts, Block, PROSE

# Repo root = two parents up from this file (tools/polish/server.py -> repo root)
HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent.parent
BACKUP_DIR = HERE / ".backups"
STATIC_DIR = HERE / "static"

load_dotenv(HERE / ".env")

app = FastAPI(title="Reborn Polish")


def _resolve_md(name: str) -> Path:
    """Resolve a .md filename safely under REPO_ROOT (no traversal)."""
    if not name.endswith(".md"):
        raise HTTPException(400, "只允许 .md 文件")
    candidate = (REPO_ROOT / name).resolve()
    try:
        candidate.relative_to(REPO_ROOT)
    except ValueError:
        raise HTTPException(400, "非法路径")
    if candidate.parent != REPO_ROOT:
        raise HTTPException(400, "只允许仓库根目录下的 .md 文件")
    if not candidate.is_file():
        raise HTTPException(404, f"文件不存在：{name}")
    return candidate


@app.get("/api/files")
def list_files() -> dict:
    files = sorted(p.name for p in REPO_ROOT.glob("*.md"))
    return {"files": files}


@app.get("/api/file")
def read_file(name: str) -> dict:
    path = _resolve_md(name)
    text = path.read_text(encoding="utf-8")
    blocks = split(text)
    return {"name": name, "blocks": to_dicts(blocks)}


class PolishRequest(BaseModel):
    text: str


@app.post("/api/polish")
async def do_polish(req: PolishRequest) -> dict:
    if not req.text.strip():
        return {"polished": req.text, "issues": []}
    try:
        result = await polish_paragraph(req.text)
    except DeepSeekError as e:
        raise HTTPException(502, str(e))
    return result


class SaveBlock(BaseModel):
    id: int
    type: str
    text: str


class SaveRequest(BaseModel):
    name: str
    blocks: List[SaveBlock]


@app.post("/api/save")
def save_file(req: SaveRequest) -> dict:
    path = _resolve_md(req.name)

    # Sanity: the prose/skip type structure must match the on-disk file, so we
    # don't accidentally overwrite with corrupted content. We compare types and
    # the verbatim text of every SKIP block against a fresh split of the file.
    on_disk = split(path.read_text(encoding="utf-8"))
    if len(on_disk) != len(req.blocks):
        raise HTTPException(409, "文件已被修改（块数不一致），请重新加载。")
    for incoming, current in zip(req.blocks, on_disk):
        if incoming.type != current.type:
            raise HTTPException(409, "文件结构不一致，请重新加载。")
        if incoming.type != PROSE and incoming.text != current.text:
            raise HTTPException(409, "非正文块被修改，拒绝保存。请重新加载。")

    BACKUP_DIR.mkdir(exist_ok=True)
    ts = time.strftime("%Y%m%d-%H%M%S")
    backup = BACKUP_DIR / f"{req.name}.{ts}.bak"
    backup.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")

    new_text = join([Block(id=b.id, type=b.type, text=b.text) for b in req.blocks])
    path.write_text(new_text, encoding="utf-8")
    return {
        "ok": True,
        "backup": backup.name,
        "bytes": len(new_text.encode("utf-8")),
    }


# Static frontend at "/" — keep this last so /api/* takes precedence.
app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")


@app.exception_handler(404)
async def _spa_fallback(request, exc):  # noqa: ARG001
    index = STATIC_DIR / "index.html"
    if index.is_file() and not request.url.path.startswith("/api"):
        return FileResponse(index)
    raise exc
