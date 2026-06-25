"""
injury_tracking/forms.py — Team 12 updated version
Changes vs Team 13:
  - InjuryReportForm: added contact_type field
  - InjuryUpdateForm: added contact_type, missed_games, missed_practices fields
  - InjurySearchForm: added contact_type and season_year filter fields
Everything else is unchanged from Team 13.
"""

from django import forms
from django.contrib.auth import get_user_model
from django.utils import timezone
from .models import (
    InjuryRecord, InjuryType, BodyPart, InjurySeverity,
    InjuryFollowUp, TeamRoster, Event
)

User = get_user_model()


class InjuryReportForm(forms.ModelForm):
    """Form for doctors/therapists to report a new injury."""

    class Meta:
        model = InjuryRecord
        fields = [
            'player', 'injury_date',
            'injury_type', 'body_part', 'severity',
            # --- Team 12 addition ---
            'contact_type',
            # ------------------------
            # --- Player self-report fields (optional for doctor entry too) ---
            'context', 'could_continue', 'pain_level', 'injury_nature', 'photo',
            # -------------------------------------------------------------------
            'description', 'symptoms',
            'treatment', 'treatment_notes',
            'estimated_recovery_time',
            'missed_games', 'missed_practices',   # Team 12 addition
            'requires_surgery', 'surgery_date',
            'follow_up_required', 'follow_up_date', 'follow_up_notes',
            'is_confidential',
        ]
        widgets = {
            'injury_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'description': forms.Textarea(attrs={'rows': 4, 'class': 'form-control'}),
            'symptoms': forms.Textarea(attrs={'rows': 3, 'class': 'form-control'}),
            'treatment_notes': forms.Textarea(attrs={'rows': 3, 'class': 'form-control'}),
            'follow_up_notes': forms.Textarea(attrs={'rows': 3, 'class': 'form-control'}),
            'surgery_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'follow_up_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'player': forms.Select(attrs={'class': 'form-control'}),
            'injury_type': forms.Select(attrs={'class': 'form-control'}),
            'body_part': forms.Select(attrs={'class': 'form-control'}),
            'severity': forms.Select(attrs={'class': 'form-control'}),
            'treatment': forms.Select(attrs={'class': 'form-control'}),
            # Team 12 widgets
            'contact_type': forms.Select(attrs={'class': 'form-control'}),
            'missed_games': forms.NumberInput(attrs={'class': 'form-control', 'min': 0}),
            'missed_practices': forms.NumberInput(attrs={'class': 'form-control', 'min': 0}),
            # ---
            # Player self-report fields
            'context': forms.Select(attrs={'class': 'form-control'}),
            'could_continue': forms.Select(attrs={'class': 'form-control'}),
            'pain_level': forms.NumberInput(attrs={'class': 'form-control', 'min': 0, 'max': 10}),
            'injury_nature': forms.Select(attrs={'class': 'form-control'}),
            'photo': forms.ClearableFileInput(attrs={'class': 'form-control', 'accept': 'image/*'}),
            # ---
            'estimated_recovery_time': forms.NumberInput(attrs={'class': 'form-control'}),
            'requires_surgery': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'follow_up_required': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'is_confidential': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)

        # Help text for new fields
        self.fields['contact_type'].help_text = (
            "Contact: caused by collision/external force. "
            "Non-Contact: athlete's own movement (e.g. ACL tear while running). "
            "Overuse: repetitive strain over time. "
            "Non-contact and overuse injuries are tracked as potentially preventable."
        )
        self.fields['missed_games'].help_text = "Leave blank if unknown at time of reporting — update later."
        self.fields['missed_practices'].help_text = "Leave blank if unknown at time of reporting — update later."

        # Player self-report fields — optional here; usually filled in by the
        # player's own report, but a doctor can set/correct them directly.
        self.fields['context'].help_text = "What the player was doing when the injury occurred."
        self.fields['could_continue'].help_text = "Whether the player was able to keep playing after the injury."
        self.fields['pain_level'].help_text = "Player's self-reported pain level, 0 (none) to 10 (worst)."
        self.fields['injury_nature'].help_text = "Player's own description of the type of injury (e.g. twist, bruise)."
        self.fields['photo'].help_text = "Optional photo of the injury."

        # ── Player queryset logic (unchanged from Team 13) ─────────────────
        authorized_teams = None
        authorized_teams_count = 0
        if user and hasattr(user, 'get_authorized_teams'):
            try:
                authorized_teams = user.get_authorized_teams()
                if authorized_teams is not None:
                    try:
                        authorized_teams_count = authorized_teams.count()
                    except Exception:
                        try:
                            authorized_teams_count = len(authorized_teams) if authorized_teams else 0
                        except Exception:
                            authorized_teams_count = 0
            except Exception:
                authorized_teams = None
                authorized_teams_count = 0

        if user and user.role == 'ADMIN':
            player_queryset = User.objects.filter(role='PLAYER').order_by('last_name', 'first_name')
        elif user and user.role == 'DOCTOR':
            if authorized_teams_count > 1:
                self.fields['team'] = forms.ModelChoiceField(
                    queryset=authorized_teams,
                    required=True,
                    empty_label="Select a team",
                    widget=forms.Select(attrs={'class': 'form-control', 'id': 'id_team_selector'}),
                )
                field_order = ['team'] + [name for name in self.fields if name != 'team']
                self.order_fields(field_order)

                selected_team = None
                data = args[0] if args else None
                if data and 'team' in data:
                    try:
                        selected_team = authorized_teams.get(id=data.get('team'))
                    except Exception:
                        selected_team = None
                if selected_team is None and user.team:
                    try:
                        if user.team in list(authorized_teams):
                            selected_team = user.team
                    except Exception:
                        pass

                if selected_team:
                    player_queryset = User.objects.filter(
                        role='PLAYER', team=selected_team
                    ).order_by('last_name', 'first_name')
                else:
                    player_queryset = User.objects.filter(
                        role='PLAYER', team__in=authorized_teams
                    ).order_by('last_name', 'first_name')
            elif authorized_teams_count == 1:
                team = authorized_teams.first()
                player_queryset = (
                    User.objects.filter(role='PLAYER', team=team).order_by('last_name', 'first_name')
                    if team
                    else User.objects.filter(role='PLAYER').order_by('last_name', 'first_name')
                )
            elif user.team:
                player_queryset = User.objects.filter(
                    role='PLAYER', team=user.team
                ).order_by('last_name', 'first_name')
            else:
                player_queryset = User.objects.filter(role='PLAYER').order_by('last_name', 'first_name')
        elif user and user.role == 'COACH':
            player_queryset = (
                User.objects.filter(role='PLAYER', team=user.team).order_by('last_name', 'first_name')
                if user.team
                else User.objects.filter(role='PLAYER', team=None)
            )
        else:
            player_queryset = User.objects.filter(role='PLAYER').order_by('last_name', 'first_name')

        self.fields['player'].queryset = player_queryset
        # ───────────────────────────────────────────────────────────────────


class InjuryUpdateForm(forms.ModelForm):
    """Form for updating an existing injury record (therapist/doctor view)."""

    class Meta:
        model = InjuryRecord
        fields = [
            'status',
            'description', 'symptoms',
            'treatment', 'treatment_notes',
            # --- Team 12 additions ---
            'contact_type',
            'missed_games', 'missed_practices',
            # -------------------------
            # --- Player self-report fields (visible + editable on review) ---
            'context', 'could_continue', 'pain_level', 'injury_nature', 'photo',
            # -------------------------------------------------------------------
            'estimated_recovery_time', 'actual_recovery_time', 'return_to_play_date',
            'medical_clearance', 'clearance_date',
            'requires_surgery', 'surgery_date',
            'follow_up_required', 'follow_up_date', 'follow_up_notes',
            'is_confidential',
        ]
        widgets = {
            'status': forms.Select(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'rows': 4, 'class': 'form-control'}),
            'symptoms': forms.Textarea(attrs={'rows': 3, 'class': 'form-control'}),
            'treatment': forms.Select(attrs={'class': 'form-control'}),
            'treatment_notes': forms.Textarea(attrs={'rows': 3, 'class': 'form-control'}),
            # Team 12 widgets
            'contact_type': forms.Select(attrs={'class': 'form-control'}),
            'missed_games': forms.NumberInput(attrs={'class': 'form-control', 'min': 0}),
            'missed_practices': forms.NumberInput(attrs={'class': 'form-control', 'min': 0}),
            # ---
            # Player self-report fields
            'context': forms.Select(attrs={'class': 'form-control'}),
            'could_continue': forms.Select(attrs={'class': 'form-control'}),
            'pain_level': forms.NumberInput(attrs={'class': 'form-control', 'min': 0, 'max': 10}),
            'injury_nature': forms.Select(attrs={'class': 'form-control'}),
            'photo': forms.ClearableFileInput(attrs={'class': 'form-control', 'accept': 'image/*'}),
            # ---
            'estimated_recovery_time': forms.NumberInput(attrs={'class': 'form-control'}),
            'actual_recovery_time': forms.NumberInput(attrs={'class': 'form-control'}),
            'return_to_play_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'clearance_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'surgery_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'follow_up_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'follow_up_notes': forms.Textarea(attrs={'rows': 3, 'class': 'form-control'}),
            'medical_clearance': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'requires_surgery': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'follow_up_required': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'is_confidential': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['status'].required = True
        self.fields['status'].help_text = 'Update the current status of the injury.'
        self.fields['contact_type'].help_text = (
            'Classify as Contact, Non-Contact, or Overuse. '
            'Non-contact and overuse injuries are flagged as potentially preventable in reports.'
        )
        self.fields['missed_games'].help_text = 'Total official games missed so far.'
        self.fields['missed_practices'].help_text = 'Total practices / training sessions missed so far.'
        self.fields['medical_clearance'].help_text = 'Check when player has received medical clearance to return to play.'
        self.fields['clearance_date'].help_text = 'Date medical clearance was granted.'
        self.fields['actual_recovery_time'].help_text = (
            'Actual recovery time in days '
            '(calculated automatically when status is set to RECOVERED).'
        )
        self.fields['context'].help_text = "What the player was doing when the injury occurred."
        self.fields['could_continue'].help_text = "Whether the player was able to keep playing after the injury."
        self.fields['pain_level'].help_text = "Player's self-reported pain level, 0 (none) to 10 (worst)."
        self.fields['injury_nature'].help_text = "Player's own description of the type of injury (e.g. twist, bruise)."
        self.fields['photo'].help_text = "Optional photo of the injury. Upload a new one to replace it."



class InjuryFollowUpForm(forms.ModelForm):
    """Form for injury follow-ups — unchanged from Team 13."""

    class Meta:
        model = InjuryFollowUp
        fields = ['follow_up_date', 'notes', 'status_update']
        widgets = {
            'follow_up_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'notes': forms.Textarea(attrs={'rows': 4, 'class': 'form-control'}),
            'status_update': forms.Select(attrs={'class': 'form-control'}),
        }


class InjurySearchForm(forms.Form):
    """
    Form for searching and filtering injuries.
    Team 12 additions: contact_type filter, season_year filter.
    """
    player = forms.ModelChoiceField(
        queryset=User.objects.filter(role='PLAYER'),
        required=False,
        empty_label="All Players",
        widget=forms.Select(attrs={'class': 'form-control'}),
    )
    injury_type = forms.ModelChoiceField(
        queryset=InjuryType.objects.all(),
        required=False,
        empty_label="All Injury Types",
        widget=forms.Select(attrs={'class': 'form-control'}),
    )
    body_part = forms.ModelChoiceField(
        queryset=BodyPart.objects.all(),
        required=False,
        empty_label="All Body Parts",
        widget=forms.Select(attrs={'class': 'form-control'}),
    )
    severity = forms.ModelChoiceField(
        queryset=InjurySeverity.objects.all(),
        required=False,
        empty_label="All Severities",
        widget=forms.Select(attrs={'class': 'form-control'}),
    )
    status = forms.ChoiceField(
        choices=[('', 'All Statuses')] + InjuryRecord.STATUS_CHOICES,
        required=False,
        widget=forms.Select(attrs={'class': 'form-control'}),
    )
    # ── Team 12 additions ────────────────────────────────────────────────
    contact_type = forms.ChoiceField(
        choices=[('', 'All Contact Types')] + InjuryRecord.CONTACT_TYPE_CHOICES,
        required=False,
        widget=forms.Select(attrs={'class': 'form-control'}),
        label="Contact type",
    )
    season_year = forms.IntegerField(
        required=False,
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'placeholder': 'e.g. 2025',
            'min': 2000,
        }),
        label="Season year",
        help_text="e.g. enter 2025 to see all injuries from the 2025–26 season.",
    )
    # ─────────────────────────────────────────────────────────────────────
    date_from = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
        label="From date",
    )
    date_to = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
        label="To date",
    )


class PlayerProfileForm(forms.ModelForm):
    """Form for players to update their profile — unchanged from Team 13."""

    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'email']
        widgets = {
            'first_name': forms.TextInput(attrs={'class': 'form-control'}),
            'last_name': forms.TextInput(attrs={'class': 'form-control'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
        }


class TeamRosterForm(forms.ModelForm):
    """Form for managing team roster — unchanged from Team 13."""

    class Meta:
        model = TeamRoster
        fields = ['player', 'position', 'jersey_number', 'is_active']
        widgets = {
            'player': forms.Select(attrs={'class': 'form-control'}),
            'position': forms.TextInput(attrs={'class': 'form-control'}),
            'jersey_number': forms.NumberInput(attrs={'class': 'form-control'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }


class EventForm(forms.ModelForm):
    """Form for creating/updating team events — unchanged from Team 13."""

    class Meta:
        model = Event
        fields = ['team', 'event_type', 'title', 'description', 'location', 'start_datetime', 'end_datetime']
        widgets = {
            'team': forms.Select(attrs={'class': 'form-control'}),
            'event_type': forms.Select(attrs={'class': 'form-control'}),
            'title': forms.TextInput(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'rows': 3, 'class': 'form-control'}),
            'location': forms.TextInput(attrs={'class': 'form-control'}),
            'start_datetime': forms.DateTimeInput(
                attrs={'type': 'datetime-local', 'class': 'form-control'},
                format='%Y-%m-%dT%H:%M',
            ),
            'end_datetime': forms.DateTimeInput(
                attrs={'type': 'datetime-local', 'class': 'form-control'},
                format='%Y-%m-%dT%H:%M',
            ),
        }

    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        if user and user.role == 'COACH':
            authorized_teams = user.get_authorized_teams() if hasattr(user, 'get_authorized_teams') else None
            if authorized_teams is not None:
                self.fields['team'].queryset = authorized_teams
            elif user.team:
                from accounts.models import Team
                self.fields['team'].queryset = Team.objects.filter(id=user.team.id)


class PlayerInjuryReportForm(forms.ModelForm):
    """
    Player self-report form (2-step wizard: Report -> Review).

    Deliberately excludes clinical fields (injury_type, severity, treatment) —
    those are placeholder-defaulted at creation time and confirmed by the
    therapist later. The player only reports what they themselves observed.
    """

    class Meta:
        model = InjuryRecord
        fields = [
            'body_part', 'injury_date', 'description',
            'context', 'contact_type', 'could_continue',
            'pain_level', 'injury_nature', 'photo',
        ]
        widgets = {
            'body_part': forms.Select(attrs={'class': 'form-select'}),
            'injury_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'description': forms.Textarea(attrs={
                'rows': 4, 'class': 'form-control', 'maxlength': 500,
                'placeholder': 'Describe what happened...',
            }),
            'context': forms.RadioSelect,
            'contact_type': forms.RadioSelect,
            'could_continue': forms.RadioSelect,
            'pain_level': forms.NumberInput(attrs={
                'type': 'range', 'class': 'form-range', 'min': 0, 'max': 10, 'step': 1,
            }),
            'injury_nature': forms.RadioSelect,
            'photo': forms.ClearableFileInput(attrs={'class': 'form-control', 'accept': 'image/*'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['body_part'].queryset = BodyPart.objects.all().order_by('name')
        self.fields['body_part'].empty_label = "Select where it hurts..."
        self.fields['body_part'].required = True
        self.fields['injury_date'].required = True
        self.fields['injury_date'].widget.attrs['max'] = timezone.localdate().isoformat()
        self.fields['description'].required = True
        self.fields['description'].help_text = (
            "Add at least a sentence so your therapist understands the situation."
        )
        self.fields['context'].required = True
        self.fields['contact_type'].required = False
        self.fields['could_continue'].required = False
        self.fields['pain_level'].required = False
        self.fields['injury_nature'].required = False
        self.fields['photo'].required = False

    def clean_injury_date(self):
        injury_date = self.cleaned_data.get('injury_date')
        if injury_date and injury_date > timezone.localdate():
            raise forms.ValidationError("Injury date cannot be in the future.")
        return injury_date

    def clean_description(self):
        description = (self.cleaned_data.get('description') or '').strip()
        if len(description) < 10:
            raise forms.ValidationError(
                "Please add a bit more detail (at least 10 characters) so your therapist understands the situation."
            )
        return description
