(() => {
    const body = document.body;
    const overlays = document.querySelectorAll(".auth-modal-overlay");
    const openButtons = document.querySelectorAll("[data-auth-target]");
    const closeButtons = document.querySelectorAll("[data-auth-close]");

    const closeAll = () => {
        overlays.forEach((overlay) => {
            overlay.classList.remove("is-open");
            overlay.setAttribute("aria-hidden", "true");
        });
        body.classList.remove("auth-modal-open");
    };

    const openModal = (modalId) => {
        const modal = document.getElementById(modalId);
        if (!modal) {
            return;
        }

        closeAll();
        modal.classList.add("is-open");
        modal.setAttribute("aria-hidden", "false");
        body.classList.add("auth-modal-open");
    };

    openButtons.forEach((button) => {
        button.addEventListener("click", () => {
            openModal(button.dataset.authTarget);
        });
    });

    closeButtons.forEach((button) => {
        button.addEventListener("click", () => {
            closeAll();
        });
    });

    overlays.forEach((overlay) => {
        overlay.addEventListener("click", (event) => {
            if (event.target === overlay) {
                closeAll();
            }
        });
    });

    document.addEventListener("keydown", (event) => {
        if (event.key === "Escape") {
            closeAll();
        }
    });

    if (window.homeAuthModalState?.showLogin) {
        openModal("login-modal");
    } else if (window.homeAuthModalState?.showRegister) {
        openModal("register-modal");
    }
})();
