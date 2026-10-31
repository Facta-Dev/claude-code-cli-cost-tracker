# Architecture graphics

Interactive HTML diagrams of the implementation, generated with
[archify](https://github.com/tt-a1i/archify) from the JSON specs next to
each file (open the `.html` in a browser — hover, and the trace animation
follows the data):

| diagram | source | static (README) | what it shows |
| --- | --- | --- | --- |
| [module-map.html](module-map.html) | `module-map.architecture.json` | [module-map.svg](module-map.svg) | The module graph: root entry scripts, the `cccost/` package, and the data at rest (transcripts, price sheet, byte-offset state) |
| [billing.dataflow.html](billing.dataflow.html) | `billing.dataflow.json` | [billing.dataflow.svg](billing.dataflow.svg) | The billing flow: transcript lines → shape/dedupe → the `cost()` pricing seam (resolve, tiers, off-peak) → the three surfaces |
| [render.sequence.html](render.sequence.html) | `render.sequence.json` | [render.sequence.svg](render.sequence.svg) | One status-line render: payload → incremental byte-offset billing → state → the line, with the never-dark fallback |

The SVGs are static snapshots (HTML-DOM extraction with the page CSS
inlined and `xmlns` seeded) used to embed the diagrams in the root README.

To regenerate (from this directory):

```bash
node <path-to-archify>/archify/bin/archify.mjs render architecture module-map.architecture.json module-map.html
```

The JSONs are the source of truth — edit the spec, re-render, commit both.