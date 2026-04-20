from decimal import Decimal, InvalidOperation

from django import forms
from django.contrib.auth.password_validation import validate_password
from django.db.models import Q
from django.utils import timezone
from typing import cast

from app.models import (
    BudgetGoal,
    Client,
    CompensationHistory,
    Department,
    EmployeeProfile,
    FinancialEntry,
    JobHistory,
    Membership,
    Project,
    Task,
    TimeEntry,
    TimeEntryTemplate,
    User,
    UserClient,
    UserDepartment,
    UserProject,
    WorkSchedule,
    Workspace,
)
from app.time_entry_prepared import get_member_template_flags


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
            workspace_field = cast(forms.ModelChoiceField, self.fields["workspace"])
            workspace_field.queryset = Workspace.objects.filter(owner=owner).order_by(
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
            "has_fixed_days": "Folga Fixa",
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
        fields = (
            "name",
            "schedule",
            "template",
            "time_tracking_mode",
            "can_edit_time_entries",
            "can_delete_time_entries",
        )
        labels = {
            "name": "Nome do departamento",
            "schedule": "Expediente",
            "template": "Template de apontamento",
            "time_tracking_mode": "Modo de apontamento",
            "can_edit_time_entries": "Permitir editar apontamentos",
            "can_delete_time_entries": "Permitir excluir apontamentos",
        }
        widgets = {
            "name": forms.TextInput(attrs=_auth_input_attrs),
            "schedule": forms.Select(attrs=_auth_input_attrs),
            "template": forms.Select(attrs=_auth_input_attrs),
            "time_tracking_mode": forms.Select(attrs=_auth_input_attrs),
            "can_edit_time_entries": forms.CheckboxInput(attrs=_auth_input_attrs),
            "can_delete_time_entries": forms.CheckboxInput(attrs=_auth_input_attrs),
        }

    def __init__(self, *args, workspace: Workspace | None = None, **kwargs):
        self._workspace = workspace
        super().__init__(*args, **kwargs)
        if workspace is not None:
            schedule_field = cast(forms.ModelChoiceField, self.fields["schedule"])
            schedule_field.queryset = WorkSchedule.objects.filter(
                workspace=workspace
            ).order_by("name")
            template_field = cast(forms.ModelChoiceField, self.fields["template"])
            template_field.queryset = TimeEntryTemplate.objects.filter(
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


_config_field_attrs = {"class": "config-widget-input"}


class ClientCreateForm(forms.ModelForm):
    class Meta:
        model = Client
        fields = ("name", "document", "email", "phone", "budget", "is_active")
        labels = {
            "name": "Nome",
            "document": "Documento (CNPJ/CPF)",
            "email": "Email",
            "phone": "Telefone",
            "budget": "Budget",
            "is_active": "Ativo",
        }
        widgets = {
            "name": forms.TextInput(attrs=_config_field_attrs),
            "document": forms.TextInput(attrs=_config_field_attrs),
            "email": forms.EmailInput(attrs=_config_field_attrs),
            "phone": forms.TextInput(attrs=_config_field_attrs),
            "budget": forms.NumberInput(attrs={**_config_field_attrs, "step": "0.01", "min": "0"}),
        }

    def save(
        self,
        commit=True,
        *,
        workspace: Workspace | None = None,
        created_by: User | None = None,
        updated_by: User | None = None,
    ):
        obj = super().save(commit=False)
        if workspace is not None:
            obj.workspace = workspace
        if created_by is not None:
            obj.created_by = obj.created_by or created_by
        if updated_by is not None:
            obj.updated_by = updated_by
        if commit:
            obj.save()
        return obj


class ProjectCreateForm(forms.ModelForm):
    class Meta:
        model = Project
        fields = (
            "client",
            "name",
            "description",
            "budget",
            "deadline",
            "estimated_hours",
            "is_active",
        )
        labels = {
            "client": "Cliente",
            "name": "Nome do projeto",
            "description": "Descrição",
            "budget": "Budget",
            "deadline": "Deadline",
            "estimated_hours": "Horas estimadas",
            "is_active": "Ativo",
        }
        widgets = {
            "client": forms.Select(attrs=_config_field_attrs),
            "name": forms.TextInput(attrs=_config_field_attrs),
            "description": forms.Textarea(attrs={**_config_field_attrs, "rows": 2}),
            "budget": forms.NumberInput(attrs={**_config_field_attrs, "step": "0.01", "min": "0"}),
            "deadline": forms.DateInput(attrs={**_config_field_attrs, "type": "date"}),
            "estimated_hours": forms.NumberInput(
                attrs={**_config_field_attrs, "step": "0.01", "min": "0"}
            ),
        }

    def __init__(self, *args, workspace: Workspace | None = None, **kwargs):
        self._workspace = workspace
        super().__init__(*args, **kwargs)
        if workspace is not None:
            client_field = cast(forms.ModelChoiceField, self.fields["client"])
            client_field.queryset = Client.objects.filter(
                workspace=workspace, is_active=True
            ).order_by("name")

    def save(
        self,
        commit=True,
        *,
        workspace: Workspace | None = None,
        created_by: User | None = None,
        updated_by: User | None = None,
    ):
        obj = super().save(commit=False)
        if workspace is not None:
            obj.workspace = workspace
        if created_by is not None:
            obj.created_by = obj.created_by or created_by
        if updated_by is not None:
            obj.updated_by = updated_by
        if commit:
            obj.save()
        return obj


class TaskCreateForm(forms.ModelForm):
    class Meta:
        model = Task
        fields = ("project", "name", "is_active")
        labels = {
            "project": "Projeto",
            "name": "Nome da tarefa",
            "is_active": "Ativa",
        }
        widgets = {
            "project": forms.Select(attrs=_config_field_attrs),
            "name": forms.TextInput(attrs=_config_field_attrs),
        }

    def __init__(self, *args, workspace: Workspace | None = None, **kwargs):
        super().__init__(*args, **kwargs)
        if workspace is not None:
            project_field = cast(forms.ModelChoiceField, self.fields["project"])
            project_field.queryset = Project.objects.filter(
                workspace=workspace, is_active=True
            ).select_related("client").order_by("client__name", "name")


class UserDepartmentAssignForm(forms.ModelForm):
    class Meta:
        model = UserDepartment
        fields = ("department", "is_primary", "start_date", "end_date")
        labels = {
            "department": "Departamento",
            "is_primary": "Principal",
            "start_date": "Início",
            "end_date": "Fim",
        }
        widgets = {
            "department": forms.Select(attrs=_auth_input_attrs),
            "start_date": forms.DateInput(attrs={**_auth_input_attrs, "type": "date"}),
            "end_date": forms.DateInput(attrs={**_auth_input_attrs, "type": "date"}),
        }

    def __init__(self, *args, workspace: Workspace | None = None, **kwargs):
        self._workspace = workspace
        super().__init__(*args, **kwargs)
        if workspace is not None:
            department_field = cast(forms.ModelChoiceField, self.fields["department"])
            department_field.queryset = Department.objects.filter(workspace=workspace).order_by(
                "name"
            )


class UserBirthDateForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ("birth_date",)
        labels = {"birth_date": "Data de nascimento"}
        widgets = {
            "birth_date": forms.DateInput(attrs={**_config_field_attrs, "type": "date"}),
        }


class WorkspaceUserDatesForm(forms.Form):
    user = forms.ModelChoiceField(
        label="Colaborador",
        queryset=User.objects.none(),
        widget=forms.Select(attrs=_config_field_attrs),
    )
    birth_date = forms.DateField(
        label="Data de nascimento",
        required=False,
        widget=forms.DateInput(attrs={**_config_field_attrs, "type": "date"}),
    )
    platform_join_date = forms.DateField(
        label="Entrada na plataforma",
        widget=forms.DateInput(attrs={**_config_field_attrs, "type": "date"}),
    )

    def __init__(self, *args, workspace: Workspace | None = None, **kwargs):
        super().__init__(*args, **kwargs)
        if workspace is not None:
            user_field = cast(forms.ModelChoiceField, self.fields["user"])
            user_field.queryset = User.objects.filter(
                Q(memberships__workspace=workspace) | Q(pk=workspace.owner_id)
            ).order_by("email").distinct()


class EmployeeProfileForm(forms.ModelForm):
    user = forms.ModelChoiceField(
        label="Colaborador",
        queryset=User.objects.none(),
        widget=forms.Select(attrs=_config_field_attrs),
    )

    class Meta:
        model = EmployeeProfile
        fields = (
            "user",
            "employment_status",
            "hire_date",
            "termination_date",
            "current_job_title",
        )
        labels = {
            "employment_status": "Status do vínculo",
            "hire_date": "Admissão",
            "termination_date": "Desligamento",
            "current_job_title": "Cargo atual",
        }
        widgets = {
            "employment_status": forms.Select(attrs=_config_field_attrs),
            "hire_date": forms.DateInput(attrs={**_config_field_attrs, "type": "date"}),
            "termination_date": forms.DateInput(attrs={**_config_field_attrs, "type": "date"}),
            "current_job_title": forms.TextInput(attrs=_config_field_attrs),
        }

    def __init__(self, *args, workspace: Workspace | None = None, **kwargs):
        self._workspace = workspace
        super().__init__(*args, **kwargs)
        user_field = cast(forms.ModelChoiceField, self.fields["user"])
        if workspace is not None:
            user_field.queryset = User.objects.filter(
                Q(memberships__workspace=workspace) | Q(pk=workspace.owner_id)
            ).order_by("email").distinct()

    def save(self, commit=True):
        obj = super().save(commit=False)
        if self._workspace is not None:
            obj.workspace = self._workspace
        if commit:
            obj.save()
        return obj


class JobHistoryForm(forms.ModelForm):
    employee_profile = forms.ModelChoiceField(
        label="Vínculo do colaborador",
        queryset=EmployeeProfile.objects.none(),
        widget=forms.Select(attrs=_config_field_attrs),
    )

    class Meta:
        model = JobHistory
        fields = ("employee_profile", "job_title", "start_date", "end_date")
        labels = {
            "job_title": "Cargo",
            "start_date": "Início",
            "end_date": "Fim",
        }
        widgets = {
            "job_title": forms.TextInput(attrs=_config_field_attrs),
            "start_date": forms.DateInput(attrs={**_config_field_attrs, "type": "date"}),
            "end_date": forms.DateInput(attrs={**_config_field_attrs, "type": "date"}),
        }

    def __init__(self, *args, workspace: Workspace | None = None, **kwargs):
        super().__init__(*args, **kwargs)
        profile_field = cast(forms.ModelChoiceField, self.fields["employee_profile"])
        if workspace is not None:
            profile_field.queryset = EmployeeProfile.objects.filter(
                workspace=workspace
            ).select_related("user").order_by("user__email")


class CompensationHistoryForm(forms.ModelForm):
    employee_profile = forms.ModelChoiceField(
        label="Vínculo do colaborador",
        queryset=EmployeeProfile.objects.none(),
        widget=forms.Select(attrs=_config_field_attrs),
    )

    class Meta:
        model = CompensationHistory
        fields = (
            "employee_profile",
            "compensation_type",
            "monthly_salary",
            "hourly_rate",
            "start_date",
            "end_date",
        )
        labels = {
            "compensation_type": "Tipo de remuneração",
            "monthly_salary": "Salário mensal",
            "hourly_rate": "Valor por hora",
            "start_date": "Início",
            "end_date": "Fim",
        }
        widgets = {
            "compensation_type": forms.Select(attrs=_config_field_attrs),
            "monthly_salary": forms.NumberInput(attrs={**_config_field_attrs, "step": "0.01", "min": "0"}),
            "hourly_rate": forms.NumberInput(attrs={**_config_field_attrs, "step": "0.01", "min": "0"}),
            "start_date": forms.DateInput(attrs={**_config_field_attrs, "type": "date"}),
            "end_date": forms.DateInput(attrs={**_config_field_attrs, "type": "date"}),
        }

    def __init__(self, *args, workspace: Workspace | None = None, **kwargs):
        super().__init__(*args, **kwargs)
        profile_field = cast(forms.ModelChoiceField, self.fields["employee_profile"])
        if workspace is not None:
            profile_field.queryset = EmployeeProfile.objects.filter(
                workspace=workspace
            ).select_related("user").order_by("user__email")


class FinancialEntryManualForm(forms.ModelForm):
    class Meta:
        model = FinancialEntry
        fields = ("flow_type", "occurred_on", "amount", "description", "client", "project", "user")
        labels = {
            "flow_type": "Fluxo",
            "occurred_on": "Data",
            "amount": "Valor",
            "description": "Descrição",
            "client": "Cliente",
            "project": "Projeto",
            "user": "Colaborador",
        }
        widgets = {
            "flow_type": forms.Select(attrs=_config_field_attrs),
            "occurred_on": forms.DateInput(attrs={**_config_field_attrs, "type": "date"}),
            "amount": forms.NumberInput(attrs={**_config_field_attrs, "step": "0.01", "min": "0.01"}),
            "description": forms.Textarea(attrs={**_config_field_attrs, "rows": 2}),
            "client": forms.Select(attrs=_config_field_attrs),
            "project": forms.Select(attrs=_config_field_attrs),
            "user": forms.Select(attrs=_config_field_attrs),
        }

    def __init__(self, *args, workspace: Workspace | None = None, **kwargs):
        self._workspace = workspace
        super().__init__(*args, **kwargs)
        if not self.is_bound:
            self.initial.setdefault("occurred_on", timezone.localdate())
        if workspace is not None:
            client_field = cast(forms.ModelChoiceField, self.fields["client"])
            client_field.queryset = Client.objects.filter(workspace=workspace).order_by("name")
            project_field = cast(forms.ModelChoiceField, self.fields["project"])
            project_field.queryset = Project.objects.filter(workspace=workspace).select_related(
                "client"
            ).order_by("client__name", "name")
            user_field = cast(forms.ModelChoiceField, self.fields["user"])
            user_field.queryset = User.objects.filter(
                Q(memberships__workspace=workspace) | Q(pk=workspace.owner_id)
            ).order_by("email").distinct()

    def save(
        self,
        commit=True,
        *,
        workspace: Workspace | None = None,
        created_by: User | None = None,
        updated_by: User | None = None,
    ):
        obj = super().save(commit=False)
        obj.entry_kind = FinancialEntry.EntryKind.MANUAL
        obj.workspace = workspace or self._workspace  # type: ignore[assignment]
        if created_by is not None:
            obj.created_by = obj.created_by or created_by
        if updated_by is not None:
            obj.updated_by = updated_by
        if commit:
            obj.save()
        return obj


class BudgetGoalForm(forms.ModelForm):
    class Meta:
        model = BudgetGoal
        fields = (
            "client",
            "project",
            "minimum_target_amount",
            "minimum_target_date",
            "desired_target_amount",
            "desired_target_date",
            "description",
        )
        labels = {
            "client": "Cliente",
            "project": "Projeto",
            "minimum_target_amount": "Meta mínima",
            "minimum_target_date": "Data da meta mínima",
            "desired_target_amount": "Meta desejada",
            "desired_target_date": "Data da meta desejada",
            "description": "Descrição",
        }
        widgets = {
            "client": forms.Select(attrs=_config_field_attrs),
            "project": forms.Select(attrs=_config_field_attrs),
            "minimum_target_amount": forms.NumberInput(
                attrs={**_config_field_attrs, "step": "0.01", "min": "0.01"}
            ),
            "minimum_target_date": forms.DateInput(attrs={**_config_field_attrs, "type": "date"}),
            "desired_target_amount": forms.NumberInput(
                attrs={**_config_field_attrs, "step": "0.01", "min": "0.01"}
            ),
            "desired_target_date": forms.DateInput(attrs={**_config_field_attrs, "type": "date"}),
            "description": forms.Textarea(attrs={**_config_field_attrs, "rows": 2}),
        }

    def __init__(self, *args, workspace: Workspace | None = None, **kwargs):
        self._workspace = workspace
        super().__init__(*args, **kwargs)
        if workspace is not None:
            client_field = cast(forms.ModelChoiceField, self.fields["client"])
            client_field.queryset = Client.objects.filter(workspace=workspace).order_by("name")
            project_field = cast(forms.ModelChoiceField, self.fields["project"])
            project_field.queryset = Project.objects.filter(workspace=workspace).select_related(
                "client"
            ).order_by("client__name", "name")

    def save(
        self,
        commit=True,
        *,
        workspace: Workspace | None = None,
        created_by: User | None = None,
        updated_by: User | None = None,
    ):
        obj = super().save(commit=False)
        obj.workspace = workspace or self._workspace  # type: ignore[assignment]
        if created_by is not None:
            obj.created_by = obj.created_by or created_by
        if updated_by is not None:
            obj.updated_by = updated_by
        if commit:
            obj.save()
        return obj


class ManualTimeEntryForm(forms.ModelForm):
    """
    Criação/edição de apontamento manual: apenas ``duration`` ou ``time_range`` (não cronômetro).
    Respeita template do departamento (campos opcionais removidos quando o template não usa).
    """

    class Meta:
        model = TimeEntry
        fields = (
            "entry_mode",
            "date",
            "hours",
            "start_time",
            "end_time",
            "client",
            "project",
            "task",
            "entry_type",
            "description",
            "is_overtime",
        )
        labels = {
            "entry_mode": "Modo",
            "date": "Data",
            "hours": "Horas",
            "start_time": "Início",
            "end_time": "Fim",
            "client": "Cliente",
            "project": "Projeto",
            "task": "Tarefa",
            "entry_type": "Tipo",
            "description": "Descrição",
            "is_overtime": "Hora extra",
        }
        widgets = {
            "date": forms.DateInput(attrs={"type": "date"}),
            "description": forms.Textarea(attrs={"rows": 3}),
            "is_overtime": forms.CheckboxInput(attrs={"class": "q1-checkbox"}),
        }

    def __init__(self, *args, user: User, workspace: Workspace, **kwargs):
        self._user = user
        self._workspace = workspace
        self._flags = get_member_template_flags(user, workspace)
        super().__init__(*args, **kwargs)

        mode_field = cast(forms.ChoiceField, self.fields["entry_mode"])
        mode_field.choices = [
            (TimeEntry.EntryMode.DURATION, "Duração"),
            (TimeEntry.EntryMode.TIME_RANGE, "Intervalo"),
        ]

        client_ids = UserClient.objects.filter(user=user, workspace=workspace).values_list(
            "client_id", flat=True
        )
        project_ids = UserProject.objects.filter(user=user, workspace=workspace).values_list(
            "project_id", flat=True
        )
        cast(forms.ModelChoiceField, self.fields["client"]).queryset = Client.objects.filter(
            pk__in=client_ids, workspace=workspace, is_active=True
        ).order_by("name")
        cast(forms.ModelChoiceField, self.fields["project"]).queryset = Project.objects.filter(
            pk__in=project_ids, workspace=workspace, is_active=True
        ).select_related("client").order_by("client__name", "name")
        cast(forms.ModelChoiceField, self.fields["task"]).queryset = Task.objects.filter(
            project_id__in=project_ids, is_active=True
        ).select_related("project").order_by("project__name", "name")

        self.fields["hours"].required = False
        self.fields["start_time"].required = False
        self.fields["end_time"].required = False
        self.fields["is_overtime"].required = False
        self.fields["start_time"].input_formats = ["%H:%M", "%H:%M:%S"]
        self.fields["end_time"].input_formats = ["%H:%M", "%H:%M:%S"]

        if not self._flags["use_client"]:
            del self.fields["client"]
        if not self._flags["use_project"]:
            del self.fields["project"]
        if not self._flags["use_task"]:
            del self.fields["task"]
        if not self._flags["use_type"]:
            del self.fields["entry_type"]
        if not self._flags["use_description"]:
            del self.fields["description"]

    def clean(self):
        cleaned = super().clean()
        if cleaned is None:
            return cleaned

        if not self._flags.get("configured"):
            raise forms.ValidationError("Template de apontamento não configurado para o seu departamento.")

        mode = cleaned.get("entry_mode")
        if mode == TimeEntry.EntryMode.TIMER:
            raise forms.ValidationError("Use o fluxo de cronômetro para modo timer.")

        if self._flags["use_client"] and not cleaned.get("client"):
            self.add_error("client", "Selecione um cliente.")
        if self._flags["use_project"] and not cleaned.get("project"):
            self.add_error("project", "Selecione um projeto.")
        if self._flags["use_task"] and not cleaned.get("task"):
            self.add_error("task", "Selecione uma tarefa.")
        if self._flags["use_type"]:
            et = cleaned.get("entry_type") or ""
            if et not in (TimeEntry.EntryType.INTERNAL, TimeEntry.EntryType.EXTERNAL):
                self.add_error("entry_type", "Selecione o tipo de apontamento.")

        if mode == TimeEntry.EntryMode.DURATION:
            hours = cleaned.get("hours")
            try:
                hdec = Decimal(str(hours)) if hours is not None else None
            except (InvalidOperation, TypeError, ValueError):
                hdec = None
            if hdec is None or hdec <= 0:
                self.add_error("hours", "Informe horas maiores que zero.")
            cleaned["start_time"] = None
            cleaned["end_time"] = None
        elif mode == TimeEntry.EntryMode.TIME_RANGE:
            st = cleaned.get("start_time")
            et = cleaned.get("end_time")
            if not st or not et:
                self.add_error("start_time", "Informe horário de início e fim.")
            cleaned["hours"] = None

        return cleaned


def manual_time_entry_form_first_error(form: forms.BaseForm) -> str:
    if not form.errors:
        return "Dados inválidos."
    for _field, errs in form.errors.items():
        if errs:
            return str(errs[0])
    return "Dados inválidos."
