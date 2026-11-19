set -e
# SSH refuses a private key that others can read, and a file mounted from Windows shows as
# readable by everyone. So the key is copied to a file of this container's own.
install -m 600 /work/.generated/id_ed25519 /tmp/id_ed25519
exec ansible-playbook --inventory /work/.generated/inventory.yml playbook.yml "$@"
