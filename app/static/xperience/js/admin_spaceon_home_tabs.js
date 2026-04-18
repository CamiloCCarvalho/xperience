/**
 * Abas horizontais na home admin Spaceon (Templates / Expedientes / Departamentos / Membros).
 * Estado persistido via hash da URL (#admin-tt-templates, etc.).
 */
(function () {
    var PANEL_IDS = [
        "admin-tt-templates",
        "admin-tt-expedientes",
        "admin-tt-departamentos",
        "admin-tt-membros",
    ];

    function panelFromHash() {
        var id = (window.location.hash || "").replace(/^#/, "");
        if (PANEL_IDS.indexOf(id) >= 0) {
            return id;
        }
        return PANEL_IDS[0];
    }

    function activate(panelId) {
        var stack = document.querySelector(".admin-spaceon-home .admin-tt-stack");
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
        stack.querySelectorAll('a.admin-tt-tab[role="tab"]').forEach(function (tab) {
            var href = tab.getAttribute("href") || "";
            var tid = href.charAt(0) === "#" ? href.slice(1) : "";
            var on = tid === panelId;
            tab.setAttribute("aria-selected", on ? "true" : "false");
            tab.classList.toggle("admin-tt-tab--active", on);
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
        var stack = document.querySelector(".admin-spaceon-home .admin-tt-stack");
        if (!stack) {
            return;
        }
        stack.querySelectorAll("a.admin-tt-tab").forEach(function (tab) {
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
        var stack = document.querySelector(".admin-spaceon-home .admin-tt-stack");
        if (!stack) {
            return;
        }
        var force = stack.getAttribute("data-admin-tt-force-hash");
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
