# Committing & Pushing Changes with Claude Code

A plain-English reminder of how changes get saved to GitHub when you work on
this project (`Islandboy1968/global-m2`) through **Claude Code on the web**.
If you forget the steps, just ask the project: *"how do I commit changes?"*

---

## The short version

1. Tell Claude what to change (e.g. *"replace the contents of `data/layout.js`
   with this..."*).
2. Claude edits the file and makes a **commit** on the working branch
   (branches are named like `claude/<something>`).
3. Claude **pushes** that branch to GitHub. If the push succeeds, you're done —
   the change is saved on GitHub.
4. (Optional) Ask Claude to **open a pull request** if you want to merge the
   change into `main`. Claude will **not** create a PR unless you ask.

That's it for the normal case. The rest of this doc is for when the push fails.

---

## What "commit" vs "push" means

- **Commit** = a saved snapshot of your change *inside the session's local copy*
  of the repo. It is safe, but it is **not yet on GitHub**.
- **Push** = uploading those commits to GitHub so they actually appear in the
  repository (and survive after the session ends).

A session container is temporary. **If a commit is never pushed, it can be
lost when the session is reclaimed.** So a change isn't truly "saved" until the
push succeeds.

> If you see a reminder like *"There are N unpushed commit(s)..."*, it means the
> work is committed locally but has not reached GitHub yet.

---

## The most common problem: push fails with "403 / Permission denied"

Claude Code on the web pushes through the **Claude GitHub app**, *not* your
personal GitHub login. If that app isn't installed (or doesn't have access to
this repo), every push fails like this:

```
remote: Permission to Islandboy1968/global-m2.git denied to Islandboy1968.
fatal: ... The requested URL returned error: 403
```

### How to fix it (one-time setup)

1. Go to **https://github.com/apps/claude**
2. Click **Install** (or **Configure** if already installed).
3. Choose **Only select repositories → `global-m2`** (or *All repositories*).
4. Click **Install & Authorize** and approve the permissions
   (this grants **Contents: Read and write**, which is what lets Claude push).

### How to check whether it's installed

- Go to **https://github.com/settings/installations**
  (Settings → *Applications* → **Installed GitHub Apps**).
- You should see **Claude** listed there. If you only see other apps
  (e.g. Netlify) and **no Claude**, that's the problem — install it using the
  steps above.

> Note: an entry under **"Authorized OAuth Apps"** is only a login, not push
> access. You need **Claude** under **Installed GitHub Apps**.

### After installing

- **Start a fresh Claude Code web session** on this repo. An already-running
  session won't automatically pick up the new credentials.
- Then ask Claude to push again. The previously committed work will upload as
  soon as a session has write access — nothing is lost in the meantime.

---

## Quick troubleshooting checklist

| Symptom | Likely cause | Fix |
|---|---|---|
| Push returns `403 ... denied` | Claude GitHub app not installed / no access to this repo | Install at https://github.com/apps/claude, grant `global-m2` |
| "N unpushed commits" reminder keeps appearing | Push hasn't succeeded yet | Fix access (above), then push |
| Change works in the session but isn't on GitHub | Committed but not pushed | Push the branch |
| Want it merged into `main` | PRs aren't automatic | Ask Claude to "open a pull request" |

---

## Things to remember

- Claude commits and pushes **only when you ask** (or as part of completing a
  task you requested). It pushes to a `claude/*` branch, **never** directly to
  `main` without permission.
- Creating a **pull request** is a separate, explicit step — ask for it.
- The fix above (installing the GitHub app) is a **one-time** thing. Once Claude
  shows up under *Installed GitHub Apps* with access to this repo, future pushes
  just work.
