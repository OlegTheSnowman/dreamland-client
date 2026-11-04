import json
import threading
import time

import websocket

URL = "wss://dreamland.rocks/dreamland"
PROTO_VERSION = "DreamLand Web Client/2.1"
KEEPALIVE = 25
RECONNECT_MAX = 15


class Connection:
    def __init__(self, on_frame, on_state):
        self.url = URL
        self.on_frame = on_frame
        self.on_state = on_state
        self.ws = None
        self.thread = None
        self.resume_token = None
        self.in_world = False
        self.resume_pending = False
        self.wanted = False
        self.lock = threading.Lock()
        self._last_ping = 0
        self._retries = 0
        self._resume_retries = 0
        self._resume_delay = 0

    def connect(self):
        self.wanted = True
        self._retries = 0
        if self.thread and self.thread.is_alive():
            return
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def disconnect(self):
        self.wanted = False
        self.resume_token = None
        ws = self.ws
        if ws:
            try:
                ws.close()
            except Exception:
                pass

    def ended(self):
        """The game said goodbye after quit: let the socket close for good."""
        self.wanted = False
        self.resume_token = None

    def send_line(self, text):
        return self.rpc("console_in", text + "\n")

    def rpc(self, command, *args):
        ws = self.ws
        if not ws or not ws.sock or not ws.sock.connected:
            return False
        try:
            with self.lock:
                ws.send(json.dumps({"command": command, "args": list(args)}))
            return True
        except Exception:
            return False

    @property
    def is_open(self):
        ws = self.ws
        return bool(ws and ws.sock and ws.sock.connected)

    def _run(self):
        delay = 0
        while self.wanted:
            self.in_world = False
            self.on_state("connecting" if not self.resume_token else "reconnecting", None)
            self.ws = websocket.WebSocketApp(
                self.url or URL,
                subprotocols=["binary"],
                header={"User-Agent": "DreamLand desktop client"},
                on_open=self._on_open,
                on_message=self._on_message,
                on_error=lambda ws, e: None,
            )
            self.ws.run_forever(ping_interval=0)
            self.ws = None
            if not self.wanted:
                break
            if not self.resume_token:
                break
            if self._resume_delay:
                delay, self._resume_delay = self._resume_delay, 0
            else:
                self._retries += 1
                if self._retries > 8:
                    self.resume_token = None
                    break
                self.on_state("reconnecting", self._retries)
                delay = min(delay * 2 if delay else 0.5, RECONNECT_MAX)
            time.sleep(delay)
        self.on_state("closed", None)

    def _on_open(self, ws):
        self.on_state("open", None)
        if self.resume_token:
            self.resume_pending = True
            self.rpc("resume", self.resume_token)
        else:
            self._answer_codepage()
        threading.Thread(target=self._keepalive, args=(ws,), daemon=True).start()

    def _answer_codepage(self):
        self.send_line("1")

    def _keepalive(self, ws):
        while self.ws is ws and ws.sock and ws.sock.connected:
            time.sleep(1)
            if self.in_world and time.time() - self._last_ping >= KEEPALIVE:
                self._last_ping = time.time()
                self.rpc("ping")

    def _on_message(self, ws, msg):
        if isinstance(msg, bytes):
            msg = msg.decode("utf-8", "replace")
        try:
            frame = json.loads(msg)
        except ValueError:
            return
        command = frame.get("command")
        args = frame.get("args") or []
        if command == "prompt":
            self.in_world = True
            self._retries = 0
            if args and isinstance(args[0], dict) and args[0].get("resume"):
                self.resume_token = args[0]["resume"]
        elif command == "resume_ok":
            self._resume_retries = 0
            self.resume_pending = False
            self.in_world = True
            self._retries = 0
            if args and args[0]:
                self.resume_token = args[0]
        elif command == "resume_failed":
            reason = args[0] if args else None
            if reason != "final" and self._resume_retries < 5:
                self._resume_retries += 1
                self._resume_delay = min(0.8 * self._resume_retries, 3)
                try:
                    ws.close()
                except Exception:
                    pass
                return
            self.resume_token = None
            self.resume_pending = False
            self._resume_retries = 0
            self._answer_codepage()
        self.on_frame(command, args)
