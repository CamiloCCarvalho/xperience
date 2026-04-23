/**
 * Membros e acessos: tabela, ordenação, vínculos cliente/projeto via fetch (sem reload).
 */
(function () {
    function getCookie(name) {
        var cookieValue = null;
        if (document.cookie && document.cookie !== "") {
            var cookies = document.cookie.split(";");
            for (var i = 0; i < cookies.length; i++) {
                var cookie = cookies[i].trim();
                if (cookie.substring(0, name.length + 1) === name + "=") {
                    cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                    break;
                }
            }
        }
        return cookieValue;
    }

    function postMemberAction(url, csrfToken, body) {
        return fetch(url, {
            method: "POST",
            headers: {
                "X-CSRFToken": csrfToken,
                "Content-Type": "application/x-www-form-urlencoded",
            },
            body: new URLSearchParams(body),
            credentials: "same-origin",
        }).then(function (res) {
            return res.text().then(function (text) {
                var data;
                try {
                    data = text ? JSON.parse(text) : {};
                } catch (e) {
                    data = { ok: false, error: text || "Resposta inválida." };
                }
                return { ok: res.ok, status: res.status, data: data };
            });
        });
    }

    function wireMembersAccess(root) {
        if (!root) {
            return;
        }
        var csrf = root.getAttribute("data-csrf-token") || getCookie("csrftoken") || "";
        var urlLinkClient = root.getAttribute("data-url-link-client") || "";
        var urlUnlinkClient = root.getAttribute("data-url-unlink-client") || "";
        var urlLinkProject = root.getAttribute("data-url-link-project") || "";
        var urlUnlinkProject = root.getAttribute("data-url-unlink-project") || "";
        var urlRemoveMember = root.getAttribute("data-url-remove-member") || "";
        var pageSize = parseInt(root.getAttribute("data-page-size") || "8", 10) || 8;

        var tbody = root.querySelector("[data-acf-members-tbody]");
        var thead = root.querySelector("[data-acf-members-thead]");
        var pager = root.querySelector("[data-acf-members-pager]");
        if (!tbody) {
            return;
        }

        var sortState = { key: null, dir: null };

        function updateSortIndicators() {
            if (!thead) {
                return;
            }
            thead.querySelectorAll("[data-sort-key]").forEach(function (btn) {
                var key = btn.getAttribute("data-sort-key");
                var icon = btn.querySelector(".acf-members__sort-icon");
                if (!icon) {
                    return;
                }
                icon.className = "acf-members__sort-icon fas fa-sort";
                btn.removeAttribute("aria-sort");
                if (sortState.key === key && sortState.dir) {
                    btn.setAttribute("aria-sort", sortState.dir === "asc" ? "ascending" : "descending");
                    icon.classList.remove("fa-sort");
                    icon.classList.add(sortState.dir === "asc" ? "fa-sort-up" : "fa-sort-down");
                }
            });
        }

        function sortRows() {
            var rows = Array.prototype.slice.call(
                tbody.querySelectorAll("tr.acf-members__row")
            );
            if (!rows.length) {
                return;
            }
            if (!sortState.key || !sortState.dir) {
                rows.sort(function (a, b) {
                    return (
                        parseInt(a.getAttribute("data-original-index") || "0", 10) -
                        parseInt(b.getAttribute("data-original-index") || "0", 10)
                    );
                });
            } else {
                var sk = "data-sort-" + sortState.key;
                rows.sort(function (a, b) {
                    var av = (a.getAttribute(sk) || "").toLowerCase();
                    var bv = (b.getAttribute(sk) || "").toLowerCase();
                    var cmp = av.localeCompare(bv, undefined, {
                        numeric: true,
                        sensitivity: "base",
                    });
                    return sortState.dir === "asc" ? cmp : -cmp;
                });
            }
            rows.forEach(function (tr) {
                tbody.appendChild(tr);
            });
            updateSortIndicators();
            var tp = totalPages();
            goToPage(tp ? Math.min(currentPage, tp) : 1);
        }

        if (thead) {
            thead.querySelectorAll("[data-sort-key]").forEach(function (btn) {
                btn.addEventListener("click", function () {
                    var key = btn.getAttribute("data-sort-key");
                    if (!key) {
                        return;
                    }
                    if (sortState.key !== key) {
                        sortState.key = key;
                        sortState.dir = "asc";
                    } else if (sortState.dir === "asc") {
                        sortState.dir = "desc";
                    } else if (sortState.dir === "desc") {
                        sortState.dir = null;
                        sortState.key = null;
                    } else {
                        sortState.dir = "asc";
                    }
                    sortRows();
                });
            });
        }

        var currentPage = 1;

        function totalPages() {
            var n = tbody.querySelectorAll("tr.acf-members__row").length;
            if (n === 0) {
                return 0;
            }
            return Math.ceil(n / pageSize);
        }

        function goToPage(p) {
            var tp = totalPages();
            if (pager) {
                pager.innerHTML = "";
            }
            if (tp === 0) {
                return;
            }
            currentPage = Math.min(Math.max(1, p), tp);
            var rows = tbody.querySelectorAll("tr.acf-members__row");
            var start = (currentPage - 1) * pageSize;
            rows.forEach(function (tr, i) {
                tr.style.display = i >= start && i < start + pageSize ? "" : "none";
            });
            if (pager) {
                if (tp <= 1) {
                    return;
                }
                function addBtn(label, disabled, page) {
                    var b = document.createElement("button");
                    b.type = "button";
                    b.className = "acf-members__pager-btn";
                    b.textContent = label;
                    b.disabled = !!disabled;
                    b.addEventListener("click", function () {
                        goToPage(page);
                    });
                    pager.appendChild(b);
                }
                addBtn("‹", currentPage <= 1, currentPage - 1);
                for (var i = 1; i <= tp; i++) {
                    (function (pi) {
                        var b = document.createElement("button");
                        b.type = "button";
                        b.className = "acf-members__pager-btn";
                        if (pi === currentPage) {
                            b.classList.add("acf-members__pager-btn--active");
                        }
                        b.textContent = String(pi);
                        b.addEventListener("click", function () {
                            goToPage(pi);
                        });
                        pager.appendChild(b);
                    })(i);
                }
                addBtn("›", currentPage >= tp, currentPage + 1);
            }
        }

        function addClientTag(cell, ucId, clientId, label) {
            var wrap = cell.querySelector("[data-acf-tags-clients]");
            if (!wrap) {
                return;
            }
            var span = document.createElement("span");
            span.className = "acf-members__tag acf-members__tag--client";
            span.setAttribute("data-uc-id", String(ucId));
            span.setAttribute("data-client-id", String(clientId));
            span.setAttribute("title", label);
            var tx = document.createElement("span");
            tx.className = "acf-members__tag-text";
            tx.textContent = label;
            var rm = document.createElement("button");
            rm.type = "button";
            rm.className = "acf-members__tag-x";
            rm.setAttribute("aria-label", "Remover cliente");
            rm.innerHTML = '<i class="fas fa-times" aria-hidden="true"></i>';
            span.appendChild(tx);
            span.appendChild(rm);
            wrap.appendChild(span);
        }

        function addProjectTag(cell, upId, projectId, label) {
            var wrap = cell.querySelector("[data-acf-tags-projects]");
            if (!wrap) {
                return;
            }
            var span = document.createElement("span");
            span.className = "acf-members__tag acf-members__tag--project";
            span.setAttribute("data-up-id", String(upId));
            span.setAttribute("data-project-id", String(projectId));
            span.setAttribute("title", label);
            var tx = document.createElement("span");
            tx.className = "acf-members__tag-text";
            tx.textContent = label;
            var rm = document.createElement("button");
            rm.type = "button";
            rm.className = "acf-members__tag-x";
            rm.setAttribute("aria-label", "Remover projeto");
            rm.innerHTML = '<i class="fas fa-times" aria-hidden="true"></i>';
            span.appendChild(tx);
            span.appendChild(rm);
            wrap.appendChild(span);
        }

        function syncSelectEnabled(select) {
            if (!select) {
                return;
            }
            var usable = false;
            for (var i = 0; i < select.options.length; i++) {
                var o = select.options[i];
                if (!o.value) {
                    continue;
                }
                if (!o.disabled && !o.hasAttribute("hidden")) {
                    usable = true;
                    break;
                }
            }
            select.disabled = !usable;
        }

        function hideLinkedOption(select, value) {
            var opt = select.querySelector('option[value="' + String(value) + '"]');
            if (opt) {
                opt.disabled = true;
                opt.setAttribute("hidden", "hidden");
                opt.classList.add("acf-members__opt--linked");
            }
            syncSelectEnabled(select);
        }

        function showLinkedOption(select, value) {
            var opt = select.querySelector('option[value="' + String(value) + '"]');
            if (opt) {
                opt.disabled = false;
                opt.removeAttribute("hidden");
                opt.classList.remove("acf-members__opt--linked");
            }
            syncSelectEnabled(select);
        }

        tbody.addEventListener("change", function (ev) {
            var sel = ev.target;
            if (!sel || sel.tagName !== "SELECT") {
                return;
            }
            if (!sel.classList.contains("acf-members__client-select")) {
                if (!sel.classList.contains("acf-members__project-select")) {
                    return;
                }
            }
            var row = sel.closest("tr.acf-members__row");
            if (!row) {
                return;
            }
            var uid = row.getAttribute("data-user-id");
            if (!uid) {
                return;
            }
            var val = sel.value;
            if (!val) {
                return;
            }
            var isClient = sel.classList.contains("acf-members__client-select");
            var url = isClient ? urlLinkClient : urlLinkProject;
            var body = isClient
                ? { user_id: uid, client_id: val }
                : { user_id: uid, project_id: val };
            postMemberAction(url, csrf, body).then(function (res) {
                if (!res.ok || !res.data || !res.data.ok) {
                    var err = (res.data && res.data.error) || "Não foi possível vincular.";
                    window.alert(err);
                    sel.value = "";
                    return;
                }
                sel.value = "";
                if (isClient) {
                    addClientTag(
                        row.querySelector("[data-acf-cell-clients]"),
                        res.data.uc_id,
                        res.data.client_id,
                        res.data.label
                    );
                    hideLinkedOption(sel, res.data.client_id);
                    updateRowSortAttrs(row);
                    refreshRowTagOverflow(row);
                } else {
                    addProjectTag(
                        row.querySelector("[data-acf-cell-projects]"),
                        res.data.up_id,
                        res.data.project_id,
                        res.data.label
                    );
                    hideLinkedOption(sel, res.data.project_id);
                    updateRowSortAttrs(row);
                    refreshRowTagOverflow(row);
                }
            });
        });

        function updateRowSortAttrs(row) {
            var clientsCell = row.querySelector("[data-acf-cell-clients]");
            var projectsCell = row.querySelector("[data-acf-cell-projects]");
            if (clientsCell) {
                var names = [];
                clientsCell.querySelectorAll(".acf-members__tag--client .acf-members__tag-text").forEach(function (el) {
                    names.push(el.textContent.trim().toLowerCase());
                });
                row.setAttribute("data-sort-clients", names.length ? names.join(",") : "zzzz");
            }
            if (projectsCell) {
                var pns = [];
                projectsCell.querySelectorAll(".acf-members__tag--project .acf-members__tag-text").forEach(function (el) {
                    pns.push(el.textContent.trim().toLowerCase());
                });
                row.setAttribute("data-sort-projects", pns.length ? pns.join(",") : "zzzz");
            }
        }

        function refreshTagOverflowInCell(cell) {
            if (!cell) {
                return;
            }
            var wrap = cell.querySelector(".acf-members__tags-wrap");
            var toggle = cell.querySelector("[data-acf-tags-toggle]");
            if (!wrap || !toggle) {
                return;
            }
            var tagsCount = wrap.querySelectorAll(".acf-members__tag").length;
            var shouldCollapse = tagsCount > 4;
            wrap.classList.remove("acf-members__tags-wrap--expanded");
            wrap.classList.remove("acf-members__tags-wrap--collapsed");
            toggle.classList.remove("acf-members__tags-toggle--placeholder");
            toggle.textContent = "Ver todos";
            toggle.setAttribute("aria-expanded", "false");
            toggle.setAttribute("aria-hidden", "false");
            if (!shouldCollapse) {
                toggle.classList.add("acf-members__tags-toggle--placeholder");
                toggle.setAttribute("aria-hidden", "true");
                return;
            }
            wrap.classList.add("acf-members__tags-wrap--collapsed");
            toggle.textContent = "Ver todos (" + String(tagsCount) + ")";
            toggle.setAttribute("aria-expanded", "false");
        }

        function refreshRowTagOverflow(row) {
            if (!row) {
                return;
            }
            refreshTagOverflowInCell(row.querySelector("[data-acf-cell-clients]"));
            refreshTagOverflowInCell(row.querySelector("[data-acf-cell-projects]"));
        }

        tbody.addEventListener("click", function (ev) {
            var btn = ev.target.closest(".acf-members__tag-x");
            if (btn) {
                var tag = btn.closest(".acf-members__tag");
                var row = btn.closest("tr.acf-members__row");
                if (!tag || !row) {
                    return;
                }
                var uid = row.getAttribute("data-user-id");
                var cellClients = row.querySelector("[data-acf-cell-clients]");
                var cellProjects = row.querySelector("[data-acf-cell-projects]");
                if (tag.classList.contains("acf-members__tag--client")) {
                    var ucid = tag.getAttribute("data-uc-id");
                    var cid = tag.getAttribute("data-client-id");
                    var labelEl = tag.querySelector(".acf-members__tag-text");
                    var label = labelEl ? labelEl.textContent : "";
                    postMemberAction(urlUnlinkClient, csrf, { uc_id: ucid }).then(function (res) {
                        if (!res.ok || !res.data || !res.data.ok) {
                            window.alert((res.data && res.data.error) || "Erro ao remover.");
                            return;
                        }
                        tag.remove();
                        var sel = cellClients.querySelector(".acf-members__client-select");
                        if (sel && cid) {
                            showLinkedOption(sel, cid);
                        }
                        updateRowSortAttrs(row);
                        refreshRowTagOverflow(row);
                    });
                } else if (tag.classList.contains("acf-members__tag--project")) {
                    var upid = tag.getAttribute("data-up-id");
                    var pid = tag.getAttribute("data-project-id");
                    var labelP = tag.querySelector(".acf-members__tag-text");
                    var textP = labelP ? labelP.textContent : "";
                    postMemberAction(urlUnlinkProject, csrf, { up_id: upid }).then(function (res) {
                        if (!res.ok || !res.data || !res.data.ok) {
                            window.alert((res.data && res.data.error) || "Erro ao remover.");
                            return;
                        }
                        tag.remove();
                        var s2 = cellProjects.querySelector(".acf-members__project-select");
                        if (s2 && pid) {
                            showLinkedOption(s2, pid);
                        }
                        updateRowSortAttrs(row);
                        refreshRowTagOverflow(row);
                    });
                }
                return;
            }
            var toggle = ev.target.closest("[data-acf-tags-toggle]");
            if (toggle) {
                if (toggle.classList.contains("acf-members__tags-toggle--placeholder")) {
                    return;
                }
                var tagsCell = toggle.closest(".acf-members__td--tags");
                var wrap = tagsCell ? tagsCell.querySelector(".acf-members__tags-wrap") : null;
                if (!wrap) {
                    return;
                }
                var expanded = wrap.classList.contains("acf-members__tags-wrap--expanded");
                if (expanded) {
                    wrap.classList.remove("acf-members__tags-wrap--expanded");
                    wrap.classList.add("acf-members__tags-wrap--collapsed");
                    var countCollapsed = wrap.querySelectorAll(".acf-members__tag").length;
                    toggle.textContent = "Ver todos (" + String(countCollapsed) + ")";
                    toggle.setAttribute("aria-expanded", "false");
                } else {
                    toggle.textContent = "Recolher";
                    wrap.classList.remove("acf-members__tags-wrap--collapsed");
                    wrap.classList.add("acf-members__tags-wrap--expanded");
                    toggle.setAttribute("aria-expanded", "true");
                }
                return;
            }
            var trash = ev.target.closest(".acf-members__row-remove");
            if (!trash || trash.disabled) {
                return;
            }
            var tr = trash.closest("tr.acf-members__row");
            if (!tr) {
                return;
            }
            var uid = tr.getAttribute("data-user-id");
            if (
                !window.confirm(
                    "Remover este membro do workspace? Os vínculos de cliente e projeto serão perdidos."
                )
            ) {
                return;
            }
            postMemberAction(urlRemoveMember, csrf, { user_id: uid }).then(function (res) {
                if (!res.ok || !res.data || !res.data.ok) {
                    window.alert((res.data && res.data.error) || "Não foi possível remover.");
                    return;
                }
                tr.remove();
                var nextTp = totalPages();
                goToPage(nextTp ? Math.min(currentPage, nextTp) : 1);
            });
        });

        updateSortIndicators();
        root.querySelectorAll(".acf-members__client-select, .acf-members__project-select").forEach(syncSelectEnabled);
        root.querySelectorAll("tr.acf-members__row").forEach(refreshRowTagOverflow);
        goToPage(1);
    }

    function init() {
        document.querySelectorAll("[data-acf-members-access]").forEach(wireMembersAccess);
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }
})();
