"""
API JSON mínima do Mural (membro) no workspace ativo da sessão.
"""

from __future__ import annotations

import json
from typing import Any

from django.core.exceptions import PermissionDenied, ValidationError
from django.http import HttpRequest, JsonResponse
from django.views.decorators.http import require_GET, require_http_methods

from app.decorators import member_active_workspace_required, platform_member_required
from app.models import BoardCard, PrivateBoardColumn, User, Workspace
from app.mural_board_service import (
    copy_public_card_to_private,
    create_board_card,
    create_private_column,
    delete_board_card,
    delete_private_column,
    get_board_card_for_member,
    get_private_column,
    load_mural_payload,
    move_private_card_between_columns,
    move_private_card_to_public,
    parse_card_fk_payload,
    rename_private_column,
    reposition_card,
    reorder_private_columns,
    serialize_card,
    serialize_card_ui,
    serialize_column,
    update_board_card,
)


def _json_body(request: HttpRequest) -> dict[str, Any]:
    ct = (request.content_type or "").lower()
    if "application/json" in ct and request.body:
        try:
            raw = json.loads(request.body.decode("utf-8"))
        except json.JSONDecodeError:
            return {}
        return raw if isinstance(raw, dict) else {}
    return {k: v for k, v in request.POST.items()}


def _json_ok(data: dict[str, Any] | None = None, status: int = 200) -> JsonResponse:
    body: dict[str, Any] = {"ok": True}
    if data:
        body.update(data)
    return JsonResponse(body, status=status)


def _json_err(message: str, status: int = 400) -> JsonResponse:
    return JsonResponse({"ok": False, "error": message}, status=status)


def _workspace(request) -> Workspace:
    ws = getattr(request, "active_member_workspace", None)
    assert isinstance(ws, Workspace)
    return ws


def _user(request) -> User:
    u = request.user
    assert isinstance(u, User)
    return u


@platform_member_required
@member_active_workspace_required
@require_GET
def mural_member_data(request: HttpRequest) -> JsonResponse:
    try:
        payload = load_mural_payload(_workspace(request), _user(request))
    except PermissionDenied as e:
        return _json_err(str(e), status=403)
    return _json_ok({"mural": payload})


@platform_member_required
@member_active_workspace_required
@require_http_methods(["POST"])
def mural_member_column_create(request: HttpRequest) -> JsonResponse:
    data = _json_body(request)
    name = data.get("name", "")
    position_raw = data.get("position")
    position: int | None = None
    if position_raw not in (None, ""):
        try:
            position = int(str(position_raw))
        except (TypeError, ValueError):
            return _json_err("position inválido.")
    color_key = data.get("color_key")
    try:
        col = create_private_column(
            _workspace(request),
            _user(request),
            name=str(name),
            position=position,
            color_key=str(color_key).strip() if color_key not in (None, "") else None,
        )
    except PermissionDenied as e:
        return _json_err(str(e), status=403)
    except ValidationError as e:
        msg = e.message_dict.get("name", str(e)) if hasattr(e, "message_dict") else str(e)
        return _json_err(str(msg))
    return _json_ok({"column": serialize_column(col)}, status=201)


@platform_member_required
@member_active_workspace_required
@require_http_methods(["PATCH", "POST"])
def mural_member_column_update(request: HttpRequest, column_id: int) -> JsonResponse:
    data = _json_body(request)
    name = data.get("name")
    if name is None:
        return _json_err("Informe name.")
    try:
        kw: dict[str, Any] = {"name": str(name)}
        if "color_key" in data:
            raw_ck = data.get("color_key")
            kw["color_key"] = str(raw_ck).strip() if raw_ck not in (None, "") else None
        col = rename_private_column(_workspace(request), _user(request), column_id, **kw)
    except PermissionDenied as e:
        return _json_err(str(e), status=403)
    except ValidationError as e:
        if hasattr(e, "message_dict") and e.message_dict:
            first = next(iter(e.message_dict.values()))
            msg = first[0] if isinstance(first, list) else str(first)
        else:
            msg = "; ".join(e.messages) if hasattr(e, "messages") else str(e)
        return _json_err(msg)
    return _json_ok({"column": serialize_column(col)})


@platform_member_required
@member_active_workspace_required
@require_http_methods(["DELETE"])
def mural_member_column_delete(request: HttpRequest, column_id: int) -> JsonResponse:
    try:
        delete_private_column(_workspace(request), _user(request), column_id)
    except PermissionDenied as e:
        return _json_err(str(e), status=403)
    except ValidationError as e:
        return _json_err(str(e))
    return _json_ok()


@platform_member_required
@member_active_workspace_required
@require_http_methods(["POST"])
def mural_member_columns_reorder(request: HttpRequest) -> JsonResponse:
    data = _json_body(request)
    raw_ids = data.get("ordered_column_ids") or data.get("ordered_ids")
    if not isinstance(raw_ids, list):
        return _json_err("ordered_column_ids deve ser uma lista de ids.")
    try:
        ordered = [int(x) for x in raw_ids]
    except (TypeError, ValueError):
        return _json_err("ordered_column_ids deve conter inteiros.")
    try:
        reorder_private_columns(_workspace(request), _user(request), ordered)
    except PermissionDenied as e:
        return _json_err(str(e), status=403)
    except ValidationError as e:
        return _json_err(str(e))
    cols = PrivateBoardColumn.objects.filter(
        workspace=_workspace(request), user=_user(request)
    ).order_by("position", "pk")
    return _json_ok({"private_columns": [serialize_column(c) for c in cols]})


@platform_member_required
@member_active_workspace_required
@require_http_methods(["POST"])
def mural_member_card_create(request: HttpRequest) -> JsonResponse:
    data = _json_body(request)
    visibility = (data.get("visibility") or "").strip()
    title = data.get("title", "")
    fks = parse_card_fk_payload(data)
    try:
        card = create_board_card(
            _workspace(request),
            _user(request),
            visibility=visibility,
            title=str(title),
            private_column_id=fks.get("private_column_id"),
            public_lane=(data.get("public_lane") or None),
            description=str(data.get("description") or ""),
            category=str(data.get("category") or ""),
            event_date=data.get("event_date") or None,
            due_date=data.get("due_date") or None,
            client_id=fks.get("client_id"),
            project_id=fks.get("project_id"),
            task_id=fks.get("task_id"),
            budget_goal_id=fks.get("budget_goal_id"),
            assigned_user_id=fks.get("assigned_user_id"),
            assigned_department_id=fks.get("assigned_department_id"),
            metadata=data.get("metadata") if isinstance(data.get("metadata"), dict) else {},
            mural_status_id=fks.get("mural_status_id"),
            color_key=(
                str(data.get("color_key")).strip()
                if data.get("color_key") not in (None, "")
                else None
            ),
        )
    except PermissionDenied as e:
        return _json_err(str(e), status=403)
    except ValidationError as e:
        if hasattr(e, "message_dict"):
            first = next(iter(e.message_dict.values()))  # type: ignore[attr-defined]
            msg = first[0] if isinstance(first, list) else str(first)
        else:
            msg = str(e)
        return _json_err(msg)
    return _json_ok({"card": serialize_card(card)}, status=201)


@platform_member_required
@member_active_workspace_required
@require_http_methods(["PATCH", "POST"])
def mural_member_card_update(request: HttpRequest, card_id: int) -> JsonResponse:
    ws = _workspace(request)
    user = _user(request)
    card = get_board_card_for_member(ws, user, card_id)
    if card is None:
        return _json_err("Card não encontrado.", status=404)
    data = _json_body(request)
    try:
        update_board_card(ws, user, card, data=data)
    except PermissionDenied as e:
        return _json_err(str(e), status=403)
    except ValidationError as e:
        if hasattr(e, "message_dict"):
            first_key = next(iter(e.message_dict.keys()))
            vals = e.message_dict[first_key]
            msg = vals[0] if isinstance(vals, list) else str(vals)
        else:
            msg = str(e)
        return _json_err(msg)
    card.refresh_from_db()
    return _json_ok({"card": serialize_card(card)})


@platform_member_required
@member_active_workspace_required
@require_http_methods(["DELETE"])
def mural_member_card_delete(request: HttpRequest, card_id: int) -> JsonResponse:
    ws = _workspace(request)
    user = _user(request)
    card = get_board_card_for_member(ws, user, card_id)
    if card is None:
        return _json_err("Card não encontrado.", status=404)
    try:
        delete_board_card(ws, user, card)
    except PermissionDenied as e:
        return _json_err(str(e), status=403)
    except ValidationError as e:
        return _json_err(str(e))
    return _json_ok()


@platform_member_required
@member_active_workspace_required
@require_http_methods(["POST"])
def mural_member_card_move_private(request: HttpRequest, card_id: int) -> JsonResponse:
    ws = _workspace(request)
    user = _user(request)
    card = get_board_card_for_member(ws, user, card_id)
    if card is None:
        return _json_err("Card não encontrado.", status=404)
    data = _json_body(request)
    private_column_raw = data.get("private_column_id")
    try:
        new_column_id = int(str(private_column_raw))
    except (TypeError, ValueError):
        return _json_err("private_column_id inválido.")
    try:
        insert_index = int(str(data.get("insert_index", 0)))
    except (TypeError, ValueError):
        return _json_err("insert_index inválido.")
    try:
        card = move_private_card_between_columns(
            ws,
            user,
            card,
            new_column_id=new_column_id,
            insert_index=insert_index,
        )
    except PermissionDenied as e:
        return _json_err(str(e), status=403)
    except ValidationError as e:
        return _json_err(str(e))
    card = get_board_card_for_member(ws, user, card.pk)
    assert card is not None
    return _json_ok({"card": serialize_card_ui(card)})


@platform_member_required
@member_active_workspace_required
@require_http_methods(["POST"])
def mural_member_card_move_to_public(request: HttpRequest, card_id: int) -> JsonResponse:
    ws = _workspace(request)
    user = _user(request)
    card = get_board_card_for_member(ws, user, card_id)
    if card is None:
        return _json_err("Card não encontrado.", status=404)
    try:
        card = move_private_card_to_public(ws, user, card)
    except PermissionDenied as e:
        return _json_err(str(e), status=403)
    except ValidationError as e:
        return _json_err(str(e))
    return _json_ok({"card": serialize_card(card)})


@platform_member_required
@member_active_workspace_required
@require_http_methods(["POST"])
def mural_member_card_copy_to_private(request: HttpRequest, card_id: int) -> JsonResponse:
    ws = _workspace(request)
    user = _user(request)
    card = get_board_card_for_member(ws, user, card_id)
    if card is None:
        return _json_err("Card não encontrado.", status=404)
    data = _json_body(request)
    private_column_id = data.get("private_column_id")
    try:
        col_id = int(str(private_column_id)) if private_column_id not in (None, "") else None
    except (TypeError, ValueError):
        return _json_err("private_column_id inválido.")
    try:
        copied = copy_public_card_to_private(ws, user, card, private_column_id=col_id)
    except PermissionDenied as e:
        return _json_err(str(e), status=403)
    except ValidationError as e:
        return _json_err(str(e))
    return _json_ok({"card": serialize_card_ui(copied)}, status=201)


@platform_member_required
@member_active_workspace_required
@require_http_methods(["POST"])
def mural_member_card_reposition(request: HttpRequest, card_id: int) -> JsonResponse:
    ws = _workspace(request)
    user = _user(request)
    card = get_board_card_for_member(ws, user, card_id)
    if card is None:
        return _json_err("Card não encontrado.", status=404)
    data = _json_body(request)
    try:
        insert_index = int(str(data.get("insert_index", 0)))
    except (TypeError, ValueError):
        return _json_err("insert_index inválido.")
    try:
        reposition_card(ws, user, card, insert_index=insert_index)
    except PermissionDenied as e:
        return _json_err(str(e), status=403)
    except ValidationError as e:
        return _json_err(str(e))
    card.refresh_from_db()
    return _json_ok({"card": serialize_card(card)})
