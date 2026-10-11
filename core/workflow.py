"""Flujos de trabajo: encadena varias herramientas PDF→PDF en una sola pasada."""
from __future__ import annotations

from pathlib import Path

from .registry import BY_SLUG
from .utils import InputFile, Result, ToolError


def run_workflow(inputs: list[InputFile], steps: list[dict], workdir: Path) -> Result:
    if not steps:
        raise ToolError("El flujo no tiene pasos.")
    if len(steps) > 12:
        raise ToolError("Un flujo puede tener como máximo 12 pasos.")
    current = list(inputs)
    log = []
    for i, step in enumerate(steps):
        tool = BY_SLUG.get(step.get("tool", ""))
        if not tool or not tool.get("workflow"):
            raise ToolError(f"El paso {i + 1} usa una herramienta que no se puede encadenar.")
        opts = dict(step.get("options") or {})
        if tool["key"] == "crop":
            opts["auto"] = True
        if tool["key"] == "merge" and len(current) < 2:
            log.append(f"{tool['name']}: omitido (solo hay un archivo)")
            continue
        if tool["key"] == "watermark":
            opts["type"] = "texto"
        out = workdir / f"paso_{i + 1}"
        out.mkdir(parents=True, exist_ok=True)
        if tool["multiple"]:
            res = tool["op"](current, opts, out)
            produced = res.files
        else:
            produced = []
            for f in current:
                res = tool["op"]([f], opts, out)
                produced += res.files
        pdfs = [p for p in produced if p.suffix.lower() == ".pdf"]
        if not pdfs:
            raise ToolError(f"El paso {i + 1} ({tool['name']}) no produjo ningún PDF.")
        current = [InputFile(p, p.name) for p in pdfs]
        log.append(f"{tool['name']}: {res.message}")
    final = []
    for i, f in enumerate(current):
        base = Path(inputs[min(i, len(inputs) - 1)].name).stem if len(current) == len(inputs) else Path(inputs[0].name).stem
        dest = f.path.with_name(f"{base[:80]}_flujo.pdf")
        n = 2
        while dest.exists() and dest != f.path:
            dest = f.path.with_name(f"{base[:80]}_flujo ({n}).pdf")
            n += 1
        final.append(f.path.rename(dest))
    return Result(final, "Flujo completado.", data={"log": log}, zip_name="flujo_bsobpdf.zip")
