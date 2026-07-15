"""
邮件发送模块
通过 SMTP (SSL/TLS) 发送日报邮件
"""

import smtplib
import ssl
from email.mime.text import MIMEText
from email.header import Header
from email.utils import formataddr
from typing import List, Dict


def send_report(smtp_config: dict,
                recipients: List[Dict[str, str]],
                subject: str,
                body: str) -> bool:
    """
    发送日报邮件

    Args:
        smtp_config: SMTP 配置 (host/port/use_ssl/username/password/sender_name)
        recipients: 收件人列表 [{"name": "", "email": ""}]
        subject: 邮件标题
        body: 邮件正文（纯文本）

    Returns:
        True=成功, False=失败
    """
    if not recipients:
        return False

    host = smtp_config['host']
    port = smtp_config['port']
    use_ssl = smtp_config.get('use_ssl', True)
    username = smtp_config['username']
    password = smtp_config['password']
    sender_name = smtp_config.get('sender_name', username)

    to_addrs = [r['email'] for r in recipients]

    msg = MIMEText(body, 'plain', 'utf-8')
    msg['From'] = formataddr((str(Header(sender_name, 'utf-8')), username))
    msg['To'] = ', '.join(formataddr((str(Header(r.get('name', ''), 'utf-8')), r['email'])) for r in recipients)
    msg['Subject'] = Header(subject, 'utf-8')

    try:
        if use_ssl:
            ctx = ssl.create_default_context()
            with smtplib.SMTP_SSL(host, port, context=ctx, timeout=30) as server:
                server.login(username, password)
                server.sendmail(username, to_addrs, msg.as_string())
        else:
            with smtplib.SMTP(host, port, timeout=30) as server:
                server.ehlo()
                server.starttls()
                server.ehlo()
                server.login(username, password)
                server.sendmail(username, to_addrs, msg.as_string())
        return True
    except Exception:
        return False
