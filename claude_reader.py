"""
Claude 历史记录读取模块
支持两种模式：
  1. 按会话分组读取（用于 AI 生成日报，提供完整上下文）
  2. 按条目读取（兼容旧逻辑）
"""

import json
import os
import glob
from datetime import datetime, date
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class WorkItem:
    """一条用户工作记录（兼容旧逻辑）"""
    time: str
    project: str
    full_project: str
    content: str
    session_id: str

    def __str__(self):
        return f"[{self.time}] {self.project}: {self.content}"


@dataclass
class SessionGroup:
    """一个完整的会话，包含上下文"""
    session_id: str
    project: str           # 简化项目名
    full_project: str      # 完整项目路径
    start_time: str        # 会话开始时间 HH:MM
    end_time: str          # 会话结束时间 HH:MM
    summary: str           # 第一条用户消息（用于列表展示）
    msg_count: int         # 消息总数
    context: str = field(default="", repr=False)  # 完整对话上下文（供 AI 阅读）


# 斜杠命令
_SLASH = frozenset({
    '/resume', '/plan', '/help', '/clear', '/compact', '/cost',
    '/doctor', '/init', '/login', '/logout', '/memory', '/model',
    '/permissions', '/review', '/scan', '/security', '/status',
    '/superpowers', '/fast', '/slow', '/ultracode', '/worktree',
    '/design', '/loop', '/tasks', '/workflows', '/agents',
})


def _simplify_path(path: str) -> str:
    if not path:
        return "未知项目"
    parts = path.replace('\\', '/').rstrip('/').split('/')
    return '/'.join(parts[-2:]) if len(parts) >= 2 else (parts[0] if parts else path)


def _is_slash(text: str) -> bool:
    t = text.strip()
    return any(t.startswith(cmd) for cmd in _SLASH)


def _clean(text: str, max_len: int = 200) -> str:
    t = text.strip()
    return t[:max_len] + '...' if len(t) > max_len else t


# ============================================================
#  按会话分组读取（新逻辑，AI 生成用）
# ============================================================

def _find_session_file(session_id: str, projects_dir: str) -> Optional[str]:
    """在 ~/.claude/projects/ 下查找会话 JSONL 文件"""
    for d in os.listdir(projects_dir):
        fp = os.path.join(projects_dir, d, session_id + '.jsonl')
        if os.path.exists(fp):
            return fp
    return None


def _extract_session_context(session_file: str, max_chars: int = 8000) -> str:
    """
    从会话 JSONL 文件提取完整对话上下文
    提取用户消息和助手的文本回复，拼接成可读的对话记录
    """
    user_msgs = []
    asst_msgs = []

    with open(session_file, 'r', encoding='utf-8') as f:
        for line in f:
            try:
                obj = json.loads(line.strip())
            except (json.JSONDecodeError, ValueError):
                continue

            msg_type = obj.get('type')
            if msg_type not in ('user', 'assistant'):
                continue

            content = obj.get('message', {}).get('content', '')

            if msg_type == 'user':
                # 提取用户文本
                if isinstance(content, str) and content.strip():
                    text = content.strip()
                    if not _is_slash(text):
                        user_msgs.append(text)
                elif isinstance(content, list):
                    for c in content:
                        if isinstance(c, dict) and c.get('type') == 'text':
                            text = c['text'].strip()
                            if text and not _is_slash(text):
                                user_msgs.append(text)

            elif msg_type == 'assistant':
                # 提取助手文本（跳过 thinking 和 tool_use）
                if isinstance(content, list):
                    for c in content:
                        if isinstance(c, dict) and c.get('type') == 'text':
                            text = c['text'].strip()
                            if len(text) > 20:  # 过滤太短的回复
                                asst_msgs.append(text)

    # 拼接成对话上下文
    lines = []
    total = 0

    # 交替排列：用户消息 + 对应的助手回复
    # 简单处理：按顺序排列，标注角色
    a_idx = 0
    for u_idx, u_msg in enumerate(user_msgs):
        entry = f"[用户] {u_msg}"
        if total + len(entry) > max_chars:
            break
        lines.append(entry)
        total += len(entry)

        # 该用户消息后的助手回复（取到下一个用户消息之前）
        while a_idx < len(asst_msgs):
            a_msg = asst_msgs[a_idx]
            a_entry = f"[助手] {a_msg}"
            if total + len(a_entry) > max_chars:
                lines.append("[助手] ...(内容已截断)")
                return '\n'.join(lines)
            lines.append(a_entry)
            total += len(a_entry)
            a_idx += 1
            break  # 每个用户消息只取一个助手回复，避免太长

    return '\n'.join(lines)


def read_today_sessions(history_path: str = "~/.claude/history.jsonl",
                        projects_path: str = "~/.claude/projects",
                        target_date: date = None,
                        load_context: bool = False) -> List[SessionGroup]:
    """
    读取指定日期的会话，按 session 分组

    Args:
        history_path: history.jsonl 路径
        projects_path: 项目目录路径
        target_date: 目标日期
        load_context: 是否立即加载完整对话上下文（较慢）

    Returns:
        SessionGroup 列表
    """
    if target_date is None:
        target_date = date.today()

    fp = os.path.expanduser(history_path)
    if not os.path.exists(fp):
        return []

    target = target_date.strftime('%Y-%m-%d')

    # 第一步：从 history.jsonl 按 session 分组
    sessions = {}  # session_id -> {project, times, summaries}

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
            if not display or _is_slash(display):
                continue

            sid = e.get('sessionId', '')
            if not sid:
                continue

            proj = e.get('project', '')

            if sid not in sessions:
                sessions[sid] = {
                    'project': proj,
                    'times': [],
                    'summaries': [],
                }
            sessions[sid]['times'].append(dt)
            sessions[sid]['summaries'].append(_clean(display, 100))

    # 第二步：构建 SessionGroup
    proj_dir = os.path.expanduser(projects_path)
    groups = []

    for sid, info in sessions.items():
        times = sorted(info['times'])
        start = times[0].strftime('%H:%M')
        end = times[-1].strftime('%H:%M')
        summary = info['summaries'][0] if info['summaries'] else ''

        group = SessionGroup(
            session_id=sid,
            project=_simplify_path(info['project']),
            full_project=info['project'],
            start_time=start,
            end_time=end,
            summary=summary,
            msg_count=len(info['summaries']),
        )

        # 加载完整对话上下文
        if load_context and os.path.isdir(proj_dir):
            sf = _find_session_file(sid, proj_dir)
            if sf:
                group.context = _extract_session_context(sf)

        groups.append(group)

    groups.sort(key=lambda g: g.start_time)
    return groups


# ============================================================
#  按条目读取（兼容旧逻辑）
# ============================================================

def read_today_items(history_path: str = "~/.claude/history.jsonl",
                     target_date: date = None) -> List[WorkItem]:
    """读取指定日期的用户工作记录（逐条），按时间排序"""
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
            if not display or _is_slash(display):
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
