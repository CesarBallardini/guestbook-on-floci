# Runs the playbook on an instance that is already deployed and fails unless nothing changed.
#
#   make idempotence      # from the folder above: deploys first, then runs this
#
# A task that reports "changed" on every run hides the real changes, and may restart the app
# on each deploy.
log_file=/tmp/idempotence.log
sh /usr/local/bin/run-playbook.sh "$@" > "$log_file" 2>&1
playbook_status=$?
cat "$log_file"
if [ "$playbook_status" -ne 0 ]; then
    echo "Idempotence check: the playbook failed." >&2
    exit "$playbook_status"
fi
# The recap has one line per host. Every one of them must say changed=0.
if grep -E 'changed=[0-9]+' "$log_file" | grep -v -q 'changed=0 '; then
    echo "Idempotence check FAILED: the tasks marked 'changed' above changed something on a second run." >&2
    exit 1
fi
echo "Idempotence check passed: a second run changed nothing."

# The VPN answers nobody without the profile's tls-crypt key. This sends what an OpenVPN client
# without it would send first (P_CONTROL_HARD_RESET_CLIENT_V2: opcode 7, key 0, a session id,
# no acknowledgements, packet id 0) and expects silence. A server without tls-crypt would
# answer it.
vpn_server="$(sed -n 's/^remote \([0-9.]*\) \([0-9]*\)$/\1 \2/p' /work/.generated/vpn/ansible.ovpn)"
if ! python3 -I - $vpn_server <<'PYTHON'
import os, socket, sys
host, port = sys.argv[1], int(sys.argv[2])
with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
    probe.settimeout(3)
    probe.sendto(bytes([7 << 3]) + os.urandom(8) + bytes(5), (host, port))
    try:
        probe.recvfrom(2048)
    except TimeoutError:
        sys.exit(0)
sys.exit(1)
PYTHON
then
    echo "VPN check FAILED: the server answered a packet without the tls-crypt key." >&2
    exit 1
fi
echo "VPN check passed: no answer without the tls-crypt key."
