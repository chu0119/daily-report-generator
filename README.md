# 📋 Daily Report Generator / 日报自动生成工具

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://www.python.org/)

> 自动读取 Claude Code 对话记录，AI 智能生成工作日报，一键邮件发送。

## ✨ 功能

- 📖 **自动采集** — 自动读取当天 Claude Code 对话历史记录
- 🤖 **AI 生成** — 调用 AI 接口智能整理生成专业日报
- 🖥️ **图形界面** — 现代化 GUI，支持项目筛选、斑马纹列表
- 📧 **邮件发送** — SMTP 一键发送日报邮件
- 🔧 **全面可配置** — 个人信息、AI 接口、邮件设置全部可自定义

## 📥 下载

### 方式一：直接下载 exe（推荐，无需 Python 环境）

从 [Releases](../../releases) 下载最新版 `日报自动生成.exe`，双击运行。

### 方式二：Python 源码运行

```bash
git clone https://github.com/chu0119/daily-report-generator.git
cd daily-report-generator
pip install ttkbootstrap requests
python daily_report.py
```

## ⚙️ 配置

启动后点击右上角 **「⚙ 配置」** 按钮进行设置。

### AI 接口

支持所有 OpenAI 兼容接口：

| 提供商 | API 地址 | 模型 |
|--------|----------|------|
| 小米 MiMo | `https://token-plan-cn.xiaomimimo.com/v1` | `mimo-v2.5-pro` |
| DeepSeek | `https://api.deepseek.com/v1` | `deepseek-chat` |
| OpenAI | `https://api.openai.com/v1` | `gpt-4o-mini` |
| 通义千问 | `https://dashscope.aliyuncs.com/compatible-mode/v1` | `qwen-plus` |
| Moonshot | `https://api.moonshot.cn/v1` | `moonshot-v1-8k` |
| 智谱 AI | `https://open.bigmodel.cn/api/paas/v4` | `glm-4-flash` |

### SMTP 邮箱

| 邮箱 | 服务器 | 端口 |
|------|--------|------|
| QQ 邮箱 | `smtp.qq.com` | 465 |
| 163 邮箱 | `smtp.163.com` | 465 |
| Outlook | `smtp.office365.com` | 587 |

## 🚀 使用

```bash
python daily_report.py                # 启动
python daily_report.py --date 2026-07-14  # 指定日期
```

1. 启动后自动加载今日 Claude Code 工作记录
2. 通过项目下拉框筛选，勾选要写入日报的记录
3. 可手动补充说明
4. 点击「🤖 AI 生成日报」
5. 在编辑区修改调整后保存/发送/复制

## 📁 项目结构

```
├── daily_report.py      # 主程序（GUI）
├── claude_reader.py     # Claude 记录读取
├── ai_generator.py      # AI 日报生成
├── email_sender.py      # 邮件发送
├── config.json          # 配置文件（首次运行自动生成）
└── README.md
```

## 🤝 贡献

欢迎提交 Issue 和 PR！

## 📄 [MIT License](LICENSE)
