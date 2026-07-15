"""
Claude 历史记录读取模块
从 ~/.claude/history.jsonl 读取指定日期的用户对话记录
"""

import json
import os
from datetime import datetime, date
from dataclasses import dataclass
from typing import List


@dataclass
class WorkItem:
    """一条工作记录"""
    time: str           # HH:MM
    project: str        # 简化项目路径
    full_project: str   # 完整项目路径
    content: str        # 用户输入内容
    session_id: str     # 会话 ID

    def __str__(self):
        return f"[{self.time}] {self.project}: {self.content}"


# 斜杠命令集合（过滤用）
_SLASH_COMMANDS = frozenset({
    '/resume', '/plan', '/help', '/clear', '/compact', '/cost',
    '/doctor', '/init', '/login', '/logout', '/memory', '/model',
    '/permissions', '/review', '/scan', '/security', '/status',
    '/superpowers', '/fast', '/slow', '/ultracode', '/worktree',
    '/design', '/loop', '/tasks', '/workflows', '/agents',
})


def _simplify_path(path: str) -> str:
    """简化项目路径，取最后两级"""
    if not path:
        return "未知项目"
    parts = path.replace('\\', '/').rstrip('/').split('/')
    return '/'.join(parts[-2:]) if len(parts) >= 2 else (parts[0] if parts else path)


def _is_slash_cmd(text: str) -> bool:
    t = text.strip()
    return any(t.startswith(cmd) for cmd in _SLASH_COMMANDS)


def _clean(text: str, max_len: int = 200) -> str:
    t = text.strip()
    return t[:max_len] + '...' if len(t) > max_len else t


def read_today_items(history_path: str = "~/.claude/history.jsonl",
                     target_date: date = None) -> List[WorkItem]:
    """读取指定日期的 Claude 工作记录，按时间排序"""
    if target_date is None:
        target_date = date.today()

    fp = os.path.expanduser(history_path)
    if not os.path.exists(fp):
        return []

    target = target_date.strftime('%Y-%m-%d')
    items = []

    with open(fp, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                e = json.loads(line)
            except json.JSONDecodeError:
                continue

            ts = e.get('timestamp', 0)
            if not ts:
                continue

            dt = datetime.fromtimestamp(ts / 1000)
            if dt.strftime('%Y-%m-%d') != target:
                continue

            display = e.get('display', '').strip()
            if not display or _is_slash_cmd(display):
                continue

            proj = e.get('project', '')
            items.append(WorkItem(
                time=dt.strftime('%H:%M'),
                project=_simplify_path(proj),
                full_project=proj,
                content=_clean(display),
                session_id=e.get('sessionId', ''),
            ))

    items.sort(key=lambda x: x.time)
    return items
