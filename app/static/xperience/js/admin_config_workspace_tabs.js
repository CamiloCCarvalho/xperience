/**
 * Abas na configuração do workspace (gestor): Empresa, Clientes, Projetos, etc.
 * Estado na URL (#admin-config-ws-empresa, …).
 */
(function () {
    var PANEL_IDS = [
        "admin-config-ws-empresa",
        "admin-config-ws-clientes",
        "admin-config-ws-projetos",
        "admin-config-ws-tarefas",
        "admin-config-ws-membros",
        "admin-config-ws-fornecedores",
    ];

    function panelFromHash() {
        var id = (window.location.hash || "").replace(/^#/, "");
        if (PANEL_IDS.indexOf(id) >= 0) {
            return id;
        }
        return PANEL_IDS[0];
    }

    function activate(panelId) {
        var stack = document.querySelector(".admin-config-ws-stack");
        if (!stack) {
            return;
        }
        PANEL_IDS.forEach(function (id) {
            var el = document.getElementById(id);
            if (!el) {
                return;
            }
            var on = id === panelId;
            el.classList.toggle("admin-config-ws-panel--active", on);
            el.setAttribute("aria-hidden", on ? "false" : "true");
        });
        stack.querySelectorAll('a.admin-config-ws-tab[role="tab"]').forEach(function (tab) {
            var href = tab.getAttribute("href") || "";
            var tid = href.charAt(0) === "#" ? href.slice(1) : "";
            var on = tid === panelId;
            tab.setAttribute("aria-selected", on ? "true" : "false");
            tab.classList.toggle("admin-config-ws-tab--active", on);
        });
    }

    function sync() {
        var raw = (window.location.hash || "").replace(/^#/, "");
        if (raw && PANEL_IDS.indexOf(raw) < 0) {
            history.replaceState(
                null,
                "",
                window.location.pathname + window.location.search
            );
        }
        activate(panelFromHash());
    }

    function wireTabs() {
        var stack = document.querySelector(".admin-config-ws-stack");
        if (!stack) {
            return;
        }
        stack.querySelectorAll("a.admin-config-ws-tab").forEach(function (tab) {
            tab.addEventListener("click", function (e) {
                var href = tab.getAttribute("href") || "";
                if (href.charAt(0) !== "#") {
                    return;
                }
                var id = href.slice(1);
                if (PANEL_IDS.indexOf(id) < 0) {
                    return;
                }
                e.preventDefault();
                if (window.location.hash !== href) {
                    window.location.hash = id;
                } else {
                    activate(id);
                }
            });
        });
    }

    function init() {
        if (!document.querySelector(".admin-config-ws-stack")) {
            return;
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
