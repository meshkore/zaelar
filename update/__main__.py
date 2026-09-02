"""`python -m update` — the release-time face of this module.

    python -m update           what this tree would report (JSON, exactly the endpoint's payload)
    python -m update bump      raise the build number by one and print it

`bump` is step 3 of the release procedure (`.meshkore/docs/ops/zaelar-cloud-release.md`): bump, commit,
then tag. The tag gate in `.github/workflows/release.yml` refuses a release whose build number did not
move, so forgetting it fails loudly at the door instead of silently shipping «version 24» twice.
"""
from __future__ import annotations

import json
import sys

from . import bump, state


def main(argv: list[str]) -> int:
    if argv and argv[0] == "bump":
        print(bump())
        return 0
    if argv:
        print(__doc__)
        return 2
    print(json.dumps(state(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
