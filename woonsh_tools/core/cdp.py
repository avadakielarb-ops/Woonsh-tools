"""
CDP (Chrome DevTools Protocol) — zero-dependency browser automation.

Provides WebSocket, Tab, Chrome launcher and Gemini-specific helpers.
Based on ЦСВ Вайт ppc_gemini.pyw, extracted into a reusable module.
"""

import base64
import json
import os
import re
import socket
import struct
import subprocess
import time
import urllib.parse
import urllib.request


CDP_PORT = 9222
GEMINI_URL = "https://gemini.google.com/app"

CHROME_PATHS = [
    os.path.join(os.environ.get("ProgramFiles", ""),
                 r"Google\Chrome\Application\chrome.exe"),
    os.path.join(os.environ.get("ProgramFiles(x86)", ""),
                 r"Google\Chrome\Application\chrome.exe"),
    os.path.join(os.environ.get("LOCALAPPDATA", ""),
                 r"Google\Chrome\Application\chrome.exe"),
    os.path.join(os.environ.get("ProgramFiles(x86)", ""),
                 r"Microsoft\Edge\Application\msedge.exe"),
    os.path.join(os.environ.get("ProgramFiles", ""),
                 r"Microsoft\Edge\Application\msedge.exe"),
]


class WebSocket:
    """Minimal WebSocket client — enough to talk to Chrome CDP."""

    def __init__(self, url, timeout=60):
        m = re.match(r"ws://([^:/]+):(\d+)(/.*)", url)
        if not m:
            raise RuntimeError(f"Bad WebSocket URL: {url}")
        host, port, path = m.group(1), int(m.group(2)), m.group(3)
        self.sock = socket.create_connection((host, port), timeout=timeout)
        self.sock.settimeout(timeout)
        self._buf = b""

        key = base64.b64encode(os.urandom(16)).decode()
        self.sock.sendall(
            f"GET {path} HTTP/1.1\r\nHost: {host}:{port}\r\n"
            f"Upgrade: websocket\r\nConnection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\n"
            f"Sec-WebSocket-Version: 13\r\n\r\n".encode()
        )
        while b"\r\n\r\n" not in self._buf:
            chunk = self.sock.recv(4096)
            if not chunk:
                raise RuntimeError("Chrome closed connection during handshake.")
            self._buf += chunk
        head, self._buf = self._buf.split(b"\r\n\r\n", 1)
        if b" 101" not in head.split(b"\r\n")[0]:
            raise RuntimeError("Chrome rejected WebSocket upgrade.")

    def _read(self, n):
        while len(self._buf) < n:
            chunk = self.sock.recv(65536)
            if not chunk:
                raise RuntimeError("Chrome connection closed.")
            self._buf += chunk
        out, self._buf = self._buf[:n], self._buf[n:]
        return out

    def _frame(self, opcode, payload):
        header = bytearray([0x80 | opcode])
        n = len(payload)
        if n < 126:
            header.append(0x80 | n)
        elif n < 65536:
            header.append(0x80 | 126)
            header += struct.pack(">H", n)
        else:
            header.append(0x80 | 127)
            header += struct.pack(">Q", n)
        mask = os.urandom(4)
        header += mask
        masked = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
        self.sock.sendall(bytes(header) + masked)

    def send(self, text):
        self._frame(0x1, text.encode("utf-8"))

    def recv(self):
        chunks = []
        while True:
            b0, b1 = self._read(2)
            fin, opcode, n = b0 & 0x80, b0 & 0x0F, b1 & 0x7F
            if n == 126:
                n = struct.unpack(">H", self._read(2))[0]
            elif n == 127:
                n = struct.unpack(">Q", self._read(8))[0]
            data = self._read(n) if n else b""
            if opcode == 0x8:
                raise RuntimeError("Chrome closed tab.")
            if opcode == 0x9:
                self._frame(0xA, data)
                continue
            if opcode == 0xA:
                continue
            chunks.append(data)
            if fin:
                return b"".join(chunks).decode("utf-8", "replace")

    def close(self):
        try:
            self._frame(0x8, b"")
        except Exception:
            pass
        try:
            self.sock.close()
        except Exception:
            pass


class Tab:
    """One Chrome tab: execute JavaScript via CDP."""

    def __init__(self, ws_url, timeout=60):
        self.ws = WebSocket(ws_url, timeout)
        self._id = 0
        self.keep_awake()

    def command(self, method, params=None, timeout=10):
        self._id += 1
        msg_id = self._id
        self.ws.sock.settimeout(timeout)
        self.ws.send(json.dumps({
            "id": msg_id, "method": method, "params": params or {}
        }))
        deadline = time.time() + timeout
        while time.time() < deadline:
            data = json.loads(self.ws.recv())
            if data.get("id") == msg_id:
                return data
        raise RuntimeError(f"Chrome did not respond to {method}.")

    def keep_awake(self):
        """Emulate focus so Gemini doesn't throttle the tab."""
        for method, params in (
            ("Emulation.setFocusEmulationEnabled", {"enabled": True}),
            ("Page.setWebLifecycleState", {"state": "active"}),
        ):
            try:
                self.command(method, params)
            except Exception:
                pass

    def evaluate(self, expression, timeout=60):
        self._id += 1
        msg_id = self._id
        self.ws.sock.settimeout(timeout)
        self.ws.send(json.dumps({
            "id": msg_id,
            "method": "Runtime.evaluate",
            "params": {
                "expression": expression,
                "returnByValue": True,
                "awaitPromise": True,
            },
        }))
        deadline = time.time() + timeout
        while time.time() < deadline:
            data = json.loads(self.ws.recv())
            if data.get("id") != msg_id:
                continue
            if "error" in data:
                raise RuntimeError(
                    f"CDP: {data['error'].get('message')}")
            result = data.get("result", {})
            if "exceptionDetails" in result:
                text = result["exceptionDetails"].get("text", "JS error")
                desc = (result["exceptionDetails"]
                        .get("exception", {}).get("description", ""))
                raise RuntimeError(f"JS: {desc or text}")
            return result.get("result", {}).get("value")
        raise RuntimeError("Chrome did not respond in time.")

    def close(self):
        self.ws.close()


# ── Chrome management ──────────────────────────────────────────────────────────

def chrome_path(saved=""):
    if saved and os.path.exists(saved):
        return saved
    for p in CHROME_PATHS:
        if p and os.path.exists(p):
            return p
    return ""


def cdp_http(path, method="GET", timeout=5):
    req = urllib.request.Request(
        f"http://127.0.0.1:{CDP_PORT}{path}", method=method)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = resp.read().decode("utf-8")
    return json.loads(body) if body.strip().startswith(("{", "[")) else body


def cdp_alive():
    try:
        cdp_http("/json/version", timeout=2)
        return True
    except Exception:
        return False


def launch_chrome(exe, profile_dir=""):
    if not exe:
        raise RuntimeError(
            "Chrome not found. Set chrome_path in config.json.")
    if not profile_dir:
        profile_dir = os.path.join(
            os.path.dirname(os.path.abspath(exe)), "woonsh-chrome-profile")
    os.makedirs(profile_dir, exist_ok=True)
    subprocess.Popen([
        exe,
        f"--remote-debugging-port={CDP_PORT}",
        f"--user-data-dir={profile_dir}",
        "--remote-allow-origins=*",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-background-timer-throttling",
        "--disable-backgrounding-occluded-windows",
        "--disable-renderer-backgrounding",
        "--disable-features=CalculateNativeWinOcclusion,"
        "OptimizationGuideOnDeviceModel,OptimizationGuideModelDownloading,"
        "TextSafetyClassifier,OptimizationHints",
        GEMINI_URL,
    ])
    for _ in range(40):
        if cdp_alive():
            return
        time.sleep(0.5)
    raise RuntimeError(
        "Chrome started but the debugging port is not responding.")


def open_gemini_tab(timeout=30):
    """Find or open a Gemini tab in our Chrome window."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            targets = cdp_http("/json")
        except Exception:
            time.sleep(0.5)
            continue
        pages = [t for t in targets
                 if t.get("type") == "page" and t.get("webSocketDebuggerUrl")]
        for t in pages:
            if "gemini.google.com" in (t.get("url") or ""):
                return t
        if pages:
            tab = Tab(pages[0]["webSocketDebuggerUrl"])
            try:
                tab.evaluate(
                    f"location.href = {json.dumps(GEMINI_URL)}")
            finally:
                tab.close()
            time.sleep(2)
            continue
        try:
            cdp_http("/json/new?url=" + urllib.parse.quote(GEMINI_URL),
                     method="PUT")
        except Exception:
            try:
                cdp_http("/json/new?url=" + urllib.parse.quote(GEMINI_URL))
            except Exception:
                pass
        time.sleep(1)
    raise RuntimeError("Could not open Gemini tab.")


# ── Gemini page interaction (JS snippets) ──────────────────────────────────────

JS_NEW_CHAT = r"""
(() => {
  const sels = [
    '[data-test-id="new-chat-button"]',
    'expandable-button[data-test-id="new-chat-button"]',
    'side-nav-action-button[data-test-id="new-chat-button"]',
    'button[aria-label*="New chat" i]',
    'a[aria-label*="New chat" i]',
  ];
  const press = (el) => {
    const hit = el.tagName === 'BUTTON' || el.tagName === 'A'
              ? el : (el.querySelector('button, a') || el);
    hit.click();
    return true;
  };
  for (const s of sels) {
    const el = document.querySelector(s);
    if (el) { press(el); return 'clicked:' + s; }
  }
  const words = ['new chat', 'новий чат', 'новый чат', 'nowy czat',
                 'nueva conversación', 'nouvelle discussion', 'neuer chat',
                 'nova conversa', 'nuova chat', 'nieuwe chat', 'ny chat',
                 'uusi keskustelu', 'nový chat', 'új csevegés', 'sohbet'];
  const nodes = document.querySelectorAll('button, a, [role="button"]');
  for (const el of nodes) {
    const text = ((el.getAttribute('aria-label') || '') + ' ' +
                  (el.innerText || '')).trim().toLowerCase();
    if (!text) continue;
    if (words.some(w => text.includes(w))) { press(el); return 'clicked:text'; }
  }
  return 'not-found';
})()
"""

JS_STATE = r"""
(() => {
  const sel = 'rich-textarea div[contenteditable="true"], '
            + 'div[contenteditable="true"][role="textbox"], '
            + 'div[contenteditable="true"], textarea';
  const box = document.querySelector(sel);
  const signin = /accounts\.google\.com|ServiceLogin/.test(location.href)
              || !!document.querySelector(
                   'a[href*="ServiceLogin"], '
                 + 'a[href*="accounts.google.com/ServiceLogin"]');
  return JSON.stringify({url: location.href, ready: !!box, signin: signin});
})()
"""

JS_INSERT = r"""
(() => {
  const sel = 'rich-textarea div[contenteditable="true"], '
            + 'div[contenteditable="true"][role="textbox"], '
            + 'div[contenteditable="true"], textarea';
  const box = document.querySelector(sel);
  if (!box) return 'no-input';
  box.focus();
  const text = __PROMPT__;
  if (box.tagName === 'TEXTAREA') {
    const setter = Object.getOwnPropertyDescriptor(
        window.HTMLTextAreaElement.prototype, 'value').set;
    setter.call(box, text);
    box.dispatchEvent(new Event('input', {bubbles: true}));
  } else {
    document.execCommand('selectAll', false, null);
    document.execCommand('insertText', false, text);
    box.dispatchEvent(new Event('input', {bubbles: true}));
  }
  return 'ok';
})()
"""

JS_TRY_SEND = r"""
(() => {
  const btns = Array.from(document.querySelectorAll('button'));
  const named = btns.find(b => {
    const a = ((b.getAttribute('aria-label') || '') + ' ' +
               (b.getAttribute('mattooltip') || '') + ' ' +
               (b.getAttribute('data-test-id') || '')).toLowerCase();
    return /send|надісл|надисл|отправ|submit/.test(a);
  });
  const byIcon = btns.find(b => {
    const ic = b.querySelector(
        'mat-icon, .material-symbols-outlined, .google-symbols');
    return ic && (ic.textContent || '').trim().toLowerCase() === 'send';
  });
  const btn = [named, byIcon].find(
      b => b && !b.disabled && b.getAttribute('aria-disabled') !== 'true');
  if (btn) { btn.click(); return 'button'; }
  const sel = 'rich-textarea div[contenteditable="true"], '
            + 'div[contenteditable="true"][role="textbox"], '
            + 'div[contenteditable="true"], textarea';
  const box = document.querySelector(sel);
  if (box) {
    for (const type of ['keydown', 'keypress', 'keyup']) {
      box.dispatchEvent(new KeyboardEvent(type, {key: 'Enter', code: 'Enter',
        keyCode: 13, which: 13, bubbles: true, cancelable: true}));
    }
    return 'enter';
  }
  return 'nothing';
})()
"""

JS_COMPOSER = r"""
(() => {
  const sel = 'rich-textarea div[contenteditable="true"], '
            + 'div[contenteditable="true"][role="textbox"], '
            + 'div[contenteditable="true"], textarea';
  const box = document.querySelector(sel);
  const text = box ? (box.value !== undefined ? box.value : box.innerText) : '';
  const nodes = document.querySelectorAll(
      'message-content, .model-response-text, [data-response-index]');
  return JSON.stringify({len: (text || '').trim().length, answers: nodes.length});
})()
"""

JS_PROBE = r"""
(() => {
  const nodes = document.querySelectorAll(
      'message-content, .model-response-text, [data-response-index]');
  const last = nodes[nodes.length - 1];
  const busy = Array.from(document.querySelectorAll('button')).some(b => {
    const a = ((b.getAttribute('aria-label') || '') + ' ' +
               (b.getAttribute('mattooltip') || '')).toLowerCase();
    return /stop|зупин|остановить/.test(a) && b.offsetParent !== null;
  });
  return JSON.stringify({
    answers: nodes.length,
    len: last ? (last.innerText || '').length : 0,
    busy: busy
  });
})()
"""

JS_EXTRACT = r"""
(() => {
  const nodes = document.querySelectorAll(
      'message-content, .model-response-text, [data-response-index]');
  const last = nodes[nodes.length - 1];
  if (!last) return '';
  const blocks = Array.from(last.querySelectorAll('code'));
  for (let i = blocks.length - 1; i >= 0; i--) {
    const t = (blocks[i].innerText || '').trim();
    if (t.startsWith('{') && t.endsWith('}')) return t;
  }
  return last.innerText || '';
})()
"""


# ── Gemini tab state helpers ───────────────────────────────────────────────────

def gemini_state(tab):
    """Check Gemini tab state: readiness, sign-in, answer count."""
    try:
        state = json.loads(tab.evaluate(JS_STATE))
        state["answers"] = json.loads(tab.evaluate(JS_PROBE))["answers"]
        state["dead"] = False
        return state
    except Exception as e:
        dead = ("закрито" in str(e) or "closed" in str(e).lower()
                or isinstance(e, (OSError, socket.error)))
        return {"ready": False, "signin": False, "url": "",
                "answers": 0, "dead": dead}


def wait_chat(tab, progress, want_empty, deadline, label):
    """Wait until Gemini page is ready with the expected chat state."""
    dead_in_row = 0
    while time.time() < deadline:
        state = gemini_state(tab)
        if state.get("dead"):
            dead_in_row += 1
            if dead_in_row >= 3:
                raise RuntimeError(
                    "Lost connection to Chrome window.\n\n"
                    "This usually happens when Gemini was closed or "
                    "Chrome restarted. Open the window and try again.")
        else:
            dead_in_row = 0
        if state["signin"]:
            raise RuntimeError(
                "Not signed in to Google in the Gemini window.\n\n"
                "Sign in and try again.")
        if state["ready"]:
            if (want_empty is None
                    or bool(state["answers"] == 0) == want_empty):
                return state
            progress(f"{label}: page still loading...")
        time.sleep(1)
    return None
