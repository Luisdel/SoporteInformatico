document.addEventListener("DOMContentLoaded", function () {
  const adminNav = document.querySelector('a[href="/admin/usuarios"]');
  const endpoint = adminNav ? "/api/admin/avisos" : "/api/avisos";
  const AUTO_REFRESH_MS = 5 * 60 * 1000; // 5 minutos

  function refreshAlerts() {
    fetch(endpoint, { credentials: "same-origin" })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (data) {
        if (!data) return;
        if (adminNav) {
          const badge = document.getElementById("admin-alertas");
          if (badge) {
            const total = (data.sin_asignar || 0) + (data.mis_no_leidas || 0);
            badge.textContent = total > 0 ? String(total) : "";
            badge.hidden = total === 0;
          }
          return;
        }
        const dot = document.getElementById("notice-dot");
        if (dot) dot.textContent = data.unread > 0 ? "(" + data.unread + ")" : "";
        if (data.unread > 0) {
          document.title = "(" + data.unread + ") " + document.title.replace(/^\(\d+\)\s*/, "");
        } else {
          document.title = document.title.replace(/^\(\d+\)\s*/, "");
        }
      })
      .catch(function () { /* silencio: reintento en el siguiente ciclo */ });
  }

  // No recargar mientras haya un borrador o un archivo elegido sin enviar.
  function hasDraft() {
    const editor = document.activeElement;
    if (editor && ["INPUT", "TEXTAREA", "SELECT"].indexOf(editor.tagName) !== -1) {
      return true;
    }
    const texts = document.querySelectorAll(
      'form[method="post"] input[type="text"],' +
      'form[method="post"] input[type="password"],' +
      'form[method="post"] textarea'
    );
    for (const field of texts) {
      if (field.value && field.value.trim() !== "") return true;
    }
    const files = document.querySelectorAll('input[type="file"]');
    for (const input of files) {
      if (input.files && input.files.length > 0) return true;
    }
    return false;
  }

  let refreshTimer = null;

  function scheduleRefresh() {
    if (refreshTimer) clearTimeout(refreshTimer);
    refreshTimer = setTimeout(function () {
      if (hasDraft()) {
        scheduleRefresh();
        return;
      }
      try {
        sessionStorage.setItem("scroll:" + window.location.pathname, String(window.scrollY));
      } catch (e) { /* almacenamiento no disponible */ }
      window.location.reload();
    }, AUTO_REFRESH_MS);
  }

  // Restaurar la posición de scroll tras una recarga automática.
  try {
    const saved = sessionStorage.getItem("scroll:" + window.location.pathname);
    if (saved !== null) {
      sessionStorage.removeItem("scroll:" + window.location.pathname);
      window.scrollTo(0, parseInt(saved, 10) || 0);
    }
  } catch (e) { /* almacenamiento no disponible */ }

  refreshAlerts();
  setInterval(refreshAlerts, 30000);
  scheduleRefresh();
});
