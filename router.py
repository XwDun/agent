from fastapi import FastAPI, Request, Response
import httpx
import json
import io
import sys

app = FastAPI()
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
# 目标转发
TARGET_HOST = "https://dashscope.aliyuncs.com"

@app.post("/{full_path:path}")
async def forward(request: Request, full_path: str):
    target_url = f"{TARGET_HOST}/{full_path}"

    body = await request.body()

    try:
        body_json = json.loads(body)
        print("\n" + "="*80)
        print("请求体：")
        print(json.dumps(body_json, ensure_ascii=False, indent=2))
        print("="*80 + "\n")
    except Exception as e:
        print("\n【无法解析JSON】", e)

    # 转发请求
    headers = dict(request.headers)
    headers.pop("host", None)
    headers.pop("content-length", None)

    async with httpx.AsyncClient() as client:
        resp = await client.request(
            method=request.method,
            url=target_url,
            headers=headers,
            content=body,
            timeout=120.0
        )

    return Response(
        content=resp.content,
        status_code=resp.status_code,
        headers=dict(resp.headers)
    )

# ==============================
# 自动启动，日志输出到 output.txt
# ==============================
if __name__ == "__main__":
    import subprocess
    import sys

    with open( "router" / "output.txt", "w", encoding="utf-8") as f:
        subprocess.run(
            [sys.executable, "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"],
            stdout=f,
            stderr=f,
            text=True,
            encoding="utf-8"
        )