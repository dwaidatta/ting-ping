const charts = (() => {
  // Terminal palette, kept in step with css/style.css.
  const LINE = "#58d3ff";
  const FILL = "rgba(88, 211, 255, 0.10)";
  const GRID = "rgba(43, 60, 78, 0.55)";
  const MUTED = "#4b5c6b";
  const MONO =
    '"JetBrains Mono", "Cascadia Mono", ui-monospace, SFMono-Regular, Menlo, Consolas, monospace';

  const instances = new Map();
  let bufferSize = 60;

  function setBufferSize(size) {
    bufferSize = size;
  }

  function createChartFor(targetId, canvasEl, initialBuffer = []) {
    const labels = initialBuffer.map((r) => new Date(r.ts * 1000).toLocaleTimeString());
    const data = initialBuffer.map((r) => r.latency_ms ?? null);

    const chart = new Chart(canvasEl.getContext("2d"), {
      type: "line",
      data: {
        labels,
        datasets: [
          {
            label: "Latency (ms)",
            data,
            borderColor: LINE,
            backgroundColor: FILL,
            borderWidth: 1.5,
            tension: 0.2,
            pointRadius: 0,
            spanGaps: true,
            fill: true,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        animation: false,
        scales: {
          x: { display: false },
          y: {
            beginAtZero: true,
            border: { display: false },
            grid: { color: GRID, drawTicks: false },
            ticks: {
              maxTicksLimit: 4,
              color: MUTED,
              font: { family: MONO, size: 9 },
              padding: 6,
            },
          },
        },
        plugins: {
          legend: { display: false },
          tooltip: {
            backgroundColor: "#0b0f14",
            borderColor: "#2b3c4e",
            borderWidth: 1,
            titleColor: "#6e8496",
            bodyColor: "#e8f0f7",
            titleFont: { family: MONO, size: 10 },
            bodyFont: { family: MONO, size: 11 },
            displayColors: false,
            callbacks: {
              label: (ctx) => (ctx.parsed.y === null ? "check failed" : `${Math.round(ctx.parsed.y)} ms`),
            },
          },
        },
      },
    });

    instances.set(targetId, chart);
    return chart;
  }

  function pushResult(targetId, result) {
    const chart = instances.get(targetId);
    if (!chart) return;

    chart.data.labels.push(new Date(result.ts * 1000).toLocaleTimeString());
    chart.data.datasets[0].data.push(result.latency_ms ?? null);

    while (chart.data.labels.length > bufferSize) {
      chart.data.labels.shift();
      chart.data.datasets[0].data.shift();
    }

    chart.update("none");
  }

  function destroyChart(targetId) {
    const chart = instances.get(targetId);
    if (chart) {
      chart.destroy();
      instances.delete(targetId);
    }
  }

  return { setBufferSize, createChartFor, pushResult, destroyChart };
})();
