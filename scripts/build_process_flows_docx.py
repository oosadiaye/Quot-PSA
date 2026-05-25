"""
build_process_flows_docx.py
============================
Convert ``docs/ARCHITECTURE/PROCESS_FLOWS.md`` to a presentation-quality
Word document with rendered Mermaid diagrams.

Pipeline:

    1. Parse the markdown file, extract every ``` mermaid block to a
       numbered .mmd file under ``docs/ARCHITECTURE/_diagrams/``.
    2. Render each .mmd to PNG via ``mmdc`` (mermaid-cli) with a
       custom theme tuned for slides — high contrast, brand palette,
       bigger fonts, transparent background.
    3. Build an intermediate markdown file where each mermaid block is
       replaced with an ``![Diagram N](path/to/diagram-N.png)`` image
       reference.
    4. Run pandoc to convert that intermediate markdown into a Word
       document, using a reference.docx that defines the cover, fonts,
       heading colours, and table styling.

Why a script and not a one-liner:
    - Diagrams need consistent theme + size across all 30+ images;
      easier to manage in one place.
    - The intermediate markdown means the pandoc step is a normal
      one-shot conversion — no custom filters, no edge cases.
    - The same script re-runs idempotently; only changed diagrams get
      re-rendered (mtime check).

Usage:
    python scripts/build_process_flows_docx.py
    python scripts/build_process_flows_docx.py --force   # rebuild all images
    python scripts/build_process_flows_docx.py --no-docx # diagrams only

Outputs:
    docs/ARCHITECTURE/_diagrams/diagram-NN.mmd      (extracted source)
    docs/ARCHITECTURE/_diagrams/diagram-NN.png      (rendered image)
    docs/ARCHITECTURE/_diagrams/PROCESS_FLOWS.imaged.md  (intermediate)
    docs/ARCHITECTURE/PROCESS_FLOWS.docx             (final)
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DOCS_DIR = PROJECT_ROOT / "docs" / "ARCHITECTURE"
SRC_MD = DOCS_DIR / "PROCESS_FLOWS.md"
DIAGRAMS_DIR = DOCS_DIR / "_diagrams"
INTERMEDIATE_MD = DIAGRAMS_DIR / "PROCESS_FLOWS.imaged.md"
OUTPUT_DOCX = DOCS_DIR / "PROCESS_FLOWS.docx"
REFERENCE_DOCX = DOCS_DIR / "_reference.docx"

# Mermaid theme tuned for a presentation: brand-blue primary nodes, AMBER
# label pills with dark slate text so transition labels pop against the
# page background. Generous spacing, large typography.
#
# v2 — fix for the "invisible label" bug seen in the first build:
# edgeLabelBackground was too pale (#f1f5f9 on white) which made the
# default white-ish label text disappear. Now switched to a warm
# amber-100 (#fef3c7) with explicit slate-900 text + a subtle border
# so the labels read like callouts rather than ghost text.
MERMAID_CONFIG: dict[str, object] = {
    "theme": "base",
    "themeVariables": {
        "primaryColor": "#1e40af",
        "primaryTextColor": "#ffffff",
        "primaryBorderColor": "#1e3a8a",
        "lineColor": "#475569",
        "secondaryColor": "#fde68a",
        "secondaryTextColor": "#0f172a",
        "secondaryBorderColor": "#92400e",
        "tertiaryColor": "#dbeafe",
        "tertiaryTextColor": "#0f172a",
        "tertiaryBorderColor": "#1e40af",
        "background": "#ffffff",
        "mainBkg": "#1e40af",
        "secondBkg": "#fde68a",
        "fontFamily": "'Segoe UI', 'Inter', system-ui, sans-serif",
        "fontSize": "16px",
        # ── edge / transition labels (the bug we're fixing) ────────────
        # Mermaid's stateDiagram-v2 renders ``--> X : label`` text as
        # ``transitionLabelColor`` on a span backgrounded by
        # ``edgeLabelBackground``. Both must contrast.
        "edgeLabelBackground": "#fef3c7",   # amber-100 pill
        "labelBackground":     "#fef3c7",
        "labelTextColor":      "#0f172a",   # slate-900 — high contrast
        "transitionColor":     "#475569",   # arrow stroke
        "transitionLabelColor": "#0f172a",  # transition text in stateDiagram
        # ── sequence diagram specific ──────────────────────────────────
        "actorBkg":         "#1e40af",
        "actorTextColor":   "#ffffff",
        "actorLineColor":   "#1e3a8a",
        "signalColor":      "#0f172a",
        "signalTextColor":  "#0f172a",
        "labelBoxBkgColor": "#fde68a",
        "labelBoxBorderColor": "#92400e",
        "loopTextColor":    "#0f172a",
        "noteBorderColor":  "#92400e",
        "noteBkgColor":     "#fef3c7",
        "noteTextColor":    "#0f172a",
        "activationBorderColor": "#1e3a8a",
        "activationBkgColor":    "#dbeafe",
        # ── flowchart specific ─────────────────────────────────────────
        # Class-defined node fills (e.g. ``classDef gate fill:#fef3c7``)
        # override these, but a sensible default keeps unstyled nodes
        # visually consistent.
        "clusterBkg":     "#f8fafc",
        "clusterBorder":  "#cbd5e1",
        "defaultLinkColor": "#475569",
        "titleColor":     "#1e40af",
    },
    "flowchart": {
        "htmlLabels": True,
        "curve": "basis",
        "nodeSpacing": 50,
        "rankSpacing": 70,
        "padding": 20,
    },
    "sequence": {
        "actorMargin": 80,
        "boxMargin": 12,
        "messageMargin": 40,
        "mirrorActors": True,
    },
    "stateDiagram": {
        "useMaxWidth": True,
    },
}

PUPPETEER_CONFIG = {
    # Headless flags that work in CI / minimal Windows environments.
    "args": ["--no-sandbox", "--disable-setuid-sandbox"],
}


def find_mmdc() -> str:
    """Locate the local ``mmdc`` binary installed by ``npm install``."""
    candidates = [
        PROJECT_ROOT / "node_modules" / ".bin" / "mmdc.cmd",
        PROJECT_ROOT / "node_modules" / ".bin" / "mmdc",
    ]
    for c in candidates:
        if c.exists():
            return str(c)
    print(
        "ERROR: mmdc not found. Run "
        "`npm install --no-save @mermaid-js/mermaid-cli` first.",
        file=sys.stderr,
    )
    sys.exit(2)


def extract_mermaid_blocks(md_text: str) -> list[str]:
    """Pull every ```mermaid fenced block out of the markdown.

    Returns the diagram source strings in document order. Both ``` and
    ~~~ fences supported, and the fence may carry trailing whitespace.
    """
    pattern = re.compile(
        r"^```mermaid\s*\n(.*?)\n```\s*$",
        re.MULTILINE | re.DOTALL,
    )
    return [m.group(1).strip() for m in pattern.finditer(md_text)]


def replace_mermaid_with_images(md_text: str, image_paths: list[str]) -> str:
    """Replace each mermaid block with an image reference.

    ``image_paths`` must be in the same order ``extract_mermaid_blocks``
    returned. Image paths are resolved relative to the intermediate
    markdown file (so pandoc can find them on disk).
    """
    pattern = re.compile(
        r"^```mermaid\s*\n.*?\n```\s*$",
        re.MULTILINE | re.DOTALL,
    )
    iterator = iter(image_paths)

    def _sub(_match: re.Match[str]) -> str:
        path = next(iterator)
        # Trailing blank line keeps pandoc from gluing the image into a
        # surrounding paragraph — Word renders it on its own line then.
        return f"![]({path})\n"

    return pattern.sub(_sub, md_text)


def render_diagrams(
    blocks: list[str], force: bool, mmdc: str,
) -> list[Path]:
    """Render each diagram source to PNG. Returns the output paths.

    Skips rendering when the .mmd source on disk is unchanged from the
    candidate text — useful on incremental rebuilds because each call
    spawns a Chromium process and the 30-image suite takes ~90 seconds
    cold.
    """
    DIAGRAMS_DIR.mkdir(parents=True, exist_ok=True)

    # Drop the per-run config to a temp file so mmdc picks up our theme.
    config_path = DIAGRAMS_DIR / "_mermaid.config.json"
    config_path.write_text(json.dumps(MERMAID_CONFIG, indent=2), encoding="utf-8")
    puppeteer_path = DIAGRAMS_DIR / "_puppeteer.config.json"
    puppeteer_path.write_text(json.dumps(PUPPETEER_CONFIG, indent=2), encoding="utf-8")

    # CSS injected per-render: rounder corners, subtle drop shadow, more
    # generous text padding. Mermaid's default SVG is information-dense;
    # this softens it for slide-style presentation.
    css_path = DIAGRAMS_DIR / "_mermaid.css"
    # CSS belt-and-braces: even when themeVariables are honoured Mermaid
    # often still writes inline ``style="background-color: #fff"`` on
    # the edgeLabel <foreignObject> wrappers. !important on the
    # background+colour pair forces a high-contrast amber pill so
    # transition labels (e.g. ``DRAFT --> PENDING : submit_for_approval``)
    # read clearly when printed at A4 width.
    css_path.write_text(
        """
        .node rect, .node polygon, .node circle, .node ellipse {
            filter: drop-shadow(0 2px 4px rgba(15, 23, 42, 0.12));
            stroke-width: 2px !important;
        }
        text {
            font-family: 'Segoe UI', 'Inter', system-ui, sans-serif !important;
        }
        /* Edge labels — every flavour Mermaid emits */
        .edgeLabel,
        .edgeLabel rect,
        .edgeLabel foreignObject,
        .edgeLabel foreignObject div,
        .edgeLabel span,
        .edgeLabel p,
        .transition-label,
        g.edgeLabel rect.background {
            background-color: #fef3c7 !important;
            fill: #fef3c7 !important;
            color: #0f172a !important;
            font-weight: 600 !important;
            border-radius: 4px;
        }
        .edgeLabel text,
        .edgeLabel tspan,
        .edge-label text,
        .transition-label text {
            fill: #0f172a !important;
            font-weight: 600 !important;
        }
        /* StateDiagram transition labels render under .transition-label
           or .edgeTerminals — cover both. */
        .stateDiagram-v2 .transition-label rect,
        .stateDiagram-v2 g.edgeLabel rect {
            fill: #fef3c7 !important;
            stroke: #92400e !important;
            stroke-width: 1px !important;
        }
        .stateDiagram-v2 .transition-label text,
        .stateDiagram-v2 g.edgeLabel text {
            fill: #0f172a !important;
        }
        /* Subgraph clusters */
        .cluster rect {
            fill: #f8fafc !important;
            stroke: #cbd5e1 !important;
            stroke-dasharray: 4 4;
        }
        /* Notes */
        .note, .noteText {
            fill: #fef3c7 !important;
            stroke: #92400e !important;
        }
        """.strip(),
        encoding="utf-8",
    )

    output_paths: list[Path] = []
    for idx, source in enumerate(blocks, start=1):
        mmd_path = DIAGRAMS_DIR / f"diagram-{idx:02d}.mmd"
        png_path = DIAGRAMS_DIR / f"diagram-{idx:02d}.png"

        # Only re-render when the source has actually changed (idempotent
        # rebuild). ``force`` overrides this for full rebuilds.
        prior = mmd_path.read_text(encoding="utf-8") if mmd_path.exists() else None
        if not force and prior == source and png_path.exists():
            output_paths.append(png_path)
            print(f"  [skip] diagram-{idx:02d}.png (unchanged)")
            continue

        mmd_path.write_text(source, encoding="utf-8")

        # 1600px width for high-DPI slides without forcing scaling
        # artefacts when Word resizes for the page width.
        cmd = [
            mmdc,
            "-i", str(mmd_path),
            "-o", str(png_path),
            "-w", "1600",
            "-c", str(config_path),
            "-p", str(puppeteer_path),
            "-C", str(css_path),
            "--backgroundColor", "white",
            "-s", "2",  # 2x scale = crisp on high-DPI displays
        ]
        print(f"  [render] diagram-{idx:02d}.png")
        result = subprocess.run(
            cmd, cwd=PROJECT_ROOT, capture_output=True, text=True,
        )
        if result.returncode != 0:
            print(f"FAILED: diagram-{idx:02d}", file=sys.stderr)
            print(result.stdout, file=sys.stderr)
            print(result.stderr, file=sys.stderr)
            sys.exit(1)
        output_paths.append(png_path)

    return output_paths


def build_reference_docx(force: bool = False) -> None:
    """Produce a styled reference.docx pandoc will use for the conversion.

    Pandoc reads paragraph + character + table styles out of the
    reference doc and applies them. The strategy:

    1. Ask pandoc to dump its built-in default reference docx.
    2. Patch it with python-docx to get presentation-quality styling:
       - A4 portrait, slightly narrower margins so diagrams have room
       - Brand-blue heading colours (Heading 1/2/3 in #1e40af / #1e3a8a)
       - Inter / Segoe UI font family for body + headings
       - Serif font preserved for code blocks (readable monospace)
       - Title slide-style first page geometry

    The ``force`` flag re-creates from pandoc's default; otherwise we
    keep any existing reference doc so manual tweaks (e.g. inserting a
    real cover page in Word) survive rebuilds.
    """
    if REFERENCE_DOCX.exists() and not force:
        return

    # Step 1 — let pandoc emit its default reference docx. The
    # ``--print-default-data-file`` flag writes the file's bytes to
    # stdout (not honouring ``-o``), so we capture them ourselves.
    # ``stdout=subprocess.PIPE`` is essential — without it the binary
    # docx bytes spray to the terminal.
    result = subprocess.run(
        ["pandoc", "--print-default-data-file", "reference.docx"],
        check=True, cwd=PROJECT_ROOT,
        stdout=subprocess.PIPE,
    )
    REFERENCE_DOCX.write_bytes(result.stdout)

    # Step 2 — restyle via python-docx if available. Failing this step
    # is non-fatal: the unstyled reference still produces a valid docx.
    try:
        from docx import Document
        from docx.shared import Pt, RGBColor, Cm
        from docx.enum.text import WD_ALIGN_PARAGRAPH
    except ImportError:  # pragma: no cover
        print("  [info] python-docx not installed — using pandoc default style.")
        return

    doc = Document(str(REFERENCE_DOCX))

    # 1. Page geometry — A4 with comfortable margins for slide-style
    #    diagrams. Wider than the pandoc default (1in everywhere) so
    #    horizontal flowcharts breathe.
    for section in doc.sections:
        section.top_margin = Cm(2.0)
        section.bottom_margin = Cm(2.0)
        section.left_margin = Cm(2.0)
        section.right_margin = Cm(2.0)

    # 2. Brand palette — applied to Heading 1/2/3 + body for a unified
    #    look. Colours match the in-app sidebar palette (hex 1e40af is
    #    the same Tailwind ``blue-800`` used everywhere in the React UI).
    BRAND = {
        'Heading 1': {'colour': RGBColor(0x1E, 0x40, 0xAF), 'size': 22, 'bold': True},
        'Heading 2': {'colour': RGBColor(0x1E, 0x3A, 0x8A), 'size': 17, 'bold': True},
        'Heading 3': {'colour': RGBColor(0x31, 0x2E, 0x81), 'size': 14, 'bold': True},
        'Heading 4': {'colour': RGBColor(0x47, 0x55, 0x69), 'size': 12, 'bold': True},
        'Title':     {'colour': RGBColor(0x1E, 0x40, 0xAF), 'size': 36, 'bold': True},
        'Subtitle':  {'colour': RGBColor(0x47, 0x55, 0x69), 'size': 16, 'bold': False},
    }
    for style_name, spec in BRAND.items():
        if style_name not in [s.name for s in doc.styles]:
            continue
        style = doc.styles[style_name]
        font = style.font
        font.name = 'Segoe UI'
        font.size = Pt(spec['size'])
        font.color.rgb = spec['colour']
        font.bold = spec['bold']

    # 3. Body text — Inter-leaning sans, slightly larger than 11pt
    #    default for slide-friendly readability.
    if 'Normal' in [s.name for s in doc.styles]:
        normal = doc.styles['Normal']
        normal.font.name = 'Segoe UI'
        normal.font.size = Pt(11)
        normal.font.color.rgb = RGBColor(0x0F, 0x17, 0x2A)

    # 4. Code style — preserve a clean monospace; pandoc maps fenced
    #    code blocks to "Source Code" or "Verbatim Char".
    for code_style in ('Source Code', 'Verbatim Char'):
        if code_style in [s.name for s in doc.styles]:
            cs = doc.styles[code_style]
            cs.font.name = 'Consolas'
            cs.font.size = Pt(10)
            cs.font.color.rgb = RGBColor(0x1E, 0x40, 0xAF)

    doc.save(str(REFERENCE_DOCX))
    print(f"  [style] {REFERENCE_DOCX.name} restyled with brand palette")


def run_pandoc() -> None:
    cmd = [
        "pandoc",
        str(INTERMEDIATE_MD),
        "-o", str(OUTPUT_DOCX),
        "--from", "markdown+pipe_tables+raw_html",
        "--to", "docx",
        "--reference-doc", str(REFERENCE_DOCX),
        "--toc", "--toc-depth=2",
        "--standalone",
        "--metadata", "title=Quot PSE — Module Process Flows",
        "--metadata", "subtitle=Public-Sector IFMIS Architecture Reference",
        "--metadata", "author=Quot PSE Engineering",
        "--metadata", "date=2026-05-08",
        # Resource path so relative image refs in the markdown resolve
        # against the diagrams directory.
        "--resource-path",
        f"{DIAGRAMS_DIR}{os.pathsep}{DOCS_DIR}{os.pathsep}{PROJECT_ROOT}",
    ]
    print(f"  [pandoc] -> {OUTPUT_DOCX.name}")
    subprocess.run(cmd, check=True, cwd=PROJECT_ROOT)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--force", action="store_true",
                    help="Re-render every diagram even if unchanged.")
    ap.add_argument("--no-docx", action="store_true",
                    help="Render diagrams only; skip the pandoc step.")
    args = ap.parse_args()

    if not SRC_MD.exists():
        print(f"Source not found: {SRC_MD}", file=sys.stderr)
        return 1

    md_text = SRC_MD.read_text(encoding="utf-8")
    blocks = extract_mermaid_blocks(md_text)
    print(f"Found {len(blocks)} mermaid block(s) in {SRC_MD.name}")

    mmdc = find_mmdc()
    image_paths = render_diagrams(blocks, args.force, mmdc)

    # Use forward slashes so pandoc handles them identically across OSes.
    rel_paths = [
        p.relative_to(DIAGRAMS_DIR).as_posix() for p in image_paths
    ]
    intermediate = replace_mermaid_with_images(md_text, rel_paths)
    INTERMEDIATE_MD.write_text(intermediate, encoding="utf-8")
    print(f"  [write] {INTERMEDIATE_MD.relative_to(PROJECT_ROOT)}")

    if args.no_docx:
        return 0

    build_reference_docx(force=args.force)
    run_pandoc()
    print(f"\nOutput: {OUTPUT_DOCX.relative_to(PROJECT_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
