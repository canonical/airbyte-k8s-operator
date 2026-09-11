# Releasing the Airbyte charm

This charm uses Charmhub [versioned tracks](https://documentation.ubuntu.com/charmcraft/stable/howto/manage-tracks/)
so that shipping a new major version does not force-upgrade users on older majors.
This document is the reference for maintainers on how releases flow and what to
do when cutting a new major.

## Channel model

A Charmhub channel is `<track>/<risk>` (e.g. `latest/edge`, `2/stable`). The
mapping from git branch to edge channel is:

| Branch     | Publishes to (edge)                              | Role                                        |
|------------|-------------------------------------------------|---------------------------------------------|
| `main`     | `latest/edge` **and** `<current-major>/edge`    | current major development line              |
| `track/N`  | `N/edge`                                         | maintenance line for an older major `N`     |

`main` is always the current major. Today the current major is **2**, so `main`
publishes to `latest/edge` and `2/edge`. Older majors are maintained on
`track/N` branches (e.g. `track/1` → `1/edge`).

`track/N` for the *current* major is kept around but stays **dormant** — `main`
drives `<current-major>/edge`, so the branch is only activated when `main` moves
on to the next major (see the runbook below).

Stable channels (`latest/stable`, `N/stable`) are **never published to
directly** — they are reached by *promoting* an existing edge revision.

## How it works: build once, release many

A *revision* is the immutable artifact; channels are pointers to a revision. We
never rebuild the same source to serve a second channel — we release the same
revision into it.

- **`publish_charm.yaml`** runs on push to `main` and `track/*`:
  - `test-and-publish-charm` builds the charm **once** and publishes it to the
    branch's edge channel (`main` → `latest/edge`, `track/N` → `N/edge`).
  - `mirror-to-major-track` (main only) takes the revision just published to
    `latest/edge` and releases the **same revision** into the current major
    track (`2/edge`) using the promote workflow. No rebuild; both channels point
    at one revision.
- **`promote_charm.yaml`** is a manual (`workflow_dispatch`) workflow that
  releases the revision currently in an origin channel to a destination channel.

> **Do not push to the current major's `track/N` while `main` mirrors to it.**
> During the v2 era `main` owns `2/edge`; a push to `track/2` would also publish
> `2/edge` and the two would clobber each other's revisions. All current-major
> work goes to `main`; `track/2` stays frozen until the next cutover.

## Promoting to stable

Run the **Promote charm** workflow (Actions → Promote charm → Run workflow) once
per channel:

- `latest/edge` → `latest/stable`
- `<current-major>/edge` → `<current-major>/stable` (e.g. `2/edge` → `2/stable`)

## Charmhub credentials (`CHARMHUB_TOKEN`)

Publish and promote authenticate with a Charmhub macaroon stored in the
`CHARMHUB_TOKEN` repository secret. **Scope it to all channels** so that adding a
new track never requires a new token:

```bash
charmcraft login \
  --export=charmhub-auth.token \
  --charm=airbyte-k8s \
  --permission=package-manage-releases \
  --permission=package-manage-revisions \
  --permission=package-view-releases \
  --permission=package-view-revisions \
  --ttl=2592000
gh secret set CHARMHUB_TOKEN -R canonical/airbyte-k8s-operator < charmhub-auth.token
rm charmhub-auth.token
```

- Omitting `--channel` authorizes all of the charm's channels. If you instead
  pin channels (`--channel=latest/edge ...`) you must include every track's
  `edge` and `stable`, and re-issue the token whenever a track is added —
  otherwise releases fail with
  `Macaroon channel restrictions ... do not allow release to <channel>`.
- `--ttl` is in seconds (`2592000` = 30 days). When the token expires,
  publish/promote fail with `api-error: Invalid macaroon`; regenerate with the
  same command.

## Adding a new major (cutover runbook)

When `main` moves from major `N` to `N+1` (e.g. v2 → v3), do these **in order**:

1. **Create the new track and confirm the token covers it.**
   ```bash
   charmcraft create-track --name airbyte-k8s --track 3
   ```
   The track-name guardrail is `\d+(\.\d+)?`, registered with the Charmhub team.
   If `CHARMHUB_TOKEN` is channel-pinned (not all-channels), regenerate it to
   include `3/edge` and `3/stable` first — otherwise the mirror step fails.

2. **Bring the outgoing major's `track/N` up to date first.** `track/2` already
   exists (kept dormant during the v2 era) — fast-forward it to `main`'s final
   v2 commit so `2/edge` keeps receiving v2 fixes from it. Do this **before**
   merging v3 into `main`; otherwise `2/edge` goes stale in the interim. (If the
   branch had been deleted, recreate it from the last v2 commit instead — mind
   the seeding gotcha below.)

3. **Point `main` at the new major.** In `.github/workflows/publish_charm.yaml`,
   change `mirror-to-major-track`'s `destination-channel` from `2/edge` to
   `3/edge`.

4. **Merge v3 into `main`.** It now publishes to `latest/edge` and mirrors to
   `3/edge`. `track/2` independently keeps publishing `2/edge`.

5. **Communicate the breaking change.** `latest` now points to v3, so anyone
   tracking `latest/stable` is auto-upgraded v2 → v3 at the next stable
   promotion. Announce it and document that v2 users should switch to `2/stable`.

## Known gotchas

- **Creating a track branch can skip/crash the publish run.** A branch-*creation*
  push sends `before=0000000...`; operator-workflows `get-plan` runs
  `git diff <before> <after>` → `fatal: bad object` → publish is skipped. Seed a
  track with a two-step push so the publishing push is an *update*, not a
  creation:
  ```bash
  # 1) create the branch at a commit whose workflow lacks the track/* trigger (no run)
  git push origin <old-commit>:refs/heads/track/2
  # 2) fast-forward it to the intended commit (an update -> publishes normally)
  git push origin <target-commit>:refs/heads/track/2
  ```
- **Token failures** surface as `api-error: Invalid macaroon` (expired) or
  `Macaroon channel restrictions ... do not allow release to <channel>` (scope).
  Both are fixed by regenerating `CHARMHUB_TOKEN` (see credentials above).
