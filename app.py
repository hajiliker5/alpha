# app.py (Lightweight Reverse Proxy for Runflare)
import os
import ssl
import asyncio
import httpx
import websockets
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse, HTMLResponse, FileResponse

app = FastAPI()

# 🟢 آدرس اسپیس هاگینگ فیس شما (مغز متفکر اصلی)
# می‌توانید این آدرس را تغییر دهید تا به اسپیس مد نظر شما اشاره کند
HF_SPACE_URL = os.environ.get("HF_SPACE_URL", "https://opera8-runflare.hf.space").strip()
HF_WS_URL = HF_SPACE_URL.replace("https://", "wss://") + "/ws"

# هدرهای امنیتی جهت اعطای دسترسی دوربین و میکروفون به مرورگر و وب‌ویو موبایل
PERMISSION_HEADERS = {
    "Permissions-Policy": "camera=*, microphone=*, geolocation=*, autoplay=*",
    "Feature-Policy": "camera *; microphone *; autoplay *",
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
    "Access-Control-Allow-Headers": "*"
}

# غیرفعال کردن بررسی سخت‌گیرانه SSL برای جلوگیری از خطاهای احتمالی ارتباط داخلی داکر رانفلر
ssl_context = ssl.create_default_context()
ssl_context.check_hostname = False
ssl_context.verify_mode = ssl.CERT_NONE


# =================================================================
# ۱. مانیتورینگ و پروکسی اتصال‌های وب‌سوکت صوتی (/ws) به هاگینگ فیس
# =================================================================
@app.websocket("/ws")
async def websocket_proxy_route(client_ws: WebSocket):
    await client_ws.accept()
    
    # شبیه‌سازی دست‌تکانی وب‌سوکت برای عبور از سد فایروال هاگینگ‌فیس
    headers = {
        "Host": HF_SPACE_URL.replace("https://", ""),
        "Origin": HF_SPACE_URL,
        "User-Agent": client_ws.headers.get("user-agent", "Mozilla/5.0")
    }
    
    ws_kwargs = {}
    try:
        ws_version = getattr(websockets, "__version__", "10.0")
        try:
            major_version = int(ws_version.split('.')[0])
        except ValueError:
            major_version = 10
            
        if major_version >= 14:
            ws_kwargs["additional_headers"] = headers
        else:
            ws_kwargs["extra_headers"] = headers
    except Exception:
        ws_kwargs["extra_headers"] = headers

    try:
        # اتصال مستقیم و پایدار وب‌سوکت به هاگینگ‌فیس
        async with websockets.connect(
            HF_WS_URL, 
            ssl=ssl_context,
            **ws_kwargs
        ) as server_ws:
            
            async def client_to_server():
                try:
                    while True:
                        data = await client_ws.receive()
                        if "text" in data and data["text"] is not None:
                            await server_ws.send(data["text"])
                        elif "bytes" in data and data["bytes"] is not None:
                            await server_ws.send(data["bytes"])
                except Exception:
                    pass

            async def server_to_client():
                try:
                    async for message in server_ws:
                        if isinstance(message, str):
                            await client_ws.send_text(message)
                        else:
                            await client_ws.send_bytes(message)
                except Exception:
                    pass

            await asyncio.gather(client_to_server(), server_to_client())
            
    except WebSocketDisconnect:
        pass
    except Exception as e:
        print(f"[WS Proxy Error]: {e}")
    finally:
        try:
            await client_ws.close()
        except:
            pass


# =================================================================
# ۲. مسیر یاب و پروکسی سراسری و استریمینگ تمام درخواست‌های وب و API
# =================================================================
@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "HEAD", "PATCH"])
async def reverse_proxy_route(request: Request, path: str):
    # کپی کردن هدرهای درخواست کاربر
    headers = dict(request.headers)
    
    # حذف هدرهای محلی رانفلر برای جلوگیری از تداخل مسیر در هاگینگ‌فیس
    headers.pop("host", None)
    headers.pop("content-length", None)
    
    # فوروارد کردن آی‌پی واقعی کاربر جهت پایداری سهمیه اعتبارات
    cf_ip = request.headers.get("CF-Connecting-IP")
    if cf_ip:
        headers["X-Forwarded-For"] = cf_ip
        
    url = f"{HF_SPACE_URL}/{path}"
    body = await request.body()
    
    # دریافت استریم داده‌ها از هاگینگ‌فیس و تحویل آنی به کاربر (بدون بافر کردن در رم رانفلر)
    async def generate_response():
        async with httpx.AsyncClient(verify=False, timeout=300.0) as client_local:
            async with client_local.stream(
                request.method,
                url,
                content=body,
                headers=headers,
                params=dict(request.query_params)
            ) as resp:
                async for chunk in resp.aiter_bytes():
                    yield chunk

    # دریافت متادیتای هدرها از هاگینگ‌فیس
    async with httpx.AsyncClient(verify=False, timeout=300.0) as client_headers:
        resp_headers = await client_headers.request(
            request.method,
            url,
            content=body,
            headers=headers,
            params=dict(request.query_params)
        )
        
    # آماده‌سازی هدرهای پاسخ برای بازگرداندن به مرورگر کاربر
    headers_to_return = dict(resp_headers.headers)
    headers_to_return.pop("content-encoding", None)
    headers_to_return.pop("content-length", None)
    headers_to_return.pop("transfer-encoding", None)
    
    # تزریق هدرهای دسترسی و کرس (CORS)
    for k, v in PERMISSION_HEADERS.items():
        headers_to_return[k] = v
        
    return StreamingResponse(
        generate_response(),
        status_code=resp_headers.status_code,
        headers=headers_to_return,
        media_type=resp_headers.headers.get("content-type")
    )
