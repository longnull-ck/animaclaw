"""
Anima — Email Tool
邮件收发功能。支持通过 SMTP 发送邮件，通过 IMAP 读取邮件。

环境变量配置：
  ANIMA_SMTP_HOST       SMTP 服务器地址（如 smtp.gmail.com）
  ANIMA_SMTP_PORT       SMTP 端口（默认 587）
  ANIMA_SMTP_USER       SMTP 用户名（邮箱地址）
  ANIMA_SMTP_PASSWORD   SMTP 密码/应用专用密码
  ANIMA_IMAP_HOST       IMAP 服务器地址（如 imap.gmail.com）
  ANIMA_IMAP_PORT       IMAP 端口（默认 993）
"""

from __future__ import annotations

import asyncio
import email
import email.mime.text
import email.mime.multipart
import logging
import os
import smtplib
import ssl
from datetime import datetime
from email.header import decode_header
from imaplib import IMAP4_SSL
from typing import Any

logger = logging.getLogger("anima.tools.email")


async def tool_email(args: dict) -> str:
    """
    邮件工具：发送或读取邮件。

    args:
      action: str        "send" 或 "read"（必填）

      # 发送时的参数：
      to: str            收件人邮箱（多个用逗号分隔）
      subject: str       主题
      body: str          正文（纯文本）
      cc: str            抄送（可选）

      # 读取时的参数：
      folder: str        邮箱文件夹（默认 INBOX）
      count: int         读取最近 N 封（默认 5）
      unread_only: bool  只读取未读邮件（默认 True）
    """
    action = args.get("action", "").lower()

    if action == "send":
        return await _send_email(args)
    elif action == "read":
        return await _read_email(args)
    else:
        return "[错误] action 必须是 'send' 或 'read'"


async def _send_email(args: dict) -> str:
    """发送邮件"""
    to = args.get("to", "")
    subject = args.get("subject", "")
    body = args.get("body", "")
    cc = args.get("cc", "")

    if not to:
        return "[错误] 缺少收件人 to"
    if not subject:
        return "[错误] 缺少邮件主题 subject"
    if not body:
        return "[错误] 缺少邮件正文 body"

    # 读取配置
    smtp_host = os.getenv("ANIMA_SMTP_HOST", "")
    smtp_port = int(os.getenv("ANIMA_SMTP_PORT", "587"))
    smtp_user = os.getenv("ANIMA_SMTP_USER", "")
    smtp_pass = os.getenv("ANIMA_SMTP_PASSWORD", "")

    if not all([smtp_host, smtp_user, smtp_pass]):
        return (
            "[错误] 邮件未配置。请在 .env 中设置：\n"
            "  ANIMA_SMTP_HOST=smtp.example.com\n"
            "  ANIMA_SMTP_USER=your@email.com\n"
            "  ANIMA_SMTP_PASSWORD=your_password"
        )

    try:
        # 在线程中执行（smtplib 是同步的）
        result = await asyncio.to_thread(
            _smtp_send, smtp_host, smtp_port, smtp_user, smtp_pass,
            to, subject, body, cc
        )
        return result
    except Exception as e:
        logger.error(f"[email] 发送失败: {e}")
        return f"[发送失败] {e}"


def _smtp_send(
    host: str, port: int, user: str, password: str,
    to: str, subject: str, body: str, cc: str,
) -> str:
    """同步发送邮件"""
    msg = email.mime.multipart.MIMEMultipart()
    msg["From"] = user
    msg["To"] = to
    msg["Subject"] = subject
    if cc:
        msg["Cc"] = cc

    msg.attach(email.mime.text.MIMEText(body, "plain", "utf-8"))

    recipients = [addr.strip() for addr in to.split(",")]
    if cc:
        recipients += [addr.strip() for addr in cc.split(",")]

    context = ssl.create_default_context()

    with smtplib.SMTP(host, port) as server:
        server.starttls(context=context)
        server.login(user, password)
        server.sendmail(user, recipients, msg.as_string())

    return f"邮件已发送至 {to}（主题: {subject}）"


async def _read_email(args: dict) -> str:
    """读取邮件"""
    folder = args.get("folder", "INBOX")
    count = int(args.get("count", 5))
    unread_only = args.get("unread_only", True)

    imap_host = os.getenv("ANIMA_IMAP_HOST", "")
    imap_port = int(os.getenv("ANIMA_IMAP_PORT", "993"))
    imap_user = os.getenv("ANIMA_SMTP_USER", "")  # 通常和 SMTP 用同一个账号
    imap_pass = os.getenv("ANIMA_SMTP_PASSWORD", "")

    if not all([imap_host, imap_user, imap_pass]):
        return (
            "[错误] IMAP 未配置。请在 .env 中设置：\n"
            "  ANIMA_IMAP_HOST=imap.example.com\n"
            "  ANIMA_SMTP_USER=your@email.com\n"
            "  ANIMA_SMTP_PASSWORD=your_password"
        )

    try:
        result = await asyncio.to_thread(
            _imap_read, imap_host, imap_port, imap_user, imap_pass,
            folder, count, unread_only
        )
        return result
    except Exception as e:
        logger.error(f"[email] 读取失败: {e}")
        return f"[读取失败] {e}"


def _imap_read(
    host: str, port: int, user: str, password: str,
    folder: str, count: int, unread_only: bool,
) -> str:
    """同步读取邮件"""
    conn = IMAP4_SSL(host, port)
    conn.login(user, password)
    conn.select(folder)

    # 搜索条件
    criteria = "UNSEEN" if unread_only else "ALL"
    _, msg_nums = conn.search(None, criteria)

    if not msg_nums[0]:
        conn.logout()
        return f"{'未读' if unread_only else ''}邮件为空"

    # 取最近 N 封
    ids = msg_nums[0].split()[-count:]
    results: list[str] = []

    for msg_id in reversed(ids):  # 最新的在前
        _, msg_data = conn.fetch(msg_id, "(RFC822)")
        raw = msg_data[0][1]
        msg = email.message_from_bytes(raw)

        # 解码主题
        subject_raw = msg.get("Subject", "")
        subject = _decode_mime_header(subject_raw)

        # 解码发件人
        from_raw = msg.get("From", "")
        from_addr = _decode_mime_header(from_raw)

        # 日期
        date_str = msg.get("Date", "")

        # 正文
        body = _get_email_body(msg)

        results.append(
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"发件人: {from_addr}\n"
            f"主题: {subject}\n"
            f"时间: {date_str}\n"
            f"内容: {body[:500]}\n"
        )

    conn.logout()

    header = f"最近 {len(results)} 封{'未读' if unread_only else ''}邮件：\n\n"
    return header + "\n".join(results)


def _decode_mime_header(header: str) -> str:
    """解码 MIME 编码的邮件头"""
    try:
        decoded_parts = decode_header(header)
        result = ""
        for part, charset in decoded_parts:
            if isinstance(part, bytes):
                result += part.decode(charset or "utf-8", errors="replace")
            else:
                result += part
        return result
    except Exception:
        return header


def _get_email_body(msg) -> str:
    """提取邮件正文"""
    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            if content_type == "text/plain":
                payload = part.get_payload(decode=True)
                if payload:
                    charset = part.get_content_charset() or "utf-8"
                    return payload.decode(charset, errors="replace")
        return "(无纯文本正文)"
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            charset = msg.get_content_charset() or "utf-8"
            return payload.decode(charset, errors="replace")
        return ""
