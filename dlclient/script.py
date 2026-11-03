import base64
import json
import os
import urllib.request

try:
    import quickjs
except ImportError:
    quickjs = None

STOCK_URL = "https://dreamland.rocks/play/defaults.js"
CALL_SECONDS = 0.5
MEMORY = 32 * 1024 * 1024

PRELUDE = r"""
var __h = { text: [], input: [] };
var __out = [];
var __inputValue = '';
function __Q(sel) { this.sel = sel; }
__Q.prototype.on = function (ev, fn) {
  if (typeof fn === 'function' && __h[ev] && (this.sel === '.trigger' || this.sel === '#triggers')) __h[ev].push(fn);
  return this;
};
__Q.prototype.off = function () { if (this.sel === '.trigger') { __h.text = []; __h.input = []; } return this; };
__Q.prototype.val = function (v) {
  if (v === undefined) return __inputValue;
  __inputValue = String(v);
  __out.push(['set_input', __inputValue]);
  return this;
};
['trigger', 'text', 'html', 'append', 'prepend', 'find', 'css', 'addClass', 'removeClass', 'toggleClass',
 'hide', 'show', 'focus', 'blur', 'attr', 'prop', 'each', 'click', 'remove', 'empty'].forEach(function (m) {
  if (!__Q.prototype[m]) __Q.prototype[m] = function () { return this; };
});
function $(sel) { return new __Q(sel); }
$.extend = function (t) { for (var i = 1; i < arguments.length; i++) { var s = arguments[i]; if (s) for (var k in s) t[k] = s[k]; } return t; };
$.ajax = function () { return { then: function () { return this; }, always: function () { return this; } }; };
var window = globalThis;
var console = { log: function () {}, error: function () {}, warn: function () {} };
var localStorage = {};
var mudprompt = {};
var keydown = function (e) {};
function send(s) { __out.push(['send', String(s)]); }
function echo(s) { __out.push(['echo', String(s)]); }
function notify(s) { __out.push(['notify', String(s)]); }
function autobuff() { __out.push(['autobuff', '']); }
function __py_error(s) { __out.push(['error', s]); }
function __drain() { return JSON.stringify(__out.splice(0)); }

function __event() {
  return {
    stopped: false, prevented: false,
    stopPropagation: function () { this.stopped = true; },
    preventDefault: function () { this.prevented = true; },
    stopImmediatePropagation: function () { this.stopped = true; }
  };
}
function __text(line) {
  var e = __event();
  for (var i = 0; i < __h.text.length; i++) {
    try { __h.text[i](e, line); } catch (x) { __py_error(String(x)); }
  }
}
function __input(line) {
  var e = __event();
  for (var i = 0; i < __h.input.length; i++) {
    try { __h.input[i](e, line); } catch (x) { __py_error(String(x)); }
    if (e.stopped) break;
  }
  return e.stopped;
}
function __key(json) {
  var k = JSON.parse(json), e = __event();
  for (var n in k) e[n] = k[n];
  e.keyCode = e.which;
  try { keydown(e); } catch (x) { __py_error(String(x)); }
  return e.prevented;
}
function __prompt(json) {
  var p = JSON.parse(json);
  for (var n in p) mudprompt[n] = p[n];
}
"""

WRAP = "(function () {\n%s\n;return keydown;\n})()"


class ScriptHost:
    def __init__(self, send, echo, notify, autobuff, get_input, set_input, error, cache_dir, bundled):
        self.cb = dict(send=send, echo=echo, notify=notify, autobuff=autobuff,
                       get_input=get_input, set_input=set_input, error=error)
        self.cache_dir = cache_dir
        self.bundled = bundled
        self.ctx = None
        self.source = None
        self.text = ""
        self.errors = 0

    @property
    def available(self):
        return quickjs is not None

    def stock_text(self):
        for path in (os.path.join(self.cache_dir, "defaults.js"), self.bundled):
            try:
                with open(path, encoding="utf-8") as f:
                    return f.read()
            except OSError:
                continue
        return ""

    def fetch_stock(self, timeout=15):
        req = urllib.request.Request(STOCK_URL, headers={"User-Agent": "DreamLand desktop client"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = r.read(1_000_000).decode("utf-8")
        os.makedirs(self.cache_dir, exist_ok=True)
        tmp = os.path.join(self.cache_dir, "defaults.js.part")
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(body)
        os.replace(tmp, os.path.join(self.cache_dir, "defaults.js"))
        return body

    def on_script_data(self, data):
        if not isinstance(data, dict):
            return
        text = ""
        if data.get("account") and isinstance(data.get("b64"), str) and data["b64"]:
            try:
                text = base64.b64decode(data["b64"]).decode("utf-8")
            except (ValueError, UnicodeDecodeError):
                text = ""
        if text:
            self.load(text, "account")
        elif self.source != "stock":
            self.load(self.stock_text(), "stock")

    def load(self, text, source):
        if not self.available:
            return False
        ctx = quickjs.Context()
        ctx.set_memory_limit(MEMORY)
        ctx.set_time_limit(CALL_SECONDS)
        try:
            ctx.eval(PRELUDE)
            kd = ctx.eval(WRAP % text)
            if kd is not None:
                ctx.set("keydown", kd)
        except Exception as e:
            self._error(str(e), loud=True)
            return False
        self.ctx, self.text, self.source = ctx, text, source
        self._drain()
        return True

    def _drain(self):
        try:
            actions = json.loads(self.ctx.eval("__drain()"))
        except Exception:
            return
        for kind, arg in actions:
            if kind == "error":
                self._error(arg)
            elif kind in ("send", "echo", "notify", "set_input"):
                self.cb[kind](arg)
            elif kind == "autobuff":
                self.cb["autobuff"]()

    def _error(self, msg, loud=False):
        self.errors += 1
        if loud:
            self.cb["error"](msg.splitlines()[0] if msg else "")

    def _call(self, fn, *args):
        if not self.ctx:
            return None
        try:
            self.ctx.set("__inputValue", self.cb["get_input"]())
            result = self.ctx.get(fn)(*args)
        except Exception as e:
            self._error(str(e))
            result = None
        self._drain()
        return result

    def on_text(self, line):
        self._call("__text", line)

    def on_input(self, line):
        return bool(self._call("__input", line))

    def on_key(self, which, code, ctrl, alt, shift):
        if not self.ctx:
            return False
        ev = {"which": which, "code": code, "ctrlKey": ctrl, "altKey": alt, "shiftKey": shift,
              "metaKey": False, "key": code}
        return bool(self._call("__key", json.dumps(ev)))

    def on_prompt(self, prompt):
        self._call("__prompt", json.dumps(prompt, ensure_ascii=False))
