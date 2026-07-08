from jarvis_core.cli import run_cli
from jarvis_core.runtime import build_runtime


def main():
    run_cli(build_runtime())


if __name__ == "__main__":
    main()
