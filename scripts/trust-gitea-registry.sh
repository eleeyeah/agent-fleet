#!/usr/bin/env bash
# Configure Docker (image push) and containerd (kubelet pull) for Gitea's HTTP
# NodePort registry. hosts.toml is ignored while CRI config_path is empty.
#
# Needs your sudo password on this machine and on tmkns-2 / tmkns-3.
# The agent cannot type that password — run this in your terminal:
#   ./scripts/trust-gitea-registry.sh && ./scripts/build-images.sh
set -euo pipefail

REGISTRY="${REGISTRY:-192.168.178.20:30300}"
WORKERS=(tmkns-2 tmkns-3)

set_cri_config_path() {
  python3 <<'PY'
from pathlib import Path
p = Path("/etc/containerd/config.toml")
text = p.read_text()
old = """    [plugins.\"io.containerd.grpc.v1.cri\".registry]
      config_path = \"\"
"""
new = """    [plugins.\"io.containerd.grpc.v1.cri\".registry]
      config_path = \"/etc/containerd/certs.d\"
"""
if old in text:
    p.write_text(text.replace(old, new, 1))
    print("containerd: set CRI registry config_path")
elif 'config_path = "/etc/containerd/certs.d"' in text:
    print("containerd: CRI registry config_path already set")
else:
    raise SystemExit("could not find CRI registry config_path in config.toml")
PY
}

write_hosts_toml() {
  mkdir -p "/etc/containerd/certs.d/${REGISTRY}"
  cat > "/etc/containerd/certs.d/${REGISTRY}/hosts.toml" <<EOF
[host."http://${REGISTRY}"]
  capabilities = ["pull", "resolve"]
  skip_verify = true
EOF
}

echo "==> this node ($(hostname)): Docker + containerd"
# daemon.json is root:root 0640 — read and write it entirely as root.
sudo python3 - "$REGISTRY" <<'PY'
import json, sys
from pathlib import Path
reg = sys.argv[1]
p = Path("/etc/docker/daemon.json")
data = {}
if p.exists() and p.stat().st_size:
    data = json.loads(p.read_text() or "{}")
regs = data.setdefault("insecure-registries", [])
if reg not in regs:
    regs.append(reg)
p.write_text(json.dumps(data, indent=2) + "\n")
print(f"docker: insecure-registries = {regs}")
PY
sudo systemctl restart docker

sudo bash -c "$(declare -f set_cri_config_path write_hosts_toml); REGISTRY='$REGISTRY'; set_cri_config_path; write_hosts_toml"
sudo systemctl restart containerd
echo "containerd restarted on $(hostname)"

# Workers need a TTY so remote sudo can prompt. The script is copied first
# so sudo's password is read from the TTY, not from a heredoc on stdin.
for h in "${WORKERS[@]}"; do
  echo "==> $h: containerd (sudo password for ${h})"
  ssh -o ConnectTimeout=10 "$h" "cat > /tmp/trust-gitea-registry-node.sh && chmod 700 /tmp/trust-gitea-registry-node.sh" <<EOF
set -euo pipefail
REGISTRY='$REGISTRY'
$(declare -f set_cri_config_path write_hosts_toml)
set_cri_config_path
write_hosts_toml
systemctl restart containerd
echo "containerd restarted on \$(hostname)"
rm -f /tmp/trust-gitea-registry-node.sh
EOF
  ssh -t -o ConnectTimeout=10 "$h" sudo bash /tmp/trust-gitea-registry-node.sh
done

echo
echo "Registry trust is in place. Next: ./scripts/build-images.sh"
