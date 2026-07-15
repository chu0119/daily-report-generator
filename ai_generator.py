"""
AI 日报生成模块
通过 OpenAI 兼容 API 生成日报内容
支持 DeepSeek、OpenAI、通义千问、Moonshot 等所有兼容接口
"""

import json
import requests
from typing import List, Optional


# AI 提示词（精心设计，确保输出格式规范）
SYSTEM_PROMPT = """你是一个专业的日报撰写助手。你的任务是根据用户提供的当日工作记录，生成一份简洁、专业、条理清晰的工作日报。

## 要求：
1. 语言简洁专业，避免口语化表达
2. 将零散的工作记录归纳整理为结构化的工作条目
3. 每条工作内容用"动词+对象+结果"的格式描述（如"完成XX功能开发，通过测试验证"）
4. 合并重复或相关的记录为一条
5. 过滤掉无意义的记录（如"你好"、纯粘贴内容等）
6. 输出纯文本格式，不要使用 Markdown 标记

## 输出格式：
严格按以下5个部分输出，每部分用编号标题，每条内容以" - "开头：

1. 今日已完成工作：
 - 工作内容1
 - 工作内容2

2. 进行中未完工事项：
 - 事项说明（如无则输出"（无）"）

3. 今日遇到问题及解决方案：
 - 问题及解决方式（如无则输出"（无）"）

4. 明日工作计划：
 - 计划事项1（根据今日工作合理推测）

5. 其他备注/需求：
 - 备注内容（如无则输出"（无）"）"""

USER_PROMPT_TEMPLATE = """请根据以下信息生成今日工作日报。

## 个人信息
姓名：{name}
部门：{department}
日期：{date}

## 今日工作记录
以下是今天使用 Claude Code 进行工作的对话记录摘要，请据此整理生成日报：

{records}

## 用户补充说明
{extra_notes}

请严格按照系统提示中的格式要求输出日报内容。"""


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
