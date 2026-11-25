from django.contrib import admin
from django.urls import path, include
from django.views.generic import TemplateView
from django.conf import settings
from django.conf.urls.static import static

from accounts.views import serve_injury_photo
from lancer_project.views import healthz

# Custom error handlers
handler404 = 'lancer_project.views.error_404'
handler500 = 'lancer_project.views.error_500'

urlpatterns = [
    # Kubernetes probe. Unauthenticated and database-free, and registered
    # ahead of everything else so no later pattern can shadow it.
    path('healthz', healthz, name='healthz'),

    path('admin/', admin.site.urls),

    # Microsoft Entra sign-in (django-allauth, IT Services Appendix A).
    # Registered before the accounts include, whose '' route would otherwise
    # take precedence for some paths.
    path('accounts/', include('allauth.urls')),

    # Protected media.  Registered unconditionally, NOT inside the DEBUG block:
    # in production /media/ is not served by Django at all, so this view is the
    # only route to an injury photograph and every request passes through its
    # permission check.  (UWindsor IT review, finding 1.)
    path(
        'media/injury-photo/<int:injury_id>/',
        serve_injury_photo,
        name='serve_injury_photo',
    ),

    path('', include('accounts.urls')),
    path('injuries/', include('injuries.urls')),
    path('tracking/', include('injury_tracking.urls', namespace='tracking')),
    path('about/', TemplateView.as_view(template_name='about.html'), name='about'),
]

if settings.DEBUG:
    # Development convenience only.  This serves profile pictures and anything
    # else under MEDIA_ROOT without authentication, which is why it must never
    # be reachable with DEBUG=False.  Injury photos are unaffected: templates
    # link to the protected view above, not to MEDIA_URL.
    from django.contrib.staticfiles.urls import staticfiles_urlpatterns

    urlpatterns += staticfiles_urlpatterns()
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
