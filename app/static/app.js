document.addEventListener("DOMContentLoaded", function () {
  const adminNav = document.querySelector('a[href="/admin/usuarios"]');
  const endpoint = adminNav ? "/api/admin/avisos" : "/api/avisos";

  function refresh() {
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

  refresh();
  setInterval(refresh, 30000);
});
