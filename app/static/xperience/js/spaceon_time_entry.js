/**
 * Home Spaceon: modo de lançamento (horas / intervalo / cronômetro), calendário + manual/create,
 * timer draft/stop e conclusão de template pós-cronômetro.
 */
(function () {
    var STORAGE_KEY = "xperience_pre_entry";
    var STORAGE_DATE_KEY = "xperience_pre_entry_target_date";
    /** "1" = calendário em modo salvar no clique; "0" = rascunho mantido, calendário desarmado (Esc). */
    var STORAGE_ARMED_KEY = "xperience_pre_entry_calendar_armed";

    var MONTH_NAMES_PT = [
        "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
        "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro",
    ];

    var apiEl = document.getElementById("q1-time-entry-api");
    var form = document.getElementById("q1-pre-entry-form");
    var calendarCard = document.getElementById("q3-calendar-card");
    var calendarBody = document.getElementById("q3-calendar-body");
    var headingEl = document.getElementById("q3-calendar-month-label");
    var btnPrev = document.getElementById("q3-cal-prev");
    var btnNext = document.getElementById("q3-cal-next");
    var btnToday = document.getElementById("q3-cal-today");
    var btnPrepare = document.getElementById("q1-btn-prepare");
    var statusEl = document.getElementById("q3-calendar-status");
    var hoursInput = document.getElementById("horas-gastas");

    if (!form || !apiEl) {
        return;
    }

    var manualCreateUrl = apiEl.getAttribute("data-manual-create-url") || "";
    var monthCountsUrl = apiEl.getAttribute("data-month-counts-url") || "";
    var timerDraftUrl = apiEl.getAttribute("data-timer-draft-url") || "";
    var timerStartUrl = apiEl.getAttribute("data-timer-start-url") || "";
    var timerStopUrl = apiEl.getAttribute("data-timer-stop-url") || "";
    var timerCompleteUrl = apiEl.getAttribute("data-timer-complete-url") || "";
    var timerDiscardUrl = apiEl.getAttribute("data-timer-discard-url") || "";
    var dayDetailUrl = apiEl.getAttribute("data-day-detail-url") || "";
    var manualUpdateTemplate = apiEl.getAttribute("data-manual-update-url-template") || "";
    var manualDeleteTemplate = apiEl.getAttribute("data-manual-delete-url-template") || "";
    var URL_PK_TOKEN = "888001888";
    var workspaceId = apiEl.getAttribute("data-workspace-id") || "";
    var configured = form.getAttribute("data-configured") === "true";

    var saving = false;
    var viewYear;
    var viewMonth;
    var selectedIso = null;
    var draftEntryId = null;
    var countsCache = {};
    var currentDayModalIso = null;
    var q3DayEditBaseline = null;
    var editPayloadByEntryId = {};
    var calendarDayClickWired = false;
    var dayModalActionsWired = false;

    function pad2(n) {
        return n < 10 ? "0" + n : String(n);
    }

    function localTodayParts() {
        var d = new Date();
        return { y: d.getFullYear(), m: d.getMonth() + 1, day: d.getDate() };
    }

    function getSelectedMode() {
        var r = form.querySelector('input[name="launch_mode"]:checked');
        return r ? r.value : "duration";
    }

    function getCsrfToken() {
        var inp = form.querySelector("[name=csrfmiddlewaretoken]");
        return inp && inp.value ? inp.value : "";
    }

    function jsonFetch(url, options) {
        var o = options || {};
        o.credentials = "same-origin";
        o.headers = o.headers || {};
        o.headers["X-CSRFToken"] = getCsrfToken();
        if (!o.headers["Content-Type"] && o.body && typeof o.body === "string") {
            o.headers["Content-Type"] = "application/json";
        }
        return fetch(url, o).then(function (res) {
            return res.text().then(function (text) {
                var body = {};
                try {
                    body = text ? JSON.parse(text) : {};
                } catch (e) {
                    body = { error: text || res.statusText };
                }
                return { res: res, body: body };
            });
        });
    }

    function manualUpdateUrl(pk) {
        return (manualUpdateTemplate || "").split(URL_PK_TOKEN).join(String(pk));
    }

    function manualDeleteUrl(pk) {
        return (manualDeleteTemplate || "").split(URL_PK_TOKEN).join(String(pk));
    }

    function timeToInput(val) {
        if (!val) {
            return "";
        }
        var s = String(val);
        return s.length >= 5 ? s.slice(0, 5) : s;
    }

    function showDayModalMainView(showMain) {
        var view = document.getElementById("q3-day-modal-view");
        var edit = document.getElementById("q3-day-modal-edit");
        if (view) {
            view.classList.toggle("q1-hidden", !showMain);
        }
        if (edit) {
            edit.classList.toggle("q1-hidden", showMain);
        }
    }

    function isoToBrLabel(iso) {
        var parts = (iso || "").split("-");
        if (parts.length !== 3) {
            return iso || "";
        }
        return parts[2] + "/" + parts[1] + "/" + parts[0];
    }

    function fillDayModalEntries(entries) {
        var wrap = document.getElementById("q3-day-entries-list");
        if (!wrap) {
            return;
        }
        wrap.innerHTML = "";
        editPayloadByEntryId = {};
        if (!entries || !entries.length) {
            var empty = document.createElement("p");
            empty.className = "q3-day-modal-empty";
            empty.textContent = "Nenhum apontamento nesta data.";
            wrap.appendChild(empty);
            return;
        }
        entries.forEach(function (item) {
            if (item.edit) {
                editPayloadByEntryId[item.id] = item.edit;
            }
            var row = document.createElement("div");
            row.className = "q3-day-modal-entry";
            var main = document.createElement("div");
            main.className = "q3-day-modal-entry__main";
            var l1 = document.createElement("div");
            l1.className = "q3-day-modal-entry__hours";
            l1.textContent = item.hours_label || "—";
            var l2 = document.createElement("div");
            l2.className = "q3-day-modal-entry__summary";
            l2.textContent = item.summary || "—";
            main.appendChild(l1);
            main.appendChild(l2);
            row.appendChild(main);
            if (item.can_edit || item.can_delete) {
                var actions = document.createElement("div");
                actions.className = "q3-day-modal-entry__actions";
                if (item.can_edit) {
                    var btnE = document.createElement("button");
                    btnE.type = "button";
                    btnE.className = "q3-day-modal-entry__icon-btn";
                    btnE.setAttribute("data-day-action", "edit");
                    btnE.setAttribute("data-entry-id", String(item.id));
                    btnE.setAttribute("aria-label", "Editar apontamento");
                    var icE = document.createElement("i");
                    icE.className = "fas fa-pencil-alt";
                    icE.setAttribute("aria-hidden", "true");
                    btnE.appendChild(icE);
                    actions.appendChild(btnE);
                }
                if (item.can_delete) {
                    var btnD = document.createElement("button");
                    btnD.type = "button";
                    btnD.className = "q3-day-modal-entry__icon-btn q3-day-modal-entry__icon-btn--danger";
                    btnD.setAttribute("data-day-action", "delete");
                    btnD.setAttribute("data-entry-id", String(item.id));
                    btnD.setAttribute("aria-label", "Excluir apontamento");
                    var icD = document.createElement("i");
                    icD.className = "fas fa-trash-alt";
                    icD.setAttribute("aria-hidden", "true");
                    btnD.appendChild(icD);
                    actions.appendChild(btnD);
                }
                row.appendChild(actions);
            }
            wrap.appendChild(row);
        });
    }

    function fillDayModalEvents(events) {
        var wrap = document.getElementById("q3-day-events-list");
        if (!wrap) {
            return;
        }
        wrap.innerHTML = "";
        if (!events || !events.length) {
            var empty = document.createElement("p");
            empty.className = "q3-day-modal-empty";
            empty.textContent = "Nenhum evento nesta data.";
            wrap.appendChild(empty);
            return;
        }
        events.forEach(function (ev) {
            var block = document.createElement("div");
            block.className = "q3-day-modal-event";
            var t = document.createElement("div");
            t.className = "q3-day-modal-event__title";
            t.textContent = ev.title || "Evento";
            block.appendChild(t);
            if (ev.detail) {
                var d = document.createElement("p");
                d.className = "q3-day-modal-event__detail";
                d.textContent = ev.detail;
                block.appendChild(d);
            }
            wrap.appendChild(block);
        });
    }

    function fetchDayDetailAndFill(iso) {
        var wrap = document.getElementById("q3-day-entries-list");
        var evWrap = document.getElementById("q3-day-events-list");
        if (wrap) {
            wrap.innerHTML = "";
            var load = document.createElement("p");
            load.className = "q3-day-modal-empty";
            load.textContent = "Carregando…";
            wrap.appendChild(load);
        }
        if (evWrap) {
            evWrap.innerHTML = "";
        }
        if (!dayDetailUrl || !iso) {
            return Promise.resolve();
        }
        var sep = dayDetailUrl.indexOf("?") >= 0 ? "&" : "?";
        var url = dayDetailUrl + sep + "date=" + encodeURIComponent(iso);
        return jsonFetch(url, { method: "GET" }).then(function (out) {
            if (!out.res.ok) {
                if (wrap) {
                    wrap.innerHTML = "";
                    var err = document.createElement("p");
                    err.className = "q3-day-modal-empty q3-day-modal-empty--warn";
                    err.textContent = (out.body && out.body.error) || "Não foi possível carregar o dia.";
                    wrap.appendChild(err);
                }
                return;
            }
            fillDayModalEntries(out.body.entries || []);
            fillDayModalEvents(out.body.events || []);
        }).catch(function () {
            if (wrap) {
                wrap.innerHTML = "";
                var err = document.createElement("p");
                err.className = "q3-day-modal-empty q3-day-modal-empty--warn";
                err.textContent = "Falha de rede ao carregar o dia.";
                wrap.appendChild(err);
            }
        });
    }

    function openDayDetailModal(iso) {
        var dlg = document.getElementById("q3-calendar-day-dialog");
        var title = document.getElementById("q3-calendar-day-dialog-title");
        if (!dlg || typeof dlg.showModal !== "function") {
            return;
        }
        currentDayModalIso = iso;
        showDayModalMainView(true);
        q3DayEditBaseline = null;
        if (title) {
            title.textContent = "Dia " + isoToBrLabel(iso);
        }
        var st = document.getElementById("q3-day-edit-status");
        if (st) {
            st.textContent = "";
        }
        dlg.showModal();
        fetchDayDetailAndFill(iso);
    }

    function eachDayEditValueOption(select, fn) {
        if (!select) {
            return;
        }
        Array.from(select.options).forEach(function (opt) {
            if (opt.value === "") {
                return;
            }
            fn(opt);
        });
    }

    function applyDayEditTaskFilter() {
        var clientEl = document.getElementById("q3-day-edit-client");
        var projectEl = document.getElementById("q3-day-edit-project");
        var taskEl = document.getElementById("q3-day-edit-task");
        if (!taskEl) {
            return;
        }
        var pid = projectEl && projectEl.value ? projectEl.value : "";
        var cid = clientEl && clientEl.value ? clientEl.value : "";
        eachDayEditValueOption(taskEl, function (opt) {
            var op = opt.getAttribute("data-project-id");
            var oc = opt.getAttribute("data-client-id");
            var show = true;
            if (pid) {
                show = op === pid;
            } else if (cid) {
                show = oc === cid;
            }
            opt.hidden = !show;
        });
        var tsel = taskEl.selectedOptions[0];
        if (taskEl.value && tsel && tsel.hidden) {
            taskEl.value = "";
        }
    }

    function applyDayEditProjectFilter() {
        var clientEl = document.getElementById("q3-day-edit-client");
        var projectEl = document.getElementById("q3-day-edit-project");
        if (!projectEl) {
            applyDayEditTaskFilter();
            return;
        }
        var cid = clientEl && clientEl.value ? clientEl.value : "";
        eachDayEditValueOption(projectEl, function (opt) {
            var oc = opt.getAttribute("data-client-id");
            opt.hidden = Boolean(cid && oc !== cid);
        });
        var sel = projectEl.selectedOptions[0];
        if (projectEl.value && sel && sel.hidden) {
            projectEl.value = "";
        }
        applyDayEditTaskFilter();
    }

    function setDayEditFkSelect(sel, idVal) {
        if (!sel) {
            return;
        }
        sel.value = idVal != null && idVal !== "" ? String(idVal) : "";
    }

    function populateDayEditSelectsFromBase(base) {
        var clientEl = document.getElementById("q3-day-edit-client");
        var projectEl = document.getElementById("q3-day-edit-project");
        var taskEl = document.getElementById("q3-day-edit-task");
        var typeEl = document.getElementById("q3-day-edit-entry-type");
        setDayEditFkSelect(clientEl, base.client_id);
        applyDayEditProjectFilter();
        setDayEditFkSelect(projectEl, base.project_id);
        applyDayEditTaskFilter();
        setDayEditFkSelect(taskEl, base.task_id);
        if (typeEl) {
            typeEl.value = base.entry_type ? String(base.entry_type) : "";
        }
    }

    function wireDayEditCascadeOnce() {
        var dc = document.getElementById("q3-day-edit-client");
        var dp = document.getElementById("q3-day-edit-project");
        if (dc && !dc.dataset.dayCascadeWired) {
            dc.dataset.dayCascadeWired = "1";
            dc.addEventListener("change", applyDayEditProjectFilter);
        }
        if (dp && !dp.dataset.dayCascadeWired) {
            dp.dataset.dayCascadeWired = "1";
            dp.addEventListener("change", applyDayEditTaskFilter);
        }
    }

    function openDayEditPanel(entryId) {
        var base = editPayloadByEntryId[entryId];
        if (!base) {
            return;
        }
        q3DayEditBaseline = base;
        showDayModalMainView(false);
        wireDayEditCascadeOnce();
        var rowD = document.getElementById("q3-day-edit-row-duration");
        var rowR = document.getElementById("q3-day-edit-row-range");
        var st = document.getElementById("q3-day-edit-status");
        if (st) {
            st.textContent = "";
        }
        if (rowD && rowR) {
            rowD.classList.toggle("q1-hidden", base.entry_mode !== "duration");
            rowR.classList.toggle("q1-hidden", base.entry_mode !== "time_range");
        }
        var h = document.getElementById("q3-day-edit-hours");
        var s = document.getElementById("q3-day-edit-start");
        var e = document.getElementById("q3-day-edit-end");
        var desc = document.getElementById("q3-day-edit-description");
        var ot = document.getElementById("q3-day-edit-overtime");
        if (h) {
            h.value = base.hours != null ? String(base.hours).replace(",", ".") : "";
        }
        if (s) {
            s.value = timeToInput(base.start_time);
        }
        if (e) {
            e.value = timeToInput(base.end_time);
        }
        populateDayEditSelectsFromBase(base);
        if (desc) {
            desc.value = base.description != null ? String(base.description) : "";
        }
        if (ot) {
            ot.checked = !!base.is_overtime;
        }
    }

    function wireDayModalActionsOnce() {
        if (dayModalActionsWired) {
            return;
        }
        dayModalActionsWired = true;
        var dlg = document.getElementById("q3-calendar-day-dialog");
        var closeBtn = document.getElementById("q3-calendar-day-dialog-close");
        var backBtn = document.getElementById("q3-day-modal-edit-back");
        var editForm = document.getElementById("q3-day-modal-edit-form");
        var entriesList = document.getElementById("q3-day-entries-list");
        if (dlg && closeBtn) {
            closeBtn.addEventListener("click", function () {
                dlg.close();
            });
            dlg.addEventListener("click", function (ev) {
                if (ev.target === dlg) {
                    dlg.close();
                }
            });
        }
        if (backBtn) {
            backBtn.addEventListener("click", function () {
                showDayModalMainView(true);
                q3DayEditBaseline = null;
                if (currentDayModalIso) {
                    fetchDayDetailAndFill(currentDayModalIso);
                }
            });
        }
        if (entriesList) {
            entriesList.addEventListener("click", function (ev) {
                var btn = ev.target.closest("[data-day-action]");
                if (!btn) {
                    return;
                }
                var id = parseInt(btn.getAttribute("data-entry-id") || "0", 10);
                if (!id) {
                    return;
                }
                var act = btn.getAttribute("data-day-action");
                if (act === "edit") {
                    openDayEditPanel(id);
                } else if (act === "delete") {
                    if (!window.confirm("Excluir este apontamento? Esta ação não pode ser desfeita.")) {
                        return;
                    }
                    jsonFetch(manualDeleteUrl(id), { method: "POST", body: "{}" }).then(function (out) {
                        if (!out.res.ok) {
                            setCalendarStatus((out.body && out.body.error) || "Não foi possível excluir.", "warn");
                            return;
                        }
                        invalidateViewMonthCountsCache();
                        fullCalendarRender();
                        if (currentDayModalIso) {
                            fetchDayDetailAndFill(currentDayModalIso);
                        }
                    });
                }
            });
        }
        if (editForm) {
            editForm.addEventListener("submit", function (ev) {
                ev.preventDefault();
                if (!q3DayEditBaseline) {
                    return;
                }
                var st = document.getElementById("q3-day-edit-status");
                if (st) {
                    st.textContent = "";
                }
                var base = q3DayEditBaseline;
                var cEl = document.getElementById("q3-day-edit-client");
                var pEl = document.getElementById("q3-day-edit-project");
                var tEl = document.getElementById("q3-day-edit-task");
                var typeEl = document.getElementById("q3-day-edit-entry-type");
                var descEl = document.getElementById("q3-day-edit-description");
                var body = {
                    entry_mode: base.entry_mode,
                    date: base.date,
                    client_id: cEl ? (cEl.value ? parseInt(cEl.value, 10) : null) : base.client_id,
                    project_id: pEl ? (pEl.value ? parseInt(pEl.value, 10) : null) : base.project_id,
                    task_id: tEl ? (tEl.value ? parseInt(tEl.value, 10) : null) : base.task_id,
                    entry_type: typeEl ? String(typeEl.value || "") : base.entry_type || "",
                    description: descEl
                        ? String(descEl.value || "")
                        : base.description != null
                          ? String(base.description)
                          : "",
                    is_overtime: !!(
                        document.getElementById("q3-day-edit-overtime") &&
                        document.getElementById("q3-day-edit-overtime").checked
                    ),
                };
                if (base.entry_mode === "duration") {
                    var hi = document.getElementById("q3-day-edit-hours");
                    body.hours = hi && hi.value ? String(hi.value) : "";
                } else if (base.entry_mode === "time_range") {
                    var si = document.getElementById("q3-day-edit-start");
                    var ei = document.getElementById("q3-day-edit-end");
                    body.start_time = si && si.value ? String(si.value) : "";
                    body.end_time = ei && ei.value ? String(ei.value) : "";
                }
                jsonFetch(manualUpdateUrl(base.id), { method: "POST", body: JSON.stringify(body) }).then(function (out) {
                    if (!out.res.ok) {
                        if (st) {
                            st.textContent = (out.body && out.body.error) || "Erro ao salvar.";
                        }
                        return;
                    }
                    q3DayEditBaseline = null;
                    showDayModalMainView(true);
                    invalidateViewMonthCountsCache();
                    fullCalendarRender();
                    if (currentDayModalIso) {
                        fetchDayDetailAndFill(currentDayModalIso);
                    }
                });
            });
        }
    }

    function onCalendarBodyClick(ev) {
        if (!calendarBody) {
            return;
        }
        var td = ev.target.closest("td.calendar-day");
        if (!td || td.classList.contains("muted-day")) {
            return;
        }
        var iso = td.getAttribute("data-date-iso");
        if (!iso) {
            return;
        }

        var bdayBtn = ev.target.closest(".q3-calendar-day-birthday--interactive");
        if (bdayBtn && !bdayBtn.disabled) {
            if (calendarCard && calendarCard.classList.contains("q3-calendar-card--prepared")) {
                return;
            }
            ev.preventDefault();
            ev.stopPropagation();
            var birthdayDialog = document.getElementById("q3-birthday-info-dialog");
            var birthdayText = document.getElementById("q3-birthday-info-text");
            if (birthdayDialog && birthdayText && typeof birthdayDialog.showModal === "function") {
                var rawLines = bdayBtn.getAttribute("data-birthday-lines");
                var lines = [];
                if (rawLines) {
                    try {
                        lines = JSON.parse(rawLines);
                    } catch (eParse) {
                        lines = [];
                    }
                }
                if (!Array.isArray(lines) || !lines.length) {
                    var displayName =
                        (apiEl && apiEl.getAttribute("data-member-display-name")) || "Colaborador";
                    var dateLabel = isoToBrLabel(iso);
                    lines = [
                        "É aniversário de " + displayName + " nesta data (" + dateLabel + ").",
                    ];
                }
                birthdayText.textContent = lines.join("\n\n");
                birthdayDialog.showModal();
            }
            return;
        }

        if (isCalendarSaveMode()) {
            if (!td.classList.contains("calendar-day--selectable")) {
                return;
            }
            if (!manualCreateUrl || saving) {
                return;
            }
            var payload = readStoredPayload();
            if (!payload) {
                setCalendarStatus("Prepare o apontamento antes de escolher o dia.", "warn");
                return;
            }
            payload.date = iso;
            saving = true;
            if (calendarCard) {
                calendarCard.classList.add("q3-calendar-card--saving");
            }
            setCalendarStatus("Salvando apontamento…", "");

            jsonFetch(manualCreateUrl, { method: "POST", body: JSON.stringify(payload) })
                .then(function (out) {
                    if (!out.res.ok) {
                        setCalendarStatus((out.body && out.body.error) || "Erro ao salvar.", "warn");
                        return;
                    }
                    try {
                        sessionStorage.removeItem(STORAGE_KEY);
                        sessionStorage.removeItem(STORAGE_DATE_KEY);
                        sessionStorage.removeItem(STORAGE_ARMED_KEY);
                    } catch (e2) {
                        /* ignore */
                    }
                    selectedIso = null;
                    var d = out.body.entry && out.body.entry.date;
                    var parts = (d ? d : iso).split("-");
                    var label = parts[2] + "/" + parts[1] + "/" + parts[0];
                    setCalendarStatus("Apontamento salvo em " + label + ".", "ok");
                    invalidateViewMonthCountsCache();
                    fullCalendarRender();
                })
                .catch(function () {
                    setCalendarStatus("Falha de rede ao salvar. Tente novamente.", "warn");
                })
                .finally(function () {
                    saving = false;
                    if (calendarCard) {
                        calendarCard.classList.remove("q3-calendar-card--saving");
                    }
                });
            return;
        }

        if (td.classList.contains("calendar-day--locked")) {
            openDayDetailModal(iso);
        }
    }

    function wireCalendarDayInteractionOnce() {
        if (!calendarBody || calendarDayClickWired) {
            return;
        }
        calendarDayClickWired = true;
        calendarBody.addEventListener("click", onCalendarBodyClick);
    }

    function setTimerRunningUi(isRunning) {
        var block = document.getElementById("q1-block-timer");
        if (block) {
            block.classList.toggle("q1-block-timer--running", !!isRunning);
        }
    }

    function syncModeBlocks() {
        var mode = getSelectedMode();
        var bd = document.getElementById("q1-block-duration");
        var br = document.getElementById("q1-block-range");
        var bt = document.getElementById("q1-block-timer");
        var calWrap = document.getElementById("q3-calendar-section-wrap");
        var btnMem = document.getElementById("q1-btn-memorize");
        var actionsRow = form.querySelector(".q1-actions");
        if (bd) {
            bd.classList.toggle("q1-hidden", mode !== "duration");
        }
        if (br) {
            br.classList.toggle("q1-hidden", mode !== "time_range");
        }
        if (bt) {
            bt.classList.toggle("q1-hidden", mode !== "timer");
        }
        if (btnPrepare) {
            btnPrepare.classList.toggle("q1-hidden", mode === "timer");
        }
        if (btnMem) {
            btnMem.classList.toggle("q1-hidden", mode === "timer");
        }
        if (calWrap) {
            calWrap.classList.toggle("q1-hidden", mode === "timer");
        }
        if (actionsRow) {
            actionsRow.classList.toggle("q1-hidden", mode === "timer");
        }
        applyLaunchModeLock();
    }

    function applyLaunchModeLock() {
        var postWrap = document.getElementById("q1-post-timer-wrap");
        var pendingFinalize = postWrap && !postWrap.classList.contains("q1-hidden");
        form.querySelectorAll('input[name="launch_mode"]').forEach(function (el) {
            if (pendingFinalize) {
                el.disabled = true;
            } else if (draftEntryId) {
                el.disabled = el.value !== "timer";
            } else {
                el.disabled = false;
            }
        });
    }

    function setCalendarStatus(msg, kind) {
        if (!statusEl) {
            return;
        }
        statusEl.textContent = msg || "";
        statusEl.classList.remove("q3-calendar-status--ok", "q3-calendar-status--warn");
        if (kind === "ok") {
            statusEl.classList.add("q3-calendar-status--ok");
        } else if (kind === "warn") {
            statusEl.classList.add("q3-calendar-status--warn");
        }
    }

    function readStoredPayload() {
        try {
            var raw = sessionStorage.getItem(STORAGE_KEY);
            return raw ? JSON.parse(raw) : null;
        } catch (e) {
            return null;
        }
    }

    function readStoredDate() {
        try {
            return sessionStorage.getItem(STORAGE_DATE_KEY);
        } catch (e) {
            return null;
        }
    }

    function isStagedPreEntryForWorkspace() {
        var p = readStoredPayload();
        if (!p || !workspaceId || p.entry_mode === "timer") {
            return false;
        }
        if (p.workspace_id == null || p.workspace_id === "") {
            return false;
        }
        return String(p.workspace_id) === String(workspaceId);
    }

    function isCalendarSaveMode() {
        if (!isStagedPreEntryForWorkspace()) {
            return false;
        }
        try {
            if (sessionStorage.getItem(STORAGE_ARMED_KEY) === "0") {
                return false;
            }
        } catch (eArm) {
            return false;
        }
        return true;
    }

    function collectFormPayload() {
        var fd = new FormData(form);
        var mode = getSelectedMode();
        var otEl = document.getElementById("q1-is-overtime");
        var o = {
            workspace_id: workspaceId ? Number(workspaceId) : null,
            entry_mode: mode,
            client_id: fd.get("client_id") != null ? String(fd.get("client_id")) : "",
            project_id: fd.get("project_id") != null ? String(fd.get("project_id")) : "",
            task_id: fd.get("task_id") != null ? String(fd.get("task_id")) : "",
            description: fd.get("description") != null ? String(fd.get("description")) : "",
            entry_type: fd.get("entry_type") != null ? String(fd.get("entry_type")) : "",
            is_overtime: !!(otEl && otEl.checked),
            prepared_at: new Date().toISOString(),
        };
        if (mode === "duration") {
            o.hours = fd.get("hours") != null ? String(fd.get("hours")) : "";
        } else if (mode === "time_range") {
            o.start_time = fd.get("start_time") != null ? String(fd.get("start_time")) : "";
            o.end_time = fd.get("end_time") != null ? String(fd.get("end_time")) : "";
        }
        return o;
    }

    function monthWeeks(year, month) {
        var dim = new Date(year, month, 0).getDate();
        var firstDow = new Date(year, month - 1, 1).getDay();
        var cells = [];
        var cur = 1 - firstDow;
        var i;
        for (i = 0; i < 42; i++) {
            cells.push(cur >= 1 && cur <= dim ? cur : null);
            cur++;
        }
        var weeks = [];
        for (i = 0; i < 6; i++) {
            weeks.push(cells.slice(i * 7, i * 7 + 7));
        }
        return weeks;
    }

    function isSameLocalDate(y, m, day, ref) {
        return ref.getFullYear() === y && ref.getMonth() + 1 === m && ref.getDate() === day;
    }

    /** Domingo = "sun" … Sábado = "sat" (alinhado a ``Date#getDay``). */
    function localWeekdayKey(y, month1Based, day) {
        var d = new Date(y, month1Based - 1, day);
        var byGetDay = ["sun", "mon", "tue", "wed", "thu", "fri", "sat"];
        return byGetDay[d.getDay()];
    }

    function monthCountsCacheKey(y, m) {
        return String(y) + "-" + String(m);
    }

    function invalidateViewMonthCountsCache() {
        delete countsCache[monthCountsCacheKey(viewYear, viewMonth)];
    }

    function emptyMonthCalendarPayload() {
        return {
            counts: {},
            hours: {},
            pay: {},
            expected: null,
            birthday: null,
            workspacePublicBirthdays: [],
            scheduleWeekdayStripes: null,
        };
    }

    function normalizeMonthCalendarPayload(body) {
        var counts = {};
        var hours = {};
        var pay = {};
        var expected = null;
        var birthday = null;
        if (body && typeof body.by_date === "object" && body.by_date !== null) {
            counts = body.by_date;
        }
        if (body && typeof body.by_date_hours === "object" && body.by_date_hours !== null) {
            hours = body.by_date_hours;
        }
        if (body && typeof body.by_date_pay === "object" && body.by_date_pay !== null) {
            pay = body.by_date_pay;
        }
        if (body && body.expected_hours_per_day != null && body.expected_hours_per_day !== "") {
            var ex = parseFloat(String(body.expected_hours_per_day), 10);
            if (!isNaN(ex) && ex > 0) {
                expected = ex;
            }
        }
        if (body && body.member_birthday && typeof body.member_birthday === "object") {
            var bm = parseInt(String(body.member_birthday.month), 10);
            var bday = parseInt(String(body.member_birthday.day), 10);
            if (!isNaN(bm) && !isNaN(bday) && bm >= 1 && bm <= 12 && bday >= 1 && bday <= 31) {
                birthday = { month: bm, day: bday };
            }
        }
        var workspacePublicBirthdays = [];
        if (body && Array.isArray(body.workspace_public_birthdays)) {
            body.workspace_public_birthdays.forEach(function (row) {
                if (!row || typeof row !== "object") {
                    return;
                }
                var pm = parseInt(String(row.month), 10);
                var pd = parseInt(String(row.day), 10);
                var nm = row.display_name != null ? String(row.display_name).trim() : "";
                if (!isNaN(pm) && !isNaN(pd) && pm >= 1 && pm <= 12 && pd >= 1 && pd <= 31 && nm) {
                    workspacePublicBirthdays.push({ month: pm, day: pd, display_name: nm });
                }
            });
        }
        var scheduleWeekdayStripes = null;
        if (body && body.schedule_weekday_visual && typeof body.schedule_weekday_visual === "object") {
            var rawList = body.schedule_weekday_visual.working_days;
            var allowed = {
                mon: true,
                tue: true,
                wed: true,
                thu: true,
                fri: true,
                sat: true,
                sun: true,
            };
            var working = {};
            if (Array.isArray(rawList)) {
                rawList.forEach(function (k) {
                    var key = String(k || "")
                        .trim()
                        .toLowerCase();
                    if (allowed[key]) {
                        working[key] = true;
                    }
                });
            }
            if (Object.keys(working).length > 0) {
                scheduleWeekdayStripes = { working: working };
            }
        }
        return {
            counts: counts,
            hours: hours,
            pay: pay,
            expected: expected,
            birthday: birthday,
            workspacePublicBirthdays: workspacePublicBirthdays,
            scheduleWeekdayStripes: scheduleWeekdayStripes,
        };
    }

    function fetchMonthCounts(y, m) {
        var key = monthCountsCacheKey(y, m);
        if (Object.prototype.hasOwnProperty.call(countsCache, key)) {
            return Promise.resolve(countsCache[key]);
        }
        if (!monthCountsUrl) {
            var empty = emptyMonthCalendarPayload();
            countsCache[key] = empty;
            return Promise.resolve(empty);
        }
        var sep = monthCountsUrl.indexOf("?") >= 0 ? "&" : "?";
        var url =
            monthCountsUrl +
            sep +
            "year=" +
            encodeURIComponent(y) +
            "&month=" +
            encodeURIComponent(m);
        return jsonFetch(url, { method: "GET" }).then(function (out) {
            var payload = emptyMonthCalendarPayload();
            if (out.res.ok && out.body) {
                payload = normalizeMonthCalendarPayload(out.body);
            }
            countsCache[key] = payload;
            return payload;
        }).catch(function () {
            var fallback = emptyMonthCalendarPayload();
            countsCache[key] = fallback;
            return fallback;
        });
    }

    function renderHeading() {
        if (headingEl) {
            headingEl.textContent = MONTH_NAMES_PT[viewMonth - 1] + " " + viewYear;
        }
    }

    function renderCalendar(calendarPayload) {
        if (!calendarBody || !calendarCard) {
            return;
        }
        var payload =
            calendarPayload && typeof calendarPayload === "object"
                ? calendarPayload
                : emptyMonthCalendarPayload();
        var map = payload.counts || {};
        var hoursMap = payload.hours || {};
        var payMap = payload.pay || {};
        var bdayRule = payload.birthday || null;
        var publicBirthdays = payload.workspacePublicBirthdays || [];
        var expectedDaily = payload.expected;
        var scheduleStripes = payload.scheduleWeekdayStripes;
        var prepared = isCalendarSaveMode();
        var weeks = monthWeeks(viewYear, viewMonth);
        var now = new Date();
        calendarBody.innerHTML = "";

        weeks.forEach(function (week) {
            var tr = document.createElement("tr");
            week.forEach(function (day) {
                var td = document.createElement("td");
                if (day == null) {
                    td.className = "calendar-day muted-day";
                } else {
                    var iso = viewYear + "-" + pad2(viewMonth) + "-" + pad2(day);
                    td.className = "calendar-day";
                    if (
                        scheduleStripes &&
                        scheduleStripes.working &&
                        !scheduleStripes.working[localWeekdayKey(viewYear, viewMonth, day)]
                    ) {
                        td.classList.add("calendar-day--schedule-off");
                    }
                    if (prepared) {
                        td.classList.add("calendar-day--selectable");
                    } else {
                        td.classList.add("calendar-day--locked");
                    }
                    if (isSameLocalDate(viewYear, viewMonth, day, now)) {
                        td.classList.add("calendar-day--today");
                    }
                    if (selectedIso === iso) {
                        td.classList.add("selected-day");
                    }
                    td.dataset.dateIso = iso;
                    var num = document.createElement("span");
                    num.className = "day-number";
                    num.textContent = String(day);
                    td.appendChild(num);
                    var content = document.createElement("div");
                    content.className = "day-content";
                    var rawCount = map[iso];
                    var n = 0;
                    if (rawCount != null) {
                        n = typeof rawCount === "number" ? rawCount : parseInt(String(rawCount), 10);
                        if (isNaN(n) || n < 0) {
                            n = 0;
                        }
                    }
                    if (expectedDaily != null && expectedDaily > 0) {
                        var rawH = hoursMap[iso];
                        var hoursDay = 0;
                        if (rawH != null) {
                            hoursDay =
                                typeof rawH === "number"
                                    ? rawH
                                    : parseFloat(String(rawH).replace(",", "."));
                            if (isNaN(hoursDay) || hoursDay < 0) {
                                hoursDay = 0;
                            }
                        }
                        var ratio = Math.min(Math.max(hoursDay / expectedDaily, 0), 1);
                        var track = document.createElement("div");
                        track.className = "q3-calendar-day-progress";
                        track.setAttribute("role", "progressbar");
                        track.setAttribute("aria-valuemin", "0");
                        track.setAttribute("aria-valuemax", "100");
                        track.setAttribute("aria-valuenow", String(Math.round(ratio * 100)));
                        track.setAttribute(
                            "aria-label",
                            "Horas apontadas em relação à meta diária: " +
                                Math.round(ratio * 100) +
                                " por cento (" +
                                (Math.round(hoursDay * 100) / 100) +
                                " de " +
                                expectedDaily +
                                " horas)"
                        );
                        var fill = document.createElement("div");
                        fill.className = "q3-calendar-day-progress__fill";
                        fill.style.width = (ratio * 100).toFixed(2) + "%";
                        track.appendChild(fill);
                        content.appendChild(track);
                    }
                    var metricsRow = document.createElement("div");
                    metricsRow.className = "q3-calendar-day-metrics";

                    var meta = document.createElement("div");
                    meta.className = "q3-calendar-day-apontamentos";
                    meta.setAttribute("role", "group");
                    meta.setAttribute(
                        "aria-label",
                        n === 1 ? "1 apontamento neste dia" : String(n) + " apontamentos neste dia"
                    );
                    var ic = document.createElement("i");
                    ic.className = "fas fa-pencil-alt q3-calendar-day-apontamentos__icon";
                    ic.setAttribute("aria-hidden", "true");
                    var cnt = document.createElement("span");
                    cnt.className = "q3-calendar-day-apontamentos__count";
                    cnt.textContent = String(n);
                    meta.appendChild(ic);
                    meta.appendChild(cnt);

                    var money = document.createElement("div");
                    money.className = "q3-calendar-day-valor";
                    money.setAttribute("role", "group");
                    var payRaw = payMap[iso];
                    var payNum =
                        payRaw != null ? parseFloat(String(payRaw).replace(",", "."), 10) : 0;
                    if (isNaN(payNum) || payNum < 0) {
                        payNum = 0;
                    }
                    var payLabel = payNum.toLocaleString("pt-BR", {
                        minimumFractionDigits: 2,
                        maximumFractionDigits: 2,
                    });
                    money.setAttribute(
                        "aria-label",
                        "Valor estimado a receber neste dia: " + payLabel + " reais"
                    );
                    var moneySym = document.createElement("span");
                    moneySym.className = "q3-calendar-day-valor__symbol";
                    moneySym.textContent = "R$";
                    moneySym.setAttribute("aria-hidden", "true");
                    var moneyAmt = document.createElement("span");
                    moneyAmt.className = "q3-calendar-day-valor__amount";
                    moneyAmt.textContent = payLabel;
                    money.appendChild(moneySym);
                    money.appendChild(moneyAmt);

                    metricsRow.appendChild(meta);
                    metricsRow.appendChild(money);
                    var ownBirthdayThisCell =
                        bdayRule && viewMonth === bdayRule.month && day === bdayRule.day;
                    var colleagueNames = [];
                    publicBirthdays.forEach(function (row) {
                        if (row.month === viewMonth && row.day === day && row.display_name) {
                            colleagueNames.push(String(row.display_name));
                        }
                    });
                    if (ownBirthdayThisCell || colleagueNames.length) {
                        var dateLabel = pad2(day) + "/" + pad2(viewMonth) + "/" + viewYear;
                        var messageLines = [];
                        if (ownBirthdayThisCell) {
                            var myName =
                                (apiEl && apiEl.getAttribute("data-member-display-name")) ||
                                "Colaborador";
                            messageLines.push(
                                "É aniversário de " + myName + " nesta data (" + dateLabel + ")."
                            );
                        }
                        colleagueNames.forEach(function (nm) {
                            messageLines.push(
                                "Aniversário de " + nm + " nesta data (" + dateLabel + ")."
                            );
                        });
                        var bdayEl = document.createElement("button");
                        bdayEl.type = "button";
                        bdayEl.className = "q3-calendar-day-birthday";
                        bdayEl.setAttribute("data-date-iso", iso);
                        bdayEl.setAttribute("data-birthday-lines", JSON.stringify(messageLines));
                        if (prepared) {
                            bdayEl.disabled = true;
                            bdayEl.setAttribute(
                                "aria-label",
                                "Aniversário neste dia — prepare o apontamento para escolher o dia no calendário"
                            );
                        } else {
                            bdayEl.classList.add("q3-calendar-day-birthday--interactive");
                            bdayEl.setAttribute(
                                "aria-label",
                                messageLines.length === 1
                                    ? "Ver mensagem de aniversário"
                                    : "Ver mensagens de aniversário (" +
                                          String(messageLines.length) +
                                          ")"
                            );
                        }
                        var bIcon = document.createElement("i");
                        bIcon.className = "fas fa-birthday-cake q3-calendar-day-birthday__icon";
                        bIcon.setAttribute("aria-hidden", "true");
                        bdayEl.appendChild(bIcon);
                        metricsRow.appendChild(bdayEl);
                    }
                    content.appendChild(metricsRow);
                    td.appendChild(content);
                }
                tr.appendChild(td);
            });
            calendarBody.appendChild(tr);
        });

        calendarCard.classList.toggle("q3-calendar-card--prepared", prepared);
    }

    function fullCalendarRender() {
        renderHeading();
        if (!calendarBody || !calendarCard) {
            return;
        }
        fetchMonthCounts(viewYear, viewMonth).then(function (cal) {
            renderCalendar(cal || emptyMonthCalendarPayload());
        });
    }

    function shiftMonth(delta) {
        viewMonth += delta;
        if (viewMonth > 12) {
            viewMonth = 1;
            viewYear++;
        } else if (viewMonth < 1) {
            viewMonth = 12;
            viewYear--;
        }
        fullCalendarRender();
    }

    function goToCurrentMonth() {
        var t = localTodayParts();
        viewYear = t.y;
        viewMonth = t.m;
        fullCalendarRender();
    }

    function wireHoursSteppers() {
        var wrap = form.querySelector(".q1-hours-control");
        if (!wrap || !hoursInput) {
            return;
        }
        var btns = wrap.querySelectorAll("button");
        if (btns.length < 2) {
            return;
        }
        var step = 0.25;
        btns[0].addEventListener("click", function () {
            var v = parseFloat(hoursInput.value) || 0;
            hoursInput.value = String(Math.min(24, Math.round((v + step) * 100) / 100));
        });
        btns[1].addEventListener("click", function () {
            var v = parseFloat(hoursInput.value) || 0;
            hoursInput.value = String(Math.max(0, Math.round((v - step) * 100) / 100));
        });
    }

    function onPrepareClick() {
        if (!configured) {
            setCalendarStatus(
                "Configure departamento e template com o gestor antes de preparar.",
                "warn"
            );
            return;
        }
        if (getSelectedMode() === "timer") {
            return;
        }
        var payload = collectFormPayload();
        var mode = payload.entry_mode;
        if (mode === "duration") {
            var h = parseFloat(payload.hours);
            if (!payload.hours || isNaN(h) || h <= 0) {
                setCalendarStatus("Informe horas maiores que zero.", "warn");
                if (hoursInput) {
                    hoursInput.focus();
                }
                return;
            }
        } else if (mode === "time_range") {
            if (!payload.start_time || !payload.end_time) {
                setCalendarStatus("Informe horário de início e de fim.", "warn");
                return;
            }
        }
        try {
            sessionStorage.setItem(STORAGE_KEY, JSON.stringify(payload));
            sessionStorage.setItem(STORAGE_ARMED_KEY, "1");
        } catch (e) {
            setCalendarStatus("Não foi possível salvar o rascunho no navegador.", "warn");
            return;
        }
        setCalendarStatus("Pronto. Clique no dia no calendário para salvar.", "ok");
        fullCalendarRender();
        if (typeof window.xperienceShowToast === "function") {
            window.xperienceShowToast(
                "success",
                "Pré-apontamento pronto. Clique em um dia no calendário para salvar o apontamento."
            );
        }
        var calWrap = document.getElementById("q3-calendar-section-wrap");
        if (calWrap && typeof calWrap.scrollIntoView === "function") {
            calWrap.scrollIntoView({ behavior: "smooth", block: "start" });
        }
    }

    function setTimerStatusLine(msg) {
        var el = document.getElementById("q1-timer-status");
        if (el) {
            el.textContent = msg || "";
        }
    }

    function setPostTimerVisible(show, entryId) {
        var wrap = document.getElementById("q1-post-timer-wrap");
        var hid = document.getElementById("q1-timer-stopped-entry-id");
        if (wrap) {
            wrap.classList.toggle("q1-hidden", !show);
        }
        if (hid) {
            hid.value = entryId != null ? String(entryId) : "";
        }
        syncModeBlocks();
    }

    function refreshTimerDraft() {
        if (!timerDraftUrl) {
            return Promise.resolve();
        }
        return jsonFetch(timerDraftUrl, { method: "GET" }).then(function (out) {
            var btnStart = document.getElementById("q1-timer-start");
            var btnStop = document.getElementById("q1-timer-stop");
            draftEntryId = null;
            if (out.body && out.body.active && out.body.entry) {
                draftEntryId = out.body.entry.id;
                var started = out.body.entry.timer_started_at || "";
                var otCb = document.getElementById("q1-is-overtime");
                if (otCb) {
                    otCb.checked = !!out.body.entry.is_overtime;
                }
                setTimerStatusLine(
                    "Cronômetro em andamento"
                );
                if (btnStart) {
                    btnStart.disabled = true;
                }
                if (btnStop) {
                    btnStop.disabled = false;
                }
                setTimerRunningUi(true);
            } else {
                var postWrapClear = document.getElementById("q1-post-timer-wrap");
                var keepStatusForPendingSave =
                    postWrapClear && !postWrapClear.classList.contains("q1-hidden");
                if (!keepStatusForPendingSave) {
                    setTimerStatusLine("");
                }
                var otCb2 = document.getElementById("q1-is-overtime");
                if (otCb2) {
                    otCb2.checked = false;
                }
                if (btnStart) {
                    btnStart.disabled = false;
                }
                if (btnStop) {
                    btnStop.disabled = true;
                }
                setTimerRunningUi(false);
            }
            syncModeBlocks();
            return out;
        });
    }

    function onTimerStart() {
        if (!timerStartUrl) {
            return;
        }
        var rt = form.querySelector('input[name="launch_mode"][value="timer"]');
        if (rt) {
            rt.checked = true;
            syncModeBlocks();
        }
        var otEl = document.getElementById("q1-is-overtime");
        var startBody = JSON.stringify({ is_overtime: !!(otEl && otEl.checked) });
        jsonFetch(timerStartUrl, { method: "POST", body: startBody }).then(function (out) {
            if (!out.res.ok) {
                setTimerStatusLine((out.body && out.body.error) || "Não foi possível iniciar.");
                return;
            }
            setPostTimerVisible(false, null);
            refreshTimerDraft();
        });
    }

    function onTimerStop() {
        if (!timerStopUrl) {
            return;
        }
        var body = draftEntryId ? JSON.stringify({ entry_id: draftEntryId }) : "{}";
        jsonFetch(timerStopUrl, { method: "POST", body: body }).then(function (out) {
            if (!out.res.ok) {
                setTimerStatusLine((out.body && out.body.error) || "Não foi possível parar.");
                return;
            }
            var eid = out.body.entry && out.body.entry.id;
            setPostTimerVisible(true, eid);
            setTimerStatusLine("Cronômetro finalizado. Complete os campos do template, se necessário, e salve.");
            invalidateViewMonthCountsCache();
            if (calendarBody && calendarCard && headingEl) {
                fullCalendarRender();
            }
            refreshTimerDraft();
        });
    }

    function onTimerSaveTemplate() {
        if (!timerCompleteUrl) {
            return;
        }
        var hid = document.getElementById("q1-timer-stopped-entry-id");
        var eid = hid && hid.value ? parseInt(hid.value, 10) : 0;
        if (!eid) {
            setTimerStatusLine("Nenhum apontamento recente para completar.");
            return;
        }
        var fd = new FormData(form);
        var otEl = document.getElementById("q1-is-overtime");
        var body = {
            entry_id: eid,
            client_id: fd.get("client_id"),
            project_id: fd.get("project_id"),
            task_id: fd.get("task_id"),
            description: fd.get("description") != null ? String(fd.get("description")) : "",
            entry_type: fd.get("entry_type") != null ? String(fd.get("entry_type")) : "",
            is_overtime: !!(otEl && otEl.checked),
        };
        jsonFetch(timerCompleteUrl, { method: "POST", body: JSON.stringify(body) }).then(function (out) {
            if (!out.res.ok) {
                setTimerStatusLine((out.body && out.body.error) || "Erro ao salvar dados.");
                return;
            }
            setPostTimerVisible(false, null);
            setTimerStatusLine("Dados do apontamento atualizados.");
            invalidateViewMonthCountsCache();
            if (calendarBody && calendarCard && headingEl) {
                fullCalendarRender();
            }
            refreshTimerDraft();
        });
    }

    function onTimerDiscardPending() {
        if (!timerDiscardUrl) {
            return;
        }
        var hid = document.getElementById("q1-timer-stopped-entry-id");
        var eid = hid && hid.value ? parseInt(hid.value, 10) : 0;
        if (!eid) {
            setTimerStatusLine("Nenhum apontamento para descartar.");
            return;
        }
        jsonFetch(timerDiscardUrl, { method: "POST", body: JSON.stringify({ entry_id: eid }) }).then(function (out) {
            if (!out.res.ok) {
                setTimerStatusLine((out.body && out.body.error) || "Não foi possível descartar.");
                return;
            }
            setPostTimerVisible(false, null);
            setTimerStatusLine("");
            invalidateViewMonthCountsCache();
            if (calendarBody && calendarCard && headingEl) {
                fullCalendarRender();
            }
            refreshTimerDraft();
        });
    }

    function init() {
        var t = localTodayParts();
        viewYear = t.y;
        viewMonth = t.m;
        selectedIso = readStoredDate();

        var existing = readStoredPayload();
        if (existing && workspaceId && String(existing.workspace_id || "") !== String(workspaceId)) {
            try {
                sessionStorage.removeItem(STORAGE_KEY);
                sessionStorage.removeItem(STORAGE_DATE_KEY);
                sessionStorage.removeItem(STORAGE_ARMED_KEY);
            } catch (e2) { /* ignore */ }
            selectedIso = null;
        }

        form.querySelectorAll('input[name="launch_mode"]').forEach(function (r) {
            r.addEventListener("change", function () {
                syncModeBlocks();
                fullCalendarRender();
            });
        });

        if (btnPrev) {
            btnPrev.addEventListener("click", function () {
                shiftMonth(-1);
            });
        }
        if (btnNext) {
            btnNext.addEventListener("click", function () {
                shiftMonth(1);
            });
        }
        if (btnToday) {
            btnToday.addEventListener("click", function () {
                goToCurrentMonth();
            });
        }
        if (btnPrepare) {
            btnPrepare.addEventListener("click", onPrepareClick);
        }

        function isHotkeyTypingTarget(el) {
            if (!el || !el.tagName) {
                return false;
            }
            var tag = el.tagName.toLowerCase();
            if (tag === "textarea" || tag === "select") {
                return true;
            }
            if (tag === "input") {
                var typ = (el.type || "").toLowerCase();
                if (
                    typ === "button" ||
                    typ === "submit" ||
                    typ === "checkbox" ||
                    typ === "radio" ||
                    typ === "reset" ||
                    typ === "file" ||
                    typ === "hidden"
                ) {
                    return false;
                }
                return true;
            }
            return Boolean(el.isContentEditable);
        }

        function isAnyDialogOpen() {
            return Boolean(document.querySelector("dialog[open]"));
        }

        document.addEventListener(
            "keydown",
            function (ev) {
                if (!ev.ctrlKey || ev.metaKey || ev.altKey || ev.repeat) {
                    return;
                }
                if (ev.code !== "Space" && ev.key !== " ") {
                    return;
                }
                if (isHotkeyTypingTarget(ev.target)) {
                    return;
                }
                if (isAnyDialogOpen()) {
                    return;
                }
                if (!btnPrepare) {
                    return;
                }
                ev.preventDefault();
                onPrepareClick();
            },
            true
        );

        document.addEventListener(
            "keydown",
            function (ev) {
                if (ev.key !== "Escape" || ev.repeat) {
                    return;
                }
                if (!isCalendarSaveMode()) {
                    return;
                }
                if (isHotkeyTypingTarget(ev.target)) {
                    return;
                }
                if (isAnyDialogOpen()) {
                    return;
                }
                ev.preventDefault();
                try {
                    sessionStorage.setItem(STORAGE_ARMED_KEY, "0");
                } catch (eEsc) {
                    /* ignore */
                }
                setCalendarStatus(
                    "Modo calendário desativado (Esc). Os dados do pré-apontamento foram mantidos. " +
                        "Use Preparar apontamento ou Ctrl+Espaço para escolher o dia novamente.",
                    "ok"
                );
                fullCalendarRender();
            },
            true
        );

        var btnTs = document.getElementById("q1-timer-start");
        var btnTsp = document.getElementById("q1-timer-stop");
        var btnTsave = document.getElementById("q1-timer-save-template");
        var btnTdiscard = document.getElementById("q1-timer-discard-pending");
        if (btnTs) {
            btnTs.addEventListener("click", onTimerStart);
        }
        if (btnTsp) {
            btnTsp.addEventListener("click", onTimerStop);
        }
        if (btnTsave) {
            btnTsave.addEventListener("click", onTimerSaveTemplate);
        }
        if (btnTdiscard) {
            btnTdiscard.addEventListener("click", onTimerDiscardPending);
        }

        var infoDialog = document.getElementById("q1-pre-entry-info-dialog");
        var infoOpen = document.getElementById("q1-pre-entry-info-open");
        var infoClose = document.getElementById("q1-pre-entry-info-close");
        if (infoDialog && infoOpen && typeof infoDialog.showModal === "function") {
            infoOpen.addEventListener("click", function () {
                infoDialog.showModal();
            });
            if (infoClose) {
                infoClose.addEventListener("click", function () {
                    infoDialog.close();
                });
            }
            infoDialog.addEventListener("click", function (ev) {
                if (ev.target === infoDialog) {
                    infoDialog.close();
                }
            });
        }

        var historyInfoDialog = document.getElementById("q4-history-info-dialog");
        var historyInfoOpen = document.getElementById("q4-history-info-open");
        var historyInfoClose = document.getElementById("q4-history-info-close");
        if (historyInfoDialog && historyInfoOpen && typeof historyInfoDialog.showModal === "function") {
            historyInfoOpen.addEventListener("click", function () {
                historyInfoDialog.showModal();
            });
            if (historyInfoClose) {
                historyInfoClose.addEventListener("click", function () {
                    historyInfoDialog.close();
                });
            }
            historyInfoDialog.addEventListener("click", function (ev) {
                if (ev.target === historyInfoDialog) {
                    historyInfoDialog.close();
                }
            });
        }

        var birthdayDialog = document.getElementById("q3-birthday-info-dialog");
        var birthdayClose = document.getElementById("q3-birthday-info-close");
        if (birthdayDialog && typeof birthdayDialog.showModal === "function") {
            if (birthdayClose) {
                birthdayClose.addEventListener("click", function () {
                    birthdayDialog.close();
                });
            }
            birthdayDialog.addEventListener("click", function (ev) {
                if (ev.target === birthdayDialog) {
                    birthdayDialog.close();
                }
            });
        }

        wireCalendarDayInteractionOnce();
        wireDayModalActionsOnce();

        wireHoursSteppers();
        form.addEventListener("submit", function (ev) {
            ev.preventDefault();
        });

        syncModeBlocks();

        if (calendarBody && headingEl) {
            if (isCalendarSaveMode()) {
                setCalendarStatus("Pré-apontamento pronto. Clique no dia para salvar.", "ok");
            } else if (isStagedPreEntryForWorkspace()) {
                setCalendarStatus(
                    "Pré-apontamento salvo no navegador. Clique em Preparar apontamento ou Ctrl+Espaço para escolher o dia no calendário.",
                    "ok"
                );
            } else {
                setCalendarStatus(
                    "Escolha o modo acima, prepare e clique no dia — ou use o cronômetro.",
                    ""
                );
            }
            fullCalendarRender();
        }

        refreshTimerDraft().then(function () {
            if (draftEntryId) {
                var rt = form.querySelector('input[name="launch_mode"][value="timer"]');
                if (rt) {
                    rt.checked = true;
                }
                syncModeBlocks();
            }
        });

        setInterval(refreshTimerDraft, 60000);
    }

    init();
})();
