/* =========================================================
   CMP Operation App - Global JavaScript
   Responsive Support:
   Desktop, Laptop, Tablet, Android, iPhone
   ========================================================= */

(function () {
    "use strict";

    const THEME_KEY = "cmp_theme";

    function applyTheme(theme) {
        const body = document.body;

        if (!body) {
            return;
        }

        if (theme === "dark") {
            body.classList.add("dark-theme");
        } else {
            body.classList.remove("dark-theme");
        }

        localStorage.setItem(THEME_KEY, theme);
        updateThemeButtons(theme);
    }

    function getSavedTheme() {
        return localStorage.getItem(THEME_KEY) || "light";
    }

    function toggleTheme() {
        const currentTheme = document.body.classList.contains("dark-theme")
            ? "dark"
            : "light";

        const nextTheme = currentTheme === "dark" ? "light" : "dark";

        applyTheme(nextTheme);
    }

    function updateThemeButtons(theme) {
        const buttons = document.querySelectorAll("[data-theme-toggle]");

        buttons.forEach(function (button) {
            button.textContent = theme === "dark" ? "Light Mode" : "Dark Mode";
        });
    }

    function initThemeToggle() {
        const buttons = document.querySelectorAll("[data-theme-toggle]");

        buttons.forEach(function (button) {
            button.addEventListener("click", toggleTheme);
        });
    }

    function initAutoHideAlerts() {
        const alerts = document.querySelectorAll("[data-auto-hide]");

        alerts.forEach(function (alertBox) {
            const delay = Number(alertBox.getAttribute("data-auto-hide")) || 4000;

            setTimeout(function () {
                alertBox.style.opacity = "0";
                alertBox.style.transform = "translateY(-6px)";
                alertBox.style.transition = "opacity 0.3s ease, transform 0.3s ease";

                setTimeout(function () {
                    alertBox.remove();
                }, 350);
            }, delay);
        });
    }

    function initFormValidation() {
        const forms = document.querySelectorAll("[data-validate-form]");

        forms.forEach(function (form) {
            form.addEventListener("submit", function (event) {
                const requiredFields = form.querySelectorAll("[required]");
                let isValid = true;

                requiredFields.forEach(function (field) {
                    const value = String(field.value || "").trim();

                    if (!value) {
                        isValid = false;
                        field.classList.add("is-invalid");
                    } else {
                        field.classList.remove("is-invalid");
                    }
                });

                if (!isValid) {
                    event.preventDefault();
                    showClientAlert("Please fill all required fields.", "danger");
                }
            });
        });
    }

    function showClientAlert(message, type) {
        const alertBox = document.createElement("div");
        alertBox.className = "alert alert-" + type;
        alertBox.setAttribute("data-auto-hide", "4000");
        alertBox.textContent = message;

        const container =
            document.querySelector("[data-alert-container]") ||
            document.querySelector(".auth-card") ||
            document.querySelector(".page-container") ||
            document.body;

        container.prepend(alertBox);

        initAutoHideAlerts();
    }

    function initMobileMenu() {
        const buttons = document.querySelectorAll("[data-mobile-menu-toggle]");

        buttons.forEach(function (button) {
            const targetSelector = button.getAttribute("data-mobile-menu-toggle");
            const target = document.querySelector(targetSelector);

            if (!target) {
                return;
            }

            button.addEventListener("click", function () {
                target.classList.toggle("is-open");
                document.body.classList.toggle("mobile-menu-open");
            });
        });
    }

    function closeMobileMenuOnResize() {
        window.addEventListener("resize", function () {
            if (window.innerWidth > 768) {
                document.body.classList.remove("mobile-menu-open");

                const openMenus = document.querySelectorAll(".sidebar.is-open");

                openMenus.forEach(function (menu) {
                    menu.classList.remove("is-open");
                });
            }
        });
    }

    function initResponsiveTables() {
        const tableWrappers = document.querySelectorAll(".table-wrapper");

        tableWrappers.forEach(function (wrapper) {
            const table = wrapper.querySelector("table");

            if (!table) {
                return;
            }

            if (table.scrollWidth > wrapper.clientWidth) {
                wrapper.setAttribute("data-scrollable", "true");
            }
        });
    }

    function initTouchOptimizations() {
        document.addEventListener(
            "touchstart",
            function () { },
            { passive: true }
        );
    }

    function init() {
        applyTheme(getSavedTheme());
        initThemeToggle();
        initAutoHideAlerts();
        initFormValidation();
        initMobileMenu();
        closeMobileMenuOnResize();
        initResponsiveTables();
        initTouchOptimizations();
    }

    document.addEventListener("DOMContentLoaded", init);

    window.CMPApp = {
        applyTheme: applyTheme,
        toggleTheme: toggleTheme,
        showClientAlert: showClientAlert
    };
})();

// ================================
// Settings Dropdown
// ================================
// Uses position:fixed + JS-computed coordinates so the dropdown is never
// clipped by overflow:hidden on any ancestor (e.g. .app-page).

document.addEventListener("DOMContentLoaded", function () {
    var settingsButton   = document.getElementById("settingsButton");
    var settingsDropdown = document.getElementById("settingsDropdown");

    if (!settingsButton || !settingsDropdown) {
        return;
    }

    function positionDropdown() {
        var rect = settingsButton.getBoundingClientRect();
        settingsDropdown.style.top   = (rect.bottom + 8) + "px";
        settingsDropdown.style.right = (window.innerWidth - rect.right) + "px";
        settingsDropdown.style.left  = "auto";
    }

    settingsButton.addEventListener("click", function (event) {
        event.stopPropagation();
        positionDropdown();
        settingsDropdown.classList.toggle("active");
    });

    document.addEventListener("click", function () {
        settingsDropdown.classList.remove("active");
    });

    settingsDropdown.addEventListener("click", function (event) {
        event.stopPropagation();
    });

    // Re-position on resize in case the button moves
    window.addEventListener("resize", function () {
        if (settingsDropdown.classList.contains("active")) {
            positionDropdown();
        }
    });
});