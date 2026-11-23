# Rolls back across a migration and fails unless the older release runs on the newer schema.
#
#   make rollback-check     # from the folder above: deploys first (build A), then runs this
#
# Runs on this machine, from the repository's root, not in the Ansible container: it builds,
# and it starts that container. Steps:
#
#   1. Build B: a copy of app/ with one more migration, which adds a table nothing reads.
#   2. Deploy B: the playbook migrates the database to B's revision.
#   3. Roll back to A: A runs on B's schema, says so, and answers.
#   4. Run the playbook again with build A, as after any rollback: it must change nothing.
#
# Whatever happens, the end undoes B's migration (the one place a downgrade runs: no real
# release knows that revision, and the next real migration would fail on it), deploys A
# again, and removes B's release and its build.
set -eu
# Git Bash would turn the container's paths below into Windows paths.
export MSYS_NO_PATHCONV=1

work_dir=.generated/rollback-check
log_file="$work_dir/playbook.log"
# The migration B adds. Nothing in the app knows it.
b_revision=rollback_check
b_deploy_started=''

instance_container="floci-aws-ec2-$(terraform -chdir=terraform output -json instance |
    sed -n 's/.*"id": *"\([^"]*\)".*/\1/p')"
a_head="$(cd app && uv run --frozen alembic heads | awk '{ print $1 }')"

on_instance() {
    docker exec -i "$instance_container" sh -s -- "$@"
}

newest_release() {
    on_instance <<'EOF'
ls /opt/guestbook/releases | sort | tail -n 1
EOF
}

# The playbook's output goes to the log file, then to the screen: a pipe would hide its status.
run_in_ansible_container() {
    if docker compose run --rm --build "$@" > "$log_file" 2>&1; then
        cat "$log_file"
    else
        cat "$log_file"
        return 1
    fi
}

# What the playbook said last: "Release <id> runs. The database's schema is ...".
said() {
    grep -o "Release [0-9TZ]* runs\. The database's schema is [a-z ]*" "$log_file" | tail -n 1
}

fail() {
    echo "$1" >&2
    exit 1
}

restore() {
    status=$?
    set +e
    echo "--- Restoring: undo B's migration, deploy A, remove B"
    b_release=''
    if [ -n "$b_deploy_started" ]; then
        b_release="$(newest_release)"
        [ "$b_release" != "$newest_before_b" ] || b_release=''
    fi
    if [ -n "$b_release" ]; then
        on_instance "$b_release" "$a_head" <<'EOF'
set -e
release="/opt/guestbook/releases/$1"
set -a; . "$release/guestbook.env"; set +a
ini="$("$release/venv/bin/python" -c 'import guestbook, pathlib; print(pathlib.Path(guestbook.__file__).parent / "alembic.ini")')"
"$release/venv/bin/alembic" --config "$ini" downgrade "$2"
EOF
        [ $? -eq 0 ] || { echo "Could not undo B's migration: run 'alembic downgrade $a_head' from release $b_release." >&2; status=1; }
    fi
    ${MAKE:-make} deploy || status=1
    if [ -n "$b_release" ]; then
        on_instance "$b_release" <<'EOF' || status=1
rm -rf "/opt/guestbook/releases/$1"
EOF
    fi
    rm -rf "$work_dir"
    if [ "$status" -eq 0 ]; then
        echo "Rollback check passed: the older release ran on the newer schema."
    else
        echo "Rollback check FAILED." >&2
    fi
    exit "$status"
}
trap restore EXIT

echo "--- 1. Build B: app/ with migration '$b_revision' after '$a_head'"
rm -rf "$work_dir"
mkdir -p "$work_dir/app"
tar -C app --exclude=./.venv --exclude=./dist --exclude=__pycache__ --exclude=./.pytest_cache \
    --exclude=./.ruff_cache --exclude=./.pyrefly_cache --exclude=./.hypothesis --exclude=./htmlcov \
    --exclude=./.coverage -cf - . | tar -C "$work_dir/app" -xf -
cat > "$work_dir/app/guestbook/infrastructure/database/migrations/versions/$b_revision.py" <<EOF
"""A migration only the rollback check makes: a table nothing reads."""

import sqlalchemy as sa
from alembic import op

revision = '$b_revision'
down_revision = '$a_head'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Apply this revision."""
    op.create_table('rollback_check', sa.Column('id', sa.Integer, primary_key=True))


def downgrade() -> None:
    """Undo this revision."""
    op.drop_table('rollback_check')
EOF
${MAKE:-make} -C "$work_dir/app" build

echo "--- 2. Deploy B"
newest_before_b="$(newest_release)"
b_deploy_started=yes
run_in_ansible_container ansible -e "build_dir=/work/$work_dir/app/dist"
b_release_run="$(said | awk '{ print $2 }')"
said | grep -q 'is up to date' || fail "B's deploy did not leave the schema up to date."

echo "--- 3. Roll back to A"
app_log_lines="$(on_instance <<'EOF'
wc -l < /var/log/guestbook.log
EOF
)"
run_in_ansible_container ansible -e rollback=true
said | grep -q 'is ahead of it' || fail "After the rollback, the playbook did not say the schema is ahead."
[ "$(said | awk '{ print $2 }')" != "$b_release_run" ] || fail "The rollback still runs B."
# The shell, not curl, discards the page: with no path conversion, Git Bash's curl is handed
# "/dev/null" as is, and on Windows it can't write there.
for path in health ''; do
    curl --fail --silent --show-error --insecure "https://localhost:8443/$path" > /dev/null
done
on_instance "$app_log_lines" <<'EOF' || fail "Release A did not log that the schema is ahead of it."
tail -n "+$(($1 + 1))" /var/log/guestbook.log | grep -q "The database's schema is ahead of this release"
EOF

echo "--- 4. The playbook again, with build A: nothing changes"
run_in_ansible_container --entrypoint sh ansible /work/ansible/check-idempotence.sh
said | grep -q 'is ahead of it' || fail "The second run did not say the schema is ahead."
