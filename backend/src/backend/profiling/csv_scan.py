"""Strict CSV validation and byte-level provenance; never repair source files."""

import codecs
import csv
import hashlib
from collections import Counter
from pathlib import Path


class SourceError(ValueError):
    pass


def fingerprint(path: Path) -> dict:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as stream:
        while block := stream.read(1024 * 1024):
            digest.update(block)
            size += len(block)
    return {"sha256": digest.hexdigest(), "size_bytes": size}


def scan_csv(path: Path) -> dict:
    result = {"file": path.name, **fingerprint(path)}
    with path.open("rb") as stream:
        prefix = stream.read(4)
    if prefix.startswith((codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE)):
        encoding = "utf-16"
    else:
        encoding = "utf-8-sig" if prefix.startswith(codecs.BOM_UTF8) else "utf-8"
    result["encoding"] = encoding
    # Full strict decoding, not a lossy or statistically guessed fallback.
    with path.open(encoding=encoding, errors="strict", newline="") as stream:
        physical_lines = sum(1 for _ in stream)
        stream.seek(0)
        sample = stream.read(65536)
        stream.seek(0)
        try:
            delimiter = csv.Sniffer().sniff(sample, delimiters=",;\t|").delimiter
        except csv.Error:
            try:
                delimiter = (
                    csv.Sniffer()
                    .sniff(sample.splitlines()[0], delimiters=",;\t|")
                    .delimiter
                )
            except (csv.Error, IndexError) as error:
                raise SourceError("cannot determine delimiter") from error
            result["delimiter_detection"] = (
                "header fallback; full-file validation follows"
            )
        else:
            result["delimiter_detection"] = "sample; full-file validation follows"
        result.update(
            {
                "delimiter": delimiter,
                "physical_lines": physical_lines,
                "quote": '"',
                "escape": '"',
                "doublequote": True,
            }
        )
        # Only detect the delimiter. Sniffer can misinfer doublequote=False from
        # a small sample even when RFC-style doubled quotes occur later.
        reader = csv.reader(
            stream, delimiter=delimiter, quotechar='"', doublequote=True, strict=True
        )
        headers = next(reader)
        if (
            not headers
            or any(not h for h in headers)
            or len(set(headers)) != len(headers)
        ):
            raise SourceError("empty or duplicate CSV headers")
        result["headers"] = headers
        records = valid = syntax_errors = 0
        widths = Counter()
        examples = []
        while True:
            start = reader.line_num + 1
            try:
                row = next(reader)
            except StopIteration:
                break
            except csv.Error as error:
                syntax_errors += 1
                if len(examples) < 5:
                    examples.append(
                        {
                            "line_start": start,
                            "line_end": reader.line_num,
                            "reason": str(error),
                        }
                    )
                continue
            records += 1
            widths[len(row)] += 1
            if len(row) == len(headers):
                valid += 1
            elif len(examples) < 5:
                examples.append(
                    {
                        "line_start": start,
                        "line_end": reader.line_num,
                        "field_count": len(row),
                    }
                )
        result.update(
            {
                "records_parsed": records,
                "structurally_valid_records": valid,
                "width_histogram": dict(sorted(widths.items())),
                "width_error_records": records - valid,
                "syntax_error_groups": syntax_errors,
                "error_examples": examples,
                "csv_valid": valid == records and syntax_errors == 0,
            }
        )
    return result
