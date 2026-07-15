"""
AI 日报生成模块
通过 OpenAI 兼容 API 生成日报内容
支持 DeepSeek、OpenAI、通义千问、Moonshot 等所有兼容接口
"""

import json
import requests
from typing import List, Optional


# ============================================================
#  AI 提示词（精心设计，确保日报质量）
# ============================================================

SYSTEM_PROMPT = """你是一位专业的日报撰写助手，擅长从零散的工作对话记录中提炼出结构清晰、内容准确的工作日报。

## 核心原则

1. **忠于事实**：所有工作内容必须基于提供的对话记录，绝不杜撰或虚构不存在的工作
2. **合理推测**：可以基于对话上下文进行合理推断（如"正在排查XX问题"可推断为"定位并排查XX异常"），但不能凭空捏造
3. **专业表达**：将口语化描述转为专业的工作语言，使用"动词+对象+结果"的规范格式
4. **去粗取精**：过滤无意义记录（问候语、纯粘贴内容、重复操作），保留实质性工作
5. **归纳合并**：将同一项目的多条相关记录归纳为一个完整的工作条目，展现工作全貌

## 对话记录解读规则

这些记录来自用户与 Claude Code（AI编程助手）的对话，解读时请注意：
- 对话中包含用户的操作指令和 AI 的执行结果，应将二者结合理解为一项完整工作
- 用户让 AI 帮忙排查问题 = 用户主导的问题排查工作
- 用户让 AI 编写代码 = 用户主导的开发/优化工作
- 用户粘贴错误日志让 AI 分析 = 用户进行的故障分析工作
- 多条连续对话属于同一任务时，合并为一条，概括为完整的工作过程

## 内容丰富度要求

- 每条工作内容应包含：做了什么、怎么做的、达到什么效果/状态
- 示例：
  - ❌ 过于简略："排查问题"
  - ❌ 杜撰虚构："完成了数据库迁移和压力测试"（记录中无此内容）
  - ✅ 合理丰富："排查 ForensicDesktop 环境检测异常，通过分析日志定位到配置文件损坏，重置配置后恢复正常"
  - ✅ 合理推测："开发日报自动生成工具，完成 AI 接口集成和 GUI 界面开发"（对话记录中有这些内容的证据）

## 不确定内容的处理

- 如果对话记录含糊不清，无法确定具体做了什么，在该条目后标注"（细节待补充）"
- 如果某条记录可能是测试/调试而非正式工作，标注"（调试中）"
- 宁可少写一条真实工作，也不要多写一条虚构工作

## 输出格式

严格按以下5部分输出纯文本（不要用 Markdown 标记）：

1. 今日已完成工作：
 - 工作内容1
 - 工作内容2

2. 进行中未完工事项：
 - 事项说明及当前进度（如无则输出"（无）"）

3. 今日遇到问题及解决方案：
 - 遇到的问题 + 采取的解决措施 + 结果（如无则输出"（无）"）

4. 明日工作计划：
 - 基于今日工作合理推断的后续计划（不要编造与今日工作无关的计划）

5. 其他备注/需求：
 - 需要补充说明的事项（如无则输出"（无）"）"""

USER_PROMPT_TEMPLATE = """请根据以下信息撰写今日工作日报。

## 基本信息
姓名：{name}
部门：{department}
日期：{date}

## 今日对话记录
以下是用户今天使用 Claude Code（AI编程助手）的工作对话记录，
请据此整理生成日报。注意结合上下文理解每条记录的实际含义。

{records}

## 用户补充说明
{extra_notes}

请严格按照系统提示中的原则和格式输出日报。
再次强调：必须基于对话记录如实撰写，不可杜撰虚构不存在的工作内容。"""


def _call_api(config: dict, system_prompt: str, user_prompt: str) -> str:
    """
    调用 OpenAI 兼容 API

    Args:
        config: AI 配置字典
        system_prompt: 系统提示词
        user_prompt: 用户提示词

    Returns:
        AI 生成的文本
    """
    api_base = config['api_base'].rstrip('/')
    api_key = config['api_key']
    model = config.get('model', 'deepseek-chat')
    temperature = config.get('temperature', 0.7)
    max_tokens = config.get('max_tokens', 2000)

    url = f"{api_base}/chat/completions"

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": temperature,
        "max_tokens": max_tokens,
    }

    response = requests.post(url, headers=headers, json=payload, timeout=60)
    response.raise_for_status()

    data = response.json()
    return data['choices'][0]['message']['content'].strip()


def generate_report(
    config: dict,
    name: str,
    department: str,
    date_str: str,
    work_records: List[str],
    extra_notes: str = "",
) -> str:
    """
    使用 AI 生成日报

    Args:
        config: AI 配置字典 (config['ai'])
        name: 姓名
        department: 部门
        date_str: 日期字符串
        work_records: 工作记录列表
        extra_notes: 用户补充说明

    Returns:
        AI 生成的日报文本

    Raises:
        Exception: API 调用失败
    """
    # 格式化工作记录
    if work_records:
        records_text = "\n".join(f"- {r}" for r in work_records)
    else:
        records_text = "（无工作记录）"

    if not extra_notes.strip():
        extra_notes = "无"

    # 构建提示词
    user_prompt = USER_PROMPT_TEMPLATE.format(
        name=name,
        department=department,
        date=date_str,
        records=records_text,
        extra_notes=extra_notes,
    )

    # 调用 API
    return _call_api(config, SYSTEM_PROMPT, user_prompt)


def test_connection(config: dict) -> tuple[bool, str]:
    """
    测试 AI API 连接

    Returns:
        (success: bool, message: str)
    """
    try:
        result = _call_api(
            config,
            "你是一个助手",
            "请回复'连接成功'四个字",
        )
        return True, f"连接成功！AI 回复：{result}"
    except requests.exceptions.ConnectionError:
        return False, "连接失败，请检查 api_base 地址是否正确"
    except requests.exceptions.HTTPError as e:
        status = e.response.status_code if e.response else "未知"
        if status == 401:
            return False, "认证失败，请检查 api_key 是否正确"
        return False, f"HTTP 错误 {status}：{str(e)}"
    except requests.exceptions.Timeout:
        return False, "请求超时，请检查网络连接"
    except Exception as e:
        return False, f"未知错误：{str(e)}"


if __name__ == '__main__':
    print("AI 日报生成模块 — 请通过 GUI 调用")
