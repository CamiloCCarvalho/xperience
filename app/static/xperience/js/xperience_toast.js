/**
 * Toasts no canto inferior (mesmo markup/estilo de Django messages em messages.html).
 * - xperienceShowToast(levelTag, text): exibe notificação programática (ex.: pré-apontamento).
 * - xperienceInitServerToastsFromDom(): liga auto-dismiss e botão fechar nos toasts já no HTML.
 */
(function (global) {
    var AUTO_MS = 4200;
    var FADE_MS = 380;

    function dismiss(el) {
        if (!el || el.getAttribute("data-toast-dismissed") === "1") {
            return;
        }
        el.setAttribute("data-toast-dismissed", "1");
        el.classList.add("toast-msg--leaving");
        window.setTimeout(function () {
            var root = document.getElementById("toast-messages-root");
            el.remove();
            if (root && root.children.length === 0) {
                root.remove();
            }
        }, FADE_MS);
    }

    function ensureRoot() {
        var root = document.getElementById("toast-messages-root");
        if (!root) {
            root = document.createElement("div");
            root.id = "toast-messages-root";
            root.className = "toast-messages";
            root.setAttribute("aria-live", "polite");
            root.setAttribute("aria-atomic", "false");
            document.body.appendChild(root);
        }
        return root;
    }

    function wireToastEl(el) {
        window.setTimeout(function () {
            dismiss(el);
        }, AUTO_MS);
        var btn = el.querySelector(".toast-msg__close");
        if (btn) {
            btn.addEventListener("click", function () {
                dismiss(el);
            });
        }
    }

    function initServerToastsFromDom() {
        var root = document.getElementById("toast-messages-root");
        if (!root) {
            return;
        }
        root.querySelectorAll(".toast-msg").forEach(function (el) {
            wireToastEl(el);
        });
    }

    /**
     * @param {string} levelTag success | error | warning | info | debug
     * @param {string} text texto puro (não HTML)
     */
    function showToast(levelTag, text) {
        var root = ensureRoot();
        var wrap = document.createElement("div");
        wrap.className = "toast-msg toast-msg--" + (levelTag || "info");
        var role =
            levelTag === "error" || levelTag === "warning" ? "alert" : "status";
        wrap.setAttribute("role", role);
        var span = document.createElement("span");
        span.className = "toast-msg__text";
        span.textContent = text != null ? String(text) : "";
        var btn = document.createElement("button");
        btn.type = "button";
        btn.className = "toast-msg__close";
        btn.setAttribute("aria-label", "Fechar notificação");
        btn.textContent = "\u00D7";
        wrap.appendChild(span);
        wrap.appendChild(btn);
        root.appendChild(wrap);
        wireToastEl(wrap);
    }

    global.xperienceShowToast = showToast;
    global.xperienceInitServerToastsFromDom = initServerToastsFromDom;
})(window);
