"""Project-level views: health check and custom error handlers."""
from django.http import HttpResponse
from django.shortcuts import render


def healthz(request):
    """Liveness/readiness probe for Kubernetes.

    Must stay unauthenticated and must not touch the database: a probe
    that needs a session or a query will fail the pod for reasons that
    have nothing to do with whether the process is alive.
    """
    return HttpResponse("OK", status=200, content_type="text/plain")


def error_404(request, exception=None):
    return render(request, '404.html', status=404)


def error_500(request):
    return render(request, '500.html', status=500)
