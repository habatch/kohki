#cloud-config
# Oracle Cloud Always Free — Paper 1 standing DFT worker
#
# Target shape: VM.Standard.A1.Flex, 4 OCPU, 24 GB RAM, Ubuntu 24.04 ARM.
# Paste this entire file (including the `#cloud-config` header) into the
# "user data" field when creating the instance.
#
# What this does:
#   1. Installs build / science tooling
#   2. Drops in micromamba (ARM64 prebuilt) and provisions a `qe` env
#      with quantum-espresso, ase, spglib from conda-forge
#   3. Stages SSSP Efficiency PBE pseudopotentials under /opt/pseudo
#   4. Creates a systemd user service `paper1-worker` that polls a
#      local queue directory and runs `pw.x` jobs
#   5. Leaves SSH working with the pubkey you supplied at launch

package_update: true
package_upgrade: false
packages:
  - curl
  - git
  - bzip2
  - build-essential
  - libopenblas-dev
  - openmpi-bin
  - libopenmpi-dev

write_files:
  - path: /etc/profile.d/paper1.sh
    permissions: "0644"
    content: |
      export MAMBA_ROOT_PREFIX=/opt/micromamba
      export PATH=/opt/micromamba/bin:$PATH
      export PSEUDO_DIR=/opt/pseudo/sssp_efficiency_pbe
      export OMP_NUM_THREADS=1

  - path: /usr/local/bin/paper1-run-job
    permissions: "0755"
    content: |
      #!/usr/bin/env bash
      set -euo pipefail
      # Job format: /var/lib/paper1/queue/<id>/{input.in,pseudo/,meta.json}
      # Output:     /var/lib/paper1/done/<id>/{output.out,bundle.zip}
      JOB_DIR="$1"
      ID=$(basename "$JOB_DIR")
      source /etc/profile.d/paper1.sh
      eval "$(/opt/micromamba/bin/micromamba shell hook -s bash)"
      micromamba activate qe

      cd "$JOB_DIR"
      mkdir -p tmp
      t0=$(date +%s)
      mpirun -n 4 --oversubscribe pw.x -in input.in > output.out 2>&1 || true
      t1=$(date +%s)

      DEST="/var/lib/paper1/done/$ID"
      mkdir -p "$DEST"
      cp input.in output.out "$DEST/"
      echo "{\"wall_seconds\": $((t1 - t0))}" > "$DEST/observables.json"
      mv "$JOB_DIR" "/var/lib/paper1/archived/$ID.$(date +%s)"

  - path: /etc/systemd/system/paper1-worker.service
    permissions: "0644"
    content: |
      [Unit]
      Description=Paper 1 DFT worker
      After=network-online.target
      [Service]
      Type=simple
      User=ubuntu
      ExecStart=/usr/local/bin/paper1-worker-loop
      Restart=always
      RestartSec=15
      [Install]
      WantedBy=multi-user.target

  - path: /usr/local/bin/paper1-worker-loop
    permissions: "0755"
    content: |
      #!/usr/bin/env bash
      set -euo pipefail
      mkdir -p /var/lib/paper1/queue /var/lib/paper1/done /var/lib/paper1/archived
      while true; do
        shopt -s nullglob
        jobs=(/var/lib/paper1/queue/*/)
        if [ ${#jobs[@]} -eq 0 ]; then
          sleep 15
          continue
        fi
        /usr/local/bin/paper1-run-job "${jobs[0]%/}" || true
      done

runcmd:
  # Storage for the worker
  - mkdir -p /var/lib/paper1/queue /var/lib/paper1/done /var/lib/paper1/archived
  - chown -R ubuntu:ubuntu /var/lib/paper1

  # Install micromamba (ARM64)
  - mkdir -p /opt/micromamba/bin
  - curl -L https://micro.mamba.pm/api/micromamba/linux-aarch64/latest | tar -xvj -C /opt/micromamba bin/micromamba
  - chown -R ubuntu:ubuntu /opt/micromamba

  # Provision the qe env as the ubuntu user
  - sudo -u ubuntu bash -lc '/opt/micromamba/bin/micromamba create -y -n qe -c conda-forge python=3.12 quantum-espresso=7.3 ase spglib mpich'

  # Stage SSSP Efficiency PBE
  - mkdir -p /opt/pseudo
  - curl -L -o /tmp/sssp.tar.gz "https://archive.materialscloud.org/record/file?filename=SSSP_1.3.0_PBE_efficiency.tar.gz&record_id=1732"
  - mkdir -p /opt/pseudo/sssp_efficiency_pbe
  - tar -xzf /tmp/sssp.tar.gz -C /opt/pseudo/sssp_efficiency_pbe --strip-components=1
  - chown -R ubuntu:ubuntu /opt/pseudo

  # Start the worker
  - systemctl daemon-reload
  - systemctl enable --now paper1-worker.service

final_message: |
  Paper 1 Oracle worker ready.
  Queue directory : /var/lib/paper1/queue
  Done directory  : /var/lib/paper1/done
  Service         : systemctl status paper1-worker
  To submit a job from your laptop:
      rsync -av ./job/ ubuntu@<ip>:/var/lib/paper1/queue/<job_id>/
