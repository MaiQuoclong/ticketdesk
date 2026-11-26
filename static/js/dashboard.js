(function () {
  var dataEl = document.getElementById("dashboard-data");
  if (!dataEl || typeof window.Chart === "undefined") return;
  var data = JSON.parse(dataEl.textContent);

  window.Chart.defaults.font.family = "'Plus Jakarta Sans', sans-serif";
  window.Chart.defaults.color = "#22252a";

  var integerAxis = { beginAtZero: true, ticks: { precision: 0 } };

  var statusCanvas = document.getElementById("chart-status");
  if (statusCanvas) {
    new window.Chart(statusCanvas, {
      type: "bar",
      data: {
        labels: data.status.labels,
        datasets: [{
          label: "Số ticket",
          data: data.status.values,
          backgroundColor: data.status.colors,
          borderRadius: 4,
        }],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { display: false } },
        scales: { y: integerAxis },
      },
    });
  }

  var agentCanvas = document.getElementById("chart-agents");
  if (agentCanvas) {
    if (!data.agents.labels.length) {
      agentCanvas.parentNode.textContent = "Chưa có nhân viên hỗ trợ.";
      return;
    }
    new window.Chart(agentCanvas, {
      type: "bar",
      data: {
        labels: data.agents.labels,
        datasets: data.agents.datasets.map(function (ds) {
          return Object.assign({ borderRadius: 4 }, ds);
        }),
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { position: "bottom" } },
        scales: { x: { stacked: true }, y: Object.assign({ stacked: true }, integerAxis) },
      },
    });
  }
})();
