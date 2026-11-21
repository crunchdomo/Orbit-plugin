const list = document.getElementById("notes");
const form = document.getElementById("new-note");

async function loadNotes() {
  const response = await fetch("/api/notes");
  const data = await response.json();
  render(data.notes);
}

function render(notes) {
  list.innerHTML = "";
  for (const note of notes) {
    const item = document.createElement("article");
    item.className = "note";
    item.innerHTML = `
      <div class="delete" data-id="${note.id}">Delete</div>
      <h3>${note.title}</h3>
      <p>${note.body}</p>
    `;
    list.appendChild(item);
  }

  document.addEventListener("click", async (event) => {
    if (!event.target.classList.contains("delete")) return;
    await fetch(`/api/notes/${event.target.dataset.id}`, { method: "DELETE" });
    loadNotes();
  });
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const title = document.getElementById("title").value;
  const body = document.getElementById("body").value;
  try {
    await fetch("/api/notes", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title, body }),
    });
    form.reset();
    loadNotes();
  } catch (error) {}
});

loadNotes();
