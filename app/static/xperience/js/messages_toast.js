(function () {
    var AUTO_MS = 4200;
    var FADE_MS = 380;
    var root = document.getElementById("toast-messages-root");
    if (!root) {
        return;
    }

    function dismiss(el) {
        if (!el || el.getAttribute("data-toast-dismissed") === "1") {
            return;
        }
        el.setAttribute("data-toast-dismissed", "1");
        el.classList.add("toast-msg--leaving");
        window.setTimeout(function () {
            el.remove();
            if (root && root.children.length === 0) {
                root.remove();
            }
        }, FADE_MS);
    }

    root.querySelectorAll(".toast-msg").forEach(function (el) {
        window.setTimeout(function () {
            dismiss(el);
        }, AUTO_MS);
        var btn = el.querySelector(".toast-msg__close");
        if (btn) {
            btn.addEventListener("click", function () {
                dismiss(el);
            });
        }
    });
})();
