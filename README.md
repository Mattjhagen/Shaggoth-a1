# mattjhagen-portfolio

The résumé + portfolio site for Matt Hagen — live at [mattjhagen.xyz](https://mattjhagen.xyz). Software work, a résumé built from 255 public repos, and fiction in one place. No build step, no framework. Just open `index.html`.

## Structure

```
mattjhagen-portfolio/
├── index.html      # home — typed-terminal hero, featured builds, stats
├── resume.html     # résumé — experience, skills, GitHub stats (print-friendly)
├── work.html       # software projects (P3, Archon IDE, Idswyft, and more)
├── writing.html    # fiction — The Gentle Conquest
├── about.html      # bio + contact
├── css/style.css   # all styles, incl. print stylesheet for the résumé
└── js/main.js      # nav toggle, terminal typing, scroll reveal
```

## Featured content

- **P3 Lending Protocol** — decentralized P2P lending with AI reputation scoring
- **Archon IDE** — local-first AI coding assistant in Rust + React
- **Idswyft** — open-source identity verification platform
- **Mesh Messenger, TapCard, Rooted Daily, PacMac Mobile** — and ~250 more repos
- **The Gentle Conquest** — psychological thriller, in production

The résumé page (`resume.html`) has a Print/PDF button and a dedicated print stylesheet, so it doubles as a paper résumé.

## Run locally

Just open `index.html` in a browser, or serve it:

```bash
python3 -m http.server 8000
# visit http://localhost:8000
```

## Deploy

Deployed on GitHub Pages from `main` with the custom domain in `CNAME` (mattjhagen.xyz). Also works on Netlify, Vercel, or Cloudflare Pages with zero config.
