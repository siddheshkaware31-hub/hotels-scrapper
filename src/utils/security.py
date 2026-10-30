"""Security validators to prevent SSRF, path traversal, and malicious inputs."""

import urllib.parse

ALLOWED_GOOGLE_HOSTS = {
    "google.com",
    "maps.google.com",
    "www.google.com",
    "goo.gl",
    "maps.app.goo.gl",
}


def is_safe_maps_url(url: str) -> bool:
    """Validate that the target URL is strictly a legitimate Google Maps HTTP(S) endpoint.

    Prevents SSRF (Server-Side Request Forgery), file:// navigation,
    internal metadata endpoint access (e.g. 169.254.169.254), and javascript: URIs.
    """
    if not url or not isinstance(url, str):
        return False

    try:
        parsed = urllib.parse.urlparse(url.strip())
        if parsed.scheme not in ("http", "https"):
            return False

        hostname = (parsed.hostname or "").lower()
        if not hostname:
            return False

        # Reject private/loopback IP addresses
        if hostname in ("localhost", "127.0.0.1", "::1", "169.254.169.254", "0.0.0.0"):
            return False

        # Ensure hostname matches or ends with approved Google domains
        if (
            hostname in ALLOWED_GOOGLE_HOSTS
            or hostname.endswith(".google.com")
            or hostname.endswith(".goo.gl")
        ):
            return True

        return False
    except Exception:
        return False
