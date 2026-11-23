set -e
# SSH refuses a private key that others can read, and a file mounted from Windows shows as
# readable by everyone. So the key is copied to a file of this container's own.
install -m 600 /work/.generated/id_ed25519 /tmp/id_ed25519

# Both hosts are reached through the VPN, as the deploy's client (.generated/vpn/ansible.ovpn,
# written by Terraform). The profile names each address that must go through the tunnel, one
# "route <address> 255.255.255.255" line each. The playbook runs only once every one of them
# does: on the emulator's Docker network a route that missed the tunnel would still reach the
# instance, and nothing else would notice.
profile=/work/.generated/vpn/ansible.ovpn
if [ ! -r "$profile" ]; then
    echo "No VPN profile at $profile: run \"terraform apply\" first." >&2
    exit 1
fi
openvpn --config "$profile" --daemon --log /tmp/openvpn.log
tunnelled_hosts="$(sed -n 's/^route \([0-9.]*\) 255\.255\.255\.255$/\1/p' "$profile")"
all_through_tunnel() {
    ip -brief link show tun0 > /dev/null 2>&1 || return 1
    for host in $tunnelled_hosts; do
        ip route get "$host" | grep -q ' dev tun0 ' || return 1
    done
}
# A new VPN server sets itself up at first boot, after the emulator's own setup of the
# instance: about four minutes after "terraform apply" ends. Hence the long wait.
wait_seconds=360
waited=0
until all_through_tunnel; do
    if [ "$waited" -ge "$wait_seconds" ]; then
        echo "The VPN did not come up in $wait_seconds seconds. OpenVPN's log:" >&2
        cat /tmp/openvpn.log >&2
        echo "On the VPN server: /var/log/vpn-user-data.log, or replace it: make replace-vpn" >&2
        exit 1
    fi
    if [ "$waited" -gt 0 ] && [ $((waited % 30)) -eq 0 ]; then
        echo "Waiting for the VPN ($waited s): a new VPN server takes a few minutes to set itself up."
    fi
    sleep 1
    waited=$((waited + 1))
done
echo "Through the VPN: $(echo $tunnelled_hosts) and the VPN server"

exec ansible-playbook --inventory /work/.generated/inventory.yml playbook.yml "$@"
