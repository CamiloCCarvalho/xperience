/**
 * Mural do membro: renderização, drag-and-drop e CRUD via API JSON.
 */
(function () {
    "use strict";

    /** @type {HTMLElement | null} */
    let root = null;
    /** @type {Record<string, unknown> | null} */
    let mural = null;
    /** @type {Record<string, unknown> | null} */
    let ui = null;

    /** @type {{ id: number, visibility: string, privateColumnId: number | null, publicLane: string | null, createdById: number } | null} */
    let dragCard = null;
    /** @type {number | null} */
    let dragColumnId = null;

    function qs(id) {
        return document.getElementById(id);
    }

    function readJsonScript(id) {
        const el = qs(id);
        if (!el || !el.textContent) return null;
        try {
            return JSON.parse(el.textContent);
        } catch (_) {
            return null;
        }
    }

    function getCsrf() {
        const h = qs("member-mural-csrf");
        return h ? h.value : "";
    }

    /**
     * @param {string} url
     * @param {RequestInit} [options]
     */
    async function apiJson(url, options) {
        const method = (options && options.method) || "GET";
        const isWrite = ["POST", "PUT", "PATCH", "DELETE"].includes(method.toUpperCase());
        /** @type {Record<string, string>} */
        const headers = {};
        if (isWrite) {
            headers["X-CSRFToken"] = getCsrf();
            headers["Content-Type"] = "application/json";
        }
        const res = await fetch(url, Object.assign({}, options, { headers: Object.assign(headers, (options && options.headers) || {}) }));
        const body = await res.json().catch(function () {
            return {};
        });
        if (!res.ok || body.ok === false) {
            const msg = typeof body.error === "string" ? body.error : "Erro " + res.status;
            throw new Error(msg);
        }
        return body;
    }

    function esc(s) {
        const d = document.createElement("div");
        d.textContent = s == null ? "" : String(s);
        return d.innerHTML;
    }

    function fmtDate(iso) {
        if (!iso) return "—";
        try {
            const d = new Date(String(iso));
            if (Number.isNaN(d.getTime())) return String(iso).slice(0, 10);
            return d.toLocaleDateString("pt-BR", { day: "2-digit", month: "short", year: "numeric" });
        } catch (_) {
            return "—";
        }
    }

    function fmtDateInput(iso) {
        if (!iso) return "";
        return String(iso).slice(0, 10);
    }

    /**
     * @param {string} tpl
     * @param {string} key
     * @param {number} id
     */
    function urlFrom(tpl, key, id) {
        return tpl.replace("{" + key + "}", String(id));
    }

    function currentUserId() {
        return Number(ui && ui.currentUserId) || 0;
    }

    function isAdminBoard() {
        return Boolean(ui && ui.isAdminBoard);
    }

    /**
     * @returns {Record<string, string>}
     */
    function paletteHexByKey() {
        const out = /** @type {Record<string, string>} */ ({});
        const pal = /** @type {{key:string, hex:string}[]} */ ((ui && ui.colorPalette) || []);
        pal.forEach(function (p) {
            out[p.key] = p.hex;
        });
        return out;
    }

    /**
     * @param {string | null | undefined} hex
     */
    function cardAccentStyle(hex) {
        const h = hex && String(hex).trim();
        if (!h) return "";
        return ' style="--mural-accent:' + esc(h) + ";border-left:4px solid " + esc(h) + ';"';
    }

    /**
     * @param {Record<string, unknown>} card
     */
    function canMutateCard(card) {
        return Number(card.created_by_id) === currentUserId();
    }

    function publicLaneLabel(lane) {
        return lane === "management" ? "Gestão" : "Membros";
    }

    /**
     * @param {HTMLElement} container
     * @param {number} clientY
     */
    function insertIndexFromPointer(container, clientY) {
        const cards = container.querySelectorAll("[data-card-id]");
        for (let i = 0; i < cards.length; i++) {
            const el = cards[i];
            const r = el.getBoundingClientRect();
            const mid = r.top + r.height / 2;
            if (clientY < mid) return i;
        }
        return cards.length;
    }

    function clearDragOver() {
        if (!root) return;
        root.querySelectorAll(".member-mural--dragover").forEach(function (el) {
            el.classList.remove("member-mural--dragover");
        });
    }

    async function syncMuralFromServer() {
        if (!ui) return;
        const urls = /** @type {Record<string, string>} */ (ui.urls || {});
        const data = await apiJson(urls.muralData, { method: "GET" });
        mural = /** @type {Record<string, unknown>} */ (data.mural);
        render();
    }

    /**
     * @param {Record<string, unknown>} card
     * @param {boolean} isPublicBoard
     */
    function renderCardHtml(card, isPublicBoard) {
        const id = Number(card.id);
        const vis = String(card.visibility || "");
        const colId = card.private_column_id == null ? "" : String(card.private_column_id);
        const publicLane = card.public_lane ? String(card.public_lane) : "";
        const createdBy = Number(card.created_by_id);
        const mutable = canMutateCard(card);
        const draggable = vis === "private" || (vis === "public" && (mutable || isAdminBoard()));
        const title = esc(card.title);
        const desc = esc((card.description && String(card.description).trim()) || "");
        const cat = card.category ? '<span class="member-mural-pill">' + esc(card.category) + "</span>" : "";
        const accentHex = card.color_hex || card.mural_status_color_hex || null;
        const accentAttr = cardAccentStyle(accentHex ? String(accentHex) : "");
        const statusName = card.mural_status_name ? String(card.mural_status_name) : "";
        const statusHex = card.mural_status_color_hex ? String(card.mural_status_color_hex) : "";
        const statusInactive = card.mural_status_is_active === false;
        const statusPill =
            statusName !== ""
                ? '<span class="member-mural-pill member-mural-pill--status" style="border-color:' +
                  esc(statusHex) +
                  ";color:" +
                  esc(statusHex) +
                  '">' +
                  esc(statusName) +
                  (statusInactive ? " (inativo)" : "") +
                  "</span>"
                : "";
        const created = fmtDate(card.created_at);
        const eventD = card.event_date ? fmtDate(card.event_date) : "";
        const dueD = card.due_date ? fmtDate(card.due_date) : "";
        const dateBits = [];
        if (eventD) dateBits.push("Evento: " + esc(eventD));
        if (dueD) dateBits.push("Prazo: " + esc(dueD));

        let extra = "";
        if (isPublicBoard) {
            const avatar = card.creator_avatar_url ? String(card.creator_avatar_url) : "";
            const creatorLabel = card.creator_label ? esc(card.creator_label) : "—";
            const lines = [];
            if (card.client_name) lines.push("<div><strong>Cliente</strong> · " + esc(card.client_name) + "</div>");
            if (card.project_name) lines.push("<div><strong>Projeto</strong> · " + esc(card.project_name) + "</div>");
            if (card.task_name) lines.push("<div><strong>Tarefa</strong> · " + esc(card.task_name) + "</div>");
            if (card.budget_goal_label) lines.push("<div><strong>Meta</strong> · " + esc(card.budget_goal_label) + "</div>");
            if (card.assigned_user_label) lines.push("<div><strong>Membro</strong> · " + esc(card.assigned_user_label) + "</div>");
            if (card.assigned_department_name) {
                lines.push("<div><strong>Depto</strong> · " + esc(card.assigned_department_name) + "</div>");
            }
            const img = avatar
                ? '<img src="' + esc(avatar) + '" alt="" width="28" height="28" loading="lazy" />'
                : '<span class="member-mural-pill" style="width:28px;height:28px;display:inline-flex;align-items:center;justify-content:center;">?</span>';
            extra =
                '<div class="member-mural-card__public-extra">' +
                '<div class="member-mural-card__creator">' +
                img +
                "<span>" +
                creatorLabel +
                "</span>" +
                '<button type="button" class="member-mural-icon-btn" data-action="copy-public-to-private" data-card-id="' +
                id +
                '" title="Copiar para minha lousa">⧉</button>' +
                "</div>" +
                (lines.length ? '<div class="member-mural-card__meta" style="flex-direction:column;align-items:flex-start">' + lines.join("") + "</div>" : "") +
                "</div>";
        }

        const roClass = !draggable ? " member-mural-card--readonly" : "";
        const dragAttr = draggable ? ' draggable="true"' : "";

        return (
            '<article class="member-mural-card' +
            roClass +
            '" role="button" tabindex="0" data-action="open-card" data-card-id="' +
            id +
            '" data-visibility="' +
            esc(vis) +
            '" data-private-column-id="' +
            esc(colId) +
            '" data-public-lane="' +
            esc(publicLane) +
            '" data-created-by-id="' +
            createdBy +
            '"' +
            accentAttr +
            dragAttr +
            ">" +
            '<p class="member-mural-card__title">' +
            title +
            "</p>" +
            (desc ? '<p class="member-mural-card__desc">' + desc + "</p>" : "") +
            '<div class="member-mural-card__meta">' +
            cat +
            (cat ? " " : "") +
            (statusPill ? statusPill + " " : "") +
            "<span>Criado " +
            esc(created) +
            "</span>" +
            (dateBits.length ? " · " + dateBits.map(esc).join(" · ") : "") +
            "</div>" +
            extra +
            "</article>"
        );
    }

    function renderMuralStatusAdminHtml() {
        if (!isAdminBoard() || !mural) return "";
        const all = /** @type {Record<string, unknown>[]} */ (mural.mural_statuses_all || []);
        const rows =
            all.length === 0
                ? '<p class="member-mural-empty">Nenhum status configurado.</p>'
                : all
                      .map(function (s) {
                          const sid = Number(s.id);
                          const nm = esc(s.name);
                          const hx = s.color_hex ? String(s.color_hex) : "#ccc";
                          const act = Boolean(s.is_active);
                          return (
                              '<div class="member-mural-status-row" data-status-id="' +
                              sid +
                              '">' +
                              '<span style="width:12px;height:12px;border-radius:2px;background:' +
                              esc(hx) +
                              ';flex-shrink:0"></span>' +
                              '<span class="member-mural-status-row__name">' +
                              nm +
                              "</span>" +
                              (act
                                  ? '<span class="member-mural-pill">Ativo</span>'
                                  : '<span class="member-mural-pill member-mural-pill--warn">Inativo</span>') +
                              '<button type="button" class="member-mural-btn member-mural-btn--small member-mural-btn--ghost" data-action="mural-status-edit" data-status-id="' +
                              sid +
                              '">Editar</button>' +
                              '<button type="button" class="member-mural-btn member-mural-btn--small member-mural-btn--ghost" data-action="mural-status-up" data-status-id="' +
                              sid +
                              '">↑</button>' +
                              '<button type="button" class="member-mural-btn member-mural-btn--small member-mural-btn--ghost" data-action="mural-status-down" data-status-id="' +
                              sid +
                              '">↓</button>' +
                              '<button type="button" class="member-mural-btn member-mural-btn--small member-mural-btn--ghost" data-action="mural-status-toggle" data-status-id="' +
                              sid +
                              '">' +
                              (act ? "Desativar" : "Ativar") +
                              "</button>" +
                              "</div>"
                          );
                      })
                      .join("");
        return (
            '<article class="spaceon-card member-mural-board dash-dashboard-card member-mural-status-admin">' +
            '<header class="dash-header">' +
            '<div class="dash-title-wrap">' +
            '<i class="fas fa-tags" aria-hidden="true"></i>' +
            "<h2>Status do mural</h2>" +
            "</div>" +
            '<div class="member-mural-board__actions">' +
            '<button type="button" class="member-mural-btn member-mural-btn--small member-mural-btn--primary" data-action="mural-status-add">Novo status</button>' +
            "</div>" +
            "</header>" +
            '<div class="member-mural-board__body"><div class="member-mural-status-admin__list">' +
            rows +
            "</div></div></article>"
        );
    }

    function render() {
        if (!root || !mural || !ui) return;
        const publicCardsByLane = /** @type {Record<string, Record<string, unknown>[]>} */ (mural.public_cards_by_lane || {});
        const membersCards = /** @type {Record<string, unknown>[]} */ (publicCardsByLane.members || []);
        const managementCards = /** @type {Record<string, unknown>[]} */ (publicCardsByLane.management || []);
        const privateCols = /** @type {Record<string, unknown>[]} */ (mural.private_columns || []);
        const privateCards = /** @type {Record<string, unknown>[]} */ (mural.private_cards || []);

        function laneListHtml(cards, lane) {
            return cards.length === 0
                ? '<p class="member-mural-empty">Nenhum card na coluna ' + publicLaneLabel(lane) + ".</p>"
                : cards.map(function (c) {
                      return renderCardHtml(c, true);
                  }).join("");
        }
        const pubListMembers = laneListHtml(membersCards, "members");
        const pubListManagement = laneListHtml(managementCards, "management");
        const membersLaneLocked = Boolean(mural.members_lane_locked);
        const createPublicLabel = isAdminBoard() ? "Novo público (Gestão)" : "Novo público";
        const membersModerationHtml = isAdminBoard()
            ? '<div class="member-mural-public__moderation">' +
              '<button type="button" class="member-mural-btn member-mural-btn--small member-mural-btn--ghost" data-action="toggle-members-lock">' +
              (membersLaneLocked ? "Desbloquear" : "Bloquear") +
              "</button>" +
              '<button type="button" class="member-mural-btn member-mural-btn--small member-mural-btn--danger" data-action="clear-members-lane">Excluir todos</button>' +
              "</div>"
            : "";
        const membersLockBadge = membersLaneLocked
            ? '<span class="member-mural-pill member-mural-pill--warn">Bloqueada para membros</span>'
            : "";

        const colsHtml = privateCols
            .map(function (col) {
                const cid = Number(col.id);
                const cHex = col.color_hex ? String(col.color_hex) : "";
                const colAccent = cHex ? ' style="border-left:4px solid ' + esc(cHex) + ';"' : "";
                const cardsInCol = privateCards.filter(function (c) {
                    return Number(c.private_column_id) === cid;
                });
                const cardsHtml =
                    cardsInCol.length === 0
                        ? '<p class="member-mural-empty">Vazio — arraste cards ou crie um novo.</p>'
                        : cardsInCol.map(function (c) {
                              return renderCardHtml(c, false);
                          }).join("");
                return (
                    '<section class="member-mural-column" data-column-id="' +
                    cid +
                    '"' +
                    colAccent +
                    ">" +
                    '<header class="member-mural-column__head" draggable="true" data-column-drag="' +
                    cid +
                    '">' +
                    '<p class="member-mural-column__title">' +
                    esc(col.name) +
                    "</p>" +
                    '<button type="button" class="member-mural-icon-btn" data-action="add-card" data-column-id="' +
                    cid +
                    '" title="Novo card">+</button>' +
                    '<button type="button" class="member-mural-icon-btn" data-action="rename-column" data-column-id="' +
                    cid +
                    '" title="Renomear">✎</button>' +
                    '<button type="button" class="member-mural-icon-btn" data-action="delete-column" data-column-id="' +
                    cid +
                    '" title="Excluir coluna">🗑</button>' +
                    "</header>" +
                    '<div class="member-mural-column__cards" data-mural-drop="private" data-column-id="' +
                    cid +
                    '">' +
                    cardsHtml +
                    "</div>" +
                    "</section>"
                );
            })
            .join("");

        root.innerHTML =
            '<article class="spaceon-card member-mural-board dash-dashboard-card">' +
            '<header class="dash-header">' +
            '<div class="dash-title-wrap">' +
            '<i class="fas fa-bullhorn" aria-hidden="true"></i>' +
            "<h2>Lousa pública</h2>" +
            "</div>" +
            '<div class="member-mural-board__actions">' +
            '<button type="button" class="member-mural-btn member-mural-btn--small member-mural-btn--primary" data-action="create-public-card">' + createPublicLabel + "</button>" +
            "</div>" +
            "</header>" +
            '<div class="member-mural-board__body">' +
            '<div class="member-mural-public" data-mural-public-wrap>' +
            '<section class="member-mural-public__lane" data-public-lane="members">' +
            '<header class="member-mural-public__lane-head"><h3>Membros</h3>' + membersLockBadge + membersModerationHtml + "</header>" +
            '<div class="member-mural-public__list" data-mural-drop="public" data-public-lane="members" data-mural-card-list>' +
            pubListMembers +
            "</div>" +
            "</section>" +
            '<section class="member-mural-public__lane" data-public-lane="management">' +
            '<header class="member-mural-public__lane-head"><h3>Gestão</h3></header>' +
            '<div class="member-mural-public__list" data-mural-drop="public" data-public-lane="management" data-mural-card-list>' +
            pubListManagement +
            "</div>" +
            "</section>" +
            "</div>" +
            "</div>" +
            "</article>" +
            renderMuralStatusAdminHtml() +
            '<article class="spaceon-card member-mural-board dash-dashboard-card">' +
            '<header class="dash-header">' +
            '<div class="dash-title-wrap">' +
            '<i class="fas fa-columns" aria-hidden="true"></i>' +
            "<h2>Lousa privada</h2>" +
            "</div>" +
            '<div class="member-mural-board__actions">' +
            '<button type="button" class="member-mural-btn member-mural-btn--small member-mural-btn--ghost" data-action="create-column">Nova coluna</button>' +
            "</div>" +
            "</header>" +
            '<div class="member-mural-board__body">' +
            '<div class="member-mural-private__columns">' +
            colsHtml +
            "</div>" +
            "</div>" +
            "</article>";
    }

    function fillMetaSelects() {
        if (!ui) return;
        const clients = /** @type {{id:number,name:string}[]} */ (ui.clients || []);
        const projects = /** @type {{id:number,name:string,client_id:number|null}[]} */ (ui.projects || []);
        const tasks = /** @type {{id:number,name:string,project_id:number}[]} */ (ui.tasks || []);
        const goals = /** @type {{id:number,name:string}[]} */ (ui.budgetGoals || []);
        const members = /** @type {{id:number,label:string}[]} */ (ui.members || []);
        const depts = /** @type {{id:number,name:string}[]} */ (ui.departments || []);

        function fill(sel, items, labelKey) {
            if (!sel) return;
            const keep = sel.querySelector('option[value=""]');
            sel.innerHTML = "";
            if (keep) sel.appendChild(keep);
            else {
                const o = document.createElement("option");
                o.value = "";
                o.textContent = "—";
                sel.appendChild(o);
            }
            items.forEach(function (it) {
                const opt = document.createElement("option");
                opt.value = String(it.id);
                opt.textContent = it[labelKey] || it.name || it.label || String(it.id);
                opt.dataset.clientId = it.client_id != null ? String(it.client_id) : "";
                opt.dataset.projectId = it.project_id != null ? String(it.project_id) : "";
                sel.appendChild(opt);
            });
        }

        fill(/** @type {HTMLSelectElement | null} */ (qs("member-mural-card-client")), clients, "name");
        fill(/** @type {HTMLSelectElement | null} */ (qs("member-mural-card-project")), projects, "name");
        fill(/** @type {HTMLSelectElement | null} */ (qs("member-mural-card-task")), tasks, "name");
        fill(/** @type {HTMLSelectElement | null} */ (qs("member-mural-card-goal")), goals, "name");
        fill(/** @type {HTMLSelectElement | null} */ (qs("member-mural-card-assign-user")), members, "label");
        fill(/** @type {HTMLSelectElement | null} */ (qs("member-mural-card-assign-dept")), depts, "name");
        fillMuralPaletteSelects();
    }

    /**
     * @param {HTMLSelectElement | null} sel
     * @param {boolean} includeEmpty
     */
    function fillPaletteSelectElement(sel, includeEmpty) {
        if (!sel || !ui) return;
        const pal = /** @type {{key:string, hex:string}[]} */ (ui.colorPalette || []);
        const cur = sel.value;
        sel.innerHTML = "";
        if (includeEmpty) {
            const o0 = document.createElement("option");
            o0.value = "";
            o0.textContent = "Padrão";
            sel.appendChild(o0);
        }
        pal.forEach(function (p) {
            const o = document.createElement("option");
            o.value = p.key;
            o.textContent = p.key;
            o.style.color = "#fff";
            o.style.backgroundColor = p.hex;
            sel.appendChild(o);
        });
        if (cur && [...sel.options].some(function (x) { return x.value === cur; })) sel.value = cur;
    }

    function fillMuralPaletteSelects() {
        fillPaletteSelectElement(/** @type {HTMLSelectElement | null} */ (qs("member-mural-card-color-key")), true);
        fillPaletteSelectElement(/** @type {HTMLSelectElement | null} */ (qs("member-mural-column-color-key")), true);
        fillPaletteSelectElement(/** @type {HTMLSelectElement | null} */ (qs("member-mural-status-color-key")), false);
    }

    /**
     * @param {Record<string, unknown> | null} card
     */
    function fillMuralStatusSelectForCard(card) {
        const sel = /** @type {HTMLSelectElement | null} */ (qs("member-mural-card-mural-status"));
        if (!sel) return;
        const cur = card && card.mural_status_id != null ? String(card.mural_status_id) : "";
        const base = /** @type {Record<string, unknown>[]} */ ((mural && mural.mural_statuses) || []);
        sel.innerHTML = "";
        const o0 = document.createElement("option");
        o0.value = "";
        o0.textContent = "—";
        sel.appendChild(o0);
        base.forEach(function (s) {
            const opt = document.createElement("option");
            opt.value = String(s.id);
            opt.textContent = String(s.name);
            sel.appendChild(opt);
        });
        if (cur) {
            const inBase = base.some(function (s) {
                return String(s.id) === cur;
            });
            if (!inBase && card && card.mural_status_name) {
                const ox = document.createElement("option");
                ox.value = cur;
                ox.textContent = String(card.mural_status_name) + " (inativo)";
                sel.appendChild(ox);
            }
            sel.value = cur;
        }
    }

    function filterProjectsByClient() {
        const cSel = /** @type {HTMLSelectElement | null} */ (qs("member-mural-card-client"));
        const pSel = /** @type {HTMLSelectElement | null} */ (qs("member-mural-card-project"));
        if (!cSel || !pSel || !ui) return;
        const cid = cSel.value;
        const projects = /** @type {{id:number,name:string,client_id:number|null}[]} */ (ui.projects || []);
        const cur = pSel.value;
        pSel.innerHTML = "";
        const o0 = document.createElement("option");
        o0.value = "";
        o0.textContent = "—";
        pSel.appendChild(o0);
        projects.forEach(function (p) {
            if (cid && String(p.client_id) !== cid) return;
            const opt = document.createElement("option");
            opt.value = String(p.id);
            opt.textContent = p.name;
            pSel.appendChild(opt);
        });
        if (cur && [...pSel.options].some(function (o) { return o.value === cur; })) pSel.value = cur;
    }

    function filterTasksByProject() {
        const pSel = /** @type {HTMLSelectElement | null} */ (qs("member-mural-card-project"));
        const tSel = /** @type {HTMLSelectElement | null} */ (qs("member-mural-card-task"));
        if (!pSel || !tSel || !ui) return;
        const pid = pSel.value;
        const tasks = /** @type {{id:number,name:string,project_id:number}[]} */ (ui.tasks || []);
        const cur = tSel.value;
        tSel.innerHTML = "";
        const o0 = document.createElement("option");
        o0.value = "";
        o0.textContent = "—";
        tSel.appendChild(o0);
        tasks.forEach(function (t) {
            if (pid && String(t.project_id) !== pid) return;
            const opt = document.createElement("option");
            opt.value = String(t.id);
            opt.textContent = t.name;
            tSel.appendChild(opt);
        });
        if (cur && [...tSel.options].some(function (o) { return o.value === cur; })) tSel.value = cur;
    }

    /**
     * @param {string} mode
     * @param {Record<string, unknown> | null} card
     * @param {string} visibility
     * @param {number | null} defaultColumnId
     */
    function openCardDialog(mode, card, visibility, defaultColumnId) {
        const dlg = /** @type {HTMLDialogElement | null} */ (qs("member-mural-card-dialog"));
        const titleEl = qs("member-mural-card-dialog-title");
        const idEl = /** @type {HTMLInputElement | null} */ (qs("member-mural-card-id"));
        const modeEl = /** @type {HTMLInputElement | null} */ (qs("member-mural-card-mode"));
        const defCol = /** @type {HTMLInputElement | null} */ (qs("member-mural-card-default-column"));
        const delBtn = qs("member-mural-card-delete");
        if (!dlg || !idEl || !modeEl || !defCol || !titleEl) return;

        modeEl.value = mode;
        defCol.value = defaultColumnId != null ? String(defaultColumnId) : "";
        const del = /** @type {HTMLButtonElement | null} */ (delBtn);
        if (del) {
            del.hidden = mode !== "edit";
            del.disabled = mode !== "edit";
        }

        if (mode === "create") {
            titleEl.textContent = visibility === "public" ? "Novo card público" : "Novo card privado";
            idEl.value = "";
            [
                "member-mural-card-title",
                "member-mural-card-description",
                "member-mural-card-category",
                "member-mural-card-event-date",
                "member-mural-card-due-date",
                "member-mural-card-client",
                "member-mural-card-project",
                "member-mural-card-task",
                "member-mural-card-goal",
                "member-mural-card-assign-user",
                "member-mural-card-assign-dept",
                "member-mural-card-mural-status",
                "member-mural-card-color-key",
            ].forEach(function (fid) {
                const el = /** @type {HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement | null} */ (qs(fid));
                if (!el) return;
                el.readOnly = false;
                el.disabled = false;
            });
            const saveBtn = /** @type {HTMLButtonElement | null} */ (qs("member-mural-card-save"));
            if (saveBtn) saveBtn.hidden = false;
            /** @type {HTMLInputElement | null} */ (qs("member-mural-card-title")).value = "";
            /** @type {HTMLTextAreaElement | null} */ (qs("member-mural-card-description")).value = "";
            /** @type {HTMLInputElement | null} */ (qs("member-mural-card-category")).value = "";
            /** @type {HTMLInputElement | null} */ (qs("member-mural-card-event-date")).value = "";
            /** @type {HTMLInputElement | null} */ (qs("member-mural-card-due-date")).value = "";
            /** @type {HTMLSelectElement | null} */ (qs("member-mural-card-client")).value = "";
            /** @type {HTMLSelectElement | null} */ (qs("member-mural-card-project")).value = "";
            filterProjectsByClient();
            /** @type {HTMLSelectElement | null} */ (qs("member-mural-card-task")).value = "";
            filterTasksByProject();
            /** @type {HTMLSelectElement | null} */ (qs("member-mural-card-goal")).value = "";
            /** @type {HTMLSelectElement | null} */ (qs("member-mural-card-assign-user")).value = "";
            /** @type {HTMLSelectElement | null} */ (qs("member-mural-card-assign-dept")).value = "";
            fillMuralPaletteSelects();
            fillMuralStatusSelectForCard(null);
            const ckNew = /** @type {HTMLSelectElement | null} */ (qs("member-mural-card-color-key"));
            if (ckNew) ckNew.value = "";
            dlg.dataset.visibility = visibility;
        } else if (card) {
            titleEl.textContent = canMutateCard(card) ? "Editar card" : "Detalhes do card";
            [
                "member-mural-card-title",
                "member-mural-card-description",
                "member-mural-card-category",
                "member-mural-card-event-date",
                "member-mural-card-due-date",
                "member-mural-card-client",
                "member-mural-card-project",
                "member-mural-card-task",
                "member-mural-card-goal",
                "member-mural-card-assign-user",
                "member-mural-card-assign-dept",
                "member-mural-card-mural-status",
                "member-mural-card-color-key",
            ].forEach(function (fid) {
                const el = /** @type {HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement | null} */ (qs(fid));
                if (!el) return;
                el.readOnly = false;
                el.disabled = false;
            });
            idEl.value = String(card.id);
            dlg.dataset.visibility = String(card.visibility);
            /** @type {HTMLInputElement | null} */ (qs("member-mural-card-title")).value = String(card.title || "");
            /** @type {HTMLTextAreaElement | null} */ (qs("member-mural-card-description")).value = String(
                card.description || ""
            );
            /** @type {HTMLInputElement | null} */ (qs("member-mural-card-category")).value = String(card.category || "");
            /** @type {HTMLInputElement | null} */ (qs("member-mural-card-event-date")).value = fmtDateInput(
                /** @type {string} */ (card.event_date)
            );
            /** @type {HTMLInputElement | null} */ (qs("member-mural-card-due-date")).value = fmtDateInput(
                /** @type {string} */ (card.due_date)
            );
            /** @type {HTMLSelectElement | null} */ (qs("member-mural-card-client")).value = card.client_id
                ? String(card.client_id)
                : "";
            filterProjectsByClient();
            /** @type {HTMLSelectElement | null} */ (qs("member-mural-card-project")).value = card.project_id
                ? String(card.project_id)
                : "";
            filterTasksByProject();
            /** @type {HTMLSelectElement | null} */ (qs("member-mural-card-task")).value = card.task_id
                ? String(card.task_id)
                : "";
            /** @type {HTMLSelectElement | null} */ (qs("member-mural-card-goal")).value = card.budget_goal_id
                ? String(card.budget_goal_id)
                : "";
            /** @type {HTMLSelectElement | null} */ (qs("member-mural-card-assign-user")).value = card.assigned_user_id
                ? String(card.assigned_user_id)
                : "";
            /** @type {HTMLSelectElement | null} */ (qs("member-mural-card-assign-dept")).value = card.assigned_department_id
                ? String(card.assigned_department_id)
                : "";
            fillMuralPaletteSelects();
            fillMuralStatusSelectForCard(card);
            const ckEd = /** @type {HTMLSelectElement | null} */ (qs("member-mural-card-color-key"));
            if (ckEd) ckEd.value = card.color_key ? String(card.color_key) : "";
            const readOnly = !canMutateCard(card);
            ["member-mural-card-title", "member-mural-card-description", "member-mural-card-category"].forEach(function (id) {
                const el = /** @type {HTMLInputElement | HTMLTextAreaElement | null} */ (qs(id));
                if (el) el.readOnly = readOnly;
            });
            [
                "member-mural-card-event-date",
                "member-mural-card-due-date",
                "member-mural-card-client",
                "member-mural-card-project",
                "member-mural-card-task",
                "member-mural-card-goal",
                "member-mural-card-assign-user",
                "member-mural-card-assign-dept",
                "member-mural-card-mural-status",
                "member-mural-card-color-key",
            ].forEach(function (id) {
                const el = /** @type {HTMLInputElement | HTMLSelectElement | null} */ (qs(id));
                if (el) el.disabled = readOnly;
            });
            const saveBtn = /** @type {HTMLButtonElement | null} */ (qs("member-mural-card-save"));
            if (saveBtn) saveBtn.hidden = readOnly;
            if (del) del.hidden = readOnly || mode !== "edit";
        }
        dlg.showModal();
    }

    function closeCardDialog() {
        const dlg = /** @type {HTMLDialogElement | null} */ (qs("member-mural-card-dialog"));
        if (dlg) dlg.close();
    }

    /**
     * @param {string} mode
     * @param {number | null} columnId
     * @param {string} name
     * @param {string} [colorKey]
     */
    function openColumnDialog(mode, columnId, name, colorKey) {
        const dlg = /** @type {HTMLDialogElement | null} */ (qs("member-mural-column-dialog"));
        const title = qs("member-mural-column-dialog-title");
        const idEl = /** @type {HTMLInputElement | null} */ (qs("member-mural-column-id"));
        const nameEl = /** @type {HTMLInputElement | null} */ (qs("member-mural-column-name"));
        const csel = /** @type {HTMLSelectElement | null} */ (qs("member-mural-column-color-key"));
        if (!dlg || !idEl || !nameEl || !title) return;
        dlg.dataset.mode = mode;
        idEl.value = columnId != null ? String(columnId) : "";
        nameEl.value = name || "";
        if (csel) {
            fillPaletteSelectElement(csel, true);
            csel.value = colorKey && paletteHexByKey()[colorKey] ? colorKey : "";
        }
        title.textContent = mode === "create" ? "Nova coluna" : "Renomear coluna";
        dlg.showModal();
    }

    function closeColumnDialog() {
        const dlg = /** @type {HTMLDialogElement | null} */ (qs("member-mural-column-dialog"));
        if (dlg) dlg.close();
    }

    /**
     * @param {string} mode
     * @param {Record<string, unknown> | null} st
     */
    function openStatusDialog(mode, st) {
        const dlg = /** @type {HTMLDialogElement | null} */ (qs("member-mural-status-dialog"));
        const title = qs("member-mural-status-dialog-title");
        const idEl = /** @type {HTMLInputElement | null} */ (qs("member-mural-status-id"));
        const modeEl = /** @type {HTMLInputElement | null} */ (qs("member-mural-status-mode"));
        const nameEl = /** @type {HTMLInputElement | null} */ (qs("member-mural-status-name"));
        const csel = /** @type {HTMLSelectElement | null} */ (qs("member-mural-status-color-key"));
        if (!dlg || !title || !idEl || !modeEl || !nameEl) return;
        modeEl.value = mode;
        fillPaletteSelectElement(csel, false);
        if (mode === "create") {
            title.textContent = "Novo status";
            idEl.value = "";
            nameEl.value = "";
            if (csel && csel.options.length) csel.selectedIndex = 0;
        } else if (st) {
            title.textContent = "Editar status";
            idEl.value = String(st.id);
            nameEl.value = String(st.name || "");
            if (csel && st.color_key) csel.value = String(st.color_key);
        }
        dlg.showModal();
    }

    function closeStatusDialog() {
        const dlg = /** @type {HTMLDialogElement | null} */ (qs("member-mural-status-dialog"));
        if (dlg) dlg.close();
    }

    async function saveStatusFromForm() {
        if (!ui) return;
        const urls = /** @type {Record<string, string>} */ (ui.urls || {});
        const mode = /** @type {HTMLInputElement | null} */ (qs("member-mural-status-mode")).value;
        const idVal = /** @type {HTMLInputElement | null} */ (qs("member-mural-status-id")).value;
        const name = /** @type {HTMLInputElement | null} */ (qs("member-mural-status-name")).value.trim();
        const ck = /** @type {HTMLSelectElement | null} */ (qs("member-mural-status-color-key"));
        const color_key = ck && ck.value ? ck.value : "";
        if (!name) {
            window.alert("Informe o nome.");
            return;
        }
        if (!color_key) {
            window.alert("Selecione uma cor.");
            return;
        }
        try {
            if (mode === "create") {
                await apiJson(urls.statusCreate, {
                    method: "POST",
                    body: JSON.stringify({ name: name, color_key: color_key }),
                });
            } else {
                const sid = Number(idVal);
                await apiJson(urlFrom(urls.statusUpdate, "statusId", sid), {
                    method: "PATCH",
                    body: JSON.stringify({ name: name, color_key: color_key }),
                });
            }
            closeStatusDialog();
            await syncMuralFromServer();
        } catch (e) {
            window.alert(e instanceof Error ? e.message : String(e));
        }
    }

    /**
     * @param {number} statusId
     * @param {number} delta
     */
    async function moveStatusByDelta(statusId, delta) {
        if (!ui || !mural) return;
        const urls = /** @type {Record<string, string>} */ (ui.urls || {});
        const all = /** @type {Record<string, unknown>[]} */ (mural.mural_statuses_all || []);
        const ids = all.map(function (s) {
            return Number(s.id);
        });
        const idx = ids.indexOf(statusId);
        if (idx < 0) return;
        const j = idx + delta;
        if (j < 0 || j >= ids.length) return;
        const next = ids.slice();
        const t = next[idx];
        next[idx] = next[j];
        next[j] = t;
        try {
            await apiJson(urls.statusReorder, { method: "POST", body: JSON.stringify({ ordered_status_ids: next }) });
            await syncMuralFromServer();
        } catch (e) {
            window.alert(e instanceof Error ? e.message : String(e));
        }
    }

    async function saveCardFromForm() {
        if (!ui) return;
        const urls = /** @type {Record<string, string>} */ (ui.urls || {});
        const dlg = /** @type {HTMLDialogElement | null} */ (qs("member-mural-card-dialog"));
        const mode = /** @type {HTMLInputElement | null} */ (qs("member-mural-card-mode")).value;
        const idVal = /** @type {HTMLInputElement | null} */ (qs("member-mural-card-id")).value;
        const visibility = dlg ? String(dlg.dataset.visibility || "private") : "private";
        const msEl = /** @type {HTMLSelectElement | null} */ (qs("member-mural-card-mural-status"));
        const cardCkEl = /** @type {HTMLSelectElement | null} */ (qs("member-mural-card-color-key"));
        const mural_status_raw = msEl && msEl.value ? msEl.value : null;
        const color_key_raw = cardCkEl && cardCkEl.value ? cardCkEl.value : null;
        const payload = {
            title: /** @type {HTMLInputElement | null} */ (qs("member-mural-card-title")).value.trim(),
            description: /** @type {HTMLTextAreaElement | null} */ (qs("member-mural-card-description")).value,
            category: /** @type {HTMLInputElement | null} */ (qs("member-mural-card-category")).value.trim(),
            event_date: /** @type {HTMLInputElement | null} */ (qs("member-mural-card-event-date")).value || null,
            due_date: /** @type {HTMLInputElement | null} */ (qs("member-mural-card-due-date")).value || null,
            client_id: /** @type {HTMLSelectElement | null} */ (qs("member-mural-card-client")).value || null,
            project_id: /** @type {HTMLSelectElement | null} */ (qs("member-mural-card-project")).value || null,
            task_id: /** @type {HTMLSelectElement | null} */ (qs("member-mural-card-task")).value || null,
            budget_goal_id: /** @type {HTMLSelectElement | null} */ (qs("member-mural-card-goal")).value || null,
            assigned_user_id: /** @type {HTMLSelectElement | null} */ (qs("member-mural-card-assign-user")).value || null,
            assigned_department_id:
                /** @type {HTMLSelectElement | null} */ (qs("member-mural-card-assign-dept")).value || null,
            mural_status_id: mural_status_raw ? Number(mural_status_raw) : null,
            color_key: color_key_raw,
        };
        if (!payload.title) {
            window.alert("Informe o título.");
            return;
        }
        try {
            if (mode === "create") {
                const defCol = /** @type {HTMLInputElement | null} */ (qs("member-mural-card-default-column")).value;
                const body = Object.assign(
                    {
                        visibility: visibility,
                        public_lane: visibility === "public" ? (isAdminBoard() ? "management" : "members") : null,
                        title: payload.title,
                        description: payload.description,
                        category: payload.category,
                        event_date: payload.event_date,
                        due_date: payload.due_date,
                        client_id: payload.client_id,
                        project_id: payload.project_id,
                        task_id: payload.task_id,
                        budget_goal_id: payload.budget_goal_id,
                        assigned_user_id: payload.assigned_user_id,
                        assigned_department_id: payload.assigned_department_id,
                        mural_status_id: payload.mural_status_id,
                        color_key: payload.color_key,
                    },
                    visibility === "private" && defCol ? { private_column_id: Number(defCol) } : {}
                );
                await apiJson(urls.cardCreate, { method: "POST", body: JSON.stringify(body) });
            } else {
                const cid = Number(idVal);
                await apiJson(urlFrom(urls.cardUpdate, "cardId", cid), {
                    method: "PATCH",
                    body: JSON.stringify(payload),
                });
            }
            closeCardDialog();
            await syncMuralFromServer();
        } catch (e) {
            window.alert(e instanceof Error ? e.message : String(e));
        }
    }

    async function deleteCardFromForm() {
        if (!ui) return;
        const urls = /** @type {Record<string, string>} */ (ui.urls || {});
        const idVal = /** @type {HTMLInputElement | null} */ (qs("member-mural-card-id")).value;
        const cid = Number(idVal);
        if (!cid || !window.confirm("Excluir este card?")) return;
        try {
            await apiJson(urlFrom(urls.cardDelete, "cardId", cid), { method: "DELETE" });
            closeCardDialog();
            await syncMuralFromServer();
        } catch (e) {
            window.alert(e instanceof Error ? e.message : String(e));
        }
    }

    async function saveColumnFromForm() {
        if (!ui) return;
        const urls = /** @type {Record<string, string>} */ (ui.urls || {});
        const dlg = /** @type {HTMLDialogElement | null} */ (qs("member-mural-column-dialog"));
        const mode = dlg ? String(dlg.dataset.mode || "create") : "create";
        const idVal = /** @type {HTMLInputElement | null} */ (qs("member-mural-column-id")).value;
        const name = /** @type {HTMLInputElement | null} */ (qs("member-mural-column-name")).value.trim();
        const ckEl = /** @type {HTMLSelectElement | null} */ (qs("member-mural-column-color-key"));
        const color_key = ckEl && ckEl.value ? ckEl.value : null;
        if (!name) {
            window.alert("Informe o nome.");
            return;
        }
        try {
            if (mode === "create") {
                await apiJson(urls.columnCreate, { method: "POST", body: JSON.stringify({ name: name, color_key: color_key }) });
            } else {
                const colId = Number(idVal);
                await apiJson(urlFrom(urls.columnUpdate, "columnId", colId), {
                    method: "PATCH",
                    body: JSON.stringify({ name: name, color_key: color_key }),
                });
            }
            closeColumnDialog();
            await syncMuralFromServer();
        } catch (e) {
            window.alert(e instanceof Error ? e.message : String(e));
        }
    }

    /**
     * @param {DragEvent} ev
     */
    async function handleCardDrop(ev) {
        if (!dragCard || !ui || !mural) return;
        const urls = /** @type {Record<string, string>} */ (ui.urls || {});
        const target = /** @type {HTMLElement} */ (ev.target);
        const publicList = target.closest("[data-mural-drop=\"public\"]");
        const privateDrop = target.closest("[data-mural-drop=\"private\"]");
        const cardId = dragCard.id;

        try {
            if (publicList && dragCard.visibility === "private") {
                const lane = String(publicList.dataset.publicLane || "members");
                if (!isAdminBoard() && lane !== "members") {
                    throw new Error("Membro não pode mover card para a coluna pública Gestão.");
                }
                const idx = insertIndexFromPointer(publicList, ev.clientY);
                await apiJson(urlFrom(urls.cardMoveToPublic, "cardId", cardId), {
                    method: "POST",
                    body: JSON.stringify({ public_lane: lane }),
                });
                await apiJson(urlFrom(urls.cardReposition, "cardId", cardId), {
                    method: "POST",
                    body: JSON.stringify({ insert_index: idx }),
                });
            } else if (privateDrop && dragCard.visibility === "private") {
                const newCol = Number(privateDrop.dataset.columnId);
                const idx = insertIndexFromPointer(privateDrop, ev.clientY);
                if (Number(dragCard.privateColumnId) !== newCol) {
                    await apiJson(urlFrom(urls.cardMovePrivate, "cardId", cardId), {
                        method: "POST",
                        body: JSON.stringify({ private_column_id: newCol, insert_index: idx }),
                    });
                } else {
                    await apiJson(urlFrom(urls.cardReposition, "cardId", cardId), {
                        method: "POST",
                        body: JSON.stringify({ insert_index: idx }),
                    });
                }
            } else if (
                publicList &&
                dragCard.visibility === "public" &&
                String(dragCard.publicLane || "") === String(publicList.dataset.publicLane || "") &&
                (isAdminBoard() || canMutateCard(/** @type {Record<string, unknown>} */ ({ created_by_id: dragCard.createdById })))
            ) {
                const idx = insertIndexFromPointer(publicList, ev.clientY);
                await apiJson(urlFrom(urls.cardReposition, "cardId", cardId), {
                    method: "POST",
                    body: JSON.stringify({ insert_index: idx }),
                });
            }
            await syncMuralFromServer();
        } catch (e) {
            window.alert(e instanceof Error ? e.message : String(e));
            await syncMuralFromServer();
        } finally {
            dragCard = null;
            clearDragOver();
        }
    }

    /**
     * @param {DragEvent} ev
     */
    function onRootDragStart(ev) {
        const t = /** @type {HTMLElement} */ (ev.target);
        const colHead = t.closest("[data-column-drag]");
        if (colHead) {
            dragColumnId = Number(colHead.getAttribute("data-column-drag"));
            ev.dataTransfer.effectAllowed = "move";
            ev.dataTransfer.setData("text/plain", "column:" + dragColumnId);
            return;
        }
        const cardEl = t.closest("[data-card-id]");
        if (!cardEl) return;
        const id = Number(cardEl.dataset.cardId);
        const visibility = String(cardEl.dataset.visibility || "");
        const privateColumnId = cardEl.dataset.privateColumnId ? Number(cardEl.dataset.privateColumnId) : null;
        const publicLane = cardEl.dataset.publicLane ? String(cardEl.dataset.publicLane) : null;
        const createdById = Number(cardEl.dataset.createdById);
        if (visibility === "public" && createdById !== currentUserId() && !isAdminBoard()) {
            ev.preventDefault();
            return;
        }
        dragCard = {
            id: id,
            visibility: visibility,
            privateColumnId: privateColumnId,
            publicLane: publicLane,
            createdById: createdById,
        };
        ev.dataTransfer.effectAllowed = "move";
        ev.dataTransfer.setData("text/plain", "card:" + id);
    }

    /**
     * @param {DragEvent} ev
     */
    function onRootDragEnd() {
        dragColumnId = null;
        dragCard = null;
        clearDragOver();
    }

    /**
     * @param {DragEvent} ev
     */
    function onRootDragOver(ev) {
        const t = /** @type {HTMLElement} */ (ev.target);
        if (dragColumnId) {
            const col = t.closest(".member-mural-column");
            if (col) {
                ev.preventDefault();
                col.classList.add("member-mural--dragover");
            }
            return;
        }
        if (dragCard) {
            const drop = t.closest("[data-mural-drop]");
            if (drop) {
                ev.preventDefault();
                drop.classList.add("member-mural--dragover");
            }
        }
    }

    /**
     * @param {DragEvent} ev
     */
    function onRootDrop(ev) {
        const colDrop = /** @type {HTMLElement | null} */ (ev.target && /** @type {HTMLElement} */ (ev.target).closest(".member-mural-column"));
        if (dragColumnId && colDrop && root) {
            ev.preventDefault();
            const cols = root.querySelector(".member-mural-private__columns");
            const draggedEl = cols ? cols.querySelector('[data-column-id="' + dragColumnId + '"]') : null;
            if (cols && draggedEl && colDrop !== draggedEl) {
                const rect = colDrop.getBoundingClientRect();
                const before = ev.clientY < rect.top + rect.height / 2;
                if (before) cols.insertBefore(draggedEl, colDrop);
                else cols.insertBefore(draggedEl, colDrop.nextSibling);
                const ordered = Array.prototype.map.call(cols.querySelectorAll(".member-mural-column"), function (n) {
                    return Number(/** @type {HTMLElement} */ (n).dataset.columnId);
                });
                const urls = /** @type {Record<string, string>} */ ((ui && ui.urls) || {});
                apiJson(urls.columnsReorder, { method: "POST", body: JSON.stringify({ ordered_column_ids: ordered }) })
                    .then(function () {
                        return syncMuralFromServer();
                    })
                    .catch(function (e) {
                        window.alert(e instanceof Error ? e.message : String(e));
                        return syncMuralFromServer();
                    });
            }
            dragColumnId = null;
            clearDragOver();
            return;
        }
        if (dragCard) {
            const drop = /** @type {HTMLElement | null} */ (ev.target && /** @type {HTMLElement} */ (ev.target).closest("[data-mural-drop]"));
            if (drop) {
                ev.preventDefault();
                void handleCardDrop(ev);
            }
        }
    }

    /**
     * @param {MouseEvent} ev
     */
    function onRootClick(ev) {
        const t = /** @type {HTMLElement} */ (ev.target);
        const btn = t.closest("[data-action]");
        if (!btn || !root) return;
        const action = btn.getAttribute("data-action");
        if (action === "create-public-card") {
            openCardDialog("create", null, "public", null);
            return;
        }
        if (action === "toggle-members-lock") {
            if (!ui) return;
            const urls = /** @type {Record<string, string>} */ (ui.urls || {});
            const nextLocked = !(mural && mural.members_lane_locked);
            apiJson(urls.membersLaneLock, {
                method: "POST",
                body: JSON.stringify({ locked: nextLocked }),
            })
                .then(function () {
                    return syncMuralFromServer();
                })
                .catch(function (e) {
                    window.alert(e instanceof Error ? e.message : String(e));
                });
            return;
        }
        if (action === "clear-members-lane") {
            if (!ui) return;
            const urls = /** @type {Record<string, string>} */ (ui.urls || {});
            if (!window.confirm("Excluir todos os cards da coluna pública Membros?")) return;
            apiJson(urls.membersLaneClear, { method: "POST", body: "{}" })
                .then(function () {
                    return syncMuralFromServer();
                })
                .catch(function (e) {
                    window.alert(e instanceof Error ? e.message : String(e));
                });
            return;
        }
        if (action === "create-column") {
            openColumnDialog("create", null, "", "");
            return;
        }
        if (action === "add-card") {
            const colId = Number(btn.getAttribute("data-column-id"));
            openCardDialog("create", null, "private", colId);
            return;
        }
        if (action === "rename-column") {
            const colId = Number(btn.getAttribute("data-column-id"));
            const colEl = root.querySelector('.member-mural-column[data-column-id="' + colId + '"] .member-mural-column__title');
            const name = colEl ? colEl.textContent || "" : "";
            const colMeta = /** @type {Record<string, unknown>[]} */ ((mural && mural.private_columns) || []).find(function (c) {
                return Number(c.id) === colId;
            });
            const ck = colMeta && colMeta.color_key ? String(colMeta.color_key) : "";
            openColumnDialog("rename", colId, name.trim(), ck);
            return;
        }
        if (action === "delete-column") {
            const colId = Number(btn.getAttribute("data-column-id"));
            const col = /** @type {Record<string, unknown>[]} */ ((mural && mural.private_columns) || []).find(function (c) {
                return Number(c.id) === colId;
            });
            const nCards = /** @type {Record<string, unknown>[]} */ ((mural && mural.private_cards) || []).filter(function (c) {
                return Number(c.private_column_id) === colId;
            }).length;
            const msg =
                nCards > 0
                    ? "Excluir a coluna \"" +
                      (col && col.name) +
                      "\" e seus " +
                      nCards +
                      " card(s)? Esta ação não pode ser desfeita."
                    : "Excluir esta coluna vazia?";
            if (!window.confirm(msg)) return;
            if (!ui) return;
            const urls = /** @type {Record<string, string>} */ (ui.urls || {});
            apiJson(urlFrom(urls.columnDelete, "columnId", colId), { method: "DELETE" })
                .then(function () {
                    return syncMuralFromServer();
                })
                .catch(function (e) {
                    window.alert(e instanceof Error ? e.message : String(e));
                });
            return;
        }
        if (action === "open-card") {
            const cardWrap = /** @type {HTMLElement | null} */ (btn.closest("[data-card-id]"));
            if (!cardWrap || !mural) return;
            const id = Number(cardWrap.getAttribute("data-card-id"));
            const pub = /** @type {Record<string, unknown>[]} */ (mural.public_cards || []);
            const prv = /** @type {Record<string, unknown>[]} */ (mural.private_cards || []);
            let card = pub.find(function (c) {
                return Number(c.id) === id;
            });
            if (!card) card = prv.find(function (c) {
                return Number(c.id) === id;
            });
            if (card) openCardDialog("edit", card, String(card.visibility), null);
            return;
        }
        if (action === "mural-status-add") {
            openStatusDialog("create", null);
            return;
        }
        if (action === "mural-status-edit") {
            const sid = Number(btn.getAttribute("data-status-id"));
            const all = /** @type {Record<string, unknown>[]} */ ((mural && mural.mural_statuses_all) || []);
            const st = all.find(function (s) {
                return Number(s.id) === sid;
            });
            if (st) openStatusDialog("edit", st);
            return;
        }
        if (action === "mural-status-toggle") {
            const sid = Number(btn.getAttribute("data-status-id"));
            const all = /** @type {Record<string, unknown>[]} */ ((mural && mural.mural_statuses_all) || []);
            const st = all.find(function (s) {
                return Number(s.id) === sid;
            });
            if (!st || !ui) return;
            const urls = /** @type {Record<string, string>} */ (ui.urls || {});
            const nextActive = !Boolean(st.is_active);
            apiJson(urlFrom(urls.statusUpdate, "statusId", sid), {
                method: "PATCH",
                body: JSON.stringify({ is_active: nextActive }),
            })
                .then(function () {
                    return syncMuralFromServer();
                })
                .catch(function (e) {
                    window.alert(e instanceof Error ? e.message : String(e));
                });
            return;
        }
        if (action === "mural-status-up") {
            const sid = Number(btn.getAttribute("data-status-id"));
            void moveStatusByDelta(sid, -1);
            return;
        }
        if (action === "mural-status-down") {
            const sid = Number(btn.getAttribute("data-status-id"));
            void moveStatusByDelta(sid, 1);
            return;
        }
        if (action === "copy-public-to-private") {
            const cardId = Number(btn.getAttribute("data-card-id"));
            if (!cardId || !ui) return;
            const urls = /** @type {Record<string, string>} */ (ui.urls || {});
            apiJson(urlFrom(urls.cardCopyToPrivate, "cardId", cardId), { method: "POST", body: "{}" })
                .then(function () {
                    return syncMuralFromServer();
                })
                .catch(function (e) {
                    window.alert(e instanceof Error ? e.message : String(e));
                });
        }
    }

    function bindForms() {
        const cardForm = qs("member-mural-card-form");
        if (cardForm) {
            cardForm.addEventListener("submit", function (e) {
                e.preventDefault();
                void saveCardFromForm();
            });
        }
        const colForm = qs("member-mural-column-form");
        if (colForm) {
            colForm.addEventListener("submit", function (e) {
                e.preventDefault();
                void saveColumnFromForm();
            });
        }
        const stForm = qs("member-mural-status-form");
        if (stForm) {
            stForm.addEventListener("submit", function (e) {
                e.preventDefault();
                void saveStatusFromForm();
            });
        }
        document.querySelectorAll("[data-mural-close-status]").forEach(function (b) {
            b.addEventListener("click", closeStatusDialog);
        });
        document.querySelectorAll("[data-mural-close-card]").forEach(function (b) {
            b.addEventListener("click", closeCardDialog);
        });
        document.querySelectorAll("[data-mural-close-column]").forEach(function (b) {
            b.addEventListener("click", closeColumnDialog);
        });
        const del = qs("member-mural-card-delete");
        if (del) del.addEventListener("click", function () { void deleteCardFromForm(); });
        const cSel = qs("member-mural-card-client");
        const pSel = qs("member-mural-card-project");
        if (cSel) cSel.addEventListener("change", filterProjectsByClient);
        if (pSel) pSel.addEventListener("change", filterTasksByProject);
    }

    function init() {
        root = /** @type {HTMLElement | null} */ (qs("member-mural-root"));
        mural = readJsonScript("member-mural-initial");
        ui = readJsonScript("member-mural-ui");
        if (!root || !mural || !ui) return;
        fillMetaSelects();
        bindForms();
        root.addEventListener("click", onRootClick);
        root.addEventListener("dragstart", onRootDragStart);
        root.addEventListener("dragend", onRootDragEnd);
        root.addEventListener("dragover", onRootDragOver);
        root.addEventListener("drop", onRootDrop);
        render();
    }

    if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
    else init();
})();
