from django.contrib import admin
from django.urls import path, include, re_path
from django.views.generic import TemplateView
from django.conf import settings
from django.conf.urls.static import static

# Custom error handlers
handler404 = 'lancer_project.views.error_404'
handler500 = 'lancer_project.views.error_500'

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('accounts.urls')),
    path('injuries/', include('injuries.urls')),
    path('tracking/', include('injury_tracking.urls', namespace='tracking')),
    path('about/', TemplateView.as_view(template_name='about.html'), name='about'),
]

# Serve static and media files in development
if settings.DEBUG:
    from django.contrib.staticfiles.urls import staticfiles_urlpatterns
    from accounts.views import serve_injury_photo
    urlpatterns += staticfiles_urlpatterns()
    # Injury photos: authenticated + permission-checked view
    urlpatterns += [
        re_path(
            r'^media/injury_photos/(?P<filename>[^/]+)$',
            serve_injury_photo,
            name='serve_injury_photo',
        ),
    ]
    # All other media (profile pictures, etc.): served normally in dev
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
