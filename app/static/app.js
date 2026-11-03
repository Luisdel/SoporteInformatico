document.addEventListener("DOMContentLoaded", function () {
  setInterval(function () {
    fetch("/api/avisos", { credentials: "same-origin" })
      .then(r => r.json())
      .then(d => {
        const dot = document.getElementById("notice-dot");
        if (dot) dot.textContent = d.unread > 0 ? ("(" + d.unread + ")") : "";
        document.title = d.unread > 0 ? "(1) " + document.title.replace(/^\(\d+\)\s*/, "") : document.title.replace(/^\(\d+\)\s*/, "");
      });
  }, 30000);
});
