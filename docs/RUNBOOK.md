# Runbook — day-2 operations

## First deployment (order matters)

1. **Patroni first**: sync `patroni-postgres-ha` — its values now declare the
   `litellm` + `agent_fleet` users and `litellm` + `agentstate` databases. Verify:

   ```bash
   kubectl get secret -n postgres-ha | grep -E 'litellm|agent_fleet'
   ```

2. **NetworkPolicy enforcement** (do this before trusting risk #4's mitigation):
   Flannel does not implement NetworkPolicy. Either migrate the CNI to Cilium, or
   install Calico in policy-only mode alongside Flannel (Canal):

   ```bash
   kubectl delete namespace kube-flannel
   kubectl apply -f https://raw.githubusercontent.com/projectcalico/calico/v3.28.2/manifests/canal.yaml
   kubectl get pods -n kube-system -l k8s-app=canal   # one Running per node
   ```

   Verify enforcement (self-contained, works before the fleet exists). The wget must
   TIME OUT; HTML output means policies are not enforced:

   ```bash
   kubectl create ns npol-check
   kubectl apply -f - <<'EOF'
   apiVersion: networking.k8s.io/v1
   kind: NetworkPolicy
   metadata:
     name: deny-all-egress
     namespace: npol-check
   spec:
     podSelector: {}
     policyTypes: [Egress]
   EOF
   kubectl run npol-test -n npol-check --rm -it --restart=Never --image=busybox:1.36 \
     -- wget -qO- --timeout=5 http://example.com && echo "POLICIES NOT ENFORCED"
   kubectl delete ns npol-check
   ```

3. **Insecure registry on every node** (containerd must trust Gitea's HTTP registry):

   ```bash
   # /etc/containerd/certs.d/192.168.178.20:30300/hosts.toml  (create on each node)
   [host."http://192.168.178.20:30300"]
     capabilities = ["pull", "resolve"]
     skip_verify = true
   ```

   Ensure `config_path = "/etc/containerd/certs.d"` is set in `/etc/containerd/config.toml`
   under `[plugins."io.containerd.grpc.v1.cri".registry]`, then `sudo systemctl restart containerd`.

4. `./scripts/bootstrap.sh` -> `./scripts/build-images.sh` -> Argo CD syncs wave 3.

## Watching a project

```bash
kubectl logs -n fleet-agents deploy/pm-agent -f          # decomposition + dispatch
kubectl logs -n fleet-agents deploy/backend-dev-agent -f # coding loop
kubectl logs -n fleet-agents deploy/reviewer-agent -f    # reviews + webhooks
# Follow one project end-to-end by correlation id:
kubectl logs -n fleet-agents -l app --all-containers --prefix | grep cid=<correlation_id>
```

Gitea UI: `http://192.168.178.20:30300` — PRs waiting for your approval are the queue
that matters. LiteLLM spend: `kubectl port-forward -n fleet-core svc/litellm 4000:4000`
-> `http://127.0.0.1:4000/ui` (login with the master key:
`kubectl get secret -n fleet-core litellm-master-key -o jsonpath='{.data.masterkey}' | base64 -d`).

## Budgets and keys

- **Agent hit its daily budget** (LiteLLM returns 429/400 budget errors in agent logs):
  either wait for the daily reset or raise it:

  ```bash
  curl -X POST http://127.0.0.1:4000/key/update \
    -H "Authorization: Bearer $MASTER_KEY" -H 'Content-Type: application/json' \
    -d '{"key": "<virtual key>", "max_budget": 20}'
  ```

- **Rotate the Anthropic key**: update the secret, restart LiteLLM. Agents are untouched.

  ```bash
  kubectl create secret generic -n fleet-core litellm-env-secret \
    --from-literal=ANTHROPIC_API_KEY=<new> --dry-run=client -o yaml | kubectl apply -f -
  kubectl rollout restart -n fleet-core deploy/litellm
  ```

- **Revoke a compromised agent key**: `POST /key/delete` with the master key, delete the
  `<agent>-litellm-key` secret, re-run `bootstrap.sh` (it regenerates only what's missing),
  restart the agent deployment.

## Stuck or misbehaving fleet

- **Task stuck IN_PROGRESS** (dev pod died mid-task): JetStream redelivers after
  `ack_wait` (2h) up to `max_deliver=2`; nothing to do unless urgent — then
  `kubectl rollout restart -n fleet-agents deploy/backend-dev-agent`.
- **Poison brief / bad decomposition loop**: the PM terminates the message after one
  failed processing attempt and opens an escalation issue. Fix the brief and resubmit.
- **Replay/inspect the queues**:

  ```bash
  kubectl exec -n fleet-core deploy/nats-box -- nats stream report
  kubectl exec -n fleet-core deploy/nats-box -- nats kv ls task-state
  kubectl exec -n fleet-core deploy/nats-box -- nats kv get task-state task.<project>.<task_id>
  ```

- **Re-dispatch a task manually** (after fixing whatever blocked it):

  ```bash
  kubectl exec -n fleet-core deploy/nats-box -- nats kv get task-state task.<p>.<t> --raw \
    | kubectl exec -i -n fleet-core deploy/nats-box -- nats pub tasks.ready
  ```

- **Emergency stop** (agents only; infra stays up):

  ```bash
  kubectl scale -n fleet-agents deploy --all --replicas=0
  ```

## CI gate verification

After the first PR, check the exact status-check context Gitea reports on the PR
(expected `ci / test`). If it differs, update `status_check_contexts` in
`fleet_common/gitea.py::protect_main` and re-run protection for existing repos.

## Known operational quirks

- First Gitea Actions run pulls runner images — the first CI can take minutes.
- If Argo CD shows `fleet-agents-local` degraded with ImagePullBackOff, images aren't
  in the registry yet (`./scripts/build-images.sh`) or containerd trust isn't configured.
- `bootstrap.sh` is idempotent: it skips anything that already exists; re-running it
  after a partial failure is the intended recovery path.
