#!/bin/bash
# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.
#
# Runs the temporal-admin `cli` action to create a Temporal namespace, retrying until the action
# reports "command succeeded" (or the namespace already exists), or until TIMEOUT seconds elapse.
# Prints {"result": "<result>"} for the Terraform external data source.

MODEL_UUID=$1
APP_NAME=$2
NAMESPACE=$3
TIMEOUT=$4

LOG="/tmp/create-namespace.$$.log"
ERR="/tmp/create-namespace.$$.err"

if [ -z "$MODEL_UUID" ] || [ -z "$APP_NAME" ] || [ -z "$NAMESPACE" ] || [ -z "$TIMEOUT" ]; then
	echo '{"result": "bad_arguments"}'
	exit 0
fi

deadline=$(($(date +%s) + TIMEOUT))
result="unknown"
while [ "$(date +%s)" -lt "$deadline" ]; do
	out=$(juju run "$APP_NAME/0" cli args="operator namespace --namespace $NAMESPACE create" \
		--model "$MODEL_UUID" --format=json --wait=2m 2>"$ERR")
	echo "[$(date)] out=$out err=$(cat "$ERR")" >>"$LOG"

	result=$(echo "$out" | jq -r ".[\"$APP_NAME/0\"].results.result // \"unknown\"" 2>>"$LOG")

	# A fresh namespace yields "command succeeded"; a namespace that already exists (e.g. the
	# data source re-running on apply) is equally acceptable.
	if [ "$result" = "command succeeded" ] || grep -qi "already exists" "$ERR" <(echo "$out"); then
		result="command succeeded"
		break
	fi

	sleep 20
done

echo '{"result": "'"$result"'"}'
