---
name: quercus-document-import
description: Import a student's missing course notes, exam guidance or past exam into a local course inventory.
---
Ask for the course ID, file path and document type (lecture, scope, past-exam, other). Run `python3 study.py import COURSE_ID TYPE PATH` from the project root. This copies the file locally, records its original name and hash, and detects duplicates. Report unreadable or unsupported files; use PDF or document skills as appropriate. Explain that the local copy can be removed by the student and do not transmit course material externally without their consent.
