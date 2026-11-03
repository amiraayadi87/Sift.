# Sift

An AI job-search agent: a daily feed of jobs for the roles you type into the search bar, filtered with facts about you, shortlisted against your own fit rules, with an honest tailored CV for each shortlisted job.

Sift runs as a Claude artifact (the app) plus three Claude scheduled tasks (Collect, Shortlist, Tailor CVs). The collector pulls listings from job boards, removes duplicates, checks locations and commutes, and writes everything to one shared set of tables.

## Parts
- `app/na.html`: the Sift app. Search bar, feed, "Me" facts, and Collect / Shortlist / Make CVs buttons.
- `engine/`: the collector, a single standard-library Python file (`na_engine.py`) built from `engine/src` by `make_single_file.py`.
- `database/schema.json`: the four tables (Search, Me, Feed, Runs) and their columns.
- `tasks/`: the multi-user sections of each scheduled task's instructions, and `cv/cv_pdf.py`, which renders a Markdown CV into a one-page A4 PDF.

## Data model
A Google Sheet and Sift's built-in database hold the same four tables with the same columns: sheet tab = database collection, sheet row = document (Feed rows keyed by Job ID). Other users' data lives only under `u/<user id>/` and is never mixed with the owner's.

## Setup
Replace the placeholders before running your own copy:
- `YOUR_GOOGLE_SHEET_ID` and `YOUR_FIT_RULES_DOC_ID` in `app/na.html`
- `<SHORTLIST_TASK_ID>` and `<CV_TASK_ID>` in `tasks/users-*.txt`

## Tests
```
python -m pytest engine/tests
```
