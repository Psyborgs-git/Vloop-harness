"""Python Control Plane (CP) entrypoint (scaffold).

Rust kernel is the infrastructure authority.
Python CP owns:
- agents/orchestration
- inference routing
- GUI/windows and user interactions
"""

from cp.bootstrap import bootstrap


def main() -> None:
    print("control-plane/main.py: scaffold booting...")
    bootstrap()


if __name__ == "__main__":
    main()
