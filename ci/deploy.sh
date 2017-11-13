#!/bin/bash
# build the helm chart
# and upload it if we are building on master

set -e
if [[ "$TRAVIS_PULL_REQUEST" == "false" && "$TRAVIS_BRANCH" == "master" ]]; then
    openssl aes-256-cbc -K $encrypted_d8355cc3d845_key -iv $encrypted_d8355cc3d845_iv -in travis.enc -out travis -d
    chmod 0400 travis
    docker login -u ${DOCKER_USERNAME} -p "${DOCKER_PASSWORD}"
    export PUSH="--push"
fi
python ./helm-chart/build.py build --commit-range ${TRAVIS_COMMIT_RANGE} ${PUSH}
