r"""Drive chatgpt.com with Playwright using your own logged-in browser profile.

Setup (Windows):
    python -m venv .venv
    .venv\Scripts\activate
    pip install -r requirements.txt

Optional first run to log in (visible browser):
    python chatgpt_playwright.py --login
Then:
    python chatgpt_playwright.py "hello" "what is 2+2?"
    python chatgpt_playwright.py --headed "hello"

From other code:
    from chatgpt_playwright import ChatSession, ask_chatgpt

    reply = ask_chatgpt("hello")  # one-off, fresh conversation

    with ChatSession() as s:      # context preserved between asks
        s.ask("my name is Alex")
        s.ask("what's my name?")
        url = s.url               # save to resume later: ChatSession(conversation_url=url)
"""
import functools
import subprocess
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

__all__ = ["ChatSession", "ask_chatgpt", "chat", "login"]

BASE_URL = "https://chatgpt.com/"
PROFILE_DIR = Path(__file__).parent / ".pw-profile"
PROMPT = "#prompt-textarea"
ASSISTANT = '[data-message-author-role="assistant"]'
STOP_BUTTON = '[data-testid="stop-button"]'


@functools.cache
def _ensure_browser() -> None:
    # pip only installs the library; the browser binary is a separate download (no-op if present)
    subprocess.run([sys.executable, "-m", "playwright", "install", "firefox"], check=True)


def login() -> None:
    _ensure_browser()
    with sync_playwright() as p:
        ctx = p.firefox.launch_persistent_context(PROFILE_DIR, headless=False)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto(BASE_URL)
        input("Log in in the browser window, then press Enter here...")
        ctx.close()


class ChatSession:
    """One browser + one ChatGPT conversation kept open across ask() calls.

    Must be used from the thread that created it (Playwright sync API limitation).
    """

    def __init__(self, conversation_url: str | None = None, headless: bool = True):
        self.conversation_url = conversation_url
        self.headless = headless
        self._pw = self._ctx = self.page = None

    def open(self) -> "ChatSession":
        _ensure_browser()
        self._pw = sync_playwright().start()
        self._ctx = self._pw.firefox.launch_persistent_context(PROFILE_DIR, headless=self.headless)
        self.page = self._ctx.pages[0] if self._ctx.pages else self._ctx.new_page()
        self.page.goto(self.conversation_url or BASE_URL)
        try:
            self.page.locator(PROMPT).wait_for(timeout=30_000)
        except Exception:
            self.page.screenshot(path="debug.png", full_page=True)
            title, url = self.page.title(), self.page.url
            self.close()
            raise RuntimeError(f"Chat box not found. title={title!r} url={url} (see debug.png)") from None
        return self

    def ask(self, message: str) -> str:
        if self.page is None:
            self.open()
        return ask(self.page, message)

    @property
    def url(self) -> str | None:
        """Conversation URL (chatgpt.com/c/<id>) once the first reply exists; pass it back to resume."""
        return self.page.url if self.page else self.conversation_url

    def close(self) -> None:
        if self.page:
            self.conversation_url = self.page.url
        if self._ctx:
            self._ctx.close()
        if self._pw:
            self._pw.stop()
        self._pw = self._ctx = self.page = None

    def __enter__(self) -> "ChatSession":
        return self.open()

    def __exit__(self, *exc) -> None:
        self.close()


def ask(page, message: str) -> str:
    before = page.locator(ASSISTANT).count()
    page.locator(PROMPT).fill(message)
    page.keyboard.press("Enter")
    page.locator(ASSISTANT).nth(before).wait_for(timeout=60_000)
    # Streaming is done once the stop button disappears
    page.locator(STOP_BUTTON).wait_for(state="detached", timeout=120_000)
    return page.locator(ASSISTANT).nth(before).inner_text()


def chat(messages: list[str], headless: bool = True) -> list[str]:
    """Send messages in one conversation and return the replies in order."""
    with ChatSession(headless=headless) as s:
        return [s.ask(msg) for msg in messages]


def ask_chatgpt(query: str, headless: bool = True) -> str:
    """Send one query in a new conversation and return the reply text."""
    return chat([query], headless=headless)[0]


if __name__ == "__main__":
    args = sys.argv[1:]
    if args[:1] == ["--login"]:
        login()
    else:
        messages = [a for a in args if a != "--headed"] or ["hello"]
        for msg, reply in zip(messages, chat(messages, headless="--headed" not in args)):
            print(f"> {msg}\n{reply}\n")
