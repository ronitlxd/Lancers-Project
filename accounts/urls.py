from django.urls import path
from . import views

urlpatterns = [
    path('', views.login_view, name='home'),
    path('login/', views.login_view, name='login'),
    path('dashboard/', views.dashboard, name='dashboard'),
    path('player/calendar/', views.player_calendar, name='player_calendar'),
    # Notifications
    path('notifications/', views.get_notifications, name='get_notifications'),
    path('notifications/all/', views.notifications_page, name='notifications_page'),
    path('notifications/<int:pk>/read/', views.mark_notification_read, name='mark_notification_read'),
    path('notifications/read-all/', views.mark_all_notifications_read, name='mark_all_notifications_read'),
    path('complete-registration/', views.complete_registration_view, name='complete_registration'),
    path('logout/', views.logout_view, name='logout'),
    path('profile/', views.profile_view, name='profile'),
    # Password reset was REMOVED with the move to Entra SSO (UWindsor IT
    # review, finding 4).  Entra owns credentials now, so a local reset flow
    # would be a second, weaker way in - and it was the only feature that
    # needed the Gmail SMTP configuration IT asked us about (their response,
    # section 1.6).
    # Team access requests
    path('request-team-access/', views.request_team_access, name='request_team_access'),
    path('team-requests/', views.admin_review_requests, name='admin_review_requests'),
    path('team-requests/<int:req_id>/<str:decision>/', views.admin_decide_request, name='admin_decide_request'),
]
