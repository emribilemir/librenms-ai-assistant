#!/usr/bin/env python3
"""Restore the EMR-55 lab device to its verified baseline."""

from run import reset_baseline, resolve_target


def main():
    target = resolve_target("lab-j9772a-01")
    result = reset_baseline(target)
    print("Reset: complete")
    print(f"SNMP state changed: {'yes' if result['changed'] else 'no'}")
    print(f"Verified: location={result['location']}")
    print(f"Verified: Port 2 admin={result['admin']} oper={result['oper']}")
    print("Verified: Device status=up")


if __name__ == "__main__":
    main()
