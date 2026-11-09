---
name: quercus-summary
description: Summarize downloaded or imported Quercus course materials at a high level.
---
Identify the course and run `python3 study.py inventory COURSE_ID`. Run `python3 study.py index COURSE_ID` to extract downloaded and imported sources into the local source index. Inspect the index, extracted texts and originals; report partial or unreadable sources. Use `python3 study.py extract PATH` for text, DOCX and PPTX; use PDF/document tools for other formats; `python3 study.py index COURSE_ID --ocr` attempts local OCR when pdftoppm and tesseract are installed. OCR and extracted equations require verification against originals. Check extracted equations, tables and diagrams against originals. Give a high-level topic map, prerequisites, concepts and connections, citing file names and page or slide numbers where available. Identify unreadable, missing or inaccessible materials; do not claim complete coverage. Do not infer exam scope from lecture notes alone.

For a course knowledge map, inventory each available lecture and source before summarizing. Identify distinct concepts, methods, variants, assumptions and relationships appropriate to the discipline; preserve source and page references. Report unreadable or omitted sources and avoid treating one broad heading per lecture as complete coverage.
