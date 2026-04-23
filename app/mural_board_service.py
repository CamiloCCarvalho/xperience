"""
Operações de domínio do Mural/Kanban (membro): colunas privadas, cards e reordenação.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Max
from app.models import BoardCard, Membership, MuralStatusOption, PrivateBoardColumn, User, Workspace
from app.mural_palette import mural_color_hex, validate_mural_color_key


_UNSET_COLUMN_COLOR: Any = object()

DEFAULT_PRIVATE_COLUMN_NAMES: tuple[str, ...] = (
    "Rascunho",
    "Notas",
    "Pendente",
    "Impedimento",
    "Andamento",
    "Concluído",
    "Cancelado",
)


def assert_workspace_member(user: User, workspace: Workspace) -> None:
    if workspace.owner_id == user.id:
        return
    if not Membership.objects.filter(user=user, workspace=workspace).exists():
        raise PermissionDenied("Sem vínculo com este workspace.")


def assert_card_mutation_allowed(card: BoardCard, user: User) -> None:
    """MVP: só o criador altera, exclui ou move o card (público ou privado)."""
    if card.created_by_id != user.id:
        raise PermissionDenied("Apenas o criador do card pode alterá-lo.")


def ensure_default_private_columns(workspace: Workspace, user: User) -> list[PrivateBoardColumn]:
    """
    Se o usuário ainda não tiver colunas privadas neste workspace, cria o conjunto padrão.
    """
    assert_workspace_member(user, workspace)
    existing = PrivateBoardColumn.objects.filter(workspace=workspace, user=user)
    if existing.exists():
        return list(existing.order_by("position", "pk"))
    cols: list[PrivateBoardColumn] = []
    with transaction.atomic():
        for i, name in enumerate(DEFAULT_PRIVATE_COLUMN_NAMES):
            cols.append(
                PrivateBoardColumn(
                    workspace=workspace,
                    user=user,
                    name=name,
                    position=i,
                )
            )
        PrivateBoardColumn.objects.bulk_create(cols)
    return list(
        PrivateBoardColumn.objects.filter(workspace=workspace, user=user).order_by("position", "pk")
    )


def get_private_column(workspace: Workspace, user: User, column_id: int) -> PrivateBoardColumn | None:
    return PrivateBoardColumn.objects.filter(
        pk=column_id,
        workspace=workspace,
        user=user,
    ).first()


def get_board_card_for_member(
    workspace: Workspace,
    user: User,
    card_id: int,
) -> BoardCard | None:
    """
    Card acessível ao membro no workspace:
    - públicos: qualquer membro
    - privados: só se created_by == user
    """
    assert_workspace_member(user, workspace)
    card = (
        BoardCard.objects.filter(pk=card_id, workspace=workspace)
        .select_related(
            "private_column",
            "client",
            "project",
            "task",
            "budget_goal",
            "assigned_user",
            "assigned_department",
            "created_by",
            "updated_by",
            "mural_status",
        )
        .first()
    )
    if card is None:
        return None
    if card.visibility == BoardCard.Visibility.PRIVATE and card.created_by_id != user.id:
        return None
    return card


def serialize_column(col: PrivateBoardColumn) -> dict[str, Any]:
    return {
        "id": col.pk,
        "workspace_id": col.workspace_id,
        "user_id": col.user_id,
        "name": col.name,
        "position": col.position,
        "color_key": col.color_key or None,
        "color_hex": mural_color_hex(col.color_key) if col.color_key else None,
        "created_at": col.created_at.isoformat(),
        "updated_at": col.updated_at.isoformat(),
    }


def serialize_mural_status_option(opt: MuralStatusOption) -> dict[str, Any]:
    return {
        "id": opt.pk,
        "name": opt.name,
        "position": opt.position,
        "is_active": opt.is_active,
        "color_key": opt.color_key,
        "color_hex": mural_color_hex(opt.color_key),
    }


def _mural_status_fields_for_card(card: BoardCard) -> dict[str, Any]:
    ms = card.mural_status
    if ms is None:
        return {
            "mural_status_id": None,
            "mural_status_name": None,
            "mural_status_color_key": None,
            "mural_status_color_hex": None,
            "mural_status_is_active": None,
        }
    return {
        "mural_status_id": ms.pk,
        "mural_status_name": ms.name,
        "mural_status_color_key": ms.color_key,
        "mural_status_color_hex": mural_color_hex(ms.color_key),
        "mural_status_is_active": ms.is_active,
    }


def serialize_card(card: BoardCard) -> dict[str, Any]:
    base: dict[str, Any] = {
        "id": card.pk,
        "workspace_id": card.workspace_id,
        "visibility": card.visibility,
        "title": card.title,
        "description": card.description,
        "private_column_id": card.private_column_id,
        "public_lane": card.public_lane,
        "position": card.position,
        "category": card.category,
        "event_date": card.event_date.isoformat() if card.event_date else None,
        "due_date": card.due_date.isoformat() if card.due_date else None,
        "client_id": card.client_id,
        "project_id": card.project_id,
        "task_id": card.task_id,
        "budget_goal_id": card.budget_goal_id,
        "assigned_user_id": card.assigned_user_id,
        "assigned_department_id": card.assigned_department_id,
        "metadata": card.metadata or {},
        "created_by_id": card.created_by_id,
        "updated_by_id": card.updated_by_id,
        "created_at": card.created_at.isoformat(),
        "updated_at": card.updated_at.isoformat(),
        "color_key": card.color_key or None,
        "color_hex": mural_color_hex(card.color_key) if card.color_key else None,
    }
    base.update(_mural_status_fields_for_card(card))
    return base


def serialize_card_ui(card: BoardCard) -> dict[str, Any]:
    """Mesmo que ``serialize_card`` com rótulos para a UI (requer ``select_related`` usuais)."""
    from app.avatar import user_avatar_url

    data = serialize_card(card)
    creator = card.created_by
    if creator is not None:
        label = (creator.get_full_name() or "").strip()
        data["creator_label"] = label or creator.email
        data["creator_avatar_url"] = user_avatar_url(creator)
    else:
        data["creator_label"] = None
        data["creator_avatar_url"] = None
    data["client_name"] = card.client.name if card.client_id and card.client else None
    data["project_name"] = card.project.name if card.project_id and card.project else None
    data["task_name"] = card.task.name if card.task_id and card.task else None
    bg = card.budget_goal if card.budget_goal_id else None
    if bg is not None:
        if bg.project_id:
            pname = bg.project.name if bg.project else ""
            data["budget_goal_label"] = f"Meta · {pname}".strip()
        elif bg.client_id:
            cname = bg.client.name if bg.client else ""
            data["budget_goal_label"] = f"Meta · {cname}".strip()
        else:
            data["budget_goal_label"] = "Meta · workspace"
    else:
        data["budget_goal_label"] = None
    au = card.assigned_user
    if au is not None:
        al = (au.get_full_name() or "").strip()
        data["assigned_user_label"] = al or au.email
    else:
        data["assigned_user_label"] = None
    ad = card.assigned_department
    data["assigned_department_name"] = ad.name if ad and card.assigned_department_id else None
    return data


def load_mural_payload(
    workspace: Workspace,
    user: User,
    *,
    include_inactive_mural_statuses: bool = False,
) -> dict[str, Any]:
    assert_workspace_member(user, workspace)
    columns = ensure_default_private_columns(workspace, user)
    card_select = (
        "client",
        "project",
        "task",
        "budget_goal",
        "budget_goal__project",
        "budget_goal__client",
        "assigned_user",
        "assigned_department",
        "created_by",
        "updated_by",
        "mural_status",
    )
    public_cards = (
        BoardCard.objects.filter(workspace=workspace, visibility=BoardCard.Visibility.PUBLIC)
        .select_related(*card_select)
        .order_by("public_lane", "position", "pk")
    )
    private_cards = (
        BoardCard.objects.filter(
            workspace=workspace,
            visibility=BoardCard.Visibility.PRIVATE,
            created_by=user,
        )
        .select_related(
            "private_column",
            *card_select,
        )
        .order_by("private_column", "position", "pk")
    )
    public_members_cards = [c for c in public_cards if c.public_lane == BoardCard.PublicLane.MEMBERS]
    public_management_cards = [c for c in public_cards if c.public_lane == BoardCard.PublicLane.MANAGEMENT]
    active_statuses = list(
        MuralStatusOption.objects.filter(workspace=workspace, is_active=True).order_by("position", "pk")
    )
    payload: dict[str, Any] = {
        "workspace_id": workspace.pk,
        "members_lane_locked": bool(workspace.mural_members_lane_locked),
        "private_columns": [serialize_column(c) for c in columns],
        "public_cards": [serialize_card_ui(c) for c in public_cards],
        "public_cards_by_lane": {
            BoardCard.PublicLane.MEMBERS: [serialize_card_ui(c) for c in public_members_cards],
            BoardCard.PublicLane.MANAGEMENT: [serialize_card_ui(c) for c in public_management_cards],
        },
        "private_cards": [serialize_card_ui(c) for c in private_cards],
        "mural_statuses": [serialize_mural_status_option(s) for s in active_statuses],
    }
    if include_inactive_mural_statuses:
        all_statuses = list(MuralStatusOption.objects.filter(workspace=workspace).order_by("position", "pk"))
        payload["mural_statuses_all"] = [serialize_mural_status_option(s) for s in all_statuses]
    return payload


def create_private_column(
    workspace: Workspace,
    user: User,
    *,
    name: str,
    position: int | None = None,
    color_key: str | None = None,
) -> PrivateBoardColumn:
    assert_workspace_member(user, workspace)
    name = (name or "").strip()
    if not name:
        raise ValidationError({"name": "Informe o nome da coluna."})
    ck = (color_key or "").strip() or None
    if ck:
        validate_mural_color_key(ck)
    with transaction.atomic():
        if position is None:
            agg = PrivateBoardColumn.objects.filter(workspace=workspace, user=user).aggregate(
                m=Max("position")
            )
            position = (agg["m"] if agg["m"] is not None else -1) + 1
        col = PrivateBoardColumn(workspace=workspace, user=user, name=name, position=position, color_key=ck)
        col.save()
    return col


def rename_private_column(
    workspace: Workspace,
    user: User,
    column_id: int,
    *,
    name: str,
    color_key: Any = _UNSET_COLUMN_COLOR,
) -> PrivateBoardColumn:
    col = get_private_column(workspace, user, column_id)
    if col is None:
        raise ValidationError("Coluna não encontrada.")
    col.name = name.strip()
    if color_key is not _UNSET_COLUMN_COLOR:
        ck = (color_key or "").strip() or None
        if ck:
            validate_mural_color_key(ck)
        col.color_key = ck
    col.save()
    return col


def delete_private_column(workspace: Workspace, user: User, column_id: int) -> None:
    col = get_private_column(workspace, user, column_id)
    if col is None:
        raise ValidationError("Coluna não encontrada.")
    col.delete()


def reorder_private_columns(workspace: Workspace, user: User, ordered_column_ids: list[int]) -> None:
    assert_workspace_member(user, workspace)
    qs = PrivateBoardColumn.objects.filter(workspace=workspace, user=user)
    existing_ids = set(qs.values_list("pk", flat=True))
    ordered_set = set(ordered_column_ids)
    if ordered_set != existing_ids or len(ordered_column_ids) != len(existing_ids):
        raise ValidationError("A lista de colunas deve conter exatamente todas as colunas do mural privado.")
    n = len(ordered_column_ids)
    offset = n + 10
    with transaction.atomic():
        for i, cid in enumerate(ordered_column_ids):
            PrivateBoardColumn.objects.filter(pk=cid, workspace=workspace, user=user).update(
                position=offset + i
            )
        for i, cid in enumerate(ordered_column_ids):
            PrivateBoardColumn.objects.filter(pk=cid, workspace=workspace, user=user).update(position=i)


def _renumber_cards_ordered(cards: list[BoardCard], user: User) -> None:
    """
    Persiste posições densas 0..n-1 sem violar unicidade (workspace, position) ou
    (private_column, position) durante saves intermediários.
    """
    if not cards:
        return
    offset = len(cards) + 10
    for i, c in enumerate(cards):
        c.position = offset + i
        c.updated_by = user
        c.save()
    for i, c in enumerate(cards):
        c.position = i
        c.updated_by = user
        c.save()


def reposition_card(
    workspace: Workspace,
    user: User,
    card: BoardCard,
    *,
    insert_index: int,
) -> None:
    assert_workspace_member(user, workspace)
    if card.workspace_id != workspace.pk:
        raise ValidationError("Card de outro workspace.")
    assert_card_mutation_allowed(card, user)

    with transaction.atomic():
        live = BoardCard.objects.select_for_update().get(pk=card.pk, workspace=workspace)
        assert_card_mutation_allowed(live, user)
        if live.visibility == BoardCard.Visibility.PUBLIC:
            pool = list(
                BoardCard.objects.select_for_update()
                .filter(
                    workspace=workspace,
                    visibility=BoardCard.Visibility.PUBLIC,
                    public_lane=live.public_lane,
                )
                .order_by("position", "pk")
            )
        else:
            pool = list(
                BoardCard.objects.select_for_update()
                .filter(
                    workspace=workspace,
                    visibility=BoardCard.Visibility.PRIVATE,
                    private_column_id=live.private_column_id,
                )
                .order_by("position", "pk")
            )
        ids = {c.pk for c in pool}
        if live.pk not in ids:
            raise ValidationError("Card inconsistente com o contexto.")
        ordered = [c for c in pool if c.pk != live.pk]
        insert_index = max(0, min(int(insert_index), len(ordered)))
        ordered.insert(insert_index, live)
        _renumber_cards_ordered(ordered, user)


def move_private_card_between_columns(
    workspace: Workspace,
    user: User,
    card: BoardCard,
    *,
    new_column_id: int,
    insert_index: int,
) -> BoardCard:
    """Move card privado para outra coluna privada do mesmo usuário (ou reordena na mesma coluna)."""
    assert_workspace_member(user, workspace)
    if card.workspace_id != workspace.pk:
        raise ValidationError("Card de outro workspace.")
    assert_card_mutation_allowed(card, user)
    if card.visibility != BoardCard.Visibility.PRIVATE:
        raise ValidationError("Apenas cards privados podem ser movidos entre colunas.")

    new_col = get_private_column(workspace, user, int(new_column_id))
    if new_col is None:
        raise ValidationError("Coluna não encontrada.")

    with transaction.atomic():
        live = BoardCard.objects.select_for_update().get(pk=card.pk, workspace=workspace)
        assert_card_mutation_allowed(live, user)
        if live.visibility != BoardCard.Visibility.PRIVATE:
            raise ValidationError("Apenas cards privados podem ser movidos entre colunas.")
        old_col_id = live.private_column_id
        if old_col_id is None:
            raise ValidationError("Card privado sem coluna.")

        if int(old_col_id) == int(new_column_id):
            reposition_card(workspace, user, live, insert_index=insert_index)
            live.refresh_from_db()
            return live

        old_remaining = list(
            BoardCard.objects.select_for_update()
            .filter(
                workspace=workspace,
                visibility=BoardCard.Visibility.PRIVATE,
                private_column_id=old_col_id,
            )
            .exclude(pk=live.pk)
            .order_by("position", "pk")
        )
        _renumber_cards_ordered(old_remaining, user)

        new_pool = list(
            BoardCard.objects.select_for_update()
            .filter(
                workspace=workspace,
                visibility=BoardCard.Visibility.PRIVATE,
                private_column_id=new_column_id,
            )
            .order_by("position", "pk")
        )
        insert_index = max(0, min(int(insert_index), len(new_pool)))
        new_pool.insert(insert_index, live)
        live.private_column = new_col
        live.updated_by = user
        _renumber_cards_ordered(new_pool, user)

    live.refresh_from_db()
    return live


def move_private_card_to_public(
    workspace: Workspace,
    user: User,
    card: BoardCard,
    *,
    public_lane: str = BoardCard.PublicLane.MEMBERS,
    allow_management_lane: bool = False,
    respect_members_lane_lock: bool = True,
) -> BoardCard:
    assert_workspace_member(user, workspace)
    if card.workspace_id != workspace.pk:
        raise ValidationError("Card de outro workspace.")
    assert_card_mutation_allowed(card, user)
    if card.visibility != BoardCard.Visibility.PRIVATE:
        raise ValidationError("Apenas cards privados podem ser movidos para a lousa pública.")

    lane = (public_lane or "").strip() or BoardCard.PublicLane.MEMBERS
    if lane == BoardCard.PublicLane.MANAGEMENT and not allow_management_lane:
        raise PermissionDenied("Membro não pode mover card para a coluna pública Gestão.")
    if lane == BoardCard.PublicLane.MEMBERS and respect_members_lane_lock and workspace.mural_members_lane_locked:
        raise PermissionDenied("A coluna pública Membros está bloqueada pela gestão.")

    with transaction.atomic():
        live = BoardCard.objects.select_for_update().get(pk=card.pk, workspace=workspace)
        assert_card_mutation_allowed(live, user)
        if live.visibility != BoardCard.Visibility.PRIVATE:
            raise ValidationError("Apenas cards privados podem ser movidos para a lousa pública.")
        public_list = list(
            BoardCard.objects.select_for_update()
            .filter(
                workspace=workspace,
                visibility=BoardCard.Visibility.PUBLIC,
                public_lane=lane,
            )
            .order_by("position", "pk")
        )
        live.visibility = BoardCard.Visibility.PUBLIC
        live.private_column = None
        live.public_lane = lane
        live.updated_by = user
        public_list.append(live)
        _renumber_cards_ordered(public_list, user)
    live.refresh_from_db()
    return live


def _parse_optional_date(val: Any) -> date | None:
    if val in (None, ""):
        return None
    if isinstance(val, date):
        return val
    return date.fromisoformat(str(val)[:10])


def create_board_card(
    workspace: Workspace,
    user: User,
    *,
    visibility: str,
    title: str,
    private_column_id: int | None = None,
    public_lane: str | None = None,
    description: str = "",
    category: str = "",
    event_date: Any = None,
    due_date: Any = None,
    client_id: int | None = None,
    project_id: int | None = None,
    task_id: int | None = None,
    budget_goal_id: int | None = None,
    assigned_user_id: int | None = None,
    assigned_department_id: int | None = None,
    metadata: dict | None = None,
    mural_status_id: int | None = None,
    color_key: str | None = None,
    allow_management_lane: bool = False,
    respect_members_lane_lock: bool = True,
) -> BoardCard:
    assert_workspace_member(user, workspace)
    title = (title or "").strip()
    if not title:
        raise ValidationError({"title": "Informe o título do card."})

    lane: str | None = None
    private_column = None
    if visibility == BoardCard.Visibility.PRIVATE:
        if not private_column_id:
            raise ValidationError({"private_column": "Card privado exige coluna."})
        private_column = get_private_column(workspace, user, int(private_column_id))
        if private_column is None:
            raise ValidationError({"private_column": "Coluna inválida."})
        next_pos = (
            BoardCard.objects.filter(
                workspace=workspace,
                visibility=BoardCard.Visibility.PRIVATE,
                private_column=private_column,
            ).aggregate(m=Max("position"))["m"]
        )
        position = (next_pos if next_pos is not None else -1) + 1
    elif visibility == BoardCard.Visibility.PUBLIC:
        lane = (public_lane or "").strip() or BoardCard.PublicLane.MEMBERS
        if lane == BoardCard.PublicLane.MANAGEMENT and not allow_management_lane:
            raise PermissionDenied("Membro não pode criar card diretamente na coluna Gestão.")
        if lane == BoardCard.PublicLane.MEMBERS and respect_members_lane_lock and workspace.mural_members_lane_locked:
            raise PermissionDenied("A coluna pública Membros está bloqueada pela gestão.")
        next_pos = BoardCard.objects.filter(
            workspace=workspace,
            visibility=BoardCard.Visibility.PUBLIC,
            public_lane=lane,
        ).aggregate(m=Max("position"))["m"]
        position = (next_pos if next_pos is not None else -1) + 1
    else:
        raise ValidationError({"visibility": "Visibilidade inválida."})

    mural_status: MuralStatusOption | None = None
    if mural_status_id:
        mural_status = MuralStatusOption.objects.filter(pk=int(mural_status_id), workspace=workspace).first()
        if mural_status is None:
            raise ValidationError({"mural_status_id": "Status inválido para este workspace."})
        if not mural_status.is_active:
            raise ValidationError({"mural_status_id": "Selecione um status ativo do mural."})

    ck = (color_key or "").strip() or None
    if ck:
        validate_mural_color_key(ck)

    card = BoardCard(
        workspace=workspace,
        created_by=user,
        updated_by=user,
        visibility=visibility,
        title=title,
        description=description or "",
        private_column=private_column,
        public_lane=lane if visibility == BoardCard.Visibility.PUBLIC else None,
        position=position,
        category=(category or "")[:64],
        event_date=_parse_optional_date(event_date),
        due_date=_parse_optional_date(due_date),
        client_id=client_id,
        project_id=project_id,
        task_id=task_id,
        budget_goal_id=budget_goal_id,
        assigned_user_id=assigned_user_id,
        assigned_department_id=assigned_department_id,
        metadata=metadata if metadata is not None else {},
        mural_status=mural_status,
        color_key=ck,
    )
    card.save()
    return card


def update_board_card(
    workspace: Workspace,
    user: User,
    card: BoardCard,
    *,
    data: dict[str, Any],
) -> BoardCard:
    assert_workspace_member(user, workspace)
    if card.workspace_id != workspace.pk:
        raise ValidationError("Card de outro workspace.")
    assert_card_mutation_allowed(card, user)

    allowed = {
        "title",
        "description",
        "category",
        "event_date",
        "due_date",
        "client_id",
        "project_id",
        "task_id",
        "budget_goal_id",
        "assigned_user_id",
        "assigned_department_id",
        "metadata",
        "mural_status_id",
        "color_key",
    }
    for key in data:
        if key not in allowed:
            continue
        val = data[key]
        if key == "mural_status_id":
            if val in (None, ""):
                card.mural_status_id = None
            else:
                card.mural_status_id = int(val)
        elif key == "color_key":
            ck = (str(val) if val is not None else "").strip() or None
            card.color_key = ck
        elif key.endswith("_id"):
            if val in (None, ""):
                setattr(card, key, None)
            else:
                setattr(card, key, int(val))
        elif key == "metadata":
            if val is None:
                card.metadata = {}
            elif isinstance(val, dict):
                card.metadata = val
            else:
                raise ValidationError({"metadata": "Metadados devem ser um objeto JSON."})
        elif key in ("event_date", "due_date"):
            if val in (None, ""):
                setattr(card, key, None)
            elif isinstance(val, str):
                setattr(card, key, date.fromisoformat(val[:10]))
            else:
                setattr(card, key, val)
        elif key == "title":
            card.title = (str(val) if val is not None else "").strip()
        else:
            setattr(card, key, val if val is not None else "")

    card.updated_by = user
    card.save()
    return card


def delete_board_card(workspace: Workspace, user: User, card: BoardCard) -> None:
    assert_workspace_member(user, workspace)
    if card.workspace_id != workspace.pk:
        raise ValidationError("Card de outro workspace.")
    assert_card_mutation_allowed(card, user)
    was_public = card.visibility == BoardCard.Visibility.PUBLIC
    public_lane = card.public_lane
    col_id = card.private_column_id
    with transaction.atomic():
        card.delete()
        if was_public:
            remaining = list(
                BoardCard.objects.select_for_update()
                .filter(
                    workspace=workspace,
                    visibility=BoardCard.Visibility.PUBLIC,
                    public_lane=public_lane,
                )
                .order_by("position", "pk")
            )
            _renumber_cards_ordered(remaining, user)
        elif col_id:
            remaining = list(
                BoardCard.objects.select_for_update()
                .filter(
                    workspace=workspace,
                    visibility=BoardCard.Visibility.PRIVATE,
                    private_column_id=col_id,
                )
                .order_by("position", "pk")
            )
            _renumber_cards_ordered(remaining, user)


def create_mural_status_option(
    workspace: Workspace,
    actor: User,
    *,
    name: str,
    color_key: str,
    position: int | None = None,
) -> MuralStatusOption:
    assert_workspace_member(actor, workspace)
    nm = (name or "").strip()
    if not nm:
        raise ValidationError({"name": "Informe o nome."})
    ck = (color_key or "").strip()
    validate_mural_color_key(ck, field_name="color_key")
    with transaction.atomic():
        if position is None:
            agg = MuralStatusOption.objects.filter(workspace=workspace).aggregate(m=Max("position"))
            position = (agg["m"] if agg["m"] is not None else -1) + 1
        opt = MuralStatusOption(
            workspace=workspace,
            name=nm,
            position=position,
            is_active=True,
            color_key=ck,
            created_by=actor,
            updated_by=actor,
        )
        try:
            opt.save()
        except IntegrityError as e:
            raise ValidationError({"name": "Já existe um status com este nome neste workspace."}) from e
    return opt


def update_mural_status_option(
    workspace: Workspace,
    actor: User,
    status_id: int,
    *,
    name: str | None = None,
    color_key: str | None = None,
    is_active: bool | None = None,
) -> MuralStatusOption:
    opt = MuralStatusOption.objects.filter(pk=status_id, workspace=workspace).first()
    if opt is None:
        raise ValidationError("Status não encontrado.")
    if name is not None:
        opt.name = str(name).strip()
        if not opt.name:
            raise ValidationError({"name": "Informe o nome."})
    if color_key is not None:
        ck = str(color_key).strip()
        if not ck:
            raise ValidationError({"color_key": "Informe uma cor da paleta."})
        validate_mural_color_key(ck, field_name="color_key")
        opt.color_key = ck
    if is_active is not None:
        opt.is_active = bool(is_active)
    opt.updated_by = actor
    try:
        opt.save()
    except IntegrityError as e:
        raise ValidationError({"name": "Já existe um status com este nome neste workspace."}) from e
    return opt


def reorder_mural_status_options(workspace: Workspace, user: User, ordered_status_ids: list[int]) -> None:
    assert_workspace_member(user, workspace)
    qs = MuralStatusOption.objects.filter(workspace=workspace)
    existing_ids = set(qs.values_list("pk", flat=True))
    ordered_set = set(ordered_status_ids)
    if ordered_set != existing_ids or len(ordered_status_ids) != len(existing_ids):
        raise ValidationError("A lista de status deve conter exatamente todos os status do workspace.")
    n = len(ordered_status_ids)
    offset = n + 10
    with transaction.atomic():
        for i, sid in enumerate(ordered_status_ids):
            o = MuralStatusOption.objects.select_for_update().get(pk=sid, workspace=workspace)
            o.position = offset + i
            o.updated_by = user
            o.save()
        for i, sid in enumerate(ordered_status_ids):
            o = MuralStatusOption.objects.select_for_update().get(pk=sid, workspace=workspace)
            o.position = i
            o.updated_by = user
            o.save()


def parse_card_fk_payload(data: dict[str, Any]) -> dict[str, Any]:
    """Extrai FKs opcionais de dict (JSON ou form)."""
    out: dict[str, Any] = {}
    for key in (
        "private_column_id",
        "client_id",
        "project_id",
        "task_id",
        "budget_goal_id",
        "assigned_user_id",
        "assigned_department_id",
        "mural_status_id",
    ):
        if key not in data:
            continue
        raw = data.get(key)
        if raw in (None, ""):
            out[key] = None
        else:
            try:
                out[key] = int(raw)
            except (TypeError, ValueError):
                out[key] = None
    return out


def copy_public_card_to_private(
    workspace: Workspace,
    user: User,
    card: BoardCard,
    *,
    private_column_id: int | None = None,
) -> BoardCard:
    assert_workspace_member(user, workspace)
    if card.workspace_id != workspace.pk:
        raise ValidationError("Card de outro workspace.")
    if card.visibility != BoardCard.Visibility.PUBLIC:
        raise ValidationError("Apenas cards públicos podem ser copiados para a lousa privada.")

    target_col = None
    if private_column_id is not None:
        target_col = get_private_column(workspace, user, private_column_id)
    if target_col is None:
        cols = ensure_default_private_columns(workspace, user)
        target_col = cols[0] if cols else None
    if target_col is None:
        raise ValidationError("Não foi possível definir a coluna de destino da cópia privada.")

    next_pos = (
        BoardCard.objects.filter(
            workspace=workspace,
            visibility=BoardCard.Visibility.PRIVATE,
            private_column=target_col,
            created_by=user,
        ).aggregate(m=Max("position"))["m"]
    )
    position = (next_pos if next_pos is not None else -1) + 1

    copied = BoardCard(
        workspace=workspace,
        created_by=user,
        updated_by=user,
        visibility=BoardCard.Visibility.PRIVATE,
        title=card.title,
        description=card.description,
        private_column=target_col,
        public_lane=None,
        position=position,
        category=card.category,
        event_date=card.event_date,
        due_date=card.due_date,
        client_id=card.client_id,
        project_id=card.project_id,
        task_id=card.task_id,
        budget_goal_id=card.budget_goal_id,
        assigned_user_id=card.assigned_user_id,
        assigned_department_id=card.assigned_department_id,
        metadata=card.metadata if isinstance(card.metadata, dict) else {},
        mural_status_id=card.mural_status_id,
        color_key=card.color_key,
    )
    copied.save()
    return copied


def set_members_lane_lock(workspace: Workspace, user: User, *, locked: bool) -> Workspace:
    assert_workspace_member(user, workspace)
    workspace.mural_members_lane_locked = bool(locked)
    workspace.updated_by = user
    workspace.save(update_fields=["mural_members_lane_locked", "updated_by", "updated_at"])
    return workspace


def clear_public_members_lane(workspace: Workspace, user: User) -> int:
    assert_workspace_member(user, workspace)
    cards = list(
        BoardCard.objects.filter(
            workspace=workspace,
            visibility=BoardCard.Visibility.PUBLIC,
            public_lane=BoardCard.PublicLane.MEMBERS,
        )
    )
    total = len(cards)
    for card in cards:
        card.updated_by = user
        card.save(update_fields=["updated_by", "updated_at"])
        card.delete()
    return total
