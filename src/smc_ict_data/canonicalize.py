from __future__ import annotations

from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass, field
from decimal import Decimal


TimestampConverter = Callable[[str | int], int]
RowValidator = Callable[[list[str], int], None]


class SourceCanonicalizationError(ValueError):
    """The source ordering is too broken to continue deterministically."""


@dataclass(frozen=True, slots=True)
class SourceTimeAnomaly:
    line_number: int
    reason: str
    open_time_us: int | None
    source_close_time_us: int | None
    canonical_open_time_us: int | None
    details: str


@dataclass(slots=True)
class CanonicalizationStats:
    source_rows_read: int = 0
    exact_duplicates_removed: int = 0
    segmented_bar_count: int = 0
    segmented_source_rows_merged: int = 0
    quarantined_source_row_count: int = 0
    quarantined_canonical_bar_count: int = 0
    source_open_time_anomaly_count: int = 0
    source_open_time_max_late_us: int = 0
    source_close_time_anomaly_count: int = 0
    source_close_time_max_early_us: int = 0
    source_close_time_late_count: int = 0
    source_close_time_max_late_us: int = 0
    anomaly_examples: list[SourceTimeAnomaly] = field(default_factory=list)

    def record(
        self,
        *,
        line_number: int,
        reason: str,
        open_time_us: int | None,
        source_close_time_us: int | None,
        canonical_open_time_us: int | None,
        details: str,
    ) -> None:
        # Keep reports bounded while retaining exact source coordinates for audit.
        if len(self.anomaly_examples) < 1_000:
            self.anomaly_examples.append(
                SourceTimeAnomaly(
                    line_number=line_number,
                    reason=reason,
                    open_time_us=open_time_us,
                    source_close_time_us=source_close_time_us,
                    canonical_open_time_us=canonical_open_time_us,
                    details=details,
                )
            )


@dataclass(slots=True)
class _Segment:
    row: list[str]
    line_number: int
    open_time_us: int
    source_close_time_us: int


@dataclass(slots=True)
class _Bucket:
    start_us: int
    end_us: int
    segments: list[_Segment] = field(default_factory=list)
    invalid_reasons: set[str] = field(default_factory=set)


def _decimal_sum(left: str, right: str) -> str:
    return format(Decimal(left) + Decimal(right), "f")


def _merge_trade_segments(segments: list[_Segment], bucket_start_us: int) -> list[str]:
    merged = list(segments[0].row)
    for segment in segments[1:]:
        row = segment.row
        if Decimal(row[2]) > Decimal(merged[2]):
            merged[2] = row[2]
        if Decimal(row[3]) < Decimal(merged[3]):
            merged[3] = row[3]
        merged[4] = row[4]
        for index in (5, 7, 9, 10):
            merged[index] = _decimal_sum(merged[index], row[index])
        merged[8] = str(int(merged[8]) + int(row[8]))
        merged[6] = row[6]
        merged[11] = row[11]

    # Merged timestamps are written as microseconds. The normalizer's unit
    # detector accepts them without losing the exact source close evidence.
    merged[0] = str(bucket_start_us)
    merged[6] = str(segments[-1].source_close_time_us)
    return merged


def canonicalize_kline_rows(
    rows: Iterable[list[str]],
    *,
    duration_us: int,
    kind: str,
    timestamp_to_us: TimestampConverter,
    validate_row: RowValidator,
    stats: CanonicalizationStats,
) -> Iterator[list[str]]:
    """Yield fixed-boundary rows without inventing price information.

    Historical Binance Spot archives occasionally contain multiple contiguous
    source rows inside one nominal 1-minute bucket. Trade rows that are wholly
    contained in one bucket and exactly contiguous are merged losslessly.

    A row that crosses a canonical boundary, has an impossible close timestamp,
    starts after a missing bucket prefix, or overlaps another segment quarantines
    the affected canonical bucket. It is never clamped, shifted, price-filled or
    silently discarded. Price, OHLC and activity-field contract violations remain
    hard errors rather than being converted into missing observations.
    """

    if duration_us <= 0:
        raise ValueError("duration_us must be positive")

    current: _Bucket | None = None
    blocked_until_us = 0
    previous_raw_open_us: int | None = None
    previous_raw_fingerprint: tuple[str, ...] | None = None

    def finalize(bucket: _Bucket) -> list[str] | None:
        if not bucket.segments:
            return None

        if len(bucket.segments) > 1:
            last_close_us = bucket.segments[-1].source_close_time_us
            if bucket.end_us - last_close_us > 1_000:
                bucket.invalid_reasons.add("segmented_bucket_does_not_reach_end")
                stats.record(
                    line_number=bucket.segments[-1].line_number,
                    reason="segmented_bucket_does_not_reach_end",
                    open_time_us=bucket.segments[-1].open_time_us,
                    source_close_time_us=last_close_us,
                    canonical_open_time_us=bucket.start_us,
                    details=f"canonical_end={bucket.end_us}",
                )

        if bucket.invalid_reasons:
            stats.quarantined_canonical_bar_count += 1
            stats.quarantined_source_row_count += len(bucket.segments)
            return None

        if len(bucket.segments) == 1:
            return bucket.segments[0].row

        stats.segmented_bar_count += 1
        stats.segmented_source_rows_merged += len(bucket.segments) - 1
        return _merge_trade_segments(bucket.segments, bucket.start_us)

    for line_number, raw_row in enumerate(rows, start=1):
        stats.source_rows_read += 1
        if len(raw_row) < 12:
            raise SourceCanonicalizationError(
                f"expected at least 12 columns at source row {line_number}, got {len(raw_row)}"
            )
        row = [item.strip() for item in raw_row[:12]]
        fingerprint = tuple(row)

        try:
            open_time_us = timestamp_to_us(row[0])
            source_close_time_us = timestamp_to_us(row[6])
        except ValueError as exc:
            raise SourceCanonicalizationError(
                f"invalid source timestamp at row {line_number}: {exc}"
            ) from exc

        if previous_raw_open_us is not None:
            if open_time_us < previous_raw_open_us:
                raise SourceCanonicalizationError(
                    f"source rows are not monotonic at row {line_number}: "
                    f"{open_time_us} < {previous_raw_open_us}"
                )
            if open_time_us == previous_raw_open_us:
                if fingerprint == previous_raw_fingerprint:
                    stats.exact_duplicates_removed += 1
                    continue
                raise SourceCanonicalizationError(
                    f"conflicting duplicate open time {open_time_us} at source row {line_number}"
                )

        bucket_start_us = open_time_us - (open_time_us % duration_us)
        bucket_end_us = bucket_start_us + duration_us

        if current is not None and bucket_start_us != current.start_us:
            if bucket_start_us < current.start_us:
                raise SourceCanonicalizationError(
                    f"canonical source buckets are not monotonic at row {line_number}"
                )
            canonical = finalize(current)
            if canonical is not None:
                yield canonical
            current = None

        if current is None:
            current = _Bucket(start_us=bucket_start_us, end_us=bucket_end_us)
            if bucket_start_us < blocked_until_us:
                current.invalid_reasons.add("overlapped_by_previous_source_row")

        segment = _Segment(
            row=row,
            line_number=line_number,
            open_time_us=open_time_us,
            source_close_time_us=source_close_time_us,
        )
        current.segments.append(segment)

        open_late_us = open_time_us - bucket_start_us
        if open_late_us:
            stats.source_open_time_anomaly_count += 1
            stats.source_open_time_max_late_us = max(
                stats.source_open_time_max_late_us, open_late_us
            )
            stats.record(
                line_number=line_number,
                reason="non_aligned_open_time",
                open_time_us=open_time_us,
                source_close_time_us=source_close_time_us,
                canonical_open_time_us=bucket_start_us,
                details=f"open_late_us={open_late_us}",
            )

        if source_close_time_us < open_time_us:
            current.invalid_reasons.add("source_close_before_open")
            stats.record(
                line_number=line_number,
                reason="source_close_before_open",
                open_time_us=open_time_us,
                source_close_time_us=source_close_time_us,
                canonical_open_time_us=bucket_start_us,
                details=f"delta_us={source_close_time_us - open_time_us}",
            )
        elif source_close_time_us > bucket_end_us:
            late_us = source_close_time_us - bucket_end_us
            stats.source_close_time_late_count += 1
            stats.source_close_time_max_late_us = max(stats.source_close_time_max_late_us, late_us)
            current.invalid_reasons.add("source_row_crosses_canonical_boundary")
            blocked_until_us = max(
                blocked_until_us,
                (source_close_time_us // duration_us + 1) * duration_us,
            )
            stats.record(
                line_number=line_number,
                reason="source_row_crosses_canonical_boundary",
                open_time_us=open_time_us,
                source_close_time_us=source_close_time_us,
                canonical_open_time_us=bucket_start_us,
                details=f"close_late_us={late_us}; blocked_until_us={blocked_until_us}",
            )
        else:
            early_us = bucket_end_us - source_close_time_us
            if early_us > 1_000:
                stats.source_close_time_anomaly_count += 1
                stats.source_close_time_max_early_us = max(
                    stats.source_close_time_max_early_us, early_us
                )

        try:
            validate_row(row, line_number)
        except ValueError as exc:
            raise SourceCanonicalizationError(
                f"source payload contract violation at row {line_number}: {exc}"
            ) from exc

        if len(current.segments) == 1:
            if open_time_us != bucket_start_us:
                current.invalid_reasons.add("bucket_missing_aligned_start")
        else:
            previous = current.segments[-2]
            if kind != "kline":
                current.invalid_reasons.add("segmented_reference_kline")
            if open_time_us <= previous.open_time_us:
                current.invalid_reasons.add("overlapping_source_segments")
            elif open_time_us > previous.source_close_time_us + 1_000:
                current.invalid_reasons.add("gap_between_source_segments")
                stats.record(
                    line_number=line_number,
                    reason="gap_between_source_segments",
                    open_time_us=open_time_us,
                    source_close_time_us=source_close_time_us,
                    canonical_open_time_us=bucket_start_us,
                    details=(
                        f"previous_close_us={previous.source_close_time_us}; "
                        f"gap_us={open_time_us - previous.source_close_time_us}"
                    ),
                )
            elif open_time_us <= previous.source_close_time_us:
                current.invalid_reasons.add("overlapping_source_segments")

        previous_raw_open_us = open_time_us
        previous_raw_fingerprint = fingerprint

    if current is not None:
        canonical = finalize(current)
        if canonical is not None:
            yield canonical
