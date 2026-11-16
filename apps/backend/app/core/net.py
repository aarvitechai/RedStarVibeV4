from starlette.requests import Request


def client_ip(request: Request) -> str:
    """Client IP. Only the gateway (behind Cloudflare) can reach the app, so its forwarding headers are trusted."""
    cf = request.headers.get("cf-connecting-ip")
    if cf:
        return cf.strip()
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    return request.client.host if request.client else "0.0.0.0"  # noqa: S104 - placeholder, never bound
