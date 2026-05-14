import subprocess
import os
import re
import tempfile
import zipfile
import shutil
from flask import Flask, request, jsonify, send_file, render_template_string
from flask_cors import CORS

app = Flask(__name__)
CORS(app)
app.config["MAX_CONTENT_LENGTH"] = 2 * 1024 * 1024 * 1024  # 2 GB upload limit

DOWNLOAD_DIR = tempfile.mkdtemp()
CONVERT_DIR  = tempfile.mkdtemp()

# Write Instagram cookies from env var to a file for yt-dlp
COOKIES_FILE = None
_cookies_raw = os.environ.get("INSTAGRAM_COOKIES", "")
_cookies_content = _cookies_raw.strip().lstrip("<").rstrip(">").strip()
print(f"[DEBUG] INSTAGRAM_COOKIES set: {bool(_cookies_content)}, first 30 chars: {repr(_cookies_content[:30])}")
if _cookies_content and "Netscape" in _cookies_content:
    _cf = tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False)
    _cf.write(_cookies_content)
    _cf.close()
    COOKIES_FILE = _cf.name
    print(f"[DEBUG] Cookies file written to: {COOKIES_FILE}")

# ─── Shared CSS ───────────────────────────────────────────────────────────────
COMMON_CSS = """
  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    min-height: 100vh;
    display: flex;
    align-items: center;
    justify-content: center;
    background: #0a0a0a;
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    color: #fff;
    padding: 24px;
  }
  .card {
    width: 100%;
    max-width: 580px;
    padding: 48px 40px;
    background: #111;
    border: 1px solid #222;
    border-radius: 20px;
    box-shadow: 0 20px 60px rgba(0,0,0,0.5);
  }
  .back {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    color: #555;
    font-size: 13px;
    text-decoration: none;
    margin-bottom: 28px;
    transition: color 0.2s;
  }
  .back:hover { color: #aaa; }
  .logo { display: flex; align-items: center; gap: 12px; margin-bottom: 32px; }
  .logo-icon {
    width: 44px; height: 44px; border-radius: 12px;
    display: flex; align-items: center; justify-content: center; font-size: 22px;
  }
  .logo-icon.ig  { background: linear-gradient(135deg,#f09433,#e6683c,#dc2743,#cc2366,#bc1888); }
  .logo-icon.cv  { background: linear-gradient(135deg,#1a73e8,#0d47a1); }
  .logo-text { font-size: 20px; font-weight: 700; letter-spacing: -0.3px; }
  h1 {
    font-size: 28px; font-weight: 800; letter-spacing: -0.5px; margin-bottom: 8px;
    background: linear-gradient(135deg,#fff 60%,#888);
    -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text;
  }
  .subtitle { color: #666; font-size: 14px; margin-bottom: 32px; }
  .input-row { display: flex; gap: 10px; margin-bottom: 16px; }
  input[type="text"] {
    flex: 1; padding: 14px 16px; background: #1a1a1a; border: 1px solid #2a2a2a;
    border-radius: 12px; color: #fff; font-size: 14px; outline: none; transition: border-color 0.2s;
  }
  input[type="text"]::placeholder { color: #444; }
  input[type="text"]:focus { border-color: #555; }
  button {
    padding: 14px 22px; border: none; border-radius: 12px; color: #fff;
    font-size: 14px; font-weight: 600; cursor: pointer; white-space: nowrap;
    transition: opacity 0.2s, transform 0.1s;
  }
  button.ig-btn  { background: linear-gradient(135deg,#f09433,#dc2743,#bc1888); }
  button.cv-btn  { background: linear-gradient(135deg,#1a73e8,#0d47a1); }
  button:hover { opacity: 0.9; }
  button:active { transform: scale(0.98); }
  button:disabled { opacity: 0.5; cursor: not-allowed; transform: none; }
  .status { font-size: 13px; min-height: 20px; transition: color 0.2s; }
  .status.loading { color: #888; }
  .status.error   { color: #f55; }
  .status.success { color: #4caf50; }
  .spinner {
    display: inline-block; width: 12px; height: 12px;
    border: 2px solid #444; border-top-color: #888; border-radius: 50%;
    animation: spin 0.7s linear infinite; margin-right: 6px; vertical-align: middle;
  }
  @keyframes spin { to { transform: rotate(360deg); } }
  .preview { margin-top: 24px; display: none; }
  .preview video { width: 100%; border-radius: 12px; background: #000; max-height: 400px; }
  .action-btn {
    display: block; width: 100%; margin-top: 12px; text-align: center;
    text-decoration: none; padding: 14px; background: #1a1a1a;
    border: 1px solid #2a2a2a; border-radius: 12px; color: #fff;
    font-size: 14px; font-weight: 600; cursor: pointer; transition: background 0.2s;
  }
  .action-btn:hover { background: #222; }
"""

# ─── Home Page ────────────────────────────────────────────────────────────────
HOME_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Video Tools</title>
  <style>
    """ + COMMON_CSS + """
    .tools { display: flex; flex-direction: column; gap: 16px; }
    .tool-card {
      display: flex; align-items: center; gap: 20px;
      padding: 24px; background: #161616; border: 1px solid #222;
      border-radius: 16px; text-decoration: none; color: #fff;
      transition: border-color 0.2s, background 0.2s;
      cursor: pointer;
    }
    .tool-card:hover { background: #1c1c1c; border-color: #333; }
    .tool-icon {
      width: 52px; height: 52px; border-radius: 14px; flex-shrink: 0;
      display: flex; align-items: center; justify-content: center; font-size: 26px;
    }
    .tool-icon.ig { background: linear-gradient(135deg,#f09433,#e6683c,#dc2743,#cc2366,#bc1888); }
    .tool-icon.cv { background: linear-gradient(135deg,#1a73e8,#0d47a1); }
    .tool-info h2 { font-size: 17px; font-weight: 700; margin-bottom: 4px; }
    .tool-info p  { font-size: 13px; color: #666; }
    .arrow { margin-left: auto; color: #444; font-size: 20px; }
  </style>
</head>
<body>
  <div class="card">
    <div class="logo">
      <div class="logo-icon ig">🎬</div>
      <span class="logo-text">Video Tools</span>
    </div>
    <h1>What do you need?</h1>
    <p class="subtitle">Pick a tool to get started.</p>

    <div class="tools">
      <a class="tool-card" href="/downloader">
        <div class="tool-icon ig">📥</div>
        <div class="tool-info">
          <h2>Reel &amp; Shorts Downloader</h2>
          <p>Download videos from Instagram or YouTube Shorts</p>
        </div>
        <span class="arrow">›</span>
      </a>
      <a class="tool-card" href="/converter">
        <div class="tool-icon cv">🔄</div>
        <div class="tool-info">
          <h2>MP4 → H.264 Converter</h2>
          <p>Convert multiple video files to H.264 in one go</p>
        </div>
        <span class="arrow">›</span>
      </a>
    </div>
  </div>
</body>
</html>"""

# ─── Downloader Page ──────────────────────────────────────────────────────────
DOWNLOADER_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Reel & Shorts Downloader</title>
  <style>""" + COMMON_CSS + """</style>
</head>
<body>
  <div class="card">
    <a class="back" href="/">← Back</a>
    <div class="logo">
      <div class="logo-icon ig">📥</div>
      <span class="logo-text">Downloader</span>
    </div>
    <h1>Download Reels &amp; Shorts</h1>
    <p class="subtitle">Paste an Instagram Reel or YouTube Shorts link below.</p>

    <div class="input-row">
      <input type="text" id="url" placeholder="Instagram Reel or YouTube Shorts URL…" />
      <button class="ig-btn" id="btn" onclick="fetchReel()">Download</button>
    </div>
    <div class="status" id="status"></div>
    <div class="preview" id="preview">
      <video id="video" controls playsinline></video>
      <a class="action-btn" id="dl-link" download="reel.mp4">⬇ Save Video</a>
    </div>
  </div>

  <script>
    const urlInput = document.getElementById('url');
    urlInput.addEventListener('keydown', e => { if (e.key === 'Enter') fetchReel(); });

    async function fetchReel() {
      const url = urlInput.value.trim();
      if (!url) return setStatus('Paste an Instagram or YouTube Shorts URL first.', 'error');
      setStatus('<span class="spinner"></span>Fetching video…', 'loading');
      document.getElementById('btn').disabled = true;
      document.getElementById('preview').style.display = 'none';
      try {
        const res = await fetch('/download', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ url })
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.error || 'Something went wrong.');
        setStatus('Done! Preview below or save the file.', 'success');
        const bust = '?t=' + Date.now();
        const video = document.getElementById('video');
        video.pause(); video.removeAttribute('src'); video.load();
        video.src = data.stream_url + bust;
        document.getElementById('dl-link').href = data.stream_url + bust;
        document.getElementById('preview').style.display = 'block';
      } catch (err) {
        setStatus(err.message, 'error');
      } finally {
        document.getElementById('btn').disabled = false;
      }
    }

    function setStatus(msg, cls) {
      const el = document.getElementById('status');
      el.innerHTML = msg;
      el.className = 'status ' + (cls || '');
    }
  </script>
</body>
</html>"""

# ─── Converter Page ───────────────────────────────────────────────────────────
CONVERTER_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>MP4 → H.264 Converter</title>
  <style>
    """ + COMMON_CSS + """
    .mode-tabs { display: flex; gap: 8px; margin-bottom: 20px; }
    .tab {
      flex: 1; padding: 10px; border: 1px solid #2a2a2a; border-radius: 10px;
      background: #161616; color: #666; font-size: 13px; font-weight: 600;
      cursor: pointer; text-align: center; transition: all 0.2s;
    }
    .tab.active { border-color: #1a73e8; color: #fff; background: #0d1a2e; }
    .drop-zone {
      border: 2px dashed #2a2a2a; border-radius: 14px; padding: 36px 24px;
      text-align: center; cursor: pointer; transition: border-color 0.2s, background 0.2s;
      margin-bottom: 20px;
    }
    .drop-zone:hover, .drop-zone.drag-over { border-color: #1a73e8; background: #0d1a2e; }
    .drop-zone p { color: #555; font-size: 14px; margin-top: 8px; }
    .drop-zone span { font-size: 36px; }
    #file-input, #folder-input { display: none; }
    .file-list { display: flex; flex-direction: column; gap: 8px; margin-bottom: 20px; max-height: 320px; overflow-y: auto; }
    .file-item {
      display: flex; align-items: center; gap: 12px;
      padding: 10px 14px; background: #161616; border: 1px solid #222; border-radius: 10px;
    }
    .file-name { flex: 1; font-size: 12px; color: #ccc; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    .file-path { font-size: 11px; color: #444; margin-top: 2px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    .file-info { flex: 1; min-width: 0; }
    .file-status { font-size: 12px; white-space: nowrap; }
    .file-status.waiting    { color: #555; }
    .file-status.converting { color: #888; }
    .file-status.done       { color: #4caf50; }
    .file-status.error      { color: #f55; }
    .file-dl { font-size: 12px; color: #1a73e8; text-decoration: none; white-space: nowrap; }
    .file-dl:hover { text-decoration: underline; }
    .btn-row { display: none; flex-direction: column; gap: 10px; }
    .top-btns { display: flex; gap: 10px; }
    .convert-all-btn, .dl-all-btn, .dl-zip-btn {
      flex: 1; padding: 14px; border: none; border-radius: 12px; color: #fff;
      font-size: 14px; font-weight: 600; cursor: pointer; transition: opacity 0.2s;
    }
    .convert-all-btn { background: linear-gradient(135deg,#1a73e8,#0d47a1); }
    .dl-all-btn { background: #1a1a1a; border: 1px solid #2a2a2a; }
    .dl-zip-btn {
      width: 100%; background: #1a1a1a; border: 1px solid #2a2a2a; display: none;
    }
    .convert-all-btn:hover, .dl-all-btn:hover, .dl-zip-btn:hover { opacity: 0.85; }
    .convert-all-btn:disabled, .dl-all-btn:disabled, .dl-zip-btn:disabled { opacity: 0.5; cursor: not-allowed; }
    .folder-card { background: #161616; border: 1px solid #222; border-radius: 12px; padding: 14px 16px; margin-bottom: 16px; }
    .folder-card-header { display: flex; align-items: center; justify-content: space-between; font-size: 13px; color: #888; }
    .folder-card-header strong { color: #fff; }
  </style>
</head>
<body>
  <div class="card">
    <a class="back" href="/">← Back</a>
    <div class="logo">
      <div class="logo-icon cv">🔄</div>
      <span class="logo-text">H.264 Converter</span>
    </div>
    <h1>MP4 → H.264</h1>
    <p class="subtitle">Convert video files to H.264 — upload files or an entire folder.</p>

    <div class="mode-tabs">
      <div class="tab active" id="tab-files" onclick="switchMode('files')">🎬 Files</div>
      <div class="tab" id="tab-folder" onclick="switchMode('folder')">📁 Folder</div>
    </div>

    <!-- FILES MODE -->
    <div id="mode-files">
      <div class="drop-zone" id="drop-zone" onclick="document.getElementById('file-input').click()">
        <span>🎞️</span>
        <p>Click or drag &amp; drop video files here</p>
        <input type="file" id="file-input" multiple accept="video/*" onchange="addFiles(this.files)" />
      </div>
      <div class="file-list" id="file-list"></div>
      <div class="btn-row" id="btn-row">
        <div class="top-btns">
          <button class="convert-all-btn" id="convert-btn" onclick="convertAll()">Convert All</button>
          <button class="dl-all-btn" id="dl-all-btn" onclick="downloadAll()">⬇ Download All</button>
        </div>
      </div>
    </div>

    <!-- FOLDER MODE -->
    <div id="mode-folder" style="display:none">
      <div class="drop-zone" id="folder-drop-zone">
        <span>📁</span>
        <p>Click to add a folder</p>
        <input type="file" id="folder-input" webkitdirectory multiple style="display:none" />
      </div>
      <div id="folders-container"></div>
    </div>
  </div>

  <script>
    let files = [];
    let mode = 'files';

    function switchMode(m) {
      mode = m;
      document.getElementById('mode-files').style.display = m === 'files' ? 'block' : 'none';
      document.getElementById('mode-folder').style.display = m === 'folder' ? 'block' : 'none';
      document.getElementById('tab-files').className = 'tab' + (m === 'files' ? ' active' : '');
      document.getElementById('tab-folder').className = 'tab' + (m === 'folder' ? ' active' : '');
    }

    // ── FILES MODE ──────────────────────────────────────────────
    const dropZone = document.getElementById('drop-zone');
    dropZone.addEventListener('dragover', e => { e.preventDefault(); dropZone.classList.add('drag-over'); });
    dropZone.addEventListener('dragleave', () => dropZone.classList.remove('drag-over'));
    dropZone.addEventListener('drop', e => {
      e.preventDefault(); dropZone.classList.remove('drag-over');
      addFiles(e.dataTransfer.files);
    });

    function addFiles(newFiles) {
      for (const f of newFiles) {
        if (!files.find(x => x.file.name === f.name && x.file.size === f.size))
          files.push({ file: f, status: 'waiting', dlUrl: null });
      }
      renderFileList();
      document.getElementById('btn-row').style.display = files.length ? 'flex' : 'none';
    }

    function renderFileList() {
      const list = document.getElementById('file-list');
      list.innerHTML = '';
      const labels = { waiting: 'Waiting', converting: '⏳ Converting…', done: '✓ Done', error: '✗ Error' };
      files.forEach(item => {
        const div = document.createElement('div');
        div.className = 'file-item';
        div.innerHTML = `
          <span>🎬</span>
          <span class="file-name">${item.file.name}</span>
          <span class="file-status ${item.status}">${labels[item.status]}</span>
          ${item.dlUrl ? `<a class="file-dl" href="${item.dlUrl}" download="${item.file.name.replace(/\.[^.]+$/, '.mp4')}">⬇</a>` : ''}
        `;
        list.appendChild(div);
      });
    }

    async function convertAll() {
      const btn = document.getElementById('convert-btn');
      const dlBtn = document.getElementById('dl-all-btn');
      btn.disabled = true; btn.textContent = 'Converting…'; dlBtn.style.display = 'none';
      for (let i = 0; i < files.length; i++) {
        if (files[i].status === 'done') continue;
        files[i].status = 'converting'; renderFileList();
        try {
          const fd = new FormData();
          fd.append('file', files[i].file);
          const res = await fetch('/convert', { method: 'POST', body: fd });
          const data = await res.json();
          if (!res.ok) throw new Error(data.error || 'Failed');
          files[i].status = 'done';
          files[i].dlUrl = data.url + '?t=' + Date.now();
        } catch { files[i].status = 'error'; }
        renderFileList();
      }
      btn.disabled = false; btn.textContent = 'Convert All';
      if (files.some(f => f.status === 'done')) dlBtn.style.display = 'block';
    }

    async function downloadAll() {
      for (const item of files.filter(f => f.status === 'done' && f.dlUrl)) {
        const a = document.createElement('a');
        a.href = item.dlUrl;
        a.download = item.file.name.replace(/\.[^.]+$/, '.mp4');
        document.body.appendChild(a); a.click(); document.body.removeChild(a);
        await new Promise(r => setTimeout(r, 500));
      }
    }

    // ── FOLDER MODE ─────────────────────────────────────────────
    let folders = [];
    const folderDropZone = document.getElementById('folder-drop-zone');
    folderDropZone.addEventListener('click', () => document.getElementById('folder-input').click());
    folderDropZone.addEventListener('dragover', e => { e.preventDefault(); folderDropZone.classList.add('drag-over'); });
    folderDropZone.addEventListener('dragleave', () => folderDropZone.classList.remove('drag-over'));
    folderDropZone.addEventListener('drop', e => { e.preventDefault(); folderDropZone.classList.remove('drag-over'); addFolder(e.dataTransfer.files); });
    document.getElementById('folder-input').addEventListener('change', function() { addFolder(this.files); });

    function addFolder(newFiles) {
      const videoFiles = Array.from(newFiles).filter(f => f.type.startsWith('video/') || /\.(mp4|mov|avi|mkv|webm|m4v)$/i.test(f.name));
      resetFolderInput();
      if (!videoFiles.length) return;
      const folderName = videoFiles[0]?.webkitRelativePath.split('/')[0] || 'Folder';
      folders.push({ id: Date.now(), name: folderName, files: videoFiles.map(f => ({ file: f, _status: 'waiting' })), converting: false, zipUrl: null });
      renderFolders();
    }

    function resetFolderInput() {
      const old = document.getElementById('folder-input');
      const neu = document.createElement('input');
      neu.type = 'file'; neu.id = 'folder-input'; neu.style.display = 'none';
      neu.setAttribute('webkitdirectory', ''); neu.setAttribute('multiple', '');
      neu.addEventListener('change', function() { addFolder(this.files); });
      old.parentNode.replaceChild(neu, old);
    }

    function renderFolders() {
      const container = document.getElementById('folders-container');
      container.innerHTML = '';
      const labels = { waiting: 'Waiting', converting: '⏳ Converting…', done: '✓ Done', error: '✗ Error' };
      folders.forEach(folder => {
        const card = document.createElement('div');
        card.className = 'folder-card';
        const fileRows = folder.files.map(item => {
          const relPath = item.file.webkitRelativePath || item.file.name;
          const parts = relPath.split('/');
          const name = parts.pop();
          const dir = parts.slice(1).join('/');
          return `<div class="file-item">
            <span>🎬</span>
            <div class="file-info">
              <div class="file-name">${name}</div>
              ${dir ? `<div class="file-path">${dir}</div>` : ''}
            </div>
            <span class="file-status ${item._status || 'waiting'}">${labels[item._status || 'waiting']}</span>
          </div>`;
        }).join('');
        const actionBtn = folder.zipUrl
          ? `<button class="convert-all-btn" style="padding:8px 16px;font-size:13px;flex:none;background:#1a1a1a;border:1px solid #2a2a2a" onclick="window.location='${folder.zipUrl}'">⬇ ZIP</button>`
          : `<button class="convert-all-btn" style="padding:8px 16px;font-size:13px;flex:none" ${folder.converting ? 'disabled' : ''} onclick="convertFolder(${folder.id})">${folder.converting ? 'Converting…' : 'Convert'}</button>`;
        card.innerHTML = `
          <div class="folder-card-header">
            <span>📁 <strong>${folder.name}</strong> — ${folder.files.length} file${folder.files.length !== 1 ? 's' : ''}</span>
            ${actionBtn}
          </div>
          <div class="file-list" style="margin:12px 0 0;max-height:200px">${fileRows}</div>
        `;
        container.appendChild(card);
      });
    }

    async function convertFolder(folderId) {
      const folder = folders.find(f => f.id === folderId);
      if (!folder || folder.converting) return;
      folder.converting = true;
      renderFolders();

      const CONCURRENCY = 3;
      const results = [];

      async function processFile(i) {
        folder.files[i]._status = 'converting'; renderFolders();
        try {
          const fd = new FormData();
          fd.append('file', folder.files[i].file);
          fd.append('path', folder.files[i].file.webkitRelativePath || folder.files[i].file.name);
          const res = await fetch('/convert', { method: 'POST', body: fd });
          const data = await res.json();
          if (!res.ok) throw new Error(data.error || 'Failed');
          folder.files[i]._status = 'done';
          results.push({ serverUrl: data.url, relativePath: folder.files[i].file.webkitRelativePath || folder.files[i].file.name });
        } catch { folder.files[i]._status = 'error'; }
        renderFolders();
      }

      for (let i = 0; i < folder.files.length; i += CONCURRENCY) {
        await Promise.all(folder.files.slice(i, i + CONCURRENCY).map((_, j) => processFile(i + j)));
      }

      if (results.length > 0) {
        try {
          const res = await fetch('/zip', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ files: results }) });
          const data = await res.json();
          if (res.ok) folder.zipUrl = data.url;
        } catch {}
      }

      folder.converting = false;
      renderFolders();
    }
  </script>
</body>
</html>"""


# ─── Routes ───────────────────────────────────────────────────────────────────

@app.route("/")
def home():
    return render_template_string(HOME_HTML)

@app.route("/downloader")
def downloader():
    return render_template_string(DOWNLOADER_HTML)

@app.route("/converter")
def converter():
    return render_template_string(CONVERTER_HTML)


@app.route("/download", methods=["POST"])
def download():
    data = request.get_json()
    url = (data or {}).get("url", "").strip()

    if not url:
        return jsonify({"error": "No URL provided."}), 400

    is_instagram = "instagram.com" in url
    is_youtube = "youtube.com/shorts" in url or "youtu.be" in url or "youtube.com/watch" in url

    if not is_instagram and not is_youtube:
        return jsonify({"error": "Please provide a valid Instagram Reel or YouTube Shorts URL."}), 400

    for f in os.listdir(DOWNLOAD_DIR):
        try:
            os.remove(os.path.join(DOWNLOAD_DIR, f))
        except Exception:
            pass

    output_template = os.path.join(DOWNLOAD_DIR, "reel.%(ext)s")

    ffmpeg_check = subprocess.run(["which", "ffmpeg"], capture_output=True, text=True)
    ffmpeg_path = ffmpeg_check.stdout.strip()

    cmd = [
        "yt-dlp",
        "--no-playlist",
        "-f", "bestvideo+bestaudio/best[acodec!=none]/best",
        "-S", "hasaud,res,fps",
        "--merge-output-format", "mp4",
        "-o", output_template,
        "--verbose",
        url,
    ]
    if ffmpeg_path:
        cmd += ["--ffmpeg-location", ffmpeg_path]
    if COOKIES_FILE:
        cmd += ["--cookies", COOKIES_FILE]

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=90)
    print(f"[DEBUG] yt-dlp stdout: {result.stdout[-2000:]}")
    print(f"[DEBUG] yt-dlp stderr: {result.stderr[-2000:]}")

    if result.returncode != 0:
        err = (result.stderr.strip() or result.stdout.strip() or "yt-dlp failed.")
        return jsonify({"error": err}), 500

    files = [f for f in os.listdir(DOWNLOAD_DIR) if f.endswith(".mp4")]
    if not files:
        return jsonify({"error": "Download failed — no file produced."}), 500

    return jsonify({"stream_url": f"/video/{files[0]}"})


@app.route("/convert", methods=["POST"])
def convert():
    if "file" not in request.files:
        return jsonify({"error": "No file uploaded."}), 400

    f = request.files["file"]
    if not f.filename:
        return jsonify({"error": "Empty filename."}), 400

    # Save upload to a temp file
    suffix = os.path.splitext(f.filename)[1] or ".mp4"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False, dir=CONVERT_DIR) as tmp:
        f.save(tmp.name)
        input_path = tmp.name

    output_path = input_path.replace(suffix, "_h264.mp4")

    ffmpeg_check = subprocess.run(["which", "ffmpeg"], capture_output=True, text=True)
    ffmpeg_bin = ffmpeg_check.stdout.strip() or "ffmpeg"

    # Try hardware-accelerated encoding first (macOS VideoToolbox), fall back to software
    result = subprocess.run([
        ffmpeg_bin, "-y",
        "-i", input_path,
        "-c:v", "h264_videotoolbox",
        "-q:v", "65",
        "-c:a", "aac",
        "-b:a", "128k",
        "-movflags", "+faststart",
        output_path
    ], capture_output=True, text=True, timeout=600)

    if result.returncode != 0:
        result = subprocess.run([
            ffmpeg_bin, "-y",
            "-i", input_path,
            "-c:v", "libx264",
            "-preset", "veryfast",
            "-crf", "23",
            "-c:a", "aac",
            "-b:a", "128k",
            "-movflags", "+faststart",
            output_path
        ], capture_output=True, text=True, timeout=600)

    os.remove(input_path)

    if result.returncode != 0:
        err = result.stderr[-2000:] or "ffmpeg failed."
        print(f"[CONVERT ERROR] {err}")
        return jsonify({"error": err}), 500

    filename = os.path.basename(output_path)
    print(f"[CONVERT OK] {filename}")
    return jsonify({"url": f"/converted/{filename}"})


@app.route("/zip", methods=["POST"])
def make_zip():
    data = request.get_json()
    file_entries = (data or {}).get("files", [])
    if not file_entries:
        return jsonify({"error": "No files provided."}), 400

    zip_path = os.path.join(CONVERT_DIR, f"converted_{tempfile.gettempprefix()}.zip")
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for entry in file_entries:
            server_url = entry.get("serverUrl", "")
            relative_path = entry.get("relativePath", "")
            # Extract filename from server URL e.g. /converted/tmpXXX_h264.mp4
            filename = server_url.split("/")[-1].split("?")[0]
            file_path = os.path.join(CONVERT_DIR, filename)
            if not os.path.exists(file_path):
                continue
            # Preserve directory structure, replace original extension with _h264.mp4
            zip_entry = re.sub(r'\.[^.]+$', '.mp4', relative_path)
            zf.write(file_path, zip_entry)

    zip_filename = os.path.basename(zip_path)
    return jsonify({"url": f"/download-zip/{zip_filename}"})


@app.route("/download-zip/<filename>")
def serve_zip(filename):
    if not re.match(r'^[\w.\-]+$', filename):
        return "Invalid filename", 400
    path = os.path.join(CONVERT_DIR, filename)
    if not os.path.exists(path):
        return "File not found", 404
    return send_file(path, mimetype="application/zip", as_attachment=True, download_name="converted_h264.zip")


@app.route("/video/<filename>")
def serve_video(filename):
    if not re.match(r'^[\w.\-]+$', filename):
        return "Invalid filename", 400
    path = os.path.join(DOWNLOAD_DIR, filename)
    if not os.path.exists(path):
        return "File not found", 404
    return send_file(path, mimetype="video/mp4", as_attachment=False, download_name="reel.mp4")


@app.route("/converted/<filename>")
def serve_converted(filename):
    if not re.match(r'^[\w.\-]+$', filename):
        return "Invalid filename", 400
    path = os.path.join(CONVERT_DIR, filename)
    if not os.path.exists(path):
        return "File not found", 404
    return send_file(path, mimetype="video/mp4", as_attachment=True, download_name=filename)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5555))
    print(f"Starting Video Tools at http://localhost:{port}")
    app.run(host="0.0.0.0", port=port, debug=False, threaded=True)
