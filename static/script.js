const form = document.getElementById("ask-form");
const input = document.getElementById("question");
const submitBtn = document.getElementById("submit-btn");
const results = document.getElementById("results");
const cardTemplate = document.getElementById("card-template");
const loadingTemplate = document.getElementById("loading-template");

form.addEventListener("submit", async (e) => {
  e.preventDefault();
  const question = input.value.trim();
  if (!question) return;

  submitBtn.disabled = true;

  const loadingNode = loadingTemplate.content.cloneNode(true);
  const loadingEl = loadingNode.querySelector(".card--loading");
  results.prepend(loadingNode);

  try {
    const resp = await fetch("/api/ask", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question }),
    });

    if (!resp.ok) throw new Error(`Error del servidor (${resp.status})`);
    const data = await resp.json();

    renderCard(question, data.answer, data.sources || []);
  } catch (err) {
    renderCard(question, `Error al consultar el catálogo: ${err.message}`, []);
  } finally {
    document.querySelector(".card--loading")?.remove();
    submitBtn.disabled = false;
    input.value = "";
    input.focus();
  }
});

function renderCard(question, answer, sources) {
  const node = cardTemplate.content.cloneNode(true);
  node.querySelector(".card-question").textContent = question;
  node.querySelector(".card-answer").textContent = answer;

  const refsFooter = node.querySelector(".card-refs");
  const refsList = node.querySelector(".refs-list");

  if (sources.length === 0) {
    refsFooter.remove();
  } else {
    sources.forEach((s) => {
      const li = document.createElement("li");
      const a = document.createElement("a");
      a.href = s.url;
      a.target = "_blank";
      a.rel = "noopener noreferrer";
      a.textContent = s.project;
      li.appendChild(a);
      refsList.appendChild(li);
    });
  }

  results.prepend(node);
}
