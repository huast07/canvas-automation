# Quercus automation

A local Python tool and five Codex skills for working with University of Toronto Quercus courses. The tool lists courses, previews and downloads likely lecture notes, and retrieves assignment and syllabus information. The skills guide Codex through those tasks, course summaries, and exam preparation.

## Requirements

- Python 3.8 or later. The tool uses only the Python standard library.
- A Quercus account and a personal access token, if token creation is enabled for your account. Find it under **Account → Settings → New Access Token** in Quercus.
- Codex with support for local skills, if you want to use the skills.

Treat your access token like a password. Do not commit it or paste it into a chat. The commands prompt for it without displaying what you type. For repeated commands, you may instead set `QUERCUS_TOKEN` in your terminal session; avoid putting it in shell history or a project file. Remove it with `unset QUERCUS_TOKEN` when finished.

## Installation

```sh
git clone https://github.com/huast07/quercus-automation.git
cd quercus-automation
python3 quercus.py --help
```

Install the skill folders into your personal Codex skills directory:

```sh
mkdir -p ~/.codex/skills
cp -R skills/quercus-* ~/.codex/skills/
```

Review existing folders before copying if you already have skills with those names. Restart Codex or start a new chat if the new skills do not appear immediately. The skills expect this project as the working directory; open Codex in the cloned repository. Skills are instructions for Codex, not standalone executable programs.

## Set up and use each skill

### List courses: `quercus-courses`

Open the project in Codex and ask it to list your Quercus courses, or invoke `$quercus-courses`. The skill uses:

```sh
python3 quercus.py courses
```

Enter your token at the hidden prompt and note the course ID. If Codex cannot access a token configured in its environment, run the command yourself and share the course list, not the token.

### Download lecture notes: `quercus-lecture-notes`

Ask Codex to download lecture notes for a course, or invoke `$quercus-lecture-notes` with its course ID. To run the underlying commands yourself:

```sh
python3 quercus.py download COURSE_ID --preview
python3 quercus.py download COURSE_ID
```

Preview first. The filter selects documents whose name or folder contains lecture, lec, notes, or slides, and excludes names or folders indicating assignments, exams, tutorials, solutions, or syllabi. This heuristic can miss notes or select unrelated files. The tool reads the course Files API, not external links. Files go into `downloads/` by course and folder; add `--output PATH` to change the destination. Existing files are skipped, including when the remote file changes; previously downloaded files are not removed.

### Summarize a course: `quercus-summary`

Download the lecture notes first, then ask Codex to summarize a course or invoke `$quercus-summary` and identify its folder under `downloads/`. Codex reads available materials, summarizes topics and connections, cites the files, and identifies material it cannot read. You can also point it at another local folder of course materials. A summary only covers the files actually available and readable.

### Check assignments: `quercus-deadlines`

Ask Codex for the next assignment due in a course, or invoke `$quercus-deadlines` with the course ID. The skill uses:

```sh
python3 quercus.py due COURSE_ID
python3 quercus.py syllabus COURSE_ID
```

The first command displays future dated Canvas assignments in your computer's local timezone, with submission status when available. The second prints the syllabus body as HTML. Codex can compare the two and flag syllabus-only dates or discrepancies. A linked syllabus may need to be provided separately. This is an on-demand check; it does not schedule notifications. Request a separate scheduled reminder if you want one.

### Prepare for an exam: `quercus-exam-prep`

Place your past midterms or finals and the instructor's stated exam scope in a local folder, alongside or separate from your downloaded notes. Ask Codex to use `$quercus-exam-prep`, identify the files and exam, and describe any topics to exclude. The skill categorizes past questions by topic and source, then creates a progression from basic concepts and practice to exam-level problems, with hints and worked solutions. It will ask for missing exam papers or scope rather than assume lecture downloads contain them.

## Privacy and limitations

The tool only reads data from Quercus; it does not submit assignments or modify courses. Your token grants access to your account, so revoke it through Quercus if exposed. Downloaded materials remain on your computer and are ignored by Git by default. Some course content can be unavailable, locked, image-only, or hosted outside Canvas; the tool and summaries cannot guarantee complete coverage.
