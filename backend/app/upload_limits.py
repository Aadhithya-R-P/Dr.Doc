"""Bound the encoded upload body before multipart parsing, including chunked bodies."""

from threading import BoundedSemaphore

from starlette.responses import JSONResponse

from app.services.pdf_extraction import PdfLimits


class UploadLimitsMiddleware:
    def __init__(self, app):
        self.app = app
        self.gate = BoundedSemaphore(1)
        self.question_gate = BoundedSemaphore(1)
        self.body_limit = PdfLimits().max_bytes + 64 * 1024

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["method"] != "POST" or scope["path"].rstrip("/") not in {"/documents", "/questions"}:
            return await self.app(scope, receive, send)
        is_question = scope["path"].rstrip("/") == "/questions"
        gate = self.question_gate if is_question else self.gate
        limit = 16000 if is_question else self.body_limit
        if not gate.acquire(blocking=False):
            return await JSONResponse(
                {"detail": {"code": "query_busy" if is_question else "upload_busy", "message": "Another request of this type is processing. Try later."}},
                status_code=503, headers={"Retry-After": "5"},
            )(scope, receive, send)
        try:
            body = bytearray()
            while True:
                message = await receive()
                if message["type"] == "http.disconnect":
                    return
                part = message.get("body", b"")
                if len(body) + len(part) > limit:
                    return await JSONResponse(
                        {"detail": {"code": "request_too_large" if is_question else "file_too_large", "message": "Request exceeds the size limit."}},
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
            gate.release()
