"""
日报自动生成工具 — GUI 版
自动读取 Claude 对话记录，AI 生成日报，邮件发送

用法：python daily_report.py [--date YYYY-MM-DD]
"""

import sys
import os
import json
import argparse
import threading
from datetime import date, datetime
from typing import List

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

import ttkbootstrap as ttk
from ttkbootstrap.constants import *
from tkinter import messagebox, filedialog, scrolledtext

from claude_reader import read_today_items, read_today_sessions, SessionGroup, _find_session_file, _extract_session_context
import ai_generator
import email_sender

PLACEHOLDER = "点击「🤖 AI 生成日报」按钮生成，或直接在此编辑..."


# ============================================================
#  配置
# ============================================================

CONFIG_PATH = os.path.join(SCRIPT_DIR, 'config.json')


def load_config() -> dict:
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}


def save_config(config: dict):
    with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
        json.dump(config, f, ensure_ascii=False, indent=2)


# ============================================================
#  主界面
# ============================================================

class DailyReportApp:
    def __init__(self, root: ttk.Window, target_date: date = None):
        self.root = root
        self.target_date = target_date or date.today()
        self.config = load_config()
        self.sessions: List[SessionGroup] = []  # 今日所有会话
        self._visible_sessions: List[SessionGroup] = []  # 筛选后的会话
        self.check_vars = []      # 当前可见会话的勾选状态
        self.custom_items = []    # 手动添加的内容

        self._setup_window()
        self._build_ui()
        self._load_records()

    # ─── 窗口 ───

    def _setup_window(self):
        wd = ['周一', '周二', '周三', '周四', '周五', '周六', '周日'][self.target_date.weekday()]
        self.root.title(f"日报自动生成 — {self.target_date.strftime('%Y-%m-%d')} {wd}")
        # 快捷键
        self.root.bind("<Control-Return>", lambda e: self._on_generate())
        self.root.bind("<Control-s>", lambda e: self._save_file())

    # ─── UI ───

    def _build_ui(self):
        # ── 顶部标题横幅 ──
        banner = ttk.Frame(self.root, padding=(15, 10))
        banner.pack(fill=X)
        banner.configure(style="primary.TFrame")  # ttkbootstrap 主色背景

        wd = ['周一', '周二', '周三', '周四', '周五', '周六', '周日'][self.target_date.weekday()]
        ttk.Label(banner, text="📋 日报自动生成",
                  font=("微软雅黑", 15, "bold"),
                  bootstyle="inverse-primary").pack(side=LEFT)
        ttk.Label(banner, text=f"{self.target_date.strftime('%Y-%m-%d')}  {wd}",
                  font=("微软雅黑", 11),
                  bootstyle="inverse-primary").pack(side=RIGHT)

        # ── 上半区：记录列表 ──
        top = ttk.Frame(self.root, padding=(12, 8))
        top.pack(fill=X)
        self._build_record_panel(top)

        # ── 分隔线 ──
        ttk.Separator(self.root, orient="horizontal").pack(fill=X, padx=12, pady=4)

        # ── 下半区：编辑区 ──
        bottom = ttk.Frame(self.root, padding=(12, 4, 12, 8))
        bottom.pack(fill=BOTH, expand=True)
        self._build_result_panel(bottom)

    def _build_record_panel(self, parent):
        # 标题 + 计数
        header = ttk.Frame(parent)
        header.pack(fill=X, pady=(0, 6))
        ttk.Label(header, text="今日工作记录",
                  font=("微软雅黑", 11, "bold")).pack(side=LEFT)
        self.count_label = ttk.Label(header, text="", font=("微软雅黑", 9), bootstyle="secondary")
        self.count_label.pack(side=RIGHT)

        # 项目筛选下拉框（放在标题行右侧、计数左侧）
        ttk.Label(header, text="项目筛选:", font=("微软雅黑", 9)).pack(side=RIGHT, padx=(0, 4))
        self.project_var = ttk.StringVar(value="全部")
        self.project_combo = ttk.Combobox(
            header, textvariable=self.project_var,
            state="readonly", width=18, font=("微软雅黑", 9))
        self.project_combo.pack(side=RIGHT, padx=(0, 8))
        self.project_combo.bind("<<ComboboxSelected>>", self._on_project_filter)

        # 工具栏（紧凑排列）
        toolbar = ttk.Frame(parent)
        toolbar.pack(fill=X, pady=(0, 4))

        for text, cmd, style in [
            ("全选", self._select_all, "info-outline"),
            ("反选", self._invert_sel, "info-outline"),
            ("＋ 手动添加", self._add_custom, "success-outline"),
        ]:
            ttk.Button(toolbar, text=text, bootstyle=style,
                       command=cmd, width=10).pack(side=LEFT, padx=(0, 4))

        ttk.Button(toolbar, text="⚙ 配置", bootstyle="secondary-outline",
                   command=self._open_settings, width=7).pack(side=RIGHT)

        # 记录列表（按会话展示）
        cols = ("time", "project", "summary", "msgs")
        self.tree = ttk.Treeview(parent, columns=cols, show="headings",
                                 height=6, selectmode="none")
        self.tree.heading("time", text="时间", anchor="w")
        self.tree.heading("project", text="项目", anchor="w")
        self.tree.heading("summary", text="会话摘要", anchor="w")
        self.tree.heading("msgs", text="消息", anchor="center")
        self.tree.column("time", width=110, minwidth=90, stretch=False)
        self.tree.column("project", width=160, minwidth=100, stretch=False)
        self.tree.column("summary", width=520, minwidth=200)
        self.tree.column("msgs", width=50, minwidth=40, stretch=False, anchor="center")

        # 斑马纹样式
        self.tree.tag_configure("oddrow", background="#f8f9fa")
        self.tree.tag_configure("evenrow", background="#ffffff")
        self.tree.tag_configure("custom", background="#e8f5e9")

        sb = ttk.Scrollbar(parent, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self.tree.pack(fill=X, expand=False)
        self.tree.bind("<ButtonRelease-1>", self._on_tree_click)

    def _build_result_panel(self, parent):
        # ── 补充说明 ──
        ttk.Label(parent, text="💬 补充说明（可选，供 AI 参考）",
                  font=("微软雅黑", 9)).pack(anchor="w")
        self.extra_text = ttk.Entry(parent, font=("微软雅黑", 9))
        self.extra_text.pack(fill=X, pady=(2, 8))

        # ── 操作按钮栏 ──
        btn_bar = ttk.Frame(parent)
        btn_bar.pack(fill=X, pady=(0, 4))

        self.btn_generate = ttk.Button(
            btn_bar, text="🤖  AI 生成日报", bootstyle="success",
            command=self._on_generate, width=16)
        self.btn_generate.pack(side=LEFT, padx=(0, 10))

        ttk.Button(btn_bar, text="预览", bootstyle="secondary",
                   command=self._preview, width=6).pack(side=LEFT, padx=(0, 4))
        ttk.Button(btn_bar, text="保存", bootstyle="info",
                   command=self._save_file, width=6).pack(side=LEFT, padx=(0, 4))
        ttk.Button(btn_bar, text="发送邮件", bootstyle="primary",
                   command=self._send_email, width=8).pack(side=LEFT, padx=(0, 4))
        ttk.Button(btn_bar, text="复制", bootstyle="secondary-outline",
                   command=self._copy_report, width=6).pack(side=LEFT)

        # 状态行
        self.status_label = ttk.Label(parent, text="", font=("微软雅黑", 9), bootstyle="secondary")
        self.status_label.pack(anchor="w", pady=(0, 4))

        # ── 编辑器 ──
        editor_frame = ttk.Labelframe(parent, text=" 日报内容（可编辑） ", padding=6)
        editor_frame.pack(fill=BOTH, expand=True)

        self.report_text = scrolledtext.ScrolledText(
            editor_frame, font=("微软雅黑", 10), wrap="word",
            relief="flat", borderwidth=0, padx=8, pady=8,
            spacing1=2, spacing3=2  # 行间距
        )
        self.report_text.pack(fill=BOTH, expand=True)
        self._set_placeholder()

        self.report_text.bind("<FocusIn>", self._on_text_focus_in)
        self.report_text.bind("<FocusOut>", self._on_text_focus_out)
        self._placeholder_active = True

    def _set_placeholder(self):
        self.report_text.delete("1.0", "end")
        self.report_text.insert("1.0", PLACEHOLDER)
        self.report_text.configure(foreground="#999999")
        self._placeholder_active = True

    def _clear_placeholder(self):
        if self._placeholder_active:
            self.report_text.delete("1.0", "end")
            self.report_text.configure(foreground="#1a1a1a")
            self._placeholder_active = False

    def _on_text_focus_in(self, event):
        self._clear_placeholder()

    def _on_text_focus_out(self, event):
        if not self.report_text.get("1.0", "end").strip():
            self._set_placeholder()

    # ─── 记录加载 ───

    def _load_records(self):
        history_path = self.config.get('history_path', '~/.claude/history.jsonl')
        projects_path = self.config.get('projects_path', '~/.claude/projects')
        self.sessions = read_today_sessions(
            history_path=history_path,
            projects_path=projects_path,
            target_date=self.target_date,
            load_context=False,
        )
        self.check_vars.clear()

        projects = sorted(set(s.project for s in self.sessions))
        self.project_combo['values'] = ["全部"] + projects
        self.project_var.set("全部")

        self._populate_tree(self.sessions)
        self._update_count()

        if not self.sessions:
            self.tree.insert("", "end", values=("", "", "📭 今日未找到记录，可点击「＋ 手动添加」", ""))

    def _populate_tree(self, sessions):
        for child in self.tree.get_children():
            self.tree.delete(child)
        self.check_vars.clear()
        self._visible_sessions = list(sessions)

        for i, s in enumerate(self._visible_sessions):
            self.check_vars.append(ttk.BooleanVar(value=True))
            tag = "evenrow" if i % 2 == 0 else "oddrow"
            time_str = f"{s.start_time}-{s.end_time}" if s.start_time != s.end_time else s.start_time
            self.tree.insert("", "end", iid=str(i),
                             values=("☑ " + time_str, s.project, s.summary, s.msg_count),
                             tags=(tag,))

    def _on_project_filter(self, event=None):
        selected = self.project_var.get()
        filtered = self.sessions if selected == "全部" else [s for s in self.sessions if s.project == selected]
        self._populate_tree(filtered)
        self._update_count()

    def _on_tree_click(self, event):
        item_id = self.tree.identify_row(event.y)
        if not item_id:
            return
        try:
            idx = int(item_id)
        except ValueError:
            return
        if idx >= len(self.check_vars):
            return

        self.check_vars[idx].set(not self.check_vars[idx].get())
        prefix = "☑ " if self.check_vars[idx].get() else "☐ "

        if idx < len(self._visible_sessions):
            s = self._visible_sessions[idx]
            time_str = f"{s.start_time}-{s.end_time}" if s.start_time != s.end_time else s.start_time
            self.tree.item(item_id, values=(prefix + time_str, s.project, s.summary, s.msg_count))
        else:
            ci = idx - len(self._visible_sessions)
            if ci < len(self.custom_items):
                self.tree.item(item_id, values=(prefix + "--:--", "手动添加", self.custom_items[ci], ""))

        self._update_count()

    def _select_all(self):
        for i, var in enumerate(self.check_vars):
            var.set(True)
            self._update_tree_row(i, True)
        self._update_count()

    def _invert_sel(self):
        for i, var in enumerate(self.check_vars):
            var.set(not var.get())
            self._update_tree_row(i, var.get())
        self._update_count()

    def _update_tree_row(self, idx: int, checked: bool):
        prefix = "☑ " if checked else "☐ "
        iid = str(idx)
        if not self.tree.exists(iid):
            return
        if idx < len(self._visible_sessions):
            s = self._visible_sessions[idx]
            time_str = f"{s.start_time}-{s.end_time}" if s.start_time != s.end_time else s.start_time
            self.tree.item(iid, values=(prefix + time_str, s.project, s.summary, s.msg_count))
        else:
            ci = idx - len(self._visible_sessions)
            if ci < len(self.custom_items):
                self.tree.item(iid, values=(prefix + "--:--", "手动添加", self.custom_items[ci], ""))

    def _update_count(self):
        checked = sum(1 for v in self.check_vars if v.get())
        total = len(self.check_vars)
        self.count_label.configure(text=f"共 {total} 条，已选 {checked} 条")

    def _add_custom(self):
        dialog = ttk.Toplevel(self.root)
        dialog.title("添加工作内容")
        dialog.geometry("480x200")
        dialog.transient(self.root)
        dialog.grab_set()

        ttk.Label(dialog, text="输入工作内容（每行一条）:",
                  font=("微软雅黑", 10)).pack(padx=15, pady=(15, 5), anchor="w")

        text = scrolledtext.ScrolledText(dialog, height=4, font=("微软雅黑", 9), wrap="word")
        text.pack(fill="both", expand=True, padx=15)
        text.focus_set()

        def confirm():
            content = text.get("1.0", "end").strip()
            if content:
                for line in content.split('\n'):
                    line = line.strip()
                    if line:
                        self.custom_items.append(line)
                        idx = len(self._visible_items) + len(self.custom_items) - 1
                        self.check_vars.append(ttk.BooleanVar(value=True))
                        self.tree.insert("", "end", iid=str(idx),
                                         values=("☑ --:--", "手动添加", line),
                                         tags=("custom",))
                self._update_count()
            dialog.destroy()

        btn = ttk.Frame(dialog, padding=10)
        btn.pack(fill="x")
        ttk.Button(btn, text="确定", bootstyle="success", command=confirm, width=8).pack(side="right", padx=5)
        ttk.Button(btn, text="取消", command=dialog.destroy, width=8).pack(side="right")
        dialog.bind("<Return>", lambda e: confirm())

    # ─── AI 生成 ───

    def _get_selected_records(self) -> list:
        """获取选中会话的完整对话上下文"""
        records = []
        for i, var in enumerate(self.check_vars):
            if not var.get():
                continue
            if i < len(self._visible_sessions):
                s = self._visible_sessions[i]
                if s.context:
                    records.append(s.context)
                else:
                    records.append(f"[{s.project}] {s.summary}")
            else:
                ci = i - len(self._visible_sessions)
                if ci < len(self.custom_items):
                    records.append(self.custom_items[ci])
        return records

    def _on_generate(self):
        ai_conf = self.config.get('ai', {})
        if not ai_conf.get('api_key'):
            messagebox.showwarning("AI 未配置",
                                   "请先在「⚙ 配置 → AI 接口」中填写 API Key")
            return

        # 先加载选中会话的完整上下文
        self.btn_generate.configure(state="disabled", text="⏳ 加载上下文...")
        self.status_label.configure(text="正在读取会话上下文...")
        self.root.update()

        projects_path = self.config.get('projects_path', '~/.claude/projects')
        selected_sessions = [self._visible_sessions[i]
                             for i, var in enumerate(self.check_vars)
                             if var.get() and i < len(self._visible_sessions)]

        # 有选中的会话但还没有上下文
        for s in selected_sessions:
            if not s.context:
                sf = _find_session_file(s.session_id, os.path.expanduser(projects_path))
                if sf:
                    s.context = _extract_session_context(sf)

        records = self._get_selected_records()
        if not records:
            messagebox.showinfo("提示", "请先选择要写入日报的会话")
            self.btn_generate.configure(state="normal", text="🤖  AI 生成日报")
            return

        personal = self.config.get('personal', {})
        extra = self.extra_text.get().strip()

        self.btn_generate.configure(state="disabled", text="⏳ AI 生成中...")
        self.status_label.configure(text="正在调用 AI 生成日报，请稍候...")
        self.root.update()

        def do_generate():
            try:
                result = ai_generator.generate_report(
                    config=ai_conf,
                    name=personal.get('name', ''),
                    department=personal.get('department', ''),
                    date_str=self.target_date.strftime('%Y-%m-%d'),
                    work_records=records,
                    extra_notes=extra,
                )
                self.root.after(0, lambda: self._on_generate_done(result, None))
            except Exception as e:
                self.root.after(0, lambda: self._on_generate_done(None, str(e)))

        threading.Thread(target=do_generate, daemon=True).start()

    def _on_generate_done(self, result, error):
        self.btn_generate.configure(state="normal", text="🤖 AI 生成日报")
        if error:
            self.status_label.configure(text=f"❌ 生成失败: {error}")
            messagebox.showerror("AI 生成失败", f"错误信息:\n{error}")
            return

        self._clear_placeholder()
        self.report_text.delete("1.0", "end")
        self.report_text.insert("1.0", result)
        self.status_label.configure(text="✅ 日报已生成，可在下方编辑修改")

    # ─── 操作 ───

    def _get_report_text(self) -> str:
        if self._placeholder_active:
            return ""
        return self.report_text.get("1.0", "end").strip()

    def _preview(self):
        text = self._get_report_text()
        if not text:
            messagebox.showinfo("提示", "请先生成或编辑日报内容")
            return

        win = ttk.Toplevel(self.root)
        win.title("📄 日报预览")
        win.geometry("600x500")
        win.transient(self.root)

        st = scrolledtext.ScrolledText(win, font=("微软雅黑", 11), wrap="word",
                                       relief="flat", padx=15, pady=15)
        st.pack(fill="both", expand=True)
        st.insert("1.0", text)
        st.configure(state="disabled")

        bf = ttk.Frame(win, padding=10)
        bf.pack(fill="x")

        def copy():
            self.root.clipboard_clear()
            self.root.clipboard_append(text)
            self.status_label.configure(text="📋 已复制到剪贴板")

        ttk.Button(bf, text="📋 复制", command=copy).pack(side="left")
        ttk.Button(bf, text="关闭", command=win.destroy).pack(side="right")

    def _save_file(self):
        text = self._get_report_text()
        if not text:
            messagebox.showinfo("提示", "请先生成或编辑日报内容")
            return

        default = f"日报_{self.target_date.strftime('%Y-%m-%d')}.txt"
        path = filedialog.asksaveasfilename(
            parent=self.root, initialdir=SCRIPT_DIR, initialfile=default,
            defaultextension=".txt",
            filetypes=[("文本文件", "*.txt"), ("所有文件", "*.*")])
        if path:
            with open(path, 'w', encoding='utf-8') as f:
                f.write(text)
            self.status_label.configure(text=f"💾 已保存到: {os.path.basename(path)}")

    def _copy_report(self):
        text = self._get_report_text()
        if not text:
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        self.status_label.configure(text="📋 已复制到剪贴板")

    def _send_email(self):
        text = self._get_report_text()
        if not text:
            messagebox.showinfo("提示", "请先生成或编辑日报内容")
            return

        smtp = self.config.get('smtp', {})
        if not smtp.get('username'):
            messagebox.showwarning("邮件未配置", "请先在「⚙ 配置 → SMTP 邮件」中填写信息")
            return

        recipients = self.config.get('recipients', [])
        if not recipients:
            messagebox.showwarning("收件人为空", "请先在「⚙ 配置 → 收件人」中添加")
            return

        personal = self.config.get('personal', {})
        subject = f"【日报】{personal.get('name', '')} {self.target_date.strftime('%Y-%m-%d')}"
        to = ', '.join(r.get('name', r['email']) for r in recipients)

        if not messagebox.askyesno("确认发送", f"即将发送日报给:\n{to}\n\n确认？"):
            return

        # 异步发送，防止界面卡死
        self.status_label.configure(text="📧 正在发送邮件...")
        self.root.config(cursor="wait")
        self.root.update()

        def do_send():
            ok = email_sender.send_report(smtp, recipients, subject, text)
            self.root.after(0, lambda: self._on_send_done(ok, text))

        threading.Thread(target=do_send, daemon=True).start()

    def _on_send_done(self, success, text):
        self.root.config(cursor="")
        if success:
            self.status_label.configure(text="📧 日报发送成功！")
            messagebox.showinfo("发送成功", "日报邮件已发送")
        else:
            backup = os.path.join(SCRIPT_DIR, f"日报_{self.target_date.strftime('%Y-%m-%d')}.txt")
            with open(backup, 'w', encoding='utf-8') as f:
                f.write(text)
            self.status_label.configure(text="❌ 发送失败，已保存到本地")
            messagebox.showerror("发送失败", f"邮件发送失败，请检查 SMTP 配置\n\n已保存到本地:\n{backup}")

    # ─── 设置 ───

    def _open_settings(self):
        SettingsDialog(self.root, self.config, on_save=self._on_config_saved)

    def _on_config_saved(self, new_config):
        self.config = new_config
        self._load_records()
        self.status_label.configure(text="✅ 配置已保存")


# ============================================================
#  设置对话框
# ============================================================

class SettingsDialog:
    def __init__(self, parent, config: dict, on_save=None):
        self.config = config
        self.on_save = on_save
        self.entries = {}

        self.win = ttk.Toplevel(parent)
        self.win.title("⚙ 设置")
        self.win.geometry("560x620")
        self.win.transient(parent)
        self.win.grab_set()

        self._build()
        self._load_values()

    def _build(self):
        nb = ttk.Notebook(self.win, bootstyle="info")
        nb.pack(fill="both", expand=True, padx=10, pady=10)

        tabs = [
            ("个人信息", self._build_personal_tab),
            ("AI 接口", self._build_ai_tab),
            ("SMTP 邮件", self._build_smtp_tab),
            ("收件人", self._build_recipients_tab),
        ]
        for title, builder in tabs:
            frame = ttk.Frame(nb, padding=10)
            nb.add(frame, text=f"  {title}  ")
            builder(frame)

        # 底部按钮
        bf = ttk.Frame(self.win, padding=(10, 5))
        bf.pack(fill="x")
        ttk.Button(bf, text="保存", bootstyle="success",
                   command=self._save, width=10).pack(side="right", padx=5)
        ttk.Button(bf, text="取消", command=self.win.destroy, width=10).pack(side="right")

    def _build_personal_tab(self, parent):
        for label, key in [("姓名", "personal.name"), ("部门", "personal.department")]:
            f = ttk.Frame(parent)
            f.pack(fill="x", pady=5)
            ttk.Label(f, text=f"{label}:", width=10, anchor="e").pack(side="left")
            self.entries[key] = ttk.Entry(f, font=("微软雅黑", 10), width=35)
            self.entries[key].pack(side="left", padx=(10, 0))

    def _build_ai_tab(self, parent):
        ttk.Label(parent, text="支持所有 OpenAI 兼容接口\n"
                               "DeepSeek / OpenAI / 通义千问 / Moonshot / 智谱 等",
                  font=("微软雅黑", 9), wraplength=480, foreground="gray").pack(anchor="w", pady=(0, 10))

        for label, key, is_pwd in [
            ("API 地址", "ai.api_base", False),
            ("API Key", "ai.api_key", True),
            ("模型名称", "ai.model", False),
        ]:
            f = ttk.Frame(parent)
            f.pack(fill="x", pady=5)
            ttk.Label(f, text=f"{label}:", width=10, anchor="e").pack(side="left")
            e = ttk.Entry(f, font=("微软雅黑", 10), width=40, show="*" if is_pwd else "")
            e.pack(side="left", padx=(10, 0))
            self.entries[key] = e

        # 温度滑块
        f = ttk.Frame(parent)
        f.pack(fill="x", pady=5)
        ttk.Label(f, text="温度:", width=10, anchor="e").pack(side="left")
        self.temp_var = ttk.DoubleVar(value=0.7)
        ttk.Scale(f, from_=0.0, to=1.0, variable=self.temp_var,
                  orient="horizontal", length=250).pack(side="left", padx=(10, 5))
        self.temp_label = ttk.Label(f, text="0.7", width=4)
        self.temp_label.pack(side="left")
        self.temp_var.trace_add("write",
                                lambda *a: self.temp_label.configure(text=f"{self.temp_var.get():.1f}"))

        # 测试连接
        bf = ttk.Frame(parent)
        bf.pack(fill="x", pady=(15, 0))
        ttk.Button(bf, text="🔗 测试连接", bootstyle="info-outline",
                   command=self._test_ai, width=12).pack(side="left")
        self.ai_status = ttk.Label(bf, text="", font=("微软雅黑", 9))
        self.ai_status.pack(side="left", padx=(10, 0))

    def _build_smtp_tab(self, parent):
        for label, key, is_pwd in [
            ("SMTP 服务器", "smtp.host", False),
            ("端口", "smtp.port", False),
            ("发件邮箱", "smtp.username", False),
            ("SMTP 授权码", "smtp.password", True),
            ("发件人显示名", "smtp.sender_name", False),
        ]:
            f = ttk.Frame(parent)
            f.pack(fill="x", pady=5)
            ttk.Label(f, text=f"{label}:", width=12, anchor="e").pack(side="left")
            e = ttk.Entry(f, font=("微软雅黑", 10), width=38, show="*" if is_pwd else "")
            e.pack(side="left", padx=(10, 0))
            self.entries[key] = e

        ttk.Label(parent, text="💡 QQ邮箱: smtp.qq.com:465   163邮箱: smtp.163.com:465\n"
                               "   需在邮箱设置中开启 SMTP 并获取授权码（非登录密码）",
                  font=("微软雅黑", 8), foreground="gray", wraplength=480).pack(anchor="w", pady=(10, 0))

    def _build_recipients_tab(self, parent):
        ttk.Label(parent, text="每行一个，格式: 姓名 邮箱",
                  font=("微软雅黑", 9)).pack(anchor="w", pady=(0, 5))

        self.recipients_text = scrolledtext.ScrolledText(
            parent, font=("Consolas", 10), height=8, wrap="word")
        self.recipients_text.pack(fill="both", expand=True)

        ttk.Label(parent, text="示例:\n张领导  zhang@company.com\n李经理  li@company.com",
                  font=("微软雅黑", 8), foreground="gray").pack(anchor="w", pady=(5, 0))

    # ─── 数据加载/保存 ───

    def _load_values(self):
        c = self.config
        p, a, s = c.get('personal', {}), c.get('ai', {}), c.get('smtp', {})

        inserts = {
            "personal.name": p.get('name', ''),
            "personal.department": p.get('department', ''),
            "ai.api_base": a.get('api_base', ''),
            "ai.api_key": a.get('api_key', ''),
            "ai.model": a.get('model', ''),
            "smtp.host": s.get('host', ''),
            "smtp.port": s.get('port', ''),
            "smtp.username": s.get('username', ''),
            "smtp.password": s.get('password', ''),
            "smtp.sender_name": s.get('sender_name', ''),
        }
        for key, val in inserts.items():
            if key in self.entries:
                self.entries[key].insert(0, str(val))

        self.temp_var.set(a.get('temperature', 0.7))

        lines = [f"{r.get('name', '')}  {r['email']}" for r in c.get('recipients', [])]
        if lines:
            self.recipients_text.insert("1.0", "\n".join(lines))

    def _get(self, key):
        return self.entries[key].get().strip() if key in self.entries else ""

    def _save(self):
        cfg = json.loads(json.dumps(self.config))
        cfg.setdefault('personal', {})
        cfg['personal']['name'] = self._get("personal.name")
        cfg['personal']['department'] = self._get("personal.department")

        cfg.setdefault('ai', {})
        cfg['ai']['api_base'] = self._get("ai.api_base")
        cfg['ai']['api_key'] = self._get("ai.api_key")
        cfg['ai']['model'] = self._get("ai.model")
        cfg['ai']['temperature'] = round(self.temp_var.get(), 1)
        cfg['ai']['enabled'] = bool(cfg['ai']['api_key'])

        cfg.setdefault('smtp', {})
        cfg['smtp']['host'] = self._get("smtp.host")
        try:
            cfg['smtp']['port'] = int(self._get("smtp.port") or 465)
        except ValueError:
            cfg['smtp']['port'] = 465
        cfg['smtp']['use_ssl'] = True
        cfg['smtp']['username'] = self._get("smtp.username")
        cfg['smtp']['password'] = self._get("smtp.password")
        cfg['smtp']['sender_name'] = self._get("smtp.sender_name")
        cfg['smtp']['enabled'] = bool(cfg['smtp']['username'])

        recipients = []
        for line in self.recipients_text.get("1.0", "end").strip().split('\n'):
            line = line.strip()
            if not line:
                continue
            parts = line.split()
            if len(parts) >= 2:
                recipients.append({"name": parts[0], "email": parts[-1]})
            elif '@' in line:
                recipients.append({"name": line.split('@')[0], "email": line})
        cfg['recipients'] = recipients

        save_config(cfg)
        if self.on_save:
            self.on_save(cfg)
        self.win.destroy()

    def _test_ai(self):
        conf = {
            "api_base": self._get("ai.api_base"),
            "api_key": self._get("ai.api_key"),
            "model": self._get("ai.model"),
            "temperature": round(self.temp_var.get(), 1),
        }
        if not conf['api_key']:
            self.ai_status.configure(text="❌ 请先填写 API Key")
            return

        self.ai_status.configure(text="⏳ 测试中...")
        self.win.update()

        def do_test():
            ok, msg = ai_generator.test_connection(conf)
            self.win.after(0, lambda: self.ai_status.configure(
                text=("✅ " + msg) if ok else ("❌ " + msg)))

        threading.Thread(target=do_test, daemon=True).start()


# ============================================================
#  入口
# ============================================================

def main():
    parser = argparse.ArgumentParser(description='日报自动生成工具')
    parser.add_argument('--date', type=str, help='指定日期 (YYYY-MM-DD)')
    args = parser.parse_args()

    target_date = None
    if args.date:
        try:
            target_date = datetime.strptime(args.date, '%Y-%m-%d').date()
        except ValueError:
            print(f"日期格式不正确: {args.date}")
            sys.exit(1)

    root = ttk.Window(title="日报自动生成", themename="cosmo", size=(1150, 880))
    root.place_window_center()
    root.minsize(900, 650)
    DailyReportApp(root, target_date=target_date)
    root.mainloop()


if __name__ == '__main__':
    main()
