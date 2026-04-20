/**
 * Modais de edição: expediente, departamento e vínculo membro↔departamento (admin home).
 */
(function () {
    function wireScheduleEdit() {
        var dialog = document.getElementById("admin-sch-edit-dialog");
        if (!dialog || typeof dialog.showModal !== "function") {
            return;
        }

        var idInput = document.getElementById("admin-sch-edit-id");
        var nameInput = document.getElementById("id_sch_edit-name");
        var hoursInput = document.getElementById("id_sch_edit-expected_hours_per_day");
        var fixedInput = document.getElementById("id_sch_edit-has_fixed_days");

        function setWorkingDays(csv) {
            var chosen = {};
            (csv || "").split(",").forEach(function (part) {
                var v = part.trim();
                if (v) {
                    chosen[v] = true;
                }
            });
            dialog.querySelectorAll('input[name="sch_edit-working_days_pick"]').forEach(function (inp) {
                inp.checked = !!chosen[inp.value];
            });
        }

        function openFromButton(btn) {
            var d = btn.dataset;
            if (idInput) {
                idInput.value = d.scheduleId || "";
            }
            if (nameInput) {
                nameInput.value = d.name || "";
            }
            if (hoursInput) {
                hoursInput.value = d.hours != null && d.hours !== "" ? d.hours : "";
            }
            if (fixedInput) {
                fixedInput.checked = d.hasFixedDays === "1";
            }
            setWorkingDays(d.workingDays || "");
            dialog.showModal();
        }

        document.querySelectorAll("[data-admin-tt-schedule-edit]").forEach(function (btn) {
            btn.addEventListener("click", function () {
                openFromButton(this);
            });
        });

        var closeBtn = document.getElementById("admin-sch-edit-close");
        if (closeBtn) {
            closeBtn.addEventListener("click", function () {
                dialog.close();
            });
        }

        dialog.addEventListener("click", function (ev) {
            if (ev.target === dialog) {
                dialog.close();
            }
        });

        if (dialog.getAttribute("data-auto-open") === "1") {
            dialog.showModal();
            dialog.removeAttribute("data-auto-open");
        }
    }

    function wireScheduleCreate() {
        var dialog = document.getElementById("admin-sch-create-dialog");
        if (!dialog || typeof dialog.showModal !== "function") {
            return;
        }

        var openBtn = document.getElementById("admin-sch-create-open");
        if (openBtn) {
            openBtn.addEventListener("click", function () {
                dialog.showModal();
            });
        }

        var closeBtn = document.getElementById("admin-sch-create-close");
        if (closeBtn) {
            closeBtn.addEventListener("click", function () {
                dialog.close();
            });
        }

        dialog.addEventListener("click", function (ev) {
            if (ev.target === dialog) {
                dialog.close();
            }
        });

        if (dialog.getAttribute("data-auto-open") === "1") {
            dialog.showModal();
            dialog.removeAttribute("data-auto-open");
        }
    }

    function wireDepartmentCreate() {
        var dialog = document.getElementById("admin-dept-create-dialog");
        if (!dialog || typeof dialog.showModal !== "function") {
            return;
        }

        var openBtn = document.getElementById("admin-dept-create-open");
        if (openBtn) {
            openBtn.addEventListener("click", function () {
                dialog.showModal();
            });
        }

        var closeBtn = document.getElementById("admin-dept-create-close");
        if (closeBtn) {
            closeBtn.addEventListener("click", function () {
                dialog.close();
            });
        }

        dialog.addEventListener("click", function (ev) {
            if (ev.target === dialog) {
                dialog.close();
            }
        });

        if (dialog.getAttribute("data-auto-open") === "1") {
            dialog.showModal();
            dialog.removeAttribute("data-auto-open");
        }
    }

    function wireDeptEdit() {
        var dialog = document.getElementById("admin-dept-edit-dialog");
        if (!dialog || typeof dialog.showModal !== "function") {
            return;
        }

        var idInput = document.getElementById("admin-dept-edit-id");
        var nameInput = document.getElementById("id_dept_edit-name");
        var scheduleSel = document.getElementById("id_dept_edit-schedule");
        var templateSel = document.getElementById("id_dept_edit-template");
        var modeSel = document.getElementById("id_dept_edit-time_tracking_mode");
        var canEdit = document.getElementById("id_dept_edit-can_edit_time_entries");
        var canDel = document.getElementById("id_dept_edit-can_delete_time_entries");

        function openFromButton(btn) {
            var d = btn.dataset;
            if (idInput) {
                idInput.value = d.deptId || "";
            }
            if (nameInput) {
                nameInput.value = d.name || "";
            }
            if (scheduleSel) {
                scheduleSel.value = d.scheduleId || "";
            }
            if (templateSel) {
                templateSel.value = d.templateId || "";
            }
            if (modeSel) {
                modeSel.value = d.mode || "";
            }
            if (canEdit) {
                canEdit.checked = d.canEdit === "1";
            }
            if (canDel) {
                canDel.checked = d.canDelete === "1";
            }
            dialog.showModal();
        }

        document.querySelectorAll("[data-admin-tt-dept-edit]").forEach(function (btn) {
            btn.addEventListener("click", function () {
                openFromButton(this);
            });
        });

        var closeBtn = document.getElementById("admin-dept-edit-close");
        if (closeBtn) {
            closeBtn.addEventListener("click", function () {
                dialog.close();
            });
        }

        dialog.addEventListener("click", function (ev) {
            if (ev.target === dialog) {
                dialog.close();
            }
        });

        if (dialog.getAttribute("data-auto-open") === "1") {
            dialog.showModal();
            dialog.removeAttribute("data-auto-open");
        }
    }

    function wireUdAssign() {
        var dialog = document.getElementById("admin-ud-assign-dialog");
        if (!dialog || typeof dialog.showModal !== "function") {
            return;
        }

        var form = dialog.querySelector("form.admin-tt-edit-dialog__form");
        var userIdInput = document.getElementById("admin-ud-assign-user-id");
        var labelEl = document.getElementById("admin-ud-assign-member-label");

        function openFromButton(btn) {
            if (btn.disabled) {
                return;
            }
            var d = btn.dataset;
            if (labelEl) {
                labelEl.textContent = d.userLabel || "";
            }
            if (userIdInput) {
                userIdInput.value = d.userId || "";
            }
            if (form && d.clearForm === "1") {
                form.reset();
                if (userIdInput) {
                    userIdInput.value = d.userId || "";
                }
                if (labelEl) {
                    labelEl.textContent = d.userLabel || "";
                }
            }
            dialog.showModal();
        }

        document.querySelectorAll("[data-admin-tt-ud-assign]").forEach(function (btn) {
            btn.addEventListener("click", function () {
                openFromButton(this);
            });
        });

        var closeBtn = document.getElementById("admin-ud-assign-close");
        if (closeBtn) {
            closeBtn.addEventListener("click", function () {
                dialog.close();
            });
        }

        dialog.addEventListener("click", function (ev) {
            if (ev.target === dialog) {
                dialog.close();
            }
        });

        if (dialog.getAttribute("data-auto-open") === "1") {
            dialog.showModal();
            dialog.removeAttribute("data-auto-open");
        }
    }

    wireScheduleCreate();
    wireScheduleEdit();
    wireDepartmentCreate();
    wireDeptEdit();
    wireUdAssign();
})();
