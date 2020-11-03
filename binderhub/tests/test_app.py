"""Exercise the binderhub entrypoint"""
import sys
from subprocess import check_output


def test_help():
    check_output([sys.executable, "-m", "binderhub", "-h"])


def test_help_all():
    check_output([sys.executable, "-m", "binderhub", "--help-all"])
