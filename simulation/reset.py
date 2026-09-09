#!/usr/bin/env python3
"""Restore the EMR-55 lab device to its verified baseline."""

import argparse

from run import TARGETS, reset_baseline


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", choices=TARGETS, default="lab-j9772a-01")
    args = parser.parse_args(argv)
    result = reset_baseline(args.target)
    print("Reset: complete")
    print(f"SNMP state changed: {'yes' if result['changed'] else 'no'}")
    print(f"Verified: location={result['location']}")
    print(f"Verified: Port 2 admin={result['admin']} oper={result['oper']}")
    print(f"Verified: Device status={result['baseline_status']}")


if __name__ == "__main__":
    main()
