"""Check bounded rainfall ownership without changing the serving process.

Run from the repository root: python scripts/check-rain-stream.py
This checks rainfall ingestion and UI summaries, not native physics or performance.
"""

import csv
import gc
import io
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import weakref
from zipfile import ZipFile

import numpy as np

from antiflood.data import load_scenarios
from antiflood.stream import RainHistory


def check():
    with TemporaryDirectory() as temporary:
        dataset = Path(temporary)
        rainfall = dataset / "raw/rainfall"
        rainfall.mkdir(parents=True)

        def write(rows):
            source = io.StringIO()
            writer = csv.writer(source)
            writer.writerow(["강우량계 코드", "자료수집 시각", "10분우량"])
            writer.writerows(rows)
            with ZipFile(rainfall / "rainfall_2022.zip", "w") as archive:
                archive.writestr("08월.csv", source.getvalue().encode("cp949"))

        rows = [
            ["a", "2022-08-08 00:09", "1"], ["b", "2022-08-08 00:09", "2"],
            ["a", "2022-08-08 00:19", "3"],  # Missing b splits the scenario.
            ["a", "2022-08-08 00:29", "4"], ["b", "2022-08-08 00:29", "5"],
        ]
        write(rows)
        gauges = [("a",), ("b",)]
        scenarios = load_scenarios(dataset, gauges)
        assert len(scenarios) == 2
        assert all(item.interval_count == 1 for item in scenarios)
        assert scenarios[0].start.minute == 20  # Largest peak remains the default.
        reader = scenarios[0].iter_intervals()
        interval = next(reader)
        np.testing.assert_array_equal(interval.gauge_mm, [4, 5])
        history = RainHistory(2)
        history.add(interval.gauge_mm)
        reference = weakref.ref(interval.gauge_mm)
        del interval
        gc.collect()
        assert reference() is None, "Reader/history retained the processed input array"
        reader.close()
        assert reader.gi_frame is None, "ZIP reader did not close on cancellation"
        for _ in range(6):
            history.add(np.zeros(2))
        assert len(history.window) == 6
        np.testing.assert_array_equal(history.hour_mm, [0, 0])
        np.testing.assert_allclose(history.decay_mm, np.array([4, 5]) * 0.8 ** 6)

        for label, bad in (
            ("conflict", rows[:2] + [["a", "2022-08-08 00:09", "9"]]),
            ("negative", [["a", "2022-08-08 00:09", "-1"]]),
            ("nonfinite", [["a", "2022-08-08 00:09", "nan"]]),
            ("unsorted", rows[2:] + rows[:2]),
        ):
            write(bad)
            try:
                load_scenarios(dataset, gauges)
            except ValueError:
                pass
            else:
                raise AssertionError(f"Accepted {label} rainfall")
    return {"scenario_gaps_and_peak": True, "processed_input_released": True,
            "cancel_closes_reader": True, "bounded_ui_hour_and_decay": True,
            "invalid_and_unsorted_input_rejected": True}


if __name__ == "__main__":
    print(json.dumps(check(), indent=2))
