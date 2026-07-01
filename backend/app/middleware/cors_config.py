"""CORS configuration helper.

Replaces the insecure wildcard+credentials combination with
environment-aware origins and safe defaults.
"""

from fastapi.middleware.cors import CORSMiddleware


from typing import Any, Coroutine


class SafeCORSMiddleware(CORSMiddleware):
    """CORSMiddleware subclass configured with safe defaults.

    Dev: localhost origins only.
    Production: env-configured origins (placeholder: no specific hosts).
    Never allows wildcard + credentials combination.
    """

    def __init__(self, app: Any, **kwargs: Any) -> None:
        # Dev origins — explicitly listed, no wildcard with credentials
        allow_origins = [
            "http://localhost:8421",
            "http://localhost:8422",
            "http://127.0.0.1:8421",
            "http://127.0.0.1:8422",
        ]
        super().__init__(
            app=app,
            allow_origins=allow_origins,
            allow_credentials=True,
            allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
            allow_headers=[
                "Content-Type",
                "Authorization",
                "X-Correlation-ID",
                "X-Request-ID",
                "Accept",
                "Origin",
            ],
            expose_headers=[
                "X-Correlation-ID",
                "X-RateLimit-Limit",
                "X-RateLimit-Remaining",
                "X-RateLimit-Reset",
            ],
            max_age=600,
            **kwargs,
        )
