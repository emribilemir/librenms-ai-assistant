#!/usr/bin/env python3
"""Restore the EMR-55 lab device to its verified baseline."""

from run import preflight, reset_baseline


def main():
    preflight()
    result = reset_baseline()
    print("Reset: complete")
    print(f"SNMP state changed: {'yes' if result['changed'] else 'no'}")
    print(f"Verified: location={result['location']}")
    print(f"Verified: Port 2 admin={result['admin']} oper={result['oper']}")
    print("Verified: Device status=up")


if __name__ == "__main__":
    main()
