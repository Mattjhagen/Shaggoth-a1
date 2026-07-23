// mobile nav
const toggle = document.querySelector(".nav__toggle");
const links = document.querySelector(".nav__links");
if (toggle && links) {
  toggle.addEventListener("click", () => {
    const open = links.classList.toggle("open");
    toggle.setAttribute("aria-expanded", String(open));
  });
}

// scroll reveal
const io = new IntersectionObserver(
  (entries) => entries.forEach((e) => { if (e.isIntersecting) { e.target.classList.add("in"); io.unobserve(e.target); } }),
  { threshold: 0.12 }
);
document.querySelectorAll(".reveal").forEach((el) => io.observe(el));

// typed terminal (home only), respects reduced motion
const term = document.querySelector("[data-typed]");
if (term && !window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
  const lines = JSON.parse(term.dataset.typed);
  term.innerHTML = "";
  let li = 0;
  function typeLine() {
    if (li >= lines.length) return;
    const div = document.createElement("div");
    div.innerHTML = lines[li];
    term.appendChild(div);
    li++;
    setTimeout(typeLine, 420);
  }
  typeLine();
} else if (term) {
  const lines = JSON.parse(term.dataset.typed);
  term.innerHTML = lines.map((l) => `<div>${l}</div>`).join("");
}
