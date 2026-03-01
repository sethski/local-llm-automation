"""
sethOS_server.py v2 — Backend for SethOS
-----------------------------------------
Install:
    pip install flask flask-cors watchdog requests beautifulsoup4 google-auth-oauthlib google-api-python-client PyMuPDF pillow

Run:
    python sethOS_server.py
"""

import os, json, mimetypes, shutil, subprocess, base64, threading, time
from pathlib import Path
from datetime import datetime
from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

HOME = Path.home()
TOKEN_FILE = Path("token.json")
CREDS_FILE = Path("credentials.json")

# ──────────────────────────────────────────
# HEALTH
# ──────────────────────────────────────────
@app.route("/api/health")
def health():
    return jsonify({"status": "ok", "time": datetime.now().isoformat()})


# ──────────────────────────────────────────
# WEB SEARCH (DuckDuckGo — no API key needed)
# ──────────────────────────────────────────
@app.route("/api/search")
def web_search():
    query = request.args.get("q", "")
    if not query:
        return jsonify({"error": "No query"}), 400
    try:
        import requests
        from bs4 import BeautifulSoup
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        url = f"https://html.duckduckgo.com/html/?q={requests.utils.quote(query)}"
        r = requests.get(url, headers=headers, timeout=8)
        soup = BeautifulSoup(r.text, "html.parser")
        results = []
        for res in soup.select(".result")[:6]:
            title_el = res.select_one(".result__title")
            snippet_el = res.select_one(".result__snippet")
            link_el = res.select_one(".result__url")
            if title_el and snippet_el:
                results.append({
                    "title": title_el.get_text(strip=True),
                    "snippet": snippet_el.get_text(strip=True),
                    "url": link_el.get_text(strip=True) if link_el else ""
                })
        return jsonify({"results": results, "query": query})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ──────────────────────────────────────────
# FETCH WEBPAGE
# ──────────────────────────────────────────
@app.route("/api/fetch")
def fetch_page():
    url = request.args.get("url", "")
    if not url:
        return jsonify({"error": "No URL"}), 400
    try:
        import requests
        from bs4 import BeautifulSoup
        if not url.startswith("http"):
            url = "https://" + url
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        r = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(r.text, "html.parser")
        for tag in soup(["script","style","nav","footer","header","aside"]):
            tag.decompose()
        text = soup.get_text(separator="\n", strip=True)
        # Limit to 8000 chars
        return jsonify({"content": text[:8000], "url": url, "title": soup.title.string if soup.title else url})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ──────────────────────────────────────────
# FILE READING (PDF, images, text)
# ──────────────────────────────────────────
@app.route("/api/read-file", methods=["POST"])
def read_file():
    """Read uploaded file and return its text content."""
    if "file" not in request.files:
        return jsonify({"error": "No file"}), 400
    f = request.files["file"]
    name = f.filename
    ext = Path(name).suffix.lower()

    try:
        # PDF
        if ext == ".pdf":
            try:
                import fitz  # PyMuPDF
                data = f.read()
                doc = fitz.open(stream=data, filetype="pdf")
                text = ""
                for page in doc:
                    text += page.get_text()
                return jsonify({"text": text[:15000], "type": "pdf", "pages": doc.page_count})
            except ImportError:
                return jsonify({"error": "Install PyMuPDF: pip install PyMuPDF", "type": "pdf"})

        # Image
        elif ext in {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}:
            data = f.read()
            b64 = base64.b64encode(data).decode()
            return jsonify({"base64": b64, "type": "image", "mime": mimetypes.guess_type(name)[0] or "image/png"})

        # Text / code
        else:
            text = f.read().decode("utf-8", errors="replace")
            return jsonify({"text": text[:15000], "type": "text"})

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ──────────────────────────────────────────
# FILE MANAGER
# ──────────────────────────────────────────
CODE_EXTS = {'.py','.ino','.js','.jsx','.ts','.tsx','.json','.html','.css',
             '.md','.txt','.yaml','.yml','.sql','.c','.cpp','.h','.sh','.bat',
             '.csv','.xml','.env','.gitignore','.toml','.rs','.go','.java','.php'}

def scan_dir(path: Path, depth=0, max_depth=4):
    items = []
    try:
        for item in sorted(path.iterdir(), key=lambda x: (x.is_file(), x.name.lower())):
            if item.name.startswith('.') or item.name in {'node_modules','__pycache__','.git','venv','env','dist','build','.next'}:
                continue
            if item.is_dir():
                items.append({"name": item.name, "type": "dir", "path": str(item),
                               "children": scan_dir(item, depth+1, max_depth) if depth < max_depth else []})
            elif item.suffix.lower() in CODE_EXTS or depth == 0:
                stat = item.stat()
                size = stat.st_size
                items.append({"name": item.name, "type": "file", "path": str(item),
                               "size": f"{size//1024}KB" if size >= 1024 else f"{size}B",
                               "modified": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d")})
    except PermissionError:
        pass
    return items

@app.route("/api/files")
def get_files():
    path_str = request.args.get("path", str(HOME / "Projects"))
    path = Path(path_str).expanduser()
    if not path.exists():
        return jsonify({"error": "Path not found", "tree": []})
    return jsonify({"tree": scan_dir(path)})

@app.route("/api/file")
def get_file():
    path_str = request.args.get("path", "")
    path = Path(path_str)
    if not path.exists() or not path.is_file():
        return jsonify({"error": "File not found"}), 404
    try:
        return jsonify({"content": path.read_text(encoding="utf-8", errors="replace"), "name": path.name})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ──────────────────────────────────────────
# FULL FILE SYSTEM BROWSER
# ──────────────────────────────────────────
@app.route("/api/filesystem")
def filesystem():
    """Returns all files/folders at a given path with full metadata."""
    path_str = request.args.get("path", str(HOME))
    path = Path(path_str).expanduser()
    if not path.exists():
        return jsonify({"error": "Path not found"}), 404

    items = []
    try:
        for item in sorted(path.iterdir(), key=lambda x: (x.is_file(), x.name.lower())):
            try:
                stat = item.stat()
                size = stat.st_size
                items.append({
                    "name": item.name,
                    "path": str(item),
                    "type": "dir" if item.is_dir() else "file",
                    "ext": item.suffix.lower() if item.is_file() else "",
                    "size": size,
                    "size_str": format_size(size),
                    "modified": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M"),
                    "created": datetime.fromtimestamp(stat.st_ctime).strftime("%Y-%m-%d %H:%M"),
                })
            except (PermissionError, OSError):
                pass
    except PermissionError:
        return jsonify({"error": "Permission denied"}), 403

    parent = str(path.parent) if path != path.parent else None
    return jsonify({"items": items, "path": str(path), "parent": parent})

def format_size(size):
    if size < 1024: return f"{size} B"
    elif size < 1024**2: return f"{size/1024:.1f} KB"
    elif size < 1024**3: return f"{size/1024**2:.1f} MB"
    else: return f"{size/1024**3:.1f} GB"

@app.route("/api/disk-usage")
def disk_usage():
    import shutil as sh
    drives = []
    if os.name == 'nt':  # Windows
        import string
        for letter in string.ascii_uppercase:
            drive = f"{letter}:\\"
            if os.path.exists(drive):
                try:
                    usage = sh.disk_usage(drive)
                    drives.append({
                        "name": drive,
                        "total": usage.total,
                        "used": usage.used,
                        "free": usage.free,
                        "percent": round(usage.used / usage.total * 100, 1)
                    })
                except:
                    pass
    else:
        usage = sh.disk_usage("/")
        drives.append({"name": "/", "total": usage.total, "used": usage.used,
                        "free": usage.free, "percent": round(usage.used/usage.total*100,1)})
    return jsonify({"drives": drives})


# ──────────────────────────────────────────
# SCREENSHOT MANAGER (with auto-sort watcher)
# ──────────────────────────────────────────
_ss_base = str(HOME / "Pictures" / "Screenshots")

@app.route("/api/screenshots/config", methods=["GET","POST"])
def ss_config():
    global _ss_base
    if request.method == "POST":
        data = request.json or {}
        _ss_base = data.get("path", _ss_base)
        # restart watcher with new path
        start_screenshot_watcher(_ss_base)
        return jsonify({"path": _ss_base})
    return jsonify({"path": _ss_base})

@app.route("/api/screenshots")
def get_screenshots():
    path_str = request.args.get("path", _ss_base)
    base = Path(path_str).expanduser()
    base.mkdir(parents=True, exist_ok=True)

    img_exts = {'.png','.jpg','.jpeg','.gif','.bmp','.webp'}
    folders = {}

    for item in base.rglob("*"):
        if item.suffix.lower() in img_exts and item.is_file():
            try:
                mtime = datetime.fromtimestamp(item.stat().st_mtime)
                date_key = mtime.strftime("%Y-%m-%d")
                if date_key not in folders:
                    folders[date_key] = []
                rel = item.relative_to(base)
                folders[date_key].append({
                    "name": item.name,
                    "path": str(item),
                    "rel": str(rel),
                    "time": mtime.strftime("%H:%M:%S"),
                    "size": format_size(item.stat().st_size)
                })
            except:
                pass

    sorted_folders = [
        {"date": date, "files": sorted(files, key=lambda f: f["time"], reverse=True)}
        for date, files in sorted(folders.items(), reverse=True)
    ]
    return jsonify({"folders": sorted_folders, "base": str(base)})

@app.route("/api/screenshots/image")
def serve_screenshot_image():
    path_str = request.args.get("path", "")
    path = Path(path_str)
    if not path.exists():
        return "Not found", 404
    return send_from_directory(str(path.parent), path.name)

@app.route("/api/screenshots/delete", methods=["POST"])
def delete_screenshot():
    data = request.json or {}
    path = Path(data.get("path",""))
    if path.exists() and path.is_file():
        path.unlink()
        return jsonify({"ok": True})
    return jsonify({"error": "Not found"}), 404


# ──────────────────────────────────────────
# APP MANAGER (Windows)
# ──────────────────────────────────────────
GAME_KEYWORDS = {'game','games','steam','epic','gog','ubisoft','ea app','origin','battle.net',
                 'minecraft','roblox','valorant','fortnite','league','riot','blizzard'}

@app.route("/api/apps")
def get_apps():
    apps = []
    seen = set()

    if os.name == 'nt':
        # Registry scan
        import winreg
        reg_paths = [
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
            (winreg.HKEY_CURRENT_USER,  r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
        ]
        for hive, reg_path in reg_paths:
            try:
                key = winreg.OpenKey(hive, reg_path)
                for i in range(winreg.QueryInfoKey(key)[0]):
                    try:
                        sub_name = winreg.EnumKey(key, i)
                        sub = winreg.OpenKey(key, sub_name)
                        def val(n):
                            try: return winreg.QueryValueEx(sub, n)[0]
                            except: return ""
                        name = val("DisplayName")
                        if not name or name in seen: continue
                        seen.add(name)
                        icon = val("DisplayIcon").split(",")[0].strip('"') if val("DisplayIcon") else ""
                        apps.append({
                            "name": name,
                            "version": val("DisplayVersion"),
                            "publisher": val("Publisher"),
                            "install_path": val("InstallLocation"),
                            "icon": icon,
                            "size": val("EstimatedSize"),
                            "date": val("InstallDate"),
                            "uninstall": val("UninstallString"),
                            "is_game": any(kw in name.lower() or kw in val("Publisher").lower()
                                          for kw in GAME_KEYWORDS)
                        })
                    except:
                        pass
            except:
                pass

        # Start menu shortcuts
        start_paths = [
            Path(os.environ.get("APPDATA","")) / "Microsoft/Windows/Start Menu/Programs",
            Path(os.environ.get("PROGRAMDATA","")) / "Microsoft/Windows/Start Menu/Programs",
        ]
        for sp in start_paths:
            if sp.exists():
                for lnk in sp.rglob("*.lnk"):
                    name = lnk.stem
                    if name not in seen and not any(x in name.lower() for x in ['uninstall','help','readme']):
                        seen.add(name)
                        apps.append({
                            "name": name,
                            "version": "", "publisher": "", "install_path": "",
                            "icon": str(lnk), "size": "", "date": "",
                            "uninstall": "", "is_game": any(kw in name.lower() for kw in GAME_KEYWORDS)
                        })
    else:
        # Linux/Mac: scan /usr/share/applications
        apps_dir = Path("/usr/share/applications")
        if apps_dir.exists():
            for f in apps_dir.glob("*.desktop"):
                lines = f.read_text(errors="replace").splitlines()
                name = next((l.split("=",1)[1] for l in lines if l.startswith("Name=")),f.stem)
                if name in seen: continue
                seen.add(name)
                apps.append({"name": name,"version":"","publisher":"","install_path":"",
                             "icon":"","size":"","date":"","uninstall":"","is_game": False})

    apps.sort(key=lambda a: a["name"].lower())
    games = [a for a in apps if a["is_game"]]
    regular = [a for a in apps if not a["is_game"]]
    return jsonify({"apps": regular, "games": games, "total": len(apps)})

@app.route("/api/apps/launch", methods=["POST"])
def launch_app():
    data = request.json or {}
    path = data.get("path","")
    if path and os.path.exists(path):
        try:
            os.startfile(path) if os.name == 'nt' else subprocess.Popen(["xdg-open", path])
            return jsonify({"ok": True})
        except Exception as e:
            return jsonify({"error": str(e)}), 500
    return jsonify({"error": "Path not found"}), 404


# ──────────────────────────────────────────
# GMAIL
# ──────────────────────────────────────────
def get_gmail_service():
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build
        SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']
        creds = None
        if TOKEN_FILE.exists():
            creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                if not CREDS_FILE.exists():
                    return None, "credentials.json not found"
                flow = InstalledAppFlow.from_client_secrets_file(str(CREDS_FILE), SCOPES)
                creds = flow.run_local_server(port=0)
            TOKEN_FILE.write_text(creds.to_json())
        return build('gmail','v1',credentials=creds), None
    except ImportError:
        return None, "Install google libs"
    except Exception as e:
        return None, str(e)

@app.route("/api/email/auth")
def email_auth():
    service, err = get_gmail_service()
    if err: return jsonify({"error": err})
    return jsonify({"status": "authorized"})

@app.route("/api/email/inbox")
def get_inbox():
    service, err = get_gmail_service()
    if err: return jsonify({"error": err}), 401
    try:
        results = service.users().messages().list(userId='me', maxResults=30, q='in:inbox').execute()
        messages = results.get('messages', [])
        emails = []
        for msg in messages[:20]:
            full = service.users().messages().get(userId='me', id=msg['id'], format='full').execute()
            headers = {h['name']: h['value'] for h in full['payload']['headers']}
            def extract_body(payload):
                if 'parts' in payload:
                    for part in payload['parts']:
                        t = extract_body(part)
                        if t: return t
                elif payload.get('mimeType') == 'text/plain':
                    import base64 as b64
                    data = payload.get('body',{}).get('data','')
                    if data: return b64.urlsafe_b64decode(data+'==').decode('utf-8',errors='replace')
                return ""
            body = extract_body(full['payload']) or full.get('snippet','')
            try:
                from email.utils import parsedate_to_datetime
                date_fmt = parsedate_to_datetime(headers.get('Date','')).strftime("%b %d, %Y %H:%M")
            except: date_fmt = headers.get('Date','')[:20]
            emails.append({
                "id": msg['id'], "from": headers.get('From','Unknown'),
                "subject": headers.get('Subject','(no subject)'),
                "date": date_fmt, "body": body[:3000],
                "unread": 'UNREAD' in full.get('labelIds',[])
            })
        return jsonify({"emails": emails})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ──────────────────────────────────────────
# SCREENSHOT WATCHER
# ──────────────────────────────────────────
_observer = None

def start_screenshot_watcher(watch_path: str):
    global _observer
    if _observer:
        try: _observer.stop(); _observer.join()
        except: pass
    try:
        from watchdog.observers import Observer
        from watchdog.events import FileSystemEventHandler
        img_exts = {'.png','.jpg','.jpeg','.gif','.bmp','.webp'}
        class Handler(FileSystemEventHandler):
            def on_created(self, event):
                if event.is_directory: return
                path = Path(event.src_path)
                if path.suffix.lower() not in img_exts: return
                time.sleep(0.8)
                now = datetime.now()
                dest_dir = Path(watch_path) / now.strftime("%Y-%m-%d")
                dest_dir.mkdir(exist_ok=True)
                dest = dest_dir / f"{now.strftime('%H-%M-%S')}{path.suffix}"
                try:
                    shutil.move(str(path), str(dest))
                    print(f"[Screenshots] {path.name} → {dest}")
                except: pass
        _observer = Observer()
        _observer.schedule(Handler(), watch_path, recursive=False)
        _observer.start()
        print(f"[Screenshots] Watching: {watch_path}")
    except ImportError:
        print("[Screenshots] watchdog not installed")


# ──────────────────────────────────────────
# MAIN
# ──────────────────────────────────────────
if __name__ == "__main__":
    print("="*50)
    print("  SethOS Server v2 — http://localhost:5000")
    print("="*50)
    ss_path = str(HOME / "Pictures" / "Screenshots")
    Path(ss_path).mkdir(parents=True, exist_ok=True)
    start_screenshot_watcher(ss_path)
    app.run(host="0.0.0.0", port=5000, debug=False, threaded=True)
