export runtest := '''
  python3 -mvenv --system-site-packages /mnt/venv
  /mnt/venv/bin/pip install --upgrade wheel
  /mnt/venv/bin/pip install --upgrade pip
  /mnt/venv/bin/pip install "/mnt/app[test]"
  cd /mnt/app
  /mnt/venv/bin/python -munittest
'''

dnf-setup := '''
  dnf update -y
  dnf install -y python3 sqlite python3-pip
'''

apt-setup := '''
  apt update
  apt upgrade -y
  apt install -y python3 sqlite3 python3-pip python3-venv
'''

apk-setup := '''
  apk update
  apk upgrade
  apk add python3 sqlite
'''

_list:
  @just --list

# Run all tests
test: python-tests debian-tests ubuntu-tests fedora-tests rhel-tests alpine-tests centos-stream-tests

# Run a test with a given setup in the given container
_run-test $container $setup="":
  #!/bin/sh
  set -euxf
  
  podman container run \
    --rm \
    -e PYTHONPATH=/mnt/app/src \
    --mount type=volume,destination=/mnt/venv \
    --mount type=bind,source=$(pwd),destination=/mnt/app,ro=true \
    --security-opt label=disable \
    "$container" \
    /bin/sh -c "
      set -euxf

      $setup
      $runtest
    "

# Test a particular python version
test-python version="latest": (_run-test ("docker.io/python:" + version))

# Test all supported python versions
python-tests: (test-python "3.6") (test-python "3.7") (test-python "3.8") (test-python "3.9") (test-python "3.10") (test-python "3.11") (test-python "3.12") (test-python "3.13") (test-python "3.14")

# Test a particular alpine version
test-alpine version="latest": (_run-test ("docker.io/alpine:" + version) apk-setup)

# Test all supported alpine versions
alpine-tests: (test-alpine "3.19") (test-alpine "3.20") (test-alpine "3.21") (test-alpine "3.22")

_test-apt image="debian:latest": (_run-test image apt-setup)

# Test a particular debian version
test-debian version="latest": (_test-apt ("docker.io/debian:" + version))

# Test a particular ubuntu version
test-ubuntu version="latest": (_test-apt ("docker.io/ubuntu:" + version))

# Test all supported debian versions
debian-tests: (test-debian "bullseye") (test-debian "bookworm") (test-debian "trixie")

# Test all supported ubuntu versions
ubuntu-tests: (test-ubuntu "20.04") (test-ubuntu "22.04") (test-ubuntu "24.04")

_test-dnf image="fedora:latest": (_run-test image dnf-setup)

# Test a particular fedora version
test-fedora version="latest": (_test-dnf ("docker.io/fedora:" + version))

# Test all supported fedora versions
fedora-tests: (test-fedora "42") (test-fedora "43")

# Test a particular RHEL version that is on dnf
test-rhel version="9": (_test-dnf ("docker.io/almalinux:" + version))

# Test all supported RHEL versions
rhel-tests: (test-rhel "8") (test-rhel "9") (test-rhel "10")

# Test a particular RHEL version
test-centos-stream version="stream10": (_test-dnf ("quay.io/centos/centos:" + version))

# Test all supported RHEL versions
centos-stream-tests: (test-centos-stream "stream9") (test-centos-stream "stream10")
