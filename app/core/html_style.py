"""Stylesheet and client-side behaviour for the single-file HTML report.

Kept apart from :mod:`app.core.html_report` so that module reads as document
structure rather than as a wall of CSS.  Everything here is inlined into the
exported file: the report has to open from an email attachment on a machine with
no network, so there is no stylesheet to fetch, no font to download and no
script to load.
"""
from __future__ import annotations

from ..config import CATEGORICAL_SEQUENCE, PALETTE

#: System font stack — nothing to download, and it still looks native on the
#: Windows machines this is read on.
_FONTS = ('-apple-system, BlinkMacSystemFont, "Segoe UI", "Segoe UI Variable", '
          'Roboto, "Helvetica Neue", Arial, sans-serif')


def stylesheet() -> str:
    """The report's CSS, built from the app's own palette."""
    return f"""
:root {{
  --primary: {PALETTE['primary']};
  --primary-dark: {PALETTE['primary_dark']};
  --accent: {PALETTE['accent']};
  --ink: {PALETTE['ink']};
  --muted: {PALETTE['muted']};
  --bg: {PALETTE['bg']};
  --card: {PALETTE['card']};
  --border: {PALETTE['border']};
  --good: {PALETTE['good']};
  --warn: {PALETTE['warn']};
  --bad: {PALETTE['bad']};
  --radius: 12px;
  --shadow: 0 1px 2px rgba(16,24,40,.05), 0 4px 16px rgba(16,24,40,.05);
  --nav-w: 268px;
}}

* {{ box-sizing: border-box; }}
html {{ scroll-behavior: smooth; scroll-padding-top: 1.2rem; }}
body {{
  margin: 0; background: var(--bg); color: var(--ink);
  font-family: {_FONTS}; font-size: 15px; line-height: 1.55;
  -webkit-font-smoothing: antialiased;
}}
a {{ color: var(--primary); text-decoration: none; }}
a:hover {{ text-decoration: underline; }}

/* ---------------------------------------------------------------- cover -- */
.cover {{
  background: linear-gradient(135deg, var(--primary-dark) 0%, var(--primary) 55%,
              var(--accent) 130%);
  color: #fff; padding: 3.2rem 2.4rem 2.6rem;
}}
.cover-inner {{ max-width: 1180px; margin: 0 auto; }}
.cover h1 {{ margin: 0 0 .35rem; font-size: 2.3rem; font-weight: 700;
             letter-spacing: -.02em; }}
.cover .sub {{ font-size: 1.12rem; opacity: .93; margin: 0 0 1.5rem; }}
.chips {{ display: flex; flex-wrap: wrap; gap: .5rem; }}
.chip {{
  background: rgba(255,255,255,.16); border: 1px solid rgba(255,255,255,.26);
  border-radius: 999px; padding: .3rem .85rem; font-size: .82rem;
  backdrop-filter: blur(2px);
}}
.chip b {{ font-weight: 600; }}

/* ----------------------------------------------------------------- shell -- */
.shell {{ max-width: 1180px; margin: 0 auto; padding: 0 1.4rem 4rem;
          display: grid; grid-template-columns: var(--nav-w) minmax(0, 1fr);
          gap: 2rem; align-items: start; }}
@media (max-width: 980px) {{ .shell {{ grid-template-columns: 1fr; }} }}

nav.toc {{
  position: sticky; top: 1rem; margin-top: 1.6rem; background: var(--card);
  border: 1px solid var(--border); border-radius: var(--radius);
  box-shadow: var(--shadow); padding: 1rem 1rem 1.1rem;
  max-height: calc(100vh - 2rem); overflow: auto;
}}
nav.toc h2 {{ font-size: .72rem; text-transform: uppercase; letter-spacing: .09em;
              color: var(--muted); margin: 0 0 .6rem; }}
nav.toc ol {{ list-style: none; margin: 0; padding: 0; }}
nav.toc li a {{ display: block; padding: .34rem .55rem; border-radius: 7px;
                color: var(--ink); font-size: .89rem; border-left: 2px solid transparent; }}
nav.toc li a:hover {{ background: var(--bg); text-decoration: none; }}
nav.toc li a.sub {{ padding-left: 1.35rem; font-size: .84rem; color: var(--muted); }}
nav.toc li a.active {{ background: #EAF3FC; color: var(--primary-dark);
                       border-left-color: var(--primary); font-weight: 600; }}
.toc-tools {{ margin-top: .8rem; display: flex; gap: .4rem; }}

main {{ min-width: 0; margin-top: 1.6rem; }}

/* -------------------------------------------------------------- sections -- */
section.report {{ margin-bottom: 2.4rem; }}
.report-head {{
  background: var(--card); border: 1px solid var(--border);
  border-radius: var(--radius); box-shadow: var(--shadow);
  padding: 1.35rem 1.5rem; margin-bottom: 1rem;
  border-top: 3px solid var(--primary);
}}
.report-head h2 {{ margin: 0 0 .3rem; font-size: 1.5rem; letter-spacing: -.015em; }}
.report-head p {{ margin: 0 0 .4rem; color: var(--ink); }}
.source {{ color: var(--muted); font-size: .85rem; }}
.popline {{ margin-top: .7rem; font-size: .9rem; color: var(--muted); }}
.popline b {{ color: var(--ink); }}

h3.block {{ font-size: 1.06rem; margin: 0 0 .2rem; letter-spacing: -.01em; }}
h4.sub {{ font-size: .95rem; margin: 1rem 0 .4rem; color: var(--ink); }}
.note {{ color: var(--muted); font-size: .86rem; margin: 0 0 .8rem; }}

.card {{
  background: var(--card); border: 1px solid var(--border);
  border-radius: var(--radius); box-shadow: var(--shadow);
  padding: 1.15rem 1.25rem 1.25rem; margin-bottom: 1rem;
}}
.grid2 {{ display: grid; grid-template-columns: repeat(2, minmax(0,1fr)); gap: 1rem; }}
@media (max-width: 820px) {{ .grid2 {{ grid-template-columns: 1fr; }} }}

/* ------------------------------------------------------------- kpi tiles -- */
/* Five tiles, one row, down to a narrow laptop — a lone tile wrapped onto a
   second row reads as a different kind of number, which it is not. */
.kpis {{ display: grid; gap: .7rem; margin-bottom: 1rem;
         grid-template-columns: repeat(auto-fit, minmax(136px, 1fr)); }}
.kpi {{
  background: var(--card); border: 1px solid var(--border);
  border-radius: var(--radius); box-shadow: var(--shadow); padding: .9rem .95rem;
  border-left: 3px solid var(--primary);
}}
.kpi .label {{ font-size: .74rem; text-transform: uppercase; letter-spacing: .07em;
               color: var(--muted); }}
.kpi .value {{ font-size: 1.6rem; font-weight: 700; letter-spacing: -.02em;
               line-height: 1.15; margin-top: .15rem; }}
.kpi .unit {{ font-size: .8rem; color: var(--muted); }}

/* ---------------------------------------------------------------- tables -- */
.table-wrap {{ overflow-x: auto; border: 1px solid var(--border);
               border-radius: 10px; background: var(--card); }}
table.data {{ border-collapse: collapse; width: 100%; font-size: .86rem; }}
table.data th, table.data td {{
  padding: .5rem .7rem; text-align: left; border-bottom: 1px solid var(--border);
  white-space: nowrap;
}}
table.data thead th {{
  position: sticky; top: 0; background: #F0F4F9; color: var(--muted);
  font-size: .74rem; text-transform: uppercase; letter-spacing: .05em;
  font-weight: 600; cursor: pointer; user-select: none; z-index: 1;
}}
table.data thead th:hover {{ color: var(--primary-dark); }}
table.data thead th::after {{ content: "↕"; opacity: .32; margin-left: .35rem;
                              font-size: .8em; }}
table.data thead th.asc::after {{ content: "↑"; opacity: .9; }}
table.data thead th.desc::after {{ content: "↓"; opacity: .9; }}
table.data tbody tr:nth-child(even) {{ background: #FBFCFE; }}
table.data tbody tr:hover {{ background: #EAF3FC; }}
table.data td.num, table.data th.num {{ text-align: right;
                                        font-variant-numeric: tabular-nums; }}
table.data td.rowhead {{ font-weight: 600; white-space: nowrap; }}
table.data td.blank {{ background: repeating-linear-gradient(
    -45deg, #FAFBFD, #FAFBFD 5px, #F2F4F8 5px, #F2F4F8 10px); }}
table.data .fytot {{ background: #EAF3FC; font-weight: 700; }}
table.data thead th.fytot {{ background: #DCEAF8; color: var(--primary-dark); }}

.tools {{ display: flex; gap: .5rem; align-items: center; margin: 0 0 .6rem;
          flex-wrap: wrap; }}
.tools input[type=search] {{
  flex: 1 1 220px; min-width: 180px; padding: .42rem .7rem; font: inherit;
  font-size: .86rem; border: 1px solid var(--border); border-radius: 8px;
  background: var(--card); color: var(--ink);
}}
.tools input[type=search]:focus {{ outline: 2px solid var(--accent);
                                   outline-offset: -1px; }}
.count {{ color: var(--muted); font-size: .82rem; }}

button.btn {{
  font: inherit; font-size: .82rem; padding: .34rem .7rem; cursor: pointer;
  border: 1px solid var(--border); border-radius: 8px; background: var(--card);
  color: var(--ink);
}}
button.btn:hover {{ border-color: var(--primary); color: var(--primary-dark); }}

/* ------------------------------------------------------------ accordions -- */
details.acc {{
  background: var(--card); border: 1px solid var(--border);
  border-radius: 10px; margin-bottom: .6rem; overflow: hidden;
}}
details.acc > summary {{
  cursor: pointer; padding: .7rem 1rem; font-weight: 600; font-size: .93rem;
  list-style: none; display: flex; align-items: center; gap: .55rem;
}}
details.acc > summary::-webkit-details-marker {{ display: none; }}
details.acc > summary::before {{
  content: "▸"; color: var(--primary); font-size: .9em; transition: transform .15s;
}}
details.acc[open] > summary::before {{ transform: rotate(90deg); }}
details.acc > summary:hover {{ background: #F7FAFD; }}
details.acc > summary .badge {{
  margin-left: auto; font-weight: 500; font-size: .78rem; color: var(--muted);
  background: var(--bg); border: 1px solid var(--border); border-radius: 999px;
  padding: .1rem .55rem;
}}
details.acc .acc-body {{ padding: .2rem 1rem 1rem; }}

/* --------------------------------------------------------------- charts -- */
.chart {{ width: 100%; }}
.js-plotly-plot .plotly .modebar {{ opacity: .35; }}
.js-plotly-plot:hover .plotly .modebar {{ opacity: 1; }}

/* -------------------------------------------------------------- insights -- */
ul.insights {{ list-style: none; margin: 0; padding: 0; }}
ul.insights li {{ padding: .5rem 0 .5rem .9rem; border-left: 3px solid var(--border);
                  margin-bottom: .45rem; font-size: .92rem; }}
ul.insights li.high {{ border-left-color: var(--bad); }}
ul.insights li.medium {{ border-left-color: var(--warn); }}
ul.insights li.low {{ border-left-color: var(--good); }}
/* Only the insight's title is a line of its own — bold inside the detail text
   ("**Americas** leads with …") has to stay inline. */
ul.insights b.t {{ display: block; }}

.empty {{ color: var(--muted); font-style: italic; padding: .6rem 0; }}
.toplink {{ font-size: .8rem; color: var(--muted); }}

footer.report-foot {{
  border-top: 1px solid var(--border); background: var(--card);
  padding: 1.4rem; color: var(--muted); font-size: .83rem; text-align: center;
}}

/* ----------------------------------------------------------------- print -- */
@media print {{
  body {{ background: #fff; }}
  .shell {{ display: block; padding: 0; }}
  nav.toc, .tools, .toc-tools, button.btn {{ display: none !important; }}
  .card, .kpi, .report-head, .table-wrap {{ box-shadow: none; break-inside: avoid; }}
  section.report {{ break-before: page; }}
  details.acc {{ break-inside: avoid; }}
  details.acc:not([open]) > .acc-body {{ display: none; }}
}}
"""


def script() -> str:
    """Table sorting, filtering, accordion controls and TOC highlighting.

    Vanilla JS on purpose: the file has to work offline from a mail client's
    download folder, so there is no framework to load and nothing to fetch.
    """
    return """
(function () {
  'use strict';

  // ---- sortable tables ---------------------------------------------------
  // Numbers are compared numerically once stripped of $ , % and K/M/B suffixes,
  // dates as dates, everything else as text — so "Cores" sorts 9 before 100.
  var MULT = { K: 1e3, M: 1e6, B: 1e9 };
  function numeric(text) {
    var t = String(text).trim().replace(/[$,%\\s]/g, '');
    var m = /^(-?\\d*\\.?\\d+)([KMB])$/.exec(t);
    if (m) return parseFloat(m[1]) * MULT[m[2]];
    if (/^-?\\d*\\.?\\d+$/.test(t)) return parseFloat(t);
    var d = Date.parse(text);
    return isNaN(d) ? null : d;
  }
  function compare(a, b) {
    var na = numeric(a), nb = numeric(b);
    if (na !== null && nb !== null) return na - nb;
    if (a === '' ) return 1;
    if (b === '' ) return -1;
    return a.localeCompare(b, undefined, { numeric: true, sensitivity: 'base' });
  }
  document.querySelectorAll('table.data').forEach(function (table) {
    var head = table.tHead;
    if (!head) return;
    head.querySelectorAll('th').forEach(function (th, index) {
      th.addEventListener('click', function () {
        var body = table.tBodies[0];
        if (!body) return;
        var desc = th.classList.contains('asc');
        head.querySelectorAll('th').forEach(function (o) {
          o.classList.remove('asc', 'desc');
        });
        th.classList.add(desc ? 'desc' : 'asc');
        var rows = Array.prototype.slice.call(body.rows);
        rows.sort(function (r1, r2) {
          var t1 = (r1.cells[index] || {}).textContent || '';
          var t2 = (r2.cells[index] || {}).textContent || '';
          return (desc ? -1 : 1) * compare(t1.trim(), t2.trim());
        });
        rows.forEach(function (r) { body.appendChild(r); });
      });
    });
  });

  // ---- per-table search --------------------------------------------------
  document.querySelectorAll('input[data-filters]').forEach(function (input) {
    var table = document.getElementById(input.getAttribute('data-filters'));
    var count = document.querySelector('[data-count-for="' + input.getAttribute('data-filters') + '"]');
    if (!table) return;
    input.addEventListener('input', function () {
      var needle = input.value.toLowerCase();
      var body = table.tBodies[0], shown = 0;
      if (!body) return;
      Array.prototype.forEach.call(body.rows, function (row) {
        var hit = !needle || row.textContent.toLowerCase().indexOf(needle) !== -1;
        row.style.display = hit ? '' : 'none';
        if (hit) shown++;
      });
      if (count) count.textContent = shown + ' of ' + body.rows.length + ' rows';
    });
  });

  // ---- accordions --------------------------------------------------------
  function setAll(open) {
    document.querySelectorAll('details.acc').forEach(function (d) { d.open = open; });
    // A Plotly chart sized while hidden lays out at zero width; resize on reveal.
    if (open) resizeCharts();
  }
  var expand = document.getElementById('expand-all');
  var collapse = document.getElementById('collapse-all');
  if (expand) expand.addEventListener('click', function () { setAll(true); });
  if (collapse) collapse.addEventListener('click', function () { setAll(false); });

  function resizeCharts() {
    if (!window.Plotly) return;
    document.querySelectorAll('.js-plotly-plot').forEach(function (el) {
      try { window.Plotly.Plots.resize(el); } catch (e) { /* not drawn yet */ }
    });
  }
  document.querySelectorAll('details.acc').forEach(function (d) {
    d.addEventListener('toggle', function () { if (d.open) resizeCharts(); });
  });
  window.addEventListener('resize', resizeCharts);
  // The first layout can measure a container that the CSS grid has not finished
  // sizing, which clips axis labels; re-measure once everything has loaded.
  window.addEventListener('load', function () { setTimeout(resizeCharts, 0); });

  // ---- table of contents -------------------------------------------------
  var links = Array.prototype.slice.call(document.querySelectorAll('nav.toc a'));
  var targets = links.map(function (a) {
    return document.getElementById(a.getAttribute('href').slice(1));
  });
  function highlight() {
    var best = 0, top = window.scrollY + 90;
    targets.forEach(function (el, i) {
      if (el && el.offsetTop <= top) best = i;
    });
    links.forEach(function (a, i) { a.classList.toggle('active', i === best); });
  }
  window.addEventListener('scroll', highlight, { passive: true });
  highlight();
})();
"""


def plotly_template() -> dict:
    """Layout defaults matching the dashboard's charts."""
    return {
        "layout": {
            "font": {"family": _FONTS, "size": 12, "color": PALETTE["ink"]},
            "paper_bgcolor": PALETTE["card"],
            "plot_bgcolor": PALETTE["card"],
            "colorway": CATEGORICAL_SEQUENCE,
            # ``automargin`` rather than fixed margins: a categorical month axis
            # rotates its labels when crowded, and a fixed margin clips them.
            "margin": {"l": 56, "r": 44, "t": 34, "b": 48},
            "hoverlabel": {"font": {"family": _FONTS, "size": 12}},
            "xaxis": {"gridcolor": PALETTE["border"], "zerolinecolor": PALETTE["border"],
                      "automargin": True},
            "yaxis": {"gridcolor": PALETTE["border"], "zerolinecolor": PALETTE["border"],
                      "automargin": True},
        }
    }
