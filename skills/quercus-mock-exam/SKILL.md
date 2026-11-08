---
name: quercus-mock-exam
description: Create a sourced, exam-aligned mock and review a student's answers.
---
Use the selected exam scope and course sources; if unavailable, guide the student to map them first. Confirm exam format, time, allowed aids and requested length, and flag unknowns. Generate original mixed questions calibrated to the documented problem categories and label historical versus generated questions. Keep solutions separate until the student requests them or submits answers. Check answers and calculations independently where feasible; `python3 check_math.py EXPECTED_EXPRESSION ANSWER_EXPRESSION` compares basic arithmetic exactly but does not verify units, formulas or symbolic reasoning, explain mistakes and offer targeted follow-up practice. Clearly mark uncertain grading or incomplete coverage; do not predict the exam grade.
