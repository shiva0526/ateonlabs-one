import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from app.core.config import settings

logger = logging.getLogger("ateon.email")

def send_otp_email(to_email: str, otp_code: str, user_name: str = "User") -> bool:
    """
    Send a 6-digit OTP verification code to the user's email address.
    If SMTP settings are configured in .env, sends via SMTP.
    Always logs the code to the server console for immediate development visibility.
    """
    subject = f"Your ATEON One Verification Code: {otp_code}"
    from_email = settings.SMTP_FROM_EMAIL or settings.SMTP_USER or "security@ateonlabs.com"

    text_content = f"""Hello {user_name},

Your ATEON One 6-digit verification code is:

{otp_code}

This code is valid for 10 minutes. Please enter this code on the sign-in screen to complete your login.
If you did not request this login code, please secure your account immediately.

Regards,
ATEON Labs Security Team
"""

    html_content = f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>Your Verification Code</title>
</head>
<body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background-color: #f5f5f7; margin: 0; padding: 40px 20px;">
  <div style="max-width: 480px; margin: 0 auto; background: #ffffff; border-radius: 20px; overflow: hidden; border: 1px solid #e5e7eb; box-shadow: 0 4px 16px rgba(0,0,0,0.04);">
    <div style="background: #111827; padding: 28px 24px; text-align: center;">
      <h1 style="color: #ffffff; font-size: 20px; font-weight: 600; margin: 0; letter-spacing: -0.02em;">ATEON One</h1>
      <p style="color: #9ca3af; font-size: 13px; margin: 4px 0 0 0;">Authentication &amp; Security</p>
    </div>
    <div style="padding: 32px 28px; text-align: center;">
      <p style="color: #374151; font-size: 15px; margin: 0 0 20px 0;">Hello <strong>{user_name}</strong>,</p>
      <p style="color: #6b7280; font-size: 14px; margin: 0 0 24px 0;">Enter this 6-digit verification code to complete your login:</p>
      
      <div style="background: #f9fafb; border: 2px dashed #d1d5db; border-radius: 12px; padding: 18px 24px; display: inline-block; margin-bottom: 24px;">
        <span style="font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace; font-size: 32px; font-weight: 700; letter-spacing: 8px; color: #111827;">{otp_code}</span>
      </div>

      <p style="color: #9ca3af; font-size: 12px; margin: 0;">This code expires in 10 minutes. Do not share this code with anyone.</p>
    </div>
    <div style="background: #f9fafb; padding: 16px; text-align: center; border-top: 1px solid #f3f4f6;">
      <p style="color: #9ca3af; font-size: 11px; margin: 0;">&copy; ATEON Labs. If you did not request this email, please ignore it.</p>
    </div>
  </div>
</body>
</html>
"""

    # Always print clearly to server console so it's instantly visible
    banner = f"""
==========================================================
>>> [2FA OTP] Verification Code for {to_email}: {otp_code}
==========================================================
"""
    try:
        print(banner, flush=True)
    except Exception:
        pass
    logger.info(f"Verification code generated for {to_email}: {otp_code}")

    # Check if SMTP is configured
    if not (settings.SMTP_HOST and settings.SMTP_USER and settings.SMTP_PASSWORD):
        logger.warning(f"SMTP credentials not fully configured. Code printed to console above.")
        return False

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = f"ATEON Security <{from_email}>"
        msg["To"] = to_email

        msg.attach(MIMEText(text_content, "plain", "utf-8"))
        msg.attach(MIMEText(html_content, "html", "utf-8"))

        if settings.SMTP_SSL or settings.SMTP_PORT == 465:
            server = smtplib.SMTP_SSL(settings.SMTP_HOST, settings.SMTP_PORT, timeout=10)
        else:
            server = smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=10)
            if settings.SMTP_TLS:
                server.starttls()

        server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
        server.send_message(msg)
        server.quit()
        logger.info(f"Successfully sent OTP email to {to_email}")
        return True
    except Exception as e:
        logger.error(f"Failed to send OTP email via SMTP to {to_email}: {e}")
        return False


def send_invite_email(to_email: str, name: str, role: str, temp_password: str) -> bool:
    """
    Send a welcome/invitation email with a temporary password to a newly
    created user. Uses the same SMTP pipeline as OTP emails.
    """
    subject = "Welcome to ATEON One"
    from_email = settings.SMTP_FROM_EMAIL or settings.SMTP_USER or "hr@ateonlabs.com"

    text_content = f"""Hello {name},

You have been invited to ATEON One as a {role.upper()}.
Your temporary password is: {temp_password}

Please log in and change your password immediately.

Regards,
ATEON Labs HR Team
"""

    html_content = f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><title>Welcome to ATEON One</title></head>
<body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background-color: #f5f5f7; margin: 0; padding: 40px 20px;">
  <div style="max-width: 480px; margin: 0 auto; background: #ffffff; border-radius: 20px; overflow: hidden; border: 1px solid #e5e7eb; box-shadow: 0 4px 16px rgba(0,0,0,0.04);">
    <div style="background: #111827; padding: 28px 24px; text-align: center;">
      <h1 style="color: #ffffff; font-size: 20px; font-weight: 600; margin: 0;">ATEON One</h1>
      <p style="color: #9ca3af; font-size: 13px; margin: 4px 0 0 0;">Team Invitation</p>
    </div>
    <div style="padding: 32px 28px;">
      <p style="color: #374151; font-size: 15px; margin: 0 0 16px 0;">Hello <strong>{name}</strong>,</p>
      <p style="color: #6b7280; font-size: 14px; margin: 0 0 20px 0;">You have been invited to ATEON One as <strong>{role.upper()}</strong>.</p>
      <p style="color: #6b7280; font-size: 14px; margin: 0 0 8px 0;">Your temporary password is:</p>
      <div style="background: #f9fafb; border: 2px dashed #d1d5db; border-radius: 12px; padding: 14px 24px; text-align: center; margin-bottom: 20px;">
        <span style="font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace; font-size: 18px; font-weight: 700; color: #111827;">{temp_password}</span>
      </div>
      <p style="color: #ef4444; font-size: 13px; margin: 0;">Please log in and change your password immediately.</p>
    </div>
    <div style="background: #f9fafb; padding: 16px; text-align: center; border-top: 1px solid #f3f4f6;">
      <p style="color: #9ca3af; font-size: 11px; margin: 0;">&copy; ATEON Labs</p>
    </div>
  </div>
</body>
</html>
"""

    logger.info(f"Sending invite email to {to_email} (role={role})")

    if not (settings.SMTP_HOST and settings.SMTP_USER and settings.SMTP_PASSWORD):
        logger.warning("SMTP not configured — invite email not sent.")
        return False

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = f"ATEON HR <{from_email}>"
        msg["To"] = to_email

        msg.attach(MIMEText(text_content, "plain", "utf-8"))
        msg.attach(MIMEText(html_content, "html", "utf-8"))

        if settings.SMTP_SSL or settings.SMTP_PORT == 465:
            server = smtplib.SMTP_SSL(settings.SMTP_HOST, settings.SMTP_PORT, timeout=10)
        else:
            server = smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=10)
            if settings.SMTP_TLS:
                server.starttls()

        server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
        server.send_message(msg)
        server.quit()
        logger.info(f"Successfully sent invite email to {to_email}")
        return True
    except Exception as e:
        logger.error(f"Failed to send invite email to {to_email}: {e}")
        return False

