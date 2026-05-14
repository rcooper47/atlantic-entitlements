import base64

from django.contrib.auth import authenticate


class BasicAuthMiddleware:
    """Authenticate requests carrying an `Authorization: Basic ...` header.

    Falls through silently on malformed headers or bad credentials so other
    auth mechanisms (session login for /admin/, `force_login` in tests) still
    work. Must be installed after AuthenticationMiddleware.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if not request.user.is_authenticated:
            header = request.META.get("HTTP_AUTHORIZATION", "")
            if header.startswith("Basic "):
                try:
                    decoded = base64.b64decode(header[6:].strip()).decode("utf-8")
                except (ValueError, UnicodeDecodeError):
                    decoded = ""
                username, sep, password = decoded.partition(":")
                if sep:
                    user = authenticate(
                        request, username=username, password=password
                    )
                    if user is not None:
                        request.user = user
        return self.get_response(request)
