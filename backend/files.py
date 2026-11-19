"""
Files router —— 浏览 NAS 目录、生成缩略图、预览/下载。

挂载到复盘后端同一个 FastAPI 实例，前缀 /files。
"""
from __future__ import annotations

import hashlib
import mimetypes
import os
from pathlib import Path
from typing import List

from fastapi import APIRouter, HTTPException, Query, Response
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from pydantic import BaseModel, Field

from ..config import settings

router = APIRouter(prefix="/files", tags=["files"])

# 根目录（NAS 挂载点，可通过环境变量覆盖）
NAS_ROOT = Path(os.environ.get("FILES_ROOT", "/mnt/nas")).resolve()

# 缩略图缓存目录（放在后端 data 下）
THUMB_CACHE = Path(os.environ.get("FILES_THUMB_CACHE", str(settings.DB_PATH.parent / "thumbs")))
THUMB_CACHE.mkdir(parents=True, exist_ok=True)

# 缩略图宽度
THUMB_W = 320

# 允许预览的文件大小上限（字节）
PREVIEW_MAX = 8 * 1024 * 1024  # 8 MB


# ---------- 数据结构 ----------

class FileInfo(BaseModel):
    name: str
    path: str                      # 从 NAS_ROOT 起的相对路径，用 / 分隔
    is_dir: bool
    size: int
    mtime: float
    mime: str
    thumb: str | None = None       # 缩略图 URL，无缩略图能力时为 null
    icon: str = Field("file")      # 图标 key


class Listing(BaseModel):
    current: str                    # 当前目录相对路径
    parent: str | None = None       # 父目录相对路径
    items: List[FileInfo]


# ---------- 辅助 ----------

IMG_EXT = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".tif", ".tiff", ".heic"}
PDF_EXT = {".pdf"}
VIDEO_EXT = {".mp4", ".mov", ".avi", ".mkv", ".m4v", ".webm"}
AUDIO_EXT = {".mp3", ".wav", ".flac", ".aac", ".ogg", ".m4a"}
TEXT_EXT = {".txt", ".md", ".json", ".csv", ".log", ".py", ".js", ".ts", ".html", ".css", ".xml", ".yaml", ".yml", ".ini", ".conf", ".sh"}


def resolve_safe(path_str: str) -> Path:
    """把用户传入的相对路径解析为绝对路径，禁止越权走出 NAS_ROOT。"""
    # 空 / "." 代表根目录
    if not path_str or path_str in (".", "/"):
        path_str = ""
    # 规范化路径，去除 .. 和多余分隔符
    target = (NAS_ROOT / path_str.lstrip("/")).resolve()
    # 必须在 NAS_ROOT 下
    try:
        target.relative_to(NAS_ROOT)
    except ValueError:
        raise HTTPException(status_code=400, detail="路径非法")
    return target


def rel(p: Path) -> str:
    try:
        return "/" + str(p.relative_to(NAS_ROOT)).replace(os.sep, "/")
    except ValueError:
        return "/"


def classify(p: Path) -> str:
    ext = p.suffix.lower()
    if ext in IMG_EXT:
        return "image"
    if ext in PDF_EXT:
        return "pdf"
    if ext in VIDEO_EXT:
        return "video"
    if ext in AUDIO_EXT:
        return "audio"
    if ext in TEXT_EXT:
        return "text"
    return "file"


def thumb_cache_key(p: Path) -> str | None:
    """返回缩略图缓存文件名；无缩略图能力返回 None。"""
    kind = classify(p)
    if kind not in ("image", "pdf"):
        return None
    h = hashlib.sha1()
    h.update(str(p).encode())
    h.update(str(p.stat().st_mtime_ns).encode())
    return f"{h.hexdigest()}.jpg"


def make_thumb(src: Path, dst: Path) -> None:
    """生成缩略图，失败时抛异常让上层捕获。"""
    kind = classify(src)
    from PIL import Image  # 延迟导入

    if kind == "image":
        # HEIC 需要 pillow-heif 注册
        try:
            import pillow_heif
            pillow_heif.register_heif_opener()
        except Exception:
            pass
        with Image.open(src) as im:
            im.thumbnail((THUMB_W, THUMB_W))
            if im.mode in ("RGBA", "LA"):
                im = im.convert("RGB")
            im.save(dst, "JPEG", quality=70, optimize=True)

    elif kind == "pdf":
        import fitz  # PyMuPDF
        doc = fitz.open(src)
        page = doc.load_page(0)
        pix = page.get_pixmap(width=THUMB_W, alpha=False)
        img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
        img.save(dst, "JPEG", quality=70, optimize=True)
        doc.close()


def file_info(p: Path) -> FileInfo:
    kind = classify(p)
    mime, _ = mimetypes.guess_type(str(p))
    mime = mime or ("application/pdf" if kind == "pdf" else "application/octet-stream")
    thumb_key = None if p.is_dir() else _thumb_key_for(p)
    thumb_url = f"/files/thumb/{thumb_key}" if thumb_key else None
    return FileInfo(
        name=p.name or str(p),
        path=rel(p),
        is_dir=p.is_dir(),
        size=p.stat().st_size if p.is_file() else 0,
        mtime=p.stat().st_mtime,
        mime=mime,
        thumb=thumb_url,
        icon="folder" if p.is_dir() else kind,
    )


# ---------- 路由 ----------

@router.get("", response_model=Listing)
@router.get("/", response_model=Listing)
def list_dir(path: str = Query("", alias="path")):
    target = resolve_safe(path)
    if not target.exists() or not target.is_dir():
        raise HTTPException(status_code=404, detail="目录不存在")

    items: List[FileInfo] = []
    try:
        with os.scandir(target) as it:
            entries = sorted(
                it,
                key=lambda e: (0 if e.is_dir() else 1, e.name.lower()),
            )
            for e in entries:
                if e.name.startswith("."):
                    continue
                items.append(file_info(Path(e.path)))
    except PermissionError:
        raise HTTPException(status_code=403, detail="权限不足")

    parent = rel(target.parent) if target != NAS_ROOT else None
    return Listing(current=rel(target), parent=parent, items=items)


_THUMB_LOCK = {}  # key -> Threading.Lock，防止并发重复生成


@router.get("/thumb/{key}")
def get_thumb(key: str):
    # 安全校验 key（sha1hex.jpg）
    if not key.endswith(".jpg"):
        raise HTTPException(status_code=400, detail="非法 key")
    cache_path = THUMB_CACHE / key
    if not cache_path.exists():
        # 没有缓存，遍历 NAS_ROOT 找对应源文件并生成
        src = _find_src_by_key(key)
        if src is None:
            raise HTTPException(status_code=404, detail="缩略图不存在")
        try:
            # 用文件锁防止并发生成
            import threading
            lock = _THUMB_LOCK.setdefault(key, threading.Lock())
            with lock:
                if not cache_path.exists():
                    make_thumb(src, cache_path)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"生成缩略图失败: {e}")
    return FileResponse(cache_path, media_type="image/jpeg")


def _find_src_by_key(key: str) -> Path | None:
    """把 key 还原回源文件路径——key 里存的是 sha1，我们拿不到原路径。
    所以改用另一种缓存文件名：key = sha1(path + mtime)，同时把原路径存一份映射。

    但更简单的做法：在 thumb_cache_key 里用 path 做 sha1，同时在缓存目录写一个 .index.json。
    这里简化处理：直接遍历找到第一个匹配（低效但启动时可以预生成；首次请求才生成时接受这个成本）。
    """
    # 重构：thumb_cache_key 改成 "hash.path_base.jpg" 不现实，还是保留 sha1。
    # 解决办法：用 key -> 源路径 的映射文件
    idx = THUMB_CACHE / ".index.json"
    import json
    import threading
    if idx.exists():
        try:
            data = json.loads(idx.read_text())
            src_str = data.get(key)
            if src_str:
                p = Path(src_str)
                if p.exists():
                    return p
        except Exception:
            pass
    return None


def _thumb_key_for(p: Path) -> str | None:
    """thumb_cache_key 的别名，同时更新映射索引。"""
    key = thumb_cache_key(p)
    if key is None:
        return None
    # 写入 key -> path 映射
    try:
        import json, threading
        idx = THUMB_CACHE / ".index.json"
        mapping = {}
        if idx.exists():
            mapping = json.loads(idx.read_text())
        mapping[key] = str(p)
        idx.write_text(json.dumps(mapping, ensure_ascii=False))
    except Exception:
        pass
    return key


@router.get("/pre", response_class=Response)
def preview(path: str = Query(...)):
    """返回文件本体（浏览器直接预览）。"""
    target = resolve_safe(path)
    if not target.exists() or not target.is_file():
        raise HTTPException(status_code=404, detail="文件不存在")
    mime, _ = mimetypes.guess_type(str(target))
    return FileResponse(target, media_type=mime or "application/octet-stream", filename=target.name)


@router.get("/dl")
def download(path: str = Query(...)):
    target = resolve_safe(path)
    if not target.exists() or not target.is_file():
        raise HTTPException(status_code=404, detail="文件不存在")
    return FileResponse(target, media_type="application/octet-stream", filename=target.name)


@router.get("/ui", response_class=HTMLResponse)
def ui():
    """单页前端。"""
    return _UI_HTML


# ---------- 前端页面（内联） ----------

_UI_HTML = r"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>文件浏览</title>
<style>
  * { box-sizing: border-box; }
  body { margin:0; font-family:-apple-system,BlinkMacSystemFont,"PingFang SC","Segoe UI",sans-serif; background:#f6f7f9; color:#222; }
  header { position:sticky; top:0; background:#fff; border-bottom:1px solid #eee; padding:10px 16px; z-index:10; }
  header .crumbs { font-size:14px; color:#555; word-break:break-all; }
  header .crumbs a { color:#0f62fe; text-decoration:none; }
  header .crumbs .sep { margin:0 4px; color:#bbb; }
  main { padding:12px; }
  .grid { display:grid; gap:10px; grid-template-columns:repeat(auto-fill,minmax(140px,1fr)); }
  .card { background:#fff; border-radius:10px; overflow:hidden; border:1px solid #eee; cursor:pointer; transition:transform .1s, box-shadow .1s; }
  .card:active { transform:scale(.98); }
  .thumb { aspect-ratio:4/3; background:#ececf0 center/cover no-repeat; display:flex; align-items:center; justify-content:center; font-size:48px; color:#999; }
  .thumb.folder { background:#ffd866; color:#a87500; font-size:36px; }
  .thumb.has-thumb { background:#ececf0; }
  .meta { padding:6px 8px; }
  .name { font-size:13px; line-height:1.35; word-break:break-all; display:-webkit-box; -webkit-line-clamp:2; -webkit-box-orient:vertical; overflow:hidden; }
  .size { font-size:11px; color:#999; margin-top:2px; }
  .empty { text-align:center; color:#999; padding:60px 20px; }
  .preview-mask { position:fixed; inset:0; background:rgba(0,0,0,.85); display:none; align-items:center; justify-content:center; z-index:100; }
  .preview-mask.show { display:flex; }
  .preview-mask img, .preview-mask video { max-width:95vw; max-height:92vh; object-fit:contain; }
  .preview-mask iframe { width:95vw; height:92vh; border:0; background:#fff; }
  .preview-mask .close { position:absolute; top:10px; right:16px; color:#fff; font-size:28px; cursor:pointer; }
  .preview-mask .dl-btn { position:absolute; top:14px; left:16px; background:#333; color:#fff; padding:6px 12px; border-radius:6px; text-decoration:none; font-size:14px; }
</style>
</head>
<body>
<header>
  <div class="crumbs" id="crumbs">加载中…</div>
</header>
<main>
  <div class="grid" id="grid"></div>
  <div class="empty" id="empty" style="display:none">目录为空</div>
</main>
<div class="preview-mask" id="mask">
  <a class="dl-btn" id="dlBtn" target="_blank" rel="noopener">下载</a>
  <span class="close" id="close">×</span>
  <div id="previewBox"></div>
</div>
<script>
const base = "/files";
let current = "";

function fmtSize(b){
  if (b<1024) return b+" B";
  if (b<1024*1024) return (b/1024).toFixed(1)+" KB";
  if (b<1024*1024*1024) return (b/1024/1024).toFixed(1)+" MB";
  return (b/1024/1024/1024).toFixed(2)+" GB";
}
function iconFor(c){ return {folder:"📁",image:"🖼️",pdf:"📕",video:"🎬",audio:"🎵",text:"📄",file:"📦"}[c]||"📦"; }

async function load(path){
  current = path;
  const q = path ? "?path="+encodeURIComponent(path) : "";
  const res = await fetch(base + q);
  const data = await res.json();
  render(data);
  history.replaceState(null,"",location.pathname + (current===""?"":("?p="+encodeURIComponent(current))));
}

function render(data){
  // 面包屑
  const crumbs = document.getElementById("crumbs");
  const parts = data.current.split("/").filter(Boolean);
  let html = `<a href="#" data-path="">📂 根目录</a>`;
  let acc = "";
  for (const p of parts){
    acc += "/" + p;
    html += `<span class="sep">/</span><a href="#" data-path="${encodeURIComponent(acc)}">${p}</a>`;
  }
  crumbs.innerHTML = html;
  crumbs.querySelectorAll("a").forEach(a => a.onclick = e => { e.preventDefault(); load(a.dataset.path); });

  // 网格
  const grid = document.getElementById("grid");
  const empty = document.getElementById("empty");
  if (data.items.length===0){ grid.innerHTML=""; empty.style.display=""; return; }
  empty.style.display = "none";
  grid.innerHTML = "";
  for (const f of data.items){
    const card = document.createElement("div");
    card.className = "card";
    const thumb = document.createElement("div");
    thumb.className = "thumb";
    if (f.is_dir){
      thumb.classList.add("folder");
      thumb.textContent = "📁";
    } else if (f.thumb){
      thumb.classList.add("has-thumb");
      thumb.style.backgroundImage = `url('${f.thumb}')`;
    } else {
      thumb.textContent = iconFor(f.icon);
    }
    const meta = document.createElement("div");
    meta.className = "meta";
    const name = document.createElement("div"); name.className="name"; name.textContent=f.name;
    const size = document.createElement("div"); size.className="size";
    if (f.is_dir){
      size.textContent = "文件夹";
    } else {
      size.textContent = fmtSize(f.size);
    }
    meta.appendChild(name); meta.appendChild(size);
    card.appendChild(thumb); card.appendChild(meta);
    card.onclick = () => {
      if (f.is_dir) load(f.path);
      else openPreview(f);
    };
    grid.appendChild(card);
  }
}

function openPreview(f){
  const box = document.getElementById("previewBox");
  box.innerHTML = "";
  const preUrl = base + "/pre?path=" + encodeURIComponent(f.path);
  const dlUrl = base + "/dl?path=" + encodeURIComponent(f.path);
  document.getElementById("dlBtn").href = dlUrl;
  const kind = f.icon;
  if (kind==="image"){
    const img = document.createElement("img"); img.src = preUrl; box.appendChild(img);
  } else if (kind==="video"){
    const v = document.createElement("video"); v.src = preUrl; v.controls=true; box.appendChild(v);
  } else if (kind==="audio"){
    const a = document.createElement("audio"); a.src = preUrl; a.controls=true; box.appendChild(a);
  } else if (kind==="pdf" || kind==="text"){
    const ifr = document.createElement("iframe"); ifr.src = preUrl; box.appendChild(ifr);
  } else {
    // 其他直接下载
    window.location.href = dlUrl;
    return;
  }
  document.getElementById("mask").classList.add("show");
}
document.getElementById("close").onclick = () => document.getElementById("mask").classList.remove("show");
document.getElementById("mask").onclick = (e) => { if (e.target.id==="mask") document.getElementById("mask").classList.remove("show"); };

// 初始路径
const url = new URL(location.href);
const initPath = url.searchParams.get("p") || "";
load(initPath);
</script>
</body>
</html>
"""
