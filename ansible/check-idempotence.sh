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
