# The Ansible control node: Ansible doesn't run on Windows, so it runs here.
# An exact release, at or above the one that stops trusting the compromised eMudhra certificates.
FROM python:3.15.2-slim
# OpenVPN and iproute2: the playbook reaches the instances through the VPN (run-playbook.sh).
RUN apt-get update \
    && apt-get install -y --no-install-recommends openssh-client openvpn iproute2 \
    && rm -rf /var/lib/apt/lists/*
# ansible-lint checks the playbook ("make lint"); it runs here for the same reason.
COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

COPY run-playbook.sh /usr/local/bin/run-playbook.sh
# Named here because Ansible ignores an ansible.cfg it finds in a world-writable folder, which
# is how a folder mounted from Windows looks.
ENV ANSIBLE_CONFIG=/work/ansible/ansible.cfg
WORKDIR /work/ansible
ENTRYPOINT ["sh", "/usr/local/bin/run-playbook.sh"]
