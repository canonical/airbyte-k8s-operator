# Releasing the Airbyte charm

This charm uses Charmhub [versioned tracks](https://documentation.ubuntu.com/charmcraft/stable/howto/manage-tracks/)
so that shipping a new major version does not force-upgrade users on older majors.
This document is the reference for maintainers on how releases flow and what to
do when cutting a new major.

## Channel model

A Charmhub channel is `<track>/<risk>` (for example, `latest/edge`, `2/stable`).
The mapping from git branch to edge channel is:

| Branch     | Publishes to (edge)                              | Role                                        |
|------------|--------------------------------------------------|---------------------------------------------|
| `main`     | `latest/edge` **and** `<current-major>/edge`     | current major development line              |
| `track/N`  | `N/edge`                                          | maintenance line for an older major `N`     |

`main` is always the current major. Today the current major is **2**, so `main`
publishes to `latest/edge` and mirrors that revision to `2/edge`.

Each branch publishes through its **own** copy of `publish_charm.yaml`. A push runs
the workflow file present on the pushed branch. A `track/N` branch therefore
publishes to `N/edge` whenever it is pushed. During the current major's lifetime
the tracks are **dormant by convention**: all current-major work goes to `main`
(which drives `<current-major>/edge` through the mirror), and the `track/N` branches
receive no pushes. A track becomes active again at a cutover (see the runbook).

> Dormancy is a convention, not an enforced lock: pushing to `track/2` today
> **would** publish `2/edge` from that branch's own workflow. Don't push to the
> current major's track while `main` is mirroring to it, or the two would compete
> over `2/edge`.

Stable channels (`latest/stable`, `N/stable`) are **never published to
directly**. They are reached by *promoting* an existing edge revision.

## How it works: build once, release many

A *revision* is the immutable artifact; channels are pointers to a revision. We
never rebuild the same source to serve a second channel. Instead we release the
same revision into it.

- **`publish_charm.yaml`** runs on push to `main`:
  - `test-and-publish-charm` builds the charm **once** and publishes it to
    `latest/edge`.
  - `mirror-to-major-track` then releases whatever revision is on `latest/edge`
    into the current major track (`2/edge`) through the promote workflow, with no
    rebuild. It runs after `test-and-publish-charm` succeeds and is skipped if that
    fails, so like every publish here it depends on a tree-matching integration-test
    run (see the gotcha below). The workflow's `concurrency` group serializes runs
    per ref, so no other push can move `latest/edge` between a run's publish and
    its mirror. GitHub keeps only one queued run per group, so a burst of pushes
    may skip intermediate revisions. The newest push wins.
- **`promote_charm.yaml`** is a manual (`workflow_dispatch`) workflow that
  releases the revision currently in an origin channel to a destination channel.

To publish a fix on a maintenance track (for example, ship a `track/1` fix to
`1/edge`), merge or push it to that branch. The branch's own `publish_charm.yaml`
publishes it to the matching `N/edge` on push. There is no separate manual
publish trigger.

## Promoting to stable

Run the **Promote charm** workflow (Actions → Promote charm → Run workflow) once
per channel:

- `latest/edge` → `latest/stable`
- `<current-major>/edge` → `<current-major>/stable` (for example, `2/edge` → `2/stable`)

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
  `edge` and `stable`, and re-issue the token whenever a track is added, or
  releases fail with
  `Macaroon channel restrictions ... do not allow release to <channel>`.
- `--ttl` is in seconds (`2592000` = 30 days). When the token expires,
  publish/promote fail with `api-error: Invalid macaroon`; regenerate with the
  same command.

## Adding a new major (cutover runbook)

When `main` moves from major `N` to `N+1` (for example, v2 → v3), do these
**in order**:

1. **Create the new track and confirm the token covers it.**
   ```bash
   charmcraft create-track --name airbyte-k8s --track 3
   ```
   The track-name guardrail is `\d+(\.\d+)?`, registered with the Charmhub team.
   If `CHARMHUB_TOKEN` is channel-pinned (not all-channels), regenerate it to
   include `3/edge` and `3/stable` first, or the mirror step fails.

2. **Activate the outgoing major's `track/2`.** Bring `track/2` (kept dormant
   during the v2 era) up to `main`'s final v2 commit. Since `main`'s workflow
   triggers only on `main`, that commit has no `track/*` trigger, so add `track/*`
   back to the `on.push.branches` list in `track/2`'s own `publish_charm.yaml` and
   commit it on `track/2`. Land that activation commit through a pull request so
   `integration_test.yaml` runs for its tree; otherwise the push has no matching
   plan and fails instead of publishing. The push to `track/2` then publishes
   `2/edge`, making it the active v2 maintenance line. Do this **before** merging
   v3 into `main`, so `2/edge` does not go stale in the interim. (If the branch had
   been deleted, recreate it from the last v2 commit; see the seeding gotcha below.)

3. **Point `main` at the new major.** In `.github/workflows/publish_charm.yaml`,
   change `mirror-to-major-track`'s `destination-channel` from `2/edge` to `3/edge`.

4. **Merge v3 into `main`.** It now publishes to `latest/edge` and mirrors to
   `3/edge`; `track/2` independently publishes `2/edge` when pushed.

5. **Communicate the breaking change.** `latest` now points to v3, so anyone
   tracking `latest/stable` is auto-upgraded v2 → v3 at the next stable
   promotion. Announce it and document that v2 users should switch to `2/stable`.

## Known gotchas

- **A publish needs a recent integration-test run for that commit.** The publish
  reuses the charm/rock artifacts and plan from the `integration_test.yaml` run
  matching the commit's git tree ID. With no matching run, `get-plan` fails with
  `Failed to find integration test workflow run on tree id ...`; if a run is found
  but its plan artifact is missing (for example, the publish raced ahead of it),
  the error is instead `can't find plan artifact`. Those artifacts also expire
  (90 days by default), so an old commit may need a fresh run. Unblock by opening
  a throwaway pull request based on the branch to produce a new integration run,
  then publish.
- **Creating a track branch can skip/crash the publish run.** A branch-*creation*
  push sends `before=0000000...`; the reusable workflow's `Find changes` step runs
  `git diff <before> <after>` → `fatal: bad object` → the run fails. Seed a track
  with a two-step push so the publishing push is an *update*, not a creation.
  First push a commit whose workflow lacks the `track/*` trigger, which produces
  no run; then fast-forward the branch to the intended commit, which is an update
  and publishes normally:
  ```bash
  git push origin <OLD-COMMIT>:refs/heads/track/2
  git push origin <TARGET-COMMIT>:refs/heads/track/2
  ```
- **Token failures** surface as `api-error: Invalid macaroon` (expired) or
  `Macaroon channel restrictions ... do not allow release to <channel>` (scope).
  Both are fixed by regenerating `CHARMHUB_TOKEN` (see credentials above).
