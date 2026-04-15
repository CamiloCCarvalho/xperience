/**
 * Home Spaceon: modo de lançamento (horas / intervalo / cronômetro), calendário + manual/create,
 * timer draft/stop e conclusão de template pós-cronômetro.
 */
(function () {
    var STORAGE_KEY = "xperience_pre_entry";
    var STORAGE_DATE_KEY = "xperience_pre_entry_target_date";

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
    var hintEl = document.getElementById("q1-pre-entry-hint");

    if (!form || !apiEl) {
        return;
    }

    var manualCreateUrl = apiEl.getAttribute("data-manual-create-url") || "";
    var monthCountsUrl = apiEl.getAttribute("data-month-counts-url") || "";
    var timerDraftUrl = apiEl.getAttribute("data-timer-draft-url") || "";
    var timerStartUrl = apiEl.getAttribute("data-timer-start-url") || "";
    var timerStopUrl = apiEl.getAttribute("data-timer-stop-url") || "";
    var timerCompleteUrl = apiEl.getAttribute("data-timer-complete-url") || "";
    var workspaceId = apiEl.getAttribute("data-workspace-id") || "";
    var configured = form.getAttribute("data-configured") === "true";

    var saving = false;
    var viewYear;
    var viewMonth;
    var selectedIso = null;
    var draftEntryId = null;
    var countsCache = {};

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

    function syncModeBlocks() {
        var mode = getSelectedMode();
        var bd = document.getElementById("q1-block-duration");
        var br = document.getElementById("q1-block-range");
        var bt = document.getElementById("q1-block-timer");
        var calWrap = document.getElementById("q3-calendar-section-wrap");
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
        if (calWrap) {
            calWrap.classList.toggle("q1-hidden", mode === "timer");
        }
        if (hintEl) {
            if (mode === "timer") {
                hintEl.innerHTML =
                    "Use <strong>Iniciar cronômetro</strong> e <strong>Parar</strong> quando terminar. " +
                    "Depois, se o template exigir, complete os campos e clique em <strong>Salvar dados do apontamento</strong>.";
            } else if (mode === "time_range") {
                hintEl.innerHTML =
                    "Informe <strong>início e fim</strong>, os demais campos do template e clique em <strong>Preparar apontamento</strong>. " +
                    "Em seguida clique no dia no calendário para salvar.";
            } else {
                hintEl.innerHTML =
                    "Informe as <strong>horas</strong> e os campos do template e clique em <strong>Preparar apontamento</strong>. " +
                    "Depois clique no dia no calendário para salvar.";
            }
        }
        lockModeRadios(!!draftEntryId);
    }

    function lockModeRadios(lock) {
        form.querySelectorAll('input[name="launch_mode"]').forEach(function (el) {
            if (el.value !== "timer") {
                el.disabled = !!lock;
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

    function isPreparedForWorkspace() {
        var p = readStoredPayload();
        if (!p || !workspaceId || p.entry_mode === "timer") {
            return false;
        }
        if (p.workspace_id == null || p.workspace_id === "") {
            return false;
        }
        return String(p.workspace_id) === String(workspaceId);
    }

    function collectFormPayload() {
        var fd = new FormData(form);
        var mode = getSelectedMode();
        var o = {
            workspace_id: workspaceId ? Number(workspaceId) : null,
            entry_mode: mode,
            client_id: fd.get("client_id") != null ? String(fd.get("client_id")) : "",
            project_id: fd.get("project_id") != null ? String(fd.get("project_id")) : "",
            task_id: fd.get("task_id") != null ? String(fd.get("task_id")) : "",
            description: fd.get("description") != null ? String(fd.get("description")) : "",
            entry_type: fd.get("entry_type") != null ? String(fd.get("entry_type")) : "",
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

    function monthCountsCacheKey(y, m) {
        return String(y) + "-" + String(m);
    }

    function invalidateViewMonthCountsCache() {
        delete countsCache[monthCountsCacheKey(viewYear, viewMonth)];
    }

    function fetchMonthCounts(y, m) {
        var key = monthCountsCacheKey(y, m);
        if (Object.prototype.hasOwnProperty.call(countsCache, key)) {
            return Promise.resolve(countsCache[key]);
        }
        if (!monthCountsUrl) {
            countsCache[key] = {};
            return Promise.resolve({});
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
            var map = {};
            if (out.res.ok && out.body && out.body.by_date && typeof out.body.by_date === "object") {
                map = out.body.by_date;
            }
            countsCache[key] = map;
            return map;
        }).catch(function () {
            countsCache[key] = {};
            return {};
        });
    }

    function renderHeading() {
        if (headingEl) {
            headingEl.textContent = MONTH_NAMES_PT[viewMonth - 1] + " " + viewYear;
        }
    }

    function renderCalendar(byDate) {
        if (!calendarBody || !calendarCard) {
            return;
        }
        var map = byDate && typeof byDate === "object" ? byDate : {};
        var prepared = isPreparedForWorkspace();
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
                    content.appendChild(meta);
                    td.appendChild(content);
                }
                tr.appendChild(td);
            });
            calendarBody.appendChild(tr);
        });

        calendarCard.classList.toggle("q3-calendar-card--prepared", prepared);
    }

    function attachDayClicks() {
        if (!calendarBody || !manualCreateUrl) {
            return;
        }
        calendarBody.querySelectorAll("td.calendar-day--selectable").forEach(function (td) {
            td.addEventListener("click", function () {
                var iso = td.getAttribute("data-date-iso");
                if (!iso || saving) {
                    return;
                }
                var payload = readStoredPayload();
                if (!payload) {
                    setCalendarStatus("Prepare o apontamento antes de escolher o dia.", "warn");
                    return;
                }
                payload.date = iso;
                saving = true;
                calendarCard.classList.add("q3-calendar-card--saving");
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
                        } catch (e2) { /* ignore */ }
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
                        calendarCard.classList.remove("q3-calendar-card--saving");
                    });
            });
        });
    }

    function fullCalendarRender() {
        renderHeading();
        if (!calendarBody || !calendarCard) {
            return;
        }
        fetchMonthCounts(viewYear, viewMonth).then(function (byDate) {
            renderCalendar(byDate || {});
            attachDayClicks();
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
        } catch (e) {
            setCalendarStatus("Não foi possível salvar o rascunho no navegador.", "warn");
            return;
        }
        setCalendarStatus("Pronto. Clique no dia no calendário para salvar.", "ok");
        fullCalendarRender();
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
                setTimerStatusLine(
                    "Cronômetro em andamento" + (started ? " (início: " + started + ")." : ".")
                );
                if (btnStart) {
                    btnStart.disabled = true;
                }
                if (btnStop) {
                    btnStop.disabled = false;
                }
                lockModeRadios(true);
            } else {
                setTimerStatusLine("");
                if (btnStart) {
                    btnStart.disabled = false;
                }
                if (btnStop) {
                    btnStop.disabled = true;
                }
                lockModeRadios(false);
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
        jsonFetch(timerStartUrl, { method: "POST", body: "{}" }).then(function (out) {
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
        var body = {
            entry_id: eid,
            client_id: fd.get("client_id"),
            project_id: fd.get("project_id"),
            task_id: fd.get("task_id"),
            description: fd.get("description") != null ? String(fd.get("description")) : "",
            entry_type: fd.get("entry_type") != null ? String(fd.get("entry_type")) : "",
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

        var btnTs = document.getElementById("q1-timer-start");
        var btnTsp = document.getElementById("q1-timer-stop");
        var btnTsave = document.getElementById("q1-timer-save-template");
        if (btnTs) {
            btnTs.addEventListener("click", onTimerStart);
        }
        if (btnTsp) {
            btnTsp.addEventListener("click", onTimerStop);
        }
        if (btnTsave) {
            btnTsave.addEventListener("click", onTimerSaveTemplate);
        }

        wireHoursSteppers();
        form.addEventListener("submit", function (ev) {
            ev.preventDefault();
        });

        syncModeBlocks();

        if (calendarBody && headingEl) {
            if (isPreparedForWorkspace()) {
                setCalendarStatus("Pré-apontamento pronto. Clique no dia para salvar.", "ok");
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
