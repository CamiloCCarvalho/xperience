from decimal import Decimal, ROUND_HALF_UP

from django.db import models, transaction
from django.db.models import Q
from django.contrib.auth.models import AbstractUser
from typing import ClassVar
from django.contrib.auth.models import BaseUserManager
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.validators import MinValueValidator, MaxValueValidator
from django.utils import timezone


def _check_constraint(*, predicate, name: str) -> models.CheckConstraint:
    """
    Compatibilidade entre versões de Django:
    - antigas: CheckConstraint(check=...)
    - novas:   CheckConstraint(condition=...)
    """
    try:
        return models.CheckConstraint(condition=predicate, name=name)
    except TypeError:
        return models.CheckConstraint(check=predicate, name=name)  # type: ignore[call-arg]


class CustomUserManager(BaseUserManager):
    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError("Email is required")

        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("is_active", True)

        return self.create_user(email, password, **extra_fields)


class User(AbstractUser):
    PATH_TO_USER_IMAGE = "app/images/users/%Y/%m/%d/"

    class PlatformRole(models.TextChoices):
        ADMIN = "admin", "Administrador da plataforma"
        MEMBER = "member", "Membro"

    username = None  # type: ignore
    email = models.EmailField(unique=True)

    platform_role = models.CharField(
        max_length=20,
        choices=PlatformRole.choices,
        default=PlatformRole.MEMBER,
    )

    is_verified = models.BooleanField(default=False)
    is_deleted = models.BooleanField(default=False)
    is_locked = models.BooleanField(default=False)
    is_expired = models.BooleanField(default=False)
    is_inactive = models.BooleanField(default=False)

    avatar = models.ImageField(upload_to=PATH_TO_USER_IMAGE, blank=True, null=True)
    birth_date = models.DateField(
        null=True,
        blank=True,
        help_text="Data de nascimento global da pessoa (não depende de workspace).",
    )
    birthday_public_in_workspace = models.BooleanField(
        default=False,
        help_text=(
            "Se verdadeiro, colegas do mesmo workspace veem dia e mês do aniversário no calendário "
            "(sem exibir o ano)."
        ),
    )
    platform_join_date = models.DateField(
        default=timezone.localdate,
        help_text="Data de entrada na plataforma (diferente de created_at técnico).",
    )

    # Payment/card fields (stored minimally). Card numbers are NOT stored in plain text.
    card_hash = models.CharField(max_length=128, blank=True)
    card_last4 = models.CharField(max_length=4, blank=True)
    card_brand = models.CharField(max_length=50, blank=True)
    card_holder_name = models.CharField(max_length=255, blank=True)
    card_expiry_month = models.PositiveSmallIntegerField(null=True, blank=True)
    card_expiry_year = models.PositiveSmallIntegerField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects: ClassVar[CustomUserManager] = CustomUserManager() # type: ignore

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    class Meta:
        verbose_name = "User"
        verbose_name_plural = "Users"
        ordering = ["-created_at"]

    def __str__(self):
        return self.first_name + " - " + self.email

    @property
    def age(self):
        """Idade calculada em tempo real a partir de birth_date (não persistida)."""
        if not self.birth_date:
            return None
        today = timezone.localdate()
        years = today.year - self.birth_date.year
        if (today.month, today.day) < (self.birth_date.month, self.birth_date.day):
            years -= 1
        return years


class Workspace(models.Model):
    """
    Workspace model
    """

    PATH_TO_WORKSPACE_IMAGE = "app/images/workspaces/%Y/%m/%d/"

    owner = models.ForeignKey('User', on_delete=models.CASCADE)
    workspace_name = models.CharField(max_length=255)
    workspace_description = models.TextField(blank=True)
    mural_members_lane_locked = models.BooleanField(default=False)
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_workspaces",
    )
    updated_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="updated_workspaces",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    workspace_avatar = models.ImageField(
        upload_to=PATH_TO_WORKSPACE_IMAGE, 
        blank=True, 
        null=True
    )

    class Meta:
        verbose_name = "Workspace"
        verbose_name_plural = "Workspaces"
        ordering = ["-created_at"]

    def __str__(self):
        return self.workspace_name + " - " + self.owner.first_name + " " + self.owner.last_name


class Membership(models.Model):
    """
    Vínculo usuário ↔ workspace. Um mesmo usuário pode ter vários memberships
    (vários workspaces do mesmo gestor ou de gestores diferentes).
    """

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="memberships")
    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name="memberships")

    role = models.CharField(
        max_length=20,
        choices=[
            ("admin", "Admin"),
            ("manager", "Manager"),
            ("user", "User"),
        ],
        default="user"
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("user", "workspace")


class EmployeeProfile(models.Model):
    """Vínculo empregatício atual de um usuário em um workspace."""

    class EmploymentStatus(models.TextChoices):
        ACTIVE = "active", "Ativo"
        ON_LEAVE = "on_leave", "Afastado"
        TERMINATED = "terminated", "Desligado"

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="employee_profiles",
    )
    workspace = models.ForeignKey(
        Workspace,
        on_delete=models.CASCADE,
        related_name="employee_profiles",
    )
    employment_status = models.CharField(
        max_length=20,
        choices=EmploymentStatus.choices,
        default=EmploymentStatus.ACTIVE,
    )
    hire_date = models.DateField()
    termination_date = models.DateField(null=True, blank=True)
    current_job_role = models.ForeignKey(
        "JobRole",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="employee_profiles_current",
        help_text="Cargo atual para leitura rápida (sincronizado com histórico vigente).",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("user", "workspace"),
                name="app_employeeprofile_user_workspace_uniq",
            ),
            _check_constraint(
                predicate=Q(termination_date__isnull=True) | Q(termination_date__gte=models.F("hire_date")),
                name="app_employeeprofile_termination_after_hire",
            ),
        ]
        verbose_name = "Vínculo do colaborador"
        verbose_name_plural = "Vínculos dos colaboradores"

    def clean(self) -> None:
        super().clean()
        errors: dict[str, str] = {}
        if self.termination_date and self.termination_date < self.hire_date:
            errors["termination_date"] = "A data de desligamento não pode ser menor que a data de admissão."
        if self.employment_status == self.EmploymentStatus.TERMINATED and not self.termination_date:
            errors["termination_date"] = "Informe a data de desligamento para status desligado."
        if self.termination_date and self.employment_status != self.EmploymentStatus.TERMINATED:
            errors["employment_status"] = "Use status desligado quando houver data de desligamento."
        if self.current_job_role_id and self.workspace_id:
            role = self.current_job_role
            if role is not None and role.workspace_id != self.workspace_id:
                errors["current_job_role"] = "O cargo atual deve pertencer ao mesmo workspace do vínculo."
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs) -> None:
        self.full_clean()
        super().save(*args, **kwargs)
        active_history = (
            self.job_history_entries.filter(end_date__isnull=True)
            .order_by("-start_date", "-pk")
            .first()
        )
        if active_history is not None and active_history.job_role_id != self.current_job_role_id:
            self.current_job_role_id = active_history.job_role_id
            type(self).objects.filter(pk=self.pk).update(
                current_job_role_id=active_history.job_role_id,
                updated_at=timezone.now(),
            )

    def __str__(self):
        return f"{self.user.email} @ {self.workspace.workspace_name}"

    def sync_current_job_role_from_history(self, *, save: bool = True) -> None:
        current_job = (
            self.job_history_entries.filter(end_date__isnull=True)
            .order_by("-start_date", "-pk")
            .first()
        )
        self.current_job_role = current_job.job_role if current_job is not None else None
        if save:
            self.save(update_fields=["current_job_role", "updated_at"])


class JobRole(models.Model):
    workspace = models.ForeignKey(
        Workspace,
        on_delete=models.CASCADE,
        related_name="job_roles",
    )
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_job_roles",
    )
    updated_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="updated_job_roles",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name", "pk"]
        constraints = [
            models.UniqueConstraint(
                fields=("workspace", "name"),
                name="app_jobrole_workspace_name_uniq",
            ),
        ]
        verbose_name = "Cargo"
        verbose_name_plural = "Cargos"

    def clean(self) -> None:
        super().clean()
        if self.name:
            self.name = self.name.strip()
        if not self.name:
            raise ValidationError({"name": "Informe o nome do cargo."})

    def save(self, *args, **kwargs) -> None:
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"{self.name} ({self.workspace.workspace_name})"


class JobHistory(models.Model):
    """Histórico de cargos de um vínculo (separado da remuneração)."""

    employee_profile = models.ForeignKey(
        EmployeeProfile,
        on_delete=models.CASCADE,
        related_name="job_history_entries",
    )
    job_role = models.ForeignKey(
        JobRole,
        on_delete=models.PROTECT,
        related_name="history_entries",
    )
    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-start_date", "-pk"]
        constraints = [
            models.UniqueConstraint(
                fields=("employee_profile",),
                condition=Q(end_date__isnull=True),
                name="app_jobhistory_single_current_job_per_profile",
            ),
            _check_constraint(
                predicate=Q(end_date__isnull=True) | Q(end_date__gte=models.F("start_date")),
                name="app_jobhistory_end_after_start",
            ),
        ]
        verbose_name = "Histórico de cargo"
        verbose_name_plural = "Históricos de cargo"

    def clean(self) -> None:
        super().clean()
        errors: dict[str, str] = {}
        if self.end_date and self.end_date < self.start_date:
            errors["end_date"] = "A data final não pode ser anterior à data inicial."
        if self.job_role_id and self.employee_profile_id:
            role = self.job_role
            if role is not None and role.workspace_id != self.employee_profile.workspace_id:
                errors["job_role"] = "O cargo deve pertencer ao mesmo workspace do vínculo."
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs) -> None:
        self.full_clean()
        super().save(*args, **kwargs)
        self.employee_profile.sync_current_job_role_from_history()

    def delete(self, *args, **kwargs):
        employee_profile = self.employee_profile
        out = super().delete(*args, **kwargs)
        employee_profile.sync_current_job_role_from_history()
        return out

    def __str__(self):
        return f"{self.employee_profile.user.email} - {self.job_role.name}"


class CompensationHistory(models.Model):
    """Histórico de remuneração mensal/horista por vínculo."""

    class CompensationType(models.TextChoices):
        MONTHLY = "monthly", "Mensal"
        HOURLY = "hourly", "Por hora"

    employee_profile = models.ForeignKey(
        EmployeeProfile,
        on_delete=models.CASCADE,
        related_name="compensation_history_entries",
    )
    compensation_type = models.CharField(max_length=20, choices=CompensationType.choices)
    monthly_salary = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    hourly_rate = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    monthly_salary_is_fixed = models.BooleanField(
        null=True,
        blank=True,
        verbose_name="Salário mensal fixo",
        help_text="Somente para tipo mensal: se verdadeiro, o valor-hora deriva do salário e das horas previstas no mês.",
    )
    monthly_reference_hours = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0.01"))],
        help_text="Somente para mensal não fixo: base mensal de horas para calcular o valor-hora (ex.: 160).",
    )
    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-start_date", "-pk"]
        constraints = [
            models.UniqueConstraint(
                fields=("employee_profile",),
                condition=Q(end_date__isnull=True),
                name="app_compensationhistory_single_current_compensation_per_profile",
            ),
            _check_constraint(
                predicate=Q(end_date__isnull=True) | Q(end_date__gte=models.F("start_date")),
                name="app_compensationhistory_end_after_start",
            ),
        ]
        verbose_name = "Histórico de remuneração"
        verbose_name_plural = "Históricos de remuneração"

    def clean(self) -> None:
        super().clean()
        errors: dict[str, str] = {}
        if self.end_date and self.end_date < self.start_date:
            errors["end_date"] = "A data final não pode ser anterior à data inicial."
        if self.compensation_type == self.CompensationType.HOURLY:
            if self.hourly_rate is None:
                errors["hourly_rate"] = "Informe o valor por hora para remuneração por hora."
            if self.monthly_salary is not None:
                errors["monthly_salary"] = "Não informe salário mensal para remuneração por hora."
            if self.monthly_salary_is_fixed is not None:
                errors["monthly_salary_is_fixed"] = "Não use este campo para remuneração por hora."
            if self.monthly_reference_hours is not None:
                errors["monthly_reference_hours"] = "Não informe horas base mensais para remuneração por hora."
        elif self.compensation_type == self.CompensationType.MONTHLY:
            if self.monthly_salary is None:
                errors["monthly_salary"] = "Informe o salário mensal para remuneração mensal."
            if self.hourly_rate is not None:
                errors["hourly_rate"] = "Não informe valor por hora para remuneração mensal."
            if self.monthly_salary_is_fixed is True:
                if self.monthly_reference_hours is not None:
                    errors["monthly_reference_hours"] = (
                        "Não informe horas base mensais quando o salário mensal é fixo (usa expediente do mês)."
                    )
            elif self.monthly_salary_is_fixed is False:
                if self.monthly_reference_hours is None or self.monthly_reference_hours <= 0:
                    errors["monthly_reference_hours"] = (
                        "Informe as horas base mensais (maior que zero) para remuneração mensal não fixa."
                    )
            else:
                errors["monthly_salary_is_fixed"] = (
                    "Indique se o salário mensal é fixo (usa expediente) ou não fixo (usa horas base contratuais)."
                )
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs) -> None:
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.employee_profile.user.email} - {self.get_compensation_type_display()}"


class FinancialEntryQuerySet(models.QuerySet):
    def inflows(self):
        return self.filter(flow_type=FinancialEntry.FlowType.INFLOW)

    def outflows(self):
        return self.filter(flow_type=FinancialEntry.FlowType.OUTFLOW)

    def approved_outflows(self):
        return self.outflows().filter(approval_status=FinancialEntry.ApprovalStatus.APPROVED)

    def effective_for_balance(self):
        return self.filter(
            Q(flow_type=FinancialEntry.FlowType.INFLOW)
            | Q(
                flow_type=FinancialEntry.FlowType.OUTFLOW,
                approval_status=FinancialEntry.ApprovalStatus.APPROVED,
            )
        )

    def review_queue(self):
        return self.outflows().filter(
            approval_status__in=[
                FinancialEntry.ApprovalStatus.PENDING,
                FinancialEntry.ApprovalStatus.PROCESSING,
            ]
        )


class FinancialEntry(models.Model):
    class EntryKind(models.TextChoices):
        MANUAL = "manual", "Manual"
        TIME_ENTRY_COST = "time_entry_cost", "Custo de apontamento"
        REVERSAL = "reversal", "Estorno"

    class FlowType(models.TextChoices):
        INFLOW = "inflow", "Entrada"
        OUTFLOW = "outflow", "Saída"

    class ApprovalStatus(models.TextChoices):
        NOT_REQUIRED = "not_required", "Não requer aprovação"
        PENDING = "pending", "Pendente"
        PROCESSING = "processing", "Processando"
        APPROVED = "approved", "Aprovado"
        REJECTED = "rejected", "Reprovado"

    workspace = models.ForeignKey(
        Workspace,
        on_delete=models.CASCADE,
        related_name="financial_entries",
    )
    entry_kind = models.CharField(max_length=24, choices=EntryKind.choices)
    flow_type = models.CharField(max_length=16, choices=FlowType.choices)
    occurred_on = models.DateField(default=timezone.localdate)
    amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    approval_status = models.CharField(
        max_length=20,
        choices=ApprovalStatus.choices,
        default=ApprovalStatus.NOT_REQUIRED,
    )
    approved_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="approved_financial_entries",
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    rejected_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="rejected_financial_entries",
    )
    rejected_at = models.DateTimeField(null=True, blank=True)
    decision_note = models.TextField(blank=True)
    description = models.TextField()
    client = models.ForeignKey(
        "Client",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="financial_entries",
    )
    project = models.ForeignKey(
        "Project",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="financial_entries",
    )
    user = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="financial_entries",
    )
    time_entry = models.ForeignKey(
        "TimeEntry",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="financial_entries",
    )
    source_time_entry_id = models.PositiveBigIntegerField(null=True, blank=True)
    reversal_of = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reversal_entries",
    )
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_financial_entries",
    )
    updated_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="updated_financial_entries",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = FinancialEntryQuerySet.as_manager()

    class Meta:
        ordering = ["-occurred_on", "-pk"]
        constraints = [
            models.UniqueConstraint(
                fields=("time_entry", "entry_kind"),
                condition=Q(time_entry__isnull=False),
                name="app_financialentry_unique_kind_per_time_entry",
            ),
            models.UniqueConstraint(
                fields=("reversal_of",),
                condition=Q(reversal_of__isnull=False),
                name="app_financialentry_single_reversal_per_entry",
            ),
        ]
        indexes = [
            models.Index(fields=["workspace", "occurred_on"]),
            models.Index(fields=["workspace", "flow_type"]),
            models.Index(fields=["workspace", "entry_kind"]),
            models.Index(fields=["workspace", "approval_status"]),
        ]
        verbose_name = "Lançamento financeiro"
        verbose_name_plural = "Lançamentos financeiros"

    def clean(self) -> None:
        super().clean()
        errors: dict[str, str] = {}

        if self.client_id and self.workspace_id and self.client.workspace_id != self.workspace_id:
            errors["client"] = "O cliente deve pertencer ao mesmo workspace do lançamento."

        if self.project_id and self.workspace_id and self.project.workspace_id != self.workspace_id:
            errors["project"] = "O projeto deve pertencer ao mesmo workspace do lançamento."

        if self.client_id and self.project_id and self.project.client_id != self.client_id:
            errors["project"] = "O projeto deve pertencer ao cliente informado."

        if self.entry_kind == self.EntryKind.TIME_ENTRY_COST:
            if self.flow_type != self.FlowType.OUTFLOW:
                errors["flow_type"] = "Custo de apontamento deve ser uma saída."
            if not self.time_entry_id:
                errors["time_entry"] = "Informe o apontamento de origem para custo automático."
            if self.reversal_of_id:
                errors["reversal_of"] = "Custo automático não pode apontar para um estorno."

        if self.entry_kind == self.EntryKind.REVERSAL:
            if not self.reversal_of_id:
                errors["reversal_of"] = "Informe o lançamento original para gerar estorno."
            elif self.reversal_of_id == self.pk:
                errors["reversal_of"] = "Um lançamento não pode estornar a si mesmo."

        if self.entry_kind == self.EntryKind.MANUAL and self.reversal_of_id:
            errors["reversal_of"] = "Lançamento manual não pode apontar para estorno."

        if self.reversal_of_id:
            original = self.reversal_of
            if original is not None and self.flow_type == original.flow_type:
                errors["flow_type"] = "O estorno deve ter fluxo oposto ao lançamento original."

        if self.flow_type == self.FlowType.INFLOW:
            if self.approval_status != self.ApprovalStatus.NOT_REQUIRED:
                errors["approval_status"] = "Entradas não passam por fluxo de aprovação."
        else:
            if self.approval_status == self.ApprovalStatus.NOT_REQUIRED:
                errors["approval_status"] = "Saídas devem usar status de aprovação."

        if self.approval_status == self.ApprovalStatus.APPROVED:
            if not self.approved_at:
                errors["approved_at"] = "Informe a data de aprovação."
            if self.rejected_by_id or self.rejected_at:
                errors["rejected_by"] = "Lançamento aprovado não pode ter dados de reprovação."

        if self.approval_status == self.ApprovalStatus.REJECTED:
            if not self.rejected_at:
                errors["rejected_at"] = "Informe a data de reprovação."
            if self.approved_by_id or self.approved_at:
                errors["approved_by"] = "Lançamento reprovado não pode ter dados de aprovação."

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs) -> None:
        if self.flow_type == self.FlowType.INFLOW:
            self.approval_status = self.ApprovalStatus.NOT_REQUIRED
        elif self.approval_status == self.ApprovalStatus.NOT_REQUIRED:
            self.approval_status = self.ApprovalStatus.PENDING
        if self.time_entry_id and self.source_time_entry_id is None:
            self.source_time_entry_id = self.time_entry_id
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.get_flow_type_display()} {self.amount} em {self.occurred_on}"


class BudgetGoal(models.Model):
    class Visibility(models.TextChoices):
        PRIVATE = "private", "Privada"
        PUBLIC = "public", "Pública"

    workspace = models.ForeignKey(
        Workspace,
        on_delete=models.CASCADE,
        related_name="budget_goals",
    )
    client = models.ForeignKey(
        "Client",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="budget_goals",
    )
    project = models.ForeignKey(
        "Project",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="budget_goals",
    )
    minimum_target_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    minimum_target_date = models.DateField()
    desired_target_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    visibility = models.CharField(
        max_length=10,
        choices=Visibility.choices,
        default=Visibility.PRIVATE,
    )
    desired_target_date = models.DateField()
    description = models.TextField(blank=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_budget_goals",
    )
    updated_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="updated_budget_goals",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at", "-pk"]
        indexes = [
            models.Index(fields=["workspace", "minimum_target_date"]),
            models.Index(fields=["workspace", "desired_target_date"]),
        ]
        verbose_name = "Meta de budget"
        verbose_name_plural = "Metas de budget"

    def clean(self) -> None:
        super().clean()
        errors: dict[str, str] = {}

        if self.client_id and self.workspace_id and self.client.workspace_id != self.workspace_id:
            errors["client"] = "O cliente deve pertencer ao mesmo workspace da meta."

        if self.project_id and self.workspace_id and self.project.workspace_id != self.workspace_id:
            errors["project"] = "O projeto deve pertencer ao mesmo workspace da meta."

        if self.client_id and self.project_id and self.project.client_id != self.client_id:
            errors["project"] = "O projeto deve pertencer ao cliente informado."

        if self.desired_target_amount < self.minimum_target_amount:
            errors["desired_target_amount"] = "A meta desejada não pode ser menor que a meta mínima."

        if self.desired_target_date < self.minimum_target_date:
            errors["desired_target_date"] = (
                "A data da meta desejada não pode ser anterior à data da meta mínima."
            )

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs) -> None:
        self.full_clean()
        super().save(*args, **kwargs)

    @classmethod
    def visible_for_user(cls, *, workspace: Workspace, user: User):
        return cls.objects.filter(workspace=workspace).filter(
            Q(visibility=cls.Visibility.PUBLIC) | Q(created_by=user)
        )

    @classmethod
    def public_for_workspace(cls, *, workspace: Workspace):
        return cls.objects.filter(
            workspace=workspace,
            visibility=cls.Visibility.PUBLIC,
        )

    def __str__(self):
        if self.project_id:
            scope = self.project.name
        elif self.client_id:
            scope = self.client.name
        else:
            scope = self.workspace.workspace_name
        return f"Meta {scope}"


class WorkSchedule(models.Model):
    """Regras de expediente por workspace."""

    workspace = models.ForeignKey(
        Workspace,
        on_delete=models.CASCADE,
        related_name="work_schedules",
    )
    name = models.CharField(max_length=255)
    working_days = models.JSONField(
        default=list,
        help_text='Lista de chaves: "mon","tue","wed","thu","fri","sat","sun"',
    )
    expected_hours_per_day = models.PositiveSmallIntegerField(
        default=8,
        validators=[MinValueValidator(1), MaxValueValidator(24)],
    )
    has_fixed_days = models.BooleanField(
        default=True,
        verbose_name="Folga Fixa",
        help_text="Se ativado, o expediente usa os dias da semana escolhidos de forma fixa.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name", "pk"]
        verbose_name = "Expediente"
        verbose_name_plural = "Expedientes"

    def __str__(self):
        return f"{self.name} ({self.workspace})"


class TimeEntryTemplate(models.Model):
    """
    Define quais blocos de campos aparecem nos apontamentos (flags fixas, sem JSON schema).
    """

    workspace = models.ForeignKey(
        Workspace,
        on_delete=models.CASCADE,
        related_name="time_entry_templates",
    )
    name = models.CharField(max_length=255)
    use_client = models.BooleanField(default=False)
    use_project = models.BooleanField(default=False)
    use_task = models.BooleanField(default=False)
    use_type = models.BooleanField(default=False)
    use_description = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name", "pk"]
        verbose_name = "Template de apontamento"
        verbose_name_plural = "Templates de apontamento"

    def __str__(self):
        return f"{self.name} ({self.workspace})"


class Department(models.Model):
    class TimeTrackingMode(models.TextChoices):
        DURATION = "duration", "Duração"
        TIME_RANGE = "time_range", "Intervalo"
        TIMER = "timer", "Cronômetro"

    workspace = models.ForeignKey(
        Workspace,
        on_delete=models.CASCADE,
        related_name="departments",
    )
    name = models.CharField(max_length=255)
    schedule = models.ForeignKey(
        WorkSchedule,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="departments",
    )
    template = models.ForeignKey(
        TimeEntryTemplate,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="departments",
    )
    time_tracking_mode = models.CharField(
        max_length=20,
        choices=TimeTrackingMode.choices,
        default=TimeTrackingMode.DURATION,
    )
    can_edit_time_entries = models.BooleanField(
        default=True,
        help_text="Se falso, membros não devem editar apontamentos salvos (regra de aplicação na view).",
    )
    can_delete_time_entries = models.BooleanField(
        default=True,
        help_text="Se falso, membros não devem excluir apontamentos (regra de aplicação na view).",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name", "pk"]
        unique_together = ("workspace", "name")
        verbose_name = "Departamento"
        verbose_name_plural = "Departamentos"

    def __str__(self):
        return f"{self.name} ({self.workspace})"


class UserDepartment(models.Model):
    """Permite histórico de realocação e departamento principal por workspace."""

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="user_departments")
    workspace = models.ForeignKey(
        Workspace,
        on_delete=models.CASCADE,
        related_name="user_departments",
    )
    department = models.ForeignKey(
        Department,
        on_delete=models.CASCADE,
        related_name="user_assignments",
    )
    is_primary = models.BooleanField(default=True)
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            # Garante um único departamento principal por usuário/workspace.
            models.UniqueConstraint(
                fields=("user", "workspace"),
                condition=Q(is_primary=True),
                name="app_userdepartment_primary_per_workspace",
            ),
            # Histórico: só pode existir um vínculo "ativo" (sem end_date) por usuário/workspace.
            models.UniqueConstraint(
                fields=("user", "workspace"),
                condition=Q(end_date__isnull=True),
                name="app_userdepartment_single_active_per_workspace",
            ),
        ]
        verbose_name = "Departamento do usuário"
        verbose_name_plural = "Departamentos dos usuários"

    def clean(self) -> None:
        super().clean()
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValidationError(
                {"end_date": "A data final não pode ser anterior à data inicial."}
            )

    def __str__(self):
        return f"{self.user.email} → {self.department.name}"


class Client(models.Model):
    """Cliente do workspace (multi-tenant)."""

    workspace = models.ForeignKey(
        Workspace,
        on_delete=models.CASCADE,
        related_name="clients",
    )
    name = models.CharField(max_length=255)
    document = models.CharField(max_length=64, blank=True)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=64, blank=True)
    budget = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
    )
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_clients",
    )
    updated_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="updated_clients",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name", "pk"]
        verbose_name = "Cliente"
        verbose_name_plural = "Clientes"

    def __str__(self):
        return f"{self.name} ({self.workspace})"


class Project(models.Model):
    """Projeto vinculado a um cliente do mesmo workspace."""

    workspace = models.ForeignKey(
        Workspace,
        on_delete=models.CASCADE,
        related_name="projects",
    )
    client = models.ForeignKey(
        Client,
        on_delete=models.CASCADE,
        related_name="projects",
    )
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    budget = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
    )
    deadline = models.DateField(null=True, blank=True)
    estimated_hours = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        null=True,
        blank=True,
    )
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_projects",
    )
    updated_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="updated_projects",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name", "pk"]
        verbose_name = "Projeto"
        verbose_name_plural = "Projetos"

    def clean(self) -> None:
        super().clean()
        if self.client_id and self.workspace_id and self.client.workspace_id != self.workspace_id:
            raise ValidationError(
                {"client": "O cliente deve pertencer ao mesmo workspace do projeto."}
            )

    def save(self, *args, **kwargs) -> None:
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.name} ({self.client})"


class Task(models.Model):
    """Tarefa opcional dentro de um projeto."""

    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        related_name="tasks",
    )
    name = models.CharField(max_length=255)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name", "pk"]
        verbose_name = "Tarefa"
        verbose_name_plural = "Tarefas"

    def __str__(self):
        return f"{self.name} ({self.project})"


class UserClient(models.Model):
    """Define quais usuários podem usar qual cliente em um workspace."""

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="client_access_links",
    )
    client = models.ForeignKey(
        Client,
        on_delete=models.CASCADE,
        related_name="user_access_links",
    )
    workspace = models.ForeignKey(
        Workspace,
        on_delete=models.CASCADE,
        related_name="user_client_links",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("user", "client", "workspace"),
                name="app_userclient_user_client_workspace_uniq",
            ),
        ]
        verbose_name = "Acesso usuário → cliente"
        verbose_name_plural = "Acessos usuário → cliente"

    def clean(self) -> None:
        super().clean()
        if self.client_id and self.workspace_id and self.client.workspace_id != self.workspace_id:
            raise ValidationError(
                {"client": "O cliente deve pertencer ao workspace informado."}
            )

    def save(self, *args, **kwargs) -> None:
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.user.email} → {self.client.name}"


class UserProject(models.Model):
    """Define quais usuários podem usar qual projeto em um workspace."""

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="project_access_links",
    )
    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        related_name="user_access_links",
    )
    workspace = models.ForeignKey(
        Workspace,
        on_delete=models.CASCADE,
        related_name="user_project_links",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("user", "project", "workspace"),
                name="app_userproject_user_project_workspace_uniq",
            ),
        ]
        verbose_name = "Acesso usuário → projeto"
        verbose_name_plural = "Acessos usuário → projeto"

    def clean(self) -> None:
        super().clean()
        if self.project_id and self.workspace_id and self.project.workspace_id != self.workspace_id:
            raise ValidationError(
                {"project": "O projeto deve pertencer ao workspace informado."}
            )

    def save(self, *args, **kwargs) -> None:
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.user.email} → {self.project.name}"


class TimeEntryQuerySet(models.QuerySet):
    """Consultas de apontamentos; use ``saved_only()`` em agregações (rascunhos ficam de fora)."""

    def saved_only(self):
        return self.filter(status=self.model.Status.SAVED)


class TimeEntry(models.Model):
    class EntryType(models.TextChoices):
        INTERNAL = "internal", "Interno"
        EXTERNAL = "external", "Externo"
        DISPLACEMENT = "displacement", "Deslocamento"
        HOME_OFFICE = "home_office", "Home Office"

    @classmethod
    def allowed_entry_type_values(cls) -> frozenset[str]:
        """Valores válidos persistidos em ``TimeEntry.entry_type``."""
        return frozenset(e.value for e in cls.EntryType)

    class Status(models.TextChoices):
        DRAFT = "draft", "Rascunho"
        SAVED = "saved", "Salvo"

    class EntryMode(models.TextChoices):
        DURATION = "duration", "Duração"
        TIME_RANGE = "time_range", "Intervalo"
        TIMER = "timer", "Cronômetro"

    _MAX_MINUTES_PER_DAY = 24 * 60

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="time_entries")
    workspace = models.ForeignKey(
        Workspace,
        on_delete=models.CASCADE,
        related_name="time_entries",
    )
    department = models.ForeignKey(
        Department,
        on_delete=models.CASCADE,
        related_name="time_entries",
    )
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.SAVED,
    )
    entry_mode = models.CharField(
        max_length=20,
        choices=EntryMode.choices,
        default=EntryMode.DURATION,
    )
    timer_started_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Início do cronômetro (rascunho em andamento ou referência ao salvar).",
    )
    date = models.DateField()
    hours = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    start_time = models.TimeField(null=True, blank=True)
    end_time = models.TimeField(null=True, blank=True)
    duration_minutes = models.PositiveIntegerField(null=True, blank=True)
    client = models.ForeignKey(
        Client,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="time_entries",
    )
    project = models.ForeignKey(
        Project,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="time_entries",
    )
    task = models.ForeignKey(
        Task,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="time_entries",
    )
    entry_type = models.CharField(
        max_length=24,
        choices=EntryType.choices,
        blank=True,
    )
    description = models.TextField(blank=True)
    is_overtime = models.BooleanField(
        default=False,
        help_text="Indica se o apontamento é hora extra (opcional no lançamento).",
    )
    timer_pending_template_completion = models.BooleanField(
        default=False,
        help_text=(
            "Após parar o cronômetro: indica que o registro salvo ainda aguarda "
            "'Salvar dados do apontamento' ou descarte explícito."
        ),
    )
    pay_amount_snapshot = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Valor monetário do apontamento congelado no salvamento (remuneração vigente na data).",
    )
    effective_hourly_rate_snapshot = models.DecimalField(
        max_digits=14,
        decimal_places=4,
        null=True,
        blank=True,
        help_text="Valor-hora efetivo usado no cálculo (congelado).",
    )
    expected_month_hours_snapshot = models.DecimalField(
        max_digits=12,
        decimal_places=4,
        null=True,
        blank=True,
        help_text="Horas previstas do mês (fixo) ou horas base contratuais (não fixo) usadas no denominador.",
    )
    compensation_history_snapshot = models.ForeignKey(
        "CompensationHistory",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        help_text="Registro de remuneração usado no cálculo (congelado).",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = TimeEntryQuerySet.as_manager()

    class Meta:
        ordering = ["-date", "-pk"]
        indexes = [
            models.Index(fields=["workspace", "date"]),
            models.Index(fields=["user", "date"]),
            models.Index(fields=["project"]),
            models.Index(fields=["user", "workspace", "status"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=("user", "workspace"),
                condition=Q(status="draft"),
                name="app_timeentry_one_draft_per_user_workspace",
            ),
        ]
        verbose_name = "Apontamento"
        verbose_name_plural = "Apontamentos"

    def clean(self) -> None:
        super().clean()
        errors: dict[str, str] = {}

        if self.client_id and self.workspace_id and self.client.workspace_id != self.workspace_id:
            errors["client"] = "O cliente não pertence a este workspace."

        if self.project_id and self.workspace_id and self.project.workspace_id != self.workspace_id:
            errors["project"] = "O projeto não pertence a este workspace."

        if self.client_id and self.project_id and self.project.client_id != self.client_id:
            errors["project"] = "O projeto não pertence ao cliente selecionado."

        if self.task_id:
            if not self.project_id:
                errors["task"] = "Defina o projeto para associar uma tarefa."
            elif self.task.project_id != self.project_id:
                errors["task"] = "A tarefa não pertence ao projeto selecionado."

        if self.department_id and self.workspace_id and self.department.workspace_id != self.workspace_id:
            errors["department"] = "O departamento não pertence a este workspace."

        is_draft = self.status == self.Status.DRAFT
        has_hours = self.hours is not None
        has_start = self.start_time is not None
        has_end = self.end_time is not None
        has_time_range = has_start and has_end

        if not is_draft and has_start != has_end:
            errors["end_time"] = "Informe início e fim para usar o modo por intervalo."

        if (
            not is_draft
            and has_time_range
            and self.entry_mode in (self.EntryMode.TIME_RANGE, self.EntryMode.TIMER)
        ):
            if self.end_time <= self.start_time:
                errors["end_time"] = (
                    "O horário de fim deve ser maior que o de início no mesmo dia "
                    "(apontamento não pode atravessar meia-noite)."
                )
            else:
                start_total_minutes = self.start_time.hour * 60 + self.start_time.minute
                end_total_minutes = self.end_time.hour * 60 + self.end_time.minute
                self.duration_minutes = end_total_minutes - start_total_minutes

        if has_hours and self.duration_minutes is None:
            minutes_decimal = (self.hours * Decimal("60")).quantize(
                Decimal("1"),
                rounding=ROUND_HALF_UP,
            )
            self.duration_minutes = int(minutes_decimal)

        if is_draft:
            if errors:
                raise ValidationError(errors)
            return

        # --- salvo: validação por modo de entrada ---
        mode = self.entry_mode
        if mode == self.EntryMode.DURATION:
            if not has_hours and not (self.duration_minutes is not None and self.duration_minutes > 0):
                errors["hours"] = "Informe horas ou duração em minutos."
        elif mode == self.EntryMode.TIME_RANGE:
            if not has_time_range:
                errors["start_time"] = "Informe início e fim no mesmo dia."
        elif mode == self.EntryMode.TIMER:
            measurable = (
                has_hours
                or (self.duration_minutes is not None and self.duration_minutes > 0)
                or has_time_range
            )
            if not measurable:
                errors["hours"] = "Finalize o cronômetro com duração ou intervalo de horários."
            if self.timer_started_at and self.timer_started_at.date() != self.date:
                errors["date"] = "A data do apontamento deve ser a mesma do início do cronômetro."
        else:
            errors["entry_mode"] = "Modo de entrada inválido."

        if self.duration_minutes is not None and self.duration_minutes > self._MAX_MINUTES_PER_DAY:
            errors["duration_minutes"] = "Duração não pode exceder 24 horas no mesmo dia (MVP)."

        if has_hours and self.hours is not None and self.hours > Decimal("24"):
            errors["hours"] = "Horas não podem exceder 24 por apontamento (MVP)."

        if errors:
            raise ValidationError(errors)

    def _assert_user_access(self) -> None:
        """Garante que o usuário do apontamento tem vínculos UserClient / UserProject."""
        if self.status == self.Status.DRAFT and not self.client_id and not self.project_id:
            return
        ws_id = self.workspace_id
        if self.client_id:
            has_client = UserClient.objects.filter(
                user_id=self.user_id,
                client_id=self.client_id,
                workspace_id=ws_id,
            ).exists()
            if not has_client:
                raise PermissionDenied("Usuário sem permissão para este cliente neste workspace.")
        if self.project_id:
            has_project = UserProject.objects.filter(
                user_id=self.user_id,
                project_id=self.project_id,
                workspace_id=ws_id,
            ).exists()
            if not has_project:
                raise PermissionDenied("Usuário sem permissão para este projeto neste workspace.")

    def save(
        self,
        *args,
        skip_access_check: bool = False,
        financial_actor: User | None = None,
        sync_financial: bool = True,
        **kwargs,
    ) -> None:
        self.full_clean()
        if not skip_access_check:
            self._assert_user_access()
        from app.compensation_pay import compute_and_assign_pay_snapshots

        compute_and_assign_pay_snapshots(self)
        with transaction.atomic():
            super().save(*args, **kwargs)
            if sync_financial and self.status == self.Status.SAVED:
                from app.financial import sync_time_entry_financial_entry

                sync_time_entry_financial_entry(self, actor=financial_actor or self.user)

    def delete(
        self,
        *args,
        financial_actor: User | None = None,
        sync_financial: bool = True,
        **kwargs,
    ) -> tuple[int, dict[str, int]]:
        with transaction.atomic():
            if sync_financial and self.status == self.Status.SAVED:
                from app.financial import reverse_time_entry_financial_entry

                reverse_time_entry_financial_entry(self, actor=financial_actor or self.user)
            return super().delete(*args, **kwargs)

    def __str__(self):
        if self.hours is not None:
            return f"{self.user.email} {self.date} {self.hours}h"
        return f"{self.user.email} {self.date} {self.duration_minutes}min"


class MuralStatusOption(models.Model):
    """
    Status configurável do mural por workspace (gestor administra; membros usam os ativos).
    """

    workspace = models.ForeignKey(
        Workspace,
        on_delete=models.CASCADE,
        related_name="mural_status_options",
    )
    name = models.CharField(max_length=120)
    position = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    color_key = models.CharField(
        max_length=16,
        help_text="Chave da paleta fixa do mural (ex.: blue, green).",
    )
    created_by = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name="mural_status_options_created",
    )
    updated_by = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name="mural_status_options_updated",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["workspace", "position", "pk"]
        constraints = [
            models.UniqueConstraint(
                fields=("workspace", "name"),
                name="app_muralstatusoption_workspace_name_uniq",
            ),
        ]
        indexes = [
            models.Index(fields=["workspace", "position"]),
            models.Index(fields=["workspace", "is_active", "position"]),
        ]
        verbose_name = "Status do mural"
        verbose_name_plural = "Status do mural"

    def clean(self) -> None:
        super().clean()
        from app.mural_palette import validate_mural_color_key

        if self.name is not None:
            self.name = str(self.name).strip()
        if not self.name:
            raise ValidationError({"name": "Informe um nome para o status."})
        validate_mural_color_key(self.color_key, field_name="color_key")

    def save(self, *args, **kwargs) -> None:
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"{self.name} ({self.workspace})"


class PrivateBoardColumn(models.Model):
    """
    Coluna editável da lousa privada (Kanban/Mural) por usuário e workspace.
    O nome é apenas rótulo; a identidade da coluna é sempre o PK.
    """

    workspace = models.ForeignKey(
        Workspace,
        on_delete=models.CASCADE,
        related_name="private_board_columns",
    )
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="private_board_columns",
    )
    name = models.CharField(max_length=255)
    position = models.PositiveIntegerField(default=0)
    color_key = models.CharField(
        max_length=16,
        blank=True,
        null=True,
        help_text="Chave opcional da paleta fixa para realce da coluna.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["workspace", "user", "position", "pk"]
        constraints = [
            models.UniqueConstraint(
                fields=("workspace", "user", "position"),
                name="app_privateboardcolumn_workspace_user_position_uniq",
            ),
        ]
        indexes = [
            models.Index(fields=["workspace", "user", "position"]),
        ]
        verbose_name = "Coluna da lousa privada"
        verbose_name_plural = "Colunas da lousa privada"

    def clean(self) -> None:
        super().clean()
        from app.mural_palette import validate_mural_color_key

        if self.name is not None and not str(self.name).strip():
            raise ValidationError({"name": "Informe um nome para a coluna."})
        validate_mural_color_key(self.color_key, field_name="color_key")

    def save(self, *args, **kwargs) -> None:
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"{self.name} ({self.user.email} · {self.workspace})"


class BoardCard(models.Model):
    """
    Card único para lousa pública (uma coluna implícita) ou privada (coluna FK).
    """

    class Visibility(models.TextChoices):
        PRIVATE = "private", "Privado"
        PUBLIC = "public", "Público"

    class PublicLane(models.TextChoices):
        MEMBERS = "members", "Membros"
        MANAGEMENT = "management", "Gestão"

    workspace = models.ForeignKey(
        Workspace,
        on_delete=models.CASCADE,
        related_name="board_cards",
    )
    created_by = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name="board_cards_created",
    )
    updated_by = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name="board_cards_updated",
    )
    visibility = models.CharField(
        max_length=10,
        choices=Visibility.choices,
    )
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    private_column = models.ForeignKey(
        PrivateBoardColumn,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="cards",
    )
    public_lane = models.CharField(
        max_length=20,
        choices=PublicLane.choices,
        null=True,
        blank=True,
    )
    position = models.PositiveIntegerField(default=0)
    category = models.CharField(max_length=64, blank=True)
    event_date = models.DateField(null=True, blank=True)
    due_date = models.DateField(null=True, blank=True)
    client = models.ForeignKey(
        "Client",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="board_cards",
    )
    project = models.ForeignKey(
        "Project",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="board_cards",
    )
    task = models.ForeignKey(
        "Task",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="board_cards",
    )
    budget_goal = models.ForeignKey(
        BudgetGoal,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="board_cards",
    )
    assigned_user = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="board_cards_assigned",
    )
    assigned_department = models.ForeignKey(
        Department,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="board_cards",
    )
    mural_status = models.ForeignKey(
        MuralStatusOption,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="board_cards",
    )
    color_key = models.CharField(
        max_length=16,
        blank=True,
        null=True,
        help_text="Chave opcional da paleta fixa para realce do card.",
    )
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["workspace", "visibility", "private_column", "position", "pk"]
        constraints = [
            _check_constraint(
                predicate=Q(visibility="private", private_column__isnull=False)
                | Q(visibility="public", private_column__isnull=True),
                name="app_boardcard_visibility_private_column_consistency",
            ),
            _check_constraint(
                predicate=Q(visibility="private", public_lane__isnull=True)
                | Q(visibility="public", public_lane__isnull=False),
                name="app_boardcard_visibility_public_lane_consistency",
            ),
            models.UniqueConstraint(
                fields=("private_column", "position"),
                condition=Q(visibility="private"),
                name="app_boardcard_private_column_position_uniq",
            ),
            models.UniqueConstraint(
                fields=("workspace", "public_lane", "position"),
                condition=Q(visibility="public", private_column__isnull=True, public_lane__isnull=False),
                name="app_boardcard_public_lane_workspace_position_uniq",
            ),
        ]
        indexes = [
            models.Index(fields=["workspace", "visibility", "public_lane", "position"]),
            models.Index(fields=["private_column", "position"]),
        ]
        verbose_name = "Card do mural"
        verbose_name_plural = "Cards do mural"

    def clean(self) -> None:
        super().clean()
        errors: dict[str, str] = {}

        if self.visibility == self.Visibility.PRIVATE:
            if not self.private_column_id:
                errors["private_column"] = "Card privado deve estar em uma coluna da lousa privada."
            if self.public_lane:
                errors["public_lane"] = "Card privado não pode ter coluna pública."
        elif self.visibility == self.Visibility.PUBLIC:
            if self.private_column_id:
                errors["private_column"] = "Card público não pode referenciar coluna privada."
            if not self.public_lane:
                errors["public_lane"] = "Card público deve indicar a coluna pública."

        if self.private_column_id:
            col = self.private_column
            if col is not None:
                if self.workspace_id and col.workspace_id != self.workspace_id:
                    errors["private_column"] = "A coluna deve pertencer ao mesmo workspace do card."
                if self.created_by_id and col.user_id != self.created_by_id:
                    errors["private_column"] = (
                        "A coluna privada deve pertencer ao mesmo usuário criador do card."
                    )

        ws_id = self.workspace_id

        if self.client_id and ws_id and self.client.workspace_id != ws_id:
            errors["client"] = "O cliente deve pertencer ao mesmo workspace do card."

        if self.project_id and ws_id and self.project.workspace_id != ws_id:
            errors["project"] = "O projeto deve pertencer ao mesmo workspace do card."

        if self.client_id and self.project_id and self.project.client_id != self.client_id:
            errors["project"] = "O projeto deve pertencer ao cliente informado."

        if self.task_id:
            if not self.project_id:
                errors["task"] = "Informe o projeto ao qual a tarefa pertence."
            elif self.task.project_id != self.project_id:
                errors["task"] = "A tarefa deve pertencer ao projeto informado."

        if self.budget_goal_id:
            bg = self.budget_goal
            if bg is not None and ws_id and bg.workspace_id != ws_id:
                errors["budget_goal"] = "A meta deve pertencer ao mesmo workspace do card."
            elif bg is not None and bg.visibility != BudgetGoal.Visibility.PUBLIC:
                errors["budget_goal"] = "Apenas metas públicas podem ser vinculadas no mural."

        if self.assigned_department_id and ws_id and self.assigned_department.workspace_id != ws_id:
            errors["assigned_department"] = (
                "O departamento atribuído deve pertencer ao mesmo workspace do card."
            )

        if self.assigned_user_id and ws_id:
            if not Membership.objects.filter(user_id=self.assigned_user_id, workspace_id=ws_id).exists():
                errors["assigned_user"] = "O usuário atribuído deve ser membro do workspace."

        from app.mural_palette import validate_mural_color_key

        validate_mural_color_key(self.color_key, field_name="color_key")

        if self.mural_status_id:
            st = self.mural_status
            if st is None:
                errors["mural_status"] = "Status inválido."
            elif ws_id and st.workspace_id != ws_id:
                errors["mural_status"] = "O status deve pertencer ao mesmo workspace do card."
            elif not st.is_active:
                prev_id: int | None = None
                if self.pk:
                    prev_id = (
                        BoardCard.objects.filter(pk=self.pk)
                        .values_list("mural_status_id", flat=True)
                        .first()
                    )
                if prev_id != self.mural_status_id:
                    errors["mural_status"] = "Selecione um status ativo do mural."

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs) -> None:
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"{self.title} ({self.get_visibility_display()})"


class PaymentMethod(models.Model):
    """
    Método de pagamento associado a um usuário.

    Não armazena CVV nem o número completo do cartão em texto plano.
    Guarda um token (placeholder, NÃO substitui tokenização PCI),
    os últimos 4 dígitos e metadados auxiliares (validade, titular,
    plano contratado e CPF mascarado).
    """

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="payment_methods",
    )
    token = models.CharField(max_length=128)
    holder_name = models.CharField(max_length=255, blank=True)
    card_last4 = models.CharField(max_length=4, blank=True)
    expiry_month = models.PositiveSmallIntegerField(null=True, blank=True)
    expiry_year = models.PositiveSmallIntegerField(null=True, blank=True)
    cpf_masked = models.CharField(max_length=32, blank=True)
    plan = models.CharField(max_length=50, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        last4 = self.card_last4 or "----"
        return f"{self.user.email} ****{last4}"
