/**
 * Tabelas ordenáveis e paginadas (clientes, projetos e tarefas).
 */
(function () {
    function wireSortableTable(root) {
        if (!root) {
            return;
        }
        var thead = root.querySelector("[data-acf-sort-table-thead]");
        var tbody = root.querySelector("[data-acf-sort-table-tbody]");
        var pager = root.querySelector("[data-acf-sort-table-pager]");
        if (!tbody) {
            return;
        }

        var pageSize = parseInt(root.getAttribute("data-page-size") || "8", 10) || 8;
        var sortState = { key: null, dir: null };
        var currentPage = 1;

        function rows() {
            return Array.prototype.slice.call(tbody.querySelectorAll("tr.acf-sort-table__row"));
        }

        function updateSortIndicators() {
            if (!thead) {
                return;
            }
            thead.querySelectorAll("[data-sort-key]").forEach(function (btn) {
                var key = btn.getAttribute("data-sort-key");
                var icon = btn.querySelector(".acf-sort-table__sort-icon");
                btn.removeAttribute("aria-sort");
                if (icon) {
                    icon.className = "acf-sort-table__sort-icon fas fa-sort";
                }
                if (sortState.key === key && sortState.dir) {
                    btn.setAttribute("aria-sort", sortState.dir === "asc" ? "ascending" : "descending");
                    if (icon) {
                        icon.classList.remove("fa-sort");
                        icon.classList.add(sortState.dir === "asc" ? "fa-sort-up" : "fa-sort-down");
                    }
                }
            });
        }

        function totalPages() {
            var count = rows().length;
            if (!count) {
                return 0;
            }
            return Math.ceil(count / pageSize);
        }

        function goToPage(page) {
            var tp = totalPages();
            if (pager) {
                pager.innerHTML = "";
            }
            if (!tp) {
                return;
            }
            currentPage = Math.max(1, Math.min(page, tp));
            var start = (currentPage - 1) * pageSize;
            rows().forEach(function (row, idx) {
                row.style.display = idx >= start && idx < start + pageSize ? "" : "none";
            });
            if (!pager || tp <= 1) {
                return;
            }

            function addBtn(label, pageTarget, disabled, active) {
                var btn = document.createElement("button");
                btn.type = "button";
                btn.className = "acf-sort-table__pager-btn";
                if (active) {
                    btn.classList.add("acf-sort-table__pager-btn--active");
                }
                btn.textContent = label;
                btn.disabled = !!disabled;
                btn.addEventListener("click", function () {
                    goToPage(pageTarget);
                });
                pager.appendChild(btn);
            }

            addBtn("‹", currentPage - 1, currentPage <= 1, false);
            for (var i = 1; i <= tp; i++) {
                addBtn(String(i), i, false, i === currentPage);
            }
            addBtn("›", currentPage + 1, currentPage >= tp, false);
        }

        function sortRows() {
            var list = rows();
            if (!sortState.key || !sortState.dir) {
                list.sort(function (a, b) {
                    return (
                        parseInt(a.getAttribute("data-original-index") || "0", 10) -
                        parseInt(b.getAttribute("data-original-index") || "0", 10)
                    );
                });
            } else {
                var sortAttr = "data-sort-" + sortState.key;
                list.sort(function (a, b) {
                    var av = (a.getAttribute(sortAttr) || "").toLowerCase();
                    var bv = (b.getAttribute(sortAttr) || "").toLowerCase();
                    var cmp = av.localeCompare(bv, undefined, {
                        numeric: true,
                        sensitivity: "base",
                    });
                    return sortState.dir === "asc" ? cmp : -cmp;
                });
            }
            list.forEach(function (row) {
                tbody.appendChild(row);
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
                        sortState.key = null;
                        sortState.dir = null;
                    } else {
                        sortState.dir = "asc";
                    }
                    sortRows();
                });
            });
        }

        updateSortIndicators();
        goToPage(1);
    }

    function init() {
        document.querySelectorAll("[data-acf-sort-table-root]").forEach(wireSortableTable);
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }
})();
