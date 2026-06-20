"""Python Control Plane entrypoint."""

from cp.bootstrap import bootstrap


def main() -> None:
    bootstrap()


if __name__ == "__main__":
    main()
