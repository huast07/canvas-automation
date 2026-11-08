---
name: quercus-deadlines
description: Find the next Quercus assignment due and compare it with the course syllabus.
---
Identify the course ID; run `python3 quercus.py due COURSE_ID` and `python3 quercus.py syllabus COURSE_ID` from the project root. Use an existing QUERCUS_TOKEN; otherwise ask the user to run commands locally and share output without the token. Interpret syllabus HTML, and report the next upcoming dated assignment with local timezone, submission status if known, and link. Compare syllabus-only dates and flag differences or missing dates rather than guessing. This check runs on demand; a scheduled notification requires a separate user-requested reminder or automation.
