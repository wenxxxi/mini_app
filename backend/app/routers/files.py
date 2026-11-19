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
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel, Field

from .. import config

router = APIRouter(prefix="/files", tags=["files"])

# 根目录（NAS 挂载点，可通过环境变量覆盖）
NAS_ROOT = Path(os.environ.get("FILES_ROOT", "/mnt/nas")).resolve()

# 缩略图缓存目录（放在后端 data 下）
_THUMB_DEFAULT = str(Path(config.DB_PATH).parent / "thumbs")
THUMB_CACHE = Path(os.environ.get("FILES_THUMB_CACHE", _THUMB_DEFAULT))
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
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="default">
<title>文件</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<style>
/* ========= iOS Files 风格 ========= */
*{box-sizing:border-box;-webkit-tap-highlight-color:transparent}
html,body{margin:0;padding:0;height:100%;overflow:hidden}
body{
  font-family:-apple-system,BlinkMacSystemFont,"SF Pro Text","PingFang SC","Helvetica Neue",sans-serif;
  background:#f2f2f7;color:#000;
  font-size:17px;line-height:1.42;
  display:flex;flex-direction:column;
}

/* 顶部导航栏（iOS UINavigationBar 风格）*/
.nav{
  position:sticky;top:0;z-index:20;
  background:rgba(242,242,247,.85);
  backdrop-filter:saturate(180%) blur(20px);
  -webkit-backdrop-filter:saturate(180%) blur(20px);
  border-bottom:.5px solid rgba(60,60,67,.29);
  padding-top:env(safe-area-inset-top);
}
.nav-bar{
  display:flex;align-items:center;min-height:44px;
  padding:0 12px;position:relative;
}
.nav-bar .back{
  display:flex;align-items:center;gap:2px;
  color:#007aff;font-size:17px;font-weight:400;
  padding:8px 4px 8px 0;min-height:36px;
  text-decoration:none;cursor:pointer;
  border:none;background:none;
  transition:opacity .15s;
}
.nav-bar .back:active{opacity:.5}
.nav-bar .back .chevron{
  width:12px;height:20px;position:relative;
}
.nav-bar .back .chevron::before,.nav-bar .back .chevron::after{
  content:"";position:absolute;left:2px;width:12px;height:2px;
  background:#007aff;border-radius:2px;transform-origin:left center;
}
.nav-bar .back .chevron::before{top:6px;transform:rotate(45deg)}
.nav-bar .back .chevron::after{top:12px;transform:rotate(-45deg)}
.nav-bar .title{
  flex:1;text-align:center;font-size:17px;font-weight:600;
  color:#000;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;
  padding:0 8px;
}
.nav-bar .right{
  min-width:44px;display:flex;justify-content:flex-end;
}

/* 内容区（可滚动）*/
.scroll{
  flex:1;overflow-y:auto;-webkit-overflow-scrolling:touch;
  padding-bottom:env(safe-area-inset-bottom);
}

/* iOS 列表（UITableView 风格）*/
.list{margin:0;background:#fff}
.section{margin-top:24px}
.section:first-child{margin-top:0}
.section-header{
  text-transform:uppercase;font-size:13px;font-weight:600;
  color:#6d6d72;padding:0 16px 6px;
}
.section-header.empty-hint{text-align:center;text-transform:none;color:#8e8e93;font-size:15px;padding-top:80px}

.row{
  display:flex;align-items:center;gap:12px;
  padding:10px 16px;min-height:56px;
  border-bottom:.5px solid rgba(60,60,67,.12);
  cursor:pointer;position:relative;
  transition:background .1s;
}
.row:active{background:rgba(120,120,128,.12)}
.row:last-child{border-bottom:none}
.row.has-parent{padding-left:4px}

/* 左侧图标容器 */
.row-icon{
  width:32px;height:32px;border-radius:6px;flex-shrink:0;
  display:flex;align-items:center;justify-content:center;
  font-size:20px;color:#fff;font-weight:600;
  overflow:hidden;background:#c7c7cc;
}
.row-icon.folder{background:#ff9500}
.row-icon.image{background:#5ac8fa}
.row-icon.pdf{background:#ff3b30}
.row-icon.video{background:#af52de}
.row-icon.audio{background:#ff2d55}
.row-icon.text{background:#8e8e93}
.row-icon.has-thumb{padding:0}
.row-icon.has-thumb img{width:100%;height:100%;object-fit:cover;border-radius:6px}

/* SF Symbol 替代：用 CSS 画简单文件图标 */
.row-icon .sym{
  font-size:17px;line-height:1;color:#fff;font-weight:400;
}
.row-icon.folder .sym{content:"📁"}

/* 中间文字 */
.row-body{flex:1;min-width:0}
.row-name{
  font-size:17px;color:#000;line-height:1.3;
  overflow:hidden;text-overflow:ellipsis;white-space:nowrap;
}
.row-sub{
  font-size:13px;color:#8e8e93;margin-top:2px;
  overflow:hidden;text-overflow:ellipsis;white-space:nowrap;
}

/* 右侧 chevron（iOS 列表分隔符）*/
.row .acc{
  width:10px;height:16px;position:relative;flex-shrink:0;opacity:.3;
}
.row .acc::before,.row .acc::after{
  content:"";position:absolute;left:0;width:10px;height:2px;
  background:#c7c7cc;border-radius:2px;transform-origin:right center;
}
.row .acc::before{top:4px;transform:rotate(45deg)}
.row .acc::after{top:10px;transform:rotate(-45deg)}
.row.no-acc .acc{display:none}

/* iOS inset 分组（桌面宽屏）*/
@media (min-width:768px){
  .list{
    max-width:720px;margin:24px auto;border-radius:12px;
    border:.5px solid rgba(60,60,67,.29);overflow:hidden;
  }
  .section{max-width:720px;margin:24px auto}
}

/* 预览遮罩（iOS style）*/
.pre-mask{
  position:fixed;inset:0;background:#000;
  display:none;align-items:center;justify-content:center;
  z-index:100;flex-direction:column;
}
.pre-mask.show{display:flex}
.pre-mask img,.pre-mask video{
  max-width:100vw;max-height:calc(100vh - 100px);object-fit:contain;
}
.pre-mask iframe{
  width:100vw;height:calc(100vh - 100px);border:0;background:#fff;
}
.pre-topbar{
  position:absolute;top:0;left:0;right:0;
  padding:calc(env(safe-area-inset-top) + 10px) 16px 10px;
  background:rgba(0,0,0,.5);backdrop-filter:blur(20px);
  display:flex;align-items:center;justify-content:space-between;
  z-index:101;
}
.pre-topbar button,.pre-topbar a{
  color:#fff;font-size:17px;background:none;border:none;
  padding:6px 12px;cursor:pointer;text-decoration:none;
  font-family:inherit;
}
.pre-topbar .title{
  flex:1;text-align:center;color:#fff;font-size:15px;
  overflow:hidden;text-overflow:ellipsis;white-space:nowrap;margin:0 8px;
}

/* 加载态 */
.loading{text-align:center;color:#8e8e93;padding:80px 20px;font-size:15px}
</style>
</head>
<body>

<!-- 顶部导航：永不销毁 -->
<nav class="nav" id="nav">
  <div class="nav-bar">
    <button class="back" id="backBtn" disabled style="visibility:hidden">
      <span class="chevron"></span>
      <span>返回</span>
    </button>
    <div class="title" id="navTitle">文件</div>
    <div class="right"></div>
  </div>
</nav>

<!-- 滚动内容区：只替换这里面的内容 -->
<main class="scroll" id="scroll">
  <div class="loading">加载中…</div>
</main>

<!-- 预览 -->
<div class="pre-mask" id="mask" role="dialog" aria-modal="true">
  <div class="pre-topbar">
    <button id="preClose">完成</button>
    <div class="title" id="preTitle"></div>
    <a id="preDl" target="_blank" rel="noopener">下载</a>
  </div>
  <div id="preBox"></div>
</div>

<script>
"use strict";
const BASE = "/files";
let CURRENT = "";        // 当前路径（相对 NAS 根）
let PARENT = null;       // 父路径（后端返回）

/* ---------- 工具 ---------- */
function fmtSize(b){
  if (b<1024) return b+" B";
  if (b<1024*1024) return (b/1024).toFixed(1)+" KB";
  if (b<1024*1024*1024) return (b/1024/1024).toFixed(1)+" MB";
  return (b/1024/1024/1024).toFixed(2)+" GB";
}
function fmtSub(f){
  if (f.is_dir) return "文件夹";
  return fmtSize(f.size) + (f.mtime ? " · " + new Date(f.mtime*1000).toLocaleDateString() : "");
}
function iconKind(f){
  if (f.is_dir) return "folder";
  switch(f.icon){
    case "image": case "pdf": case "video":
    case "audio": case "text": return f.icon;
    default: return "file";
  }
}
function iconGlyph(kind){
  // SF Symbol 风格文字 fallback（iOS 字体自带 SF Symbols，但 web 不一定，用文字兜底）
  return {folder:"文件夹",image:"照片",pdf:"PDF",video:"视频",audio:"音乐",text:"文档",file:"文件"}[kind] || "文件";
}

/* ---------- 加载目录 ---------- */
async function load(path){
  CURRENT = path;
  const q = path ? "?path=" + encodeURIComponent(path) : "";
  try{
    const res = await fetch(BASE + q);
    if (!res.ok) throw new Error(res.statusText);
    const data = await res.json();
    PARENT = data.parent;
    render(data);
    // 同步 URL（纯前端路由，浏览器前进/后退可用）
    history.replaceState(null,"",
      location.pathname + (CURRENT==="" ? "" : "?p=" + encodeURIComponent(CURRENT)));
  }catch(e){
    document.getElementById("scroll").innerHTML =
      `<div class="loading" style="color:#ff3b30">加载失败：${e.message}</div>`;
  }
}

/* ---------- 渲染 ---------- */
function render(data){
  // 标题：最后一段
  const parts = data.current.split("/").filter(Boolean);
  document.getElementById("navTitle").textContent =
    parts.length ? parts[parts.length-1] : "文件";

  // 返回按钮可见性
  const backBtn = document.getElementById("backBtn");
  if (PARENT != null){
    backBtn.style.visibility = "";
    backBtn.disabled = false;
    // 按钮文字改成上一级名称
    const pp = PARENT.split("/").filter(Boolean);
    backBtn.querySelector("span:last-child").textContent =
      pp.length ? pp[pp.length-1] : "文件";
  }else{
    backBtn.style.visibility = "hidden";
    backBtn.disabled = true;
  }

  // 内容：分区（文件夹优先，然后文件）
  const scroll = document.getElementById("scroll");
  if (!data.items.length){
    scroll.innerHTML = `<div class="section-header empty-hint">此目录为空</div>`;
    return;
  }
  const dirs = data.items.filter(f => f.is_dir);
  const files = data.items.filter(f => !f.is_dir);

  let html = "";
  if (dirs.length){
    html += `<div class="list">`;
    for (const d of dirs) html += rowHtml(d);
    html += `</div>`;
  }
  if (files.length){
    if (dirs.length) html += `<div class="section-header">文件</div>`;
    html += `<div class="list">`;
    for (const f of files) html += rowHtml(f);
    html += `</div>`;
  }
  scroll.innerHTML = html;
}

function rowHtml(f){
  const kind = iconKind(f);
  const glyph = iconGlyph(kind);
  let iconHtml;
  if (!f.is_dir && f.thumb){
    iconHtml = `<div class="row-icon ${kind} has-thumb"><img src="${f.thumb}" loading="lazy" alt=""></div>`;
  }else{
    iconHtml = `<div class="row-icon ${kind}"><span class="sym">${glyph}</span></div>`;
  }
  const noAcc = (f.is_dir) ? "" : ""; // 文件也显示 chevron（iOS 行为）
  return `
  <div class="row ${f.is_dir?'has-parent':''}"
       data-path="${f.path}" data-isdir="${f.is_dir}">
    ${iconHtml}
    <div class="row-body">
      <div class="row-name"></div>
      <div class="row-sub"></div>
    </div>
    <div class="acc"></div>
  </div>`.replace(
      /<div class="row-body">[\s\S]*?<\/div>/,
      `<div class="row-body">
        <div class="row-name">${escapeHtml(f.name)}</div>
        <div class="row-sub">${escapeHtml(fmtSub(f))}</div>
      </div>`
    );
}

function escapeHtml(s){
  return String(s).replace(/[&<>"']/g, c =>
    ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
}

/* ---------- 事件委托（核心：永不销毁的父容器统一监听）---------- */
document.getElementById("scroll").addEventListener("click", e => {
  const row = e.target.closest(".row[data-path]");
  if (!row) return;
  const path = row.dataset.path;
  const isDir = row.dataset.isdir === "true";
  if (isDir){
    load(path);
  }else{
    // 取原始文件信息（从 DOM 恢复）
    const name = row.querySelector(".row-name").textContent;
    const kindClass = row.querySelector(".row-icon").classList;
    let kind = "file";
    for (const c of ["folder","image","pdf","video","audio","text"])
      if (kindClass.contains(c)) kind = c;
    openPreview({path, name, icon: kind});
  }
});

document.getElementById("backBtn").addEventListener("click", () => {
  if (PARENT != null) load(PARENT);
});

// 浏览器前进/后退
window.addEventListener("popstate", () => {
  const u = new URL(location.href);
  load(u.searchParams.get("p") || "");
});

/* ---------- 预览 ---------- */
function openPreview(f){
  const box = document.getElementById("preBox");
  box.innerHTML = "";
  document.getElementById("preTitle").textContent = f.name;
  const preUrl = BASE + "/pre?path=" + encodeURIComponent(f.path);
  const dlUrl  = BASE + "/dl?path=" + encodeURIComponent(f.path);
  document.getElementById("preDl").href = dlUrl;

  const kind = f.icon;
  if (kind==="image"){
    const img = document.createElement("img"); img.src = preUrl; box.appendChild(img);
  }else if (kind==="video"){
    const v = document.createElement("video"); v.src = preUrl; v.controls = true; v.play();
    box.appendChild(v);
  }else if (kind==="audio"){
    const a = document.createElement("audio"); a.src = preUrl; a.controls = true; box.appendChild(a);
  }else if (kind==="pdf" || kind==="text"){
    const ifr = document.createElement("iframe"); ifr.src = preUrl; box.appendChild(ifr);
  }else{
    window.location.href = dlUrl;
    return;
  }
  document.getElementById("mask").classList.add("show");
}
document.getElementById("preClose").addEventListener("click", () => {
  const m = document.getElementById("mask");
  m.classList.remove("show");
  setTimeout(() => document.getElementById("preBox").innerHTML = "", 300);
});

/* ---------- 启动 ---------- */
(function(){
  const u = new URL(location.href);
  load(u.searchParams.get("p") || "");
})();
</script>
</body>
</html>
"""
