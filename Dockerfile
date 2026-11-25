# LancersPulse container image for University of Windsor Kubernetes.
# Follows Appendix A of the IT Services deployment review response.

FROM python:3.12-slim

# PYTHONUNBUFFERED matters here: audit events are written to stderr and the
# platform pipeline forwards them to the University SIEM. Buffered output
# would delay or lose them when a pod is terminated.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Collect static at build time. STATICFILES_STORAGE is WhiteNoise's
# CompressedManifestStaticFilesStorage, which needs its manifest to exist
# before the first request or every {% static %} tag raises.
# These values are build-only; the real ones are injected at runtime.
RUN SECRET_KEY=build-time-only \
    DEBUG=False \
    MEDIA_ROOT=/tmp/build-media \
    python manage.py collectstatic --noinput

# Run as a non-root user (IT Services response, section 1.10).
# The uid is fixed so the PersistentVolume can be owned by it.
RUN useradd --create-home --uid 10001 appuser \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 8080

# Single replica, so migrations run on start. Revisit if this is ever scaled:
# concurrent migrate on a shared SQLite file would race.
CMD ["sh", "-c", "python manage.py migrate --noinput && exec gunicorn --bind 0.0.0.0:8080 --workers 2 --access-logfile - --error-logfile - lancer_project.wsgi:application"]
