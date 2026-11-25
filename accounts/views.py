from pathlib import Path

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, authenticate, logout
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.utils import timezone
from .forms import (
    PlayerProfileForm, CoachProfileForm, DoctorProfileForm,
    TeamSelectionForm, CoachTeamSelectionForm, UserProfileForm, TeamPermissionRequestForm,
    PlayerSelfPersonalForm, PlayerSelfSportForm,
)
from lancer_project.audit import audit
from .models import PlayerProfile, CoachProfile, DoctorProfile, TeamPermissionRequest, TeamPermission, CustomUser

def csrf_failure(request, reason=""):
    """Friendly CSRF failure handler.

    Most CSRF 403s on this app come from stale tokens after a session rotation
    (login, registration step transition, server restart). Instead of showing
    Django's debug 403 page, drop a flash message and bounce the user back to
    the same URL so they get a fresh form + token.
    """
    from django.contrib import messages as _messages
    _messages.warning(
        request,
        "Your session timed out — please try again."
    )
    target = request.META.get('HTTP_REFERER') or request.path or '/login/'
    # Don't loop on a POST URL — fall back to login
    if request.method == 'POST' and target == request.path:
        target = '/login/'
    return redirect(target)


# ---------------------------------------------------------------------------
# Public self-registration was REMOVED (UWindsor IT review, findings 1 and 3).
#
# The old flow let anyone reach /register/ and took their role from the email
# address they typed, with no verification step: registering as
# <anything>@doctor.uwindsor.ca granted Athletic Therapist access to athlete
# medical records.  It also wrote an unauthenticated visitor's uploaded file
# into MEDIA_ROOT under their session key, with the extension taken from the
# client.
#
# Accounts are now provisioned by an administrator, who assigns the role and
# team.  Entra will authenticate; Django remains the authority on who may do
# what (IT Services response, sections 1.2, 1.3 and 3.6).  New users still
# finish their own profile through complete_registration_view below.
# ---------------------------------------------------------------------------


@login_required
def complete_registration_view(request):
    """Complete registration with role-specific information"""
    user = request.user
    
    if user.is_registration_complete:
        return redirect('dashboard')
    
    if request.method == 'POST':
        if user.role == 'PLAYER':
            profile_form = PlayerProfileForm(request.POST, request.FILES)
            team_form = TeamSelectionForm(request.POST)
            
            if profile_form.is_valid() and team_form.is_valid():
                # Create player profile
                profile = profile_form.save(commit=False)
                profile.user = user
                profile.save()
                
                # Assign team
                user.team = team_form.cleaned_data['team']
                user.is_registration_complete = True
                user.save()
                
                messages.success(request, 'Registration completed successfully!')
                return redirect('dashboard')
                
        elif user.role == 'COACH':
            profile_form = CoachProfileForm(request.POST)
            
            if profile_form.is_valid():
                # Create coach profile
                profile = profile_form.save(commit=False)
                profile.user = user
                profile.save()
                
                # Coaches cannot select their own team - only admins assign teams.
                # Any team already set by an administrator is kept; otherwise it
                # stays blank until one is assigned (no access by default).
                
                user.is_registration_complete = True
                user.save()
                
                if not user.team:
                    messages.success(request, 'Registration completed! An admin will assign your team shortly.')
                else:
                    messages.success(request, 'Registration completed successfully!')
                return redirect('dashboard')
                
        elif user.role == 'DOCTOR':
            profile_form = DoctorProfileForm(request.POST)
            
            if profile_form.is_valid():
                # Create doctor profile
                profile = profile_form.save(commit=False)
                profile.user = user
                profile.save()
                
                # Doctors don't need team assignment
                user.is_registration_complete = True
                user.save()
                
                messages.success(request, 'Registration completed successfully!')
                return redirect('dashboard')
    else:
        # Initialize forms based on user role
        if user.role == 'PLAYER':
            profile_form = PlayerProfileForm()
            team_form = TeamSelectionForm()
        elif user.role == 'COACH':
            profile_form = CoachProfileForm()
            # Coaches cannot select their own team - only admins can assign (security)
            team_form = None
        elif user.role == 'DOCTOR':
            profile_form = DoctorProfileForm()
            team_form = None
        else:
            messages.error(request, 'Invalid user role.')
            return redirect('register')
    
    context = {
        'user': user,
        'profile_form': profile_form,
        'team_form': team_form,
    }
    
    return render(request, 'accounts/complete_registration.html', context)

def login_view(request):
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            # Check if user needs to complete registration
            if not user.is_registration_complete:
                return redirect('complete_registration')
            return redirect('dashboard')
        else:
            return render(request, 'accounts/login.html', {'error': 'Invalid credentials'})
    return render(request, 'accounts/login.html')

def logout_view(request):
    # Clear any AXES lockout records for this user before logging out
    try:
        from axes.models import AccessAttempt
        if request.user.is_authenticated:
            AccessAttempt.objects.filter(username=request.user.username).delete()
    except Exception:
        pass
    logout(request)
    return redirect('login')

@login_required
def dashboard(request):
    """Redirect to appropriate dashboard based on user role"""
    user = request.user
    
    # Check if registration is complete first
    if not user.is_registration_complete:
        return redirect('complete_registration')
    
    if user.role == 'ADMIN':
        return redirect('tracking:admin_dashboard')
    elif user.role == 'COACH':
        # If coach has no team, show a message instead of redirecting to coach_dashboard
        if not user.team:
            messages.info(request, 'Your registration is complete! An administrator will assign your team shortly.')
            # Show a simple page or redirect to profile
            return redirect('profile')
        return redirect('tracking:coach_dashboard')
    elif user.role == 'DOCTOR':
        return redirect('tracking:doctor_dashboard')
    elif user.role == 'PLAYER':
        return redirect('tracking:player_dashboard')
    else:
        return redirect('login')

@login_required
def profile_view(request):
    user = request.user

    # Players get a streamlined profile page showing only fields captured at registration.
    if user.role == 'PLAYER':
        return _player_profile_view(request)

    if request.method == 'POST':
        form = UserProfileForm(request.POST, request.FILES, instance=user)
        if form.is_valid():
            # Security: Prevent coaches from changing their team assignment
            # Team can only be changed by admins via admin panel
            if user.role == 'COACH' and 'team' in request.POST:
                messages.warning(request, 'Team assignment cannot be changed. Please contact an administrator.')
                return redirect('profile')
            
            form.save()
            messages.success(request, 'Your profile has been updated successfully!')
            return redirect('profile')
    else:
        form = UserProfileForm(instance=user)
    
    # Get role-specific profile information
    role_profile = None
    if user.role == 'PLAYER':
        try:
            role_profile = user.playerprofile
        except PlayerProfile.DoesNotExist:
            role_profile = None
    elif user.role == 'COACH':
        try:
            role_profile = user.coachprofile
        except CoachProfile.DoesNotExist:
            role_profile = None
    elif user.role == 'DOCTOR':
        try:
            role_profile = user.doctorprofile
        except DoctorProfile.DoesNotExist:
            role_profile = None
    
    context = {
        'form': form,
        'user': user,
        'role_profile': role_profile,
    }
    
    return render(request, 'accounts/user_profile.html', context)

def _player_profile_view(request):
    """Player-only profile page. Shows only fields collected during registration."""
    user = request.user
    profile, _ = PlayerProfile.objects.get_or_create(user=user)

    if request.method == 'POST':
        personal = PlayerSelfPersonalForm(request.POST, request.FILES, instance=user)
        sport = PlayerSelfSportForm(request.POST, instance=profile)
        # Pre-fill team since it lives on CustomUser, not PlayerProfile
        if user.team and 'team' not in request.POST:
            sport.fields['team'].initial = user.team
        if personal.is_valid() and sport.is_valid():
            personal.save()
            profile = sport.save(commit=False)
            profile.user = user
            profile.save()
            user.team = sport.cleaned_data['team']
            user.save(update_fields=['team'])
            messages.success(request, 'Profile updated.')
            return redirect('profile')
    else:
        personal = PlayerSelfPersonalForm(instance=user)
        sport = PlayerSelfSportForm(instance=profile, initial={'team': user.team})

    return render(request, 'accounts/player_profile.html', {
        'user': user,
        'profile': profile,
        'personal_form': personal,
        'sport_form': sport,
    })


@login_required
def player_calendar(request):
    """Full monthly calendar for the player — team events, appointments, and injuries."""
    if request.user.role != 'PLAYER':
        messages.error(request, "Player access required.")
        return redirect('dashboard')

    from datetime import timedelta
    import json
    from injury_tracking.models import Event, Appointment, InjuryRecord

    today = timezone.now().date()
    cutoff = today - timedelta(days=60)

    team_events = []
    if request.user.team:
        team_events = list(Event.objects.filter(
            team=request.user.team,
            end_datetime__date__gte=cutoff,
        ).order_by('start_datetime'))

    player_appointments = list(Appointment.objects.filter(
        player=request.user,
        preferred_date__gte=cutoff,
    ).select_related('therapist').order_by('preferred_date'))

    # Injuries are NOT shown on the player calendar — they appear in the dashboard instead
    player_follow_ups = list(InjuryRecord.objects.filter(
        player=request.user,
        follow_up_required=True,
        follow_up_date__isnull=False,
        follow_up_date__gte=cutoff,
    ).select_related('injury_type', 'body_part').order_by('follow_up_date'))

    events_data = []
    for ev in team_events:
        events_data.append({
            'title': ev.title,
            'start': ev.start_datetime.isoformat(),
            'end': ev.end_datetime.isoformat(),
            'color': '#0b76ef',
            'extendedProps': {
                'kind': 'team_event',
                'event_type': ev.get_event_type_display(),
                'location': ev.location or '',
            },
        })
    for a in player_appointments:
        color = '#10b981' if a.status == 'CONFIRMED' else (
            '#ef4444' if a.status == 'CANCELLED' else '#f59e0b'
        )
        events_data.append({
            'title': f"Appointment ({a.get_status_display()})",
            'start': a.preferred_date.isoformat(),
            'allDay': True,
            'color': color,
            'extendedProps': {
                'kind': 'appointment',
                'status': a.get_status_display(),
                'therapist': (a.therapist.get_full_name() if a.therapist else 'TBD'),
                'time_slot': a.get_preferred_time_slot_display(),
                'note': a.note or '',
            },
        })
    for fu in player_follow_ups:
        events_data.append({
            'title': f"Follow-up: {fu.body_part.name}",
            'start': fu.follow_up_date.isoformat(),
            'allDay': True,
            'color': '#8b5cf6',
            'extendedProps': {
                'kind': 'follow_up',
                'body_part': fu.body_part.name,
                'injury_type': fu.injury_type.name,
                'status': fu.get_status_display(),
            },
        })

    # Upcoming events for the desktop right sidebar
    upcoming = []
    for ev in team_events:
        if ev.start_datetime.date() >= today:
            upcoming.append({
                'when': ev.start_datetime,
                'title': ev.title,
                'kind': 'event',
                'meta': ev.get_event_type_display(),
            })
    for a in player_appointments:
        if a.preferred_date >= today:
            upcoming.append({
                'when': a.preferred_date,
                'title': f"Appointment — {a.get_status_display()}",
                'kind': 'appointment',
                'meta': a.get_preferred_time_slot_display(),
            })
    for fu in player_follow_ups:
        if fu.follow_up_date >= today:
            upcoming.append({
                'when': fu.follow_up_date,
                'title': f"Follow-up: {fu.body_part.name}",
                'kind': 'follow_up',
                'meta': fu.get_status_display(),
            })
    # Sort by datetime/date — coerce to naive datetime for comparison
    from datetime import datetime as _dt
    def _key(item):
        w = item['when']
        if isinstance(w, _dt):
            return w.replace(tzinfo=None)  # strip tz so naive/aware don't clash
        return _dt.combine(w, _dt.min.time())
    upcoming.sort(key=_key)
    upcoming = upcoming[:6]

    unread_notifications = 0
    try:
        from .models import Notification
        unread_notifications = Notification.objects.filter(
            user=request.user, is_read=False
        ).count()
    except Exception:
        pass

    return render(request, 'accounts/player_calendar.html', {
        'events_json': json.dumps(events_data),
        'upcoming': upcoming,
        'unread_notifications': unread_notifications,
    })


@login_required
def get_notifications(request):
    """JSON: last 10 notifications + unread count, for the bell dropdown."""
    from .models import Notification
    qs = Notification.objects.filter(user=request.user).order_by('-created_at')
    unread_count = qs.filter(is_read=False).count()
    items = []
    for n in qs[:10]:
        items.append({
            'id': n.id,
            'message': n.message,
            'type': n.notification_type,
            'link': n.link or '',
            'is_read': n.is_read,
            'created_at': n.created_at.isoformat(),
        })
    return JsonResponse({'unread_count': unread_count, 'notifications': items})


@login_required
@require_POST
def mark_notification_read(request, pk):
    from .models import Notification
    n = get_object_or_404(Notification, pk=pk, user=request.user)
    if not n.is_read:
        n.is_read = True
        n.save(update_fields=['is_read'])
    return JsonResponse({'ok': True})


@login_required
@require_POST
def mark_all_notifications_read(request):
    from .models import Notification
    Notification.objects.filter(user=request.user, is_read=False).update(is_read=True)
    return JsonResponse({'ok': True})


@login_required
def notifications_page(request):
    """Full notifications list page with pagination."""
    from .models import Notification
    from django.core.paginator import Paginator

    qs = Notification.objects.filter(user=request.user).order_by('-created_at')
    unread_count = qs.filter(is_read=False).count()

    # Mark all as read on page visit
    qs.filter(is_read=False).update(is_read=True)

    paginator = Paginator(qs, 20)
    page_obj = paginator.get_page(request.GET.get('page'))

    return render(request, 'accounts/notifications.html', {
        'page_obj': page_obj,
        'unread_count': unread_count,
    })


@login_required
def request_team_access(request):
    if request.user.role not in ['COACH', 'DOCTOR', 'ADMIN']:
        messages.error(request, 'Only coaches and doctors can request additional team access.')
        return redirect('dashboard')
    if request.method == 'POST':
        form = TeamPermissionRequestForm(request.POST)
        if form.is_valid():
            req = form.save(commit=False)
            req.user = request.user
            req.status = 'PENDING'
            req.save()
            messages.success(request, 'Your request has been submitted for admin approval.')
            return redirect('request_team_access')
    else:
        form = TeamPermissionRequestForm()
    my_requests = TeamPermissionRequest.objects.filter(user=request.user).order_by('-created_at')
    return render(request, 'accounts/request_team_access.html', {'form': form, 'my_requests': my_requests})

@login_required
def admin_review_requests(request):
    if request.user.role != 'ADMIN':
        messages.error(request, 'Admin access required.')
        return redirect('dashboard')
    pending = TeamPermissionRequest.objects.filter(status='PENDING')
    return render(request, 'accounts/admin_team_requests.html', {'pending': pending})

@login_required
@require_POST
def admin_decide_request(request, req_id, decision):
    if request.user.role != 'ADMIN':
        messages.error(request, 'Admin access required.')
        return redirect('dashboard')
    req = get_object_or_404(TeamPermissionRequest, id=req_id)
    if req.status != 'PENDING':
        messages.info(request, 'This request has already been processed.')
        return redirect('admin_review_requests')
    if decision not in ['approve', 'deny']:
        messages.error(request, 'Invalid decision.')
        return redirect('admin_review_requests')
    if decision == 'approve':
        # Create TeamPermission
        TeamPermission.objects.get_or_create(user=req.user, team=req.team, role_scope=req.role_scope)
        req.status = 'APPROVED'
        messages.success(request, 'Request approved and access granted.')
    else:
        req.status = 'DENIED'
        messages.info(request, 'Request denied.')
    req.reviewed_by = request.user
    req.reviewed_at = timezone.now()
    req.save()
    # Granting a team permission widens who can read clinical data, so it is
    # an auditable event in its own right (UWindsor IT review, finding 7).
    audit(
        'TEAM_PERMISSION_DECISION',
        actor=request.user,
        request=request,
        target_type='TeamPermissionRequest',
        target_id=req.id,
        subject_id=req.user_id,
        team_id=req.team_id,
        role_scope=req.role_scope,
        decision=req.status,
    )
    return redirect('admin_review_requests')


# ---------------------------------------------------------------------------
# Protected media serving
#
# UWindsor IT review, finding 1: injury photographs were reachable without an
# authorization check in production.  The cause was routing: this view existed
# but lancer_project/urls.py only registered it inside `if settings.DEBUG:`, so
# in production /media/ was served by the web server and never reached Django.
#
# The route is now registered unconditionally and keyed on the injury's primary
# key rather than a filename, which removes both the fragile
# `photo='injury_photos/' + filename` lookup and the path-traversal surface.
#
# Profile pictures remain unprotected by design. Any other upload that needs
# restricting should follow the same pattern as this view.
# ---------------------------------------------------------------------------
from django.http import FileResponse, Http404

from injury_tracking.permissions import can_view_injury_photo

_PHOTO_CONTENT_TYPES = {
    '.jpg': 'image/jpeg',
    '.jpeg': 'image/jpeg',
    '.png': 'image/png',
    '.webp': 'image/webp',
}


@login_required
def serve_injury_photo(request, injury_id):
    """Serve an injury photograph to a user authorized to see it.

    Denials raise Http404 rather than PermissionDenied: a 403 would confirm
    that a photo exists for that injury, which is itself a disclosure.
    """
    from injury_tracking.models import InjuryRecord

    injury = get_object_or_404(
        InjuryRecord.objects.select_related('player'), pk=injury_id
    )

    if not injury.photo or not can_view_injury_photo(request.user, injury):
        audit(
            'INJURY_PHOTO_VIEW',
            actor=request.user,
            request=request,
            outcome='FAILURE',
            target_type='InjuryRecord',
            target_id=injury_id,
        )
        raise Http404

    audit(
        'INJURY_PHOTO_VIEW',
        actor=request.user,
        request=request,
        target_type='InjuryRecord',
        target_id=injury.pk,
    )

    suffix = Path(injury.photo.name).suffix.lower()
    response = FileResponse(
        injury.photo.open('rb'),
        content_type=_PHOTO_CONTENT_TYPES.get(suffix, 'application/octet-stream'),
    )
    # Never let a browser sniff a stored file into something executable.
    response['X-Content-Type-Options'] = 'nosniff'
    response['Content-Disposition'] = 'inline'
    # Cache-Control: no-store is already applied to authenticated responses by
    # lancer_project.middleware.NoCacheAuthenticatedMiddleware.
    return response
