(function () {
    function syncDocumentElementTheme() {
        var body = document.body;
        if (!body) {
            return;
        }
        var t = body.getAttribute("data-theme");
        if (t === "dark") {
            document.documentElement.setAttribute("data-theme", "dark");
        } else {
            document.documentElement.removeAttribute("data-theme");
        }
    }

    function init() {
        var body = document.body;
        var toggleButton = document.getElementById("theme-toggle-btn");
        var toggleIcon = document.getElementById("theme-toggle-icon");

        if (!toggleButton || !toggleIcon || !body) {
            return;
        }

        function isDarkTheme() {
            return body.getAttribute("data-theme") === "dark";
        }

        function updateToggleIcon() {
            var darkMode = isDarkTheme();
            toggleIcon.classList.toggle("fa-toggle-on", darkMode);
            toggleIcon.classList.toggle("fa-toggle-off", !darkMode);
            toggleButton.setAttribute(
                "aria-label",
                darkMode ? "Alternar para tema claro" : "Alternar para tema escuro"
            );
            syncDocumentElementTheme();
        }

        var savedTheme = localStorage.getItem("theme");
        if (savedTheme === "dark") {
            body.setAttribute("data-theme", "dark");
        } else if (savedTheme === "light") {
            body.setAttribute("data-theme", "");
        }

        updateToggleIcon();

        toggleButton.addEventListener("click", function () {
            if (isDarkTheme()) {
                body.setAttribute("data-theme", "");
                localStorage.setItem("theme", "light");
            } else {
                body.setAttribute("data-theme", "dark");
                localStorage.setItem("theme", "dark");
            }
            updateToggleIcon();
            var userMenu = document.getElementById("header-user-menu");
            if (
                userMenu &&
                typeof userMenu.open !== "undefined" &&
                userMenu.contains(toggleButton) &&
                userMenu.open
            ) {
                userMenu.open = false;
            }
        });
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }
})();
