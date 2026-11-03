try:
    from accessible_output2.outputs.auto import Auto
except Exception:
    Auto = None


class Speech:
    def __init__(self):
        self.out = None
        if Auto:
            try:
                self.out = Auto()
            except Exception:
                self.out = None

    def say(self, text, interrupt=False):
        if self.out and text and text.strip():
            try:
                self.out.speak(text, interrupt=interrupt)
            except Exception:
                pass

    def silence(self):
        if self.out:
            try:
                self.out.speak("", interrupt=True)
            except Exception:
                pass
