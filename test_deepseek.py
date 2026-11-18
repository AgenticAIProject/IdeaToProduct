"""
test_deepseek.py
================
Standalone diagnostic script to inspect raw DeepSeek API responses,
available models, balance, reasoning tokens, and LangChain integration.
"""

import os
import json
import urllib.request
import urllib.error
from dotenv import load_dotenv

load_dotenv()

raw_key = os.environ.get("DEEPSEEK_API_KEY", "")
API_KEY = raw_key.replace("'", "").replace('"', "").strip()
BASE_URL = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com").rstrip("/")
MODEL = os.environ.get("DEEPSEEK_MODEL", "deepseek-flash")

print("=" * 60)
print("DEEPSEEK DIAGNOSTIC TEST")
print("=" * 60)
print(f"Base URL : {BASE_URL}")
print(f"API Key  : {API_KEY[:6]}...{API_KEY[-4:] if len(API_KEY) > 10 else ''} (length: {len(API_KEY)})")
print(f"Model    : {MODEL}")
print("-" * 60)

if not API_KEY:
    print("[ERROR] DEEPSEEK_API_KEY is not set in .env!")
    exit(1)

def make_request(endpoint: str, data: dict | None = None) -> dict | None:
    url = f"{BASE_URL}{endpoint}"
    print(f"\n[REQUEST] Calling: {url}")
    if data:
        print(f"  Model: {data.get('model')}, Max Tokens: {data.get('max_tokens')}")
    
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    
    req_body = json.dumps(data).encode("utf-8") if data else None
    req = urllib.request.Request(url, data=req_body, headers=headers, method="POST" if data else "GET")
    
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            status = resp.getcode()
            body = resp.read().decode("utf-8")
            parsed = json.loads(body)
            print(f"[RESPONSE] Status: {status} OK")
            return parsed
    except urllib.error.HTTPError as e:
        status = e.code
        err_body = e.read().decode("utf-8", errors="replace")
        print(f"[RESPONSE ERROR] HTTP {status} {e.reason}")
        try:
            parsed = json.loads(err_body)
            print(f"  Error details: {json.dumps(parsed, indent=2)}")
        except Exception:
            print(f"  Raw: {err_body}")
        return None
    except Exception as exc:
        print(f"[NETWORK ERROR] Failed: {exc}")
        return None

# 1. Check Balance
print("\n--- 1. Account Balance ---")
bal = make_request("/user/balance")
if bal:
    print(json.dumps(bal, indent=2))

# 2. Check Available Models
print("\n--- 2. Available Models ---")
models = make_request("/models")
if models and "data" in models:
    for m in models["data"]:
        print(f"  * ID: {m.get('id')} | Name: {m.get('name')} | Context: {m.get('context_window')} | Max Output: {m.get('max_output_tokens')}")

# 3. Test deepseek-flash with enough tokens for reasoning + content
print(f"\n--- 3. Testing '{MODEL}' with 500 max_tokens ---")
payload_500 = {
    "model": MODEL,
    "messages": [
        {"role": "user", "content": "Write a 1-line Python function that squares a number. Output ONLY the code."}
    ],
    "max_tokens": 500,
    "temperature": 0.1,
}
resp = make_request("/chat/completions", payload_500)
if resp:
    choice = resp["choices"][0]
    msg = choice["message"]
    print(f"  Finish Reason: {choice.get('finish_reason')}")
    print(f"  Reasoning Content (thinking):\n    {msg.get('reasoning_content', '<none>')}")
    print(f"  Final Content (code):\n    {repr(msg.get('content'))}")
    print(f"  Usage: {resp.get('usage')}")

# 4. Test LangChain ChatOpenAI with this exact setup
print("\n--- 4. Testing LangChain ChatOpenAI ---")
try:
    from langchain_openai import ChatOpenAI
    llm = ChatOpenAI(
        model=MODEL,
        api_key=API_KEY,
        base_url=BASE_URL,
        max_tokens=1000,
        temperature=0.1
    )
    lc_resp = llm.invoke("Write a 1-line Python function that squares a number. Output ONLY the code.")
    print("  LangChain response.content:")
    print(f"    {repr(lc_resp.content)}")
    print("  LangChain response_metadata:")
    print(f"    {lc_resp.response_metadata}")
except Exception as e:
    print(f"  LangChain error: {e}")

print("\n" + "=" * 60)
print("DIAGNOSTIC COMPLETE")
print("=" * 60)
