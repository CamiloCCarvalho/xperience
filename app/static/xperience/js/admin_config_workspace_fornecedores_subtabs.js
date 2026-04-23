/**
 * Sub-abas dentro de Fornecedores (Vínculo | Cargos | Remuneração) — hashes #admin-config-ws-fornecedores-*.
 */
(function () {
    var SUB_IDS = [
        "admin-config-ws-fornecedores-vinculo",
        "admin-config-ws-fornecedores-cargos",
        "admin-config-ws-fornecedores-remuneracao",
    ];

    function activeSubIdFromHash() {
        var raw = (window.location.hash || "").replace(/^#/, "");
        if (SUB_IDS.indexOf(raw) >= 0) {
            return raw;
        }
        if (raw === "admin-config-ws-fornecedores") {
            return "admin-config-ws-fornecedores-vinculo";
        }
        return "admin-config-ws-fornecedores-vinculo";
    }

    function activateSub(panelId) {
        var stack = document.querySelector("[data-admin-fornecedores-sub-stack]");
        if (!stack) {
            return;
        }
        SUB_IDS.forEach(function (id) {
            var el = document.getElementById(id);
            if (!el) {
                return;
            }
            var on = id === panelId;
            el.classList.toggle("admin-tt-panel--active", on);
            el.setAttribute("aria-hidden", on ? "false" : "true");
        });
        stack.querySelectorAll("nav.admin-tt-tabs a.admin-tt-tab").forEach(function (tab) {
            var href = tab.getAttribute("href") || "";
            var tid = href.charAt(0) === "#" ? href.slice(1) : "";
            var on = tid === panelId;
            tab.setAttribute("aria-selected", on ? "true" : "false");
            tab.classList.toggle("admin-tt-tab--active", on);
        });
    }

    function syncSub() {
        var outer = document.getElementById("admin-config-ws-fornecedores");
        if (!outer || !outer.classList.contains("admin-tt-panel--active")) {
            return;
        }
        activateSub(activeSubIdFromHash());
    }

    function wireSubTabs() {
        var stack = document.querySelector("[data-admin-fornecedores-sub-stack]");
        if (!stack) {
            return;
        }
        stack.querySelectorAll("nav.admin-tt-tabs a.admin-tt-tab").forEach(function (tab) {
            tab.addEventListener("click", function (e) {
                var href = tab.getAttribute("href") || "";
                if (href.charAt(0) !== "#") {
                    return;
                }
                var id = href.slice(1);
                if (SUB_IDS.indexOf(id) < 0) {
                    return;
                }
                e.preventDefault();
                if (window.location.hash !== href) {
                    window.location.hash = id;
                } else {
                    activateSub(id);
                }
            });
        });
    }

    function init() {
        wireSubTabs();
        syncSub();
        window.addEventListener("hashchange", syncSub);
        window.addEventListener("admin-config-ws-outer-tab-synced", syncSub);
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }
})();
