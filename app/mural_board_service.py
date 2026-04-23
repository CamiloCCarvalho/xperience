"""
Operações de domínio do Mural/Kanban (membro): colunas privadas, cards e reordenação.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Max
from app.models import BoardCard, Membership, PrivateBoardColumn, User, Workspace


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
        "created_at": col.created_at.isoformat(),
        "updated_at": col.updated_at.isoformat(),
    }


def serialize_card(card: BoardCard) -> dict[str, Any]:
    return {
        "id": card.pk,
        "workspace_id": card.workspace_id,
        "visibility": card.visibility,
        "title": card.title,
        "description": card.description,
        "private_column_id": card.private_column_id,
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
    }


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
    data["client_name"] = card.client.name if card.client_id else None
    data["project_name"] = card.project.name if card.project_id else None
    data["task_name"] = card.task.name if card.task_id else None
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


def load_mural_payload(workspace: Workspace, user: User) -> dict[str, Any]:
    assert_workspace_member(user, workspace)
    columns = ensure_default_private_columns(workspace, user)
    public_cards = (
        BoardCard.objects.filter(workspace=workspace, visibility=BoardCard.Visibility.PUBLIC)
        .select_related(
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
        )
        .order_by("position", "pk")
    )
    private_cards = (
        BoardCard.objects.filter(
            workspace=workspace,
            visibility=BoardCard.Visibility.PRIVATE,
            created_by=user,
        )
        .select_related(
            "private_column",
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
        )
        .order_by("private_column", "position", "pk")
    )
    return {
        "workspace_id": workspace.pk,
        "private_columns": [serialize_column(c) for c in columns],
        "public_cards": [serialize_card_ui(c) for c in public_cards],
        "private_cards": [serialize_card_ui(c) for c in private_cards],
    }


def create_private_column(
    workspace: Workspace,
    user: User,
    *,
    name: str,
    position: int | None = None,
) -> PrivateBoardColumn:
    assert_workspace_member(user, workspace)
    name = (name or "").strip()
    if not name:
        raise ValidationError({"name": "Informe o nome da coluna."})
    with transaction.atomic():
        if position is None:
            agg = PrivateBoardColumn.objects.filter(workspace=workspace, user=user).aggregate(
                m=Max("position")
            )
            position = (agg["m"] if agg["m"] is not None else -1) + 1
        col = PrivateBoardColumn(workspace=workspace, user=user, name=name, position=position)
        col.save()
    return col


def rename_private_column(
    workspace: Workspace,
    user: User,
    column_id: int,
    *,
    name: str,
) -> PrivateBoardColumn:
    col = get_private_column(workspace, user, column_id)
    if col is None:
        raise ValidationError("Coluna não encontrada.")
    col.name = name.strip()
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
                .filter(workspace=workspace, visibility=BoardCard.Visibility.PUBLIC)
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


def move_private_card_to_public(workspace: Workspace, user: User, card: BoardCard) -> BoardCard:
    assert_workspace_member(user, workspace)
    if card.workspace_id != workspace.pk:
        raise ValidationError("Card de outro workspace.")
    assert_card_mutation_allowed(card, user)
    if card.visibility != BoardCard.Visibility.PRIVATE:
        raise ValidationError("Apenas cards privados podem ser movidos para a lousa pública.")

    with transaction.atomic():
        live = BoardCard.objects.select_for_update().get(pk=card.pk, workspace=workspace)
        assert_card_mutation_allowed(live, user)
        if live.visibility != BoardCard.Visibility.PRIVATE:
            raise ValidationError("Apenas cards privados podem ser movidos para a lousa pública.")
        public_list = list(
            BoardCard.objects.select_for_update()
            .filter(workspace=workspace, visibility=BoardCard.Visibility.PUBLIC)
            .order_by("position", "pk")
        )
        live.visibility = BoardCard.Visibility.PUBLIC
        live.private_column = None
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
) -> BoardCard:
    assert_workspace_member(user, workspace)
    title = (title or "").strip()
    if not title:
        raise ValidationError({"title": "Informe o título do card."})

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
        next_pos = BoardCard.objects.filter(
            workspace=workspace,
            visibility=BoardCard.Visibility.PUBLIC,
        ).aggregate(m=Max("position"))["m"]
        position = (next_pos if next_pos is not None else -1) + 1
    else:
        raise ValidationError({"visibility": "Visibilidade inválida."})

    card = BoardCard(
        workspace=workspace,
        created_by=user,
        updated_by=user,
        visibility=visibility,
        title=title,
        description=description or "",
        private_column=private_column,
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
    }
    for key in data:
        if key not in allowed:
            continue
        val = data[key]
        if key.endswith("_id"):
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
    col_id = card.private_column_id
    with transaction.atomic():
        card.delete()
        if was_public:
            remaining = list(
                BoardCard.objects.select_for_update()
                .filter(workspace=workspace, visibility=BoardCard.Visibility.PUBLIC)
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
