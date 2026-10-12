"""Disable socket connections for the default deterministic QA profile."""
import runpy
import socket
import sys


def block_network():
    def refused(*args, **kwargs):
        raise RuntimeError("Network connections disabled in offline quality profile")
    socket.socket.connect = refused
    socket.socket.connect_ex = refused
    socket.create_connection = refused


def pytest_sessionstart(session):
    block_network()


if __name__ == "__main__":
    script, *arguments = sys.argv[1:]
    block_network()
    sys.argv = [script, *arguments]
    runpy.run_path(script, run_name="__main__")
