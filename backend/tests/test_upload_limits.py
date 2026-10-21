import asyncio

from app.upload_limits import UploadLimitsMiddleware


def scope():
    return {"type": "http", "method": "POST", "path": "/documents"}


def test_streamed_body_without_content_length_is_bounded():
    async def exercise():
        called = False

        async def app(scope, receive, send):
            nonlocal called
            called = True

        middleware = UploadLimitsMiddleware(app)
        messages = iter([
            {"type": "http.request", "body": b"a" * middleware.body_limit, "more_body": True},
            {"type": "http.request", "body": b"b", "more_body": False},
        ])
        sent = []

        async def receive():
            return next(messages)

        async def send(message):
            sent.append(message)

        await middleware(scope(), receive, send)
        assert sent[0]["status"] == 413
        assert not called
    asyncio.run(exercise())


def test_busy_upload_is_rejected_and_gate_releases_after_failure():
    async def exercise():
        async def app(scope, receive, send):
            raise RuntimeError("synthetic app failure")

        middleware = UploadLimitsMiddleware(app)
        sent = []

        async def receive():
            return {"type": "http.request", "body": b"sample", "more_body": False}

        async def send(message):
            sent.append(message)

        middleware.gate.acquire()
        await middleware(scope(), receive, send)
        assert sent[0]["status"] == 503
        middleware.gate.release()
        try:
            await middleware(scope(), receive, send)
        except RuntimeError:
            pass
        assert middleware.gate.acquire(blocking=False)
        middleware.gate.release()
    asyncio.run(exercise())
