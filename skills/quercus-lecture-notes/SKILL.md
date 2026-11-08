---
name: quercus-lecture-notes
description: Inventory and sync a selected Quercus course's lecture notes and identify local gaps.
---
Run from the Quercus project root. Identify the course with `python3 quercus.py courses`. Run `python3 quercus.py download COURSE_ID --preview`; review the filename-based candidates, their IDs and missing/changed status. Include known missed lecture files with `--include-id ID` and exclude false positives with `--exclude-id ID`; repeat options as needed. Run the same command without `--preview` to download selected missing notes. Existing and changed files are never overwritten; report them for manual review. Show inventory and failed or unavailable items, explain that names and metadata do not prove coverage, and offer document import for missing notes. Use an existing QUERCUS_TOKEN; otherwise have the user run the commands locally and share results, never their token. Do not assert all lectures were covered merely because the command completed.
