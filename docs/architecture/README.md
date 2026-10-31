# Architecture graphics

Interactive HTML diagrams of the implementation, generated with
[archify](https://github.com/tt-a1i/archify) from the JSON specs next to
each file (open the `.html` in a browser — hover, and the trace animation
follows the data):

| diagram | source | what it shows |
| --- | --- | --- |
| [module-map.html](module-map.html) | `module-map.architecture.json` | The module graph: root entry scripts, the `cccost/` package, and the data at rest (transcripts, price sheet, byte-offset state) |
| [billing.dataflow.html](billing.dataflow.html) | `billing.dataflow.json` | The billing flow: transcript lines → shape/dedupe → the `cost()` pricing seam (resolve, tiers, off-peak) → the three surfaces |
| [render.sequence.html](render.sequence.html) | `render.sequence.json` | One status-line render: payload → incremental byte-offset billing → state → the line, with the never-dark fallback |

To regenerate (from this directory):

```bash
node <path-to-archify>/archify/bin/archify.mjs render architecture module-map.architecture.json module-map.html
```

The JSONs are the source of truth — edit the spec, re-render, commit both.