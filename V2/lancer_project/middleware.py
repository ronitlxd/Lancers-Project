"""
lancer_project/middleware.py

NoCacheAuthenticatedMiddleware
──────────────────────────────
Adds Cache-Control: no-store to every response served to a logged-in user.
This prevents browsers from caching protected pages, so pressing the back
button after logout cannot restore a stale authenticated view.
"""


class NoCacheAuthenticatedMiddleware:
    """Set Cache-Control: no-store on all authenticated responses."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if request.user.is_authenticated:
            response['Cache-Control'] = 'no-store, no-cache, must-revalidate, private'
            response['Pragma'] = 'no-cache'
            response['Expires'] = '0'
        return response
