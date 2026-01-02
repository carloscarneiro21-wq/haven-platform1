"""
Email Service
=============
Provides email sending functionality with support for:
- SMTP (default)
- SendGrid (if API key configured)

Used for password reset emails and other notifications.
"""

import os
import logging
import smtplib
import hashlib
import secrets
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional, Dict, Any
from datetime import datetime, timezone, timedelta
from pydantic import BaseModel, EmailStr

logger = logging.getLogger(__name__)


class EmailConfig(BaseModel):
    """Email configuration."""
    # SMTP settings
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_pass: str = ""
    smtp_from_email: str = ""
    smtp_from_name: str = "HAVEN Trading System"
    smtp_use_tls: bool = True
    
    # SendGrid settings
    sendgrid_api_key: str = ""
    sendgrid_from_email: str = ""
    sendgrid_from_name: str = "HAVEN Trading System"
    
    # App settings
    app_base_url: str = ""
    app_name: str = "HAVEN"


class EmailService:
    """
    Email service with SMTP and SendGrid support.
    
    Provider selection:
    - If SENDGRID_API_KEY exists -> SendGrid
    - Else -> SMTP
    """
    
    def __init__(self, config: EmailConfig = None):
        self.config = config or self._load_config_from_env()
        self._provider = self._determine_provider()
        logger.info(f"EmailService initialized with provider: {self._provider}")
    
    def _load_config_from_env(self) -> EmailConfig:
        """Load configuration from environment variables."""
        return EmailConfig(
            smtp_host=os.environ.get("SMTP_HOST", "smtp.gmail.com"),
            smtp_port=int(os.environ.get("SMTP_PORT", "587")),
            smtp_user=os.environ.get("SMTP_USER", ""),
            smtp_pass=os.environ.get("SMTP_PASS", ""),
            smtp_from_email=os.environ.get("SMTP_FROM_EMAIL", ""),
            smtp_from_name=os.environ.get("SMTP_FROM_NAME", "HAVEN Trading System"),
            smtp_use_tls=os.environ.get("SMTP_USE_TLS", "true").lower() == "true",
            sendgrid_api_key=os.environ.get("SENDGRID_API_KEY", ""),
            sendgrid_from_email=os.environ.get("SENDGRID_FROM_EMAIL", ""),
            sendgrid_from_name=os.environ.get("SENDGRID_FROM_NAME", "HAVEN Trading System"),
            app_base_url=os.environ.get("APP_BASE_URL", os.environ.get("REACT_APP_BACKEND_URL", "")),
            app_name=os.environ.get("APP_NAME", "HAVEN"),
        )
    
    def _determine_provider(self) -> str:
        """Determine which email provider to use."""
        if self.config.sendgrid_api_key:
            return "sendgrid"
        elif self.config.smtp_user and self.config.smtp_pass:
            return "smtp"
        else:
            return "mock"
    
    def is_configured(self) -> bool:
        """Check if email service is properly configured."""
        return self._provider != "mock"
    
    def get_provider(self) -> str:
        """Get current provider name."""
        return self._provider
    
    async def send_email(
        self,
        to_email: str,
        subject: str,
        html_content: str,
        text_content: str = None,
    ) -> Dict[str, Any]:
        """
        Send an email using the configured provider.
        
        Returns:
            {
                "success": bool,
                "provider": str,
                "message_id": str | None,
                "error": str | None
            }
        """
        if self._provider == "sendgrid":
            return await self._send_sendgrid(to_email, subject, html_content, text_content)
        elif self._provider == "smtp":
            return await self._send_smtp(to_email, subject, html_content, text_content)
        else:
            return await self._send_mock(to_email, subject, html_content, text_content)
    
    async def _send_sendgrid(
        self,
        to_email: str,
        subject: str,
        html_content: str,
        text_content: str = None,
    ) -> Dict[str, Any]:
        """Send email via SendGrid API."""
        try:
            import httpx
            
            from_email = self.config.sendgrid_from_email or self.config.smtp_from_email
            from_name = self.config.sendgrid_from_name
            
            payload = {
                "personalizations": [{"to": [{"email": to_email}]}],
                "from": {"email": from_email, "name": from_name},
                "subject": subject,
                "content": []
            }
            
            if text_content:
                payload["content"].append({"type": "text/plain", "value": text_content})
            payload["content"].append({"type": "text/html", "value": html_content})
            
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    "https://api.sendgrid.com/v3/mail/send",
                    json=payload,
                    headers={
                        "Authorization": f"Bearer {self.config.sendgrid_api_key}",
                        "Content-Type": "application/json"
                    },
                    timeout=30.0
                )
                
                if response.status_code in [200, 202]:
                    message_id = response.headers.get("X-Message-Id", "")
                    logger.info(f"Email sent via SendGrid to {to_email}")
                    return {
                        "success": True,
                        "provider": "sendgrid",
                        "message_id": message_id,
                        "error": None
                    }
                else:
                    error = f"SendGrid error: {response.status_code} - {response.text}"
                    logger.error(error)
                    return {
                        "success": False,
                        "provider": "sendgrid",
                        "message_id": None,
                        "error": error
                    }
        except Exception as e:
            error = f"SendGrid exception: {str(e)}"
            logger.error(error)
            return {
                "success": False,
                "provider": "sendgrid",
                "message_id": None,
                "error": error
            }
    
    async def _send_smtp(
        self,
        to_email: str,
        subject: str,
        html_content: str,
        text_content: str = None,
    ) -> Dict[str, Any]:
        """Send email via SMTP."""
        try:
            from_email = self.config.smtp_from_email or self.config.smtp_user
            from_name = self.config.smtp_from_name
            
            # Create message
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = f"{from_name} <{from_email}>"
            msg["To"] = to_email
            
            if text_content:
                msg.attach(MIMEText(text_content, "plain"))
            msg.attach(MIMEText(html_content, "html"))
            
            # Connect and send
            if self.config.smtp_use_tls:
                server = smtplib.SMTP(self.config.smtp_host, self.config.smtp_port)
                server.starttls()
            else:
                server = smtplib.SMTP_SSL(self.config.smtp_host, self.config.smtp_port)
            
            server.login(self.config.smtp_user, self.config.smtp_pass)
            server.sendmail(from_email, to_email, msg.as_string())
            server.quit()
            
            logger.info(f"Email sent via SMTP to {to_email}")
            return {
                "success": True,
                "provider": "smtp",
                "message_id": None,
                "error": None
            }
        except Exception as e:
            error = f"SMTP exception: {str(e)}"
            logger.error(error)
            return {
                "success": False,
                "provider": "smtp",
                "message_id": None,
                "error": error
            }
    
    async def _send_mock(
        self,
        to_email: str,
        subject: str,
        html_content: str,
        text_content: str = None,
    ) -> Dict[str, Any]:
        """Mock email sending (for development/testing)."""
        logger.warning(f"[MOCK EMAIL] To: {to_email}, Subject: {subject}")
        logger.warning("[MOCK EMAIL] Email service not configured. Set SMTP credentials.")
        return {
            "success": True,
            "provider": "mock",
            "message_id": f"mock-{secrets.token_hex(8)}",
            "error": None,
            "warning": "Email not actually sent - service not configured"
        }
    
    # ==================== Password Reset Emails ====================
    
    def _get_password_reset_html(self, reset_url: str, username: str) -> str:
        """Generate HTML content for password reset email."""
        return f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Password Reset - {self.config.app_name}</title>
</head>
<body style="margin: 0; padding: 0; background-color: #0B0E11; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;">
    <table width="100%" cellpadding="0" cellspacing="0" style="background-color: #0B0E11; padding: 40px 20px;">
        <tr>
            <td align="center">
                <table width="100%" style="max-width: 500px; background-color: #1E2329; border-radius: 12px; overflow: hidden;">
                    <!-- Header -->
                    <tr>
                        <td style="background-color: #F0B90B; padding: 30px; text-align: center;">
                            <h1 style="margin: 0; color: #0B0E11; font-size: 28px; font-weight: bold; letter-spacing: 2px;">
                                {self.config.app_name}
                            </h1>
                        </td>
                    </tr>
                    
                    <!-- Content -->
                    <tr>
                        <td style="padding: 40px 30px;">
                            <h2 style="margin: 0 0 20px; color: #EAECEF; font-size: 22px;">
                                Password Reset Request
                            </h2>
                            
                            <p style="margin: 0 0 15px; color: #B7BDC6; font-size: 14px; line-height: 1.6;">
                                Hello <strong style="color: #EAECEF;">{username}</strong>,
                            </p>
                            
                            <p style="margin: 0 0 25px; color: #B7BDC6; font-size: 14px; line-height: 1.6;">
                                You requested a password reset. Click the button below to reset your password.
                            </p>
                            
                            <!-- Button -->
                            <table width="100%" cellpadding="0" cellspacing="0">
                                <tr>
                                    <td align="center" style="padding: 10px 0 30px;">
                                        <a href="{reset_url}" 
                                           style="display: inline-block; padding: 14px 40px; background-color: #F0B90B; color: #0B0E11; text-decoration: none; font-weight: bold; font-size: 14px; border-radius: 6px;">
                                            Reset Password
                                        </a>
                                    </td>
                                </tr>
                            </table>
                            
                            <!-- Warning -->
                            <div style="background-color: #2B3139; border-radius: 8px; padding: 15px; margin-bottom: 20px;">
                                <p style="margin: 0; color: #848E9C; font-size: 12px; line-height: 1.5;">
                                    ⚠️ This link will expire in <strong style="color: #F0B90B;">15 minutes</strong>.
                                </p>
                                <p style="margin: 10px 0 0; color: #848E9C; font-size: 12px; line-height: 1.5;">
                                    If you didn't request this reset, you can safely ignore this email.
                                </p>
                            </div>
                            
                            <!-- Link fallback -->
                            <p style="margin: 0; color: #848E9C; font-size: 11px; word-break: break-all;">
                                If the button doesn't work, copy this link:<br>
                                <a href="{reset_url}" style="color: #F0B90B; text-decoration: none;">{reset_url}</a>
                            </p>
                        </td>
                    </tr>
                    
                    <!-- Footer -->
                    <tr>
                        <td style="background-color: #161A1E; padding: 20px 30px; border-top: 1px solid #2B3139;">
                            <p style="margin: 0; color: #848E9C; font-size: 11px; text-align: center;">
                                This is an automated message from {self.config.app_name}.<br>
                                Please do not reply to this email.
                            </p>
                        </td>
                    </tr>
                </table>
            </td>
        </tr>
    </table>
</body>
</html>
"""
    
    def _get_password_reset_text(self, reset_url: str, username: str) -> str:
        """Generate plain text content for password reset email."""
        return f"""
{self.config.app_name} - Password Reset

You requested a password reset.
Click the link below to reset your password:
{reset_url}
This link expires in 15 minutes.
If you did not request this, ignore this email.

---
This is an automated message from {self.config.app_name}.
"""
    
    async def send_password_reset_email(
        self,
        to_email: str,
        username: str,
        reset_token: str,
    ) -> Dict[str, Any]:
        """
        Send password reset email.
        
        Args:
            to_email: User's email address
            username: User's username (for personalization)
            reset_token: The reset token (will be included in URL)
        
        Returns:
            Email send result
        """
        # Build reset URL
        base_url = self.config.app_base_url.rstrip("/")
        # Remove /api suffix if present for frontend URL
        if base_url.endswith("/api"):
            base_url = base_url[:-4]
        reset_url = f"{base_url}/reset-password?token={reset_token}"
        
        subject = "Reset your HAVEN password"
        html_content = self._get_password_reset_html(reset_url, username)
        text_content = self._get_password_reset_text(reset_url, username)
        
        result = await self.send_email(to_email, subject, html_content, text_content)
        
        # Log (without sensitive data)
        if result["success"]:
            logger.info(f"Password reset email sent to {to_email[:3]}***@*** via {result['provider']}")
        else:
            logger.error(f"Failed to send password reset email: {result['error']}")
        
        return result


# ==================== Token Utilities ====================

def hash_token(token: str) -> str:
    """Hash a token using SHA-256."""
    return hashlib.sha256(token.encode()).hexdigest()


def generate_reset_token() -> tuple[str, str]:
    """
    Generate a secure reset token and its hash.
    
    Returns:
        (raw_token, token_hash)
    """
    raw_token = secrets.token_urlsafe(32)
    token_hash = hash_token(raw_token)
    return raw_token, token_hash


# Global instance
email_service: EmailService = None


def get_email_service() -> EmailService:
    """Get or create the email service instance."""
    global email_service
    if email_service is None:
        email_service = EmailService()
    return email_service
