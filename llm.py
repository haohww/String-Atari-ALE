from openai import OpenAI
import json
import os

TEST_MODEL = "gemini"
INFERENCE_MODEL = "DeepSeek-R1"

DEFAULT_MODEL = TEST_MODEL


def get_llm_action(current_state, model=DEFAULT_MODEL):
    if model == "DeepSeek-R1":
        return get_R1_action(current_state)
    elif model == "gemini":
        return get_gemini_action(current_state)


def get_R1_action(current_state):
    client = OpenAI(
        base_url="https://aihubmix.com/v1",
        api_key=os.environ["apikey"],
    )

    messages = [{"role": "user", "content": current_state}]
    MODEL = "DeepSeek-R1"
    try:
        response = client.chat.completions.create(
            model=MODEL,
            messages=messages,
        )
        direction = response.choices[0].message.content.strip().upper()
        resoning_content = (
            response.choices[0].message.reasoning_content.strip()
            if MODEL == "DeepSeek-R1"
            else ""
        )
        print(f"LLM 决策：{direction}")
        # print(f"LLM 决策理由：{resoning_content}")
    except Exception as e:
        print(f"调用错误: {e}")
        direction = "UP"  # 如果出错，默认返回 UP
        resoning_content = ""
    return direction, resoning_content


def get_gemini_action(current_state):
    client = OpenAI(
        base_url="https://aihubmix.com/v1",
        api_key="sk-EFOmZQf9Zrd0EAPwF4Db2b7379B149668dC6257b599d23Ec",
    )

    current_state += """**Output rules**
Provide your output in the json format, with two keys: action and reasoning.
example:
"action": "UP",
"reasoning": "I need to go up to avoid ghost."""

    messages = [{"role": "user", "content": current_state}]
    MODEL = "gemini-2.0-flash"
    try:
        response = client.chat.completions.create(
            model=MODEL,
            messages=messages,
        )
        # print(f"response: {response}")
        resp = json.loads(
            response.choices[0]
            .message.content.replace("```json", "")
            .replace("```", "")
        )
        direction = resp.get("action", "")
        resoning_content = resp.get("reasoning", "")
        # print(f"LLM 决策：{direction}")
        # print(f"LLM 决策理由：{resoning_content}")
    except Exception as e:
        print(f"调用错误: {e}")
        direction = "UP"  # 如果出错，默认返回 UP
        resoning_content = ""
    return direction, resoning_content
