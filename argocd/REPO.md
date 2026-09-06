# Set the git repoURL (one-time)

`agent-fleet/` must live in its own git repository (same pattern as
`patroni-postgres-ha`). After creating the remote, replace the placeholder
`git@github.com:eleeyeah/agent-fleet.git` in **all** of:

- `argocd/root-app.yaml`
- `argocd/project/project.yaml` (`sourceRepos`)
- `argocd/project/applicationset.yaml`
- every `envs/local/*/application.yaml` that references the repo
  (`00-security`, `12-redis`, `20-agents`, and the `$values` ref sources in
  `10-gitea`, `11-nats`, `13-litellm`)

```bash
grep -rl "eleeyeah/agent-fleet" . | xargs sed -i 's#git@github.com:eleeyeah/agent-fleet.git#<YOUR-REPO-URL>#g'
```

If the repo is private, register it in Argo CD with a deploy key or HTTPS token —
same procedure as `patroni-postgres-ha/argocd/CONNECT-REPO.md`.
