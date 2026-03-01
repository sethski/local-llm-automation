# SethOS v2 — Complete Setup Guide

## ▶️ First Time Setup

### Step 1 — Install Python packages
```
pip install flask flask-cors watchdog requests beautifulsoup4 google-auth-oauthlib google-api-python-client PyMuPDF pillow
```

### Step 2 — Install Ollama models
```
ollama pull qwen2.5
ollama pull qwen2.5-coder
```

### Step 3 — Install Node.js packages
```
npm install
```

### Step 4 — Start the app
```
npm start
```

---

## Every Time After That
Just run: `npm start`
The Python server starts automatically inside the app.

---

## What's New in v2

| Feature | Details |
|---------|---------|
| 📄 PDF reading | Drop a PDF into chat — AI reads the full content |
| 🌐 Web search | Click 🌐 button to give AI internet access via DuckDuckGo |
| 🗑️ Delete chats | Hover over a chat in history → click trash icon |
| 🖼️ Screenshots | Now actually loads and shows your real screenshots |
| 🗂️ File System | Browse ALL files on your PC with storage sizes |
| 📦 App Manager | See all installed apps + games, separated |
| 📝 Documents | Full rich text editor (Google Docs-style) |
| 💾 Auto-save | Documents save automatically to local storage |

---

## Gmail Setup
1. Go to https://console.cloud.google.com
2. Create project → Enable Gmail API
3. Credentials → OAuth 2.0 Client → Desktop App → Download credentials.json
4. Place credentials.json next to sethOS_server.py
5. Restart → click Connect Gmail in the Email tab

---

## Document Editor Features
- Bold, Italic, Underline, Strikethrough
- Headings H1–H3, Paragraph, Code blocks, Blockquote
- Bullet lists, numbered lists, indent/outdent
- Text color, highlight color
- Insert table, link, divider
- Find & Replace (click Find in menubar)
- Export as HTML or TXT
- Print
- Auto-saves every 2 seconds to local storage
