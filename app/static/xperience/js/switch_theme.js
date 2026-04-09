(function () {
    const body = document.body;
    const toggleButton = document.getElementById("theme-toggle-btn");
    const toggleIcon = document.getElementById("theme-toggle-icon");

    if (!toggleButton || !toggleIcon) {
        return;
    }

    function isDarkTheme() {
        return body.getAttribute("data-theme") === "dark";
    }

    function updateToggleIcon() {
        const darkMode = isDarkTheme();
        toggleIcon.classList.toggle("fa-toggle-on", darkMode);
        toggleIcon.classList.toggle("fa-toggle-off", !darkMode);
        toggleButton.setAttribute(
            "aria-label",
            darkMode ? "Alternar para tema claro" : "Alternar para tema escuro"
        );
    }

    const savedTheme = localStorage.getItem("theme");
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
    });
})();