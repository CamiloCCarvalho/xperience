from django import forms
from django.contrib.auth.password_validation import validate_password

from app.models import (
    Department,
    Membership,
    TimeEntryTemplate,
    User,
    UserDepartment,
    WorkSchedule,
    Workspace,
)


_auth_input_attrs = {"class": "auth-input"}
_auth_email_attrs = {**_auth_input_attrs, "autocomplete": "email"}
_auth_password_attrs = {**_auth_input_attrs, "autocomplete": "new-password"}


class AdminRegisterForm(forms.Form):
    username = forms.CharField(
        label="Usuário",
        max_length=150,
        widget=forms.TextInput(attrs={**_auth_input_attrs, "autocomplete": "username"}),
    )
    email = forms.EmailField(
        label="Email",
        widget=forms.EmailInput(attrs=_auth_email_attrs),
    )
    password = forms.CharField(
        label="Senha",
        widget=forms.PasswordInput(attrs=_auth_password_attrs, render_value=False),
    )
    password_confirm = forms.CharField(
        label="Confirmar senha",
        widget=forms.PasswordInput(attrs=_auth_password_attrs, render_value=False),
    )

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("Já existe uma conta com este email.")
        return email

    def clean(self):
        data = super().clean()
        if not data:
            return data
        p1 = data.get("password")
        p2 = data.get("password_confirm")
        if p1 and p2 and p1 != p2:
            self.add_error("password_confirm", "As senhas não coincidem.")
        if p1:
            validate_password(p1)
        return data

    def save(self) -> User:
        return User.objects.create_user(
            email=self.cleaned_data["email"],
            password=self.cleaned_data["password"],
            first_name=self.cleaned_data["username"],
            platform_role=User.PlatformRole.ADMIN,
        )


class LoginForm(forms.Form):
    email = forms.EmailField(
        label="Email",
        widget=forms.EmailInput(attrs=_auth_email_attrs),
    )
    password = forms.CharField(
        label="Senha",
        widget=forms.PasswordInput(
            attrs={**_auth_password_attrs, "autocomplete": "current-password"},
            render_value=False,
        ),
    )


class WorkspaceCreateForm(forms.ModelForm):
    class Meta:
        model = Workspace
        fields = ("workspace_name", "workspace_description")
        labels = {
            "workspace_name": "Nome do workspace",
            "workspace_description": "Descrição",
        }


class MemberAddForm(forms.Form):
    workspace = forms.ModelChoiceField(
        label="Workspace",
        queryset=Workspace.objects.none(),
    )
    first_name = forms.CharField(label="Nome", max_length=150)
    email = forms.EmailField(label="Email")
    password = forms.CharField(label="Senha inicial", widget=forms.PasswordInput)
    password_confirm = forms.CharField(label="Confirmar senha", widget=forms.PasswordInput)

    def __init__(self, *args, owner: User | None = None, **kwargs):
        super().__init__(*args, **kwargs)
        if owner is not None:
            self.fields["workspace"].queryset = Workspace.objects.filter(owner=owner).order_by(
                "workspace_name"
            )

    def clean_email(self):
        return self.cleaned_data["email"].strip().lower()

    def clean(self):
        data = super().clean()
        if not data:
            return data
        email = data.get("email")
        workspace = data.get("workspace")
        existing = User.objects.filter(email__iexact=email).first() if email else None

        if email and workspace:
            if existing and existing.platform_role == User.PlatformRole.ADMIN:
                self.add_error(
                    "email",
                    "Este email pertence a um administrador da plataforma.",
                )
            elif (
                existing
                and Membership.objects.filter(user=existing, workspace=workspace).exists()
            ):
                self.add_error("email", "Este usuário já está neste workspace.")

        p1 = data.get("password")
        p2 = data.get("password_confirm")
        if not existing:
            if p1 and p2 and p1 != p2:
                self.add_error("password_confirm", "As senhas não coincidem.")
            if p1:
                validate_password(p1)
        return data

    def save(self) -> Membership:
        email = self.cleaned_data["email"]
        workspace = self.cleaned_data["workspace"]
        existing = User.objects.filter(email__iexact=email).first()
        if existing:
            existing.first_name = self.cleaned_data["first_name"]
            existing.save(update_fields=["first_name"])
            user = existing
        else:
            user = User.objects.create_user(
                email=email,
                password=self.cleaned_data["password"],
                first_name=self.cleaned_data["first_name"],
                platform_role=User.PlatformRole.MEMBER,
            )
        return Membership.objects.create(user=user, workspace=workspace, role="user")


WORKDAY_CHOICES = [
    ("mon", "Seg"),
    ("tue", "Ter"),
    ("wed", "Qua"),
    ("thu", "Qui"),
    ("fri", "Sex"),
    ("sat", "Sáb"),
    ("sun", "Dom"),
]


class TimeEntryTemplateForm(forms.ModelForm):
    class Meta:
        model = TimeEntryTemplate
        fields = (
            "name",
            "use_client",
            "use_project",
            "use_task",
            "use_type",
            "use_description",
        )
        labels = {
            "name": "Nome",
            "use_client": "Cliente",
            "use_project": "Projeto",
            "use_task": "Tarefa",
            "use_type": "Tipo (interno/externo)",
            "use_description": "Descrição",
        }
        widgets = {
            "name": forms.TextInput(attrs=_auth_input_attrs),
        }

    def __init__(self, *args, workspace: Workspace | None = None, **kwargs):
        self._workspace = workspace
        super().__init__(*args, **kwargs)

    def clean_name(self):
        name = self.cleaned_data["name"].strip()
        if not name:
            raise forms.ValidationError("Informe um nome.")
        if self._workspace is None:
            return name
        qs = TimeEntryTemplate.objects.filter(workspace=self._workspace, name__iexact=name)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError("Já existe um template com este nome neste workspace.")
        return name

    def save(self, commit=True):
        obj = super().save(commit=False)
        if self._workspace is not None:
            obj.workspace = self._workspace
        if commit:
            obj.save()
        return obj


class WorkScheduleForm(forms.ModelForm):
    working_days_pick = forms.MultipleChoiceField(
        label="Dias com expediente",
        choices=WORKDAY_CHOICES,
        required=False,
        widget=forms.CheckboxSelectMultiple,
    )

    class Meta:
        model = WorkSchedule
        fields = ("name", "expected_hours_per_day", "has_fixed_days")
        labels = {
            "name": "Nome do expediente",
            "expected_hours_per_day": "Horas previstas por dia",
            "has_fixed_days": "Usa dias fixos da semana",
        }
        widgets = {
            "name": forms.TextInput(attrs=_auth_input_attrs),
            "expected_hours_per_day": forms.NumberInput(attrs=_auth_input_attrs),
        }

    def __init__(self, *args, workspace: Workspace | None = None, **kwargs):
        self._workspace = workspace
        super().__init__(*args, **kwargs)
        if self.instance.pk and self.instance.working_days:
            self.initial.setdefault("working_days_pick", self.instance.working_days)
        elif not self.is_bound:
            self.initial.setdefault(
                "working_days_pick",
                ["mon", "tue", "wed", "thu", "fri"],
            )

    def clean(self):
        data = super().clean()
        if data is not None:
            data["working_days_list"] = list(data.get("working_days_pick") or [])
        return data

    def save(self, commit=True):
        obj = super().save(commit=False)
        obj.working_days = self.cleaned_data.get("working_days_list") or []
        if self._workspace is not None:
            obj.workspace = self._workspace
        if commit:
            obj.save()
        return obj


class DepartmentForm(forms.ModelForm):
    class Meta:
        model = Department
        fields = ("name", "schedule", "template")
        labels = {
            "name": "Nome do departamento",
            "schedule": "Expediente",
            "template": "Template de apontamento",
        }
        widgets = {
            "name": forms.TextInput(attrs=_auth_input_attrs),
            "schedule": forms.Select(attrs=_auth_input_attrs),
            "template": forms.Select(attrs=_auth_input_attrs),
        }

    def __init__(self, *args, workspace: Workspace | None = None, **kwargs):
        self._workspace = workspace
        super().__init__(*args, **kwargs)
        if workspace is not None:
            self.fields["schedule"].queryset = WorkSchedule.objects.filter(
                workspace=workspace
            ).order_by("name")
            self.fields["template"].queryset = TimeEntryTemplate.objects.filter(
                workspace=workspace
            ).order_by("name")

    def clean_name(self):
        name = self.cleaned_data["name"].strip()
        if not name:
            raise forms.ValidationError("Informe um nome.")
        if self._workspace is None:
            return name
        qs = Department.objects.filter(workspace=self._workspace, name__iexact=name)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError("Já existe um departamento com este nome neste workspace.")
        return name

    def save(self, commit=True):
        obj = super().save(commit=False)
        if self._workspace is not None:
            obj.workspace = self._workspace
        if commit:
            obj.save()
        return obj
