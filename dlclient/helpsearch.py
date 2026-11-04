import gzip
import json
import os
import threading
import time
import urllib.request

try:
    import quickjs
except Exception:
    quickjs = None

BASE = "https://dreamland.rocks/"
CORE = "site/js/helpsearch.js"
FILES = {"core": CORE, "index": "data/help-index.json"}
MAX_AGE = 24 * 3600
LANGS = ("ru", "en", "ua")

GLUE = r"""
var S = globalThis.DLHelpSearch;
var CACHE = {};
function __textFor(lang) {
    if (!CACHE[lang]) {
        var over = OVERLAY[lang] || {};
        CACHE[lang] = S.textCache(function (id) {
            var o = over[id];
            return o != null && o !== '' ? o : (RU[id] || '');
        });
    }
    return CACHE[lang];
}
function __search(query, lang, limit) {
    var full = S.normQuery(query);
    var p = S.parseQuery(full);
    if (!p.q) return JSON.stringify({ found: [], suggested: false });
    var textFor = __textFor(lang);
    var found = S.search(INDEX, p.q, lang, textFor, limit, p.test);
    var out = [];
    var suggested = false;
    if (found.length) {
        found.forEach(function (a) {
            var k = S.kind(a);
            var ex = S.excerpt(textFor(a.id), p.q);
            var extra = ex && (ex[0] + ex[1] + ex[2]) !== '' ? (ex[0] + ex[1] + ex[2])
                : (a.kwList || []).slice(0, 4).join(', ').toLowerCase();
            out.push({ id: a.id, title: S.label(a, lang), kind: k ? k[lang] : '', extra: S.squash(extra) });
        });
    } else {
        suggested = true;
        S.fuzzy(INDEX, full, lang).forEach(function (h) {
            var k = S.kind(h.article);
            out.push({ id: h.article.id, title: S.label(h.article, lang), kind: k ? k[lang] : '',
                       extra: S.fuzzyHint(h, lang) });
        });
    }
    return JSON.stringify({ found: out, suggested: suggested });
}
"""


def _norm(lang):
    return lang if lang in LANGS else "en"


class HelpSearch:
    def __init__(self, folder):
        self.folder = os.path.join(folder, "help")
        os.makedirs(self.folder, exist_ok=True)
        self.ctx = None
        self.loaded = set()
        self.lock = threading.Lock()

    def _path(self, name):
        return os.path.join(self.folder, name.replace("/", "_"))

    def _fetch(self, rel, timeout=30):
        path = self._path(rel)
        fresh = os.path.exists(path) and time.time() - os.path.getmtime(path) < MAX_AGE
        if not fresh:
            try:
                body = None
                if rel.endswith(".json"):
                    try:
                        req = urllib.request.Request(BASE + rel + ".gz", headers={"User-Agent": "DreamLand desktop client"})
                        with urllib.request.urlopen(req, timeout=timeout) as r:
                            body = gzip.decompress(r.read(50_000_000))
                    except Exception:
                        body = None
                if body is None:
                    req = urllib.request.Request(BASE + rel, headers={"User-Agent": "DreamLand desktop client"})
                    with urllib.request.urlopen(req, timeout=timeout) as r:
                        body = r.read(50_000_000)
                if rel.endswith(".json"):
                    json.loads(body.decode("utf-8"))
                elif body.lstrip().startswith(b"<"):
                    raise ValueError("not a script")
                with open(path + ".part", "wb") as f:
                    f.write(body)
                os.replace(path + ".part", path)
            except Exception:
                if not os.path.exists(path):
                    raise
        with open(path, encoding="utf-8") as f:
            return f.read()

    def prepare(self, lang):
        lang = _norm(lang)
        with self.lock:
            if self.ctx is None:
                if quickjs is None:
                    raise RuntimeError("no JavaScript engine")
                ctx = quickjs.Context()
                ctx.set_memory_limit(512 * 1024 * 1024)
                ctx.eval(self._fetch(FILES["core"]))
                ctx.set("__raw", self._fetch(FILES["index"]))
                ctx.eval("var INDEX = JSON.parse(__raw); __raw = ''; var OVERLAY = {}; var RU = {};")
                ctx.set("__raw", self._fetch("data/help-body-ru.json"))
                ctx.eval("RU = JSON.parse(__raw); __raw = '';")
                ctx.eval(GLUE)
                self.ctx = ctx
                self.loaded = {"ru"}
            if lang not in self.loaded:
                self.ctx.set("__raw", self._fetch("data/help-body-%s.json" % lang))
                self.ctx.eval("OVERLAY[%s] = JSON.parse(__raw); __raw = '';" % json.dumps(lang))
                self.loaded.add(lang)

    def search(self, query, lang, limit=24):
        lang = _norm(lang)
        self.prepare(lang)
        with self.lock:
            self.ctx.set("__q", query)
            data = json.loads(self.ctx.eval("__search(__q, %s, %d)" % (json.dumps(lang), int(limit))))
        return data["found"], data["suggested"]
