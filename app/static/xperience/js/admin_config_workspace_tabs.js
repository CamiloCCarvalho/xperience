/**
 * Abas na configuração do workspace (gestor): Empresa, Caixa, Metas, …, Vínculo, Cargos, Remuneração.
 * Estado na URL (#admin-config-ws-empresa, …). Mesmo padrão visual que admin-tt (faixa verde + painéis).
 * Compat.: #admin-config-ws-fornecedores e hashes antigos fornecedores-* redirecionam para os novos ids.
 */
(function () {
    var PANEL_IDS = [
        "admin-config-ws-empresa",
        "admin-config-ws-caixa",
        "admin-config-ws-metas",
        "admin-config-ws-clientes",
        "admin-config-ws-projetos",
        "admin-config-ws-tarefas",
        "admin-config-ws-membros",
        "admin-config-ws-vinculo",
        "admin-config-ws-cargos",
        "admin-config-ws-remuneracao",
    ];

    /** @type {Record<string, string>} */
    var LEGACY_HASH_MAP = {
        "admin-config-ws-fornecedores": "admin-config-ws-vinculo",
        "admin-config-ws-fornecedores-vinculo": "admin-config-ws-vinculo",
        "admin-config-ws-fornecedores-cargos": "admin-config-ws-cargos",
        "admin-config-ws-fornecedores-remuneracao": "admin-config-ws-remuneracao",
    };

    function normalizePanelId(raw) {
        if (LEGACY_HASH_MAP[raw]) {
            return LEGACY_HASH_MAP[raw];
        }
        return raw;
    }

    function panelFromHash() {
        var id = (window.location.hash || "").replace(/^#/, "");
        id = normalizePanelId(id);
        if (PANEL_IDS.indexOf(id) >= 0) {
            return id;
        }
        return PANEL_IDS[0];
    }

    function isRecognizedHash(raw) {
        if (!raw) {
            return true;
        }
        var n = normalizePanelId(raw);
        return PANEL_IDS.indexOf(n) >= 0 || LEGACY_HASH_MAP[raw] !== undefined;
    }

    function activate(panelId) {
        var stack = document.querySelector(".admin-config-ws-main .admin-tt-stack");
        if (!stack) {
            return;
        }
        PANEL_IDS.forEach(function (id) {
            var el = document.getElementById(id);
            if (!el) {
                return;
            }
            var on = id === panelId;
            el.classList.toggle("admin-tt-panel--active", on);
            el.setAttribute("aria-hidden", on ? "false" : "true");
        });
        var mainShell = stack.firstElementChild;
        if (mainShell && mainShell.classList.contains("admin-tt-tabbed-shell")) {
            mainShell.querySelectorAll('header nav.admin-tt-tabs a.admin-tt-tab[role="tab"]').forEach(function (tab) {
                var href = tab.getAttribute("href") || "";
                var tid = href.charAt(0) === "#" ? href.slice(1) : "";
                tid = normalizePanelId(tid);
                var on = tid === panelId;
                tab.setAttribute("aria-selected", on ? "true" : "false");
                tab.classList.toggle("admin-tt-tab--active", on);
            });
        }
    }

    function sync() {
        var raw = (window.location.hash || "").replace(/^#/, "");
        if (raw && LEGACY_HASH_MAP[raw]) {
            history.replaceState(null, "", window.location.pathname + window.location.search + "#" + LEGACY_HASH_MAP[raw]);
        }
        var effective = (window.location.hash || "").replace(/^#/, "");
        if (effective && !isRecognizedHash(effective)) {
            history.replaceState(null, "", window.location.pathname + window.location.search);
        }
        activate(panelFromHash());
    }

    function wireTabs() {
        var stack = document.querySelector(".admin-config-ws-main .admin-tt-stack");
        if (!stack) {
            return;
        }
        var mainShell = stack.firstElementChild;
        if (!mainShell || !mainShell.classList.contains("admin-tt-tabbed-shell")) {
            return;
        }
        mainShell.querySelectorAll("header nav.admin-tt-tabs a.admin-tt-tab").forEach(function (tab) {
            tab.addEventListener("click", function (e) {
                var href = tab.getAttribute("href") || "";
                if (href.charAt(0) !== "#") {
                    return;
                }
                var id = normalizePanelId(href.slice(1));
                if (PANEL_IDS.indexOf(id) < 0) {
                    return;
                }
                e.preventDefault();
                var targetHref = "#" + id;
                if (window.location.hash !== targetHref) {
                    window.location.hash = id;
                } else {
                    activate(id);
                }
            });
        });
    }

    function init() {
        var stack = document.querySelector(".admin-config-ws-main .admin-tt-stack");
        if (!stack) {
            return;
        }
        var force = stack.getAttribute("data-admin-config-force-hash");
        if (force && window.location.hash !== force) {
            window.location.hash = force;
        }
        sync();
        wireTabs();
        window.addEventListener("hashchange", sync);
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }
})();
