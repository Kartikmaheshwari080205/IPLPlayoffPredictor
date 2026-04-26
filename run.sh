#!/usr/bin/env sh

set -u

case "${1-}" in
	-t)
		shift
		python refresh_ipl_data.py
		temp.exe "$@"
		exit $?
		;;
	-p)
		shift
		python refresh_ipl_data.py
		predictor.exe "$@"
		exit $?
		;;
	-h|--help)
		printf '%s\n' \
			'Usage:' \
			'  ./run.sh           Run refresh_ipl_data.py' \
			'  ./run.sh -t        Run temp.exe' \
			'  ./run.sh -p        Run predictor.exe'
		exit 0
		;;
	*)
		python refresh_ipl_data.py "$@"
		exit $?
		;;
esac