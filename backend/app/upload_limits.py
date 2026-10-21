"""Bound the encoded upload body before multipart parsing, including chunked bodies."""

from threading import BoundedSemaphore

from starlette.responses import JSONResponse

from app.services.pdf_extraction import PdfLimits


class UploadLimitsMiddleware:
    def __init__(self, app):
        self.app = app
        self.gate = BoundedSemaphore(1)
        self.body_limit = PdfLimits().max_bytes + 64 * 1024

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["method"] != "POST" or scope["path"].rstrip("/") != "/documents":
            return await self.app(scope, receive, send)
        if not self.gate.acquire(blocking=False):
            return await JSONResponse(
                {"detail": {"code": "upload_busy", "message": "Another upload is processing. Try later."}},
                status_code=503, headers={"Retry-After": "5"},
            )(scope, receive, send)
        try:
            body = bytearray()
            while True:
                message = await receive()
                if message["type"] == "http.disconnect":
                    return
                part = message.get("body", b"")
                if len(body) + len(part) > self.body_limit:
                    return await JSONResponse(
                        {"detail": {"code": "file_too_large", "message": "Encoded upload exceeds the request size limit."}},
                        status_code=413,
                    )(scope, receive, send)
                body.extend(part)
                if not message.get("more_body", False):
                    break
            delivered = False

            async def replay():
                nonlocal delivered
                if not delivered:
                    delivered = True
                    return {"type": "http.request", "body": bytes(body), "more_body": False}
                return await receive()

            await self.app(scope, replay, send)
        finally:
            self.gate.release()
