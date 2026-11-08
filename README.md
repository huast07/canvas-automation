# Quercus automation

A local Python tool and five Codex skills for working with University of Toronto Quercus courses. The tool lists courses, previews and downloads likely lecture notes, and retrieves assignment and syllabus information. The skills guide Codex through those tasks, course summaries, and exam preparation.

## Requirements

- Python 3.8 or later. The tool uses only the Python standard library.
- A Quercus account and a personal access token, if token creation is enabled for your account. Find it under **Account → Settings → New Access Token** in Quercus.
- Codex with support for local skills, if you want to use the skills.

Treat your access token like a password. Do not commit it or paste it into a chat. The commands prompt for it without displaying what you type. For repeated commands, you may instead set `QUERCUS_TOKEN` in your terminal session; avoid putting it in shell history or a project file. Remove it with `unset QUERCUS_TOKEN` when finished.

## Set up your Quercus access token

1. Sign in to [Quercus](https://q.utoronto.ca/) in your browser. Open **Account → Settings** and look for **New Access Token**. If the option is not available, ask your institution about API access; do not try to bypass its controls.
2. Give the token a recognizable purpose and an expiration date if offered. Generate it and copy it into a password manager or another secure location. Quercus may show the token only once.
3. Run a command such as `python3 quercus.py courses` from the project directory. Paste the token at the hidden prompt and press Enter; nothing is shown while you type. Repeat for each command, or use the session option below.

For a single terminal session, you can avoid repeated prompts without putting the token in your shell history:

```sh
read -rs 'QUERCUS_TOKEN?Quercus access token: '  # zsh
export QUERCUS_TOKEN
python3 quercus.py courses
unset QUERCUS_TOKEN
```

The `read` syntax above is for the default macOS zsh shell; enter the token only at the prompt, not on the command line. Other shells may use different syntax. An environment variable is inherited by processes launched from that terminal, so use it only in a trusted session. Keep tokens out of chat, Git, `.env` files and logs. If a token is exposed or no longer needed, revoke it in Quercus **Account → Settings** and create a replacement if needed. Token creation and expiration options depend on institutional settings.

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

## Exam preparation workflows

The repository also includes skills for an end-to-end preparation session: `$quercus-prepare-exam`, `$quercus-document-import`, `$quercus-exam-scope`, `$quercus-study-planner`, `$quercus-cram`, and `$quercus-mock-exam`. Install or update them using the installation instructions above, then start a new Codex chat in this project. Ask Codex to use `$quercus-prepare-exam` to choose a course, sync lecture notes, map exam scope and choose a practice path. `$quercus-exam-prep` requires lecture sync and scope mapping first. Cram mode uses the same prerequisites and adapts the session to available time. These are Codex skills: the model performs the interpretation, tutoring and feedback; the Python CLI does not itself generate summaries or questions.

Preview reports file IDs and whether candidates are missing locally or changed remotely. Override the heuristic when necessary:

```sh
python3 quercus.py download COURSE_ID --preview --include-id FILE_ID --exclude-id OTHER_ID
python3 quercus.py download COURSE_ID --include-id FILE_ID --exclude-id OTHER_ID
```

A sync records downloaded files in `study-data/COURSE_ID/sync.json`. It keeps existing files, including remotely changed files, and reports changes for manual review. Metadata counts for modules, pages, discussions and assignments are informational; this version does not download their contents or reliably detect missing numbered lectures. A completed sync is not proof of complete lecture coverage.

Add a missing local document and inspect the course inventory:

```sh
python3 study.py import COURSE_ID lecture /path/to/notes.pdf
python3 study.py import COURSE_ID scope /path/to/exam-scope.pdf
python3 study.py import COURSE_ID past-exam /path/to/past-exam.pdf
python3 study.py inventory COURSE_ID
python3 study.py check-ready COURSE_ID
```

Imports are copied into `study-data/`, hashed for duplicate detection, and associated with the course. `study.py extract PATH` extracts text from UTF-8 text, DOCX and PPTX files; PDFs and image-only files require suitable PDF/OCR tools available to Codex. The exam-scope skill reviews source material and saves a scope JSON record using `study.py save-scope COURSE_ID PATH`; it requires `topics` and `problems` arrays. `study.py record-attempt COURSE_ID PATH` appends a JSON attempt with a `topic` field only when requested by the student. Both downloads and study data are local and ignored by Git; to remove them, delete the relevant course folders yourself. Deleting the Git repository alone does not remove copies elsewhere.

Run the local tests with `python3 -m unittest discover -s tests -v`. The skill workflows depend on Codex and available document tools and have not been validated against every course or exam format. Read generated answers critically and verify exam dates and requirements with the instructor.
