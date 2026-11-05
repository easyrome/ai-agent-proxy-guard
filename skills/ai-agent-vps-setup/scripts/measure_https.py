#!/usr/bin/env python3
"""Bounded HTTPS measurements through one explicit route; no direct fallback."""

import argparse
import datetime
import ipaddress
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
import time
from urllib.parse import urlsplit


METRICS = {
    "http_status": "http_code",
    "bytes_received": "size_download",
    "connect_seconds": "time_connect",
    "tls_ready_seconds": "time_appconnect",
    "first_byte_seconds": "time_starttransfer",
    "total_seconds": "time_total",
}


class ArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        self.exit(1, "Invalid arguments; use --help for supported options.\n")


def percentile(values, fraction):
    values = sorted(values)
    if not values:
        return None
    rank = (len(values) - 1) * fraction
    low, high = math.floor(rank), math.ceil(rank)
    return round(values[low] + (values[high] - values[low]) * (rank - low), 6)


def clean_environment():
    return {
        key: value for key, value in os.environ.items()
        if key.lower() not in {"http_proxy", "https_proxy", "all_proxy", "no_proxy", "sslkeylogfile"}
    }


def validate(args):
    target = urlsplit(args.url)
    if target.scheme != "https" or not target.hostname or target.username is not None or target.password is not None or target.fragment:
        raise ValueError("Use an HTTPS URL without embedded credentials or a fragment.")
    _ = target.port
    if args.proxy:
        proxy = urlsplit(args.proxy)
        if proxy.scheme not in {"http", "socks5h"} or proxy.username is not None or proxy.password is not None:
            raise ValueError("Use an HTTP or SOCKS5H loopback proxy without embedded credentials.")
        if proxy.path not in {"", "/"} or proxy.query or proxy.fragment or not proxy.port:
            raise ValueError("Proxy URL must contain only scheme, loopback IP and port.")
        try:
            loopback = ipaddress.ip_address(proxy.hostname).is_loopback
        except ValueError:
            loopback = False
        if not loopback:
            raise ValueError("Proxy must use a literal loopback IP address.")
    if not 1 <= args.count <= 30 or not 1 <= args.max_bytes <= 1048576:
        raise ValueError("Count must be 1..30 and max-bytes 1..1048576.")
    if not math.isfinite(args.timeout) or not 1 <= args.timeout <= 60:
        raise ValueError("Timeout must be 1..60 seconds.")
    if not math.isfinite(args.interval) or not 0 <= args.interval <= 10:
        raise ValueError("Interval must be 0..10 seconds.")
    if args.cacert and not Path(args.cacert).is_file():
        raise ValueError("CA file is unavailable.")
    if args.output and Path(args.output).exists():
        raise ValueError("Output already exists; choose another file.")


def measure(args):
    environment = clean_environment()
    version = subprocess.run([args.curl, "-q", "--version"], capture_output=True, text=True, timeout=10, env=environment)
    match = re.match(r"curl (\d+)\.(\d+)\.(\d+)", version.stdout)
    if version.returncode or not match or tuple(map(int, match.groups())) < (8, 4, 0):
        raise ValueError("curl 8.4.0 or newer is required for bounded streaming transfers.")
    write_out = "{" + ",".join('"' + name + '":%{' + field + "}" for name, field in METRICS.items()) + "}"
    command = [
        args.curl, "-q", "--silent", "--show-error", "--proto", "=https",
        "--connect-timeout", str(min(10, args.timeout)), "--max-time", str(args.timeout),
        "--max-filesize", str(args.max_bytes), "--range", f"0-{args.max_bytes - 1}",
        "--output", os.devnull, "--write-out", write_out,
    ]
    if args.proxy:
        command += ["--proxy", args.proxy, "--noproxy", ""]
    else:
        command += ["--proxy", "", "--noproxy", "*"]
    if args.cacert:
        command += ["--cacert", args.cacert]
    command += ["--url", args.url]
    samples = []
    for index in range(args.count):
        sample = {"index": index + 1, "ok": False}
        try:
            completed = subprocess.run(command, capture_output=True, text=True, timeout=args.timeout + 5, env=environment)
            sample["curl_exit_code"] = completed.returncode
            try:
                parsed = json.loads(completed.stdout)
                if not all(isinstance(parsed[key], (int, float)) and math.isfinite(parsed[key]) and parsed[key] >= 0 for key in METRICS):
                    raise ValueError("Invalid metrics")
                sample.update({key: parsed[key] for key in METRICS})
                sample["ok"] = (
                    completed.returncode == 0 and parsed["http_status"] in {200, 206}
                    and 0 < parsed["bytes_received"] <= args.max_bytes and parsed["total_seconds"] > 0
                )
                if sample["ok"]:
                    sample["small_object_bytes_per_second"] = round(parsed["bytes_received"] / parsed["total_seconds"], 3)
                else:
                    sample["failure"] = "transport_or_http_or_size"
            except (ValueError, KeyError, TypeError):
                sample["failure"] = "metrics_unavailable"
        except subprocess.TimeoutExpired:
            sample["failure"] = "process_timeout"
        samples.append(sample)
        if index + 1 < args.count:
            time.sleep(args.interval)
    good = [sample for sample in samples if sample["ok"]]
    summary = {}
    for metric in ["first_byte_seconds", "total_seconds", "small_object_bytes_per_second"]:
        values = [sample[metric] for sample in good]
        summary[metric] = {"p50": percentile(values, .5), "p95": percentile(values, .95)}
    return {
        "schema": "https-measurement.v1",
        "recorded_at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "status": "measured" if len(good) == len(samples) else "incomplete",
        "route": "explicit_loopback_proxy" if args.proxy else "explicit_direct",
        "curl_version": ".".join(match.groups()),
        "attempt_count": len(samples), "success_count": len(good), "failure_count": len(samples) - len(good),
        "max_bytes_per_request": args.max_bytes,
        "summary_successful_samples_only": summary,
        "samples": samples,
    }


def main():
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--url", required=True, help="Approved HTTPS small-file endpoint")
    route = parser.add_mutually_exclusive_group(required=True)
    route.add_argument("--proxy", help="Explicit HTTP or SOCKS5H proxy on a literal loopback IP")
    route.add_argument("--direct", action="store_true", help="Explicit direct control; exposes client network to the endpoint")
    parser.add_argument("--count", type=int, default=10)
    parser.add_argument("--interval", type=float, default=1)
    parser.add_argument("--timeout", type=float, default=15)
    parser.add_argument("--max-bytes", type=int, default=65536)
    parser.add_argument("--curl", default="curl", help="Path to a trusted curl executable")
    parser.add_argument("--cacert", help="Optional trusted CA bundle; TLS verification remains enabled")
    parser.add_argument("--output", help="New JSON file; existing files are never overwritten")
    args = parser.parse_args()
    try:
        validate(args)
        result = measure(args)
        rendered = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
        if args.output:
            with open(args.output, "x", encoding="utf-8") as stream:
                stream.write(rendered)
        sys.stdout.write(rendered)
        return 0 if result["status"] == "measured" else 2
    except (ValueError, OSError, subprocess.SubprocessError):
        print("Measurement could not start or save. Check arguments, curl, CA and output path.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
