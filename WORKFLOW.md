# Workflow: committing, deploying, verifying

How changes reach carolinashowtimes.com. Follow this exactly so the history
and the server stay predictable.

The short version:

```bash
git switch -c short-topic-name     # never commit on main
# ...edit, test locally...
git commit -a                      # subject, blank line, why
gh pr create --base main           # summary + testing notes
gh pr merge <N> --merge --delete-branch
git switch main && git pull --ff-only
./deploy.sh                        # ships it and runs the pipeline
# ...then verify against the live site, not just the deploy output
```

## 1. Commit

- **Branch per change.** `git switch -c <topic>` off an up-to-date `main`.
  Don't commit directly to `main`.
- **Message shape:** imperative subject, blank line, then *why* — the
  reasoning, the measurement, the thing that surprised you. Not a list of
  files. End with the `Co-Authored-By:` line your harness specifies.
- **Never stage blindly.** `git add -A` once pulled 14MB of HAR captures
  containing session cookies into a commit. Run `git status --short` and
  look at the list before committing.
- **Scan for secrets before pushing:**
  ```bash
  git diff --cached | grep -inE "appkey=|userkey=|[0-9a-f]{8}-[0-9a-f]{4}-"
  ```
- **Never commit:** `.env`, `har_files/`, `movie_showtimes.db`,
  `movie_showtimes.csv`, `index.html`, `power.html`, `power.json`,
  `showtimes.json`. All generated or sensitive; all git-ignored already.

## 2. Pull request

```bash
gh pr create --base main --title "..." --body "..."
gh pr merge <N> --merge --delete-branch
git switch main && git pull --ff-only
```

Body should say what changed, **why**, and how it was tested. Somebody
reading the PR later should not have to reconstruct the reasoning.

Two traps found the hard way:

- **Don't stack PRs.** Merging a parent with `--delete-branch` makes GitHub
  *close* the child PR rather than retarget it (this killed PR #8). If you
  must stack, merge the parent, then open a fresh PR for the child.
- **`gh pr edit --base` is broken on this repo** — it fails with a
  Projects-classic GraphQL error. Use the REST API instead, and note it
  refuses once a PR is closed:
  ```bash
  gh api -X PATCH repos/AndrewGEvans95/carolina-theatre-scraper/pulls/<N> -f base=main
  ```

## 3. Deploy

```bash
./deploy.sh
```

One SSH connection that, on the server: `git pull --ff-only origin main` in
`/opt/carolina-theatre-scraper` as `carolina-scraper`, installs
requirements with `venv/bin/python -m pip`, then runs `manual_run.sh` —
scrape, availability, `index.html`, `showtimes.json`, `power.html` +
`power.json`.

- **Deploy only ships code.** Cron runs the same pipeline every 6 hours
  (00:00, 06:00, 12:00, 18:00 UTC), so content refreshes without you.
- **Only changed a generator, template or stylesheet?** `./deploy.sh
  --no-scrape` rebuilds the pages from the data already on the server.
  A full deploy re-fetches 66 film pages for data that hasn't moved.
- **Takes 2–5 minutes.** If your tool call times out, it is still running
  server-side — redirect to a log and read that rather than re-running:
  ```bash
  ./deploy.sh > /tmp/deploy.log 2>&1; grep -E "After:|All tasks completed|ERROR" /tmp/deploy.log
  ```
  A dropped local connection does **not** abort the remote run. Check the
  server's log before assuming failure.
- **Never edit files in `/opt` directly.** The next `git pull --ff-only`
  will refuse and the deploy stops.

## 4. SSH to the server

Alias `carolinashowtimes` → root on the DigitalOcean droplet.

- **ufw rate-limits port 22** (`LIMIT`): roughly 6 connections per 30
  seconds gets your IP banned for about a minute. **Batch everything into
  one `ssh` invocation.** Never loop `scp` or run a command per host check.
  For anything multi-step:
  ```bash
  ssh carolinashowtimes 'bash -s' < script.sh
  ```
- **Never put a pattern that matches your own command into a remote
  `pkill -f`.** `pkill -f "apt-get"` matched the ssh session's own shell
  and killed the connection mid-script. Use a bracket: `pkill -f "[a]pt-get"`.
- Read-only checks first; back up before anything destructive; prefer
  `mv` to an archive directory over `rm`.
- Useful one-liners:
  ```bash
  ssh carolinashowtimes 'tail -40 /var/log/carolina-scraper/scraper.log'
  ssh carolinashowtimes 'crontab -l -u carolina-scraper'
  ssh carolinashowtimes '/opt/carolina-theatre-scraper/manual_run.sh'   # rerun pipeline
  ```

## 5. The power dashboard is private

The dashboard is published at an **unlisted URL**, not from the normal
web root and not linked from anywhere. Where it goes is decided on the
server by `/etc/carolina-scraper/power-path`:

- **file present** → published at `/var/www/html/<token>/power.html`
- **file absent** → private, at `/opt/carolina-theatre-scraper/private/`

So publishing and unpublishing are a server-side toggle, taking effect on
the next run; deleting the token file and removing the directory takes it
offline. Don't write the token into the repository, a `robots.txt` or a
nav link — any of those would advertise the path that keeps it quiet. The
page carries `noindex,nofollow` so search engines skip it.

To look at it: `./view_power.sh` copies that directory down and opens the
page. It opens on a WOPR terminal - password `JOSHUA` - which is set
dressing rather than access control, since the check runs in the browser. The directory carries its own `styles.css`, so the copy renders the
same as the published version would.

## 6. Secrets

- Ticketing API keys live at **`/etc/carolina-scraper/api.env`** on the
  server — `root:carolina-scraper`, mode `640`, deliberately **outside
  `/opt`** so no `git pull` or `deploy.sh` can touch them.
- Locally they live in `.env` (git-ignored). Load them via
  `availability.load_credentials()`; don't paste keys into commands.
- Without credentials the availability step logs and skips; the rest of
  the pipeline still works. Keep it that way.

## 7. Verify — the step that actually matters

A clean deploy log is not evidence the change worked. Check the thing you
changed, on the live site:

```bash
curl -s https://carolinashowtimes.com/ | grep -c sold-bar          # content present
ssh carolinashowtimes 'tail -5 /var/log/carolina-scraper/scraper.log'
```

- **UI changes:** screenshot at several widths with headless Chrome and
  *look at the image*. Check for horizontal overflow, ragged row heights,
  and glyphs the font lacks — Press Start 2P has no `→`, which shipped
  once as `12.00_14.45`.
  - **Copy `styles.css` into the directory you generate into.** An
    unstyled page trivially "fits", so measuring one proves nothing. A
    table overflow on every laptop-width window shipped this way.
  - **Check a range of widths, not two.** The page was fine at 1280px and
    390px while broken at everything between. A layout that needs a fixed
    width needs the breakpoint set from that measurement, plus room for a
    scrollbar.
- **Data changes:** query the database on the server, don't infer from the
  page.
- **Interaction:** drive the filters/sort in a real browser and read the
  console for errors.

Real bugs found this way, after "successful" deploys: the availability
window skipping the next four hours of showings (UTC vs theatre time), a
stale-snapshot ordering bug, and velocity columns silently clipped off the
page by 84px of table overflow.

## 8. Standing gotchas

- **Time:** showtimes are stored in **theatre-local** time; the server runs
  **UTC**. Anything compared against `formatted_datetime` or `starts_at`
  must use theatre time (`availability.theatre_now()`). But `checked_at`
  stays on the server clock — readers pick the newest row by string order,
  so mixing clocks makes a fresh row sort below an old one.
- **Titles differ between sources:** the website says "Pride and
  Prejudice", ticketing says "Pride & Prejudice". Match showings on start
  time + room, never on title.
- **Don't write to the ticketing system.** Reads only: no cart, basket or
  order calls, ever. Holding inventory to measure it takes real tickets off
  sale and looks like fraud to their vendor.
- **`har_files/`** may contain session cookies. Useful for research,
  never committed.
